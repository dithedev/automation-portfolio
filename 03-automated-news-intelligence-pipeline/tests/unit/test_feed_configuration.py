"""Feed configuration validation checks."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.infrastructure.feeds.config import (
    FeedConfiguration,
    FeedConfigurationError,
    load_feed_configuration,
)


def make_source(**overrides: object) -> dict[str, object]:
    """Build a valid source configuration with selected overrides."""
    return {
        "key": "example-news",
        "name": "Example News",
        "url": "https://example.com/feed.xml",
        "allowed_host": "example.com",
        "category": "artificial_intelligence",
        **overrides,
    }


def test_configuration_applies_defaults() -> None:
    configuration = FeedConfiguration.model_validate(
        {
            "version": 1,
            "defaults": {"enabled": False},
            "sources": [make_source()],
        }
    )

    source = configuration.sources[0].to_source(configuration.defaults)

    assert source.enabled is False
    assert configuration.defaults.max_items_per_run == 20
    assert configuration.defaults.request_timeout_seconds == 15


def test_source_can_override_enabled_default() -> None:
    configuration = FeedConfiguration.model_validate(
        {
            "version": 1,
            "defaults": {"enabled": False},
            "sources": [make_source(enabled=True)],
        }
    )

    source = configuration.sources[0].to_source(configuration.defaults)

    assert source.enabled is True


def test_source_uses_shared_fetch_limits_by_default() -> None:
    configuration = FeedConfiguration.model_validate(
        {
            "version": 1,
            "defaults": {
                "max_items_per_run": 30,
                "request_timeout_seconds": 20,
            },
            "sources": [make_source()],
        }
    )
    source = configuration.sources[0]

    assert source.effective_max_items(configuration.defaults) == 30
    assert source.effective_timeout_seconds(configuration.defaults) == 20


def test_source_can_override_shared_fetch_limits() -> None:
    configuration = FeedConfiguration.model_validate(
        {
            "version": 1,
            "defaults": {
                "max_items_per_run": 30,
                "request_timeout_seconds": 20,
            },
            "sources": [
                make_source(
                    max_items_per_run=10,
                    request_timeout_seconds=5,
                )
            ],
        }
    )
    source = configuration.sources[0]

    assert source.effective_max_items(configuration.defaults) == 10
    assert source.effective_timeout_seconds(configuration.defaults) == 5


@pytest.mark.parametrize(
    "max_items_per_run",
    [1, 50],
)
def test_configuration_accepts_item_limit_boundaries(
    max_items_per_run: int,
) -> None:
    configuration = FeedConfiguration.model_validate(
        {
            "version": 1,
            "defaults": {
                "max_items_per_run": max_items_per_run,
            },
            "sources": [make_source()],
        }
    )

    assert configuration.defaults.max_items_per_run == max_items_per_run


@pytest.mark.parametrize(
    "request_timeout_seconds",
    [1, 60],
)
def test_configuration_accepts_timeout_boundaries(
    request_timeout_seconds: int,
) -> None:
    configuration = FeedConfiguration.model_validate(
        {
            "version": 1,
            "defaults": {
                "request_timeout_seconds": request_timeout_seconds,
            },
            "sources": [make_source()],
        }
    )

    assert configuration.defaults.request_timeout_seconds == request_timeout_seconds


def test_configuration_rejects_normalized_duplicate_keys() -> None:
    with pytest.raises(ValidationError):
        FeedConfiguration.model_validate(
            {
                "version": 1,
                "sources": [
                    make_source(),
                    make_source(key=" EXAMPLE-NEWS "),
                ],
            }
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"url": "http://example.com/feed.xml"},
        {"allowed_host": "other.example.com"},
        {"priority": "5.001"},
        {"enabled": "false"},
        {"max_items_per_run": 51},
        {"request_timeout_seconds": 0},
        {"request_timeout_seconds": 61},
        {"unexpected": True},
    ],
)
def test_configuration_rejects_invalid_source(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        FeedConfiguration.model_validate(
            {
                "version": 1,
                "sources": [make_source(**overrides)],
            }
        )


@pytest.mark.parametrize(
    "defaults",
    [
        {"max_items_per_run": 0},
        {"max_items_per_run": 51},
        {"request_timeout_seconds": 0},
        {"request_timeout_seconds": 61},
    ],
)
def test_configuration_rejects_invalid_defaults(
    defaults: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        FeedConfiguration.model_validate(
            {
                "version": 1,
                "defaults": defaults,
                "sources": [make_source()],
            }
        )


def test_loader_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FeedConfigurationError):
        load_feed_configuration(tmp_path / "missing.yml")


def test_loader_hides_invalid_configuration_contents(
    tmp_path: Path,
) -> None:
    path = tmp_path / "feeds.yml"
    path.write_text("private-marker: [", encoding="utf-8")

    with pytest.raises(FeedConfigurationError) as captured:
        load_feed_configuration(path)

    assert "private-marker" not in str(captured.value)


def test_loader_reads_yaml(tmp_path: Path) -> None:
    path = tmp_path / "feeds.yml"
    path.write_text(
        """
version: 1
sources:
  - key: example-news
    name: Example News
    url: https://example.com/feed.xml
    allowed_host: example.com
    category: artificial_intelligence
""",
        encoding="utf-8",
    )

    configuration = load_feed_configuration(path)

    assert configuration.sources[0].key == "example-news"


def test_feed_configuration_components_have_docstrings() -> None:
    assert FeedConfigurationError.__doc__
    assert FeedConfiguration.__doc__
    assert FeedConfiguration.validate_sources.__doc__
    assert load_feed_configuration.__doc__
