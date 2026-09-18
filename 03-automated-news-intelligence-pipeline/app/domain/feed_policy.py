"""URL and literal IP restrictions for configured RSS feeds."""

from ipaddress import IPv6Address, ip_address
from urllib.parse import urlsplit

from app.domain.validators import ensure_https_url, normalize_hostname
from app.texts.feeds import (
    FEED_IP_INVALID,
    FEED_IP_NOT_PUBLIC,
    FEED_LOCALHOST_FORBIDDEN,
    FEED_PORT_FORBIDDEN,
)


def ensure_public_ip(value: str) -> None:
    """Require a public unicast IP address without performing DNS resolution.

    IPv4-mapped IPv6 addresses are checked against their embedded IPv4 address.
    Scoped IPv6 addresses are rejected to avoid interface-dependent routing.

    Raises:
        ValueError: If the address is malformed or not public unicast.
    """
    try:
        address = ip_address(value)
    except ValueError as error:
        raise ValueError(FEED_IP_INVALID) from error

    if isinstance(address, IPv6Address):
        if address.scope_id is not None:
            raise ValueError(FEED_IP_NOT_PUBLIC)

        mapped_address = address.ipv4_mapped

        if mapped_address is not None:
            address = mapped_address

    if (
        not address.is_global
        or address.is_multicast
        or address.is_reserved
        or address.is_loopback
        or address.is_link_local
        or address.is_unspecified
    ):
        raise ValueError(FEED_IP_NOT_PUBLIC)


def ensure_feed_url(value: str, *, allowed_host: str) -> None:
    """Require an allowlisted HTTPS feed URL using port 443.

    Literal IP addresses must be public unicast. Hostnames are not resolved
    here: the HTTP client must validate every DNS result and redirect before
    connecting, and prevent reconnection through an unchecked DNS lookup.

    Raises:
        ValueError: If the URL violates the feed network policy.
    """
    ensure_https_url(
        value,
        "feed_url",
        expected_hostname=allowed_host,
    )
    parsed = urlsplit(value)

    if parsed.port not in (None, 443):
        raise ValueError(FEED_PORT_FORBIDDEN)

    hostname = normalize_hostname(parsed.hostname or "", "feed_url")

    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValueError(FEED_LOCALHOST_FORBIDDEN)

    try:
        ip_address(hostname)
    except ValueError:
        return

    ensure_public_ip(hostname)
