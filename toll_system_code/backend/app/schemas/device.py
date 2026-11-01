from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import DeviceType, DeviceStatus
from app.schemas.base import ORMBase


class DeviceCreate(BaseModel):
    name: str | None = None
    device_type: DeviceType
    plaza_id: uuid.UUID | None = None
    lane_id: str | None = None
    status: DeviceStatus = DeviceStatus.ONLINE


class DeviceRead(ORMBase):
    device_id: uuid.UUID
    name: str | None
    device_type: DeviceType
    plaza_id: uuid.UUID | None
    lane_id: str | None
    status: DeviceStatus
    error_count_24h: int | None
    avg_latency_ms: Decimal | None
    last_heartbeat_at: datetime