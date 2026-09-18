"""Feed fetch, URL policy, configuration, synchronization, and DNS messages."""

FETCH_COMPLETION_BEFORE_START = "finished_at must not be before started_at"
FETCH_NOT_MODIFIED_HTTP_REQUIRED = "Not-modified feed fetch requires HTTP 304"
FETCH_NOT_MODIFIED_ENTRIES_FORBIDDEN = "Not-modified feed fetch must contain zero entries"
FETCH_SUCCESS_HTTP_REQUIRED = "Successful feed fetch requires an HTTP status between 200 and 299"
FETCH_ERROR_FORBIDDEN = "Only failed feed fetch may contain error information"
FETCH_ERROR_REQUIRED = "Failed feed fetch requires error_code"

FEED_PORT_FORBIDDEN = "Feed URL must use the default HTTPS port or explicit port 443"
FEED_LOCALHOST_FORBIDDEN = "Feed URL must not use localhost"
FEED_IP_INVALID = "Feed address must be a valid IP address"
FEED_IP_NOT_PUBLIC = "Feed address must be a public unicast IP address"

FEEDS_CONFIG_UNREADABLE = "Feed configuration could not be read."
FEEDS_CONFIG_INVALID = "Feed configuration does not satisfy the source contract."
FEEDS_KEYS_DUPLICATE = "Feed configuration contains duplicate source keys."
FEEDS_IDENTITY_MISMATCH = "Source URL or allowed hostname differs from the stored source identity."
FEEDS_SEED_FAILED = "Source synchronization failed. Verify configuration and database access."
FEEDS_SEED_SUCCEEDED = "Source synchronization completed: {count} sources."

FEED_DNS_RESOLUTION_FAILED = "Feed hostname could not be resolved."
FEED_DNS_RESULT_EMPTY = "Feed hostname did not resolve to an IP address."

URL_CANONICALIZE_FAILED = "URL could not be canonicalized."
URL_SCHEME_UNSUPPORTED = "Only HTTPS article URLs are accepted."

FEED_HTTP_TIMEOUT = "Feed request timed out."
FEED_HTTP_CONNECTION_FAILED = "Feed request could not be completed."
FEED_HTTP_UNSAFE = "Feed URL failed network safety checks."
FEED_HTTP_TOO_LARGE = "Feed response exceeded the configured size limit."
FEED_HTTP_STATUS_FAILED = "Feed request returned an unacceptable HTTP status."
FEED_HTTP_CONTENT_TYPE_FAILED = "Feed response content type is not allowed."
FEED_HTTP_RETRY_EXHAUSTED = "Feed request failed after retries."

FEED_PARSE_FAILED = "Feed content could not be parsed into usable entries."
FEED_ENTRY_SKIPPED = "Feed entry was skipped during normalization."

TOPIC_PROFILE_UNREADABLE = "Topic profile could not be read."
TOPIC_PROFILE_INVALID = "Topic profile does not satisfy the selection contract."
