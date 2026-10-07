"""Pagination, sorting and filtering helpers shared by every list endpoint."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, Field
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

T = TypeVar("T")
M = TypeVar("M")

MAX_PAGE_SIZE = 200


class Page(BaseModel, Generic[T]):
    """Envelope returned by every paginated endpoint."""

    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def build(cls, items: Sequence[T], total: int, page: int, page_size: int) -> Page[T]:
        pages = (total + page_size - 1) // page_size if page_size else 0
        return cls(items=list(items), total=total, page=page, page_size=page_size, pages=pages)


class PageParams:
    """FastAPI dependency for list endpoints: pagination, sort and search."""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="1-based page number"),
        page_size: int = Query(25, ge=1, le=MAX_PAGE_SIZE, description="Rows per page"),
        q: str | None = Query(None, description="Free text search"),
        sort_by: str | None = Query(None, description="Column to sort by"),
        sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    ) -> None:
        self.page = page
        self.page_size = page_size
        self.q = (q or "").strip() or None
        self.sort_by = sort_by
        self.sort_dir = sort_dir

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size

    def dict(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "page_size": self.page_size,
            "q": self.q,
            "sort_by": self.sort_by,
            "sort_dir": self.sort_dir,
        }


@dataclass(slots=True)
class FilterSpec:
    """Declarative description of the filters a list endpoint accepts."""

    field: str
    column: Any
    operator: str = "eq"  # eq|in|gte|lte|like|isnull
    cast: Callable[[str], Any] | None = None


def build_filters(specs: Sequence[FilterSpec], values: dict[str, Any]) -> list[Any]:
    """Translate raw query values into SQLAlchemy criteria."""
    criteria: list[Any] = []
    for spec in specs:
        raw = values.get(spec.field)
        if raw is None or raw == "":
            continue
        value = spec.cast(raw) if spec.cast else raw
        match spec.operator:
            case "eq":
                criteria.append(spec.column == value)
            case "in":
                if isinstance(value, str):
                    value = [part.strip() for part in value.split(",") if part.strip()]
                criteria.append(spec.column.in_(value))
            case "gte":
                criteria.append(spec.column >= value)
            case "lte":
                criteria.append(spec.column <= value)
            case "like":
                criteria.append(spec.column.ilike(f"%{value}%"))
            case "isnull":
                criteria.append(spec.column.is_(None))
            case _:  # pragma: no cover - guarded by the spec author
                raise ValueError(f"Unsupported filter operator: {spec.operator}")
    return criteria


def apply_search(stmt: Select, term: str | None, columns: Sequence[Any]) -> Select:
    if not term or not columns:
        return stmt
    pattern = f"%{term}%"
    conditions = [column.ilike(pattern) for column in columns]
    from sqlalchemy import or_

    return stmt.where(or_(*conditions))


def apply_sort(stmt: Select, params: PageParams, allowed: dict[str, Any], default: Any) -> Select:
    column = allowed.get(params.sort_by or "", None)
    if column is None:
        column = default
    direction = "desc" if params.sort_dir == "desc" else "asc"
    return stmt.order_by(column.desc() if direction == "desc" else column.asc())


def paginate_query(db: Session, stmt: Select, params: PageParams) -> tuple[list[Any], int]:
    """Execute ``stmt`` returning a page of ORM entities plus the total count."""
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = int(db.execute(count_stmt).scalar_one() or 0)
    rows = db.execute(stmt.offset(params.offset).limit(params.limit)).scalars().unique().all()
    return rows, total


def serialize_value(value: Any) -> Any:
    """JSON friendly conversion used by audit snapshots and exports."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): serialize_value(item) for key, item in value.items()}
    return value


def snapshot(entity: Any, fields: Sequence[str] | None = None) -> dict[str, Any]:
    """Take a JSON-serialisable snapshot of a model instance for auditing."""
    if entity is None:
        return {}
    mapper = getattr(type(entity), "__mapper__", None)
    if mapper is None:
        return {}
    names = fields or [column.key for column in mapper.columns]
    data: dict[str, Any] = {}
    for name in names:
        if not hasattr(entity, name):
            continue
        data[name] = serialize_value(getattr(entity, name))
    return data


class IdsPayload(BaseModel):
    """Payload for bulk operations."""

    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
