"""`cadgen step build IN OUT`: one document in, a NEW document out.

The verb re-emits an existing STEP through cadgen's own pipeline — OCCT read ->
content-keyed package -> the canonical XCAF writer — so OUT's bytes are
deterministic whichever kernel wrote IN, and optionally ANNOTATES it with
kinematics and animation that land in OUT's sidecar. That is the door for a
document with no model script (design/pose-animation-split.md, CLI/doors
follow-on).

What is pinned here is the contract a caller depends on: OUT is required and
never IN, the annotation resolves against real geometry, and freshness splits in
two — bytes key on the input hash alone, the annotation on its own
digest — which is what lets a kinematics-only edit refresh the sidecar without
re-emitting.
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.python.support.paths import add_repo_path
from tests.python.support.cad_test_roots import IsolatedCadRoots

add_repo_path("packages/cadgen/src")

MODEL = """
from cadgen import label_shape, step
from cadgen import build123d as bd


@step
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
        offline = mock.patch.dict(os.environ, {"CADGEN_DAEMON": "0"})
        offline.start()
        self.addCleanup(offline.stop)
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
            [str(script)],
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
        result = self._build(kinematics=json.dumps(KINEMATICS))
        self.assertTrue(result.ok)
        self.assertTrue(self.out.is_file())
        self.assertFalse(result.skipped)

        sidecar = self._sidecar()
        self.assertEqual(9, sidecar["schemaVersion"])
        # Declarations only: no source tie of any kind in the file
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
        # This build declares kinematics only.
        self.assertNotIn("animation", sidecar)

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
        self.assertEqual(before, self.out.read_bytes(), "bytes cannot change: same input")
        sidecar = self._sidecar()
        self.assertEqual({"value": [0.0, 120.0]}, sidecar["kinematics"]["mates"][0]["limits"])
        self.assertIn("wide", sidecar["kinematics"]["poses"])
        from cadgen.store.gate import stale

        self.assertFalse(stale(self.out).stale, "the rewritten sidecar hash must land in the record")

    def test_a_missing_or_corrupt_output_sidecar_is_rebuilt_not_reported_current(self) -> None:
        from cadgen._internal.source_sidecar import source_sidecar_path
        from cadgen.store.gate import stale

        self._build(kinematics=json.dumps(KINEMATICS))
        sidecar = source_sidecar_path(self.out)
        for damage in ("missing", "corrupt"):
            if damage == "missing":
                sidecar.unlink()
            else:
                sidecar.write_text('{"schemaVersion": 8, "documentHash": "wrong"}', encoding="utf-8")
            self.assertTrue(stale(self.out).stale)
            result = self._build(kinematics=json.dumps(KINEMATICS))
            self.assertFalse(result.skipped)
            self.assertEqual("swing", self._sidecar()["kinematics"]["mates"][0]["name"])
            self.assertFalse(stale(self.out).stale)

    def test_removing_the_last_annotation_removes_its_recorded_output(self) -> None:
        from cadgen._internal.source_sidecar import source_sidecar_path
        from cadgen.store.gate import stale
        from cadgen.store.records import read_record

        materials = {"definitions": {"paint": {"baseColor": "#336699"}},
                     "assignments": [{"targets": ["#arm"], "material": "paint"}]}
        self._build(kinematics=json.dumps(KINEMATICS), materials=materials, animation=ANIM_JS)
        before = self.out.read_bytes()
        materials["definitions"]["paint"]["baseColor"] = "#996633"
        with mock.patch("cadgen._internal.step_reemit._emit", side_effect=AssertionError("annotation edit emitted STEP")):
            updated = self._build(kinematics=json.dumps(KINEMATICS), materials=materials, animation=ANIM_JS.replace("demo", "swing"))
            self.assertTrue(updated.sidecar_only)
            self.assertEqual("#996633", self._sidecar()["appearance"]["materials"]["paint"]["baseColor"])
            self.assertIn("swing", self._sidecar()["animation"]["source"])
            result = self._build()
        self.assertEqual(before, self.out.read_bytes())
        sidecar = source_sidecar_path(self.out).resolve()
        self.assertTrue(result.sidecar_only)
        self.assertFalse(sidecar.exists())
        self.assertNotIn(str(sidecar), (read_record(self.out) or {}).get("outputs", {}))
        self.assertFalse(stale(self.out).stale)

    def test_an_unrecorded_output_sidecar_is_not_accepted_as_current(self) -> None:
        from cadgen._internal.source_sidecar import source_sidecar_path, write_source_sidecar

        self._build()
        sidecar = source_sidecar_path(self.out)
        write_source_sidecar(
            self.out,
            {"appearance": {"materials": {"finish": {"name": "Finish", "roughness": 0.2}}, "assignments": {"unexpected": "finish"}}},
        )
        self.assertTrue(sidecar.is_file())
        result = self._build()
        self.assertFalse(result.skipped)
        self.assertFalse(sidecar.exists())

    def test_a_kinematics_only_edit_preserves_output_mapped_appearance(self) -> None:
        from cadgen.catalog import artifact_file_hash, result_descriptor_for
        from cadgen._internal.source_sidecar import read_source_sidecar, source_sidecar_path, write_source_sidecar
        from cadgen.store.records import read_record, write_record

        input_leaf = (result_descriptor_for(self.vendor) or {})["occurrences"][0]["id"]
        material = {"name": "Finish", "roughness": 0.2, "metalness": 0.7, "opacity": 0.8}
        write_source_sidecar(
            self.vendor,
            {"appearance": {"materials": {"finish": material}, "assignments": {input_leaf: "finish"}}},
        )
        self._build(kinematics=json.dumps(KINEMATICS))

        # Model the legitimate case where re-emission changed product paths:
        # the output sidecar's appearance is already mapped to OUT's canonical
        # IDs, while inputAppearance in the record still gates on IN's block.
        output_leaves = [item["id"] for item in (result_descriptor_for(self.out) or {})["occurrences"]]
        output_leaf = next(item for item in output_leaves if item != input_leaf)
        current = read_source_sidecar(self.out) or {}
        write_source_sidecar(
            self.out,
            {
                "kinematics": current["kinematics"],
                "appearance": {"materials": {"finish": material}, "assignments": {output_leaf: "finish"}},
            },
        )
        record = read_record(self.out) or {}
        outputs = dict(record["outputs"])
        output_sidecar = source_sidecar_path(self.out).resolve()
        outputs[str(output_sidecar)] = {"sha256": artifact_file_hash(output_sidecar)}
        record["outputs"] = outputs
        record["intrinsicAppearance"] = {"materials": {"finish": material}, "assignments": {output_leaf: "finish"}}
        write_record(self.out, record)

        widened = json.loads(json.dumps(KINEMATICS))
        widened["mates"][0]["limits"] = [0, 120]
        result = self._build(kinematics=json.dumps(widened))
        self.assertTrue(result.sidecar_only)
        self.assertEqual(
            {"materials": {"finish": material}, "assignments": {output_leaf: "finish"}},
            (read_source_sidecar(self.out) or {})["appearance"],
        )

    def test_reemit_refuses_when_the_parsed_snapshot_is_not_the_hashed_input(self) -> None:
        self._build(kinematics=json.dumps(KINEMATICS))
        before = self.out.read_bytes()
        replacement = SimpleNamespace(step_hash="0" * 64)
        with mock.patch(
            "cadgen._internal.step_scene_package.load_step_scene_exact",
            return_value=replacement,
        ):
            with self.assertRaisesRegex(RuntimeError, "changed while it was being read"):
                self._build(kinematics=json.dumps(KINEMATICS), force=True)
        self.assertEqual(before, self.out.read_bytes())

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

    def test_animation_file_is_embedded_without_a_path_dependency(self) -> None:
        module = self.root / "source.js"
        module.write_text(ANIM_JS, encoding="utf-8")
        self._build(animation=str(module))
        self.assertEqual({"language": "javascript", "source": ANIM_JS}, self._sidecar()["animation"])
        module.unlink()
        self.assertEqual(ANIM_JS, self._sidecar()["animation"]["source"])


if __name__ == "__main__":
    unittest.main()
