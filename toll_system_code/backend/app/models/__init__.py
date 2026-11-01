from app.models.highway import Highway  # noqa: F401
from app.models.plaza import Plaza  # noqa: F401
from app.models.segment import Segment  # noqa: F401
from app.models.tariff import Tariff  # noqa: F401
from app.models.vehicle import Vehicle  # noqa: F401
from app.models.trip import Trip  # noqa: F401
from app.models.transaction import Transaction  # noqa: F401
from app.models.exception import ExceptionRecord  # noqa: F401
from app.models.device import Device  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.audit import AuditLog  # noqa: F401

# Convenience re-exports of enums, so existing call sites like
# `from app.models.vehicle import VehicleClass` still resolve.
from app.models.enums import (  # noqa: F401
    VehicleClass,
    TollingType,
    IdentificationMethod,
    PaymentStatus,
    TripStatus,
    ExceptionType,
    DeviceType,
    DeviceStatus,
    UserRole,
)