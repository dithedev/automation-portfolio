"""CLI user-facing messages."""

CLI_MANUAL_RUN_DISABLED = "Manual runs are disabled (MANUAL_RUN_ENABLED=false)."
CLI_RUN_STARTED = "Pipeline run started."
CLI_RUN_SUMMARY = "status={status} run_id={run_id} digest_id={digest_id}"
CLI_DRY_RUN_PREFIX = "[dry-run]"
CLI_SKIPPED_LOCKED = "Another pipeline run holds the advisory lock; exiting."
CLI_NO_CONTENT = "Not enough candidates for a digest."
CLI_CONFIG_OK = "Configuration is valid."
CLI_CLEANUP_CONFIRM_REQUIRED = "Refusing destructive cleanup without --confirm."
CLI_CLEANUP_SUMMARY = (
    "feed_fetches={feed_fetches} delivery_attempts={delivery_attempts} dry_run={dry_run}"
)
CLI_SEED_SUCCEEDED = "Seeded {count} feed sources."
CLI_COMMAND_FAILED = "Command failed."
