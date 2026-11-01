"""Arrange/inspect helpers shared by the API tests."""
from __future__ import annotations

from decimal import Decimal

from app.models.audit import AuditLog
from app.models.device import Device
from app.models.enums import (
    DeviceStatus,
    DeviceType,
    ExceptionType,
    IdentificationMethod,
    PaymentStatus,
    VehicleClass,
)
from app.models.exception import ExceptionRecord
from app.models.transaction import Transaction
from app.models.vehicle import Vehicle


def add_vehicle(db, plate="MH12AB1234", balance="100.00", vehicle_class=VehicleClass.CAR_JEEP_VAN, **extra) -> Vehicle:
    vehicle = Vehicle(plate_number=plate, balance=Decimal(balance), vehicle_class=vehicle_class, **extra)
    db.add(vehicle)
    db.commit()
    return vehicle


def add_transaction(db, seed, *, amount="65.00", is_exception=False, plate="MH12AB1234") -> Transaction:
    transaction = Transaction(
        plaza_id=seed.plaza.plaza_id,
        lane_id="L1",
        plate_number=plate,
        identification_method=IdentificationMethod.ANPR_ONLY,
        amount_charged=Decimal(amount),
        payment_status=PaymentStatus.PAID,
        is_exception=is_exception,
    )
    db.add(transaction)
    db.commit()
    return transaction


def add_device(db, seed, *, status=DeviceStatus.ONLINE, name="Camera 1") -> Device:
    device = Device(name=name, device_type=DeviceType.CAMERA_FRONT, plaza_id=seed.plaza.plaza_id, status=status)
    db.add(device)
    db.commit()
    return device


def add_exception(db, seed, *, resolved=False) -> ExceptionRecord:
    record = ExceptionRecord(
        plaza_id=seed.plaza.plaza_id,
        lane_id="L1",
        exception_type=ExceptionType.LOW_CONFIDENCE_PLATE,
        resolved=resolved,
    )
    db.add(record)
    db.commit()
    return record


def audit_rows(db, action: str) -> list[AuditLog]:
    db.expire_all()
    return db.query(AuditLog).filter_by(action=action).all()


