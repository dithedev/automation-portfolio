"""DNS safety checks for trusted feed hosts."""

import socket

import pytest

from app.infrastructure.feeds.dns import (
    FeedDNSResolutionError,
    resolve_public_addresses,
)


def make_address_info(
    *addresses: str,
) -> list[
    tuple[
        socket.AddressFamily,
        socket.SocketKind,
        int,
        str,
        tuple[str, int] | tuple[str, int, int, int],
    ]
]:
    """Build getaddrinfo-compatible results for IPv4 and IPv6 addresses."""
    results: list[
        tuple[
            socket.AddressFamily,
            socket.SocketKind,
            int,
            str,
            tuple[str, int] | tuple[str, int, int, int],
        ]
    ] = []

    for address in addresses:
        if ":" in address:
            results.append(
                (
                    socket.AF_INET6,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    (address, 443, 0, 0),
                )
            )
        else:
            results.append(
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    (address, 443),
                )
            )

    return results


async def test_resolver_returns_unique_public_addresses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_getaddrinfo(
        host: str,
        port: int,
        family: int,
        type_: int,
        proto: int,
    ) -> list[
        tuple[
            socket.AddressFamily,
            socket.SocketKind,
            int,
            str,
            tuple[str, int] | tuple[str, int, int, int],
        ]
    ]:
        assert host == "example.com"
        assert port == 443
        assert family == socket.AF_UNSPEC
        assert type_ == socket.SOCK_STREAM
        assert proto == socket.IPPROTO_TCP

        return make_address_info(
            "2606:4700:4700::1111",
            "8.8.8.8",
            "8.8.8.8",
        )

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    addresses = await resolve_public_addresses("Example.COM.")

    assert addresses == (
        "8.8.8.8",
        "2606:4700:4700::1111",
    )


@pytest.mark.parametrize(
    "unsafe_address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.1.1",
        "100.64.0.1",
        "::1",
        "fc00::1",
        "fe80::1",
    ],
)
async def test_resolver_rejects_any_unsafe_address(
    monkeypatch: pytest.MonkeyPatch,
    unsafe_address: str,
) -> None:
    def fake_getaddrinfo(
        host: str,
        port: int,
        family: int,
        type_: int,
        proto: int,
    ) -> list[
        tuple[
            socket.AddressFamily,
            socket.SocketKind,
            int,
            str,
            tuple[str, int] | tuple[str, int, int, int],
        ]
    ]:
        return make_address_info("8.8.8.8", unsafe_address)

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    with pytest.raises(ValueError, match="public unicast"):
        await resolve_public_addresses("example.com")


async def test_resolver_rejects_empty_dns_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_getaddrinfo(
        host: str,
        port: int,
        family: int,
        type_: int,
        proto: int,
    ) -> list[
        tuple[
            socket.AddressFamily,
            socket.SocketKind,
            int,
            str,
            tuple[str, int] | tuple[str, int, int, int],
        ]
    ]:
        return []

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    with pytest.raises(
        FeedDNSResolutionError,
        match="did not resolve",
    ):
        await resolve_public_addresses("example.com")


async def test_resolver_hides_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_getaddrinfo(
        host: str,
        port: int,
        family: int,
        type_: int,
        proto: int,
    ) -> list[
        tuple[
            socket.AddressFamily,
            socket.SocketKind,
            int,
            str,
            tuple[str, int] | tuple[str, int, int, int],
        ]
    ]:
        raise socket.gaierror("provider details")

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    with pytest.raises(
        FeedDNSResolutionError,
        match="could not be resolved",
    ) as captured:
        await resolve_public_addresses("example.com")

    assert "provider details" not in str(captured.value)


async def test_literal_public_ip_skips_dns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_getaddrinfo(
        host: str,
        port: int,
        family: int,
        type_: int,
        proto: int,
    ) -> list[
        tuple[
            socket.AddressFamily,
            socket.SocketKind,
            int,
            str,
            tuple[str, int] | tuple[str, int, int, int],
        ]
    ]:
        raise AssertionError("DNS must not run for a literal IP address")

    monkeypatch.setattr(socket, "getaddrinfo", unexpected_getaddrinfo)

    assert await resolve_public_addresses("8.8.8.8") == ("8.8.8.8",)


async def test_literal_unsafe_ip_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_getaddrinfo(
        host: str,
        port: int,
        family: int,
        type_: int,
        proto: int,
    ) -> list[
        tuple[
            socket.AddressFamily,
            socket.SocketKind,
            int,
            str,
            tuple[str, int] | tuple[str, int, int, int],
        ]
    ]:
        raise AssertionError("DNS must not run for a literal IP address")

    monkeypatch.setattr(socket, "getaddrinfo", unexpected_getaddrinfo)

    with pytest.raises(ValueError, match="must not use"):
        await resolve_public_addresses("127.0.0.1")


def test_dns_components_have_docstrings() -> None:
    assert FeedDNSResolutionError.__doc__
    assert resolve_public_addresses.__doc__
