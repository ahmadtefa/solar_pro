"""Generic, permission-aware CRUD router factory.

Routes stay thin: this module owns HTTP concerns (pagination, filtering,
serialisation) while every rule lives in the models/services.  Anything with a
document lifecycle gets bespoke endpoints instead of this factory.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Body, Depends, Request, status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import DB, CurrentUser, CurrentUserDep, audit_context
from app.core.errors import ConflictError, NotFoundError, ValidationFailure
from app.core.pagination import PageParams


def serialise(entity: Any, fields: Sequence[str] | None = None, *, exclude: Iterable[str] = ()) -> dict[str, Any]:
    """Serialise a mapped object without leaking internals or relationships."""
    excluded = set(exclude)
    if fields:
        names = [name for name in fields if name not in excluded]
    else:
        names = [column.name for column in entity.__mapper__.columns if column.name not in excluded]
    out: dict[str, Any] = {}
    for name in names:
        if not hasattr(entity, name):
            continue
        value = getattr(entity, name, None)
        if isinstance(value, (Decimal, uuid.UUID, date, datetime)):
            value = str(value)
        out[name] = value
    return out


class ResourceSpec:
    """Describes a CRUD resource: model, permissions and searchable columns."""

    def __init__(
        self,
        *,
        name: str,
        model: type[Any],
        module: str,
        entity: str,
        search_fields: Sequence[str] = (),
        default_sort: str = "created_at",
        label_field: str | None = None,
        list_fields: Sequence[str] | None = None,
        create_handler: Callable[..., Any] | None = None,
        update_handler: Callable[..., Any] | None = None,
        delete_handler: Callable[..., Any] | None = None,
        filters: dict[str, str] | None = None,
        soft_delete: bool = True,
    ) -> None:
        self.name = name
        self.model = model
        self.module = module
        self.entity = entity
        self.search_fields = list(search_fields)
        self.default_sort = default_sort
        self.label_field = label_field
        self.list_fields = list(list_fields) if list_fields else None
        self.create_handler = create_handler
        self.update_handler = update_handler
        self.delete_handler = delete_handler
        self.filters = filters or {}
        self.soft_delete = soft_delete

    # ------------------------------------------------------------------ utils
    @property
    def view_permission(self) -> str:
        return f"{self.module}.{self.entity}.view"

    @property
    def create_permission(self) -> str:
        return f"{self.module}.{self.entity}.create"

    @property
    def edit_permission(self) -> str:
        return f"{self.module}.{self.entity}.edit"

    @property
    def delete_permission(self) -> str:
        return f"{self.module}.{self.entity}.delete"

    def columns(self) -> list[str]:
        return [column.name for column in self.model.__mapper__.columns]

    def label(self, entity: Any) -> str | None:
        if self.label_field:
            return getattr(entity, self.label_field, None)
        for candidate in ("name", "document_no", "code"):
            if hasattr(entity, candidate):
                return getattr(entity, candidate, None)
        return None

    def apply_filters(self, stmt: Select[Any], params: dict[str, Any]) -> Select[Any]:
        for query_name, column_name in self.filters.items():
            value = params.get(query_name)
            if value in (None, ""):
                continue
            column = getattr(self.model, column_name, None)
            if column is None:
                continue
            stmt = stmt.where(column == value)
        return stmt


def build_crud_router(spec: ResourceSpec, *, tags: Sequence[str] | None = None) -> APIRouter:
    """Create a router exposing list/get/create/update/delete for a resource."""
    router = APIRouter(tags=list(tags or [spec.name]))

    def _base_statement(current: CurrentUser) -> Select[Any]:
        stmt = select(spec.model)
        if hasattr(spec.model, "company_id"):
            stmt = stmt.where(spec.model.company_id == current.company_id)
        if hasattr(spec.model, "deleted_at"):
            stmt = stmt.where(spec.model.deleted_at.is_(None))
        return stmt

    def _search(stmt: Select[Any], term: str) -> Select[Any]:
        conditions = []
        for field in spec.search_fields:
            column = getattr(spec.model, field, None)
            if column is None:
                continue
            conditions.append(column.ilike(f"%{term}%"))
        return stmt.where(or_(*conditions)) if conditions else stmt

    @router.get("", summary=f"List {spec.name}")
    def list_items(
        request: Request,
        db: DB,
        current: CurrentUserDep,
        params: PageParams = Depends(),
    ) -> dict[str, Any]:
        current.require(spec.view_permission)
        query = {key: value for key, value in request.query_params.items() if value not in (None, "")}
        stmt = spec.apply_filters(_base_statement(current), query)
        if params.q:
            stmt = _search(stmt, params.q)
        total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        sort_column = getattr(spec.model, params.sort_by, None) if params.sort_by else None
        if sort_column is None:
            sort_column = getattr(spec.model, spec.default_sort, None) or spec.model.id
        stmt = stmt.order_by(sort_column.desc() if params.sort_dir == "desc" else sort_column.asc())
        records = db.execute(stmt.offset(params.offset).limit(params.limit)).scalars().unique().all()
        return {
            "items": [serialise(record, spec.list_fields) for record in records],
            "total": total,
            "page": params.page,
            "page_size": params.page_size,
            "pages": (total + params.page_size - 1) // params.page_size if params.page_size else 0,
        }

    @router.get("/{item_id}", summary=f"Get one {spec.name} record")
    def get_item(item_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
        current.require(spec.view_permission)
        record = db.execute(_base_statement(current).where(spec.model.id == item_id)).scalars().first()
        if record is None:
            raise NotFoundError(f"{spec.name.title()} not found", id=str(item_id))
        return serialise(record)

    @router.post("", status_code=status.HTTP_201_CREATED, summary=f"Create {spec.name}")
    def create_item(
        db: DB,
        current: CurrentUserDep,
        payload: dict[str, Any] = Body(...),
    ) -> dict[str, Any]:
        current.require(spec.create_permission)
        if spec.create_handler is not None:
            record = spec.create_handler(db, current, payload)
        else:
            values = _filtered_values(spec, payload)
            if hasattr(spec.model, "company_id"):
                values.setdefault("company_id", current.company_id)
            record = spec.model(**values)
            db.add(record)
            db.flush()
        db.flush()
        return {"id": str(record.id), "label": spec.label(record), "record": serialise(record)}

    @router.put("/{item_id}", summary=f"Update {spec.name}")
    def update_item(
        item_id: uuid.UUID,
        db: DB,
        current: CurrentUserDep,
        payload: dict[str, Any] = Body(...),
    ) -> dict[str, Any]:
        current.require(spec.edit_permission)
        record = db.execute(_base_statement(current).where(spec.model.id == item_id)).scalars().first()
        if record is None:
            raise NotFoundError(f"{spec.name.title()} not found", id=str(item_id))
        if spec.update_handler is not None:
            record = spec.update_handler(db, current, record, payload)
        else:
            for key, value in _filtered_values(spec, payload).items():
                if key in {"id", "company_id", "created_at"}:
                    continue
                if hasattr(record, key):
                    setattr(record, key, value)
        db.flush()
        return {"id": str(record.id), "record": serialise(record)}

    @router.delete("/{item_id}", summary=f"Delete {spec.name}")
    def delete_item(item_id: uuid.UUID, db: DB, current: CurrentUserDep) -> dict[str, Any]:
        current.require(spec.delete_permission)
        record = db.execute(_base_statement(current).where(spec.model.id == item_id)).scalars().first()
        if record is None:
            raise NotFoundError(f"{spec.name.title()} not found", id=str(item_id))
        if spec.delete_handler is not None:
            spec.delete_handler(db, current, record)
        elif spec.soft_delete and hasattr(record, "deleted_at"):
            record.deleted_at = datetime.now(tz=None).astimezone()
        else:
            db.delete(record)
        db.flush()
        return {"id": str(item_id), "deleted": True}

    return router


def _filtered_values(spec: ResourceSpec, payload: dict[str, Any]) -> dict[str, Any]:
    """Keep only payload keys that map onto real model columns."""
    columns = set(spec.columns())
    return {key: value for key, value in payload.items() if key in columns}


def guarded_create(model: type[Any], *, unique: Sequence[tuple[str, str]] = ()) -> Callable[..., Any]:
    """Build a create handler enforcing unique columns before insert."""

    def handler(db: Session, current: CurrentUser, payload: dict[str, Any]) -> Any:
        for field, label in unique:
            value = payload.get(field)
            if value in (None, ""):
                continue
            existing = db.execute(
                select(model).where(
                    model.company_id == current.company_id,
                    getattr(model, field) == value,
                )
            ).scalars().first()
            if existing is not None:
                raise ConflictError(f"{label} '{value}' already exists")
        values = {key: value for key, value in payload.items() if key in {c.name for c in model.__mapper__.columns}}
        values.setdefault("company_id", current.company_id)
        record = model(**values)
        db.add(record)
        db.flush()
        return record

    return handler


def guarded_update(model: type[Any]) -> Callable[..., Any]:
    """Build an update handler restricted to real, non-audit columns."""

    readonly = {"id", "company_id", "created_at", "updated_at", "deleted_at"}

    def handler(db: Session, current: CurrentUser, record: Any, payload: dict[str, Any]) -> Any:
        if hasattr(record, "status") and record.status in {"posted", "cancelled"}:
            raise ValidationFailure("Posted or cancelled records cannot be edited")
        columns = {c.name for c in model.__mapper__.columns}
        for key, value in payload.items():
            if key in readonly or key not in columns:
                continue
            setattr(record, key, value)
        db.flush()
        return record

    return handler


def audit_aware_create(model: type[Any]) -> Callable[..., Any]:
    """Create handler that also writes an audit entry for the actor."""

    def handler(db: Session, current: CurrentUser, payload: dict[str, Any]) -> Any:
        columns = {c.name for c in model.__mapper__.columns}
        values = {key: value for key, value in payload.items() if key in columns}
        values.setdefault("company_id", current.company_id)
        record = model(**values)
        db.add(record)
        db.flush()
        from app.services.audit_service import AuditService

        AuditService(db, audit_context(current)).log_create(
            record, entity_type=model.__tablename__, label=getattr(record, "code", None) or str(record.id)
        )
        return record

    return handler


__all__ = [
    "ResourceSpec",
    "audit_aware_create",
    "build_crud_router",
    "guarded_create",
    "guarded_update",
    "serialise",
]
