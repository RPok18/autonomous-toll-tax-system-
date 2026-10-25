from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.config import get_settings
from app.database import get_db
from app.api.deps import require_role
from app.models.enums import UserRole
from app.models.exception import ExceptionRecord
from app.schemas.exception import ExceptionCreate, ExceptionRead

router = APIRouter(prefix="/exceptions", tags=["exceptions"])
IMAGE_NAME = re.compile(r"^[0-9a-f]{32}\.(jpg|png)$")
JPEG_SIGNATURE = b"\xff\xd8\xff"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


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
        actor=str(identity["sub"]),
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
    limit: int = 50,
    db: Session = Depends(get_db),
) -> list[ExceptionRecord]:
    query = db.query(ExceptionRecord)
    if resolved is not None:
        query = query.filter_by(resolved=resolved)
    if plaza_id is not None:
        query = query.filter_by(plaza_id=plaza_id)
    return query.order_by(ExceptionRecord.created_at.desc()).limit(limit).all()


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
        exception.resolved = True
        exception.resolved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(exception)

    log_action(
        db,
        actor=str(identity["sub"]),
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
async def upload_exception_image(
    exception_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    identity=Depends(require_role(UserRole.OPERATOR, UserRole.ADMIN)),
) -> ExceptionRecord:
    exception = (
        db.query(ExceptionRecord)
        .filter_by(exception_id=exception_id)
        .with_for_update()
        .first()
    )
    if exception is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exception not found")
    if exception.resolved:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Resolved exceptions cannot receive images")

    image_bytes = await file.read(get_settings().max_plate_image_bytes + 1)
    if len(image_bytes) > get_settings().max_plate_image_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Image is too large")

    if image_bytes.startswith(JPEG_SIGNATURE):
        extension = "jpg"
    elif image_bytes.startswith(PNG_SIGNATURE):
        extension = "png"
    else:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported image format")

    directory = Path(get_settings().plate_image_dir)
    directory.mkdir(parents=True, exist_ok=True)
    image_name = f"{uuid.uuid4().hex}.{extension}"
    image_path = directory / image_name
    try:
        with image_path.open("xb") as image_file:
            image_file.write(image_bytes)
    except OSError:
        image_path.unlink(missing_ok=True)
        raise

    previous_image = exception.image_path
    exception.image_path = image_name
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        image_path.unlink(missing_ok=True)
        raise
    db.refresh(exception)

    if previous_image and IMAGE_NAME.fullmatch(previous_image):
        (directory / previous_image).unlink(missing_ok=True)

    log_action(
        db,
        actor=str(identity["sub"]),
        action="upload_plate_image",
        resource_type="exception",
        resource_id=str(exception_id),
    )
    return exception


@router.get(
    "/{exception_id}/image",
)
def view_exception_image(
    exception_id: uuid.UUID,
    db: Session = Depends(get_db),
    identity=Depends(require_role(UserRole.OPERATOR, UserRole.ADMIN, UserRole.AUDITOR)),
) -> Response:
    exception = db.query(ExceptionRecord).filter_by(exception_id=exception_id).first()
    if exception is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exception not found")
    if not exception.image_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    if not IMAGE_NAME.fullmatch(exception.image_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")

    extension = Path(exception.image_path).suffix
    image_path = Path(get_settings().plate_image_dir) / exception.image_path
    if image_path.is_symlink() or not image_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    image_bytes = image_path.read_bytes()

    log_action(
        db,
        actor=str(identity["sub"]),
        action="view_plate_image",
        resource_type="exception",
        resource_id=str(exception_id),
    )
    media_type = "image/jpeg" if extension == ".jpg" else "image/png"
    return Response(
        content=image_bytes,
        media_type=media_type,
        headers={"Cache-Control": "no-store"},
    )