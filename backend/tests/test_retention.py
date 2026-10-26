"""Data retention (decision record 07): what purge_expired removes, keeps and reports.

Needs the PostgreSQL test database from conftest.py.
"""
from __future__ import annotations

import os
import subprocess
import sys
import uuidL
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.config import get_settings
from app.core.retention import purge_expired
from app.models.audit import AuditLog
from app.models.enums import ExceptionType, IdentificationMethod, PaymentStatus
from app.models.exception import ExceptionRecord
from app.models.transaction import Transaction
from conftest import BACKEND_DIR
from helpers import add_vehicle, audit_rows

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


def days_ago(days: float) -> datetime:
    return NOW - timedelta(days=days)


def run(db, image_dir, **kwargs):
    report = purge_expired(db, now=NOW, image_days=7, record_days=365, image_dir=image_dir, **kwargs)
    db.expire_all()
    return report


def add_old_transaction(db, seed, vehicle, age_days) -> Transaction:
    transaction = Transaction(
        plaza_id=seed.plaza.plaza_id,
        lane_id="L1",
        vehicle_id=vehicle.vehicle_id,
        plate_number=vehicle.plate_number,
        tag_id="TAG-9",
        identification_method=IdentificationMethod.HYBRID_AGREED,
        amount_charged=Decimal("65.00"),
        payment_status=PaymentStatus.PAID,
        transaction_time=days_ago(age_days),
    )
    db.add(transaction)
    db.commit()
    return transaction


def add_dated_exception(db, seed, *, resolved_days_ago=None, created_days_ago=1, image=None, transaction=None,
                        details=None, legacy=False) -> ExceptionRecord:
    resolved = resolved_days_ago is not None
    record = ExceptionRecord(
        plaza_id=seed.plaza.plaza_id,
        lane_id="L1",
        exception_type=ExceptionType.TAG_MISMATCH,
        resolved=resolved,
        resolved_at=None if (legacy or not resolved) else days_ago(resolved_days_ago),
        created_at=days_ago(created_days_ago if not legacy else resolved_days_ago),
        image_path=image,
        details=details,
        transaction_id=transaction.transaction_id if transaction else None,
    )
    db.add(record)
    db.commit()
    return record


def image_file(directory, age_days=0.0) -> str:
    name = f"{uuid.uuid4().hex}.jpg"
    path = directory / name
    path.write_bytes(b"\xff\xd8\xff-image")
    stamp = days_ago(age_days).timestamp()
    os.utime(path, (stamp, stamp))
    return name


# ---------------------------------------------------------------- transactions

def test_old_transactions_lose_identifiers_but_keep_plaza_time_and_amount(db, seed, tmp_path):
    vehicle = add_vehicle(db)
    old = add_old_transaction(db, seed, vehicle, 366)
    recent = add_old_transaction(db, seed, vehicle, 364)

    report = run(db, tmp_path)

    assert report.transactions_anonymised == 1
    db.refresh(old)
    db.refresh(recent)
    assert (old.plate_number, old.tag_id, old.vehicle_id, old.trip_id) == (None, None, None, None)
    assert old.amount_charged == Decimal("65.00")
    assert old.plaza_id == seed.plaza.plaza_id
    assert old.transaction_time == days_ago(366)
    assert recent.plate_number == vehicle.plate_number and recent.vehicle_id == vehicle.vehicle_id


# ---------------------------------------------------------------- exceptions

def test_old_resolved_exceptions_lose_the_transaction_link_and_free_text(db, seed, tmp_path):
    vehicle = add_vehicle(db)
    transaction = add_old_transaction(db, seed, vehicle, 10)
    old = add_dated_exception(db, seed, resolved_days_ago=366, transaction=transaction, details="plate MH12AB1234")
    recent = add_dated_exception(db, seed, resolved_days_ago=10, transaction=transaction, details="keep")
    still_open = add_dated_exception(db, seed, created_days_ago=400, transaction=transaction, details="open case")

    report = run(db, tmp_path)

    assert report.exceptions_stripped == 1
    for record in (old, recent, still_open):
        db.refresh(record)
    assert (old.transaction_id, old.details) == (None, None)
    assert old.exception_type == ExceptionType.TAG_MISMATCH  # the row stays for statistics
    assert recent.details == "keep" and recent.transaction_id == transaction.transaction_id
    assert still_open.details == "open case"  # an open exception is never touched, however old


def test_exceptions_resolved_before_resolved_at_existed_use_their_creation_time(db, seed, tmp_path):
    legacy = add_dated_exception(db, seed, resolved_days_ago=400, legacy=True, details="old text")

    report = run(db, tmp_path)

    assert report.exceptions_stripped == 1
    db.refresh(legacy)
    assert legacy.details is None


# ---------------------------------------------------------------- images

