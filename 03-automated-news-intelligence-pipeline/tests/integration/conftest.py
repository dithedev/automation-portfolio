"""Temporary PostgreSQL fixtures for database integration tests."""

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from alembic.config import Config
from sqlalchemy.engine import URL, Connection, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool
from testcontainers.community.postgres import PostgresContainer

from alembic import command
from app.config import PROJECT_ROOT
from app.infrastructure.db.session import build_session_factory


def upgrade_schema(connection: Connection) -> None:
    """Apply migrations through the supplied test connection."""
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.attributes["connection"] = connection
    command.upgrade(config, "head")


def downgrade_schema(connection: Connection) -> None:
    """Remove application tables through the supplied test connection."""
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.attributes["connection"] = connection
    command.downgrade(config, "base")


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[URL]:
    """Start an isolated PostgreSQL container with an automatically assigned port."""
    with PostgresContainer(
        image="postgres:17-bookworm",
        username="pipeline_test",
        password="pipeline_test",
        dbname="pipeline_test",
    ) as postgres:
        url = make_url(postgres.get_connection_url())
        yield url.set(drivername="postgresql+asyncpg")


@pytest_asyncio.fixture
async def db_engine(postgres_url: URL) -> AsyncIterator[AsyncEngine]:
    """Apply migrations before a test and roll them back afterwards."""
    engine = create_async_engine(
        postgres_url,
        poolclass=NullPool,
        echo=False,
        hide_parameters=True,
        connect_args={
            "timeout": 5,
            "command_timeout": 60,
            "server_settings": {"timezone": "UTC"},
        },
    )

    try:
        async with engine.begin() as connection:
            await connection.run_sync(upgrade_schema)

        try:
            yield engine
        finally:
            async with engine.begin() as connection:
                await connection.run_sync(downgrade_schema)
    finally:
        await engine.dispose()


@pytest.fixture
def session_factory(
    db_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Provide independent sessions for transaction visibility checks."""
    return build_session_factory(db_engine)
