from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.database import get_db
from app.api.deps import require_role
from app.models.enums import PaymentStatus, UserRole
from app.models.transaction import Transaction
from app.schemas.transaction import TransactionCreate, TransactionRead

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post(
    "",
    response_model=TransactionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.OPERATOR, UserRole.ADMIN))],
)
def create_transaction(
    payload: TransactionCreate,
    db: Session = Depends(get_db),
    identity=Depends(require_role(UserRole.OPERATOR, UserRole.ADMIN)),
) -> Transaction:
    transaction = Transaction(**payload.model_dump())
    db.add(transaction)
    db.commit()
    db.refresh(transaction)

    log_action(
        db,
        actor=str(identity.get("sub")),
        action="create_transaction",
        resource_type="transaction",
        resource_id=str(transaction.transaction_id),
    )
    return transaction


@router.get(
    "/{transaction_id}",
    response_model=TransactionRead,
    dependencies=[Depends(require_role(UserRole.OPERATOR, UserRole.ADMIN, UserRole.AUDITOR))],
)
def get_transaction(transaction_id: uuid.UUID, db: Session = Depends(get_db)) -> Transaction:
    transaction = db.query(Transaction).filter_by(transaction_id=transaction_id).first()
    if transaction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return transaction


@router.get(
    "",
    response_model=list[TransactionRead],
    dependencies=[Depends(require_role(UserRole.OPERATOR, UserRole.ADMIN, UserRole.AUDITOR))],
)
def list_transactions(
    plaza_id: uuid.UUID | None = None,
    is_exception: bool | None = None,
    payment_status: PaymentStatus | None = None,
    date_from: datetime | None = Query(None, alias="from"),
    date_to: datetime | None = Query(None, alias="to"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    response: Response = None,
    db: Session = Depends(get_db),
) -> list[Transaction]:
    query = db.query(Transaction)
    if plaza_id is not None:
        query = query.filter_by(plaza_id=plaza_id)
    if is_exception is not None:
        query = query.filter_by(is_exception=is_exception)
    if payment_status is not None:
        query = query.filter_by(payment_status=payment_status)
    if date_from is not None:
        query = query.filter(Transaction.transaction_time >= date_from)
    if date_to is not None:
        query = query.filter(Transaction.transaction_time < date_to)
    # Total number of matching rows, so the dashboard can say "50 of 1 234".
    response.headers["X-Total-Count"] = str(query.count())
    return query.order_by(Transaction.transaction_time.desc()).offset(offset).limit(limit).all()