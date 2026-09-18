"""Database connection, diagnostic, and repository messages."""

DATABASE_CONFIGURATION_INVALID = "Database configuration is invalid."
DATABASE_CHECK_FAILED = "Database check failed. Verify PostgreSQL availability and DATABASE_URL."
DATABASE_CHECK_SUCCEEDED = "Database connection and session checks passed."
DATABASE_PROBE_INVALID = "Database probe returned an unexpected result."

SOURCE_NOT_FOUND = "Source does not exist."
SOURCE_IDENTITY_MISMATCH = "Stored source identity cannot be changed."

RUN_NOT_FOUND = "Pipeline run does not exist."
RUN_IDENTITY_MISMATCH = "Stored pipeline run identity cannot be changed."
RUN_TERMINAL_UPDATE_FORBIDDEN = "Completed pipeline run cannot be changed."

NEWS_NOT_FOUND = "News item does not exist."
NEWS_DUPLICATE_CONFLICT = "News deduplication keys do not identify one stored item."
NEWS_ID_CONFLICT = "News item ID belongs to a different article."

DIGEST_NOT_FOUND = "Digest does not exist."
DIGEST_GENERATED_REQUIRED = "Only a newly generated digest can be created."
DIGEST_NEWS_MISSING = "One or more selected news items do not exist."
DIGEST_CANDIDATES_REQUIRED = "All selected news items must have candidate status."

ATTEMPT_NOT_FOUND = "Delivery attempt does not exist."
ATTEMPT_IDENTITY_MISMATCH = "Stored delivery attempt identity cannot be changed."
ATTEMPT_TERMINAL_UPDATE_FORBIDDEN = "Completed delivery attempt cannot be changed."
