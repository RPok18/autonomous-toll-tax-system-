from sqlalchemy import Enum as SAEnum


def pg_enum(enum_cls, pg_type_name: str, **kw):
    return SAEnum(enum_cls, name=pg_type_name, native_enum=True, create_type=False, **kw)