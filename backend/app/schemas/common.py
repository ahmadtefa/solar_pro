"""Schemas shared by every router."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    """Base for response models read straight from SQLAlchemy objects."""

    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    message: str
    detail: dict[str, Any] | None = None


class IdResponse(BaseModel):
    id: uuid.UUID
    label: str | None = None


class BulkResult(BaseModel):
    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[dict[str, Any]] = Field(default_factory=list)


class PageResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


class LookupItem(BaseModel):
    id: uuid.UUID
    code: str | None = None
    name: str | None = None
    label: str | None = None


class DocumentActionRequest(BaseModel):
    reason: str | None = Field(None, max_length=400)


class PostRequest(BaseModel):
    allow_draft: bool = False


class ApproveRequest(BaseModel):
    remarks: str | None = Field(None, max_length=400)


class CancelRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=400)


class RejectRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=400)


class DateRangeParams(BaseModel):
    date_from: date | None = None
    date_to: date | None = None


class MoneyOut(BaseModel):
    amount: Decimal
    currency_code: str | None = None


class CountResponse(BaseModel):
    key: str
    count: int


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    environment: str
    time: datetime


__all__ = [
    "ApproveRequest",
    "BulkResult",
    "CancelRequest",
    "CountResponse",
    "DateRangeParams",
    "DocumentActionRequest",
    "HealthResponse",
    "IdResponse",
    "LookupItem",
    "MessageResponse",
    "MoneyOut",
    "ORMModel",
    "PageResponse",
    "PostRequest",
    "RejectRequest",
]
