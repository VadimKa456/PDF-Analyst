"""Outbound AI connection safety, including DNS-rebinding resistance."""
from __future__ import annotations

import socket

import httpcore
import pytest

from app.services.ai_transport import resolve_checked_addresses


def _dns_record(ip: str, port: int = 443):
    address = (ip, port)
    if ":" in ip:
        address = (ip, port, 0, 0)
        family = socket.AF_INET6
    else:
        family = socket.AF_INET
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", address)


def test_public_host_resolving_to_private_address_is_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.ai_transport.socket.getaddrinfo",
        lambda host, port, type: [_dns_record("127.0.0.1", port)],
    )

    with pytest.raises(httpcore.ConnectError, match="non-public address"):
        resolve_checked_addresses("provider.example", 443)


def test_all_dns_answers_must_be_public(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.ai_transport.socket.getaddrinfo",
        lambda host, port, type: [
            _dns_record("93.184.216.34", port),
            _dns_record("10.0.0.8", port),
        ],
    )

    with pytest.raises(httpcore.ConnectError, match="non-public address"):
        resolve_checked_addresses("provider.example", 443)


def test_localhost_may_resolve_only_to_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.ai_transport.socket.getaddrinfo",
        lambda host, port, type: [
            _dns_record("127.0.0.1", port),
            _dns_record("::1", port),
        ],
    )

    resolved = resolve_checked_addresses("localhost", 11434)

    assert {str(address) for address in resolved} == {"127.0.0.1", "::1"}


def test_localhost_mapped_to_non_loopback_is_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.ai_transport.socket.getaddrinfo",
        lambda host, port, type: [_dns_record("93.184.216.34", port)],
    )

    with pytest.raises(httpcore.ConnectError, match="non-public address"):
        resolve_checked_addresses("localhost", 11434)


def test_global_dns_address_is_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.ai_transport.socket.getaddrinfo",
        lambda host, port, type: [_dns_record("93.184.216.34", port)],
    )

    resolved = resolve_checked_addresses("provider.example", 443)

    assert [str(address) for address in resolved] == ["93.184.216.34"]


def test_dns_failure_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_resolution(host, port, type):
        raise socket.gaierror("temporary resolver failure")

    monkeypatch.setattr(
        "app.services.ai_transport.socket.getaddrinfo",
        fail_resolution,
    )

    with pytest.raises(httpcore.ConnectError, match="Unable to resolve"):
        resolve_checked_addresses("provider.example", 443)
