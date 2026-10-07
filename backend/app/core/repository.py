"""Tenant scoped repository helpers.

Every business entity lives inside a company.  Repositories built on top of
``TenantRepository`` always filter by the active company, so a bug in a route
handler cannot expose another company's data.
"""

from __future__ import annotations

import uuid
from typing import Any, Generic, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.database import CompanyScoped
from app.core.errors import NotFoundError, TenantError

ModelT = TypeVar("ModelT")


class TenantRepository(Generic[ModelT]):
    """CRUD operations automatically scoped to the active company."""

    model: type[ModelT]

    def __init__(self, db: Session, company_id: uuid.UUID | None) -> None:
        if company_id is None:
            raise TenantError("An active company context is required for this operation")
        self.db = db
        self.company_id = company_id

    # ------------------------------------------------------------------ reads
    def base_query(self) -> Select:
        stmt = select(self.model)
        if issubclass(self.model, CompanyScoped):
            stmt = stmt.where(self.model.company_id == self.company_id)  # type: ignore[attr-defined]
        return stmt

    def get(self, entity_id: uuid.UUID, *, include_deleted: bool = False) -> ModelT | None:
        stmt = self.base_query().where(self.model.id == entity_id)  # type: ignore[attr-defined]
        if not include_deleted and hasattr(self.model, "deleted_at"):
            stmt = stmt.where(self.model.deleted_at.is_(None))  # type: ignore[attr-defined]
        return self.db.execute(stmt).scalars().first()

    def get_or_404(self, entity_id: uuid.UUID, *, include_deleted: bool = False) -> ModelT:
        entity = self.get(entity_id, include_deleted=include_deleted)
        if entity is None:
            raise NotFoundError(f"{self.model.__name__} not found", entity=str(entity_id))
        return entity

    def get_by(self, **kwargs: Any) -> ModelT | None:
        stmt = self.base_query()
        for key, value in kwargs.items():
            stmt = stmt.where(getattr(self.model, key) == value)
        if hasattr(self.model, "deleted_at"):
            stmt = stmt.where(self.model.deleted_at.is_(None))  # type: ignore[attr-defined]
        return self.db.execute(stmt).scalars().first()

    def exists(self, **kwargs: Any) -> bool:
        return self.get_by(**kwargs) is not None

    def all(self, *criteria: Any, limit: int | None = None) -> list[ModelT]:
        stmt = self.base_query()
        if criteria:
            stmt = stmt.where(*criteria)
        if hasattr(self.model, "deleted_at"):
            stmt = stmt.where(self.model.deleted_at.is_(None))  # type: ignore[attr-defined]
        stmt = stmt.order_by(self.model.created_at.desc())  # type: ignore[attr-defined]
        if limit:
            stmt = stmt.limit(limit)
        return list(self.db.execute(stmt).scalars().unique().all())

    def count(self, *criteria: Any) -> int:
        stmt = select(func.count()).select_from(self.model)
        if issubclass(self.model, CompanyScoped):
            stmt = stmt.where(self.model.company_id == self.company_id)  # type: ignore[attr-defined]
        if criteria:
            stmt = stmt.where(*criteria)
        return int(self.db.execute(stmt).scalar_one() or 0)

    # ----------------------------------------------------------------- writes
    def create(self, **values: Any) -> ModelT:
        if issubclass(self.model, CompanyScoped):
            values.pop("company_id", None)
            values["company_id"] = self.company_id
        entity = self.model(**values)
        self.db.add(entity)
        self.db.flush()
        return entity

    def update(self, entity: ModelT, **values: Any) -> ModelT:
        values.pop("company_id", None)
        values.pop("id", None)
        for key, value in values.items():
            if value is None and key in {"deleted_at"}:
                continue
            setattr(entity, key, value)
        self.db.flush()
        return entity

    def soft_delete(self, entity: ModelT) -> None:
        if hasattr(entity, "soft_delete"):
            entity.soft_delete()  # type: ignore[attr-defined]
        else:  # pragma: no cover - hard delete fallback for entities without soft delete
            self.db.delete(entity)
        self.db.flush()

    def hard_delete(self, entity: ModelT) -> None:
        self.db.delete(entity)
        self.db.flush()
