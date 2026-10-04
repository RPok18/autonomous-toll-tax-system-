import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.database import Base


class AuditLog(Base):
    """Role-based access & action audit trail — P6 requirement."""

    __tablename__ = "audit_logs"

    audit_log_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor = Column(String(80), index=True)
    action = Column(String(100), index=True)
    resource_type = Column(String(50), nullable=True)
    resource_id = Column(String(100), nullable=True)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))