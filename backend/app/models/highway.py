import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Numeric, DateTime
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.database import Base
from app.models._pgenum import pg_enum
from app.models.enums import TollingType


class Highway(Base):
    __tablename__ = "highways"

    highway_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nh_number = Column(String(20), unique=True, nullable=False)
    name = Column(String(150), nullable=False)
    states = Column(ARRAY(String(2)), nullable=False)
    total_length_km = Column(Numeric(8, 2))
    tolling_type = Column(pg_enum(TollingType, "tolling_type"), nullable=False, default=TollingType.OPEN)
    operator_name = Column(String(150))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    plazas = relationship("Plaza", back_populates="highway")
    segments = relationship("Segment", back_populates="highway")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Highway {self.nh_number} {self.name}>"