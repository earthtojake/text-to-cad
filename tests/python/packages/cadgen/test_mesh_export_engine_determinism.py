"""A document's mesh bytes do not depend on what warmed the store first.

Law 5: same inputs, same bytes. Meshes are tessellated by ONE tessellator, but
two engines run it — Node, for the export builders, and the snapshot browser,
which posts what it rendered back into the same content-addressed mesh store.
They share a cache key, so whichever arrives first decides what every later
export of that document writes.

That made `Math.sin`/`Math.cos` a determinism hazard: ECMA-262 specifies them to
no accuracy, and the two engines disagree on a few percent of arguments. The
symptom was tiny and easy to miss — a cylinder's seam normal came out as
-3.8e-16 from a cold store and 6.1e-17 (cos(pi/2)) after a snapshot, eight bytes
in one GLB accessor, no visible difference — and it still broke content
addressing and every freshness ledger built on it. `surf/trig.js` is the fix;
this is the door-level proof.

The fixture is a box, a CYLINDER and a second box: an analytic curved face is
what carries the seam, and a box-only model would pass either way.
"""

from __future__ import annotations

import os
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

MODEL = textwrap.dedent("""\
    from cadgen import step


    @step
    def fixture():
        from build123d.geometry import Location
        from build123d.topology import Compound, Solid

        base = Solid.make_box(40, 30, 6)
        base.label = "base"
        shaft = Solid.make_cylinder(5, 24).locate(Location((20, 15, 6)))
        shaft.label = "shaft"
        arm = Solid.make_box(10, 8, 4).locate(Location((30, 20, 30)))
        arm.label = "arm"
        model = Compound(children=[base, shaft, arm])
        model.label = "fixture"
        return model


    if __name__ == "__main__":
        fixture()
    """)

DOOR_MODULES = {"glb": "glb_build", "3mf": "threemf_build", "stl": "stl_build"}


class MeshExportEngineDeterminismTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="mesh-engine-determinism-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self.base_env = dict(os.environ)
        self.base_env.update({
            "CADGEN_DAEMON": "0",
            "CADGEN_COMPONENT_WORKERS": "1",
            "PYTHONPATH": str(REPO / "packages/cadgen/src"),
        })

    def _run(self, argv: list[str], *, cwd: Path, store: Path) -> None:
        env = dict(self.base_env, CADGEN_CACHE_DIR=str(store))
        proc = subprocess.run(
            [PYTHON, *argv], cwd=str(cwd), env=env,
            capture_output=True, text=True, timeout=600,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def _cli(self, module: str, *args: str, cwd: Path, store: Path) -> None:
        self._run(["-c", f"from cadgen.cli.{module} import main; raise SystemExit(main())", *args],
                  cwd=cwd, store=store)

    def _document(self, name: str) -> Path:
        """A fresh directory holding ONLY the written document (law 1)."""
        directory = self.root / name
        directory.mkdir()
        for artifact in self.source.parent.glob("fixture.step*"):
            if artifact.suffix != ".py":
                (directory / artifact.name).write_bytes(artifact.read_bytes())
        return directory

    def test_meshes_are_the_same_bytes_cold_and_snapshot_warmed(self) -> None:
        build = self.root / "build"
        build.mkdir()
        self.source = build / "fixture.py"
        self.source.write_text(MODEL, encoding="utf-8")
        self._run(["fixture.py"], cwd=build, store=self.root / "build-store")
        self.assertTrue((build / "fixture.step").is_file(), "the model script writes its STEP")

        cold_dir, warm_dir = self._document("cold"), self._document("warm")
        cold_store, warm_store = self.root / "store-cold", self.root / "store-warm"

        # The warm store renders the document FIRST, which fills the mesh store
        # from the browser. Its exports then read those entries instead of
        # tessellating in Node.
        self._cli("step_snapshot", "fixture.step", "shot.png", "--width", "200", "--height", "150",
                  cwd=warm_dir, store=warm_store)

        for fmt, module in DOOR_MODULES.items():
            with self.subTest(format=fmt):
                out = f"out.{fmt}"
                self._cli(module, "fixture.step", out, cwd=cold_dir, store=cold_store)
                self._cli(module, "fixture.step", out, cwd=warm_dir, store=warm_store)
                cold_bytes = (cold_dir / out).read_bytes()
                warm_bytes = (warm_dir / out).read_bytes()
                self.assertEqual(
                    cold_bytes, warm_bytes,
                    f"{fmt} exported {len(cold_bytes)} bytes from a cold store and "
                    f"{len(warm_bytes)} from a snapshot-warmed one, and they differ: the "
                    "tessellation a document exports still depends on which engine "
                    "reached the mesh store first (law 5)",
                )


if __name__ == "__main__":
    unittest.main()
