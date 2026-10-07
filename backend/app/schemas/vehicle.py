from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import VehicleClass
from app.schemas.base import ORMBase


class VehicleCreate(BaseModel):
    plate_number: str | None = None
    registration_state: str | None = None
    vehicle_class: VehicleClass = VehicleClass.UNKNOWN
    fastag_id: str | None = None
    fastag_issuer_bank: str | None = None
    is_commercial: bool = False
    is_exempt: bool = False
    is_blacklisted: bool = False


class VehicleRead(ORMBase):
    vehicle_id: uuid.UUID
    plate_number: str | None
    registration_state: str | None
    vehicle_class: VehicleClass
    fastag_id: str | None
    fastag_issuer_bank: str | None
    is_commercial: bool
    is_exempt: bool
    is_blacklisted: bool
    first_seen_at: datetime
    created_at: datetime
    updated_at: datetime