"""HTTP transport that pins AI endpoint connections to validated DNS answers.

AI provider hostnames remain configurable, but every TCP connection resolves
the hostname immediately before connecting and pins the socket to one of the
validated IP literals. This prevents a public hostname from being rebound to
loopback, private, link-local, or other non-global addresses between validation
and connection. Environment proxies are disabled so credentials are not routed
through an inherited proxy unexpectedly.
"""
from __future__ import annotations

import ipaddress
import socket

import httpcore
import httpx


_MAX_DNS_ADDRESSES = 16


def resolve_checked_addresses(host: str, port: int) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Resolve a host and reject the entire answer set if any address is unsafe."""
    normalized_host = host.rstrip(".").lower()
    try:
        literal = ipaddress.ip_address(normalized_host)
    except ValueError:
        literal = None

    allow_loopback = normalized_host == "localhost" or bool(
        literal is not None and literal.is_loopback
    )

    try:
        records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise httpcore.ConnectError(f"Unable to resolve AI endpoint host {host!r}: {exc}") from exc

    if not records:
        raise httpcore.ConnectError(f"AI endpoint host {host!r} resolved to no addresses.")
    if len(records) > _MAX_DNS_ADDRESSES:
        raise httpcore.ConnectError(
            f"AI endpoint host {host!r} returned too many DNS addresses."
        )

    checked: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    seen: set[str] = set()
    for record in records:
        try:
            address_text = str(record[4][0]).split("%", 1)[0]
            address = ipaddress.ip_address(address_text)
        except (IndexError, TypeError, ValueError) as exc:
            raise httpcore.ConnectError(
                f"AI endpoint host {host!r} returned an invalid address."
            ) from exc

        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped

        permitted = address.is_loopback if allow_loopback else address.is_global
        if not permitted:
            raise httpcore.ConnectError(
                f"AI endpoint host {host!r} resolved to a non-public address; "
                "the connection was blocked."
            )

        key = str(address)
        if key not in seen:
            seen.add(key)
            checked.append(address)

    return checked


class _CheckedNetworkBackend(httpcore.SyncBackend):
    """Resolve, validate, then connect to the exact validated numeric address."""

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options=None,
    ):
        addresses = resolve_checked_addresses(host, port)
        last_error: Exception | None = None
        for address in addresses:
            try:
                # Passing a numeric literal to the base backend pins the TCP
                # destination. TLS SNI and certificate validation still use
                # the original URL hostname maintained by httpcore.
                return super().connect_tcp(
                    str(address),
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        if last_error is not None:
            raise last_error
        raise httpcore.ConnectError(f"AI endpoint host {host!r} has no usable addresses.")


class SafeAITransport(httpx.HTTPTransport):
    """HTTPX transport with DNS-rebinding protection and no environment proxy."""

    def __init__(self) -> None:
        super().__init__(trust_env=False, retries=0)
        # httpx currently exposes no public network_backend argument. Keep the
        # compatibility check explicit so a future httpcore change fails closed.
        pool = getattr(self, "_pool", None)
        if pool is None or not hasattr(pool, "_network_backend"):
            raise RuntimeError(
                "Unsupported httpx/httpcore transport internals; refusing an unpinned AI connection."
            )
        pool._network_backend = _CheckedNetworkBackend()
