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

__all__ = [
    "as_uuid",
    "as_uuid_list",
    "as_decimal",
    "as_date",
    "as_int",
    "as_bool",
    "is_uuid_like",
    "normalise_payload",
]


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


#: Suffixes that mark a date or a datetime column in a JSON payload.
_DATE_KEYS = {"date_from", "date_to", "as_of", "on_date", "effective_from", "effective_to", "period_start", "period_end"}


def normalise_payload(payload: Any) -> Any:
    """Coerce JSON values into the types the service layer expects.

    HTTP payloads are JSON, so every date arrives as a string while services do
    arithmetic such as ``document_date + timedelta(days=term_days)``.  Walking
    the payload once (dicts and lists of dicts, one level of nesting is enough
    for document headers plus lines) keeps the models clean of defensive casts.
    """
    if isinstance(payload, list):
        return [normalise_payload(item) for item in payload]
    if not isinstance(payload, dict):
        return payload
    normalised: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, (dict, list)):
            normalised[key] = normalise_payload(value)
            continue
        normalised[key] = _coerce_value(key, value)
    return normalised


def _coerce_value(key: str, value: Any) -> Any:
    if value is None or not isinstance(value, str):
        return value
    lowered = key.lower()
    if lowered.endswith("_ids"):
        return value
    if lowered.endswith("_id") or lowered == "id":
        try:
            return as_uuid(value)
        except ValueError:
            return value
    if lowered.endswith("_at"):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    if lowered.endswith("_date") or lowered.endswith("_on") or lowered in _DATE_KEYS:
        try:
            return as_date(value)
        except ValueError:
            return value
    return value