def test_images_are_deleted_seven_days_after_the_exception_is_resolved(db, seed, tmp_path):
    expired = image_file(tmp_path)
    fresh = image_file(tmp_path)
    open_case = image_file(tmp_path)
    a = add_dated_exception(db, seed, resolved_days_ago=8, image=expired)
    b = add_dated_exception(db, seed, resolved_days_ago=6, image=fresh)
    c = add_dated_exception(db, seed, created_days_ago=30, image=open_case)  # unresolved, old photo

    report = run(db, tmp_path)

    assert report.images_deleted == 1
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted([fresh, open_case])
    for record in (a, b, c):
        db.refresh(record)
    assert a.image_path is None
    assert b.image_path == fresh
    assert c.image_path == open_case  # an open exception keeps its image


def test_orphan_image_files_are_deleted_when_old_enough_and_other_files_are_left_alone(db, seed, tmp_path):
    old_orphan = image_file(tmp_path, age_days=10)
    new_orphan = image_file(tmp_path, age_days=1)
    for name in ("notes.txt", "plate.jpg"):  # not server-generated names: never touched
        path = tmp_path / name
        path.write_text("keep me")
        stamp = days_ago(100).timestamp()
        os.utime(path, (stamp, stamp))

    report = run(db, tmp_path)

    assert report.orphan_images_deleted == 1
    left = sorted(p.name for p in tmp_path.iterdir())
    assert old_orphan not in left and new_orphan in left
    assert "notes.txt" in left and "plate.jpg" in left


def test_a_database_row_pointing_at_a_missing_file_does_not_stop_the_purge(db, seed, tmp_path):
    record = add_dated_exception(db, seed, resolved_days_ago=30, image=f"{uuid.uuid4().hex}.jpg")

    report = run(db, tmp_path)

    assert report.images_deleted == 1
    db.refresh(record)
    assert record.image_path is None


# ---------------------------------------------------------------- audit log

def test_old_audit_entries_are_deleted_and_the_purge_itself_is_audited(db, seed, tmp_path):
    db.add(AuditLog(actor="u1", action="login", created_at=days_ago(400)))
    db.add(AuditLog(actor="u2", action="login", created_at=days_ago(1)))
    db.commit()

    report = run(db, tmp_path)

    assert report.audit_entries_deleted == 1
    remaining = {(row.actor, row.action) for row in db.query(AuditLog).all()}
    assert ("u1", "login") not in remaining
    assert ("u2", "login") in remaining
    purge_rows = audit_rows(db, "retention_purge")
    assert len(purge_rows) == 1
    assert purge_rows[0].actor == "system"
    assert purge_rows[0].metadata_json["audit_entries_deleted"] == 1


# ---------------------------------------------------------------- behaviour of the run itself

def test_dry_run_reports_but_changes_nothing(db, seed, tmp_path):
    vehicle = add_vehicle(db)
    old = add_old_transaction(db, seed, vehicle, 400)
    name = image_file(tmp_path)
    add_dated_exception(db, seed, resolved_days_ago=30, image=name)
    db.add(AuditLog(actor="u1", action="login", created_at=days_ago(400)))
    db.commit()

    report = run(db, tmp_path, dry_run=True)

    assert report.dry_run is True
    assert (report.transactions_anonymised, report.images_deleted, report.audit_entries_deleted) == (1, 1, 1)
    db.refresh(old)
    assert old.plate_number == vehicle.plate_number
    assert (tmp_path / name).exists()
    assert db.query(AuditLog).count() == 1
    assert audit_rows(db, "retention_purge") == []


def test_running_twice_changes_nothing_the_second_time(db, seed, tmp_path):
    vehicle = add_vehicle(db)
    add_old_transaction(db, seed, vehicle, 400)
    add_dated_exception(db, seed, resolved_days_ago=400, details="x", image=image_file(tmp_path))
    db.add(AuditLog(actor="u1", action="login", created_at=days_ago(400)))
    db.commit()
    first = run(db, tmp_path)
    assert first.transactions_anonymised == 1

    second = run(db, tmp_path)

    assert second.as_dict() == {
        "images_deleted": 0,
        "orphan_images_deleted": 0,
        "transactions_anonymised": 0,
        "exceptions_stripped": 0,
        "audit_entries_deleted": 0,
        "dry_run": False,
    }


def test_image_retention_longer_than_record_retention_is_refused(db, tmp_path):
    with pytest.raises(ValueError):
        purge_expired(db, now=NOW, image_days=30, record_days=7, image_dir=tmp_path)


def test_defaults_match_the_decision_record():
    settings = get_settings()
    assert settings.anpr_image_retention_days == 7
    assert settings.record_retention_days == 365


def test_command_line_script_dry_run(db, db_engine):
    env = {**os.environ, "DATABASE_URL": db_engine.url.render_as_string(hide_password=False)}

    result = subprocess.run(
        [sys.executable, str(BACKEND_DIR / "scripts" / "run_retention.py"), "--dry-run"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "DRY RUN" in result.stdout
    assert "transactions_anonymised: 0" in result.stdout
