"""Alembic environment.

The URL and metadata come from the application itself, so migrations always
match the models: ``alembic upgrade head`` works against SQLite in development
and against PostgreSQL in production without editing this file.
"""

from __future__ import annotations

import warnings
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

warnings.filterwarnings("ignore")

from app.core.config import settings  # noqa: E402
from app.core.database import Base  # noqa: E402

import app.models_registry  # noqa: F401,E402  (importing registers every mapper)

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _include_object(object_, name: str, type_: str, reflected: bool, compare_to) -> bool:
    if type_ == "table" and name in {"spatial_ref_sys"}:
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = settings.database_url
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_object=_include_object,
            # SQLite cannot ALTER most column definitions; batch mode rewrites the
            # table instead, which keeps local upgrades working.
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
