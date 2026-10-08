"""The tube skins the core suite plays: cadgen's own payload for a 20 mm cord that curls.

The cord (``cord.py`` below) is a 0.8 mm round tube 20 mm long on +X from the
origin; its clip ``curl`` bends it, over one second, into a quarter circle of
radius 40/pi mm about (0, 40/pi, 0), keeping its length, with joints 2 mm apart.
This writes the document sidecar's animation section (``cord.animation.json``)
and cadgen's tube skins for it (``cord.skins.glb``), exactly the bytes the
viewer's ``GET /__cad/tube-skins`` serves, so the JS suites read what cadgen
writes and no JS writes the format.

Run it from the repository root with the repo's Python whenever the payload, the
binding rule or the mesher moves::

    .venv/bin/python packages/core/src/common/fixtures/tube_skins/make_fixture.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[5]

MODEL = '''\
import math

import cadgen
from cadgen import build123d as bd
from cadgen import step

REST = {"normal": [0, 0, 1], "segments": [{"kind": "line", "start": [0, 0, 0], "end": [20, 0, 0]}]}


def curl(t, m):
    angle = max(t, 1e-3) * math.pi / 2
    m.get("#cord").deform_tube(rest=REST, path={"normal": [0, 0, 1], "segments": [{
        "kind": "arc", "center": [0, 20 / angle, 0], "axis": [0, 0, 1], "start": [0, 0, 0],
        "sweepDeg": math.degrees(angle)}]}, max_segment_length=2)


@step(out="cord.step", animation={"curl": cadgen.clip(curl, duration=1, loop=False, fps=10)})
def cord():
    body = bd.sweep(bd.Plane(origin=(0, 0, 0), z_dir=(1, 0, 0)) * bd.Circle(0.8),
                    path=bd.Edge.make_line((0, 0, 0), (20, 0, 0)))
    body.label = "cord"
    return bd.Compound(children=[body], label="assembly")


if __name__ == "__main__":
    cord()
'''

PROBE = '''\
import json, sys
from pathlib import Path
from cadgen._internal.source_sidecar import read_source_sidecar
from cadgen._internal.tube_skin_payload import tube_skins_bytes
from cadgen.viewer.store_paths import result_snapshot

step = sys.argv[1]
document, tree = result_snapshot(step)
animation = read_source_sidecar(step, document_hash=document)["animation"]
Path(sys.argv[2]).write_bytes(tube_skins_bytes(tree=tree, document_hash=document, animation=animation))
Path(sys.argv[3]).write_text(json.dumps(animation, indent=1) + "\\n", encoding="utf-8")
'''


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="tube-skins-fixture-") as folder:
        root = Path(folder)
        (root / "cord.py").write_text(MODEL, encoding="utf-8")
        env = {**os.environ, "CADGEN_DAEMON": "0", "CADGEN_TELEMETRY": "0", "CADGEN_CACHE_DIR": str(root / "store"),
               "CADGEN_STATE_DIR": str(root / "state"), "PYTHONPATH": str(REPO / "packages/cadgen/src")}
        subprocess.run([sys.executable, "cord.py"], cwd=root, env=env, check=True)
        subprocess.run([sys.executable, "-c", PROBE, str(root / "cord.step"), str(HERE / "cord.skins.glb"),
                        str(HERE / "cord.animation.json")], cwd=root, env=env, check=True)
    print(json.dumps({"skins": (HERE / "cord.skins.glb").stat().st_size,
                      "animation": (HERE / "cord.animation.json").stat().st_size}))


if __name__ == "__main__":
    main()
