"""The sidecar boundary (packages/cadgen/README.md, law 3).

A sidecar belongs to the model that declared it -- never to its parent, never
to its children. A parent composing a child receives geometry and nothing
else. The one mate concept that persists is ``@step(kinematics=)``: a child
that declares its own joints writes them into ITS sidecar when it builds, and
a parent that composes that child writes only the joints the parent declared
into its own. The check builds real model scripts composing each other through
the real pipeline and reads the sidecars off disk.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path
from tests.python.support.cad_test_roots import IsolatedCadRoots

add_repo_path("packages/cadgen/src")

CHILD = '''import cadgen
from cadgen import label_shape, step
from cadgen import build123d as bd

KINEMATICS = {
    "mates": [
        cadgen.revolute("child_swing", parent="#child_base", child="#child_arm",
                        origin=(0, 0, 4), direction=(0, 0, 1), limits=(0, 90)),
    ],
}


@step(kind="assembly", kinematics=KINEMATICS)
def child():
    base = label_shape(bd.Box(20, 20, 4), "child_base")
    arm = label_shape(bd.Pos(10, 0, 6) * bd.Box(16, 4, 4), "child_arm")
    return bd.Compound(children=[base, arm])


if __name__ == "__main__":
    child()
'''

PARENT = '''import cadgen
from cadgen import label_shape, step
from cadgen import build123d as bd

import child

KINEMATICS = {
    "mates": [
        cadgen.revolute("parent_swing", parent="#plate", child="#sub",
                        origin=(0, 0, 3), direction=(0, 0, 1), limits=(0, 45)),
    ],
}


@step(kind="assembly", kinematics=KINEMATICS)
def parent():
    sub = child.child()                        # composition: geometry only
    sub.label = "sub"
    plate = label_shape(bd.Box(40, 40, 3), "plate")
    return bd.Compound(children=[plate, sub])


if __name__ == "__main__":
    parent()
'''


class SidecarBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._roots = IsolatedCadRoots(self, prefix="sidecar-boundary-")
        self._tempdir = self._roots.temporary_cad_directory(prefix="tmp-sidecar-boundary-")
        self.root = Path(self._tempdir.name)
        (self.root / "child.py").write_text(CHILD, encoding="utf-8")
        (self.root / "parent.py").write_text(PARENT, encoding="utf-8")

    def tearDown(self) -> None:
        self._tempdir.cleanup()

    def _build(self, script: Path) -> int:
        from cadgen.catalog import StepImportOptions
        from cadgen.generation import generate_step_targets

        out = script.with_suffix(".step")
        return generate_step_targets(
            [f"{script}={out.as_posix()}"],
            step_options=StepImportOptions(),
            force=True,
            verbose=False,
        )

    def _sidecar_mates(self, script: Path) -> list[str]:
        from cadgen._internal.source_sidecar import read_source_sidecar

        sidecar = read_source_sidecar(script.with_suffix(".step")) or {}
        return [str(mate.get("name")) for mate in sidecar.get("kinematics", {}).get("mates", [])]

    def test_each_model_writes_only_its_own_kinematics(self) -> None:
        child = self.root / "child.py"
        parent = self.root / "parent.py"
        self.assertEqual(0, self._build(child))
        self.assertEqual(0, self._build(parent))

        self.assertEqual(["child_swing"], self._sidecar_mates(child))
        self.assertEqual(
            ["parent_swing"],
            self._sidecar_mates(parent),
            "a child's kinematics must not ride up into the parent's sidecar",
        )


if __name__ == "__main__":
    unittest.main()
