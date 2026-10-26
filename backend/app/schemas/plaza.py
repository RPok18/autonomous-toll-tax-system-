from __future__ import annotations

import uuid

from app.schemas.base import ORMBase


class PlazaRead(ORMBase):
    plaza_id: uuid.UUID
    plaza_code: str
    name: str
    state_code: str
    num_lanes: int
    is_active: bool
