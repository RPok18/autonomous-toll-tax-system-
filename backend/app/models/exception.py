import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.database import Base
from app.models._pgenum import pg_enum
from app.models.enums import ExceptionType


class ExceptionRecord(Base):
    __tablename__ = "exceptions"

    exception_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = Column(PG_UUID(as_uuid=True), ForeignKey("transactions.transaction_id"), nullable=True)
    plaza_id = Column(PG_UUID(as_uuid=True), ForeignKey("plazas.plaza_id"), nullable=True)
    lane_id = Column(String(20), nullable=True)

    exception_type = Column(pg_enum(ExceptionType, "exception_type"), nullable=False)
    details = Column(Text, nullable=True)
    resolved = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    transaction = relationship("Transaction", back_populates="exceptions")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Exception {self.exception_type} tx={self.transaction_id}>"