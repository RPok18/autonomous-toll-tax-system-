"""Translate database rule violations into client errors instead of 500s.

Before this module a duplicate plate or FASTag id, or a reference to a plaza or
transaction that does not exist, surfaced as an unhandled IntegrityError (500).
The messages are generic on purpose: constraint names and values stay in the
server log, not in the response.
"""
from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

UNIQUE_VIOLATION = "23505"
FOREIGN_KEY_VIOLATION = "23503"


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
        sqlstate = getattr(exc.orig, "sqlstate", None)
        if sqlstate == UNIQUE_VIOLATION:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={"detail": "A record with the same unique value already exists"},
            )
        if sqlstate == FOREIGN_KEY_VIOLATION:
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content={"detail": "A referenced record does not exist"},
            )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": "The request violates a database rule"},
        )
