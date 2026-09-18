from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from re import fullmatch
from uuid import UUID, uuid4

from app.domain.enum_validation import ensure_enum_member
from app.domain.enums import IgnoreReason, NewsItemStatus
from app.domain.feed_policy import ensure_feed_url
from app.domain.state_machine import ensure_news_item_transition
from app.domain.validators import (
    ensure_https_url,
    ensure_non_negative_int,
    ensure_sha256,
    ensure_utc_datetime,
    normalize_bounded_string,
    normalize_hostname,
    utc_now,
)
from app.texts.domain import (
    NEWS_IGNORE_REASON_FORBIDDEN,
    NEWS_IGNORE_REASON_REQUIRED,
    NEWS_SUMMARY_REQUIRED,
    NEWS_TITLE_REQUIRED,
    NEWS_TITLE_TOO_LONG,
    SOURCE_FIELD_IMMUTABLE,
    SOURCE_HEADER_INVALID,
    SOURCE_KEY_INVALID,
    SOURCE_LANGUAGE_INVALID,
    SOURCE_PRIORITY_INVALID,
)


@dataclass(slots=True, kw_only=True)
class Source:
    """Store feed configuration and conditional-request metadata.

    The source key, feed URL, and allowed hostname cannot be reassigned.
    Category text is limited to 64 characters after trimming.
    Fetch methods validate input before updating request metadata.
    """

    key: str
    name: str
    feed_url: str
    allowed_host: str
    category: str
    language: str = "en"
    enabled: bool = True
    priority: Decimal = Decimal("5.00")
    id: UUID = field(default_factory=uuid4)
    etag: str | None = None
    last_modified: str | None = None
    last_checked_at: datetime | None = None
    last_success_at: datetime | None = None
    consecutive_failures: int = 0
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __setattr__(self, field_name: str, value: object) -> None:
        """Prevent reassignment of source identity and allowlist fields."""
        if field_name in {"key", "feed_url", "allowed_host"} and hasattr(
            self,
            field_name,
        ):
            raise AttributeError(SOURCE_FIELD_IMMUTABLE.format(field_name=field_name))

        object.__setattr__(self, field_name, value)

    def __post_init__(self) -> None:
        """Normalize configuration and validate the source contract."""
        key = normalize_bounded_string(
            self.key,
            "key",
            maximum=64,
        ).lower()

        if fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", key) is None:
            raise ValueError(SOURCE_KEY_INVALID)

        allowed_host = normalize_hostname(self.allowed_host, "allowed_host")
        ensure_feed_url(
            self.feed_url,
            allowed_host=allowed_host,
        )
        name = normalize_bounded_string(
            self.name,
            "Source name",
            maximum=160,
        )
        category = normalize_bounded_string(
            self.category,
            "Source category",
            maximum=64,
        )
        language = self.language.strip().lower()

        if len(language) != 2 or not language.isascii() or not language.isalpha():
            raise ValueError(SOURCE_LANGUAGE_INVALID)

        if not self.priority.is_finite() or not Decimal("0") <= self.priority <= Decimal("10"):
            raise ValueError(SOURCE_PRIORITY_INVALID)

        ensure_non_negative_int(
            self.consecutive_failures,
            "consecutive_failures",
        )
        ensure_utc_datetime(self.created_at, "created_at")
        ensure_utc_datetime(self.updated_at, "updated_at")

        if self.last_checked_at is not None:
            ensure_utc_datetime(self.last_checked_at, "last_checked_at")

        if self.last_success_at is not None:
            ensure_utc_datetime(self.last_success_at, "last_success_at")

        etag = self._validate_header(self.etag, "etag")
        last_modified = self._validate_header(
            self.last_modified,
            "last_modified",
        )

        # Normalize protected fields once during construction.
        object.__setattr__(self, "key", key)
        object.__setattr__(self, "allowed_host", allowed_host)
        self.name = name
        self.category = category
        self.language = language
        self.etag = etag
        self.last_modified = last_modified

    def record_fetch_success(
        self,
        *,
        checked_at: datetime,
        etag: str | None,
        last_modified: str | None,
    ) -> None:
        """Record a successful fetch and reset consecutive failures.

        Raises:
            ValueError: If the timestamp or response headers are invalid.
                Rejected input leaves the source unchanged.
        """
        ensure_utc_datetime(checked_at, "checked_at")
        validated_etag = self._validate_header(etag, "etag")
        validated_last_modified = self._validate_header(
            last_modified,
            "last_modified",
        )

        self.last_checked_at = checked_at
        self.last_success_at = checked_at
        self.etag = validated_etag
        self.last_modified = validated_last_modified
        self.consecutive_failures = 0
        self.updated_at = checked_at

    def record_fetch_failure(self, *, checked_at: datetime) -> None:
        """Record a failed fetch while preserving successful response metadata.

        Raises:
            ValueError: If the timestamp or failure count is invalid.
                Rejected input leaves the source unchanged.
        """
        ensure_utc_datetime(checked_at, "checked_at")
        failures = ensure_non_negative_int(
            self.consecutive_failures,
            "consecutive_failures",
        )

        self.last_checked_at = checked_at
        self.consecutive_failures = failures + 1
        self.updated_at = checked_at

    @staticmethod
    def _validate_header(value: str | None, field_name: str) -> str | None:
        """Reject control characters before storing conditional headers."""
        if value is None:
            return None

        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError(SOURCE_HEADER_INVALID.format(field_name=field_name))

        return value


