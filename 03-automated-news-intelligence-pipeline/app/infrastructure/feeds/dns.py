"""Resolve trusted feed hosts and reject unsafe network destinations."""

import asyncio
import socket
from ipaddress import ip_address

from app.domain.feed_policy import ensure_public_ip
from app.domain.validators import normalize_hostname
from app.texts.feeds import (
    FEED_DNS_RESOLUTION_FAILED,
    FEED_DNS_RESULT_EMPTY,
)


class FeedDNSResolutionError(RuntimeError):
    """Report DNS failures without exposing provider-specific details."""


async def resolve_public_addresses(hostname: str) -> tuple[str, ...]:
    """Resolve a hostname and return all unique public IP addresses.

    Literal IP addresses are validated directly without a DNS lookup. Every
    address returned for a hostname must satisfy the feed network policy.

    Raises:
        ValueError: If the hostname or any resolved address is unsafe.
        FeedDNSResolutionError: If DNS fails or returns no usable addresses.
    """
    normalized_hostname = normalize_hostname(hostname, "hostname")

    try:
        literal_address = ip_address(normalized_hostname)
    except ValueError:
        literal_address = None

    if literal_address is not None:
        normalized_address = str(literal_address)
        ensure_public_ip(normalized_address)
        return (normalized_address,)

    try:
        address_info = await asyncio.to_thread(
            socket.getaddrinfo,
            normalized_hostname,
            443,
            socket.AF_UNSPEC,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
        )
    except OSError:
        raise FeedDNSResolutionError(FEED_DNS_RESOLUTION_FAILED) from None

    addresses = {str(ip_address(result[4][0])) for result in address_info if result[4]}

    if not addresses:
        raise FeedDNSResolutionError(FEED_DNS_RESULT_EMPTY)

    for address in addresses:
        ensure_public_ip(address)

    return tuple(
        sorted(
            addresses,
            key=lambda value: (
                ip_address(value).version,
                ip_address(value).packed,
            ),
        )
    )
