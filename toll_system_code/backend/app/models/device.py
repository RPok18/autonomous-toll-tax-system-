import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, Numeric, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.database import Base
from app.models._pgenum import pg_enum
from app.models.enums import DeviceType, DeviceStatus


class Device(Base):
    __tablename__ = "devices"

    device_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(150))
    device_type = Column(pg_enum(DeviceType, "device_type"), nullable=False)
    plaza_id = Column(PG_UUID(as_uuid=True), ForeignKey("plazas.plaza_id"), nullable=True)
    lane_id = Column(String(20), nullable=True)

    status = Column(pg_enum(DeviceStatus, "device_status"), nullable=False, default=DeviceStatus.ONLINE)
    error_count_24h = Column(Integer, default=0)
    avg_latency_ms = Column(Numeric(8, 2), nullable=True)
    last_heartbeat_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Device {self.name} status={self.status}>"