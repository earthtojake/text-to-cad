"""The frames every process of the engine's speaks to the process that started it: a JSON object on
one line and, when the object says ``bytes``, exactly that many bytes after the line. A worker
answers the daemon in them (``worker``), and a render process both reads its requests and answers
in them (``render.service``). The standard library alone.

``read`` skips a line that is no JSON object (one that does not start with ``{``) before a frame,
so a banner a child prints where its frames go does not end the conversation.
"""

from __future__ import annotations

import json
from typing import Any

__all__ = ["exactly", "read", "write"]


def read(stream: Any) -> tuple[dict[str, Any], bytes] | None:
    """The next frame on ``stream`` (a binary stream): its object and the bytes it says follow
    (``b""`` when it says none); None at the end of the stream. ``EOFError`` when the stream ends
    inside a frame; a line that starts with ``{`` and is no JSON is ``json``'s ``ValueError``."""
    while True:
        line = stream.readline()
        if not line:
            return None
        line = line.strip()
        if line.startswith(b"{"):
            break
    message = json.loads(line)
    size = int(message.get("bytes") or 0)
    return message, exactly(stream, size) if size else b""


def exactly(stream: Any, size: int) -> bytes:
    """``size`` bytes read from ``stream``, however many reads that takes; ``EOFError`` when it
    ends first."""
    chunks = []
    while size:
        chunk = stream.read(size)
        if not chunk:
            raise EOFError("the stream ended inside a frame")
        chunks.append(chunk)
        size -= len(chunk)
    return b"".join(chunks)


def write(stream: Any, message: dict[str, Any], payload: bytes = b"") -> None:
    """``message`` on one line of ``stream``, saying ``bytes`` and followed by ``payload`` when
    there is one, then flushed. The caller makes a frame whole where two threads write."""
    if payload:
        message = {**message, "bytes": len(payload)}
    stream.write(json.dumps(message, separators=(",", ":")).encode() + b"\n")
    if payload:
        stream.write(payload)
    stream.flush()
