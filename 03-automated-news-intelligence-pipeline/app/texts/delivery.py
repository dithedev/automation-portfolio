"""Delivery attempt validation messages."""

DELIVERY_POSITIVE_INTEGER_REQUIRED = "{field_name} must be at least 1"
DELIVERY_COMPLETION_BEFORE_START = "finished_at must not be before started_at"
DELIVERY_PENDING_REQUIRED = "Only pending delivery attempt may be completed"
DELIVERY_PENDING_RESULT_FORBIDDEN = "Pending delivery attempt must not have result data"
DELIVERY_COMPLETION_REQUIRED = "Completed delivery attempt must have finished_at"
DELIVERY_MESSAGE_ID_REQUIRED = "Sent delivery attempt must have telegram_message_id"
DELIVERY_SUCCESS_HTTP_REQUIRED = (
    "Sent delivery attempt must have an HTTP status between 200 and 299"
)
DELIVERY_SENT_ERROR_FORBIDDEN = "Sent delivery attempt must not contain error or retry information"
DELIVERY_FAILED_ERROR_REQUIRED = "Failed delivery attempt requires error_code"
DELIVERY_FAILED_MESSAGE_ID_FORBIDDEN = "Failed delivery attempt must not have telegram_message_id"
