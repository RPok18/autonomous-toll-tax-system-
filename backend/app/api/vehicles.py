from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.models.audit import AuditLog
from app.database import get_db
from app.api.deps import require_role
from app.models.enums import IdentificationMethod, PaymentStatus, UserRole
from app.models.plaza import Plaza
from app.models.trip import Trip
from app.models.vehicle import Vehicle
from app.schemas.transaction import TransactionRead
from app.schemas.vehicle import (
    TollChargeRequest,
    TollChargeResponse,
    VehicleCreate,
    VehicleRead,
    normalize_plate_number,
)
from app.toll import TariffNotFoundError, TollCalculator

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


def _log_failed_charge(
    db: Session,
    *,
    actor: str,
    plate_number: str,
    plaza_code: str,
    reason: str,
    amount: Decimal | None = None,
) -> None:
    db.add(
        AuditLog(
            actor=actor,
            action="charge_vehicle_toll_failed",
            resource_type="toll_charge",
            resource_id=plate_number,
            metadata_json={
                "plate_number": plate_number,
                "plaza_code": plaza_code,
                "amount_charged": str(amount) if amount is not None else None,
                "reason": reason,
            },
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()


@router.post(
    "",
    response_model=VehicleRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.OPERATOR, UserRole.ADMIN))],
)
def create_vehicle(
    payload: VehicleCreate,
    db: Session = Depends(get_db),
    identity=Depends(require_role(UserRole.OPERATOR, UserRole.ADMIN)),
) -> Vehicle:
    vehicle = Vehicle(**payload.model_dump())
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)

    log_action(
        db,
        actor=str(identity.get("sub")),
        action="create_vehicle",
        resource_type="vehicle",
        resource_id=str(vehicle.vehicle_id),
    )
    return vehicle


@router.get(
    "/{vehicle_id}",
    response_model=VehicleRead,
    dependencies=[Depends(require_role(UserRole.OPERATOR, UserRole.ADMIN, UserRole.AUDITOR, UserRole.VIEWER))],
)
def get_vehicle(vehicle_id: uuid.UUID, db: Session = Depends(get_db)) -> Vehicle:
    vehicle = db.query(Vehicle).filter_by(vehicle_id=vehicle_id).first()
    if vehicle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    return vehicle


@router.get(
    "/by-plate/{plate_number}",
    response_model=VehicleRead,
    dependencies=[Depends(require_role(UserRole.OPERATOR, UserRole.ADMIN, UserRole.AUDITOR, UserRole.VIEWER))],
)
def get_vehicle_by_plate(plate_number: str, db: Session = Depends(get_db)) -> Vehicle:
    vehicle = db.query(Vehicle).filter_by(plate_number=normalize_plate_number(plate_number)).first()
    if vehicle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    return vehicle


@router.post(
    "/charge",
    response_model=TollChargeResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.OPERATOR, UserRole.ADMIN))],
)
def charge_vehicle(
    payload: TollChargeRequest,
    db: Session = Depends(get_db),
    identity: dict = Depends(require_role(UserRole.OPERATOR, UserRole.ADMIN)),
) -> TollChargeResponse:
    actor = str(identity.get("sub") or identity.get("username") or "unknown")
    vehicle = (
        db.query(Vehicle)
        .filter_by(plate_number=payload.plate_number)
        .with_for_update()
        .first()
    )
    if vehicle is None:
        _log_failed_charge(
            db,
            actor=actor,
            plate_number=payload.plate_number,
            plaza_code=payload.plaza_code,
            reason="Vehicle not found",
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")

    plaza = db.query(Plaza).filter_by(plaza_code=payload.plaza_code, is_active=True).first()
    if plaza is None:
        _log_failed_charge(
            db,
            actor=actor,
            plate_number=vehicle.plate_number,
            plaza_code=payload.plaza_code,
            reason="Toll plaza not found",
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Toll plaza not found")

    trip = Trip(
        vehicle_id=vehicle.vehicle_id,
        entry_plaza_id=plaza.plaza_id,
        entry_time=datetime.now(timezone.utc),
    )
    try:
        transaction = TollCalculator(db).calculate(
            trip,
            vehicle,
            lane_id=payload.lane_id,
            identification_method=IdentificationMethod.MANUAL,
        )
    except TariffNotFoundError as exc:
        _log_failed_charge(
            db,
            actor=actor,
            plate_number=vehicle.plate_number,
            plaza_code=payload.plaza_code,
            reason="No applicable tariff found",
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No applicable tariff found",
        ) from exc

    amount = Decimal(transaction.amount_charged).quantize(Decimal("0.01"))
    if vehicle.balance < amount:
        _log_failed_charge(
            db,
            actor=actor,
            plate_number=vehicle.plate_number,
            plaza_code=payload.plaza_code,
            amount=amount,
            reason="Insufficient balance",
        )
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="Insufficient balance")

    vehicle.balance -= amount
    transaction.payment_status = PaymentStatus.PAID
    db.add(transaction)
    db.flush()

    db.add(
        AuditLog(
            actor=actor,
            action="charge_vehicle_toll",
            resource_type="transaction",
            resource_id=str(transaction.transaction_id),
            metadata_json={
                "plate_number": vehicle.plate_number,
                "amount_charged": str(amount),
                "balance_after": str(vehicle.balance),
            },
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    db.refresh(transaction)

    return TollChargeResponse(
        transaction=TransactionRead.model_validate(transaction),
        balance_after=vehicle.balance,
    )


@router.get(
    "",
    response_model=list[VehicleRead],
    dependencies=[Depends(require_role(UserRole.OPERATOR, UserRole.ADMIN, UserRole.AUDITOR, UserRole.VIEWER))],
)
def list_vehicles(
    plate_number: str | None = None,
    fastag_id: str | None = None,
    is_blacklisted: bool | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> list[Vehicle]:
    query = db.query(Vehicle)
    if plate_number is not None:
        query = query.filter_by(plate_number=plate_number)
    if fastag_id is not None:
        query = query.filter_by(fastag_id=fastag_id)
    if is_blacklisted is not None:
        query = query.filter_by(is_blacklisted=is_blacklisted)
    return query.order_by(Vehicle.created_at.desc()).limit(limit).all()