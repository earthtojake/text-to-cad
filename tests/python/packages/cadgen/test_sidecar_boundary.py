"""The sidecar boundary (packages/cadgen/README.md, law 3).

A sidecar belongs to the model that declared it -- never to its parent, never
to its children. A parent composing a child receives geometry and nothing
else, so the STEP exporter attaches to a model's scene ONLY the mates that
model declared on its own compound, even though the child it composes
declares mates of its own; the child's own export sees the child's mates.

Before this law the exporter walked the whole returned tree gathering
``assembly_mates`` from every node, so a child's relations silently became
the parent's. The check runs against real build123d compounds produced by
real model scripts composing each other, through the real exporter.
"""

from __future__ import annotations

import importlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.authoring import building  # noqa: E402
from cadgen.step_export import build_build123d_step_scene  # noqa: E402

CHILD = '''from cadgen import build123d as bd
from cadgen import step
from cadgen.assembly import AssemblyHelper


@step
def child():
    asm = AssemblyHelper("child")
    base = asm.add(bd.Box(20, 20, 4), "child_base")
    lid = asm.add(bd.Box(20, 20, 2), "child_lid")
    seat = asm.rigid_frame(base, "seat", bd.Location((0, 0, 2)))
    underside = asm.rigid_frame(lid, "underside", bd.Location((0, 0, -1)))
    asm.face_to_face(seat, underside, label="child_mate")
    return asm.build()


if __name__ == "__main__":
    child()
'''

PARENT = '''from cadgen import build123d as bd
from cadgen import step
from cadgen.assembly import AssemblyHelper

import child


@step
def parent():
    asm = AssemblyHelper("parent")
    sub = asm.add(child.child(), "sub")           # composition: geometry only
    plate = asm.add(bd.Box(40, 40, 3), "plate")
    top = asm.rigid_frame(plate, "top", bd.Location((0, 0, 1.5)))
    foot = asm.rigid_frame(sub, "foot", bd.Location((0, 0, -2)))
    asm.face_to_face(top, foot, label="parent_mate")
    return asm.build()


if __name__ == "__main__":
    parent()
'''


class SidecarBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="sidecar-boundary-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        (self.root / "child.py").write_text(CHILD, encoding="utf-8")
        (self.root / "parent.py").write_text(PARENT, encoding="utf-8")
        sys.path.insert(0, str(self.root))
        self.addCleanup(sys.path.remove, str(self.root))
        for name in ("child", "parent"):
            sys.modules.pop(name, None)
            self.addCleanup(sys.modules.pop, name, None)

    def _scene_mates(self, module_name: str) -> list[str]:
        module = importlib.import_module(module_name)
        # Calling a decorated model outside a build would BUILD it; inside
        # ``building()`` it composes and returns the compound, which is the
        # object the exporter reads.
        with building():
            compound = getattr(module, module_name)()
        scene = build_build123d_step_scene(
            compound, self.root / f"{module_name}.step", source_kind="python"
        )
        return [str(mate.get("sourceLabel")) for mate in getattr(scene, "assembly_mates", None) or []]

    def test_a_parent_scene_carries_only_the_parents_own_mates(self) -> None:
        self.assertEqual(["child_mate"], self._scene_mates("child"))
        self.assertEqual(
            ["parent_mate"],
            self._scene_mates("parent"),
            "a child's mates must not ride up into the parent's scene",
        )


if __name__ == "__main__":
    unittest.main()
