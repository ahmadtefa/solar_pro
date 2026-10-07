"""JSON helpers shared by services that persist metadata payloads."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any


def json_safe(value: Any) -> Any:
    """Return a JSON serialisable copy of ``value``.

    ``Decimal``/``UUID``/``date``/``datetime`` values are converted to strings so
    they can be stored in the platform's JSON/JSONB metadata columns on every
    supported database (SQLite keeps JSON as text, PostgreSQL uses JSONB).
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    return str(value)


__all__ = ["json_safe"]
