import json
import shutil
import struct
import unittest
from pathlib import Path
from unittest import mock

import build123d

from cadpy_common import assembly_export as assembly_export_module
from cadpy_common.assembly_export import build_assembly_compound, export_assembly_step_scene
from cadpy_common.assembly_spec import AssemblyInstanceSpec, AssemblyNodeSpec, AssemblySpec
from cadpy_common.glb_topology import STEP_TOPOLOGY_SCHEMA_VERSION
from cadpy_common.glb_mesh_payload import DEFAULT_MATERIAL, scene_glb_mesh_payload
from cadpy_common.render import part_glb_path
from cadpy_common.step_scene import (
    SelectorProfile,
    _apply_transform_point,
    _bbox_from_shape,
    extract_selectors_from_scene,
    mesh_step_scene,
    occurrence_selector_id,
    scene_occurrence_shape,
    _shape_hash,
)
from tests.python.support.cad_test_roots import IsolatedCadRoots


IDENTITY_TRANSFORM = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)
TRANSLATED_TRANSFORM = (1.0, 0.0, 0.0, 4.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)


def _pad4(payload: bytes, *, byte: bytes = b"\0") -> bytes:
    padding = (4 - (len(payload) % 4)) % 4
    return payload + (byte * padding)


def _write_topology_glb(path: Path, manifest: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest_payload = json.dumps({"schemaVersion": STEP_TOPOLOGY_SCHEMA_VERSION, "profile": "index", **manifest}, separators=(",", ":")).encode("utf-8")
    display_manifest_payload = json.dumps(
        {
            "schemaVersion": STEP_TOPOLOGY_SCHEMA_VERSION,
            "profile": "surface-edges",
            "stepHash": "",
            "halfEdgesView": "surfaceHalfEdges",
            "buffers": {"views": {"surfaceHalfEdges": {"dtype": "uint32", "bufferView": 1, "byteOffset": 0, "byteLength": 0, "count": 0, "itemSize": 4}}},
        },
        separators=(",", ":"),
    ).encode("utf-8")
    display_offset = len(_pad4(manifest_payload))
    binary = _pad4(manifest_payload) + _pad4(display_manifest_payload)
    gltf = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(manifest_payload)},
            {"buffer": 0, "byteOffset": display_offset, "byteLength": len(display_manifest_payload)},
        ],
        "extensionsUsed": ["STEP_topology"],
        "extensions": {
            "STEP_topology": {
                "schemaVersion": STEP_TOPOLOGY_SCHEMA_VERSION,
                "indexView": 0,
                "edgeView": 1,
                "encoding": "utf-8",
            }
        },
    }
    json_chunk = _pad4(json.dumps(gltf, separators=(",", ":")).encode("utf-8"), byte=b" ")
    path.write_bytes(
        b"glTF"
        + struct.pack("<II", 2, 12 + 8 + len(json_chunk) + 8 + len(binary))
        + struct.pack("<I4s", len(json_chunk), b"JSON")
        + json_chunk
        + struct.pack("<I4s", len(binary), b"BIN\0")
        + binary
    )


class AssemblyExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self._isolated_roots = IsolatedCadRoots(self, prefix="assembly-export-")
        self.cad_root = self._isolated_roots.cad_root

    def tearDown(self) -> None:
        shutil.rmtree(self._isolated_roots.root, ignore_errors=True)

    def _write_part(self) -> Path:
        step_path = self.cad_root / "STEP" / "leaf.step"
        step_path.parent.mkdir(parents=True, exist_ok=True)
        build123d.export_step(build123d.Box(1, 1, 1), step_path)
        return step_path

    def _write_colored_part(self) -> Path:
        step_path = self.cad_root / "STEP" / "leaf.step"
        step_path.parent.mkdir(parents=True, exist_ok=True)
        box = build123d.Box(1, 1, 1)
        box.color = build123d.Color(1, 0, 0, 1)
        build123d.export_step(box, step_path)
        return step_path

    def _write_native_assembly_part(self, *, write_topology: bool = False) -> Path:
        step_path = self.cad_root / "STEP" / "native_module.step"
        step_path.parent.mkdir(parents=True, exist_ok=True)
        left = build123d.Box(1, 1, 1)
        left.label = "left"
        right = build123d.Box(1, 1, 1).moved(build123d.Location((10, 0, 0)))
        right.label = "right"
        module = build123d.Compound(children=[left, right], label="native_module")
        build123d.export_step(module, step_path)
        if write_topology:
            _write_topology_glb(part_glb_path(step_path), {"assembly": {"root": {"children": [{}]}}})
        return step_path

    def _assembly_spec(self, *instances: AssemblyInstanceSpec) -> AssemblySpec:
        assembly_path = self.cad_root / "STEP" / "assembly.py"
        assembly_path.parent.mkdir(parents=True, exist_ok=True)
        return AssemblySpec(
            assembly_path=assembly_path,
            instances=instances,
        )

    def _leaf_instance(
        self,
        *,
        instance_id: str = "leaf",
        transform: tuple[float, ...] = IDENTITY_TRANSFORM,
        use_source_colors: bool = True,
    ) -> AssemblyInstanceSpec:
        return AssemblyInstanceSpec(
            instance_id=instance_id,
            source_path=(self.cad_root / "STEP" / "leaf.step").resolve(),
            path="leaf.step",
            name=instance_id,
            transform=transform,
            use_source_colors=use_source_colors,
        )

    def _transformed_payload_bbox(self, scene, node) -> dict[str, list[float]]:
        payload = scene_glb_mesh_payload(
            scene,
            node.prototype_key,
            default_color=DEFAULT_MATERIAL,
            suppress_face_colors=True,
        )
        points = []
        for x in (payload.minimum[0] * 1000.0, payload.maximum[0] * 1000.0):
            for y in (payload.minimum[1] * 1000.0, payload.maximum[1] * 1000.0):
                for z in (payload.minimum[2] * 1000.0, payload.maximum[2] * 1000.0):
                    points.append(_apply_transform_point(node.transform, [x, y, z]))
        return {
            "min": [min(point[index] for point in points) for index in range(3)],
            "max": [max(point[index] for point in points) for index in range(3)],
        }

    def _assert_bbox_close(self, actual: dict[str, list[float]], expected: dict[str, list[float]]) -> None:
        for key in ("min", "max"):
            for actual_value, expected_value in zip(actual[key], expected[key], strict=True):
                self.assertAlmostEqual(actual_value, expected_value, places=3)

    def test_imported_part_does_not_read_persistent_source_color(self) -> None:
        self._write_part()
        assembly_spec = self._assembly_spec(self._leaf_instance())

        assembly = build_assembly_compound(assembly_spec, label="assembly")

        self.assertIsNone(assembly.children[0].color)

    def test_instance_can_suppress_embedded_source_color(self) -> None:
        self._write_colored_part()
        assembly_spec = self._assembly_spec(self._leaf_instance(use_source_colors=False))

        assembly = build_assembly_compound(assembly_spec, label="assembly")

        self.assertIsNone(assembly.children[0].color)

    def test_repeated_part_instances_keep_distinct_occurrence_names(self) -> None:
        self._write_part()
        assembly_spec = self._assembly_spec(
            self._leaf_instance(instance_id="leaf_a"),
            self._leaf_instance(instance_id="leaf_b", transform=TRANSLATED_TRANSFORM),
        )
        assembly_path = assembly_spec.assembly_path
        output_path = assembly_path.with_suffix(".step")

        scene = export_assembly_step_scene(assembly_spec, output_path)
        bundle = extract_selectors_from_scene(
            scene,
            cad_ref="assemblies/assembly",
            profile=SelectorProfile.SUMMARY,
        )
        columns = bundle.manifest["tables"]["occurrenceColumns"]
        source_names = {
            dict(zip(columns, row))["sourceName"]
            for row in bundle.manifest["occurrences"]
        }

        self.assertIn("leaf_a", source_names)
        self.assertIn("leaf_b", source_names)
        self.assertEqual(output_path.resolve(), scene.step_path)
        self.assertIsNotNone(scene.doc)

    def test_recursive_children_keep_subassembly_labels(self) -> None:
        self._write_part()
        assembly_spec = AssemblySpec(
            assembly_path=self.cad_root / "STEP" / "assembly.py",
            instances=(),
            children=(
                AssemblyNodeSpec(
                    instance_id="module",
                    name="module",
                    transform=IDENTITY_TRANSFORM,
                    children=(
                        AssemblyNodeSpec(
                            instance_id="leaf",
                            name="leaf",
                            source_path=(self.cad_root / "STEP" / "leaf.step").resolve(),
                            path="leaf.step",
                            transform=IDENTITY_TRANSFORM,
                        ),
                    ),
                ),
            ),
        )

        assembly = build_assembly_compound(assembly_spec, label="assembly")

        self.assertEqual("module", assembly.children[0].label)
        self.assertEqual("module__leaf", assembly.children[0].children[0].label)

    def test_direct_export_recursive_children_keep_occurrence_names(self) -> None:
        self._write_part()
        assembly_spec = AssemblySpec(
            assembly_path=self.cad_root / "STEP" / "assembly.py",
            instances=(),
            children=(
                AssemblyNodeSpec(
                    instance_id="module",
                    name="module",
                    transform=IDENTITY_TRANSFORM,
                    children=(
                        AssemblyNodeSpec(
                            instance_id="leaf",
                            name="leaf",
                            source_path=(self.cad_root / "STEP" / "leaf.step").resolve(),
                            path="leaf.step",
                            transform=IDENTITY_TRANSFORM,
                        ),
                    ),
                ),
            ),
        )

        scene = export_assembly_step_scene(assembly_spec, assembly_spec.assembly_path.with_suffix(".step"))
        bundle = extract_selectors_from_scene(
            scene,
            cad_ref="assemblies/assembly",
            profile=SelectorProfile.SUMMARY,
        )
        columns = bundle.manifest["tables"]["occurrenceColumns"]
        source_names = {
            dict(zip(columns, row))["sourceName"]
            for row in bundle.manifest["occurrences"]
        }

        self.assertIn("module", source_names)
        self.assertIn("module__leaf", source_names)

    def test_direct_export_preserves_imported_step_assembly_child_locations(self) -> None:
        native_step = self._write_native_assembly_part()
        assembly_spec = self._assembly_spec(
            AssemblyInstanceSpec(
                instance_id="native",
                source_path=native_step.resolve(),
                path="native_module.step",
                name="native",
                transform=IDENTITY_TRANSFORM,
            ),
        )

        scene = export_assembly_step_scene(assembly_spec, assembly_spec.assembly_path.with_suffix(".step"))
        native_root = scene.roots[0].children[0].children[0]
        child_x_offsets = sorted(round(float(child.local_transform[3]), 3) for child in native_root.children)

        self.assertEqual([0.0, 10.0], child_x_offsets)

    def test_imported_step_assembly_glb_payload_does_not_double_apply_child_location(self) -> None:
        native_step = self._write_native_assembly_part()
        assembly_spec = self._assembly_spec(
            AssemblyInstanceSpec(
                instance_id="native",
                source_path=native_step.resolve(),
                path="native_module.step",
                name="native",
                transform=IDENTITY_TRANSFORM,
            ),
        )

        scene = export_assembly_step_scene(assembly_spec, assembly_spec.assembly_path.with_suffix(".step"))
        mesh_step_scene(scene, linear_deflection=0.006, angular_deflection=0.6, relative=True)
        right_box_leaf = next(
            node
            for node in scene.roots[0].children[0].children[0].children[1].children
            if node.prototype_key is not None
        )
        expected_bbox = _bbox_from_shape(scene_occurrence_shape(scene, right_box_leaf))
        payload_bbox = self._transformed_payload_bbox(scene, right_box_leaf)

        self.assertEqual("o1.1.1.2.1", occurrence_selector_id(right_box_leaf))
        self._assert_bbox_close(payload_bbox, {"min": expected_bbox["min"], "max": expected_bbox["max"]})

    def test_cached_compound_copy_preserves_parent_transform(self) -> None:
        leaf = build123d.Box(1, 1, 1)
        leaf.label = "leaf"
        compound = build123d.Compound(children=[leaf], label="module")
        moved = compound.moved(build123d.Location((10, 0, 0)))

        copied = assembly_export_module._copy_cached_shape_tree(moved)

        self.assertAlmostEqual(10.0, copied.center().X, places=6)

    def test_catalog_index_is_reused_for_repeated_instances(self) -> None:
        self._write_part()
        assembly_spec = self._assembly_spec(
            self._leaf_instance(instance_id="leaf_a"),
            self._leaf_instance(instance_id="leaf_b", transform=TRANSLATED_TRANSFORM),
        )

        with mock.patch.object(
            assembly_export_module,
            "iter_cad_sources",
            wraps=assembly_export_module.iter_cad_sources,
        ) as iter_cad_sources:
            assembly = build_assembly_compound(assembly_spec, label="assembly")

        self.assertEqual(1, iter_cad_sources.call_count)
        self.assertEqual(["leaf_a", "leaf_b"], [child.label for child in assembly.children])

    def test_direct_export_propagates_leaf_shape_label_to_step_product(self) -> None:
        """Regression: leaf-Part definitions in the assembly STEP must carry
        the shape label, not the generic 'SOLID' OCCT fallback. Without
        ``_set_label_name`` on the leaf branch of ``_shape_definition_for_tree``,
        a CAD UI such as Fusion shows every single-Part component as ``solid``.
        """
        leaf_label = "leaf_box_product"
        step_path = self.cad_root / "STEP" / f"{leaf_label}.step"
        step_path.parent.mkdir(parents=True, exist_ok=True)
        box = build123d.Box(1, 1, 1)
        box.label = leaf_label
        build123d.export_step(box, step_path)

        assembly_spec = self._assembly_spec(
            AssemblyInstanceSpec(
                instance_id="leaf",
                source_path=step_path.resolve(),
                path=f"{leaf_label}.step",
                name="leaf",
                transform=IDENTITY_TRANSFORM,
            ),
        )
        output_path = assembly_spec.assembly_path.with_suffix(".step")

        export_assembly_step_scene(assembly_spec, output_path)
        contents = output_path.read_bytes()

        self.assertIn(f"PRODUCT('{leaf_label}'".encode("ascii"), contents)
        self.assertNotIn(b"PRODUCT('SOLID'", contents)

    def test_direct_writer_reuses_quantity_colors_for_tuple_rgba(self) -> None:
        assembly_spec = self._assembly_spec()
        writer = assembly_export_module._DirectXcafAssemblyWriter(assembly_spec, label="assembly")
        captured_colors: list[object] = []

        class FakeColorTool:
            def SetColor(self, label, wrapped, color_type):
                captured_colors.append(wrapped)

        writer.color_tool = FakeColorTool()

        writer._set_label_color(object(), (0.1, 0.2, 0.3, 1.0))
        writer._set_label_color(object(), (0.1, 0.2, 0.3, 1.0))

        self.assertEqual(2, len(captured_colors))
        self.assertIs(captured_colors[0], captured_colors[1])

    def test_direct_writer_applies_step_scene_face_colors_to_prototype_shapes(self) -> None:
        assembly_spec = self._assembly_spec()
        writer = assembly_export_module._DirectXcafAssemblyWriter(assembly_spec, label="assembly")
        captured_colors: list[object] = []

        class FakeColorTool:
            def SetColor(self, label, wrapped, color_type):
                captured_colors.append(wrapped)

        writer.color_tool = FakeColorTool()
        shape = build123d.Box(1, 1, 1).wrapped
        shape_label = writer.shape_tool.AddShape(shape, False)
        face_hashes = []
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS

        explorer = TopExp_Explorer(shape, TopAbs_FACE)
        while explorer.More():
            face_hashes.append(_shape_hash(TopoDS.Face_s(explorer.Current())))
            explorer.Next()

        writer._set_shape_face_colors(shape_label, shape, {face_hashes[0]: (0.0, 0.0, 1.0, 1.0)})

        self.assertEqual(1, len(captured_colors))


if __name__ == "__main__":
    unittest.main()
