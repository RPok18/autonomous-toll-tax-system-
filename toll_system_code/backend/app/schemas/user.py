from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import UserRole
from app.schemas.base import ORMBase


class UserCreate(BaseModel):
    """Plain-text password in, hashed before storage \u2014 never log or echo this."""

    username: str
    password: str
    role: UserRole = UserRole.VIEWER


class UserRead(ORMBase):
    user_id: uuid.UUID
    username: str
    role: UserRole
    is_active: bool
    created_at: datetime