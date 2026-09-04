"""The layering rule, held on a build the test performs itself.

Two stores of state sit beside a generated STEP and neither may leak into the other:

* The TREE is what the bytes imply -- derived, evictable, content-keyed. Kinematics
  is not derivable from artifact bytes, so a tree carrying it would make
  identical-bytes documents collide and would be swept by `cadgen store gc`.
* The SIDECAR is what the author declared, and it TRAVELS WITH THE FILE. It holds
  kinematics and nothing else (law 17): no mesh declarations, no choreography (the
  render module beside the document is read by the viewer, never by a build), and
  no path into anybody's source tree.

The fixture is a hinge with one revolute mate, written and built here in a fresh
store, so the assertions hold on a real build and read nothing under models/.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from tests.python.support.paths import REPO_ROOT, add_repo_path

add_repo_path("packages/cadgen/src")

HINGE_SOURCE = """\
import cadgen
from cadgen import label_shape, step
from cadgen import build123d as bd

KINEMATICS = {
    "mates": [
        cadgen.revolute("swing", parent="#base", child="#arm",
                        origin=(0, 0, 6), direction=(0, 0, 1), limits=(0, 90)),
    ],
    "poses": {"open": {"swing": 45}},
}


@step(kinematics=KINEMATICS)
def hinge():
    base = label_shape(bd.Box(20, 20, 4), "base")
    arm = label_shape(bd.Pos(10, 0, 6) * bd.Box(16, 4, 4), "arm")
    return bd.Compound(children=[base, arm])


if __name__ == "__main__":
    hinge()
"""

# Keys that belong to the sidecar and must never appear in the tree's assembly.json.
SIDECAR_ONLY_KEYS = ("kinematics",)


class LayeringCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._project = tempfile.TemporaryDirectory(prefix="layering-")
        cls._store = tempfile.TemporaryDirectory(prefix="layering-store-")
        root = Path(cls._project.name)
        script = root / "hinge.py"
        script.write_text(HINGE_SOURCE, encoding="utf-8")
        env = dict(os.environ)
        env.update(
            {
                "CADGEN_DAEMON": "0",
                "CADGEN_CACHE_DIR": cls._store.name,
                "PYTHONPATH": str(REPO_ROOT / "packages" / "cadgen" / "src"),
            }
        )
        completed = subprocess.run(
            [sys.executable, script.name],
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        if completed.returncode != 0:
            raise AssertionError(completed.stderr[-2000:])
        cls.document = root / "hinge.step"
        cls.sidecar = json.loads((root / "hinge.step.json").read_text(encoding="utf-8"))
        with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": cls._store.name}):
            from cadgen.catalog import result_view_dir

            view = result_view_dir(cls.document)
        cls.descriptor = json.loads((view / "assembly.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls) -> None:
        cls._project.cleanup()
        cls._store.cleanup()


class TreeCarriesNoAuthoredState(LayeringCase):
    def test_the_tree_carries_no_kinematics(self) -> None:
        for key in SIDECAR_ONLY_KEYS:
            self.assertNotIn(
                key,
                self.descriptor,
                f"{key!r} is AUTHORED state and belongs in the sidecar; a content-keyed "
                "tree cannot hold it (identical bytes would collide, and gc would sweep it)",
            )


class SidecarCarriesKinematicsOnly(LayeringCase):
    def test_the_sidecar_holds_kinematics_and_its_schema_and_nothing_else(self) -> None:
        self.assertEqual(sorted(self.sidecar), ["kinematics", "schemaVersion"])

    def test_the_sidecar_reaches_into_no_source_tree(self) -> None:
        # A generated file has zero dependencies on the machine that made it.
        text = json.dumps(self.sidecar)
        self.assertNotIn(str(Path(self._project.name).resolve()), text)
        self.assertNotIn(str(REPO_ROOT), text)


if __name__ == "__main__":
    unittest.main()
