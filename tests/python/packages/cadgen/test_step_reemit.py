"""`cadgen step build IN OUT`: one document in, a NEW document out.

The verb re-emits an existing STEP through cadgen's own pipeline — OCCT read ->
content-keyed package -> the canonical XCAF writer — so OUT's bytes are
deterministic whichever kernel wrote IN, and optionally ANNOTATES it with
kinematics and animation that land in OUT's sidecar. That is the door for a
document with no model script (design/pose-animation-split.md, CLI/doors
follow-on).

What is pinned here is the contract a caller depends on: OUT is required and
never IN, the annotation resolves against real geometry, and freshness splits in
two — bytes key on the input hash and the bake point, the annotation on its own
digest — which is what lets a kinematics-only edit refresh the sidecar without
re-emitting.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path
from tests.python.support.cad_test_roots import IsolatedCadRoots

add_repo_path("packages/cadgen/src")

MODEL = """
from cadgen import label_shape, step
from cadgen import build123d as bd


@step(kind="assembly")
def hinge():
    base = label_shape(bd.Box(20, 20, 4), "base")
    arm = label_shape(bd.Pos(10, 0, 6) * bd.Box(16, 4, 4), "arm")
    return bd.Compound(children=[base, arm])


if __name__ == "__main__":
    hinge()
