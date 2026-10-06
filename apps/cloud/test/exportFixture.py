"""The browser test's build: a small project exported for real by ``cadgen viewer export``.

    python exportFixture.py PROJECT OUT

Writes PROJECT (a STEP part, a STEP assembly, a DXF, an STL and a URDF naming it, a source file)
and seeds the two STEPs' trees and surfaces into the store named by ``CADGEN_CACHE_DIR`` without
the kernel (``tests/python/support/store_fixtures.seed_result``: proven box geometry, the shape
the viewer draws), so the export runs no native work and the test stays fast. The export itself
is the real one; what the page then does with it is the test.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "packages" / "cadgen" / "src"))

STL = """solid tetra
facet normal 0 0 -1
 outer loop
  vertex 0 0 0
  vertex 10 0 0
  vertex 0 10 0
 endloop
endfacet
facet normal 0 -1 0
 outer loop
  vertex 0 0 0
  vertex 0 0 10
  vertex 10 0 0
 endloop
endfacet
facet normal -1 0 0
 outer loop
  vertex 0 0 0
  vertex 0 10 0
  vertex 0 0 10
 endloop
endfacet
facet normal 1 1 1
 outer loop
  vertex 10 0 0
  vertex 0 0 10
  vertex 0 10 0
 endloop
endfacet
endsolid tetra
"""
URDF = """<?xml version="1.0"?>
<robot name="smoke">
  <link name="base"><visual><geometry><mesh filename="meshes/tetra.stl" scale="0.001 0.001 0.001"/></geometry></visual></link>
  <link name="arm"><visual><geometry><cylinder radius="0.012" length="0.10"/></geometry></visual></link>
  <joint name="shoulder" type="revolute">
    <parent link="base"/><child link="arm"/>
    <origin xyz="0 0 0.06"/><axis xyz="0 1 0"/>
    <limit lower="-1.0" upper="1.0" effort="1" velocity="1"/>
  </joint>
</robot>
"""


def main(project: Path, out: Path) -> None:
    import ezdxf

    from cadgen.viewer.export import export_views
    from tests.python.support.store_fixtures import seed_result

    for folder in ("src", "STEP", "DXF", "meshes"):
        (project / folder).mkdir(parents=True, exist_ok=True)
    (project / "src" / "bracket.py").write_text("from cadgen import step\n\n@step\ndef bracket():\n    ...\n", encoding="utf-8")
    part = project / "STEP" / "bracket.step"
    part.write_text("ISO-10303-21; bracket\n", encoding="utf-8")
    seed_result(part, {"label": "bracket"})
    assembly = project / "STEP" / "pair.step"
    assembly.write_text("ISO-10303-21; pair\n", encoding="utf-8")
    seed_result(assembly, {"label": "pair", "components": {"left": {}, "right": {}}})
    (assembly.parent / "pair.step.json").write_text(json.dumps({
        "schemaVersion": 9, "documentHash": hashlib.sha256(assembly.read_bytes()).hexdigest(),
    }), encoding="utf-8")
    document = ezdxf.new()
    document.modelspace().add_lwpolyline([(-10, -6), (10, -6), (10, 6), (-10, 6)], close=True, dxfattribs={"layer": "OUTLINE"})
    document.saveas(str(project / "DXF" / "plate.dxf"))
    (project / "meshes" / "tetra.stl").write_text(STL, encoding="utf-8")
    (project / "robot.urdf").write_text(URDF, encoding="utf-8")
    print(json.dumps(export_views(str(project), str(out))))


if __name__ == "__main__":
    if len(sys.argv) != 3 or not os.environ.get("CADGEN_CACHE_DIR"):
        raise SystemExit("usage: CADGEN_CACHE_DIR=STORE python exportFixture.py PROJECT OUT")
    main(Path(sys.argv[1]), Path(sys.argv[2]))
