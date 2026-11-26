"""Outbound AI connection safety, including DNS-rebinding resistance."""
from __future__ import annotations

import socket
import ipaddress

import httpcore
import pytest

from app.services.ai_transport import (
    SafeAITransport,
    _CheckedNetworkBackend,
    resolve_checked_addresses,
)


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

def test_checked_backend_pins_tcp_to_numeric_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    expected_stream = object()

    monkeypatch.setattr(
        "app.services.ai_transport.resolve_checked_addresses",
        lambda host, port: [ipaddress.ip_address("93.184.216.34")],
    )

    def fake_connect_tcp(
        self,
        host,
        port,
        timeout=None,
        local_address=None,
        socket_options=None,
    ):
        captured.update(
            host=host,
            port=port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )
        return expected_stream

    monkeypatch.setattr(httpcore.SyncBackend, "connect_tcp", fake_connect_tcp)
    backend = _CheckedNetworkBackend()
    result = backend.connect_tcp(
        "provider.example",
        443,
        timeout=2.5,
        local_address="0.0.0.0",
        socket_options=[(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)],
    )

    assert result is expected_stream
    assert captured["host"] == "93.184.216.34"
    assert captured["host"] != "provider.example"
    assert captured["port"] == 443
    assert captured["timeout"] == 2.5
    assert captured["local_address"] == "0.0.0.0"
    assert captured["socket_options"] == [(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)]


def test_checked_backend_fails_before_opening_socket_on_unsafe_dns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempted_socket = False

    def reject_resolution(host: str, port: int):
        raise httpcore.ConnectError("resolved to a non-public address")

    def fake_connect_tcp(self, host, port, **kwargs):
        nonlocal attempted_socket
        attempted_socket = True
        raise AssertionError("socket must not be opened for an unsafe address")

    monkeypatch.setattr(
        "app.services.ai_transport.resolve_checked_addresses",
        reject_resolution,
    )
    monkeypatch.setattr(httpcore.SyncBackend, "connect_tcp", fake_connect_tcp)

    with pytest.raises(httpcore.ConnectError, match="non-public address"):
        _CheckedNetworkBackend().connect_tcp("provider.example", 443)

    assert attempted_socket is False


def test_safe_http_transport_installs_checked_backend_and_disables_proxies() -> None:
    transport = SafeAITransport()
    try:
        assert isinstance(transport._pool._network_backend, _CheckedNetworkBackend)
        assert transport._pool._proxy is None
    finally:
        transport.close()
