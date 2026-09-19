"""Shared test fixtures.

The autouse network blocker below is the structural enforcement of the no-network
mandate (`ARCHITECTURE.md:144`). Plumb runs on the user's compute and nothing leaves
it (`CLAUDE.md` #2), so no test may reach the network — and that is enforced here
rather than left to reviewer discipline.

DNS resolution is network access, forward and reverse alike. Blocking only
`socket.socket` leaves a hole: a test that resolves a hostname reaches the real
resolver and passes, and `socket.create_connection` resolves before it ever builds a
socket. So the name lookups and the connection helper are blocked too, all raising
the same `NetworkAccessBlockedError` so the failure mode stays uniform.

**This is a same-process guard, not containment.** It patches names in this
interpreter; it is not a sandbox, and three things still get out:

- **`subprocess`.** Nothing here stops a test shelling out to `curl`. Real
  containment needs a network namespace or a CI-level firewall.
- **Import-time rebinding.** A module that does `from socket import create_connection`
  before this fixture runs keeps a reference to the real function, which the patch
  cannot reach.
- **Local-only calls are allowed on purpose.** `socket.socketpair` and Unix-domain
  sockets never leave the machine, so they are deliberately not blocked.

Treat a green suite as evidence that our own code did not *call* the network, not as
proof that nothing could have.
"""

import socket

import pytest

_BLOCKED_NAMES = (
    "socket",
    "create_connection",
    "getaddrinfo",
    "gethostbyname",
    "gethostbyaddr",
)


class NetworkAccessBlockedError(RuntimeError):
    """Raised when a test attempts to reach the network."""


def _blocked(name: str):
    def _raise(*args: object, **kwargs: object):
        raise NetworkAccessBlockedError(
            f"network access is blocked in tests; socket.{name}() may not be called "
            "(see ARCHITECTURE.md:144). If a test needs I/O, use a local fixture."
        )

    return _raise


@pytest.fixture(autouse=True)
def _block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every socket, name lookup, and connection attempt raise, per test."""
    for name in _BLOCKED_NAMES:
        monkeypatch.setattr(socket, name, _blocked(name))
