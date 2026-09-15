"""A saved STEP's bytes own geometry; its sidecar owns intrinsic appearance."""

from __future__ import annotations

import json
import os
import shutil
import struct
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.tmp_root import generated_cad_directory


IDENTITY = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
RGBA = [0.2, 0.4, 0.6, 0.75]
ROUGH = {
    "name": "Rough finish",
    "baseColor": "#FF0000",
    "roughness": 0.1,
    "metalness": 0.2,
    "clearcoat": 0.3,
    "clearcoatRoughness": 0.4,
    "opacity": 0.5,
}
POLISHED = {
    "name": "Polished finish",
    "baseColor": "#0000FF",
    "roughness": 0.9,
    "metalness": 0.8,
    "clearcoat": 0.7,
    "clearcoatRoughness": 0.6,
    "opacity": 1.0,
}


def _model_source(material: dict[str, object]) -> str:
    return textwrap.dedent(
        f"""
        from cadgen import step
        from cadgen import build123d as bd

        @step(materials={{
            "definitions": {{"finish": {material!r}}},
            "assignments": [{{"targets": ["#box"], "material": "finish"}}],
        }})
        def box():
            shape = bd.Box(2, 3, 4)
            shape.label = "box"
            shape.color = bd.Color(0.2, 0.4, 0.6, 0.75)
            return shape

        if __name__ == "__main__":
            box()
        """
    ).lstrip()


def _materials(descriptor: dict) -> dict[str, dict[str, object]]:
    result = {}
    for occurrence in descriptor.get("occurrences") or []:
        if occurrence.get("material") is None:
            continue
        material = dict(occurrence["material"])
        if occurrence.get("materialName"):
            material["name"] = occurrence["materialName"]
        if occurrence.get("baseColor"):
            material["baseColor"] = occurrence["baseColor"]
        result[str(occurrence["id"])] = material
    return result


def _appearance_materials(appearance: dict) -> dict[str, dict[str, object]]:
    materials = appearance["materials"]
    return {
        occurrence_id: dict(materials[material_id])
        for occurrence_id, material_id in appearance["assignments"].items()
    }


def _glb_json(path: Path) -> dict:
    payload = path.read_bytes()
    if payload[:4] != b"glTF":
        raise AssertionError(f"{path} is not a GLB")
    json_length, chunk_type = struct.unpack_from("<II", payload, 12)
    if chunk_type != 0x4E4F534A:
        raise AssertionError(f"{path} has no leading JSON chunk")
    return json.loads(payload[20 : 20 + json_length].decode("utf-8"))


class SavedDocumentIdentityTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = generated_cad_directory(prefix="saved-document-identity-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self.store = self.root / "store"
        self._environment = mock.patch.dict(
            os.environ,
            {
                "CADGEN_CACHE_DIR": str(self.store),
                "CADGEN_COMPONENT_WORKERS": "1",
                "CADGEN_DAEMON": "0",
                "CADGEN_JOBS": "1",
            },
        )
        self._environment.start()
        self.addCleanup(self._environment.stop)
        from cadgen.store.closure import forget_model_files

        forget_model_files()
        self.addCleanup(forget_model_files)

    def _write_model(self, folder: str, material: dict[str, float]) -> tuple[Path, Path]:
        directory = self.root / folder
        directory.mkdir()
        script = directory / "box.py"
        script.write_text(_model_source(material), encoding="utf-8")
        return script, directory / "box.step"

    def _build(self, script: Path) -> None:
        from cadgen.generation import generate_step_targets

        self.assertEqual(0, generate_step_targets([str(script)], force=True, verbose=False))

    def test_same_step_bytes_share_one_canonical_tree_and_keep_independent_finishes(self) -> None:
        from cadgen._internal.doors import document_tree
        from cadgen._internal.source_sidecar import apply_appearance, read_source_sidecar
        from cadgen.store.index import model_ref
        from cadgen.store.records import read_record
        from cadgen.store.trees import flatten

        rough_script, rough_step = self._write_model("rough", ROUGH)
        polished_script, polished_step = self._write_model("polished", POLISHED)
        self._build(rough_script)
        self._build(polished_script)

        self.assertEqual(rough_step.read_bytes(), polished_step.read_bytes())
        rough_record = read_record(model_ref(rough_script, "box"))
        polished_record = read_record(model_ref(polished_script, "box"))
        self.assertIsNotNone(rough_record)
        self.assertIsNotNone(polished_record)
        self.assertNotEqual(
            rough_record["tree"], polished_record["tree"],
            "the authored model results retain their distinct intrinsic finishes",
        )
        self.assertEqual(rough_record["documentTree"], polished_record["documentTree"])
        document_tree_hash = rough_record["documentTree"]
        canonical_before = flatten(document_tree_hash)
        self.assertIsNotNone(canonical_before)
        self.assertFalse(_materials(canonical_before), "PBR annotations do not belong in the byte-derived tree")

        rough_sidecar = read_source_sidecar(rough_step)
        polished_sidecar = read_source_sidecar(polished_step)
        self.assertEqual(rough_sidecar["documentHash"], polished_sidecar["documentHash"])
        self.assertNotEqual(rough_sidecar["appearance"], polished_sidecar["appearance"])
        leaf_ids = {str(item["id"]) for item in canonical_before["occurrences"]}
        self.assertEqual(leaf_ids, set(rough_sidecar["appearance"]["assignments"]))
        self.assertEqual(leaf_ids, set(polished_sidecar["appearance"]["assignments"]))
        colors = [item["color"] for item in canonical_before["occurrences"]]
        self.assertTrue(colors)
        for color in colors:
            for actual, expected in zip(color, RGBA, strict=True):
                self.assertAlmostEqual(expected, actual, places=6)

        rough_authored = flatten(rough_record["tree"])
        polished_authored = flatten(polished_record["tree"])
        self.assertEqual(
            {frozenset(value.items()) for value in _appearance_materials(
                rough_authored["appearance"]
            ).values()},
            {frozenset(ROUGH.items())},
        )
        self.assertEqual(
            {frozenset(value.items()) for value in _appearance_materials(
                polished_authored["appearance"]
            ).values()},
            {frozenset(POLISHED.items())},
        )

        # The file pair must stand alone. Remove every source and every cached
        # object/index; the document door can reconstruct only from STEP bytes.
        rough_script.unlink()
        polished_script.unlink()
        shutil.rmtree(self.store)
        self.assertFalse(rough_script.exists())
        self.assertFalse(polished_script.exists())

        rebuilt_rough_tree = document_tree(rough_step)
        rebuilt_polished_tree = document_tree(polished_step)
        self.assertEqual(document_tree_hash, rebuilt_rough_tree)
        self.assertEqual(rebuilt_rough_tree, rebuilt_polished_tree)
        canonical_after = flatten(rebuilt_rough_tree)
        self.assertEqual(canonical_before, canonical_after)

        rough_recovered = apply_appearance(canonical_after, read_source_sidecar(rough_step)["appearance"])
        polished_recovered = apply_appearance(canonical_after, read_source_sidecar(polished_step)["appearance"])
        self.assertEqual(
            {frozenset(value.items()) for value in _materials(rough_recovered).values()},
            {frozenset(ROUGH.items())},
        )
        self.assertEqual(
            {frozenset(value.items()) for value in _materials(polished_recovered).values()},
            {frozenset(POLISHED.items())},
        )
        rough_recovered["occurrences"][0]["material"]["roughness"] = 0.55
        self.assertEqual(0.9, polished_recovered["occurrences"][0]["material"]["roughness"])
        self.assertFalse(_materials(canonical_after))

        # The bare document door reads only the reconstructed document tree
        # plus each adjacent sidecar. Same bytes share tessellation while the
        # appearance digest keeps finished mesh artifacts distinct.
        from cadgen._internal.mesh_export import mesh_variant_key
        from cadgen._internal.source_sidecar import appearance_digest, write_source_sidecar
        from cadgen.store.index import read_entry
        from cadgen.step_export_target import export_cad_target

        rough_glb = rough_step.with_suffix(".glb")
        polished_glb = polished_step.with_suffix(".glb")
        rough_export = export_cad_target(rough_step, [("glb", rough_glb)], repo_root=self.root)
        polished_export = export_cad_target(polished_step, [("glb", polished_glb)], repo_root=self.root)
        self.assertFalse(rough_export["files"][0]["skipped"])
        self.assertFalse(polished_export["files"][0]["skipped"])
        rough_bytes = rough_glb.read_bytes()
        polished_bytes = polished_glb.read_bytes()
        self.assertNotEqual(rough_bytes, polished_bytes)

        def assert_finish(path: Path, expected: dict[str, float]) -> None:
            (material,) = _glb_json(path)["materials"]
            pbr = material["pbrMetallicRoughness"]
            self.assertEqual(expected["name"], material["name"])
            expected_rgb = [1, 0, 0] if expected["baseColor"] == "#FF0000" else [0, 0, 1]
            self.assertEqual(expected_rgb, pbr["baseColorFactor"][:3])
            self.assertEqual(expected["roughness"], pbr["roughnessFactor"])
            self.assertEqual(expected["metalness"], pbr["metallicFactor"])
            effective_opacity = expected["opacity"] * RGBA[3]
            self.assertEqual(effective_opacity, pbr["baseColorFactor"][3])
            if effective_opacity < 1:
                self.assertEqual("BLEND", material["alphaMode"])
            else:
                self.assertNotIn("alphaMode", material)
            clearcoat = material["extensions"]["KHR_materials_clearcoat"]
            self.assertEqual(expected["clearcoat"], clearcoat["clearcoatFactor"])
            self.assertEqual(expected["clearcoatRoughness"], clearcoat["clearcoatRoughnessFactor"])

        assert_finish(rough_glb, ROUGH)
        assert_finish(polished_glb, POLISHED)
        rough_mtime = rough_glb.stat().st_mtime_ns
        repeated = export_cad_target(rough_step, [("glb", rough_glb)], repo_root=self.root)
        self.assertTrue(repeated["files"][0]["skipped"])
        self.assertEqual(rough_mtime, rough_glb.stat().st_mtime_ns)

        rough_key = appearance_digest(read_source_sidecar(rough_step)["appearance"])
        polished_key = appearance_digest(read_source_sidecar(polished_step)["appearance"])
        document_entry = read_entry("document", rough_sidecar["documentHash"])
        variants = set((document_entry.get("meshes") or {}))
        self.assertIn(mesh_variant_key("glb", None, None, appearance_key=rough_key), variants)
        self.assertIn(mesh_variant_key("glb", None, None, appearance_key=polished_key), variants)
        self.assertNotEqual(rough_key, polished_key)

        # An annotation-only edit leaves STEP bytes and the document tree
        # untouched, but must miss the old output's appearance-sensitive gate.
        write_source_sidecar(rough_step, {"appearance": {
            "materials": {"finish": POLISHED},
            "assignments": {occurrence_id: "finish" for occurrence_id in leaf_ids},
        }})
        edited = export_cad_target(rough_step, [("glb", rough_glb)], repo_root=self.root)
        self.assertFalse(edited["files"][0]["skipped"])
        self.assertNotEqual(rough_bytes, rough_glb.read_bytes())
        self.assertEqual(polished_bytes, rough_glb.read_bytes())
        self.assertEqual(document_tree_hash, document_tree(rough_step))
        assert_finish(rough_glb, POLISHED)

    def test_parent_result_and_saved_sidecar_preserve_an_exact_pinned_child_finish(self) -> None:
        from cadgen._internal.source_sidecar import read_source_sidecar
        from cadgen.store.records import read_record
        from cadgen.store.trees import flatten

        child = self.root / "child.py"
        child.write_text(
            _model_source(ROUGH).replace("def box():", "def child():").replace("    box()\n", "    child()\n"),
            encoding="utf-8",
        )
        parent = self.root / "parent.py"
        parent.write_text(
            textwrap.dedent(
                """
                from cadgen import step
                from cadgen import build123d as bd
                from child import child

                @step(materials={{
                    "definitions": {{"finish": {POLISHED!r}}},
                    "assignments": [
                        {{"targets": ["#moved_polished_child"], "material": "finish"}},
                    ],
                }})
                def parent():
                    pinned = child()
                    pinned.label = "pinned_child"
                    modified = child()
                    moved = bd.Pos(5, 0, 0) * modified
                    moved.label = "moved_polished_child"
                    return bd.Compound(children=[pinned, moved], label="parent")

                if __name__ == "__main__":
                    parent()
                """
            ).lstrip().format(ROUGH=ROUGH, POLISHED=POLISHED),
            encoding="utf-8",
        )
        self._build(parent)

        child_record = read_record(child)
        parent_record = read_record(parent)
        self.assertTrue(parent_record["children"])
        self.assertEqual(
            {(entry["model"], entry["tree"]) for entry in parent_record["children"]},
            {(child_record["model"], child_record["tree"])},
        )
        parent_result = flatten(parent_record["tree"])
        self.assertEqual(
            {frozenset(value.items()) for value in _appearance_materials(
                parent_result["appearance"]
            ).values()},
            {frozenset(ROUGH.items()), frozenset(POLISHED.items())},
            parent_result,
        )
        parent_sidecar = read_source_sidecar(parent.with_suffix(".step"))
        self.assertEqual(
            {frozenset(value.items()) for value in _appearance_materials(parent_sidecar["appearance"]).values()},
            {frozenset(ROUGH.items()), frozenset(POLISHED.items())},
        )

        # A later child result cannot rewrite the exact tree pinned by parent.
        child.write_text(
            _model_source(POLISHED).replace("def box():", "def child():").replace("    box()\n", "    child()\n"),
            encoding="utf-8",
        )
        self._build(child)
        self.assertNotEqual(child_record["tree"], read_record(child)["tree"])
        pinned_again = flatten(read_record(parent)["tree"])
        self.assertEqual(
            {frozenset(value.items()) for value in _appearance_materials(
                pinned_again["appearance"]
            ).values()},
            {frozenset(ROUGH.items()), frozenset(POLISHED.items())},
        )
        self.assertEqual(
            {frozenset(value.items()) for value in _appearance_materials(
                read_source_sidecar(parent.with_suffix(".step"))["appearance"]
            ).values()},
            {frozenset(ROUGH.items()), frozenset(POLISHED.items())},
        )

    def test_kinematics_remap_requires_an_exact_document_subtree(self) -> None:
        from cadgen._internal.kinematics_resolve import remap_document_kinematics
        from cadgen.store.trees import put_tree

        tree_hash = put_tree(
            {
                "label": "document",
                "entryKind": "assembly",
                "units": "mm",
                "components": {"c": {"contentHash": "content", "brep": "object", "surf": "object"}},
                "occurrences": [
                    {"id": "o1.1.1", "name": "left", "component": "c", "transform": IDENTITY},
                    {"id": "o1.1.2", "name": "right", "component": "c", "transform": IDENTITY},
                    {"id": "o1.2.1.1", "name": "wrapped", "component": "c", "transform": IDENTITY},
                ],
                "links": [],
                "assembly": {
                    "root": {
                        "id": "o1",
                        "name": "document",
                        "nodeType": "assembly",
                        "leafPartIds": ["o1.1.1", "o1.1.2", "o1.2.1.1"],
                        "children": [
                            {
                                "id": "o1.1",
                                "name": "pair",
                                "nodeType": "subassembly",
                                "leafPartIds": ["o1.1.1", "o1.1.2"],
                                "children": [
                                    {"id": "o1.1.1", "name": "left", "nodeType": "part", "leafPartIds": ["o1.1.1"], "children": []},
                                    {"id": "o1.1.2", "name": "right", "nodeType": "part", "leafPartIds": ["o1.1.2"], "children": []},
                                ],
                            },
                            {
                                "id": "o1.2",
                                "name": "outer_wrapper",
                                "nodeType": "subassembly",
                                "leafPartIds": ["o1.2.1.1"],
                                "children": [{
                                    "id": "o1.2.1",
                                    "name": "inner_wrapper",
                                    "nodeType": "subassembly",
                                    "leafPartIds": ["o1.2.1.1"],
                                    "children": [{"id": "o1.2.1.1", "name": "wrapped", "nodeType": "part", "leafPartIds": ["o1.2.1.1"], "children": []}],
                                }],
                            },
                        ],
                    }
                },
            }
        )
        block = {
            "mates": [{"name": "join", "parentId": "authored_pair", "childId": "authored_wrapper"}]
        }
        occurrence_map = {
            "authored_pair": ["o1.1.1", "o1.1.2"],
            "authored_wrapper": ["o1.2.1.1"],
            "crossing": ["o1.1.1", "o1.2.1.1"],
        }
        node_map = {
            "authored_pair": "o1.1",
            "authored_wrapper": "o1.2",
            "crossing": "o1",
        }

        remapped = remap_document_kinematics(block, occurrence_map, node_map, tree_hash)
        self.assertEqual("o1.1", remapped["mates"][0]["parentId"])
        self.assertEqual("o1.2", remapped["mates"][0]["childId"])
        self.assertEqual("authored_pair", block["mates"][0]["parentId"])

        missing = {"mates": [{"name": "missing", "parentId": "absent", "childId": "authored_wrapper"}]}
        with self.assertRaisesRegex(ValueError, "parentId absent has no exact document subtree"):
            remap_document_kinematics(missing, occurrence_map, node_map, tree_hash)
        non_subtree = {"mates": [{"name": "cross", "parentId": "crossing", "childId": "authored_wrapper"}]}
        with self.assertRaisesRegex(ValueError, "parentId crossing document subtree does not match its exact leaves"):
            remap_document_kinematics(non_subtree, occurrence_map, node_map, tree_hash)


if __name__ == "__main__":
    unittest.main()
