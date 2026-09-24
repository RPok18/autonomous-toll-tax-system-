import uuid
from datetime import datetime

from sqlalchemy import Column, Numeric, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.database import Base
from app.models._pgenum import pg_enum
from app.models.enums import TripStatus


class Trip(Base):
    """One full entry->exit journey on a closed/distance-based corridor."""

    __tablename__ = "trips"

    trip_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vehicle_id = Column(PG_UUID(as_uuid=True), ForeignKey("vehicles.vehicle_id"), nullable=False)
    segment_id = Column(PG_UUID(as_uuid=True), ForeignKey("segments.segment_id"), nullable=True)
    entry_plaza_id = Column(PG_UUID(as_uuid=True), ForeignKey("plazas.plaza_id"), nullable=False)
    entry_time = Column(DateTime(timezone=True), nullable=False)
    exit_plaza_id = Column(PG_UUID(as_uuid=True), ForeignKey("plazas.plaza_id"), nullable=True)
    exit_time = Column(DateTime(timezone=True), nullable=True)
    distance_travelled_km = Column(Numeric(8, 2))
    status = Column(pg_enum(TripStatus, "trip_status"), nullable=False, default=TripStatus.IN_PROGRESS)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    vehicle = relationship("Vehicle", back_populates="trips")
    transactions = relationship("Transaction", back_populates="trip")

    __table_args__ = (
        CheckConstraint("exit_time IS NULL OR exit_time >= entry_time", name="ck_trips_exit_after_entry"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Trip {self.trip_id} status={self.status}>"