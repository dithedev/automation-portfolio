"""Application settings validation messages."""

TIMEZONE_UNKNOWN = "Unknown IANA timezone: {timezone}"
OPENAI_MODEL_INVALID = "OPENAI_MODEL must be gpt-4o-mini for this project."

DATABASE_URL_INVALID = (
    "DATABASE_URL must be a valid postgresql+asyncpg DSN "
    "with a hostname, database name, username, and password."
)
CREDENTIAL_REQUIRED = "{field_name} must not be empty for this configuration."
PRODUCTION_PLACEHOLDER_FORBIDDEN = "{field_name} contains an unsafe placeholder for production."
PRODUCTION_ADMIN_KEY_TOO_SHORT = "ADMIN_API_KEY must contain at least 32 characters in production."

DIGEST_LIMITS_INVALID = (
    "Digest limits must satisfy MIN_DIGEST_ITEMS <= DIGEST_TOP_ARTICLES <= MAX_DIGEST_ITEMS."
)
LLM_CANDIDATE_LIMIT_INVALID = "MAX_LLM_CANDIDATES must not be less than MAX_DIGEST_ITEMS."
