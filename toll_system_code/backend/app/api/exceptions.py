from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.audit import log_action
from app.database import get_db
from app.api.deps import require_role
from app.models.enums import ExceptionType, UserRole
from app.models.exception import ExceptionRecord
from app.schemas.exception import ExceptionCreate, ExceptionRead

router = APIRouter(prefix="/exceptions", tags=["exceptions"])

# Plate images (decision record 07): stored only for exception passes, shown only to these roles.
IMAGE_VIEW_ROLES = (UserRole.ADMIN, UserRole.OPERATOR, UserRole.AUDITOR)
IMAGE_UPLOAD_ROLES = (UserRole.ADMIN, UserRole.OPERATOR)

_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_IMAGE_NAME = re.compile(r"^[0-9a-f]{32}\.(jpg|png)$")


def _image_type(data: bytes) -> tuple[str, str] | None:
    """(file extension, media type) judged from the file's own bytes, never from the client's headers."""
    if data.startswith(_JPEG_MAGIC):
        return ".jpg", "image/jpeg"
    if data.startswith(_PNG_MAGIC):
        return ".png", "image/png"
    return None


def _stored_image(record: ExceptionRecord) -> Path | None:
    """Path of the record's image file if it is a server-generated name inside the image folder."""
    name = record.image_path
    if not name or not _IMAGE_NAME.match(name):
        return None
    directory = Path(get_settings().plate_image_dir).resolve()
    path = (directory / name).resolve()
    if path.parent != directory:
        return None
    return path


def _remove_file(path: Path | None) -> None:
    if path is not None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


@router.post(
    "",
    response_model=ExceptionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.OPERATOR, UserRole.ADMIN))],
)
def create_exception(
    payload: ExceptionCreate,
    db: Session = Depends(get_db),
    identity=Depends(require_role(UserRole.OPERATOR, UserRole.ADMIN)),
) -> ExceptionRecord:
    values = payload.model_dump()
    if values["resolved"]:
        values["resolved_at"] = datetime.now(timezone.utc)
    exception = ExceptionRecord(**values)
    db.add(exception)
    db.commit()
    db.refresh(exception)

    log_action(
        db,
        actor=str(identity.get("sub")),
        action="create_exception",
        resource_type="exception",
        resource_id=str(exception.exception_id),
    )
    return exception


@router.get(
    "/{exception_id}",
    response_model=ExceptionRead,
    dependencies=[Depends(require_role(UserRole.OPERATOR, UserRole.ADMIN, UserRole.AUDITOR))],
)
def get_exception(exception_id: uuid.UUID, db: Session = Depends(get_db)) -> ExceptionRecord:
    exception = db.query(ExceptionRecord).filter_by(exception_id=exception_id).first()
    if exception is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exception not found")
    return exception


@router.get(
    "",
    response_model=list[ExceptionRead],
    dependencies=[Depends(require_role(UserRole.OPERATOR, UserRole.ADMIN, UserRole.AUDITOR))],
)
def list_exceptions(
    resolved: bool | None = None,
    plaza_id: uuid.UUID | None = None,
    transaction_id: uuid.UUID | None = None,
    exception_type: ExceptionType | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    response: Response = None,
    db: Session = Depends(get_db),
) -> list[ExceptionRecord]:
    query = db.query(ExceptionRecord)
    if resolved is not None:
        query = query.filter_by(resolved=resolved)
    if plaza_id is not None:
        query = query.filter_by(plaza_id=plaza_id)
    if transaction_id is not None:
        query = query.filter_by(transaction_id=transaction_id)
    if exception_type is not None:
        query = query.filter_by(exception_type=exception_type)
    response.headers["X-Total-Count"] = str(query.count())
    return query.order_by(ExceptionRecord.created_at.desc()).offset(offset).limit(limit).all()


@router.patch(
    "/{exception_id}/resolve",
    response_model=ExceptionRead,
    dependencies=[Depends(require_role(UserRole.OPERATOR, UserRole.ADMIN))],
)
def resolve_exception(
    exception_id: uuid.UUID,
    db: Session = Depends(get_db),
    identity=Depends(require_role(UserRole.OPERATOR, UserRole.ADMIN)),
) -> ExceptionRecord:
    exception = db.query(ExceptionRecord).filter_by(exception_id=exception_id).first()
    if exception is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exception not found")

    if not exception.resolved:
        # The image retention clock starts here, so resolving twice must not restart it.
        exception.resolved = True
        exception.resolved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(exception)

    log_action(
        db,
        actor=str(identity.get("sub")),
        action="resolve_exception",
        resource_type="exception",
        resource_id=str(exception_id),
    )
    return exception


@router.post(
    "/{exception_id}/image",
    response_model=ExceptionRead,
    status_code=status.HTTP_201_CREATED,
)
def upload_plate_image(
    exception_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    identity: dict = Depends(require_role(*IMAGE_UPLOAD_ROLES)),
) -> ExceptionRecord:
    """Attach the plate image of an open exception. A normal pass never gets an image."""
    record = db.query(ExceptionRecord).filter_by(exception_id=exception_id).with_for_update().first()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exception not found")
    if record.resolved:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Exception is already resolved")

    settings = get_settings()
    data = file.file.read(settings.max_plate_image_bytes + 1)
    if len(data) > settings.max_plate_image_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Image is too large")
    detected = _image_type(data)
    if detected is None:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Only JPEG and PNG images are accepted")

    directory = Path(settings.plate_image_dir)
    directory.mkdir(parents=True, exist_ok=True)
    new_path = directory / f"{uuid.uuid4().hex}{detected[0]}"
    new_path.write_bytes(data)

    previous = _stored_image(record)
    record.image_path = new_path.name
    try:
        db.commit()
    except Exception:
        _remove_file(new_path)
        raise
    _remove_file(previous)
    db.refresh(record)

    log_action(
        db,
        actor=str(identity["username"]),
        action="upload_plate_image",
        resource_type="exception",
        resource_id=str(exception_id),
    )
    return record


@router.get("/{exception_id}/image", response_class=FileResponse)
def get_plate_image(
    exception_id: uuid.UUID,
    db: Session = Depends(get_db),
    identity: dict = Depends(require_role(*IMAGE_VIEW_ROLES)),
) -> FileResponse:
    """Return the plate image. Every successful view is written to the audit log."""
    record = db.query(ExceptionRecord).filter_by(exception_id=exception_id).first()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exception not found")

    path = _stored_image(record)
    if path is None or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")

    log_action(
        db,
        actor=str(identity["username"]),
        action="view_plate_image",
        resource_type="exception",
        resource_id=str(exception_id),
    )
    media_type = "image/png" if path.suffix == ".png" else "image/jpeg"
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "no-store"})
