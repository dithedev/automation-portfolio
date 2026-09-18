"""Configure offline and async online database migrations."""

import asyncio
from logging.config import fileConfig

from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from alembic import context
from app.config import get_settings
from app.infrastructure.db.migrations import VERSION_TABLE, include_name
from app.infrastructure.db.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Generate PostgreSQL migration SQL without loading credentials."""
    context.configure(
        dialect_name="postgresql",
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=False,
        include_name=include_name,
        version_table=VERSION_TABLE,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Execute migration operations through a synchronous connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=False,
        include_name=include_name,
        version_table=VERSION_TABLE,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Open a dedicated migration connection and release it after use."""
    settings = get_settings()
    engine = create_async_engine(
        settings.database_url.get_secret_value(),
        poolclass=NullPool,
        echo=False,
        hide_parameters=True,
        connect_args={
            "timeout": 5,
            "command_timeout": 60,
            "server_settings": {
                "timezone": "UTC",
            },
        },
    )

    try:
        async with engine.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await engine.dispose()


def run_migrations_online() -> None:
    """Run migrations using an injected connection or a dedicated engine."""
    connection = config.attributes.get("connection")

    if isinstance(connection, Connection):
        do_run_migrations(connection)
        return

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
