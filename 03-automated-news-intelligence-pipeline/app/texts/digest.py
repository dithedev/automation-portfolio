"""Digest validation messages."""

ITEM_POSITION_INVALID = "Digest item position must be between 1 and 7"
ITEM_RELEVANCE_INVALID = "relevance_score must be between 0 and 1"
DIGEST_TAG_INVALID = "Digest item tag is not in the allowed tag set"

DIGEST_MODEL_INVALID = "Digest model must be gpt-4o-mini"
DIGEST_ITEMS_INVALID = "Digest must contain between 1 and 7 items"
DIGEST_POSITIONS_DUPLICATE = "Digest item positions must be unique"
DIGEST_NEWS_DUPLICATE = "Digest news items must be unique"
DIGEST_POSITIONS_INVALID = "Digest item positions must be consecutive starting at 1"

DIGEST_TEXT_REQUIRED = "rendered_text must not be empty"
DIGEST_TIME_BEFORE_CREATION = "{field_name} must not be before created_at"
DIGEST_SENT_TIME_REQUIRED = "Sent digest must have sent_at"
DIGEST_SENT_TIME_FORBIDDEN = "Only sent digest may have sent_at"
DIGEST_ERROR_REQUIRED = "Failed digest requires error_code"
DIGEST_ERROR_FORBIDDEN = "Only failed digest may contain error information"
