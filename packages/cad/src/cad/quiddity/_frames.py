"""The frames a part's features cross a pipe in, between the process that holds the kernel (``_process``) and the
recogniser's own (``_recogniser``): each eight bytes of length, big-endian, and that many bytes -- a part's STEP
one way, JSON the other."""

from __future__ import annotations

import json
import struct
from typing import Any, BinaryIO

__all__ = ["HEAD", "read", "send"]

#: A frame's head: its length, eight bytes, big-endian.
HEAD = struct.Struct(">Q")


def send(stream: BinaryIO, value: dict[str, Any]) -> None:
    """One frame: ``value`` as JSON."""
    data = json.dumps(value, separators=(",", ":")).encode("utf-8")
    stream.write(HEAD.pack(len(data)) + data)
    stream.flush()


def read(stream: BinaryIO) -> bytes | None:
    """One frame's bytes; None at the end of the stream, or where it ends inside a frame."""
    head = stream.read(HEAD.size)
    if len(head) < HEAD.size:
        return None
    (size,) = HEAD.unpack(head)
    data = stream.read(size) if size else b""
    return data if len(data) == size else None
