import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Numeric, Boolean, DateTime, ForeignKey, CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.database import Base


class Segment(Base):
    """A billable entry<->exit plaza pair on a closed/distance-based corridor."""

    __tablename__ = "segments"

    segment_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    highway_id = Column(PG_UUID(as_uuid=True), ForeignKey("highways.highway_id"), nullable=False)
    entry_plaza_id = Column(PG_UUID(as_uuid=True), ForeignKey("plazas.plaza_id"), nullable=False)
    exit_plaza_id = Column(PG_UUID(as_uuid=True), ForeignKey("plazas.plaza_id"), nullable=False)
    name = Column(String(150))
    distance_km = Column(Numeric(8, 2), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    highway = relationship("Highway", back_populates="segments")
    tariffs = relationship("Tariff", back_populates="segment")

    __table_args__ = (
        CheckConstraint("entry_plaza_id <> exit_plaza_id", name="ck_segments_distinct_plazas"),
        UniqueConstraint("entry_plaza_id", "exit_plaza_id", name="uq_segments_entry_exit"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Segment {self.name} {self.distance_km}km>"