"""CalculiX's files: a study as its input, and what it prints read back.

A study's mesh is written as C3D10 elements (each part its own element set and material), its held nodes as boundary
conditions -- a node held along directions that are not global axes (a sloped or curved roller) in its own frame
(``*TRANSFORM``) -- and its loads as nodal forces (``*CLOAD``).
CalculiX prints the displacement of every node, the reaction on every held node and the stress at each element's four
integration points; :func:`read_dat` reads them. Stdlib only at import; numerics inside the functions.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    import numpy as np

    from cad._internal.fea.study import Material

__all__ = ["C3D10_EDGES", "C3D10_POINTS", "SMALLEST_JACOBIAN", "c3d10_elements", "read_dat", "write_inp"]

#: C3D10's mid-edge nodes 5-10 sit on these corner pairs (CalculiX's order, Abaqus's too).
C3D10_EDGES = ((0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3))
#: C3D10's four integration points, barycentric on its corners: point k is the one nearest corner k.
C3D10_POINTS = tuple(tuple(0.585410196624968 if k == n else 0.138196601125011 for k in range(4)) for n in range(4))
#: CalculiX refuses an element whose Jacobian determinant is under this at any of :data:`C3D10_POINTS`
#: (``*ERROR in e_c3d: nonpositive jacobian``), and checks nowhere else.
SMALLEST_JACOBIAN = 1e-20
#: CalculiX reads each number from its first 20 characters: 13 significant digits fit with sign and exponent.
_REAL = "{:.12e}"


def c3d10_elements(nodes: "np.ndarray", tets: "np.ndarray") -> "np.ndarray":
    """(E, 10) netgen's tetrahedra (``tets``: corners, then mid-edge nodes in :data:`NETGEN_EDGES`' order) in C3D10's:
    corners turned (2 and 3 swapped) where they give a negative volume, as CalculiX needs
    ``(x2 - x1) × (x3 - x1) · (x4 - x1) > 0``, then the node on each of :data:`C3D10_EDGES`' corner pairs."""
    import numpy as np

    from cad.netgen._mesher import NETGEN_EDGES

    tets = np.asarray(tets)
    if tets.shape[1] != 10:
        raise ValueError("CalculiX's C3D10 needs quadratic (10-node) tetrahedra")
    x = nodes
    a, b, c, d = (x[tets[:, k]] for k in range(4))
    turned = np.einsum("ij,ij->i", np.cross(b - a, c - a), d - a) < 0.0
    slot = {pair: 4 + k for k, pair in enumerate(NETGEN_EDGES)}
    out = np.empty_like(tets)
    for rows, corners in ((~turned, (0, 1, 2, 3)), (turned, (0, 2, 1, 3))):
        out[rows, :4] = tets[rows][:, list(corners)]
        for k, (i, j) in enumerate(C3D10_EDGES, start=4):
            out[rows, k] = tets[rows][:, slot[tuple(sorted((corners[i], corners[j])))]]
    return out


def _lines(values, per_line: int = 10):
    """Comma-separated rows of at most ``per_line`` numbers: CalculiX reads 132 characters a line."""
    values = [str(v) for v in values]
    for start in range(0, len(values), per_line):
        yield ", ".join(values[start:start + per_line])


