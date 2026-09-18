"""Load the thematic selection profile without network access."""

from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.texts.feeds import TOPIC_PROFILE_INVALID, TOPIC_PROFILE_UNREADABLE


class TopicProfileError(ValueError):
    """Report an unreadable or invalid topic profile."""


class TopicProfile(BaseModel):
    """Keywords and length floors used by deterministic pre-filtering."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    name: str = Field(min_length=1, max_length=160)
    include_keywords: tuple[str, ...] = Field(min_length=1)
    exclude_keywords: tuple[str, ...] = Field(default_factory=tuple)
    min_title_length: int = Field(default=12, ge=1, le=500, strict=True)
    min_summary_length: int = Field(default=40, ge=1, le=12_000, strict=True)

    @model_validator(mode="after")
    def normalize_keywords(self) -> Self:
        include = tuple(
            keyword.strip().lower() for keyword in self.include_keywords if keyword.strip()
        )
        exclude = tuple(
            keyword.strip().lower() for keyword in self.exclude_keywords if keyword.strip()
        )

        if not include:
            raise ValueError(TOPIC_PROFILE_INVALID)

        return self.model_copy(
            update={
                "name": self.name.strip(),
                "include_keywords": include,
                "exclude_keywords": exclude,
            }
        )


def load_topic_profile(path: Path) -> TopicProfile:
    """Read and validate the topic profile YAML file."""
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise TopicProfileError(TOPIC_PROFILE_UNREADABLE) from None

    try:
        data = yaml.safe_load(content)
        return TopicProfile.model_validate(data)
    except (yaml.YAMLError, ValidationError, ValueError):
        raise TopicProfileError(TOPIC_PROFILE_INVALID) from None
