"""kinematics= end to end: declaration -> resolved sidecar -> baked artifact.

The decoration-time vocabulary is pinned in test_kinematics_def; this covers
the BUILD half (design/pose-animation-split.md): mate refs validate against
real occurrences, axis selector refs resolve to world numbers, the block lands
in the ``.step.json`` sidecar (schema 4) with the animation module's text
COPIED in, and the kinematics dict's ``"at"`` key bakes the artifact —
descriptor transforms move, and the sidecar re-zeroes so the artifact as
written is q=0.
"""

from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path
from tests.python.support.cad_test_roots import IsolatedCadRoots

add_repo_path("packages/cadgen/src")

HINGE_MODEL = """
import cadgen
from cadgen import label_shape, step
from cadgen import build123d as bd

KINEMATICS = {{
    "mates": [
        cadgen.revolute("swing", parent="#base", child="#arm",
                        origin=(0, 0, 6), direction=(0, 0, 1), limits=(0, 90)),
    ],
    "poses": {{"open": {{"swing": 45}}}}{kinematics_extra},
}}

@step(kind="assembly", kinematics=KINEMATICS{extra})
def hinge():
    base = label_shape(bd.Box(20, 20, 4), "base")
    arm = label_shape(bd.Pos(10, 0, 6) * bd.Box(16, 4, 4), "arm")
    return bd.Compound(children=[base, arm])


if __name__ == "__main__":
    hinge()
"""

ANIM_JS = "export const clips = { demo: { duration: 2, update(t, m) {} } };\n"

# The same hinge, but each side is a GROUP of two parts. Mating the groups is
# what "a mate on a parent occurrence carries its whole instance subtree" means
# in practice, and it is the shape every real assembly has.
GROUPED_MODEL = """
import cadgen
from cadgen import label_shape, step
from cadgen import build123d as bd

KINEMATICS = {
    "mates": [
        cadgen.revolute("swing", parent="#base_group", child="#arm_group",
                        origin=(0, 0, 6), direction=(0, 0, 1), limits=(0, 90)),
    ],
}

def _group(label, parts):
    return bd.Compound(obj=list(parts), children=list(parts), label=label)

@step(kind="assembly", kinematics=KINEMATICS)
def grouped():
    base = _group("base_group", [
        label_shape(bd.Box(20, 20, 4), "base_plate"),
        label_shape(bd.Pos(0, 0, 4) * bd.Box(8, 8, 4), "base_boss"),
    ])
    arm = _group("arm_group", [
        label_shape(bd.Pos(10, 0, 6) * bd.Box(16, 4, 4), "arm_tube"),
        label_shape(bd.Pos(18, 0, 6) * bd.Box(4, 6, 6), "arm_tip"),
    ])
    return bd.Compound(children=[base, arm])


if __name__ == "__main__":
    grouped()
"""


class KinematicsBuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self._roots = IsolatedCadRoots(self, prefix="cadkin-")
        self._tempdir = self._roots.temporary_cad_directory(prefix="tmp-cadkin-")
        self.root = Path(self._tempdir.name)

    def tearDown(self) -> None:
        self._tempdir.cleanup()

    def _build(self, script: Path) -> int:
        from cadgen.catalog import StepImportOptions
        from cadgen.generation import generate_step_targets

        return generate_step_targets(
            [str(script)],
            step_options=StepImportOptions(),
            force=True,
            verbose=False,
        )

    def _descriptor(self, script: Path) -> dict:
        from cadgen.catalog import result_view_dir

        package = result_view_dir(script.with_suffix(".step"))
        return json.loads((package / "assembly.json").read_text())

    def _sidecar(self, script: Path) -> dict:
        from cadgen._internal.source_sidecar import read_source_sidecar

        return read_source_sidecar(script.with_suffix(".step")) or {}

    def _write(self, name: str, extra: str = "", kinematics_extra: str = "") -> Path:
        script = self.root / name
        script.write_text(
            HINGE_MODEL.format(extra=extra, kinematics_extra=kinematics_extra),
            encoding="utf-8",
        )
        return script

    def test_kinematics_and_animation_land_in_the_sidecar(self) -> None:
        script = self._write("hinge.py", extra=', animation="hinge.anim.js"')
        (self.root / "hinge.anim.js").write_text(ANIM_JS, encoding="utf-8")
        self.assertEqual(0, self._build(script))

        sidecar = self._sidecar(script)
        self.assertEqual(sidecar["schemaVersion"], 5)
        # The sidecar file carries the branded suffix.
        self.assertTrue((self.root / "hinge.step.json").is_file())

        block = sidecar["kinematics"]
        (mate,) = block["mates"]
        self.assertEqual(mate["name"], "swing")
        self.assertEqual(mate["kind"], "revolute")
        # Labels stay canonical; the literal axis is already numbers.
        self.assertEqual(mate["parent"], "#base")
        self.assertEqual(mate["child"], "#arm")
        self.assertEqual(mate["axis"], {"origin": [0.0, 0.0, 6.0], "dir": [0.0, 0.0, 1.0]})
        self.assertEqual(block["poses"], {"open": {"swing": 45.0}})

        # The animation module's TEXT is copied; no path to the source tree
        # appears anywhere in the sidecar.
        self.assertEqual(sidecar["animation"], {"clips": ANIM_JS})
        self.assertNotIn("hinge.anim.js", json.dumps(sidecar))

        # The descriptor stays STEP-pure: kinematics is sidecar-only.
        self.assertNotIn("kinematics", self._descriptor(script))

    def test_axis_selector_refs_resolve_to_world_numbers(self) -> None:
        script = self.root / "pivot.py"
        script.write_text(
            HINGE_MODEL.format(extra="", kinematics_extra="").replace(
                'cadgen.revolute("swing", parent="#base", child="#arm",\n'
                '                        origin=(0, 0, 6), direction=(0, 0, 1), limits=(0, 90)),',
                'cadgen.revolute("swing", parent="#base", child="#arm",\n'
                '                        axis="#arm.f1", limits=(0, 90)),',
            ),
            encoding="utf-8",
        )
        self.assertEqual(0, self._build(script))
        (mate,) = self._sidecar(script)["kinematics"]["mates"]
        axis = mate["axis"]
        self.assertNotIn("ref", axis)
        self.assertEqual(len(axis["origin"]), 3)
        self.assertEqual(len(axis["dir"]), 3)
        self.assertAlmostEqual(math.hypot(*axis["dir"]), 1.0, places=6)

    def test_a_mate_on_a_subassembly_resolves_to_the_group(self) -> None:
        # Subassemblies are not rendered parts, so they are absent from the flat
        # leaf index; they live in the descriptor's instance tree, which is the
        # namespace mates target. Without this the rocker-bogie shape of model
        # (a mate per GROUP) could not be declared at all.
        script = self.root / "grouped.py"
        script.write_text(GROUPED_MODEL, encoding="utf-8")
        self.assertEqual(0, self._build(script))

        (mate,) = self._sidecar(script)["kinematics"]["mates"]
        self.assertEqual(mate["parent"], "#base_group")
        self.assertEqual(mate["child"], "#arm_group")
        # The resolved ids ride the sidecar beside the labels, so the viewer
        # matches a whole subtree by id prefix rather than redoing topology.
        self.assertEqual(mate["parentId"], "o1.1")
        self.assertEqual(mate["childId"], "o1.2")

        # Both of the arm group's leaves sit under the mated occurrence.
        leaves = {o["id"] for o in self._descriptor(script)["occurrences"]}
        self.assertEqual({"o1.1.1", "o1.1.2", "o1.2.1", "o1.2.2"}, leaves)

    def test_an_unresolvable_mate_ref_fails_the_build(self) -> None:
        script = self.root / "broken.py"
        script.write_text(
            HINGE_MODEL.format(extra="", kinematics_extra="").replace('child="#arm"', 'child="#wrist"'),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "'#wrist' does not name an occurrence"):
            self._build(script)

    def test_a_missing_animation_module_fails_the_build(self) -> None:
        script = self._write("noanim.py", extra=', animation="nope.anim.js"')
        with self.assertRaisesRegex(FileNotFoundError, "animation module not found"):
            self._build(script)

    def test_at_bakes_the_artifact_and_rezeroes_the_sidecar(self) -> None:
        rest = self._write("rest.py")
        # The bake point lives INSIDE the kinematics dict: everything says
        # kinematics, so there is no pose= kwarg beside it to keep in step.
        posed = self._write("posed.py", kinematics_extra=', "at": "open"')
        self.assertEqual(0, self._build(rest))
        self.assertEqual(0, self._build(posed))

        def arm_transform(script: Path) -> list[float]:
            for occurrence in self._descriptor(script)["occurrences"]:
                if "arm" in str(occurrence.get("name", "")):
                    return [round(float(v), 6) for v in occurrence["transform"]]
            raise AssertionError("no arm occurrence")

        at_rest = arm_transform(rest)
        at_pose = arm_transform(posed)
        self.assertNotEqual(at_rest, at_pose)
        # 45 degrees about +Z through (0, 0, 6): the rotation block is exact.
        half = round(math.sqrt(0.5), 6)
        self.assertEqual(at_pose[0], half)
        self.assertEqual(round(at_pose[1] + half, 6), 0.0)

        block = self._sidecar(posed)["kinematics"]
        self.assertEqual(block["bakedPose"], {"swing": 45.0})
        # The artifact as written is q=0: limits shift, presets re-zero.
        self.assertEqual(block["mates"][0]["limits"], {"value": [-45.0, 45.0]})
        self.assertEqual(block["poses"], {"open": {"swing": 0.0}})

        # And the two STEP files genuinely differ: the pose is IN the bytes.
        posed_bytes = posed.with_suffix(".step").read_bytes()
        self.assertNotEqual(rest.with_suffix(".step").read_bytes(), posed_bytes)

        # Byte determinism: the same pose in produces the same artifact out.
        self.assertEqual(0, self._build(posed))
        self.assertEqual(posed_bytes, posed.with_suffix(".step").read_bytes())

    def test_the_root_exposes_no_pose_surface(self) -> None:
        import cadgen

        with self.assertRaises(AttributeError):
            cadgen.pose  # noqa: B018 - the attribute access IS the assertion


