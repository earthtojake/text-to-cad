"""Warm-process daemon for the CAD build CLIs — ON BY DEFAULT everywhere.

Holds OCP, build123d and the parser modules resident so repeated builds skip the import
cost. Every front door — the ``cadgen`` CLI and the skill script shims —
routes warm unless ``CADGEN_DAEMON=0`` opts out. The daemon sets ``CADGEN_DAEMON_CHILD`` in the process
it serves from so a tool invoked through it cannot recurse back into the client.
"""

from __future__ import annotations


def main(argv: list[str] | None = None) -> int:
    """Start the daemon without importing its server during package discovery."""
    from cadgen.daemon.server import main as server_main

    return server_main(argv)

__all__ = ["main"]
