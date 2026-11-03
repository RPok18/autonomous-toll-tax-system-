from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import api_router
from app.config import get_settings
from app.database import init_db

settings = get_settings()

app = FastAPI(title="Autonomous Toll Tax System", version="0.1.0")
app.include_router(api_router)
app.mount(
    "/dashboard",
    StaticFiles(directory=Path(__file__).resolve().parent / "dashboard", html=True),
    name="dashboard",
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}