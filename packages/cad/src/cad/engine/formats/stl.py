"""An STL's triangles, binary or ASCII, read with numpy: one part, its numbers taken as
millimetres (an STL says no unit; the viewer draws its numbers as they are).

Binary or ASCII is told as three's ``STLLoader`` tells it: binary when the size is the header,
the count and that many 50-byte facets; else ASCII when ``solid`` opens it (within its first
bytes); else binary. A facet's own normal is not read: the viewer smooths or creases the
triangles itself (``buffer.py``)."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

__all__ = ["StlError", "read_stl"]

_FACET = np.dtype([("normal", "<f4", 3), ("corners", "<f4", (3, 3)), ("attribute", "<u2")])
_VERTEX = re.compile(rb"vertex\s+(\S+)\s+(\S+)\s+(\S+)")


class StlError(ValueError):
    """A file that does not read as an STL, said by name."""


def _binary(data: bytes) -> bool:
    if len(data) >= 84 and 84 + 50 * int.from_bytes(data[80:84], "little") == len(data):
        return True
    return not any(data[offset:offset + 5] == b"solid" for offset in range(5))


def read_stl(path: Path) -> np.ndarray:
    """The triangles of the STL at ``path``: (M, 3, 3) float64, as its numbers are."""
    data = Path(path).read_bytes()
    if _binary(data):
        if len(data) < 84:
            raise StlError(f"{Path(path).name} is too short to be an STL")
        count = min(int.from_bytes(data[80:84], "little"), (len(data) - 84) // 50)
        facets = np.frombuffer(data, _FACET, count, 84)
        return facets["corners"].astype(np.float64)
    found = _VERTEX.findall(data)
    if len(found) % 3:
        raise StlError(f"{Path(path).name}: an ASCII STL's vertices come three to a facet; it has {len(found)}")
    try:
        return np.array(found, dtype=np.float64).reshape(-1, 3, 3)
    except ValueError as error:
        raise StlError(f"{Path(path).name}: a vertex is not three numbers ({error})") from None
