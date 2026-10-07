from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.database import get_db
from app.api.deps import require_role
from app.models.enums import UserRole
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
    limit: int = 50,
    db: Session = Depends(get_db),
) -> list[Transaction]:
    query = db.query(Transaction)
    if plaza_id is not None:
        query = query.filter_by(plaza_id=plaza_id)
    if is_exception is not None:
        query = query.filter_by(is_exception=is_exception)
    return query.order_by(Transaction.transaction_time.desc()).limit(limit).all()