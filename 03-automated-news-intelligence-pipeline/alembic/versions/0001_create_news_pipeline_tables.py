"""Create news pipeline tables

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision."""
    op.create_table(
        "feed_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("feed_url", sa.Text(), nullable=False),
        sa.Column("allowed_host", sa.String(length=253), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=16), server_default=sa.text("'en'"), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "priority",
            sa.Numeric(precision=4, scale=2),
            server_default=sa.text("5.00"),
            nullable=False,
        ),
        sa.Column("etag", sa.Text(), nullable=True),
        sa.Column("last_modified", sa.Text(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "consecutive_failures", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "consecutive_failures >= 0",
            name=op.f("ck_feed_sources_consecutive_failures_non_negative"),
        ),
        sa.CheckConstraint(
            "priority >= 0 AND priority <= 10", name=op.f("ck_feed_sources_priority_range")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feed_sources")),
        sa.UniqueConstraint("key", name=op.f("uq_feed_sources_key")),
    )
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "trigger_type",
            sa.Enum(
                "scheduled",
                "manual",
                "dry_run",
                name="pipeline_trigger_type",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "running",
                "success",
                "partial_success",
                "no_content",
                "failed",
                "skipped_locked",
                name="pipeline_run_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default=sa.text("'running'"),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("feeds_total", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("feeds_succeeded", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("items_fetched", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("items_inserted", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("items_duplicate", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("candidates_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("selected_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "error_code",
            sa.Enum(
                "FEED_TIMEOUT",
                "FEED_CONNECTION_FAILED",
                "UNSAFE_FEED_URL",
                "FEED_RESPONSE_TOO_LARGE",
                "FEED_PARSE_FAILED",
                "OPENAI_TIMEOUT",
                "OPENAI_RATE_LIMITED",
                "INVALID_STRUCTURED_OUTPUT",
                "OUTPUT_POST_VALIDATION_FAILED",
                "TELEGRAM_TIMEOUT",
                "TELEGRAM_RATE_LIMITED",
                "TELEGRAM_PERMANENT_FAILURE",
                "UNEXPECTED_PIPELINE_FAILURE",
                name="pipeline_error_code",
                native_enum=False,
                create_constraint=True,
                length=64,
            ),
            nullable=True,
        ),
        sa.Column("error_summary", sa.String(length=500), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("app_version", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "(status = 'failed' AND error_code IS NOT NULL) OR (status <> 'failed' AND error_code IS NULL AND error_summary IS NULL)",
            name=op.f("ck_pipeline_runs_error_matches_status"),
        ),
        sa.CheckConstraint(
            "(status = 'running' AND finished_at IS NULL AND duration_ms IS NULL) OR (status <> 'running' AND finished_at IS NOT NULL AND duration_ms IS NOT NULL)",
            name=op.f("ck_pipeline_runs_completion_matches_status"),
        ),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name=op.f("ck_pipeline_runs_duration_non_negative"),
        ),
        sa.CheckConstraint(
            "feeds_succeeded <= feeds_total", name=op.f("ck_pipeline_runs_feed_counters_consistent")
        ),
        sa.CheckConstraint(
            "feeds_total >= 0 AND feeds_succeeded >= 0 AND items_fetched >= 0 AND items_inserted >= 0 AND items_duplicate >= 0 AND candidates_count >= 0 AND selected_count >= 0",
            name=op.f("ck_pipeline_runs_counters_non_negative"),
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name=op.f("ck_pipeline_runs_completion_time_valid"),
        ),
        sa.CheckConstraint(
            "items_inserted + items_duplicate <= items_fetched",
            name=op.f("ck_pipeline_runs_item_counters_consistent"),
        ),
        sa.CheckConstraint(
            "selected_count <= candidates_count",
            name=op.f("ck_pipeline_runs_selection_counters_consistent"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pipeline_runs")),
    )
    op.create_table(
        "digests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("digest_date", sa.Date(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "generated",
                "sending",
                "sent",
                "failed",
                name="digest_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default=sa.text("'generated'"),
            nullable=False,
        ),
        sa.Column("rendered_text", sa.Text(), nullable=False),
        sa.Column(
            "model", sa.String(length=100), server_default=sa.text("'gpt-4o-mini'"), nullable=False
        ),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("provider_response_id", sa.String(length=160), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "error_code",
            sa.Enum(
                "FEED_TIMEOUT",
                "FEED_CONNECTION_FAILED",
                "UNSAFE_FEED_URL",
                "FEED_RESPONSE_TOO_LARGE",
                "FEED_PARSE_FAILED",
                "OPENAI_TIMEOUT",
                "OPENAI_RATE_LIMITED",
                "INVALID_STRUCTURED_OUTPUT",
                "OUTPUT_POST_VALIDATION_FAILED",
                "TELEGRAM_TIMEOUT",
                "TELEGRAM_RATE_LIMITED",
                "TELEGRAM_PERMANENT_FAILURE",
                "UNEXPECTED_PIPELINE_FAILURE",
                name="digest_error_code",
                native_enum=False,
                create_constraint=True,
                length=64,
            ),
            nullable=True,
        ),
        sa.Column("error_summary", sa.String(length=500), nullable=True),
        sa.CheckConstraint(
            "(status = 'failed' AND error_code IS NOT NULL) OR (status <> 'failed' AND error_code IS NULL AND error_summary IS NULL)",
            name=op.f("ck_digests_error_matches_status"),
        ),
        sa.CheckConstraint(
            "(status = 'sent' AND sent_at IS NOT NULL) OR (status <> 'sent' AND sent_at IS NULL)",
            name=op.f("ck_digests_sent_time_matches_status"),
        ),
        sa.CheckConstraint("model = 'gpt-4o-mini'", name=op.f("ck_digests_model_valid")),
        sa.CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name=op.f("ck_digests_input_tokens_non_negative"),
        ),
        sa.CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name=op.f("ck_digests_output_tokens_non_negative"),
        ),
        sa.CheckConstraint(
            "sent_at IS NULL OR sent_at >= created_at", name=op.f("ck_digests_sent_time_valid")
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["pipeline_runs.id"],
            name=op.f("fk_digests_run_id_pipeline_runs"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_digests")),
        sa.UniqueConstraint("run_id", name=op.f("uq_digests_run_id")),
    )
    op.create_table(
        "feed_fetches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "not_modified",
                "success",
                "failed",
                name="feed_fetch_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("entries_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column(
            "error_code",
            sa.Enum(
                "FEED_TIMEOUT",
                "FEED_CONNECTION_FAILED",
                "UNSAFE_FEED_URL",
                "FEED_RESPONSE_TOO_LARGE",
                "FEED_PARSE_FAILED",
                "OPENAI_TIMEOUT",
                "OPENAI_RATE_LIMITED",
                "INVALID_STRUCTURED_OUTPUT",
                "OUTPUT_POST_VALIDATION_FAILED",
                "TELEGRAM_TIMEOUT",
                "TELEGRAM_RATE_LIMITED",
                "TELEGRAM_PERMANENT_FAILURE",
                "UNEXPECTED_PIPELINE_FAILURE",
                name="feed_fetch_error_code",
                native_enum=False,
                create_constraint=True,
                length=64,
            ),
            nullable=True,
        ),
        sa.Column("error_summary", sa.String(length=500), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(status = 'failed' AND error_code IS NOT NULL) OR (status <> 'failed' AND error_code IS NULL AND error_summary IS NULL)",
            name=op.f("ck_feed_fetches_error_matches_status"),
        ),
        sa.CheckConstraint(
            "status <> 'not_modified' OR (http_status IS NOT NULL AND http_status = 304 AND entries_count = 0)",
            name=op.f("ck_feed_fetches_not_modified_result_valid"),
        ),
        sa.CheckConstraint(
            "status <> 'success' OR (http_status IS NOT NULL AND http_status BETWEEN 200 AND 299)",
            name=op.f("ck_feed_fetches_success_http_valid"),
        ),
        sa.CheckConstraint("duration_ms >= 0", name=op.f("ck_feed_fetches_duration_non_negative")),
        sa.CheckConstraint("entries_count >= 0", name=op.f("ck_feed_fetches_entries_non_negative")),
        sa.CheckConstraint(
            "finished_at >= started_at", name=op.f("ck_feed_fetches_completion_time_valid")
        ),
        sa.CheckConstraint(
            "http_status IS NULL OR http_status BETWEEN 100 AND 599",
            name=op.f("ck_feed_fetches_http_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["pipeline_runs.id"],
            name=op.f("fk_feed_fetches_run_id_pipeline_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["feed_sources.id"],
            name=op.f("fk_feed_fetches_source_id_feed_sources"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feed_fetches")),
        sa.UniqueConstraint("run_id", "source_id", name=op.f("uq_feed_fetches_run_id")),
    )
    op.create_index(op.f("ix_feed_fetches_source_id"), "feed_fetches", ["source_id"], unique=False)
    op.create_table(
        "news_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("original_url", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("url_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("normalized_title", sa.String(length=500), nullable=False),
        sa.Column("raw_summary", sa.Text(), nullable=True),
        sa.Column("sanitized_summary", sa.Text(), nullable=False),
        sa.Column("author", sa.String(length=255), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "collected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("content_hash", sa.CHAR(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "collected",
                "candidate",
                "used",
                "ignored",
                name="news_item_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default=sa.text("'collected'"),
            nullable=False,
        ),
        sa.Column(
            "ignore_reason",
            sa.Enum(
                "too_old",
                "missing_title",
                "missing_content",
                "invalid_url",
                "irrelevant",
                "duplicate_content",
                name="news_item_ignore_reason",
                native_enum=False,
                create_constraint=True,
                length=64,
            ),
            nullable=True,
        ),
        sa.CheckConstraint(
            "(status = 'ignored' AND ignore_reason IS NOT NULL) OR (status <> 'ignored' AND ignore_reason IS NULL)",
            name=op.f("ck_news_items_ignore_reason_matches_status"),
        ),
        sa.CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'", name=op.f("ck_news_items_content_hash_valid")
        ),
        sa.CheckConstraint(
            "url_hash ~ '^[0-9a-f]{64}$'", name=op.f("ck_news_items_url_hash_valid")
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["feed_sources.id"],
            name=op.f("fk_news_items_source_id_feed_sources"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_news_items")),
        sa.UniqueConstraint("url_hash", name=op.f("uq_news_items_url_hash")),
    )
    op.create_index(
        "ix_news_items_source_collected_at",
        "news_items",
        ["source_id", sa.literal_column("collected_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_news_items_status_published_at",
        "news_items",
        ["status", sa.literal_column("published_at DESC")],
        unique=False,
    )
    op.create_index(
        "uq_news_items_source_external_id",
        "news_items",
        ["source_id", "external_id"],
        unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )
    op.create_table(
        "delivery_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("digest_id", sa.Uuid(), nullable=False),
        sa.Column("part_number", sa.SmallInteger(), nullable=False),
        sa.Column("attempt_number", sa.SmallInteger(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "sent",
                "failed",
                name="delivery_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("retry_after_seconds", sa.Integer(), nullable=True),
        sa.Column(
            "error_code",
            sa.Enum(
                "FEED_TIMEOUT",
                "FEED_CONNECTION_FAILED",
                "UNSAFE_FEED_URL",
                "FEED_RESPONSE_TOO_LARGE",
                "FEED_PARSE_FAILED",
                "OPENAI_TIMEOUT",
                "OPENAI_RATE_LIMITED",
                "INVALID_STRUCTURED_OUTPUT",
                "OUTPUT_POST_VALIDATION_FAILED",
                "TELEGRAM_TIMEOUT",
                "TELEGRAM_RATE_LIMITED",
                "TELEGRAM_PERMANENT_FAILURE",
                "UNEXPECTED_PIPELINE_FAILURE",
                name="delivery_error_code",
                native_enum=False,
                create_constraint=True,
                length=64,
            ),
            nullable=True,
        ),
        sa.Column("error_summary", sa.String(length=500), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(status = 'pending' AND finished_at IS NULL AND telegram_message_id IS NULL AND http_status IS NULL AND retry_after_seconds IS NULL AND error_code IS NULL AND error_summary IS NULL) OR (status = 'sent' AND finished_at IS NOT NULL AND telegram_message_id IS NOT NULL AND http_status IS NOT NULL AND http_status BETWEEN 200 AND 299 AND retry_after_seconds IS NULL AND error_code IS NULL AND error_summary IS NULL) OR (status = 'failed' AND finished_at IS NOT NULL AND telegram_message_id IS NULL AND error_code IS NOT NULL)",
            name=op.f("ck_delivery_attempts_result_matches_status"),
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name=op.f("ck_delivery_attempts_completion_time_valid"),
        ),
        sa.CheckConstraint(
            "http_status IS NULL OR http_status BETWEEN 100 AND 599",
            name=op.f("ck_delivery_attempts_http_status_valid"),
        ),
        sa.CheckConstraint(
            "part_number >= 1 AND attempt_number >= 1",
            name=op.f("ck_delivery_attempts_numbering_positive"),
        ),
        sa.CheckConstraint(
            "retry_after_seconds IS NULL OR retry_after_seconds >= 0",
            name=op.f("ck_delivery_attempts_retry_after_non_negative"),
        ),
        sa.CheckConstraint(
            "telegram_message_id IS NULL OR telegram_message_id > 0",
            name=op.f("ck_delivery_attempts_message_id_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["digest_id"],
            ["digests.id"],
            name=op.f("fk_delivery_attempts_digest_id_digests"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_delivery_attempts")),
        sa.UniqueConstraint(
            "digest_id",
            "part_number",
            "attempt_number",
            name=op.f("uq_delivery_attempts_digest_id"),
        ),
    )
    op.create_table(
        "digest_items",
        sa.Column("digest_id", sa.Uuid(), nullable=False),
        sa.Column("news_item_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("summary", sa.String(length=400), nullable=False),
        sa.Column("tag", sa.String(length=32), nullable=False),
        sa.Column("relevance_score", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("selection_reason", sa.String(length=300), nullable=False),
        sa.CheckConstraint("position BETWEEN 1 AND 7", name=op.f("ck_digest_items_position_valid")),
        sa.CheckConstraint(
            "relevance_score >= 0 AND relevance_score <= 1",
            name=op.f("ck_digest_items_relevance_score_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["digest_id"],
            ["digests.id"],
            name=op.f("fk_digest_items_digest_id_digests"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["news_item_id"],
            ["news_items.id"],
            name=op.f("fk_digest_items_news_item_id_news_items"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("digest_id", "news_item_id", name=op.f("pk_digest_items")),
        sa.UniqueConstraint("digest_id", "position", name=op.f("uq_digest_items_digest_id")),
    )
    op.create_index(
        op.f("ix_digest_items_news_item_id"), "digest_items", ["news_item_id"], unique=False
    )


def downgrade() -> None:
    """Revert this revision."""
    op.drop_index(op.f("ix_digest_items_news_item_id"), table_name="digest_items")
    op.drop_table("digest_items")
    op.drop_table("delivery_attempts")
    op.drop_index(
        "uq_news_items_source_external_id",
        table_name="news_items",
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )
    op.drop_index("ix_news_items_status_published_at", table_name="news_items")
    op.drop_index("ix_news_items_source_collected_at", table_name="news_items")
    op.drop_table("news_items")
    op.drop_index(op.f("ix_feed_fetches_source_id"), table_name="feed_fetches")
    op.drop_table("feed_fetches")
    op.drop_table("digests")
    op.drop_table("pipeline_runs")
    op.drop_table("feed_sources")