if __name__ == "__main__":
    unittest.main()


POSED_MESH_MODEL = """
import cadgen
from cadgen import label_shape, step, stl
from cadgen import build123d as bd

KINEMATICS = {
    "mates": [
        cadgen.revolute("swing", parent="#base", child="#arm",
                        origin=(0, 0, 6), direction=(0, 0, 1), limits=(0, 90)),
    ],
    "poses": {"open": {"swing": 45}},
}

@step(kind="assembly")
@stl(out="latch_rest.stl")
@stl(out="latch_open.stl", kinematics={**KINEMATICS, "at": "open"})
def latch():
    base = label_shape(bd.Box(20, 20, 4), "base")
    arm = label_shape(bd.Pos(10, 0, 6) * bd.Box(16, 4, 4), "arm")
    return bd.Compound(children=[base, arm])


if __name__ == "__main__":
    latch()
"""


class PosedMeshExportTests(unittest.TestCase):
    """A mesh declaration's OWN kinematics + "at" bake, independent of @step."""

    def setUp(self) -> None:
        self._roots = IsolatedCadRoots(self, prefix="cadkinmesh-")
        self._tempdir = self._roots.temporary_cad_directory(prefix="tmp-cadkinmesh-")
        self.root = Path(self._tempdir.name)

    def tearDown(self) -> None:
        self._tempdir.cleanup()

    def test_a_posed_stl_variant_differs_and_gates_on_its_pose(self) -> None:
        import os
        import subprocess
        import sys

        script = self.root / "latch.py"
        script.write_text(POSED_MESH_MODEL, encoding="utf-8")
        env = dict(os.environ)
        env.update({
            "CADGEN_DAEMON": "0",
            "CADGEN_COMPONENT_WORKERS": "1",
            "PYTHONPATH": str(Path(__file__).resolve().parents[4] / "packages/cadgen/src"),
        })
        first = subprocess.run(
            [sys.executable, str(script)], cwd=str(self.root), env=env,
            capture_output=True, text=True, timeout=600,
        )
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        rest = (self.root / "latch_rest.stl").read_bytes()
        posed = (self.root / "latch_open.stl").read_bytes()
        self.assertEqual(len(rest), len(posed), "same tessellation, different placement")
        self.assertNotEqual(rest, posed, "the pose must be IN the bytes")

        # The ledger keys on the pose too: a second run rewrites neither.
        second = subprocess.run(
            [sys.executable, str(script)], cwd=str(self.root), env=env,
            capture_output=True, text=True, timeout=600,
        )
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertNotIn("wrote STL", second.stderr)
