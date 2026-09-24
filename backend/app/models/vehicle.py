import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.database import Base
from app.models._pgenum import pg_enum
from app.models.enums import VehicleClass


class Vehicle(Base):
    __tablename__ = "vehicles"

    vehicle_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plate_number = Column(String(15), unique=True, nullable=True)  # normalized, e.g. "MH12AB1234"
    registration_state = Column(String(2), nullable=True)
    vehicle_class = Column(pg_enum(VehicleClass, "vehicle_class"), nullable=False, default=VehicleClass.UNKNOWN)
    fastag_id = Column(String(32), unique=True, nullable=True)  # FASTag-like RFID tag ID
    fastag_issuer_bank = Column(String(64), nullable=True)
    is_commercial = Column(Boolean, nullable=False, default=False)
    is_exempt = Column(Boolean, nullable=False, default=False)
    is_blacklisted = Column(Boolean, nullable=False, default=False)
    first_seen_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    transactions = relationship("Transaction", back_populates="vehicle")
    trips = relationship("Trip", back_populates="vehicle")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Vehicle plate={self.plate_number} tag={self.fastag_id} class={self.vehicle_class}>"