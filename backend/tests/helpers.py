from __future__ import annotations

from app.models.enums import ExceptionType, VehicleClass
from app.models.exception import ExceptionRecord
from app.models.vehicle import Vehicle


def add_vehicle(db, *, plate_number: str = "MH12AB1234") -> Vehicle:
    vehicle = Vehicle(
        plate_number=plate_number,
        registration_state=plate_number[:2],
        vehicle_class=VehicleClass.CAR_JEEP_VAN,
        fastag_id=f"TAG-{plate_number}",
        balance=0,
    )
    db.add(vehicle)
    db.commit()
    return vehicle


def add_exception(db, seed, *, resolved: bool = False) -> ExceptionRecord:
    exception = ExceptionRecord(
        plaza_id=seed.plaza.plaza_id,
        lane_id="L1",
        exception_type=ExceptionType.TAG_MISMATCH,
        resolved=resolved,
    )
    db.add(exception)
    db.commit()
    db.refresh(exception)
    return exception


def audit_rows(db, action: str):
    from app.models.audit import AuditLog

    return db.query(AuditLog).filter_by(action=action).order_by(AuditLog.created_at).all()
