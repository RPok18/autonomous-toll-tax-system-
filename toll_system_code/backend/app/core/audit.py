"""Audit logging (P6). Every sensitive dashboard action (viewing a
transaction's plate image, exporting data, denied access) should call
``log_action`` so there is a reviewable trail."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.audit import AuditLog


def log_action(
    db: Session,
    actor: str,
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata_json=metadata or {},
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry