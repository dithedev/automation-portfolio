from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AliasChoices,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.texts.config import (
    CREDENTIAL_REQUIRED,
    DATABASE_URL_INVALID,
    DIGEST_LIMITS_INVALID,
    LLM_CANDIDATE_LIMIT_INVALID,
    OPENAI_MODEL_INVALID,
    PRODUCTION_ADMIN_KEY_TOO_SHORT,
    PRODUCTION_PLACEHOLDER_FORBIDDEN,
    TIMEZONE_UNKNOWN,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Load and validate application configuration for live and demo modes."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        hide_input_in_errors=True,
    )

    # Application
    app_name: str = Field(
        default="Automated News Intelligence Pipeline",
        alias="APP_NAME",
    )
    app_env: Literal["development", "test", "production"] = Field(
        default="development",
        alias="APP_ENV",
    )
    app_mode: Literal["live", "demo"] = Field(alias="APP_MODE")
    app_host: str = Field(default="127.0.0.1", alias="APP_HOST")
    app_port: int = Field(default=8000, ge=1, le=65535, alias="APP_PORT")
    app_log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        validation_alias=AliasChoices("LOG_LEVEL", "APP_LOG_LEVEL"),
    )
    app_timezone: str = Field(
        default="Europe/Vilnius",
        validation_alias=AliasChoices("SCHEDULER_TIMEZONE", "APP_TIMEZONE"),
    )

    # PostgreSQL
    postgres_db: str = Field(default="news_pipeline", alias="POSTGRES_DB")
    postgres_user: str = Field(default="news_pipeline", alias="POSTGRES_USER")
    postgres_password: SecretStr | None = Field(
        default=None,
        alias="POSTGRES_PASSWORD",
    )
    database_url: SecretStr = Field(alias="DATABASE_URL")

    # OpenAI
    openai_api_key: SecretStr | None = Field(
        default=None,
        alias="OPENAI_API_KEY",
    )
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    openai_timeout_seconds: float = Field(
        default=30,
        gt=0,
        le=120,
        alias="OPENAI_TIMEOUT_SECONDS",
    )
    openai_max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        alias="OPENAI_MAX_RETRIES",
    )
    openai_max_output_tokens: int = Field(
        default=2000,
        ge=100,
        le=16_384,
        alias="OPENAI_MAX_OUTPUT_TOKENS",
    )

    # Telegram
    telegram_bot_token: SecretStr | None = Field(
        default=None,
        alias="TELEGRAM_BOT_TOKEN",
    )
    telegram_chat_id: str | None = Field(
        default=None,
        alias="TELEGRAM_CHAT_ID",
        repr=False,
    )
    telegram_enabled: bool = Field(default=False, alias="TELEGRAM_ENABLED")
    telegram_max_retries: int = Field(
        default=3,
        ge=1,
        le=10,
        alias="TELEGRAM_MAX_RETRIES",
    )
    telegram_timeout_seconds: float = Field(
        default=30,
        gt=0,
        le=120,
        alias="TELEGRAM_TIMEOUT_SECONDS",
    )

    # News collection
    feeds_config_path: Path = Field(
        default=Path("config/feeds.yaml"),
        alias="FEEDS_CONFIG_PATH",
    )
    topic_profile_path: Path = Field(
        default=Path("config/topic_profile.yaml"),
        alias="TOPIC_PROFILE_PATH",
    )
    feed_failure_warning_threshold: int = Field(
        default=3,
        ge=1,
        le=100,
        alias="FEED_FAILURE_WARNING_THRESHOLD",
    )
    max_articles_per_source: int = Field(
        default=20,
        ge=1,
        le=50,
        alias="MAX_ARTICLES_PER_SOURCE",
    )
    max_new_items_per_run: int = Field(
        default=100,
        ge=1,
        le=100,
        alias="MAX_NEW_ITEMS_PER_RUN",
    )
    article_max_length: int = Field(
        default=12_000,
        ge=1_000,
        le=100_000,
        alias="ARTICLE_MAX_LENGTH",
    )
    feed_response_max_bytes: int = Field(
        default=2_097_152,
        ge=1024,
        le=16_777_216,
        alias="FEED_RESPONSE_MAX_BYTES",
    )
    feed_fetch_concurrency: int = Field(
        default=3,
        ge=1,
        le=20,
        alias="FEED_FETCH_CONCURRENCY",
    )
    max_item_age_hours: int = Field(
        default=72,
        ge=1,
        le=720,
        alias="MAX_ITEM_AGE_HOURS",
    )
    http_connect_timeout_seconds: float = Field(
        default=5,
        gt=0,
        le=60,
        alias="HTTP_CONNECT_TIMEOUT_SECONDS",
    )
    http_timeout_seconds: float = Field(
        default=15,
        gt=0,
        le=60,
        alias="HTTP_TIMEOUT_SECONDS",
    )
    http_write_timeout_seconds: float = Field(
        default=5,
        gt=0,
        le=60,
        alias="HTTP_WRITE_TIMEOUT_SECONDS",
    )
    http_pool_timeout_seconds: float = Field(
        default=5,
        gt=0,
        le=60,
        alias="HTTP_POOL_TIMEOUT_SECONDS",
    )
    http_max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        alias="HTTP_MAX_RETRIES",
    )
    user_agent: str = Field(
        default=(
            "AutomatedNewsIntelligencePipeline/0.1 "
            "(https://github.com/dithedev/automation-portfolio)"
        ),
        min_length=10,
        max_length=200,
        alias="USER_AGENT",
    )

    # Digest generation
    min_digest_items: int = Field(
        default=3,
        ge=3,
        le=7,
        alias="MIN_DIGEST_ITEMS",
    )
    max_digest_items: int = Field(
        default=7,
        ge=3,
        le=7,
        alias="MAX_DIGEST_ITEMS",
    )
    max_llm_candidates: int = Field(
        default=25,
        ge=3,
        le=25,
        alias="MAX_LLM_CANDIDATES",
    )
    digest_top_articles: int = Field(
        default=5,
        ge=3,
        le=7,
        alias="DIGEST_TOP_ARTICLES",
    )
    digest_language: Literal["en"] = Field(
        default="en",
        alias="DIGEST_LANGUAGE",
    )
    digest_schedule_hour: int = Field(
        default=8,
        ge=0,
        le=23,
        alias="DIGEST_SCHEDULE_HOUR",
    )
    digest_schedule_minute: int = Field(
        default=0,
        ge=0,
        le=59,
        alias="DIGEST_SCHEDULE_MINUTE",
    )
    scheduler_enabled: bool = Field(default=False, alias="SCHEDULER_ENABLED")
    scheduler_misfire_grace_seconds: int = Field(
        default=300,
        ge=0,
        le=86_400,
        alias="SCHEDULER_MISFIRE_GRACE_SECONDS",
    )

    # Security and operations
    admin_api_key: SecretStr | None = Field(
        default=None,
        alias="ADMIN_API_KEY",
    )
    manual_run_enabled: bool = Field(default=True, alias="MANUAL_RUN_ENABLED")
    expose_demo_endpoints: bool = Field(
        default=False,
        alias="EXPOSE_DEMO_ENDPOINTS",
    )
    log_pii: bool = Field(default=False, alias="LOG_PII")

    @field_validator("app_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        """Require a recognized IANA timezone identifier."""
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError(TIMEZONE_UNKNOWN.format(timezone=value)) from error

        return value

    @field_validator("feeds_config_path", "topic_profile_path")
    @classmethod
    def resolve_project_relative_path(cls, value: Path) -> Path:
        """Resolve relative configuration paths against the project root."""
        if value.is_absolute():
            return value

        return PROJECT_ROOT / value

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        """Require an async PostgreSQL DSN without exposing its credentials."""
        raw_value = value.get_secret_value()

        try:
            parsed = urlsplit(raw_value)
            port = parsed.port
            username = unquote(parsed.username or "")
            password = unquote(parsed.password or "")
            database_name = parsed.path.removeprefix("/")

            valid = (
                raw_value == raw_value.strip()
                and parsed.scheme == "postgresql+asyncpg"
                and bool(parsed.hostname)
                and bool(username.strip())
                and bool(password.strip())
                and bool(database_name.strip())
                and "/" not in database_name
                and not parsed.fragment
                and port != 0
                and not (port is None and parsed.netloc.endswith(":"))
            )
        except ValueError:
            valid = False

        if not valid:
            raise ValueError(DATABASE_URL_INVALID)

        return value

    @model_validator(mode="after")
    def validate_security_settings(self) -> "Settings":
        """Validate cross-field limits and credentials required by active mode.

        Demo mode does not require external provider credentials.
        Live mode requires OpenAI credentials and, when delivery is enabled,
        Telegram credentials. Production rejects credential placeholders.
        """
        if self.openai_model != "gpt-4o-mini":
            raise ValueError(OPENAI_MODEL_INVALID)

        if not (self.min_digest_items <= self.digest_top_articles <= self.max_digest_items):
            raise ValueError(DIGEST_LIMITS_INVALID)

        if self.max_llm_candidates < self.max_digest_items:
            raise ValueError(LLM_CANDIDATE_LIMIT_INVALID)

        if self.postgres_password is not None:
            self._validate_credential(
                self.postgres_password.get_secret_value(),
                "POSTGRES_PASSWORD",
            )

        parsed_database_url = urlsplit(self.database_url.get_secret_value())
        self._validate_credential(
            unquote(parsed_database_url.password or ""),
            "DATABASE_URL",
        )

        if self.app_mode == "live":
            self._validate_credential(
                self._secret_value(self.openai_api_key),
                "OPENAI_API_KEY",
            )

            if self.telegram_enabled:
                self._validate_credential(
                    self._secret_value(self.telegram_bot_token),
                    "TELEGRAM_BOT_TOKEN",
                )
                self._validate_credential(
                    self.telegram_chat_id or "",
                    "TELEGRAM_CHAT_ID",
                )

        admin_key_required = self.app_env == "production" or (
            self.app_mode == "live" and self.manual_run_enabled
        )

        if admin_key_required:
            admin_key = self._secret_value(self.admin_api_key)
            self._validate_credential(admin_key, "ADMIN_API_KEY")

            if self.app_env == "production" and len(admin_key.strip()) < 32:
                raise ValueError(PRODUCTION_ADMIN_KEY_TOO_SHORT)

        return self

    def _validate_credential(self, value: str, field_name: str) -> None:
        """Reject blank active credentials and production placeholders."""
        normalized = value.strip()

        if not normalized:
            raise ValueError(CREDENTIAL_REQUIRED.format(field_name=field_name))

        if self.app_env != "production":
            return

        lowered = normalized.lower()
        placeholder = (
            lowered in {"test", "example", "placeholder"}
            or "replace-with" in lowered
            or "change-me" in lowered
        )

        if placeholder:
            raise ValueError(
                PRODUCTION_PLACEHOLDER_FORBIDDEN.format(
                    field_name=field_name,
                )
            )

    @staticmethod
    def _secret_value(value: SecretStr | None) -> str:
        """Extract a configured secret or return an empty validation value."""
        return value.get_secret_value() if value is not None else ""


@lru_cache
def get_settings() -> Settings:
    """Return one cached settings instance per application process."""
    return Settings()
