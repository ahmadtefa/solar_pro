"""Audit trail service.

The audit trail is append-only: services record what changed, who changed it and
from where.  ``record`` never raises on failure - auditing must not break a
business transaction - but failures are logged for follow-up.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy.orm import Session

from app.core.enums import AuditAction
from app.core.pagination import serialize_value, snapshot

logger = logging.getLogger("kayan.audit")

#: Fields that must never be persisted in an audit snapshot.
_REDACTED_FIELDS = {
    "password",
    "password_hash",
    "new_password",
    "old_password",
    "refresh_token",
    "refresh_token_hash",
    "previous_refresh_token_hash",
    "token",
    "token_hash",
    "secret",
    "secret_key",
    "api_key",
}


class AuditContext:
    """Request/actor information attached to every audit row."""

    __slots__ = ("company_id", "user_id", "user_email", "session_id", "branch_id", "ip_address", "user_agent", "request_id")

    def __init__(
        self,
        *,
        company_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        user_email: str | None = None,
        session_id: uuid.UUID | None = None,
        branch_id: uuid.UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
    ) -> None:
        self.company_id = company_id
        self.user_id = user_id
        self.user_email = user_email
        self.session_id = session_id
        self.branch_id = branch_id
        self.ip_address = ip_address
        self.user_agent = user_agent
        self.request_id = request_id


def _clean(values: dict[str, Any] | None) -> dict[str, Any] | None:
    if not values:
        return None
    cleaned: dict[str, Any] = {}
    for key, value in values.items():
        if key in _REDACTED_FIELDS or key.endswith("_hash"):
            cleaned[key] = "***redacted***"
        else:
            cleaned[key] = serialize_value(value)
    return cleaned


def diff_snapshots(
    old: dict[str, Any] | None, new: dict[str, Any] | None
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[str]]:
    """Return ``(old_changes, new_changes, changed_field_names)``."""
    if not old or not new:
        return _clean(old), _clean(new), []
    changed: list[str] = []
    old_changes: dict[str, Any] = {}
    new_changes: dict[str, Any] = {}
    for key, new_value in new.items():
        if key in {"updated_at", "created_at"}:
            continue
        old_value = old.get(key)
        if serialize_value(old_value) != serialize_value(new_value):
            changed.append(key)
            old_changes[key] = old_value
            new_changes[key] = new_value
    if not changed:
        return None, None, []
    return _clean(old_changes), _clean(new_changes), sorted(changed)


class AuditService:
    def __init__(self, db: Session, context: AuditContext | None = None) -> None:
        self.db = db
        self.context = context or AuditContext()

    # ------------------------------------------------------------------ core
    def record(
        self,
        *,
        action: AuditAction | str,
        entity_type: str,
        entity_id: uuid.UUID | None = None,
        entity_label: str | None = None,
        old_values: dict[str, Any] | None = None,
        new_values: dict[str, Any] | None = None,
        changed_fields: Sequence[str] | None = None,
        company_id: uuid.UUID | None = None,
        remarks: str | None = None,
        commit: bool = False,
    ) -> None:
        from app.models.identity import AuditLog

        tenant_id = company_id or self.context.company_id
        if tenant_id is None:
            # Company-level audit rows require a tenant; skip silently but log.
            logger.debug("Skipping audit row without company context: %s %s", action, entity_type)
            return
        try:
            row = AuditLog(
                company_id=tenant_id,
                user_id=self.context.user_id,
                user_email=self.context.user_email,
                session_id=self.context.session_id,
                branch_id=self.context.branch_id,
                action=str(action),
                entity_type=entity_type,
                entity_id=entity_id,
                entity_label=entity_label,
                old_values=_clean(old_values),
                new_values=_clean(new_values),
                changed_fields=list(changed_fields) if changed_fields else None,
                ip_address=self.context.ip_address,
                user_agent=(self.context.user_agent or "")[:400] or None,
                request_id=self.context.request_id,
                remarks=remarks,
            )
            self.db.add(row)
            if commit:
                self.db.commit()
        except Exception:  # pragma: no cover - auditing must never break the request
            logger.exception("Failed to write audit log for %s %s", action, entity_type)

    # --------------------------------------------------------------- helpers
    def log_create(self, entity: Any, *, entity_type: str | None = None, label: str | None = None) -> None:
        self.record(
            action=AuditAction.CREATE,
            entity_type=entity_type or type(entity).__name__,
            entity_id=getattr(entity, "id", None),
            entity_label=label or self._label(entity),
            new_values=snapshot(entity),
        )

    def log_update(
        self,
        entity: Any,
        old_snapshot: dict[str, Any],
        *,
        entity_type: str | None = None,
        label: str | None = None,
        action: AuditAction | str = AuditAction.UPDATE,
    ) -> None:
        new_snapshot = snapshot(entity)
        old_changes, new_changes, changed = diff_snapshots(old_snapshot, new_snapshot)
        if not changed and str(action) == str(AuditAction.UPDATE):
            return
        self.record(
            action=action,
            entity_type=entity_type or type(entity).__name__,
            entity_id=getattr(entity, "id", None),
            entity_label=label or self._label(entity),
            old_values=old_changes,
            new_values=new_changes,
            changed_fields=changed,
        )

    def log_delete(self, entity: Any, *, entity_type: str | None = None, label: str | None = None) -> None:
        self.record(
            action=AuditAction.DELETE,
            entity_type=entity_type or type(entity).__name__,
            entity_id=getattr(entity, "id", None),
            entity_label=label or self._label(entity),
            old_values=snapshot(entity),
        )

    def log_action(
        self,
        action: AuditAction | str,
        entity: Any,
        *,
        entity_type: str | None = None,
        label: str | None = None,
        remarks: str | None = None,
        new_values: dict[str, Any] | None = None,
    ) -> None:
        self.record(
            action=action,
            entity_type=entity_type or type(entity).__name__,
            entity_id=getattr(entity, "id", None),
            entity_label=label or self._label(entity),
            remarks=remarks,
            new_values=new_values,
        )

    @staticmethod
    def _label(entity: Any) -> str | None:
        for attribute in ("document_no", "code", "name", "employee_no", "entry_no", "sku", "email"):
            value = getattr(entity, attribute, None)
            if value:
                return str(value)[:250]
        return None
