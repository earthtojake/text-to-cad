"""The SURF container, read without the kernel.

``cadgen._internal.surface_extract`` writes a component's SURF: ``SURF``, the
format version and the JSON index's length (two little-endian u32), the JSON
index (faces, edges, shapes, their metrics and boxes), then the binary payload
the index points into. Reading it is plain bytes and JSON, so a process that
only reads -- a snapshot listing parts, the CAD Viewer's server -- reads it here
and never loads OCCT.
"""

from __future__ import annotations

import json
import struct

__all__ = ["SURF_MAGIC", "read_surf", "read_surf_index"]

SURF_MAGIC = b"SURF"


def read_surf(data: bytes) -> tuple[dict, memoryview]:
    """``(index, payload)`` of a SURF container's bytes; ``ValueError`` for anything else."""
    if data[:4] != SURF_MAGIC:
        raise ValueError("not a SURF container")
    _version, json_len = struct.unpack_from("<II", data, 4)
    index = json.loads(data[12:12 + json_len].decode("utf-8"))
    return index, memoryview(data)[12 + json_len:]


def read_surf_index(path) -> dict:
    """The JSON index of the SURF container at ``path``, its payload left unread;
    ``ValueError`` for anything but a SURF container, ``OSError`` for no file."""
    with open(path, "rb") as stream:
        head = stream.read(12)
        if len(head) < 12 or head[:4] != SURF_MAGIC:
            raise ValueError("not a SURF container")
        _version, json_len = struct.unpack_from("<II", head, 4)
        return json.loads(stream.read(json_len).decode("utf-8"))
