from datetime import UTC, datetime
from ipaddress import ip_address
from urllib.parse import urlsplit

from app.domain.enums import ErrorCode
from app.texts.domain import (
    BOUNDED_STRING_REQUIRED,
    BOUNDED_STRING_TOO_LONG,
    BOUNDED_STRING_TOO_SHORT,
    DATETIME_TIMEZONE_REQUIRED,
    ERROR_CODE_REQUIRED,
    ERROR_CODE_TOO_LONG,
    ERROR_CODE_UNSUPPORTED,
    ERROR_SUMMARY_TOO_LONG,
    HOSTNAME_INVALID,
    HOSTNAME_REQUIRED,
    HOSTNAME_TOO_LONG,
    HTTP_STATUS_OUT_OF_RANGE,
    HTTPS_REQUIRED,
    NON_NEGATIVE_INTEGER_REQUIRED,
    SHA256_REQUIRED,
    UNSAFE_IP_HOST_FORBIDDEN,
    URL_CREDENTIALS_FORBIDDEN,
    URL_HOSTNAME_MISMATCH,
    URL_HOSTNAME_REQUIRED,
)
from app.texts.validation import INTEGER_REQUIRED, URL_PORT_INVALID


def utc_now() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(UTC)


def ensure_utc_datetime(value: datetime, field_name: str) -> None:
    """Require a datetime containing usable timezone information.

    Raises:
        ValueError: If the supplied datetime is naive.
    """
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(DATETIME_TIMEZONE_REQUIRED.format(field_name=field_name))


def normalize_hostname(value: str, field_name: str) -> str:
    """Normalize a hostname and reject unsafe literal IP addresses.

    The result is lowercase and has no trailing dot. DNS resolution and
    redirect checks belong to the feed client.

    Raises:
        ValueError: If the hostname is empty, malformed, too long, or unsafe.
    """
    normalized = value.strip().lower().rstrip(".")

    if not normalized:
        raise ValueError(HOSTNAME_REQUIRED.format(field_name=field_name))

    if len(normalized) > 253:
        raise ValueError(HOSTNAME_TOO_LONG.format(field_name=field_name))

    # IPv6 contains colons, so literal IPs must be checked before DNS labels.
    try:
        literal_ip = ip_address(normalized)
    except ValueError:
        literal_ip = None

    if literal_ip is not None:
        if (
            literal_ip.is_private
            or literal_ip.is_loopback
            or literal_ip.is_link_local
            or literal_ip.is_multicast
            or literal_ip.is_unspecified
            or literal_ip.is_reserved
        ):
            raise ValueError(UNSAFE_IP_HOST_FORBIDDEN.format(field_name=field_name))

        return literal_ip.compressed

    if (
        normalized.startswith(".")
        or ".." in normalized
        or any(
            not label
            or len(label) > 63
            or label.startswith("-")
            or label.endswith("-")
            or not all(
                character.isascii() and (character.isalnum() or character == "-")
                for character in label
            )
            for label in normalized.split(".")
        )
    ):
        raise ValueError(HOSTNAME_INVALID.format(field_name=field_name))

    return normalized


def ensure_https_url(
    value: str,
    field_name: str,
    *,
    expected_hostname: str | None = None,
) -> None:
    """Validate HTTPS transport, credentials, hostname, and optional port.

    An expected hostname enforces exact allowlist matching. Runtime DNS
    resolution and redirect validation remain the feed client's responsibility.

    Raises:
        ValueError: If the URL violates transport or host restrictions.
    """
    try:
        parsed_url = urlsplit(value)
        hostname = parsed_url.hostname
        username = parsed_url.username
        password = parsed_url.password
    except ValueError as error:
        raise ValueError(URL_HOSTNAME_REQUIRED.format(field_name=field_name)) from error

    if parsed_url.scheme.lower() != "https":
        raise ValueError(HTTPS_REQUIRED.format(field_name=field_name))

    if not hostname:
        raise ValueError(URL_HOSTNAME_REQUIRED.format(field_name=field_name))

    if username is not None or password is not None:
        raise ValueError(URL_CREDENTIALS_FORBIDDEN.format(field_name=field_name))

    # urlsplit() defers invalid-port errors until the port property is accessed.
    try:
        port = parsed_url.port
    except ValueError as error:
        raise ValueError(URL_PORT_INVALID.format(field_name=field_name)) from error

    if port == 0 or (port is None and parsed_url.netloc.endswith(":")):
        raise ValueError(URL_PORT_INVALID.format(field_name=field_name))

    normalized_hostname = normalize_hostname(hostname, field_name)

    if expected_hostname is None:
        return

    normalized_expected_hostname = normalize_hostname(
        expected_hostname,
        "allowed_host",
    )

    if normalized_hostname != normalized_expected_hostname:
        raise ValueError(
            URL_HOSTNAME_MISMATCH.format(
                field_name=field_name,
                allowed_host=normalized_expected_hostname,
            )
        )


