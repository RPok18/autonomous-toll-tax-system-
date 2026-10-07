from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import ExceptionType
from app.schemas.base import ORMBase


class ExceptionCreate(BaseModel):
    transaction_id: uuid.UUID | None = None
    plaza_id: uuid.UUID | None = None
    lane_id: str | None = None
    exception_type: ExceptionType
    details: str | None = None
    resolved: bool = False


class ExceptionRead(ORMBase):
    exception_id: uuid.UUID
    transaction_id: uuid.UUID | None
    plaza_id: uuid.UUID | None
    lane_id: str | None
    exception_type: ExceptionType
    details: str | None
    resolved: bool
    created_at: datetime