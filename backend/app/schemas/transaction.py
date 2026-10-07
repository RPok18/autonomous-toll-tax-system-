from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import IdentificationMethod, PaymentStatus, VehicleClass
from app.schemas.base import ORMBase


class TransactionCreate(BaseModel):
    """Payload a lane controller posts after fusion + policy have run."""

    plaza_id: uuid.UUID
    lane_id: str
    trip_id: uuid.UUID | None = None
    vehicle_id: uuid.UUID | None = None
    tariff_id: uuid.UUID | None = None

    plate_number: str | None = None
    plate_confidence: Decimal | None = None
    tag_id: str | None = None
    tag_confidence: Decimal | None = None
    identification_method: IdentificationMethod = IdentificationMethod.UNRESOLVED
    vehicle_class: VehicleClass | None = None

    base_amount: Decimal | None = None
    discount_amount: Decimal = Decimal("0")
    surcharge_amount: Decimal = Decimal("0")
    amount_charged: Decimal = Decimal("0")
    currency: str = "INR"
    payment_status: PaymentStatus = PaymentStatus.PENDING

    applied_rules: list[str] = []
    is_exception: bool = False
    latency_ms: Decimal | None = None


class TransactionRead(ORMBase):
    """What the API and dashboard read back — mirrors the Transaction model."""

    transaction_id: uuid.UUID
    plaza_id: uuid.UUID
    lane_id: str
    trip_id: uuid.UUID | None
    vehicle_id: uuid.UUID | None
    tariff_id: uuid.UUID | None

    plate_number: str | None
    plate_confidence: Decimal | None
    tag_id: str | None
    tag_confidence: Decimal | None
    identification_method: IdentificationMethod
    vehicle_class: VehicleClass | None

    base_amount: Decimal | None
    discount_amount: Decimal
    surcharge_amount: Decimal
    amount_charged: Decimal
    currency: str
    payment_status: PaymentStatus

    applied_rules: list[str]
    is_exception: bool
    latency_ms: Decimal | None

    transaction_time: datetime
    created_at: datetime