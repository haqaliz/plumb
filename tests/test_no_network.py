"""The no-network mandate is enforced structurally, not by convention.

`ARCHITECTURE.md:144` requires no network in CI. `tests/conftest.py` installs an
autouse fixture that makes any socket attempt raise; these tests prove the blocker
actually fires, so a test that reaches the network fails the suite rather than
passing quietly.
"""

import socket

import pytest


def test_socket_construction_is_blocked() -> None:
    with pytest.raises(RuntimeError, match="network"):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)


def test_outbound_connection_is_blocked() -> None:
    # Numeric host, so nothing resolves before the socket is built.
    with pytest.raises(RuntimeError, match="network"):
        socket.create_connection(("127.0.0.1", 9), timeout=0.01)


def test_dns_resolution_is_blocked() -> None:
    # DNS is network access: blocking only `socket.socket` would let this reach the
    # real resolver and pass.
    with pytest.raises(RuntimeError, match="network"):
        socket.getaddrinfo("example.com", 80)


def test_hostname_lookup_is_blocked() -> None:
    with pytest.raises(RuntimeError, match="network"):
        socket.gethostbyname("example.com")


def test_reverse_lookup_is_blocked() -> None:
    # Reverse DNS is network access too.
    with pytest.raises(RuntimeError, match="network"):
        socket.gethostbyaddr("127.0.0.1")


def test_outbound_connection_is_blocked_before_it_resolves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`create_connection` must fail on its own, not merely via `socket.socket`.

    Blocking only the constructor lets `create_connection` resolve the hostname
    first, so the process still talks to the resolver before it fails. The spy
    replaces the blocked `getaddrinfo` for this test and must never be called.
    """
    resolved: list[object] = []
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: resolved.append(a))

    with pytest.raises(RuntimeError, match="network"):
        socket.create_connection(("example.com", 80), timeout=0.01)

    assert resolved == []