def ensure_sha256(value: str, field_name: str) -> None:
    """Require exactly 64 lowercase hexadecimal characters.

    Digests are validated without trimming or changing their case.

    Raises:
        ValueError: If the value violates the stored SHA-256 format.
    """
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(SHA256_REQUIRED.format(field_name=field_name))


def normalize_bounded_string(
    value: str,
    field_name: str,
    *,
    minimum: int = 1,
    maximum: int,
) -> str:
    """Trim a string and enforce inclusive length boundaries.

    Raises:
        ValueError: If the normalized value falls outside the boundaries.
    """
    normalized = value.strip()

    if not normalized:
        raise ValueError(BOUNDED_STRING_REQUIRED.format(field_name=field_name))

    if len(normalized) < minimum:
        raise ValueError(
            BOUNDED_STRING_TOO_SHORT.format(
                field_name=field_name,
                minimum=minimum,
            )
        )

    if len(normalized) > maximum:
        raise ValueError(
            BOUNDED_STRING_TOO_LONG.format(
                field_name=field_name,
                maximum=maximum,
            )
        )

    return normalized


def ensure_non_negative_int(value: int, field_name: str) -> int:
    """Require a non-negative integer and reject boolean values.

    Raises:
        TypeError: If the supplied value is not an integer.
        ValueError: If the supplied integer is negative.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(INTEGER_REQUIRED.format(field_name=field_name))

    if value < 0:
        raise ValueError(NON_NEGATIVE_INTEGER_REQUIRED.format(field_name=field_name))

    return value


def ensure_http_status(
    value: int,
    field_name: str = "http_status",
) -> int:
    """Require an HTTP status code from 100 through 599.

    Raises:
        TypeError: If the supplied value is not an integer.
        ValueError: If the supplied value is outside the HTTP status range.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(INTEGER_REQUIRED.format(field_name=field_name))

    if not 100 <= value <= 599:
        raise ValueError(HTTP_STATUS_OUT_OF_RANGE.format(field_name=field_name))

    return value


def normalize_error_code(value: ErrorCode | str) -> ErrorCode:
    """Convert an enum or known external string into an ErrorCode.

    Raises:
        ValueError: If the value is empty, too long, or unsupported.
    """
    raw_value = value.value if isinstance(value, ErrorCode) else value.strip()

    if not raw_value:
        raise ValueError(ERROR_CODE_REQUIRED)

    if len(raw_value) > 64:
        raise ValueError(ERROR_CODE_TOO_LONG)

    try:
        return ErrorCode(raw_value)
    except ValueError as error:
        raise ValueError(ERROR_CODE_UNSUPPORTED.format(error_code=raw_value)) from error


def normalize_error_summary(value: str | None) -> str | None:
    """Trim a sanitized error summary and normalize blanks to None.

    The caller must remove secrets before passing a summary to this helper.

    Raises:
        ValueError: If the normalized summary exceeds 500 characters.
    """
    if value is None:
        return None

    normalized = value.strip()

    if not normalized:
        return None

    if len(normalized) > 500:
        raise ValueError(ERROR_SUMMARY_TOO_LONG)

    return normalized
