import json
import struct
import unittest
from array import array
from pathlib import Path

import build123d
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

from cadpy_common.glb import (
    export_assembly_glb_from_scene,
    export_native_glb_from_scene,
    export_part_glb_from_scene,
    read_step_display_edge_manifest_from_glb,
    read_step_topology_bundle_from_glb,
    read_step_topology_manifest_from_glb,
)
from cadpy_common.glb_topology import STEP_TOPOLOGY_SCHEMA_VERSION, glb_surface_edge_class_has_nonzero_values
from cadpy_common.step_scene import (
    LoadedStepScene,
    OccurrenceNode,
    SelectorBundle,
    SelectorOptions,
    SelectorProfile,
    _shape_hash,
    extract_selectors_from_scene,
    load_step_scene,
)
from tests.python.support.tmp_root import temporary_directory


def _identity_transform() -> tuple[float, ...]:
    return (
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
    )


def _meshed_box(width: float = 10, depth: float = 20, height: float = 30) -> object:
    shape = build123d.Box(width, depth, height).wrapped
    BRepMesh_IncrementalMesh(shape, 0.1, True, 0.1, True).Perform()
    return shape


def _single_leaf_scene(shape: object, **kwargs) -> tuple[LoadedStepScene, int]:
    prototype_key = _shape_hash(shape)
    scene = LoadedStepScene(
        step_path=Path("fixture.step"),
        roots=[
            OccurrenceNode(
                path=(1,),
                name="fixture",
                source_name="fixture",
                transform=_identity_transform(),
                local_transform=_identity_transform(),
                prototype_key=prototype_key,
            )
        ],
        prototype_shapes={prototype_key: shape},
        prototype_names={prototype_key: "fixture"},
        **kwargs,
    )
    return scene, prototype_key


