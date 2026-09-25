"""An exported mesh is manifold: the plate-with-one-hole end of issue #371.

`skills/cad/references/supported-exports.md` promises that a mesh export is
watertight. The tessellator's own guarantee is pinned next to it, in
`packages/cadgen-js/src/lib/surf/tessellateWatertight.test.js`; this test pins
what a USER gets — the bytes of a written STL, read back with nothing but
`struct` — for the ordinary part the issue reported: a rectangular plate with a
single cylindrical through-hole. Issue #433 is the same part bent: the hole
goes through a curved wall.

A cylindrical cut's rim is where the defect lived. Boundary snapping lands two
of the bore face's vertices on one model point, and a weld that misses them
leaves a zero-area triangle that still carries its edges, so the mesh picks up
edges used by 4, 5 or 7 faces and loses its volume. The miss depended on mesh
density, so a coarse `mesh_tolerance` is exercised alongside the default.
"""

from __future__ import annotations

import collections
import os
import struct
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

REPO = Path(__file__).resolve().parents[4]
PYTHON = sys.executable

# The issue's part: 40 x 20 x 2.4 mm, one M3 clearance hole. The hole's POSITION
# mattered — x=10 was broken while x=20 was clean — so both are built.
MODEL = textwrap.dedent("""\
    from cadgen import build123d as bd
    from cadgen import stl


    @stl(out="{out}"{options})
    def plate():
        align = (bd.Align.MIN,) * 3
        body = bd.Box(40, 20, 2.4, align=align)
        return body - bd.Pos({x}, 10.0, 0) * bd.Cylinder(1.7, 7.2)


    if __name__ == "__main__":
        plate()
    """)


# Issue #433's part: a 130 mm strip of a curved wall (90 mm radius, 2.2 mm
# thick) with one 3.3 mm hole through the top of the curve. The hole meeting a
# CURVED face is the difference from the plate above; on 0.6.6 it wrote one
# triangle twice and ~20 zero-area slivers around the rim.
CURVED_WALL = textwrap.dedent("""\
    from cadgen import build123d as bd
    from cadgen import stl

    R, T = {radius}, 2.2
    L, W = 130.0, 40.0


    @stl(out="{out}"{options})
    def strip():
        ring = bd.Cylinder(R, 2 * W, rotation=(90, 0, 0)) - bd.Cylinder(R - T, 2 * W, rotation=(90, 0, 0))
        body = ring & bd.Pos(0, 0, R / 2) * bd.Box(L, W, R)
        return body - bd.Pos(0, 0, R) * bd.Cylinder(1.65, 10)


    if __name__ == "__main__":
        strip()
    """)


def read_binary_stl(path: Path) -> list[tuple[tuple[float, float, float], ...]]:
    """Every triangle as its three corners, straight out of the file."""
    data = path.read_bytes()
    count = struct.unpack("<I", data[80:84])[0]
    triangles = []
    for i in range(count):
        base = 84 + i * 50
        floats = struct.unpack("<9f", data[base + 12:base + 48])
        triangles.append(tuple(tuple(floats[j:j + 3]) for j in (0, 3, 6)))
    return triangles


def twice_area(corners) -> float:
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = corners
    ux, uy, uz = bx - ax, by - ay, bz - az
    vx, vy, vz = cx - ax, cy - ay, cz - az
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    return (nx * nx + ny * ny + nz * nz) ** 0.5


class MeshExportManifoldTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="mesh-export-manifold-")
        self.addCleanup(self._tmp.cleanup)
        self.project = Path(self._tmp.name).resolve()
        self.env = dict(os.environ)
        self.env.update({
            "CADGEN_DAEMON": "0",
            "CADGEN_COMPONENT_WORKERS": "1",
            # Its own store, so a stale tessellation cannot stand in for the run.
            "CADGEN_CACHE_DIR": str(self.project / "store"),
            "PYTHONPATH": str(REPO / "packages/cadgen/src"),
        })

    def _export(self, name: str, *, x: float = 0.0, options: str = "", model: str = MODEL, **fields) -> Path:
        out = f"STL/{name}.stl"
        script = self.project / f"{name}.py"
        script.write_text(model.format(out=out, x=x, options=options, **fields), encoding="utf-8")
        proc = subprocess.run(
            [PYTHON, script.name], cwd=str(self.project), env=self.env,
            capture_output=True, text=True, timeout=600,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        written = self.project / out
        self.assertTrue(written.is_file(), out)
        return written

    def assertManifold(self, path: Path, label: str) -> None:
        triangles = read_binary_stl(path)
        self.assertGreater(len(triangles), 0, f"{label}: the export has triangles")

        # A zero-area triangle carries no surface. It is also what breaks the
        # rest: it contributes its edges while covering nothing.
        degenerate = [t for t in triangles if twice_area(t) == 0.0]
        self.assertEqual(degenerate, [], f"{label}: zero-area triangles {degenerate[:3]}")

        # Welded by exact position, which is what a slicer does with an STL.
        faces = collections.Counter(tuple(sorted(t)) for t in triangles)
        duplicated = [face for face, used in faces.items() if used > 1]
        self.assertEqual(duplicated, [], f"{label}: triangles written more than once {duplicated[:3]}")

        edges: collections.Counter = collections.Counter()
        for triangle in triangles:
            corners = tuple(sorted(triangle))
            for a, b in ((corners[0], corners[1]), (corners[1], corners[2]), (corners[0], corners[2])):
                edges[(a, b)] += 1
        multiplicity = collections.Counter(edges.values())
        self.assertEqual(
            dict(multiplicity), {2: len(edges)},
            f"{label}: every edge of a closed solid is used by exactly two faces, got {dict(multiplicity)}",
        )

    def test_plate_with_one_hole_exports_a_manifold_mesh(self) -> None:
        # x=10 is the issue's failing position, x=20 the one that was already
        # clean — the defect was never a property of the part, only of where the
        # rim's vertices happened to land.
        for x in (10.0, 20.0):
            with self.subTest(x=x):
                self.assertManifold(self._export(f"plate_{int(x)}", x=x), f"hole at x={x}")

    def test_plate_with_one_hole_survives_a_coarse_tolerance(self) -> None:
        # The weld used to be density-dependent, so it held at the default
        # spacing and failed once the rim's triangles grew past its epsilon.
        path = self._export("plate_coarse", x=10.0, options=", mesh_tolerance=1e-2")
        self.assertManifold(path, "hole at x=10, mesh_tolerance=1e-2")

    def test_hole_through_a_curved_wall_exports_a_manifold_mesh(self) -> None:
        # The issue's radius, plus the flatter wall it reported as worse (two
        # duplicated triangles). The strip's square ends matter: the whole half
        # ring never duplicated a triangle.
        for radius in (90.0, 200.0):
            with self.subTest(radius=radius):
                path = self._export(f"strip_{int(radius)}", model=CURVED_WALL, radius=radius)
                self.assertManifold(path, f"hole through a {radius} mm wall")


if __name__ == "__main__":
    unittest.main()
