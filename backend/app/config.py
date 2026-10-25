"""Centralized, env-driven settings for the toll system."""
from functools import lru_cache
from typing import Literal

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
    anpr_image_retention_days: int = 7  # P6 data minimization
    plate_image_dir: str = "data/plate_images"
    max_plate_image_bytes: int = 5 * 1024 * 1024
    record_retention_days: int = 365

    # P2 - RFID / fusion
    rfid_simulate: bool = True
    rfid_read_timeout_ms: int = 300
    rfid_min_confidence: float = 0.55
    fusion_mode: str = "hybrid"  # hybrid | anpr_only | rfid_only
    fusion_primary_signal: Literal["anpr", "rfid"] = "anpr"

    # Auth
    access_token_expire_minutes: int = 60
    jwt_algorithm: str = "HS256"


@lru_cache
def get_settings() -> Settings:
    return Settings()