import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Numeric, SmallInteger, Date, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.database import Base
from app.models._pgenum import pg_enum
from app.models.enums import VehicleClass


class Tariff(Base):
    __tablename__ = "tariffs"

    tariff_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plaza_id = Column(PG_UUID(as_uuid=True), ForeignKey("plazas.plaza_id"), nullable=True)
    segment_id = Column(PG_UUID(as_uuid=True), ForeignKey("segments.segment_id"), nullable=True)
    vehicle_class = Column(pg_enum(VehicleClass, "vehicle_class"), nullable=False)

    base_fare = Column(Numeric(10, 2), nullable=False)
    rate_per_km = Column(Numeric(10, 2))  # used when segment_id is set

    return_trip_discount_percent = Column(Numeric(5, 2), nullable=False, default=0)
    return_trip_window_hours = Column(SmallInteger, nullable=False, default=24)
    monthly_pass_fare = Column(Numeric(10, 2))
    local_resident_discount_percent = Column(Numeric(5, 2), nullable=False, default=0)
    night_surcharge_percent = Column(Numeric(5, 2), nullable=False, default=0)

    currency = Column(String(3), nullable=False, default="INR")
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)  # NULL = currently in force
    notified_by = Column(String(150))

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    plaza = relationship("Plaza", back_populates="tariffs")
    segment = relationship("Segment", back_populates="tariffs")

    __table_args__ = (
        CheckConstraint(
            "(plaza_id IS NOT NULL AND segment_id IS NULL) OR (plaza_id IS NULL AND segment_id IS NOT NULL)",
            name="ck_tariffs_one_scope",
        ),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_tariffs_date_range"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Tariff {self.vehicle_class} base={self.base_fare}>"