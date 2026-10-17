"""The GLBs the core and UI suites open: cadgen's own exports, and one compressed sample.

``pair`` (``MODEL`` below) is two boxes, in millimetres, Z up: ``base``, a 20 mm cube from
the origin to (20, -20, 20), red (#D02020) in a polished finish (roughness 0.05, metalness
1), and ``rider``, a 10 mm cube from (30, -10, 0) to (40, 0, 10), blue (#2040D0). Its clip
``slide`` moves the rider 60 mm along +X over one second and holds there. This writes:

- ``pair.glb``: ``cadgen glb build pair.step``, the static export (colour-grouped primitives).
- ``pair.slide.glb``: ``cadgen glb build pair.step --animation slide``, the animated export
  (one node per occurrence, ``o1.1`` the base and ``o1.2`` the rider, the rider under the
  clip's pivot, keyed CUBICSPLINE).

``cube.meshopt.glb`` is not made here: cadgen writes no compressed GLB, but a GLB a person
opens can be one, and the loader decodes it. It is a unit cube (12 triangles, #3366CC),
welded, quantized (``KHR_mesh_quantization``) and meshopt-compressed
(``EXT_meshopt_compression``, required), written by the JS writer this repository once kept
for test fixtures (``packages/core/src/lib/glb/writeGlb.js``, its ``render`` preset;
``git log --diff-filter=D -- packages/core/src/lib/glb/writeGlb.js`` names the commit that
deleted it), and kept as bytes: both extensions are ratified glTF, so it has no reason to
move. Any writer of them can replace it (meshoptimizer's ``gltfpack -c`` over a cube) as
long as ``glbMeshoptRoundTrip.test.js`` still describes it.

Run it from the repository root with the repo's Python whenever cadgen's GLB export moves::

    .venv/bin/python packages/core/src/lib/render/fixtures/make_fixtures.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[5]

MODEL = '''\
import cadgen
from cadgen import build123d as bd
from cadgen import srgb, step

MATERIALS = {
    "definitions": {"polished": {"name": "Polished", "roughness": 0.05, "metalness": 1}},
    "assignments": [{"targets": ["#base"], "material": "polished"}],
}


def slide(t, m):
    m.get("#rider").translate((60 * t, 0, 0))


@step(out="pair.step", materials=MATERIALS,
      animation={"slide": cadgen.clip(slide, duration=1, loop=False, fps=1)})
def pair():
    base = bd.Pos(10, -10, 10) * bd.Box(20, 20, 20)
    base.label = "base"
    base.color = srgb("#D02020")
    rider = bd.Pos(35, -5, 5) * bd.Box(10, 10, 10)
    rider.label = "rider"
    rider.color = srgb("#2040D0")
    return bd.Compound(children=[base, rider], label="pair")


if __name__ == "__main__":
    pair()
'''

EXPORT = '''\
import sys
from pathlib import Path
from cadgen import glb

step = Path(sys.argv[1])
glb.build(step, step.with_name("pair.glb"))
glb.build(step, step.with_name("pair.slide.glb"), animation="slide")
'''


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="glb-fixtures-") as folder:
        root = Path(folder)
        (root / "pair.py").write_text(MODEL, encoding="utf-8")
        env = {**os.environ, "CADGEN_DAEMON": "0", "CADGEN_TELEMETRY": "0", "CADGEN_UPDATE_CHECK": "0",
               "DO_NOT_TRACK": "1", "CADGEN_CACHE_DIR": str(root / "store"), "CADGEN_STATE_DIR": str(root / "state"),
               "PYTHONPATH": str(REPO / "packages/cadgen/src")}
        subprocess.run([sys.executable, "pair.py"], cwd=root, env=env, check=True)
        subprocess.run([sys.executable, "-c", EXPORT, str(root / "pair.step")], cwd=root, env=env, check=True)
        for name in ("pair.glb", "pair.slide.glb"):
            shutil.copyfile(root / name, HERE / name)
    print(json.dumps({name: (HERE / name).stat().st_size for name in ("pair.glb", "pair.slide.glb")}))


if __name__ == "__main__":
    main()
