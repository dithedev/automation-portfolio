"""Domain validation messages."""

DATETIME_TIMEZONE_REQUIRED = "{field_name} must be timezone-aware"

HTTPS_REQUIRED = "{field_name} must use HTTPS"
URL_HOSTNAME_REQUIRED = "{field_name} must contain a hostname"
URL_CREDENTIALS_FORBIDDEN = "{field_name} must not contain URL credentials"
URL_HOSTNAME_MISMATCH = "{field_name} hostname must exactly match allowed host {allowed_host!r}"
UNSAFE_IP_HOST_FORBIDDEN = (
    "{field_name} must not use a private, loopback, link-local, multicast, "
    "unspecified, or reserved IP address"
)

HOSTNAME_REQUIRED = "{field_name} must not be empty"
HOSTNAME_TOO_LONG = "{field_name} must not exceed 253 characters"
HOSTNAME_INVALID = "{field_name} must contain a valid hostname"

SHA256_REQUIRED = "{field_name} must be a 64-character SHA-256 hex digest"

BOUNDED_STRING_REQUIRED = "{field_name} must not be empty"
BOUNDED_STRING_TOO_SHORT = "{field_name} must contain at least {minimum} characters"
BOUNDED_STRING_TOO_LONG = "{field_name} must not exceed {maximum} characters"

NON_NEGATIVE_INTEGER_REQUIRED = "{field_name} must not be negative"
HTTP_STATUS_OUT_OF_RANGE = "{field_name} must be between 100 and 599"

ERROR_CODE_REQUIRED = "error_code must not be empty"
ERROR_CODE_TOO_LONG = "error_code must not exceed 64 characters"
ERROR_CODE_UNSUPPORTED = "Unsupported error_code: {error_code!r}"
ERROR_SUMMARY_TOO_LONG = "error_summary must not exceed 500 characters"

INVALID_STATE_TRANSITION = (
    "Invalid {entity} state transition: {current_status!r} -> {target_status!r}"
)

SOURCE_KEY_INVALID = (
    "Source key must contain lowercase ASCII letters or digits separated by single hyphens"
)
SOURCE_FIELD_IMMUTABLE = "{field_name} cannot be changed after initialization"
SOURCE_LANGUAGE_INVALID = "Source language must be a two-letter ASCII code"
SOURCE_PRIORITY_INVALID = "Source priority must be between 0 and 10"
SOURCE_HEADER_INVALID = "{field_name} must not contain control characters"

NEWS_TITLE_REQUIRED = "News item title must not be empty"
NEWS_TITLE_TOO_LONG = "News item title must not exceed 500 characters"
NEWS_SUMMARY_REQUIRED = "sanitized_summary must not be empty"
NEWS_IGNORE_REASON_REQUIRED = "ignore_reason is required when ignoring a news item"
NEWS_IGNORE_REASON_FORBIDDEN = "ignore_reason is only allowed for ignored news items"
