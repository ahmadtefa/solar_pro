"""Realtime channels.

The only channel shipped today is ``/api/v1/ws/notifications``: the client opens
it with an access token and receives the unread counter plus a push every time a
notification is created for the user.  The connection is read-only for the
server (the client may send ``{"type": "ping"}`` keep-alives).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.database import SessionLocal, set_session_tenant
from app.core.errors import AppError
from app.services.auth_service import AuthService
from app.services.notification_service import NotificationService

logger = logging.getLogger("kayan.ws")
router = APIRouter()

HEARTBEAT_SECONDS = 20


class ConnectionManager:
    """Tracks live sockets per user and company."""

    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, user_id: uuid.UUID, socket: WebSocket) -> None:
        await socket.accept()
        async with self._lock:
            self._connections.setdefault(user_id, set()).add(socket)

    async def disconnect(self, user_id: uuid.UUID, socket: WebSocket) -> None:
        async with self._lock:
            sockets = self._connections.get(user_id)
            if sockets is not None:
                sockets.discard(socket)
                if not sockets:
                    self._connections.pop(user_id, None)

    async def send_to_user(self, user_id: uuid.UUID, payload: dict[str, Any]) -> int:
        async with self._lock:
            sockets = list(self._connections.get(user_id, ()))
        delivered = 0
        for socket in sockets:
            try:
                await socket.send_text(json.dumps(payload, default=str))
                delivered += 1
            except Exception:  # pragma: no cover - socket already closing
                await self.disconnect(user_id, socket)
        return delivered

    @property
    def users(self) -> int:
        return len(self._connections)


manager = ConnectionManager()


def authenticate(token: str) -> tuple[uuid.UUID, uuid.UUID]:
    """Return ``(user_id, company_id)`` for a WebSocket access token."""
    from app.core.security import decode_token

    payload = decode_token(token, expected_type="access")
    user_id = uuid.UUID(str(payload.get("sub")))
    company_id = payload.get("cid")
    if not company_id:
        raise AppError("The token is not bound to a company")
    return user_id, uuid.UUID(str(company_id))


@router.websocket("/ws/notifications")
async def notifications_channel(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
) -> None:
    try:
        user_id, company_id = authenticate(token)
    except Exception:
        await websocket.close(code=4401, reason="unauthorized")
        return

    with SessionLocal() as session:
        set_session_tenant(session, company_id)
        auth = AuthService(session)
        if not auth.has_company_access(user_id, company_id):
            await websocket.close(code=4403, reason="forbidden")
            return
        unread = NotificationService(session, company_id).unread_count(user_id)

    await manager.connect(user_id, websocket)
    try:
        await websocket.send_text(
            json.dumps(
                {
                    "type": "ready",
                    "user_id": str(user_id),
                    "company_id": str(company_id),
                    "unread": unread,
                    "at": datetime.now(UTC).isoformat(),
                },
                default=str,
            )
        )
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=HEARTBEAT_SECONDS)
            except TimeoutError:
                with SessionLocal() as session:
                    set_session_tenant(session, company_id)
                    unread = NotificationService(session, company_id).unread_count(user_id)
                await websocket.send_text(
                    json.dumps({"type": "heartbeat", "unread": unread, "at": datetime.now(UTC).isoformat()})
                )
                continue
            payload = _parse(message)
            if payload.get("type") in {"ping", "heartbeat"}:
                await websocket.send_text(
                    json.dumps({"type": "pong", "at": datetime.now(UTC).isoformat()}, default=str)
                )
            elif payload.get("type") == "unread":
                with SessionLocal() as session:
                    set_session_tenant(session, company_id)
                    unread = NotificationService(session, company_id).unread_count(user_id)
                await websocket.send_text(json.dumps({"type": "unread", "unread": unread}))
    except WebSocketDisconnect:
        pass
    except Exception:  # pragma: no cover - network failures are expected
        logger.debug("notification socket closed unexpectedly", exc_info=True)
    finally:
        with contextlib.suppress(Exception):
            await manager.disconnect(user_id, websocket)


def _parse(message: str) -> dict[str, Any]:
    try:
        payload = json.loads(message)
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def broadcast(user_id: uuid.UUID, payload: dict[str, Any]) -> int:
    """Fire-and-forget push used by services through the notification hook."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:  # pragma: no cover - called outside the event loop
        return 0
    loop.create_task(manager.send_to_user(user_id, payload))
    return 1


__all__ = ["router", "manager", "broadcast"]
