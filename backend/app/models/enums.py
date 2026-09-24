"""Python enums mirroring the Postgres ENUM types in db/schema.sql.
Kept in one place so model files and app code share a single definition."""
import enum


class VehicleClass(str, enum.Enum):
    TWO_WHEELER = "two_wheeler"
    CAR_JEEP_VAN = "car_jeep_van"
    LCV = "lcv"
    BUS_TRUCK = "bus_truck"
    HCV_MAV = "hcv_mav"
    OVERSIZED = "oversized"
    EXEMPT_OTHER = "exempt_other"
    UNKNOWN = "unknown"


class TollingType(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"


class IdentificationMethod(str, enum.Enum):
    ANPR_ONLY = "anpr_only"
    RFID_ONLY = "rfid_only"
    HYBRID_AGREED = "hybrid_agreed"
    HYBRID_RFID_PRIMARY = "hybrid_rfid_primary"
    HYBRID_ANPR_PRIMARY = "hybrid_anpr_primary"
    MANUAL = "manual"
    UNRESOLVED = "unresolved"


class PaymentStatus(str, enum.Enum):
    PAID = "paid"
    PENDING = "pending"
    FAILED = "failed"
    WAIVED = "waived"
    DISPUTED = "disputed"


class TripStatus(str, enum.Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class ExceptionType(str, enum.Enum):
    LOW_CONFIDENCE_PLATE = "low_confidence_plate"
    TAG_MISMATCH = "tag_mismatch"
    NO_IDENTIFICATION = "no_identification"
    TAG_NOT_FOUND = "tag_not_found"
    POLICY_VIOLATION = "policy_violation"
    DEVICE_FAULT = "device_fault"


class DeviceType(str, enum.Enum):
    CAMERA_FRONT = "camera_front"
    CAMERA_REAR = "camera_rear"
    RFID_READER = "rfid_reader"
    BARRIER = "barrier"


class DeviceStatus(str, enum.Enum):
    ONLINE = "online"
    DEGRADED = "degraded"
    OFFLINE = "offline"


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    AUDITOR = "auditor"
    VIEWER = "viewer"