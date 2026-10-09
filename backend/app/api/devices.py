from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.database import get_db
from app.api.deps import require_role
from app.models.enums import UserRole, DeviceStatus
from app.models.device import Device
from app.schemas.device import DeviceCreate, DeviceRead

router = APIRouter(prefix="/devices", tags=["devices"])


@router.post(
    "",
    response_model=DeviceRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
def create_device(
    payload: DeviceCreate,
    db: Session = Depends(get_db),
    identity=Depends(require_role(UserRole.ADMIN)),
) -> Device:
    device = Device(**payload.model_dump())
    db.add(device)
    db.commit()
    db.refresh(device)

    log_action(
        db,
        actor=str(identity.get("sub")),
        action="create_device",
        resource_type="device",
        resource_id=str(device.device_id),
    )
    return device


@router.get(
    "/{device_id}",
    response_model=DeviceRead,
    dependencies=[Depends(require_role(UserRole.OPERATOR, UserRole.ADMIN, UserRole.AUDITOR))],
)
def get_device(device_id: uuid.UUID, db: Session = Depends(get_db)) -> Device:
    device = db.query(Device).filter_by(device_id=device_id).first()
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    return device


@router.get(
    "",
    response_model=list[DeviceRead],
    dependencies=[Depends(require_role(UserRole.OPERATOR, UserRole.ADMIN, UserRole.AUDITOR))],
)
def list_devices(
    plaza_id: uuid.UUID | None = None,
    status_filter: DeviceStatus | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> list[Device]:
    query = db.query(Device)
    if plaza_id is not None:
        query = query.filter_by(plaza_id=plaza_id)
    if status_filter is not None:
        query = query.filter_by(status=status_filter)
    return query.order_by(Device.last_heartbeat_at.desc()).limit(limit).all()


@router.patch(
    "/{device_id}/heartbeat",
    response_model=DeviceRead,
    dependencies=[Depends(require_role(UserRole.OPERATOR, UserRole.ADMIN))],
)
def heartbeat(device_id: uuid.UUID, db: Session = Depends(get_db)) -> Device:
    """Called periodically by lane hardware to report it's alive."""
    from datetime import datetime, timezone

    device = db.query(Device).filter_by(device_id=device_id).first()
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    device.last_heartbeat_at = datetime.now(timezone.utc)
    if device.status == DeviceStatus.OFFLINE:
        device.status = DeviceStatus.ONLINE
    db.commit()
    db.refresh(device)
    return device