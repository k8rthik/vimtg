"""The suite must never reach the real network.

pytest-socket (configured via ``--allow-hosts`` in pyproject) blocks
connections to anything but loopback, so a test that forgets to mock
Scryfall/EDHREC fails loudly instead of silently hitting the internet.
"""

from __future__ import annotations

import socket

import httpx
import pytest
from pytest_socket import SocketConnectBlockedError

# pytest-socket also emits a UserWarning for each blocked attempt; here the
# block is the point.
pytestmark = pytest.mark.filterwarnings("ignore:A test tried to use socket")


def test_raw_socket_to_public_host_is_blocked() -> None:
    # 192.0.2.0/24 is TEST-NET-1: never routable, so even if the guard were
    # off this could not touch a real service.
    with pytest.raises(SocketConnectBlockedError):
        socket.create_connection(("192.0.2.1", 443), timeout=1)


def test_httpx_request_to_public_host_is_blocked() -> None:
    with pytest.raises(SocketConnectBlockedError):
        httpx.get("https://192.0.2.1/bulk-data", timeout=1)


def test_loopback_stays_available() -> None:
    # asyncio's self-pipe (socketpair over loopback on Windows) and local test
    # servers must keep working.
    a, b = socket.socketpair()
    try:
        a.sendall(b"x")
        assert b.recv(1) == b"x"
    finally:
        a.close()
        b.close()