def _read_glb_json(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    magic, version, _length = struct.unpack_from("<III", payload, 0)
    if magic != 0x46546C67 or version != 2:
        raise AssertionError("Not a GLB v2 file")
    chunk_length, chunk_type = struct.unpack_from("<I4s", payload, 12)
    if chunk_type != b"JSON":
        raise AssertionError("First GLB chunk is not JSON")
    return json.loads(payload[20:20 + chunk_length].decode("utf-8"))


class GlbExportTests(unittest.TestCase):
    def test_part_glb_embeds_step_topology_extension(self) -> None:
        with temporary_directory(prefix="cad-glb-test-") as temp_dir:
            step_path = Path(temp_dir) / "fixture.step"
            scene, _prototype_key = _single_leaf_scene(_meshed_box())
            bundle = SelectorBundle(
                manifest={
                    "schemaVersion": 1,
                    "profile": "artifact",
                    "stepPath": "fixture.step",
                    "stepHash": "step-hash-123",
                    "tables": {},
                    "occurrences": [],
                    "shapes": [],
                    "faces": [],
                    "edges": [],
                },
                buffers={"edgeIds": array("I", [7, 11]), "surfaceHalfEdges": array("I")},
            )

            glb_path = export_part_glb_from_scene(
                step_path,
                scene,
                linear_deflection=0.1,
                angular_deflection=0.1,
                selector_bundle=bundle,
            )

            gltf = _read_glb_json(glb_path)
            self.assertIn("STEP_topology", gltf.get("extensionsUsed", []))
            self.assertIn("STEP_topology", gltf.get("extensions", {}))
            extension = gltf.get("extensions", {}).get("STEP_topology", {})
            self.assertIn("indexView", extension)
            self.assertIn("edgeView", extension)
            self.assertIn("selectorView", extension)
            index = read_step_topology_manifest_from_glb(glb_path)
            self.assertIsNotNone(index)
            assert index is not None
            self.assertEqual("index", index.get("profile"))
            self.assertEqual("part", index.get("entryKind"))
            self.assertNotIn("cadRef", index)
            self.assertNotIn("cadPath", index)
            surface_edges = read_step_display_edge_manifest_from_glb(glb_path)
            self.assertIsNotNone(surface_edges)
            assert surface_edges is not None
            self.assertEqual("surface-edges", surface_edges.get("profile"))
            self.assertEqual(STEP_TOPOLOGY_SCHEMA_VERSION, surface_edges.get("schemaVersion"))
            self.assertEqual("surfaceHalfEdges", surface_edges.get("halfEdgesView"))
            self.assertIn("surfaceHalfEdges", surface_edges.get("buffers", {}).get("views", {}))
            self.assertNotIn("faces", surface_edges)
            self.assertNotIn("relations", surface_edges)
            embedded = read_step_topology_bundle_from_glb(glb_path)
            self.assertIsNotNone(embedded)
            assert embedded is not None
            self.assertEqual(STEP_TOPOLOGY_SCHEMA_VERSION, embedded.manifest["schemaVersion"])
            self.assertNotIn("cadRef", embedded.manifest)
            self.assertNotIn("cadPath", embedded.manifest)
            self.assertEqual([7, 11], list(embedded.buffers["edgeIds"]))

    def test_step_glb_surface_edge_class_attribute_is_populated_from_selector_topology(self) -> None:
        with temporary_directory(prefix="cad-glb-surface-edges-") as temp_dir:
            step_path = Path(temp_dir) / "cylinder.step"
            build123d.export_step(build123d.Cylinder(5, 10), step_path)
            scene = load_step_scene(step_path)
            bundle = extract_selectors_from_scene(
                scene,
                profile=SelectorProfile.ARTIFACT,
                options=SelectorOptions(linear_deflection=0.2, angular_deflection=0.2),
            )

            glb_path = export_part_glb_from_scene(
                step_path,
                scene,
                linear_deflection=0.2,
                angular_deflection=0.2,
                selector_bundle=bundle,
            )

            self.assertTrue(glb_surface_edge_class_has_nonzero_values(glb_path))

    def test_legacy_topology_json_and_bin_bundle_is_read_when_glb_lacks_extension(self) -> None:
        with temporary_directory(prefix="cad-glb-test-") as temp_dir:
            artifact_dir = Path(temp_dir) / ".fixture.step"
            artifact_dir.mkdir()
            glb_path = artifact_dir / "model.glb"
            glb_path.write_bytes(b"legacy visual glb without embedded topology")

            edge_ids = array("I", [19, 23])
            edge_bytes = edge_ids.tobytes()
            (artifact_dir / "topology.bin").write_bytes(edge_bytes)
            (artifact_dir / "topology.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "profile": "artifact",
                        "cadRef": "fixtures/legacy",
                        "buffers": {
                            "uri": "topology.bin",
                            "littleEndian": True,
                            "views": {
                                "edgeIds": {
                                    "dtype": "uint32",
                                    "byteOffset": 0,
                                    "byteLength": len(edge_bytes),
                                    "count": 2,
                                    "itemSize": 4,
                                }
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            index = read_step_topology_manifest_from_glb(glb_path)
            self.assertIsNotNone(index)
            assert index is not None
            self.assertEqual("fixtures/legacy", index.get("cadRef"))

            bundle = read_step_topology_bundle_from_glb(glb_path)
            self.assertIsNotNone(bundle)
            assert bundle is not None
            self.assertEqual("fixtures/legacy", bundle.manifest.get("cadRef"))
            self.assertEqual([19, 23], list(bundle.buffers["edgeIds"]))

    def test_assembly_glb_preserves_face_colors_as_material_primitives(self) -> None:
        with temporary_directory(prefix="cad-glb-test-") as temp_dir:
            step_path = Path(temp_dir) / "fixture.step"
            shape = _meshed_box()
            face_hashes: list[int] = []
            explorer = TopExp_Explorer(shape, TopAbs_FACE)
            while explorer.More() and len(face_hashes) < 2:
                face_hashes.append(_shape_hash(TopoDS.Face_s(explorer.Current())))
                explorer.Next()
            scene, prototype_key = _single_leaf_scene(
                shape,
                prototype_face_colors={
                    _shape_hash(shape): {
                        face_hashes[0]: (1.0, 0.0, 0.0, 1.0),
                        face_hashes[1]: (0.0, 0.0, 1.0, 1.0),
                    }
                },
            )

            glb_path = export_assembly_glb_from_scene(
                step_path,
                scene,
                linear_deflection=0.1,
                angular_deflection=0.1,
            )

            gltf = _read_glb_json(glb_path)
            colors = [
                material.get("pbrMetallicRoughness", {}).get("baseColorFactor")
                for material in gltf.get("materials", [])
            ]
            primitives = gltf.get("meshes", [])[0].get("primitives", [])
            primitive_materials = {primitive.get("material") for primitive in primitives}
            primitive_attributes = [primitive.get("attributes", {}) for primitive in primitives]
            self.assertEqual(prototype_key, _shape_hash(shape))
            self.assertIn([1.0, 0.0, 0.0, 1.0], colors)
            self.assertIn([0.0, 0.0, 1.0, 1.0], colors)
            self.assertGreaterEqual(len(primitive_materials), 2)
            self.assertTrue(all("NORMAL" in attributes for attributes in primitive_attributes))

    def test_assembly_glb_applies_occurrence_color_to_descendant_meshes(self) -> None:
        with temporary_directory(prefix="cad-glb-test-") as temp_dir:
            step_path = Path(temp_dir) / "fixture.step"
            shape = _meshed_box()
            prototype_key = _shape_hash(shape)
            scene = LoadedStepScene(
                step_path=step_path,
                roots=[
                    OccurrenceNode(
                        path=(1,),
                        name="assembly",
                        source_name="assembly",
                        transform=_identity_transform(),
                        prototype_key=None,
                        local_transform=_identity_transform(),
                        children=(
                            OccurrenceNode(
                                path=(1, 1),
                                name="part",
                                source_name="part",
                                transform=_identity_transform(),
                                local_transform=_identity_transform(),
                                prototype_key=prototype_key,
                            ),
                        ),
                    )
                ],
                prototype_shapes={prototype_key: shape},
                prototype_names={prototype_key: "fixture"},
            )

            glb_path = export_assembly_glb_from_scene(
                step_path,
                scene,
                linear_deflection=0.1,
                angular_deflection=0.1,
                occurrence_colors={"o1": (0.1, 0.2, 0.3, 1.0)},
            )

            gltf = _read_glb_json(glb_path)
            colors = [
                material.get("pbrMetallicRoughness", {}).get("baseColorFactor")
                for material in gltf.get("materials", [])
            ]
            self.assertIn([0.1, 0.2, 0.3, 1.0], colors)

    def test_part_glb_uses_scene_material_colors(self) -> None:
        with temporary_directory(prefix="cad-glb-test-") as temp_dir:
            step_path = Path(temp_dir) / "fixture.step"
            shape = _meshed_box()
            scene, prototype_key = _single_leaf_scene(
                shape,
                prototype_colors={_shape_hash(shape): (0.168627, 0.184314, 0.2, 1.0)},
            )

            glb_path = export_part_glb_from_scene(
                step_path,
                scene,
                linear_deflection=0.1,
                angular_deflection=0.1,
            )

            gltf = _read_glb_json(glb_path)
            colors = [
                material.get("pbrMetallicRoughness", {}).get("baseColorFactor")
                for material in gltf.get("materials", [])
            ]
            self.assertEqual(prototype_key, _shape_hash(shape))
            self.assertIn([0.168627, 0.184314, 0.2, 1.0], colors)

    def test_native_glb_is_y_up_without_step_topology_or_cad_extras(self) -> None:
        with temporary_directory(prefix="cad-glb-test-") as temp_dir:
            step_path = Path(temp_dir) / "fixture.step"
            shape = _meshed_box(width=10, depth=20, height=30)
            scene, _prototype_key = _single_leaf_scene(
                shape,
                prototype_colors={_shape_hash(shape): (0.168627, 0.184314, 0.2, 1.0)},
            )

            glb_path = export_native_glb_from_scene(
                step_path,
                scene,
                target_path=Path(temp_dir) / "fixture.glb",
                linear_deflection=0.1,
                angular_deflection=0.1,
            )

            gltf = _read_glb_json(glb_path)
            self.assertNotIn("extensionsUsed", gltf)
            self.assertNotIn("extensions", gltf)
            self.assertTrue(all("extras" not in node for node in gltf.get("nodes", [])))
            position_accessor = gltf["accessors"][0]
            self.assertEqual([-0.005, -0.015, -0.01], [round(value, 6) for value in position_accessor["min"]])
            self.assertEqual([0.005, 0.015, 0.01], [round(value, 6) for value in position_accessor["max"]])
            colors = [
                material.get("pbrMetallicRoughness", {}).get("baseColorFactor")
                for material in gltf.get("materials", [])
            ]
            self.assertIn([0.168627, 0.184314, 0.2, 1.0], colors)

    def test_native_glb_converts_assembly_transforms_to_y_up(self) -> None:
        with temporary_directory(prefix="cad-glb-test-") as temp_dir:
            step_path = Path(temp_dir) / "fixture.step"
            shape = _meshed_box()
            prototype_key = _shape_hash(shape)
            translated = (
                1.0,
                0.0,
                0.0,
                10.0,
                0.0,
                1.0,
                0.0,
                20.0,
                0.0,
                0.0,
                1.0,
                30.0,
                0.0,
                0.0,
                0.0,
                1.0,
            )
            scene = LoadedStepScene(
                step_path=step_path,
                roots=[
                    OccurrenceNode(
                        path=(1,),
                        name="assembly",
                        source_name="assembly",
                        transform=_identity_transform(),
                        local_transform=_identity_transform(),
                        prototype_key=None,
                        children=(
                            OccurrenceNode(
                                path=(1, 1),
                                name="part",
                                source_name="part",
                                transform=translated,
                                local_transform=translated,
                                prototype_key=prototype_key,
                            ),
                        ),
                    )
                ],
                prototype_shapes={prototype_key: shape},
                prototype_names={prototype_key: "fixture"},
            )

            glb_path = export_native_glb_from_scene(
                step_path,
                scene,
                target_path=Path(temp_dir) / "assembly.glb",
                linear_deflection=0.1,
                angular_deflection=0.1,
            )

            gltf = _read_glb_json(glb_path)
            child = next(node for node in gltf["nodes"] if node.get("mesh") == 0)
            self.assertEqual("part", child.get("name"))
            self.assertEqual([0.01, 0.03, -0.02], [round(value, 6) for value in child["matrix"][12:15]])


if __name__ == "__main__":
    unittest.main()
