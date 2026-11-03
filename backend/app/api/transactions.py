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
from app.schemas.vehicle import normalize_plate_number

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _list_transaction_history(
    db: Session,
    *,
    vehicle_id: uuid.UUID | None = None,
    transaction_id: uuid.UUID | None = None,
    plate_number: str | None = None,
    plaza_id: uuid.UUID | None = None,
    payment_status: PaymentStatus | None = None,
    is_exception: bool | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    from_time: datetime | None = None,
    to_time: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
    response: Response | None = None,
) -> list[Transaction]:
    for field_name, value in (
        ("start_time", start_time),
        ("end_time", end_time),
        ("from", from_time),
        ("to", to_time),
    ):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"{field_name} must include a timezone",
            )
    if start_time is not None and end_time is not None and start_time > end_time:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="start_time must be before or equal to end_time",
        )
    if from_time is not None and to_time is not None and from_time > to_time:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="'from' must be before or equal to 'to'",
        )

    normalized_plate = normalize_plate_number(plate_number) if plate_number is not None else None
    if plate_number is not None and not normalized_plate:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="plate_number must contain letters or digits",
        )

    filters = {
        key: value
        for key, value in {
            "vehicle_id": vehicle_id,
            "transaction_id": transaction_id,
            "plate_number": normalized_plate,
            "plaza_id": plaza_id,
            "payment_status": payment_status,
            "is_exception": is_exception,
        }.items()
        if value is not None
    }

    query = db.query(Transaction)
    if filters:
        query = query.filter_by(**filters)
    if start_time is not None:
        query = query.filter(Transaction.transaction_time >= start_time)
    if end_time is not None:
        query = query.filter(Transaction.transaction_time <= end_time)
    if from_time is not None:
        query = query.filter(Transaction.transaction_time >= from_time)
    if to_time is not None:
        query = query.filter(Transaction.transaction_time < to_time)
    if response is not None:
        response.headers["X-Total-Count"] = str(query.count())

    return (
        query.order_by(Transaction.transaction_time.desc(), Transaction.transaction_id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


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
    "/by-vehicle/{vehicle_id}",
    response_model=list[TransactionRead],
    dependencies=[Depends(require_role(UserRole.OPERATOR, UserRole.ADMIN, UserRole.AUDITOR))],
    summary="Get transaction history for a vehicle",
)
def list_vehicle_transactions(
    vehicle_id: uuid.UUID,
    plaza_id: uuid.UUID | None = None,
    payment_status: PaymentStatus | None = None,
    is_exception: bool | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[Transaction]:
    return _list_transaction_history(
        db,
        vehicle_id=vehicle_id,
        plaza_id=plaza_id,
        payment_status=payment_status,
        is_exception=is_exception,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
    )


@router.get(
    "",
    response_model=list[TransactionRead],
    dependencies=[Depends(require_role(UserRole.OPERATOR, UserRole.ADMIN, UserRole.AUDITOR))],
    summary="Search transaction history",
)
def list_transactions(
    response: Response,
    vehicle_id: uuid.UUID | None = None,
    transaction_id: uuid.UUID | None = None,
    plate_number: str | None = None,
    plaza_id: uuid.UUID | None = None,
    payment_status: PaymentStatus | None = None,
    is_exception: bool | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    from_time: datetime | None = Query(default=None, alias="from"),
    to_time: datetime | None = Query(default=None, alias="to"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[Transaction]:
    return _list_transaction_history(
        db,
        vehicle_id=vehicle_id,
        transaction_id=transaction_id,
        plate_number=plate_number,
        plaza_id=plaza_id,
        payment_status=payment_status,
        is_exception=is_exception,
        start_time=start_time,
        end_time=end_time,
        from_time=from_time,
        to_time=to_time,
        limit=limit,
        offset=offset,
        response=response,
    )