def write_inp(path: Path, nodes: "np.ndarray", elements: "np.ndarray", part_of: "np.ndarray",
              materials: "Sequence[Material]", held: "Sequence[tuple[int, int]]", frames: "dict[int, np.ndarray]",
              forces: "np.ndarray") -> None:
    """The CalculiX input of one linear static solve.

    Node ``n + 1`` is ``nodes[n]`` and element ``e + 1`` is ``elements[e]`` (C3D10's order); each part
    (``part_of``, an index into ``materials``) is an element set with its own material. ``held`` are ``(node,
    direction)`` pairs held at zero, the direction a global axis, or an axis of the node's own frame where ``frames``
    has one (columns: its axes; the first two are CalculiX's local x and y). ``forces`` (N, 3) are nodal forces in N,
    in the global axes: CalculiX reads a framed node's force in its frame, so that node's is turned into it. The step
    prints U for every node, RF on the held nodes and S at every element's integration points.
    """
    import numpy as np

    real = _REAL.format
    out = ["** cad: linear static", "*NODE, NSET=NALL"]
    out += [f"{n + 1}, {real(x)}, {real(y)}, {real(z)}" for n, (x, y, z) in enumerate(np.asarray(nodes).tolist())]
    sets = []
    for index, material in enumerate(materials):
        rows = np.flatnonzero(np.asarray(part_of) == index)
        if not len(rows):
            continue
        sets.append(f"PART{index}")
        out.append(f"*ELEMENT, TYPE=C3D10, ELSET=PART{index}")
        out += [f"{e + 1}, " + ", ".join(str(n + 1) for n in elements[e]) for e in rows.tolist()]
        out += [f"*MATERIAL, NAME=MATERIAL{index}", "*ELASTIC", f"{real(material.E)}, {real(material.nu)}",
                f"*SOLID SECTION, ELSET=PART{index}, MATERIAL=MATERIAL{index}"]
    held_nodes = sorted({node for node, _ in held})
    if held_nodes:
        out += ["*NSET, NSET=NHELD", *_lines(n + 1 for n in held_nodes)]
    for node in sorted(frames):
        frame = frames[node]
        out += [f"*NSET, NSET=T{node + 1}", str(node + 1), f"*TRANSFORM, NSET=T{node + 1}, TYPE=R",
                ", ".join(real(v) for v in (*frame[:, 0], *frame[:, 1]))]
    out += ["*STEP", "*STATIC"]
    if held:
        out += ["*BOUNDARY", *(f"{node + 1}, {k + 1}, {k + 1}, 0." for node, k in held)]
    forces = np.array(forces, dtype=float)
    for node, frame in frames.items():
        forces[node] = frame.T @ forces[node]
    loaded = np.argwhere(forces != 0.0)
    if len(loaded):
        out += ["*CLOAD", *(f"{n + 1}, {k + 1}, {real(forces[n, k])}" for n, k in loaded.tolist())]
    # GLOBAL=YES: a node in its own frame prints in the global axes too.
    out += ["*NODE PRINT, NSET=NALL, GLOBAL=YES", "U"]
    if held_nodes:
        out += ["*NODE PRINT, NSET=NHELD, TOTALS=NO, GLOBAL=YES", "RF"]
    for name in sets:
        out += [f"*EL PRINT, ELSET={name}", "S"]
    out += ["*END STEP", ""]
    Path(path).write_text("\n".join(out), encoding="ascii")


_BLOCKS = {"displacements": "U", "forces": "RF", "stresses": "S"}
# Fortran's E13.6 drops the E of a three-digit exponent: 1.234567-100.
_BARE_EXPONENT = re.compile(r"(?<=\d)([+-]\d{3})\b")


def read_dat(text: str) -> "dict[str, np.ndarray]":
    """The printed blocks of a CalculiX .dat as arrays: ``U`` and ``RF`` rows ``(node, x, y, z)``, ``S`` rows
    ``(element, point, xx, yy, zz, xy, xz, yz)``. A block's rows follow its title line and one blank line; blocks
    of one kind (each part's stresses) are joined."""
    import io

    import numpy as np

    blocks: dict[str, list[str]] = {}
    current: list[str] | None = None
    titled = False                                                  # the last line was a block's title
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            current = current if titled else None
            titled = False
            continue
        title = stripped.split(" ", 1)[0]
        titled = title in _BLOCKS and " for set " in stripped
        if titled:
            current = blocks.setdefault(_BLOCKS[title], [])
        elif current is not None:
            current.append(stripped)
    out = {}
    for name, rows in blocks.items():
        body = "\n".join(rows)
        try:
            out[name] = np.loadtxt(io.StringIO(body), ndmin=2)
        except ValueError:
            out[name] = np.loadtxt(io.StringIO(_BARE_EXPONENT.sub(r"E\1", body)), ndmin=2)
    return out
