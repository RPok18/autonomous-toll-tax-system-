import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Numeric, SmallInteger, Boolean, Date, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.database import Base


class Plaza(Base):
    __tablename__ = "plazas"

    plaza_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    highway_id = Column(PG_UUID(as_uuid=True), ForeignKey("highways.highway_id"), nullable=False)
    plaza_code = Column(String(20), unique=True, nullable=False)
    name = Column(String(150), nullable=False)
    chainage_km = Column(Numeric(8, 2))
    state_code = Column(String(2), nullable=False)
    latitude = Column(Numeric(9, 6))
    longitude = Column(Numeric(9, 6))
    num_lanes = Column(SmallInteger, nullable=False, default=1)
    direction = Column(String(20))
    operator_name = Column(String(150))
    commissioned_on = Column(Date)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    highway = relationship("Highway", back_populates="plazas")
    tariffs = relationship("Tariff", back_populates="plaza")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Plaza {self.plaza_code} {self.name}>"