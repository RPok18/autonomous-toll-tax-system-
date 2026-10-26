from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.database import get_db
from app.api.deps import require_role
from app.models.enums import ExceptionType, UserRole
from app.models.exception import ExceptionRecord
from app.schemas.exception import ExceptionCreate, ExceptionRead

router = APIRouter(prefix="/exceptions", tags=["exceptions"])


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
    exception = ExceptionRecord(**payload.model_dump())
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
    response: Response,
    resolved: bool | None = None,
    plaza_id: uuid.UUID | None = None,
    transaction_id: uuid.UUID | None = None,
    exception_type: ExceptionType | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
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
    return (
        query.order_by(ExceptionRecord.created_at.desc(), ExceptionRecord.exception_id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


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

    exception.resolved = True
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