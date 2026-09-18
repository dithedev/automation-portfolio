"""Load trusted feed configuration without making network requests."""

from decimal import Decimal
from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.domain import Source
from app.texts.feeds import (
    FEEDS_CONFIG_INVALID,
    FEEDS_CONFIG_UNREADABLE,
    FEEDS_KEYS_DUPLICATE,
)

MAX_ITEMS_PER_RUN = 50
MAX_REQUEST_TIMEOUT_SECONDS = 60


class FeedConfigurationError(ValueError):
    """Report invalid feed configuration without exposing its contents."""


class FeedDefaults(BaseModel):
    """Define defaults shared by configured sources."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True, strict=True)
    max_items_per_run: int = Field(
        default=20,
        ge=1,
        le=MAX_ITEMS_PER_RUN,
        strict=True,
    )
    request_timeout_seconds: int = Field(
        default=15,
        ge=1,
        le=MAX_REQUEST_TIMEOUT_SECONDS,
        strict=True,
    )


class FeedSourceConfig(BaseModel):
    """Describe source settings and optional per-source overrides."""

    model_config = ConfigDict(extra="forbid")

    key: str
    name: str
    url: str
    allowed_host: str
    category: str
    language: str = "en"
    enabled: bool | None = Field(default=None, strict=True)
    priority: Decimal = Field(
        default=Decimal("5.00"),
        ge=Decimal("0"),
        le=Decimal("10"),
        max_digits=4,
        decimal_places=2,
        allow_inf_nan=False,
    )
    max_items_per_run: int | None = Field(
        default=None,
        ge=1,
        le=MAX_ITEMS_PER_RUN,
        strict=True,
    )
    request_timeout_seconds: int | None = Field(
        default=None,
        ge=1,
        le=MAX_REQUEST_TIMEOUT_SECONDS,
        strict=True,
    )

    def to_source(self, defaults: FeedDefaults) -> Source:
        """Build a domain source using shared defaults and domain validation."""
        return Source(
            key=self.key,
            name=self.name,
            feed_url=self.url,
            allowed_host=self.allowed_host,
            category=self.category,
            language=self.language,
            enabled=defaults.enabled if self.enabled is None else self.enabled,
            priority=self.priority,
        )

    def effective_max_items(self, defaults: FeedDefaults) -> int:
        """Return the source limit or its validated shared default."""
        if self.max_items_per_run is not None:
            return self.max_items_per_run

        return defaults.max_items_per_run

    def effective_timeout_seconds(self, defaults: FeedDefaults) -> int:
        """Return the source timeout or its validated shared default."""
        if self.request_timeout_seconds is not None:
            return self.request_timeout_seconds

        return defaults.request_timeout_seconds


class FeedConfiguration(BaseModel):
    """Validate a versioned source list before database synchronization."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    defaults: FeedDefaults = Field(default_factory=FeedDefaults)
    sources: tuple[FeedSourceConfig, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_sources(self) -> Self:
        """Validate source contracts and reject normalized duplicate keys."""
        keys: set[str] = set()

        for configured in self.sources:
            source = configured.to_source(self.defaults)

            if source.key in keys:
                raise ValueError(FEEDS_KEYS_DUPLICATE)

            keys.add(source.key)

        return self


def load_feed_configuration(path: Path) -> FeedConfiguration:
    """Read YAML and validate all sources before returning configuration.

    Raises:
        FeedConfigurationError: If the file cannot be read or validation fails.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise FeedConfigurationError(FEEDS_CONFIG_UNREADABLE) from None

    try:
        data = yaml.safe_load(content)
        return FeedConfiguration.model_validate(data)
    except (yaml.YAMLError, ValidationError):
        raise FeedConfigurationError(FEEDS_CONFIG_INVALID) from None
