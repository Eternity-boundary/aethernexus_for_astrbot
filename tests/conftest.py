"""Offline tests with network access blocked and isolated AstrBot data.

SPDX-License-Identifier: GPL-3.0-only
"""

import os
import socket
import sys
import tempfile
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_DIR.parent))
sys.path.insert(0, str(PLUGIN_DIR.parents[2]))
# Set this before importing AstrBot; never read the desktop app's real data.
os.environ["ASTRBOT_ROOT"] = tempfile.mkdtemp(prefix="aethernexus-tests-")


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch):
    """Fail any accidental non-loopback connection during contract tests.

    Args:
        monkeypatch: Pytest patch fixture.
    """
    original = socket.socket.connect

    def connect(sock, address):
        """Allow event-loop sockets while blocking external network access.

        Args:
            sock: Socket being connected.
            address: Socket destination.

        Returns:
            The original connection result for loopback only.
        """
        if isinstance(address, tuple) and address[0] not in (
            "127.0.0.1",
            "::1",
            "localhost",
        ):
            raise AssertionError("External network access is forbidden in tests.")
        return original(sock, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_ADMIN_KEY", raising=False)
