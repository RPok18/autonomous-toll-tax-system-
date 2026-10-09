from __future__ import annotations

import enum

from sqlalchemy import Enum as SAEnum


def pg_enum(enum_cls: type[enum.Enum], pg_type_name: str, **kw):
    return SAEnum(
        enum_cls,
        name=pg_type_name,
        native_enum=True,
        create_type=False,
        values_callable=lambda obj: [e.value for e in obj],
        **kw,
    )