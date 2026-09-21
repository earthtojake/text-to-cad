"""Named material authoring, inheritance, and schema-9 artifact binding."""

from __future__ import annotations

import hashlib
import os
import unittest
from pathlib import Path

from tests.python.support.cad_test_roots import IsolatedCadRoots
from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory

add_repo_path("packages/cadgen/src")

from cadgen._internal.source_sidecar import (  # noqa: E402
    SidecarAppearanceError,
    apply_appearance,
    normalize_animation,
    normalize_materials,
    read_source_sidecar,
    resolve_materials,
    source_sidecar_path,
    write_source_sidecar,
)


class MaterialDeclarationTests(unittest.TestCase):
    def test_annotation_refresh_fingerprint_is_literal_and_conservative(self) -> None:
        from cadgen._internal.annotation_refresh import _COMPUTED, _source_parts

        exclusive = b"""
from cadgen import step
MATERIALS = {"definitions": {"paint": {}}, "assignments": []}
@step(materials=MATERIALS)
def model():
    return make_box(1)
"""
        parts = _source_parts(exclusive, "model")
        self.assertIsNotNone(parts)
        self.assertEqual("paint", next(iter(parts[1]["materials"]["definitions"])))

        shared = exclusive.replace(b"    return make_box(1)", b"    use(MATERIALS)\n    return make_box(1)")
        mutated = exclusive.replace(
            b"@step(materials=MATERIALS)",
            b'MATERIALS["assignments"].append({"targets": ["#body"], "material": "paint"})\n'
            b"@step(materials=MATERIALS)",
        )
        computed = exclusive.replace(b"materials=MATERIALS", b"materials=make_materials()")
        self.assertIsNone(_source_parts(shared, "model"))
        self.assertIsNone(_source_parts(mutated, "model"))
        computed_parts = _source_parts(computed, "model")
        self.assertIsNotNone(computed_parts)
        self.assertIs(_COMPUTED, computed_parts[1]["materials"])
        changed_computed = computed.replace(b"make_materials()", b"make_other_materials()")
        self.assertNotEqual(computed_parts[0], _source_parts(changed_computed, "model")[0])

        geometry_edit = exclusive.replace(b"make_box(1)", b"make_box(2)")
        edited_parts = _source_parts(geometry_edit, "model")
        self.assertIsNotNone(edited_parts)
        self.assertNotEqual(parts[0], edited_parts[0])
        self.assertEqual(parts[1], edited_parts[1])

    def test_step_declaration_carries_materials_and_animation_without_running_model(self) -> None:
        from cadgen import step

        @step(
            materials={"definitions": {"paint": {"baseColor": "#112233"}}, "assignments": []},
            animation="export const clips = {};",
        )
        def declared_material_model():
            return None

        definition = declared_material_model.__cadgen_model__
        self.assertEqual("paint", definition.materials["definitions"]["paint"]["name"])
        self.assertEqual([], definition.materials["assignments"])
        self.assertEqual("javascript", definition.animation["language"])

    def test_declaration_is_closed_owned_and_strict(self) -> None:
        source = {
            "definitions": {
                "steel": {"name": "Ground steel", "baseColor": "#a0B1c2", "roughness": 0.2},
            },
            "assignments": [{"targets": ["#shaft", "#gearbox"], "material": "steel"}],
        }
        normalized = normalize_materials(source, where="@step materials=")
        self.assertEqual("#A0B1C2", normalized["definitions"]["steel"]["baseColor"])
        self.assertEqual(0.2, normalized["definitions"]["steel"]["roughness"])
        normalized["definitions"]["steel"]["roughness"] = 0.9
        self.assertEqual(0.2, source["definitions"]["steel"]["roughness"])
        unassigned = resolve_materials(
            {"occurrences": [], "assembly": {"root": {"id": "o1", "children": []}}},
            {"definitions": {"paint": {"name": "Paint"}}, "assignments": []},
        )
        self.assertEqual({"paint": {"name": "Paint"}}, unassigned["materials"])
        self.assertEqual({}, unassigned["assignments"])

        invalid = (
            {"definitions": {}, "assignments": []},
            {"definitions": {"x": {"texture": "x.png"}}, "assignments": [{"targets": ["#x"], "material": "x"}]},
            {"definitions": {"x": {"roughness": True}}, "assignments": [{"targets": ["#x"], "material": "x"}]},
            {"definitions": {"x": {"baseColor": "red"}}, "assignments": [{"targets": ["#x"], "material": "x"}]},
            {"definitions": {"x": {}}, "assignments": [{"targets": ["x"], "material": "x"}]},
            {"definitions": {"x": {}}, "assignments": [{"targets": ["#x"], "material": "missing"}]},
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(SidecarAppearanceError):
                normalize_materials(value, where="@step materials=")

    def test_groups_expand_to_leaves_and_local_assignments_override_inherited(self) -> None:
        descriptor = {
            "occurrences": [
                {"id": "o1.1.1", "component": "a"},
                {"id": "o1.1.2", "component": "b"},
                {"id": "o1.2", "component": "c"},
            ],
            "assembly": {"root": {"id": "o1", "name": "root", "children": [
                {"id": "o1.1", "name": "gearbox", "children": [
                    {"id": "o1.1.1", "name": "shaft", "children": []},
                    {"id": "o1.1.2", "name": "bearing", "children": []},
                ]},
                {"id": "o1.2", "name": "cover", "children": []},
            ]}},
        }
        inherited = {
            "materials": {"steel": {"name": "Inherited steel", "roughness": 0.8}},
            "assignments": {"o1.1.1": "steel", "o1.2": "steel"},
        }
        declaration = {
            "definitions": {"steel": {"name": "Local steel", "roughness": 0.15}},
            "assignments": [{"targets": ["#gearbox"], "material": "steel"}],
        }
        resolved = resolve_materials(descriptor, declaration, inherited=inherited)
        local_id = resolved["assignments"]["o1.1.1"]
        self.assertEqual(local_id, resolved["assignments"]["o1.1.2"])
        self.assertNotEqual("steel", local_id)
        self.assertEqual("steel", resolved["assignments"]["o1.2"])
        self.assertEqual("Local steel", resolved["materials"][local_id]["name"])

        applied = apply_appearance(descriptor, resolved)
        by_id = {row["id"]: row for row in applied["occurrences"]}
        self.assertEqual("Local steel", by_id["o1.1.2"]["materialName"])
        with self.assertRaisesRegex(SidecarAppearanceError, "does not name a part or group"):
            resolve_materials(descriptor, {
                "definitions": {"x": {}},
                "assignments": [{"targets": ["#missing"], "material": "x"}],
            })

    def test_schema_nine_binds_named_appearance_and_animation_to_step_bytes(self) -> None:
        roots = IsolatedCadRoots(self, prefix="material-sidecar-")
        temp = roots.temporary_cad_directory(prefix="material-sidecar-")
        self.addCleanup(temp.cleanup)
        step = Path(temp.name) / "part.step"
        step.write_bytes(b"ISO-10303-21;\nEND-ISO-10303-21;\n")
        appearance = {
            "materials": {"paint": {"name": "Blue paint", "baseColor": "#204080"}},
            "assignments": {"o1": "paint"},
        }
        animation = normalize_animation("export const clips = {};", where="@step animation=")
        write_source_sidecar(step, {"appearance": appearance, "animation": animation})
        payload = read_source_sidecar(step)
        self.assertEqual(9, payload["schemaVersion"])
        self.assertEqual(hashlib.sha256(step.read_bytes()).hexdigest(), payload["documentHash"])
        self.assertEqual(appearance, payload["appearance"])
        self.assertEqual(animation, payload["animation"])
        step.write_bytes(step.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "does not match"):
            read_source_sidecar(step)
        self.assertTrue(source_sidecar_path(step).is_file())

    def test_intrinsic_appearance_changes_tree_identity_and_inherits_into_parent(self) -> None:
        import build123d as bd
        from unittest import mock

        from cadgen.store.build import build_tree_from_compound
        from cadgen.store.materialize import materialize
        from cadgen.store.trees import flatten

        temp = generated_cad_directory(prefix="material-tree-")
        self.addCleanup(temp.cleanup)
        with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(Path(temp.name) / "store")}):
            def declaration(roughness: float) -> dict:
                return {
                    "definitions": {"steel": {"name": "Ground steel", "roughness": roughness}},
                    "assignments": [{"targets": ["#o1"], "material": "steel"}],
                }

            child_a, tree_a, stats_a = build_tree_from_compound(
                bd.Box(2, 3, 4), root_name="child", materials=declaration(0.2)
            )
            child_b, tree_b, stats_b = build_tree_from_compound(
                bd.Box(2, 3, 4), root_name="child", materials=declaration(0.8)
            )
            self.assertEqual(tree_a["components"], tree_b["components"])
            self.assertNotEqual(child_a, child_b)
            self.assertEqual(stats_a["unannotatedTree"], stats_b["unannotatedTree"])

            placed_a = materialize(child_a)
            placed_a.label = "left_child"
            parent_a, _, _ = build_tree_from_compound(
                bd.Compound(children=[placed_a]), root_name="parent"
            )
            placed_b = materialize(child_b)
            placed_b.label = "left_child"
            parent_b, _, _ = build_tree_from_compound(
                bd.Compound(children=[placed_b]), root_name="parent"
            )
            self.assertNotEqual(parent_a, parent_b)
            inherited = flatten(parent_b)["appearance"]
            self.assertEqual({"Ground steel"}, {
                material["name"] for material in inherited["materials"].values()
            })
            self.assertEqual({0.8}, {
                material["roughness"] for material in inherited["materials"].values()
            })

    def test_dynamic_cad_material_fails_with_migration_hint(self) -> None:
        from cadgen._internal.component_package import _occurrence_material

        class Shape:
            pass

        shape = Shape()
        shape.cad_material = {"roughness": 0.2}
        with self.assertRaisesRegex(ValueError, "@step\\(materials="):
            _occurrence_material(shape)

    def test_model_build_writes_resolved_unified_sidecar_and_refresh_baseline(self) -> None:
        roots = IsolatedCadRoots(self, prefix="material-build-")
        temp = roots.temporary_cad_directory(prefix="material-build-")
        self.addCleanup(temp.cleanup)
        script = Path(temp.name) / "colored.py"
        script.write_text(
            """
import cadgen
from cadgen import build123d as bd
from cadgen import label_shape, step

def _computed_kinematics():
    return {"mates": [cadgen.fastened("fixed", parent="#anchor", child="#body")]}

@step(
    materials={
        "definitions": {"paint": {"name": "Blue paint", "baseColor": "#112233", "roughness": .3}},
        "assignments": [{"targets": ["#body"], "material": "paint"}],
    },
    animation="export const clips = {};",
    kinematics=_computed_kinematics(),
)
def colored():
    anchor = label_shape(bd.Pos(-3, 0, 0) * bd.Box(1, 1, 1), "anchor")
    body = label_shape(bd.Box(2, 3, 4), "body")
    return bd.Compound(children=[anchor, body])

if __name__ == "__main__":
    colored()
""",
            encoding="utf-8",
        )
        from cadgen.catalog import StepImportOptions
        from cadgen.generation import generate_step_targets
        from cadgen.store.index import model_ref
        from cadgen.store.records import read_record

        self.assertEqual(0, generate_step_targets(
            [str(script)], step_options=StepImportOptions(), force=True, verbose=False
        ))
        sidecar = read_source_sidecar(script.with_suffix(".step"))
        self.assertEqual("javascript", sidecar["animation"]["language"])
        self.assertEqual("fixed", sidecar["kinematics"]["mates"][0]["name"])
        kinematics_before = sidecar["kinematics"]
        self.assertEqual("Blue paint", next(iter(sidecar["appearance"]["materials"].values()))["name"])
        self.assertTrue(sidecar["appearance"]["assignments"])
        record = read_record(model_ref(script, "colored"))
        self.assertTrue(record["unannotatedTree"])
        self.assertTrue(record["geometryClosure"])
        self.assertTrue(record["documentOccurrenceMap"])
        self.assertTrue(record["documentNodeMap"])
        self.assertEqual("Blue paint", record["materials"]["definitions"]["paint"]["name"])
        self.assertEqual("javascript", record["animation"]["language"])
        self.assertEqual(kinematics_before, record["kinematics"])

        step_before = script.with_suffix(".step").read_bytes()
        tree_before = record["tree"]
        baseline_before = record["unannotatedTree"]
        edited = script.read_text(encoding="utf-8").replace(
            "\"baseColor\": \"#112233\", \"roughness\": .3",
            "\"baseColor\": \"#445566\", \"roughness\": .7",
        ).replace(
            "export const clips = {};",
            "export const clips = { refreshed: {} };",
        )
        script.write_text(edited, encoding="utf-8")
        from unittest import mock
        with mock.patch(
            "cadgen._internal.generation.run_script_generator",
            side_effect=AssertionError("annotation-only refresh ran model geometry"),
        ):
            self.assertEqual(0, generate_step_targets(
                [str(script)], step_options=StepImportOptions(), force=False, verbose=False
            ))
        refreshed = read_record(model_ref(script, "colored"))
        self.assertEqual(step_before, script.with_suffix(".step").read_bytes())
        self.assertNotEqual(tree_before, refreshed["tree"])
        self.assertEqual(baseline_before, refreshed["unannotatedTree"])
        refreshed_sidecar = read_source_sidecar(script.with_suffix(".step"))
        material = next(iter(refreshed_sidecar["appearance"]["materials"].values()))
        self.assertEqual("#445566", material["baseColor"])
        self.assertEqual(0.7, material["roughness"])
        self.assertIn("refreshed", refreshed_sidecar["animation"]["source"])
        self.assertEqual(kinematics_before, refreshed_sidecar["kinematics"])


if __name__ == "__main__":
    unittest.main()
