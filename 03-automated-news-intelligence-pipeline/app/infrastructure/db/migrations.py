"""Ownership boundaries for database migration autogeneration."""

from collections.abc import MutableMapping
from typing import Final, Literal

VERSION_TABLE: Final[str] = "news_pipeline_alembic_version"

MANAGED_TABLES: Final[frozenset[str]] = frozenset(
    {
        "feed_sources",
        "pipeline_runs",
        "feed_fetches",
        "news_items",
        "digests",
        "digest_items",
        "delivery_attempts",
    }
)


def include_name(
    name: str | None,
    type_: Literal[
        "schema",
        "table",
        "column",
        "index",
        "unique_constraint",
        "foreign_key_constraint",
        "check_constraint",
    ],
    parent_names: MutableMapping[
        Literal["schema_name", "table_name", "schema_qualified_table_name"],
        str | None,
    ],
) -> bool:
    """Limit reflected tables to objects owned by this application.

    The ownership list is independent of current model metadata so that
    removing a model can still produce a migration for its former table.
    """
    if type_ == "table":
        return name in MANAGED_TABLES

    return True
