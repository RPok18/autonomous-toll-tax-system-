"""SQLAlchemy engine, session factory, and declarative base."""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import get_settings

settings = get_settings()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
# Note: several models (e.g. Highway.states) use Postgres-specific column
# types (ARRAY, native UUID/ENUM), so Postgres is the supported target —
# SQLite is not a drop-in fallback for this schema.

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency yielding a scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables. Called on startup; replace with Alembic migrations
    once the schema stabilizes."""
    from app import models  # noqa: F401  (ensure models are registered)

    Base.metadata.create_all(bind=engine)