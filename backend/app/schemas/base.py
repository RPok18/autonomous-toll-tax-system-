from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ORMBase(BaseModel):
    """Base for any schema read directly off a SQLAlchemy model instance."""

    model_config = ConfigDict(from_attributes=True)