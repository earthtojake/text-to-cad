"""A document's mesh bytes do not depend on what warmed the store first.

Law 5: same inputs, same bytes. Every mesh is OCCT's, derived once per component
and tolerance into the store's content-addressed mesh entries, and three paths
reach them: a build exporting its own declared mesh, which derives them in its
own process (no build-pool job: its kernel and shapes are already loaded); a
door's export, which derives them in build-pool jobs; and a snapshot, which
derives the meshes it draws. They share a key, so whichever arrives first
decides what every later export of that document reads -- and the bytes must
not care which one that was.

The fixture is a box, a CYLINDER and a second box: an analytic curved face is
what carries a seam, and a box-only model would pass either way.
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
    from cadgen import step, stl


    @step
    @stl
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

# The model script's run, with every build-pool dispatch refused: the build's own
# export must derive its surfaces and meshes in the build's process.
BUILD_IN_PROCESS = textwrap.dedent("""\
    import runpy
    import sys

    from cadgen.daemon import artifacts


    def refuse(request, root):
        raise AssertionError(f"the build's own export submitted a {request['kind']} job to the build pool")


    artifacts._dispatch = refuse
    sys.argv = ["fixture.py"]
    runpy.run_path("fixture.py", run_name="__main__")
    """)


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

    def _doors(self, *, cwd: Path, store: Path) -> None:
        """Every door's export of the document, `out.<format>`, one after another in ONE
        process, as a warm worker serves them: each reads the store the ones before it
        filled, exactly as separate runs on that store would."""
        calls = "".join(
            f"code = __import__('cadgen.cli.{module}', fromlist=['main']).main(['fixture.step', 'out.{fmt}'])\n"
            "if code:\n    raise SystemExit(code)\n"
            for fmt, module in DOOR_MODULES.items()
        )
        self._run(["-c", calls], cwd=cwd, store=store)

    def _document(self, name: str) -> Path:
        """A fresh directory holding ONLY the written document (law 1)."""
        directory = self.root / name
        directory.mkdir()
        for artifact in self.source.parent.glob("fixture.step*"):
            if artifact.suffix != ".py":
                (directory / artifact.name).write_bytes(artifact.read_bytes())
        return directory

    def test_meshes_are_the_same_bytes_built_cold_and_snapshot_warmed(self) -> None:
        build = self.root / "build"
        build.mkdir()
        self.source = build / "fixture.py"
        self.source.write_text(MODEL, encoding="utf-8")
        self._run(["-c", BUILD_IN_PROCESS], cwd=build, store=self.root / "build-store")
        self.assertTrue((build / "fixture.step").is_file(), "the model script writes its STEP")
        built = (build / "fixture.stl").read_bytes()

        cold_dir, warm_dir = self._document("cold"), self._document("warm")
        cold_store, warm_store = self.root / "store-cold", self.root / "store-warm"

        # The warm store renders the document FIRST, which fills the mesh store
        # for the snapshot. Its exports then read those entries instead of
        # deriving their own.
        self._cli("step_snapshot", "fixture.step", "shot.png", "--width", "200", "--height", "150",
                  cwd=warm_dir, store=warm_store)

        self._doors(cwd=cold_dir, store=cold_store)
        self._doors(cwd=warm_dir, store=warm_store)
        for fmt in DOOR_MODULES:
            with self.subTest(format=fmt):
                out = f"out.{fmt}"
                cold_bytes = (cold_dir / out).read_bytes()
                warm_bytes = (warm_dir / out).read_bytes()
                self.assertEqual(
                    cold_bytes, warm_bytes,
                    f"{fmt} exported {len(cold_bytes)} bytes from a cold store and "
                    f"{len(warm_bytes)} from a snapshot-warmed one, and they differ: the "
                    "mesh a document exports depends on which path reached the store "
                    "first (law 5)",
                )
        self.assertEqual(
            built, (cold_dir / "out.stl").read_bytes(),
            "the build's own STL, derived in its process, differs from a door's, derived "
            "in build-pool jobs from an empty store (law 5)",
        )


if __name__ == "__main__":
    unittest.main()
