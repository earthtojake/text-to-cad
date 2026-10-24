"""Binary STL: every placed triangle, in millimetres, its normal from its corners."""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

import numpy as np

from cadgen.engine.export.mesh import meshes, placed_points

__all__ = ["write"]

_RECORD = np.dtype([("normal", "<f4", 3), ("corners", "<f4", (3, 3)), ("attribute", "<u2")])


def write(view: Any, path: Path) -> None:
    held = meshes(view)
    total = sum(held[placed.prototype].triangles for placed in view.placements)
    with open(path, "wb") as handle:
        handle.write(view.name.encode("ascii", "replace")[:80].ljust(80, b" "))
        handle.write(struct.pack("<I", total))
        for placed in view.placements:
            mesh = held[placed.prototype]
            if not mesh.triangles:
                continue
            corners = placed_points(mesh.positions, placed.matrix)[mesh.indices.reshape(-1, 3)]
            normal = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
            lengths = np.linalg.norm(normal, axis=1, keepdims=True)
            rows = np.zeros(len(corners), dtype=_RECORD)
            rows["normal"] = normal / np.where(lengths > 0, lengths, 1)
            rows["corners"] = corners
            handle.write(rows.tobytes())
