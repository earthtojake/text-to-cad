"""Bounded, read-only file and port parsing for diagnostic inventories."""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

MAX_BYTES = 1024 * 1024


def read_bytes(path: Path) -> tuple[bytes | None, str]:
    """Only regular files: opening a stale FIFO must never block doctor."""
    try:
        handle = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
        try:
            info = os.fstat(handle)
            if not stat.S_ISREG(info.st_mode):
                return None, "invalid"
            if info.st_size > MAX_BYTES:
                return None, "too_large"
            with os.fdopen(handle, "rb", closefd=False) as stream:
                data = stream.read(MAX_BYTES + 1)
        finally:
            os.close(handle)
        return (None, "too_large") if len(data) > MAX_BYTES else (data, "ok")
    except FileNotFoundError:
        return None, "missing"
    except OSError:
        return None, "unreadable"


def read(path: Path, *, toml: bool = False) -> tuple[dict | None, str]:
    """Read a bounded structured file; errors carry no source text or exception message."""
    data, status = read_bytes(path)
    if data is None:
        return None, status
    try:
        if toml:
            import tomllib

            result = tomllib.loads(data.decode("utf-8"))
        else:
            result = json.loads(data)
        return (result, "ok") if isinstance(result, dict) else (None, "invalid")
    except (ValueError, UnicodeError, RecursionError):
        return None, "invalid"


def _port(value) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        result = int(value)
        return result if str(result) == str(value).strip() and 1 <= result <= 65535 else None
    except (ValueError, TypeError):
        return None


