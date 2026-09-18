"""Integration checks for the initial database migration."""

from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from alembic import command
from app.config import PROJECT_ROOT


def assert_migrated_schema(connection: Connection) -> None:
    """Verify application tables, current revision, and model compatibility."""
    expected_tables = {
        "feed_sources",
        "pipeline_runs",
        "feed_fetches",
        "news_items",
        "digests",
        "digest_items",
        "delivery_attempts",
        "news_pipeline_alembic_version",
    }

    assert set(inspect(connection).get_table_names()) == expected_tables

    migration_context = MigrationContext.configure(
        connection,
        opts={"version_table": "news_pipeline_alembic_version"},
    )
    assert migration_context.get_current_revision() == "0001"

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.attributes["connection"] = connection
    command.check(config)


async def test_initial_migration_matches_models(db_engine: AsyncEngine) -> None:
    """Require migration-created tables to match the registered ORM models."""
    async with db_engine.begin() as connection:
        await connection.run_sync(assert_migrated_schema)
