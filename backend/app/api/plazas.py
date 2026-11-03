from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.database import get_db
from app.models.enums import UserRole
from app.models.plaza import Plaza

router = APIRouter(prefix="/plazas", tags=["plazas"])


@router.get("")
def list_plazas(
    db: Session = Depends(get_db),
    _identity=Depends(require_role(
        UserRole.OPERATOR,
        UserRole.ADMIN,
        UserRole.AUDITOR,
    )),
):
    return (
        db.query(Plaza)
        .filter(Plaza.is_active.is_(True))
        .order_by(Plaza.plaza_code)
        .all()
    )
