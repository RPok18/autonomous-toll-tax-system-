"""Centralized, env-driven settings for the toll system."""
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Autonomous Toll Tax System"
    env: str = "development"
    secret_key: str = "change-me-before-any-real-deployment"

    # Default assumes the docker-compose Postgres service. Override via
    # DATABASE_URL in .env for a different host/user/db.
    database_url: str = "postgresql+psycopg://toll_app:toll_app@localhost:5432/toll_system"

    # P1 - ANPR
    anpr_device: str = "cpu"  # "cpu" or "cuda:0" for RTX 2050 4GB
    anpr_min_confidence: float = 0.55

    # P6 - privacy and data retention (decision record 07)
    # Days an exception's plate image is kept after the exception is resolved.
    anpr_image_retention_days: int = 7
    # Days transactions, resolved exceptions and audit entries are kept (12 months).
    record_retention_days: int = 365
    # Where exception plate images are stored. Default: <repo root>/media/plate_captures (ignored by Git).
    plate_image_dir: str = str(Path(__file__).resolve().parents[2] / "media" / "plate_captures")
    max_plate_image_bytes: int = 5_000_000

    # P2 - RFID / fusion
    rfid_simulate: bool = True
    rfid_read_timeout_ms: int = 300
    fusion_mode: str = "hybrid"  # hybrid | anpr_only | rfid_only
    rfid_min_confidence: float = 0.5  # lowest RFID read confidence FusionEngine accepts
    # Which signal wins when ANPR and RFID are both usable but disagree.
    fusion_primary_signal: str = "rfid"  # rfid | anpr

    # Auth
    access_token_expire_minutes: int = 60
    jwt_algorithm: str = "HS256"


@lru_cache
def get_settings() -> Settings:
    return Settings()