from __future__ import annotations

from fastapi import FastAPI

from app.api import api_router
from app.config import get_settings
from app.database import init_db

settings = get_settings()

app = FastAPI(title="Autonomous Toll Tax System", version="0.1.0")
app.include_router(api_router)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}