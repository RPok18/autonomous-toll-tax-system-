import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Numeric, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.database import Base
from app.models._pgenum import pg_enum
from app.models.enums import IdentificationMethod, PaymentStatus, VehicleClass


class Transaction(Base):
    """One auditable toll charge event — matches transactions in db/schema.sql."""

    __tablename__ = "transactions"

    transaction_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plaza_id = Column(PG_UUID(as_uuid=True), ForeignKey("plazas.plaza_id"), nullable=False)
    lane_id = Column(String(20), nullable=False)
    trip_id = Column(PG_UUID(as_uuid=True), ForeignKey("trips.trip_id"), nullable=True)
    vehicle_id = Column(PG_UUID(as_uuid=True), ForeignKey("vehicles.vehicle_id"), nullable=True)
    tariff_id = Column(PG_UUID(as_uuid=True), ForeignKey("tariffs.tariff_id"), nullable=True)

    # Point-in-time capture, kept even if the vehicle record changes later.
    plate_number = Column(String(15), nullable=True)
    plate_confidence = Column(Numeric(4, 3), nullable=True)
    tag_id = Column(String(32), nullable=True)
    tag_confidence = Column(Numeric(4, 3), nullable=True)
    identification_method = Column(
        pg_enum(IdentificationMethod, "identification_method"), nullable=False, default=IdentificationMethod.UNRESOLVED
    )
    vehicle_class = Column(pg_enum(VehicleClass, "vehicle_class"), nullable=True)

    base_amount = Column(Numeric(10, 2), nullable=True)
    discount_amount = Column(Numeric(10, 2), nullable=False, default=0)
    surcharge_amount = Column(Numeric(10, 2), nullable=False, default=0)
    amount_charged = Column(Numeric(10, 2), nullable=False, default=0)
    currency = Column(String(3), nullable=False, default="INR")
    payment_status = Column(pg_enum(PaymentStatus, "payment_status"), nullable=False, default=PaymentStatus.PENDING)

    applied_rules = Column(JSON, default=list)  # audit trail: which tariff/discount/surcharge rules fired
    is_exception = Column(Boolean, nullable=False, default=False)
    latency_ms = Column(Numeric(8, 2), nullable=True)  # P5 metric

    transaction_time = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    vehicle = relationship("Vehicle", back_populates="transactions")
    trip = relationship("Trip", back_populates="transactions")
    exceptions = relationship("ExceptionRecord", back_populates="transaction")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Transaction {self.transaction_id} plate={self.plate_number} amount={self.amount_charged}>"