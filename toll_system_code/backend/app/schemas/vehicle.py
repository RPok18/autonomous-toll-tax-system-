from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.models.enums import VehicleClass
from app.schemas.base import ORMBase
from app.schemas.transaction import TransactionRead


def normalize_plate_number(value: str) -> str:
    return "".join(character for character in value.upper() if character.isalnum())


class VehicleCreate(BaseModel):
    plate_number: str | None = None
    registration_state: str | None = None
    vehicle_class: VehicleClass = VehicleClass.UNKNOWN
    balance: Decimal = Field(default=Decimal("0.00"), ge=0)
    fastag_id: str | None = None
    fastag_issuer_bank: str | None = None
    is_commercial: bool = False
    is_exempt: bool = False
    is_blacklisted: bool = False

    @field_validator("plate_number")
    @classmethod
    def normalize_plate(cls, value: str | None) -> str | None:
        return normalize_plate_number(value) if value is not None else None


class VehicleRead(ORMBase):
    vehicle_id: uuid.UUID
    plate_number: str | None
    registration_state: str | None
    vehicle_class: VehicleClass
    balance: Decimal
    fastag_id: str | None
    fastag_issuer_bank: str | None
    is_commercial: bool
    is_exempt: bool
    is_blacklisted: bool
    first_seen_at: datetime
    created_at: datetime
    updated_at: datetime


class TollChargeRequest(BaseModel):
    plate_number: str = Field(min_length=1, max_length=20)
    plaza_code: str = Field(min_length=1, max_length=20)
    lane_id: str = Field(default="AUTO", min_length=1, max_length=20)

    @field_validator("plate_number")
    @classmethod
    def normalize_plate(cls, value: str) -> str:
        normalized = normalize_plate_number(value)
        if not normalized:
            raise ValueError("plate_number must contain letters or digits")
        return normalized

    @field_validator("plaza_code")
    @classmethod
    def normalize_plaza_code(cls, value: str) -> str:
        return value.strip().upper()


class TollChargeResponse(BaseModel):
    transaction: TransactionRead
    balance_after: Decimal