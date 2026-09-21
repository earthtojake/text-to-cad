"""Orderly retirement of a test-owned daemon, never the ambient endpoint."""

from __future__ import annotations

import os
import sys


def retire_owned_daemon(address: str) -> None:
    from cadgen.daemon import client

    if not address or os.environ.get("CADGEN_DAEMON_SOCKET") != address:
        raise ValueError("daemon cleanup requires the explicit test-owned address")
    try:
        channel = client._connect(address)
    except OSError:
        return  # This test never started its default daemon, or already stopped it.
    try:
        # Version retirement is the daemon's existing orderly shutdown path:
        # close its listener, drain work, and shut down its worker pool. Unlike
        # SIGTERM on Windows it also releases the workers. Never retry/spawn.
        if not client._send_json(channel, {"token": "test-owned-daemon-retirement"}):
            raise RuntimeError("could not request test daemon retirement")
        result = client._recv_json(channel, 10.0)
        if result != {"restart": True}:
            raise RuntimeError(f"unexpected test daemon retirement response: {result!r}")
    finally:
        channel.close()


if __name__ == "__main__":
    retire_owned_daemon(sys.argv[1])
