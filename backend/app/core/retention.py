"""Data retention (decision record 07: privacy and data retention).

``purge_expired`` applies the retention rules in one pass:

* plate images of resolved exceptions are deleted ``anpr_image_retention_days``
  after the exception was resolved (an open exception keeps its image), and
  image files that no exception refers to are deleted once they are that old;
* transactions older than ``record_retention_days`` lose plate number, tag id
  and the vehicle and trip links, so only plaza, time and amount remain;
* resolved exceptions older than that lose their transaction link and free text;
* audit entries older than that are deleted.

Running it twice in a row changes nothing the second time. A real run writes
one ``retention_purge`` audit entry with the counts.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.audit import log_action
from app.models.audit import AuditLog
from app.models.exception import ExceptionRecord
from app.models.transaction import Transaction

IMAGE_NAME = re.compile(r"^[0-9a-f]{32}\.(jpg|png)$")


@dataclass
class RetentionReport:
    images_deleted: int = 0
    orphan_images_deleted: int = 0
    transactions_anonymised: int = 0
    exceptions_stripped: int = 0
    audit_entries_deleted: int = 0
    dry_run: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


def purge_expired(
    db: Session,
    *,
    now: datetime | None = None,
    image_days: int | None = None,
    record_days: int | None = None,
    image_dir: str | Path | None = None,
    dry_run: bool = False,
) -> RetentionReport:
    settings = get_settings()
    now = now or datetime.now(timezone.utc)
    image_days = settings.anpr_image_retention_days if image_days is None else image_days
    record_days = settings.record_retention_days if record_days is None else record_days
    directory = Path(image_dir or settings.plate_image_dir)
    if image_days < 0 or record_days < 0:
        raise ValueError("retention periods cannot be negative")
    if image_days > record_days:
        raise ValueError("image retention cannot be longer than record retention")

    image_cutoff = now - timedelta(days=image_days)
    record_cutoff = now - timedelta(days=record_days)
    report = RetentionReport(dry_run=dry_run)
    files_to_delete: list[Path] = []

    # An exception's retention clock starts when it was resolved; rows resolved
    # before resolved_at existed fall back to their creation time.
    resolved_time = func.coalesce(ExceptionRecord.resolved_at, ExceptionRecord.created_at)

    # 1. Plate images of resolved exceptions.
    expired = (
        db.query(ExceptionRecord)
        .filter(
            ExceptionRecord.image_path.isnot(None),
            ExceptionRecord.resolved.is_(True),
            resolved_time <= image_cutoff,
        )
        .all()
    )
    for record in expired:
        if IMAGE_NAME.match(record.image_path or ""):
            files_to_delete.append(directory / record.image_path)
        report.images_deleted += 1
        if not dry_run:
            record.image_path = None

    # 1b. Image files no exception refers to (for example after a crash between file and database).
    still_referenced = {
        name for (name,) in db.query(ExceptionRecord.image_path).filter(ExceptionRecord.image_path.isnot(None))
    }
    if directory.is_dir():
        for path in directory.iterdir():
            if not (path.is_file() and IMAGE_NAME.match(path.name)) or path.name in still_referenced:
                continue
            modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if modified <= image_cutoff:
                files_to_delete.append(path)
                report.orphan_images_deleted += 1

    # 2. Transactions: keep plaza, time and amount, drop everything that identifies the vehicle.
    old_transactions = db.query(Transaction).filter(
        Transaction.transaction_time <= record_cutoff,
        or_(
            Transaction.plate_number.isnot(None),
            Transaction.tag_id.isnot(None),
            Transaction.vehicle_id.isnot(None),
            Transaction.trip_id.isnot(None),
        ),
    )
    report.transactions_anonymised = old_transactions.count()

    # 3. Resolved exceptions: drop the transaction link and the free text.
    old_exceptions = db.query(ExceptionRecord).filter(
        ExceptionRecord.resolved.is_(True),
        resolved_time <= record_cutoff,
        or_(ExceptionRecord.transaction_id.isnot(None), ExceptionRecord.details.isnot(None)),
    )
    report.exceptions_stripped = old_exceptions.count()

    # 4. Audit entries.
    old_audit = db.query(AuditLog).filter(AuditLog.created_at <= record_cutoff)
    report.audit_entries_deleted = old_audit.count()

    if dry_run:
        return report

    old_transactions.update(
        {"plate_number": None, "tag_id": None, "vehicle_id": None, "trip_id": None},
        synchronize_session=False,
    )
    old_exceptions.update({"transaction_id": None, "details": None}, synchronize_session=False)
    old_audit.delete(synchronize_session=False)
    db.commit()

    # Files go only after the database change is safe: a leftover file is cleaned up as an orphan next run.
    for path in files_to_delete:
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    log_action(db, actor="system", action="retention_purge", resource_type="retention", metadata=report.as_dict())
    return report
