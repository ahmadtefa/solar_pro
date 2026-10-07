"""Notification centre, preferences and outbound message queue."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.crud import serialise
from app.api.deps import DB, CurrentUserDep
from app.core.errors import NotFoundError, ValidationFailure
from app.models.identity import Notification, OutboxMessage
from app.services.notification_service import NotificationService

router = APIRouter()

EXTERNAL_CHANNELS = {"email", "sms", "push", "whatsapp"}


@router.get("", summary="My notifications")
def list_notifications(
    db: DB,
    current: CurrentUserDep,
    unread_only: bool = False,
    module: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    current.require("core.notification.view")
    service = NotificationService(db, current.company_id)
    rows, total = service.list_for_user(current.id, unread_only=unread_only, limit=limit, offset=offset)
    if module:
        rows = [row for row in rows if row.module == module]
    return {
        "items": [serialise(row) for row in rows],
        "total": total,
        "unread": service.unread_count(current.id),
        "limit": limit,
        "offset": offset,
    }


@router.get("/unread-count", summary="Unread badge count")
def unread_count(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.notification.view")
    return {"unread": NotificationService(db, current.company_id).unread_count(current.id)}


@router.post("/{notification_id}/read", summary="Mark one notification as read")
def mark_read(notification_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.notification.edit")
    service = NotificationService(db, current.company_id)
    notification = db.get(Notification, notification_id)
    if notification is None or notification.company_id != current.company_id:
        raise NotFoundError("Notification not found", id=str(notification_id))
    if notification.user_id != current.id and not current.is_superuser:
        raise NotFoundError("Notification not found", id=str(notification_id))
    service.mark_read(current.id, [notification_id])
    db.flush()
    return {"id": str(notification_id), "is_read": True}


@router.post("/read-all", summary="Mark every notification as read")
def mark_all_read(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.notification.edit")
    service = NotificationService(db, current.company_id)
    updated = service.mark_read(current.id, None)
    db.flush()
    return {"marked": updated, "unread": service.unread_count(current.id)}


@router.delete("/{notification_id}", summary="Delete a notification")
def delete_notification(notification_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.notification.delete")
    service = NotificationService(db, current.company_id)
    notification = db.get(Notification, notification_id)
    if notification is None or notification.company_id != current.company_id or notification.user_id != current.id:
        raise NotFoundError("Notification not found", id=str(notification_id))
    service.delete(current.id, notification_id)
    db.flush()
    return {"id": str(notification_id), "deleted": True}


# --------------------------------------------------------------------------- #
# Preferences
# --------------------------------------------------------------------------- #
@router.get("/preferences", summary="My channel preferences")
def list_preferences(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.notification.view")
    rows = NotificationService(db, current.company_id).list_preferences(current.id)
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.put("/preferences", summary="Enable or disable a channel for a module")
def set_preference(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.notification.edit")
    module = payload.get("module")
    channel = payload.get("channel")
    if not module or not channel:
        raise ValidationFailure("module and channel are required")
    quiet = payload.get("quiet_hours")
    preference = NotificationService(db, current.company_id).set_preference(
        current.id,
        module=module,
        channel=channel,
        is_enabled=bool(payload.get("is_enabled", True)),
        quiet_hours=(quiet.get("start"), quiet.get("end")) if isinstance(quiet, dict) else None,
    )
    db.flush()
    return serialise(preference)


# --------------------------------------------------------------------------- #
# Outbox (email / SMS / push / WhatsApp)
# --------------------------------------------------------------------------- #
@router.get("/outbox", summary="Queued outbound messages")
def list_outbox(
    db: DB,
    current: CurrentUserDep,
    status_filter: str | None = Query(None, alias="status"),
    channel: str | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    current.require("core.notification.view")
    stmt = select(OutboxMessage).where(OutboxMessage.company_id == current.company_id)
    if status_filter:
        stmt = stmt.where(OutboxMessage.status == status_filter)
    if channel:
        stmt = stmt.where(OutboxMessage.channel == channel)
    rows = db.execute(
        stmt.order_by(OutboxMessage.created_at.desc()).limit(limit)
    ).scalars().all()
    return {"items": [serialise(row) for row in rows], "total": len(rows)}


@router.post("/send", status_code=201, summary="Queue an outbound message")
def queue_message(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.notification.edit")
    channel = (payload.get("channel") or "").lower()
    recipient = payload.get("recipient")
    body = payload.get("body")
    if channel not in EXTERNAL_CHANNELS:
        raise ValidationFailure(f"channel must be one of {sorted(EXTERNAL_CHANNELS)}")
    if not recipient or not body:
        raise ValidationFailure("recipient and body are required")
    scheduled_at = payload.get("scheduled_at")
    message = NotificationService(db, current.company_id).queue_message(
        channel=channel,
        recipient=recipient,
        body=body,
        subject=payload.get("subject"),
        template_code=payload.get("template_code"),
        payload=payload.get("payload"),
        scheduled_at=datetime.fromisoformat(scheduled_at) if scheduled_at else None,
    )
    db.flush()
    return serialise(message)


@router.post("/outbox/flush", summary="Drain the outbound queue through the provider")
def flush_outbox(db: DB, current: CurrentUserDep, limit: int = Query(50, ge=1, le=500)) -> dict[str, Any]:
    current.require("core.notification.edit")
    result = NotificationService(db, current.company_id).send_pending(limit=limit)
    db.flush()
    return result


@router.post("/broadcast", status_code=201, summary="Broadcast to users or a role")
def broadcast(payload: dict[str, Any], db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.notification.edit")
    title = payload.get("title")
    if not title:
        raise ValidationFailure("title is required")
    service = NotificationService(db, current.company_id)
    if payload.get("role_code"):
        rows = service.notify_role(
            role_code=payload["role_code"],
            company_id=current.company_id,
            title=title,
            body=payload.get("body"),
            notification_type=payload.get("notification_type") or "info",
            module=payload.get("module") or "core",
            action_url=payload.get("action_url"),
            send_external=bool(payload.get("send_external", False)),
        )
    elif payload.get("user_ids"):
        rows = service.notify_users(
            [uuid.UUID(str(item)) for item in payload["user_ids"]],
            title=title,
            body=payload.get("body"),
            notification_type=payload.get("notification_type") or "info",
            module=payload.get("module") or "core",
            action_url=payload.get("action_url"),
            send_external=bool(payload.get("send_external", False)),
        )
    else:
        raise ValidationFailure("user_ids or role_code is required")
    db.flush()
    return {"created": len(rows), "items": [serialise(row) for row in rows]}


@router.get("/statistics", summary="Delivery statistics")
def statistics(db: DB, current: CurrentUserDep) -> dict[str, Any]:
    current.require("core.notification.view")
    notifications = db.execute(
        select(Notification.notification_type, func.count(Notification.id))
        .where(Notification.company_id == current.company_id)
        .group_by(Notification.notification_type)
    ).all()
    outbox = db.execute(
        select(OutboxMessage.channel, OutboxMessage.status, func.count(OutboxMessage.id))
        .where(OutboxMessage.company_id == current.company_id)
        .group_by(OutboxMessage.channel, OutboxMessage.status)
    ).all()
    unread = db.execute(
        select(func.count(Notification.id)).where(
            Notification.company_id == current.company_id, Notification.is_read.is_(False)
        )
    ).scalar_one()
    return {
        "by_type": [{"type": row[0], "count": int(row[1])} for row in notifications],
        "outbox": [{"channel": row[0], "status": row[1], "count": int(row[2])} for row in outbox],
        "unread_total": int(unread),
    }


__all__ = ["router"]
