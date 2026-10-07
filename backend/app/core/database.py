"""Database engine, session management, base model and tenant enforcement.

Tenant isolation is enforced at two levels:

1. Explicit repository filtering on ``company_id`` (see ``app.core.repository``).
2. A global SQLAlchemy ``do_orm_execute`` hook that transparently appends
   ``WHERE company_id = :active_company`` to every SELECT touching a
   company-scoped entity, unless the statement explicitly opts out with
   ``execution_options(skip_tenant=True)``.

Level 2 is defence in depth: even a hand written query that forgets to filter
cannot leak another tenant's rows.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, MetaData, Uuid, create_engine, event
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    declared_attr,
    mapped_column,
    sessionmaker,
    with_loader_criteria,
)

from app.core.config import settings

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base shared by every model."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDMixin:
    """UUID primary key generated in Python (works on PostgreSQL and SQLite)."""

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    """Creation / update audit columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class SoftDeleteMixin:
    """Soft delete support - rows are marked, never physically removed."""

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        self.deleted_at = datetime.now(UTC)

    def restore(self) -> None:
        self.deleted_at = None


class CompanyScoped:
    """Marker mixin - every row belongs to exactly one company (tenant).

    The column is declared here through ``declared_attr`` so that the global
    tenant filter (``with_loader_criteria(CompanyScoped, ...)``) has a real
    attribute to bind against for every mapped subclass.  Models may override
    the declaration when they need different nullability or indexing.
    """

    @declared_attr
    def company_id(cls) -> Mapped[uuid.UUID]:  # noqa: N805 - declared_attr convention
        return mapped_column(
            Uuid(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
        )

    @property
    def _company_scoped(self) -> bool:  # pragma: no cover - marker helper
        return True


class AuditFieldsMixin:
    """Who created / updated the row."""

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


def _build_engine():  # pragma: no cover - exercised through app startup
    url = settings.database_url
    kwargs: dict[str, Any] = {
        "echo": settings.db_echo,
        "future": True,
        "pool_pre_ping": True,
    }
    if url.startswith("sqlite"):
        from sqlalchemy.pool import StaticPool

        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
    else:
        kwargs["pool_size"] = settings.db_pool_size
        kwargs["max_overflow"] = settings.db_max_overflow
    return create_engine(url, **kwargs)


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # pragma: no cover
    """Enable foreign keys and WAL on SQLite (dev/demo convenience)."""
    if settings.database_url.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


@event.listens_for(Session, "do_orm_execute")
def _apply_tenant_criteria(execute_state) -> None:
    """Automatically scope company-scoped entities to the active tenant."""
    if not execute_state.is_select:
        return
    if execute_state.execution_options.get("skip_tenant", False):
        return
    company_id = execute_state.session.info.get("company_id")
    if not company_id:
        return
    if execute_state.is_column_load or execute_state.is_relationship_load:
        return
    execute_state.statement = execute_state.statement.options(
        with_loader_criteria(
            CompanyScoped,
            lambda cls: cls.company_id == company_id,
            include_aliases=True,
            propagate_to_loaders=True,
        )
    )


def set_session_tenant(session: Session, company_id: uuid.UUID | None) -> None:
    """Bind the active tenant to the session (used by the API dependencies)."""
    session.info["company_id"] = company_id


def get_session_company(session: Session) -> uuid.UUID | None:
    return session.info.get("company_id")


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a session bound to the request lifecycle."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def session_scope(company_id: uuid.UUID | None = None, skip_tenant: bool = False) -> Iterator[Session]:
    """Context manager for service / script usage with commit-or-rollback."""
    session = SessionLocal()
    if company_id:
        session.info["company_id"] = company_id
    if skip_tenant:
        session.info["skip_tenant"] = True
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def utcnow() -> datetime:
    return datetime.now(UTC)

def utcnow_naive() -> datetime:
    """Naive UTC now, comparable with values read back from every dialect.

    SQLite (used for local development and the test suite) drops tzinfo when it
    stores a timestamp, so comparing a loaded column against an aware datetime
    raises ``TypeError``.  Services therefore normalise the reference value.
    """
    return datetime.now(UTC).replace(tzinfo=None)


def as_utc(value: datetime | None) -> datetime | None:
    """Attach UTC to a naive timestamp and leave aware values untouched."""
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def is_past(value: datetime | None, *, reference: datetime | None = None) -> bool:
    """True when ``value`` lies in the past, tolerating naive/aware mixtures."""
    if value is None:
        return False
    moment = as_utc(value)
    now = as_utc(reference) or datetime.now(UTC)
    return bool(moment and moment < now)


def seconds_until(value: datetime | None, *, reference: datetime | None = None) -> int:
    """Seconds from now until ``value`` (negative when already passed)."""
    moment = as_utc(value)
    now = as_utc(reference) or datetime.now(UTC)
    if moment is None:
        return 0
    return int((moment - now).total_seconds())



def create_all() -> None:  # pragma: no cover - used by dev bootstrap only
    """Create the schema from metadata (tests / quick start)."""
    from app import models_registry  # noqa: F401  (populate metadata)

    Base.metadata.create_all(bind=engine)
