from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.database import get_db
from app.api.deps import require_role
from app.models.enums import UserRole
from app.models.vehicle import Vehicle
from app.schemas.vehicle import VehicleCreate, VehicleRead

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


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