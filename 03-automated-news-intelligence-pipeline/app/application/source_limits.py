"""Resolve per-source fetch limits from settings and feed YAML."""

from uuid import UUID

from app.application.feed_ingestion import SourceFetchLimits
from app.config import Settings
from app.domain import Source
from app.infrastructure.feeds.config import MAX_ITEMS_PER_RUN, FeedConfiguration


def resolve_source_limits(
    *,
    settings: Settings,
    feed_configuration: FeedConfiguration,
    sources: tuple[Source, ...],
) -> dict[UUID, SourceFetchLimits]:
    """Build ingest limits keyed by persisted source id."""
    config_by_key = {
        item.to_source(feed_configuration.defaults).key: item for item in feed_configuration.sources
    }
    limits: dict[UUID, SourceFetchLimits] = {}

    for source in sources:
        configured = config_by_key.get(source.key)
        yaml_max = (
            configured.effective_max_items(feed_configuration.defaults)
            if configured is not None
            else settings.max_articles_per_source
        )
        yaml_timeout = (
            configured.effective_timeout_seconds(feed_configuration.defaults)
            if configured is not None
            else int(settings.http_timeout_seconds)
        )
        limits[source.id] = SourceFetchLimits(
            max_entries=min(
                settings.max_articles_per_source,
                yaml_max,
                MAX_ITEMS_PER_RUN,
            ),
            read_timeout_seconds=float(yaml_timeout),
        )

    return limits
