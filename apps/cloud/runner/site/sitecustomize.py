"""Flag a sandboxed job that reaches for the network: a signal, not a wall.

The runner puts this directory first on PYTHONPATH, so every Python process a job
starts (model scripts, their build workers, inspection scripts) imports it at start-up.
An audit hook marks the job when code connects a socket to, or resolves the name of,
anything but this machine. The sandbox has no network either way; the mark is what
lets the server tell people "this code tried to use the network". Code can remove an
audit hook's evidence, so nothing relies on it for safety.
"""

from __future__ import annotations

import os
import socket
import sys

_FLAG_DIR = os.environ.get("T2C_FLAG_DIR")
_LOCAL_NAMES = {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback", ""}


def _is_local_host(host: object) -> bool:
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    text = str(host).strip().lower().strip("[]")
    if text in _LOCAL_NAMES or text.endswith(".localhost"):
        return True
    if text.startswith("127.") or text in {"::1", "0.0.0.0", "::"}:
        return True
    return text.startswith("::ffff:127.")


def _mark(what: str) -> None:
    global _marked
    if _marked:
        return
    _marked = True
    try:
        os.makedirs(_FLAG_DIR, exist_ok=True)
        with open(os.path.join(_FLAG_DIR, "network"), "a", encoding="utf-8") as handle:
            handle.write(what[:200] + "\n")
    except OSError:
        pass


def _hook(event: str, args: tuple) -> None:
    try:
        if event == "socket.connect":
            sock, address = args[0], args[1]
            family = getattr(sock, "family", None)
            if family in (socket.AF_INET, socket.AF_INET6) and isinstance(address, tuple) and address:
                if not _is_local_host(address[0]):
                    _mark(f"connect {address[0]}")
        elif event == "socket.getaddrinfo":
            if args and not _is_local_host(args[0]):
                _mark(f"resolve {args[0]!r}")
    except Exception:  # noqa: BLE001 - an audit hook must never break the program it watches
        pass


_marked = False
if _FLAG_DIR:
    sys.addaudithook(_hook)