@dataclass(slots=True, kw_only=True)
class NewsItem:
    """Store a collected article and its processing state.

    Collection stores lowercase URL and content hashes for deduplication.
    Only ignored items may contain an ignore reason.
    """

    source_id: UUID
    original_url: str
    canonical_url: str
    url_hash: str
    title: str
    normalized_title: str
    sanitized_summary: str
    content_hash: str
    id: UUID = field(default_factory=uuid4)
    external_id: str | None = None
    raw_summary: str | None = field(default=None, repr=False)
    author: str | None = None
    published_at: datetime | None = None
    collected_at: datetime = field(default_factory=utc_now)
    status: NewsItemStatus = NewsItemStatus.COLLECTED
    ignore_reason: IgnoreReason | None = None

    def __post_init__(self) -> None:
        """Validate article data and normalize stored text."""
        ensure_enum_member(self.status, NewsItemStatus, "status")
        ensure_https_url(self.original_url, "original_url")
        ensure_https_url(self.canonical_url, "canonical_url")
        ensure_sha256(self.url_hash, "url_hash")
        ensure_sha256(self.content_hash, "content_hash")
        ensure_utc_datetime(self.collected_at, "collected_at")

        if self.published_at is not None:
            ensure_utc_datetime(self.published_at, "published_at")

        title = self.title.strip()

        if not title:
            raise ValueError(NEWS_TITLE_REQUIRED)

        if len(title) > 500:
            raise ValueError(NEWS_TITLE_TOO_LONG)

        normalized_title = normalize_bounded_string(
            self.normalized_title,
            "normalized_title",
            maximum=500,
        )
        sanitized_summary = self.sanitized_summary.strip()

        if not sanitized_summary:
            raise ValueError(NEWS_SUMMARY_REQUIRED)

        self._validate_ignore_reason(self.status, self.ignore_reason)

        self.title = title
        self.normalized_title = normalized_title
        self.sanitized_summary = sanitized_summary

    def transition_to(
        self,
        target_status: NewsItemStatus,
        *,
        ignore_reason: IgnoreReason | None = None,
    ) -> None:
        """Apply an allowed transition with a consistent ignore reason.

        Raises:
            TypeError: If a status or ignore reason has the wrong enum type.
            ValueError: If the ignore reason conflicts with the target status.
            InvalidStateTransitionError: If the transition is forbidden.
                Rejected input leaves the news item unchanged.
        """
        ensure_enum_member(self.status, NewsItemStatus, "status")
        self._validate_ignore_reason(target_status, ignore_reason)
        ensure_news_item_transition(self.status, target_status)

        self.status = target_status
        self.ignore_reason = ignore_reason

    @staticmethod
    def _validate_ignore_reason(
        status: NewsItemStatus,
        ignore_reason: IgnoreReason | None,
    ) -> None:
        """Require a typed ignore reason only when the item is ignored."""
        ensure_enum_member(status, NewsItemStatus, "status")

        if ignore_reason is not None:
            ensure_enum_member(ignore_reason, IgnoreReason, "ignore_reason")

        if status is NewsItemStatus.IGNORED:
            if ignore_reason is None:
                raise ValueError(NEWS_IGNORE_REASON_REQUIRED)
        elif ignore_reason is not None:
            raise ValueError(NEWS_IGNORE_REASON_FORBIDDEN)
