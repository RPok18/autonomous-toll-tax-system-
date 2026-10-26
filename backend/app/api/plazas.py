from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.database import get_db
from app.models.enums import UserRole
from app.models.plaza import Plaza
from app.schemas.plaza import PlazaRead

router = APIRouter(prefix="/plazas", tags=["plazas"])


@router.get(
    "",
    response_model=list[PlazaRead],
    dependencies=[Depends(require_role(UserRole.OPERATOR, UserRole.ADMIN, UserRole.AUDITOR))],
)
def list_plazas(db: Session = Depends(get_db)) -> list[Plaza]:
    return db.query(Plaza).order_by(Plaza.plaza_code).all()
