"""Small, dependency-free coercion helpers shared by services and schemas.

API payloads arrive as JSON, so values that end up in ``Uuid`` columns are
strings.  Coercing them here keeps the type guarantees at the model boundary
without sprinkling ``uuid.UUID(str(...))`` through every service.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

__all__ = ["as_uuid", "as_uuid_list", "as_decimal", "as_date", "as_int", "as_bool", "is_uuid_like"]


def as_uuid(value: Any) -> uuid.UUID | None:
    """Return a ``UUID`` for ``value`` (``None``/empty string pass through)."""
    if value is None or value == "":
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError(f"Invalid UUID value: {value!r}") from exc


def as_uuid_list(values: Any) -> list[uuid.UUID]:
    if not values:
        return []
    return [as_uuid(item) for item in values if item]  # type: ignore[misc]


def as_decimal(value: Any, default: str = "0") -> Decimal:
    if value is None or value == "":
        return Decimal(default)
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid decimal value: {value!r}") from exc


def as_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def as_int(value: Any, default: int | None = None) -> int | None:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


def is_uuid_like(value: Any) -> bool:
    try:
        as_uuid(value)
        return True
    except ValueError:
        return False