"""

KINEMATICS = {
    "mates": [
        {
            "name": "swing",
            "kind": "revolute",
            "parent": "#base",
            "child": "#arm",
            "axis": {"origin": [0, 0, 6], "dir": [0, 0, 1]},
            "limits": [0, 90],
        }
    ],
    "poses": {"open": {"swing": 45}},
}

ANIM_JS = "export const clips = { demo: { duration: 2, update(t, m) {} } };\n"


class StepReemitTests(unittest.TestCase):
    def setUp(self) -> None:
        self._roots = IsolatedCadRoots(self, prefix="cadreemit-")
        self._tempdir = self._roots.temporary_cad_directory(prefix="tmp-cadreemit-")
        self.root = Path(self._tempdir.name)
        # A real document to re-emit, produced the way every document is: by
        # running a model script.
        script = self.root / "hinge.py"
        script.write_text(MODEL, encoding="utf-8")
        self._run_script(script)
        self.vendor = self.root / "vendor.step"
        self.vendor.write_bytes((self.root / "hinge.step").read_bytes())
        self.out = self.root / "annotated.step"

    def tearDown(self) -> None:
        self._tempdir.cleanup()

    def _run_script(self, script: Path) -> None:
        from cadgen.catalog import StepImportOptions
        from cadgen.generation import generate_step_targets

        code = generate_step_targets(
            [f"{script}={script.with_suffix('.step').as_posix()}"],
            step_options=StepImportOptions(),
            force=True,
            verbose=False,
        )
        self.assertEqual(0, code)

    def _build(self, **kwargs):
        from cadgen import step as step_namespace

        return step_namespace.build(self.vendor, self.out, **kwargs)

    def _sidecar(self) -> dict:
        from cadgen._internal.source_sidecar import read_source_sidecar

        return read_source_sidecar(self.out) or {}

    def test_out_is_required_and_never_the_input(self) -> None:
        from cadgen import step as step_namespace

        with self.assertRaisesRegex(ValueError, "OUT is the input document"):
            step_namespace.build(self.vendor, self.vendor)

    def test_a_model_script_is_refused_by_naming_the_run(self) -> None:
        from cadgen import step as step_namespace

        with self.assertRaisesRegex(ValueError, "run it: python"):
            step_namespace.build(self.root / "hinge.py", self.out)

    def test_the_annotation_lands_in_the_outputs_sidecar(self) -> None:
        animation = self.root / "hinge.anim.js"
        animation.write_text(ANIM_JS, encoding="utf-8")
        result = self._build(kinematics=json.dumps(KINEMATICS), animation=animation)
        self.assertTrue(result.ok)
        self.assertTrue(self.out.is_file())
        self.assertFalse(result.skipped)

        sidecar = self._sidecar()
        self.assertEqual(5, sidecar["schemaVersion"])
        # Declarations only (schema 5): no source tie of any kind in the file
        # beside the artifact. The freshness identity — sourceKind "step", the
        # INPUT's content hash — lives in the provenance RECORD.
        self.assertNotIn("sourceKind", sidecar)
        self.assertNotIn("meshExports", sidecar)
        self.assertNotIn("sourcePath", sidecar)
        from cadgen._internal.source_sidecar import read_source_provenance

        provenance = read_source_provenance(self.out) or {}
        self.assertEqual("step", provenance.get("sourceKind"))

        (mate,) = sidecar["kinematics"]["mates"]
        # Refs resolved against the geometry we just wrote, not just echoed.
        self.assertEqual("o1.1", mate["parentId"])
        self.assertEqual("o1.2", mate["childId"])
        self.assertEqual({"value": [0.0, 90.0]}, mate["limits"])
        # The animation module's TEXT is copied; no path survives.
        self.assertEqual({"clips": ANIM_JS}, sidecar["animation"])
        self.assertNotIn("hinge.anim.js", json.dumps(sidecar))

    def test_the_output_is_ours_and_byte_deterministic(self) -> None:
        self._build(kinematics=json.dumps(KINEMATICS))
        first = self.out.read_bytes()
        self.assertTrue(first.startswith(b"ISO-10303-21"))
        self._build(kinematics=json.dumps(KINEMATICS), force=True)
        self.assertEqual(first, self.out.read_bytes())

    def test_rerunning_is_a_no_op(self) -> None:
        self._build(kinematics=json.dumps(KINEMATICS))
        before = self.out.read_bytes()
        again = self._build(kinematics=json.dumps(KINEMATICS))
        self.assertTrue(again.skipped)
        self.assertFalse(again.sidecar_only)
        self.assertEqual(before, self.out.read_bytes())

    def test_a_kinematics_only_edit_refreshes_the_sidecar_and_nothing_else(self) -> None:
        self._build(kinematics=json.dumps(KINEMATICS))
        before = self.out.read_bytes()

        widened = json.loads(json.dumps(KINEMATICS))
        widened["mates"][0]["limits"] = [0, 120]
        widened["poses"]["wide"] = {"swing": 100}
        result = self._build(kinematics=json.dumps(widened))

        self.assertTrue(result.sidecar_only)
        self.assertEqual(before, self.out.read_bytes(), "bytes cannot change: no bake, same input")
        sidecar = self._sidecar()
        self.assertEqual({"value": [0.0, 120.0]}, sidecar["kinematics"]["mates"][0]["limits"])
        self.assertIn("wide", sidecar["kinematics"]["poses"])

    def test_an_at_bake_point_moves_the_bytes(self) -> None:
        self._build(kinematics=json.dumps(KINEMATICS))
        at_rest = self.out.read_bytes()
        baked = json.loads(json.dumps(KINEMATICS))
        baked["at"] = "open"
        result = self._build(kinematics=json.dumps(baked))
        self.assertFalse(result.skipped)
        self.assertFalse(result.sidecar_only)
        self.assertNotEqual(at_rest, self.out.read_bytes(), "the bake is IN the bytes")
        # The artifact as written is its own q=0.
        self.assertEqual({"swing": 45.0}, self._sidecar()["kinematics"]["bakedPose"])

    def test_the_json_and_python_kinematics_spellings_agree(self) -> None:
        import cadgen

        self._build(kinematics=json.dumps(KINEMATICS))
        from_json = self._sidecar()["kinematics"]

        self.out.unlink()
        from cadgen._internal.source_sidecar import remove_source_sidecar

        remove_source_sidecar(self.out)
        self._build(
            kinematics={
                "mates": [
                    cadgen.revolute("swing", parent="#base", child="#arm",
                                    origin=(0, 0, 6), direction=(0, 0, 1), limits=(0, 90))
                ],
                "poses": {"open": {"swing": 45}},
            }
        )
        self.assertEqual(from_json, self._sidecar()["kinematics"])

    def test_a_kinematics_file_path_is_accepted(self) -> None:
        spec = self.root / "hinge.kinematics.json"
        spec.write_text(json.dumps(KINEMATICS), encoding="utf-8")
        self._build(kinematics=str(spec))
        self.assertEqual("swing", self._sidecar()["kinematics"]["mates"][0]["name"])

    def test_a_missing_animation_module_fails_loudly(self) -> None:
        with self.assertRaisesRegex(ValueError, "--animation module not found"):
            self._build(animation=self.root / "nope.anim.js")


if __name__ == "__main__":
    unittest.main()
