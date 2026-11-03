from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import ExceptionType
from app.schemas.base import ORMBase


class ExceptionCreate(BaseModel):
    transaction_id: uuid.UUID | None = None
    plaza_id: uuid.UUID | None = None
    lane_id: str | None = None
    exception_type: ExceptionType
    details: str | None = None
    resolved: bool = False


class ExceptionResolve(BaseModel):
    resolution_note: str = Field(min_length=1, max_length=1000)

    @field_validator("resolution_note", mode="before")
    @classmethod
    def trim_resolution_note(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Resolution note must not be blank")
        return value


class ExceptionRead(ORMBase):
    exception_id: uuid.UUID
    transaction_id: uuid.UUID | None
    plaza_id: uuid.UUID | None
    lane_id: str | None
    exception_type: ExceptionType
    details: str | None
    resolved: bool
    resolved_at: datetime | None
    resolution_note: str | None
    created_at: datetime
    has_image: bool
