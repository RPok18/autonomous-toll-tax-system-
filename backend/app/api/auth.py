from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.security import create_access_token, verify_password
from app.database import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    # NOTE: assumes User has a `username` column alongside hashed_password
    # and role. If your User model names it differently, change the
    # filter_by key below to match.
    user = db.query(User).filter_by(username=payload.username).first()

    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token = create_access_token(subject=str(user.user_id), role=user.role)
    log_action(db, actor=str(user.user_id), action="login", resource_type="user", resource_id=str(user.user_id))

    return TokenResponse(access_token=token, role=user.role)