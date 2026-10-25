"""Role-based access control dependencies (P6).

A bearer token carries `sub` (username) and `role`; `require_role` is a
FastAPI dependency factory that 403s anyone without an allowed role.
Every denied check also writes an audit log entry.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.security import decode_access_token
from app.database import get_db
from app.models.user import UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)


def get_current_identity(token: str | None = Depends(oauth2_scheme)) -> dict:
    if token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = decode_access_token(token)
    except Exception as exc:  # invalid/expired token
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from exc
    return {"username": payload["sub"], "role": payload["role"]}


def require_role(*allowed_roles: UserRole):
    def _dependency(
        identity: dict = Depends(get_current_identity),
        db: Session = Depends(get_db),
    ) -> dict:
        if identity["role"] not in [r.value for r in allowed_roles]:
            log_action(db, actor=identity["username"], action="access_denied",
                       resource_type="endpoint", metadata={"required_roles": [r.value for r in allowed_roles]})
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role for this action")
        return identity

    return _dependency