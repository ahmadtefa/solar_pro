"""Notification centre and outbound messaging.

In-app notifications are stored immediately.  Outbound channels (email, SMS,
push, WhatsApp) are queued in ``outbox_messages``; a provider implementation can
drain the queue (``send_pending``) or be replaced entirely.  When no provider is
configured messages stay ``queued`` so nothing is silently lost.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import NotificationChannel, NotificationType
from app.core.errors import NotFoundError
from app.models.identity import Notification, NotificationPreference, OutboxMessage


class NotificationService:
    def __init__(self, db: Session, company_id: uuid.UUID) -> None:
        self.db = db
        self.company_id = company_id

    # ------------------------------------------------------------------ create
    def notify_users(
        self,
        user_ids: Iterable[uuid.UUID],
        *,
        title: str,
        body: str | None = None,
        notification_type: str = NotificationType.INFO.value,
        module: str | None = None,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        action_url: str | None = None,
        payload: dict[str, Any] | None = None,
        channel: str = NotificationChannel.IN_APP.value,
        send_external: bool = False,
    ) -> list[Notification]:
        created: list[Notification] = []
        for user_id in dict.fromkeys(user_ids):
            if user_id is None:
                continue
            if not self._channel_enabled(user_id, module or "core", channel):
                continue
            notification = Notification(
                company_id=self.company_id,
                user_id=user_id,
                title=title[:250],
                body=body,
                notification_type=notification_type,
                channel=channel,
                module=module,
                entity_type=entity_type,
                entity_id=entity_id,
                action_url=action_url,
                payload_json=payload or {},
                delivery_status="delivered",
                sent_at=datetime.now(UTC),
            )
            self.db.add(notification)
            created.append(notification)
        self.db.flush()
        if send_external and created:
            self.queue_external(created)
        return created

    def notify_role(self, *, role_code: str, company_id: uuid.UUID | None = None, **kwargs: Any) -> list[Notification]:
        from app.models.identity import Role, UserRole

        tenant = company_id or self.company_id
        user_ids = self.db.execute(
            select(UserRole.user_id)
            .join(Role, Role.id == UserRole.role_id)
            .where(Role.company_id == tenant, Role.code == role_code)
        ).scalars().all()
        return self.notify_users(user_ids, **kwargs)

    def _channel_enabled(self, user_id: uuid.UUID, module: str, channel: str) -> bool:
        preference = self.db.execute(
            select(NotificationPreference).where(
                NotificationPreference.company_id == self.company_id,
                NotificationPreference.user_id == user_id,
                NotificationPreference.module == module,
                NotificationPreference.channel == channel,
            )
        ).scalars().first()
        return True if preference is None else bool(preference.is_enabled)

    # ------------------------------------------------------------------ reads
    def list_for_user(
        self, user_id: uuid.UUID, *, unread_only: bool = False, limit: int = 50, offset: int = 0
    ) -> tuple[list[Notification], int]:
        stmt = select(Notification).where(
            Notification.company_id == self.company_id, Notification.user_id == user_id
        )
        if unread_only:
            stmt = stmt.where(Notification.is_read.is_(False))
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = int(self.db.execute(count_stmt).scalar_one() or 0)
        rows = self.db.execute(
            stmt.order_by(Notification.created_at.desc()).offset(offset).limit(limit)
        ).scalars().all()
        return list(rows), total

    def unread_count(self, user_id: uuid.UUID) -> int:
        return int(
            self.db.execute(
                select(func.count()).select_from(Notification).where(
                    Notification.company_id == self.company_id,
                    Notification.user_id == user_id,
                    Notification.is_read.is_(False),
                )
            ).scalar_one()
            or 0
        )

    def mark_read(self, user_id: uuid.UUID, notification_ids: Sequence[uuid.UUID] | None = None) -> int:
        stmt = select(Notification).where(
            Notification.company_id == self.company_id, Notification.user_id == user_id, Notification.is_read.is_(False)
        )
        if notification_ids:
            stmt = stmt.where(Notification.id.in_(list(notification_ids)))
        rows = list(self.db.execute(stmt).scalars().all())
        now = datetime.now(UTC)
        for row in rows:
            row.is_read = True
            row.read_at = now
        self.db.flush()
        return len(rows)

    def delete(self, user_id: uuid.UUID, notification_id: uuid.UUID) -> None:
        row = self.db.execute(
            select(Notification).where(
                Notification.company_id == self.company_id,
                Notification.id == notification_id,
                Notification.user_id == user_id,
            )
        ).scalars().first()
        if row is None:
            raise NotFoundError("Notification not found")
        self.db.delete(row)
        self.db.flush()

    # ------------------------------------------------------------- preferences
    def set_preference(
        self, user_id: uuid.UUID, *, module: str, channel: str, is_enabled: bool, quiet_hours: tuple[str, str] | None = None
    ) -> NotificationPreference:
        preference = self.db.execute(
            select(NotificationPreference).where(
                NotificationPreference.company_id == self.company_id,
                NotificationPreference.user_id == user_id,
                NotificationPreference.module == module,
                NotificationPreference.channel == channel,
            )
        ).scalars().first()
        if preference is None:
            preference = NotificationPreference(
                company_id=self.company_id, user_id=user_id, module=module, channel=channel
            )
            self.db.add(preference)
        preference.is_enabled = is_enabled
        if quiet_hours:
            preference.quiet_hours_start, preference.quiet_hours_end = quiet_hours
        self.db.flush()
        return preference

    def list_preferences(self, user_id: uuid.UUID) -> list[NotificationPreference]:
        return list(
            self.db.execute(
                select(NotificationPreference).where(
                    NotificationPreference.company_id == self.company_id,
                    NotificationPreference.user_id == user_id,
                )
            ).scalars().all()
        )

    # ------------------------------------------------------------------ outbox
    def queue_message(
        self,
        *,
        channel: str,
        recipient: str,
        body: str,
        subject: str | None = None,
        template_code: str | None = None,
        payload: dict[str, Any] | None = None,
        scheduled_at: datetime | None = None,
    ) -> OutboxMessage:
        message = OutboxMessage(
            company_id=self.company_id,
            channel=channel,
            recipient=recipient,
            subject=subject,
            body=body,
            template_code=template_code,
            payload_json=payload or {},
            scheduled_at=scheduled_at,
            status="queued",
        )
        self.db.add(message)
        self.db.flush()
        return message

    def queue_external(self, notifications: Sequence[Notification], channel: str = NotificationChannel.EMAIL.value) -> None:
        for notification in notifications:
            self.queue_message(
                channel=channel,
                recipient=str(notification.user_id),
                subject=notification.title,
                body=notification.body or notification.title,
                payload={"notification_id": str(notification.id), "entity_type": notification.entity_type},
            )
            notification.delivery_status = "queued"

    def send_pending(self, *, limit: int = 50, provider=None) -> dict[str, int]:
        """Drain the outbox.

        ``provider`` is any callable ``(message) -> None``; when it is absent the
        messages remain queued (documented behaviour, not a silent failure).
        """
        messages = list(
            self.db.execute(
                select(OutboxMessage)
                .where(
                    OutboxMessage.company_id == self.company_id,
                    OutboxMessage.status == "queued",
                )
                .order_by(OutboxMessage.created_at.asc())
                .limit(limit)
            ).scalars().all()
        )
        sent = failed = 0
        for message in messages:
            if provider is None:
                break
            message.attempts += 1
            try:
                provider(message)
                message.status = "sent"
                message.sent_at = datetime.now(UTC)
                sent += 1
            except Exception as exc:  # pragma: no cover - provider specific
                message.status = "failed" if message.attempts >= 3 else "queued"
                message.last_error = str(exc)[:500]
                failed += 1
        self.db.flush()
        return {"sent": sent, "failed": failed, "queued": len(messages) - sent - failed}
