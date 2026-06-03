import os
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import build123d
import trimesh
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

from cadpy_common.step_scene import LoadedStepScene, OccurrenceNode, _shape_hash
from tests.python.support.tmp_root import temporary_directory
from cadpy_common.threemf import export_scene_3mf, export_shape_3mf


NS = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}


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


def _translate_transform(x: float, y: float, z: float) -> tuple[float, ...]:
    return (
        1.0,
        0.0,
        0.0,
        x,
        0.0,
        1.0,
        0.0,
        y,
        0.0,
        0.0,
        1.0,
        z,
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


def _read_model(path: Path) -> ET.Element:
    with zipfile.ZipFile(path) as package:
        return ET.fromstring(package.read("3D/3dmodel.model"))


class ThreeMfExportTests(unittest.TestCase):
    def test_export_shape_3mf_writes_loadable_package(self) -> None:
        with temporary_directory(prefix="cad-3mf-test-") as temp_dir:
            output_path = Path(temp_dir) / "box.3mf"
            shape = build123d.Box(10, 20, 30).wrapped
            BRepMesh_IncrementalMesh(shape, 0.1, True, 0.1, True).Perform()

            export_shape_3mf(shape, output_path)

            self.assertTrue(output_path.exists())
            self.assertTrue(zipfile.is_zipfile(output_path))
            with zipfile.ZipFile(output_path) as package:
                self.assertIn("[Content_Types].xml", package.namelist())
                self.assertIn("_rels/.rels", package.namelist())
                self.assertIn("3D/3dmodel.model", package.namelist())
                self.assertNotIn("mesh.stl", package.namelist())
                model_xml = package.read("3D/3dmodel.model")
            root = ET.fromstring(model_xml)
            self.assertEqual("millimeter", root.attrib["unit"])
            self.assertIsNotNone(root.find("./m:resources/m:basematerials", NS))
            vertices = root.findall(".//m:vertex", NS)
            triangles = root.findall(".//m:triangle", NS)
            self.assertTrue(vertices)
            self.assertTrue(triangles)
            self.assertLess(len(vertices), len(triangles) * 3)
            loaded = trimesh.load(output_path, file_type="3mf")
            geometry = getattr(loaded, "geometry", None)
            self.assertTrue(len(geometry) if geometry is not None else len(loaded.faces))

    def test_scene_export_emits_component_objects_and_transforms(self) -> None:
        with temporary_directory(prefix="cad-3mf-test-") as temp_dir:
            output_path = Path(temp_dir) / "assembly.3mf"
            shape = _meshed_box()
            prototype_key = _shape_hash(shape)
            scene = LoadedStepScene(
                step_path=Path("assembly.step"),
                roots=[
                    OccurrenceNode(
                        path=(1,),
                        name="root",
                        source_name="root",
                        transform=_identity_transform(),
                        local_transform=_identity_transform(),
                        prototype_key=None,
                        children=[
                            OccurrenceNode(
                                path=(1, 1),
                                name="left",
                                source_name="block",
                                transform=_identity_transform(),
                                local_transform=_identity_transform(),
                                prototype_key=prototype_key,
                            ),
                            OccurrenceNode(
                                path=(1, 2),
                                name="right",
                                source_name="block",
                                transform=_translate_transform(25, 0, 0),
                                local_transform=_translate_transform(25, 0, 0),
                                prototype_key=prototype_key,
                            ),
                        ],
                    )
                ],
                prototype_shapes={prototype_key: shape},
                prototype_names={prototype_key: "block"},
            )

            export_scene_3mf(scene, output_path)

            root = _read_model(output_path)
            objects = root.findall("./m:resources/m:object", NS)
            mesh_objects = [obj for obj in objects if obj.find("m:mesh", NS) is not None]
            component_objects = [obj for obj in objects if obj.find("m:components", NS) is not None]
            components = root.findall(".//m:component", NS)
            transforms = [component.attrib.get("transform") for component in components if component.attrib.get("transform")]
            self.assertEqual(1, len(mesh_objects))
            self.assertEqual(1, len(component_objects))
            self.assertEqual(2, len(components))
            self.assertTrue(any("25" in transform.split() for transform in transforms))

    def test_uniform_color_uses_object_level_material(self) -> None:
        with temporary_directory(prefix="cad-3mf-test-") as temp_dir:
            output_path = Path(temp_dir) / "red.3mf"
            shape = _meshed_box()
            scene, prototype_key = _single_leaf_scene(
                shape,
                prototype_colors={_shape_hash(shape): (1.0, 0.0, 0.0, 1.0)},
            )

            export_scene_3mf(scene, output_path)

            root = _read_model(output_path)
            bases = root.findall("./m:resources/m:basematerials/m:base", NS)
            mesh_object = next(obj for obj in root.findall("./m:resources/m:object", NS) if obj.find("m:mesh", NS) is not None)
            triangles = root.findall(".//m:triangle", NS)
            self.assertEqual(prototype_key, _shape_hash(shape))
            self.assertIn("#FF0000FF", [base.attrib.get("displaycolor") for base in bases])
            self.assertEqual("1", mesh_object.attrib.get("pid"))
            self.assertIsNotNone(mesh_object.attrib.get("pindex"))
            self.assertFalse(any("p1" in triangle.attrib for triangle in triangles))

    def test_display_colors_are_srgb_encoded_from_scene_colors(self) -> None:
        with temporary_directory(prefix="cad-3mf-test-") as temp_dir:
            output_path = Path(temp_dir) / "rail.3mf"
            shape = _meshed_box()
            scene, _prototype_key = _single_leaf_scene(shape)

            export_scene_3mf(scene, output_path, occurrence_colors={"o1": (0.22, 0.28, 0.34, 1.0)})

            root = _read_model(output_path)
            bases = root.findall("./m:resources/m:basematerials/m:base", NS)
            self.assertIn("#81909EFF", [base.attrib.get("displaycolor") for base in bases])

    def test_occurrence_color_overrides_default_material(self) -> None:
        with temporary_directory(prefix="cad-3mf-test-") as temp_dir:
            output_path = Path(temp_dir) / "dark.3mf"
            shape = _meshed_box()
            scene, _prototype_key = _single_leaf_scene(shape)

            export_scene_3mf(scene, output_path, occurrence_colors={"o1": (0.168627, 0.184314, 0.2, 1.0)})

            root = _read_model(output_path)
            bases = root.findall("./m:resources/m:basematerials/m:base", NS)
            mesh_object = next(obj for obj in root.findall("./m:resources/m:object", NS) if obj.find("m:mesh", NS) is not None)
            dark_index = next(
                str(index)
                for index, base in enumerate(bases)
                if base.attrib.get("displaycolor") == "#72777CFF"
            )
            self.assertEqual(dark_index, mesh_object.attrib.get("pindex"))

    def test_parent_occurrence_color_applies_to_descendant_meshes(self) -> None:
        with temporary_directory(prefix="cad-3mf-test-") as temp_dir:
            output_path = Path(temp_dir) / "child.3mf"
            shape = _meshed_box()
            prototype_key = _shape_hash(shape)
            scene = LoadedStepScene(
                step_path=Path("assembly.step"),
                roots=[
                    OccurrenceNode(
                        path=(1,),
                        name="colored-parent",
                        source_name="colored-parent",
                        transform=_identity_transform(),
                        local_transform=_identity_transform(),
                        prototype_key=None,
                        children=[
                            OccurrenceNode(
                                path=(1, 1),
                                name="child",
                                source_name="child",
                                transform=_identity_transform(),
                                local_transform=_identity_transform(),
                                prototype_key=prototype_key,
                            )
                        ],
                    )
                ],
                prototype_shapes={prototype_key: shape},
            )

            export_scene_3mf(scene, output_path, occurrence_colors={"o1": (0.168627, 0.184314, 0.2, 1.0)})

            root = _read_model(output_path)
            bases = root.findall("./m:resources/m:basematerials/m:base", NS)
            mesh_object = next(obj for obj in root.findall("./m:resources/m:object", NS) if obj.find("m:mesh", NS) is not None)
            dark_index = next(
                str(index)
                for index, base in enumerate(bases)
                if base.attrib.get("displaycolor") == "#72777CFF"
            )
            self.assertEqual(dark_index, mesh_object.attrib.get("pindex"))

    def test_mixed_face_colors_use_triangle_material_indices(self) -> None:
        with temporary_directory(prefix="cad-3mf-test-") as temp_dir:
            output_path = Path(temp_dir) / "mixed.3mf"
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

            export_scene_3mf(scene, output_path)

            root = _read_model(output_path)
            bases = root.findall("./m:resources/m:basematerials/m:base", NS)
            triangles = root.findall(".//m:triangle", NS)
            triangle_materials = {triangle.attrib.get("p1") for triangle in triangles if "p1" in triangle.attrib}
            mesh_object = next(obj for obj in root.findall("./m:resources/m:object", NS) if obj.find("m:mesh", NS) is not None)
            self.assertEqual(prototype_key, _shape_hash(shape))
            self.assertIn("#FF0000FF", [base.attrib.get("displaycolor") for base in bases])
            self.assertIn("#0000FFFF", [base.attrib.get("displaycolor") for base in bases])
            self.assertIsNone(mesh_object.attrib.get("pindex"))
            self.assertGreaterEqual(len(triangle_materials), 2)


@unittest.skipUnless(os.environ.get("CAD_3MF_HEAVY_TESTS") == "1", "set CAD_3MF_HEAVY_TESTS=1 to run fixture exports")
class ThreeMfFixtureExportTests(unittest.TestCase):
    def test_sample_assembly_exports_native_components(self) -> None:
        with temporary_directory(prefix="cad-3mf-fixture-") as temp_dir:
            output_path = Path(temp_dir) / "sample_assembly.3mf"
            shape_a = _meshed_box()
            shape_b = _meshed_box(6, 8, 10)
            key_a = _shape_hash(shape_a)
            key_b = _shape_hash(shape_b)
            scene = LoadedStepScene(
                step_path=Path("sample_assembly.step"),
                roots=[
                    OccurrenceNode(
                        path=(1,),
                        name="sample_assembly",
                        source_name="sample_assembly",
                        transform=_identity_transform(),
                        local_transform=_identity_transform(),
                        prototype_key=None,
                        children=[
                            OccurrenceNode(
                                path=(1, 1),
                                name="sample_module",
                                source_name="sample_module",
                                transform=_identity_transform(),
                                local_transform=_identity_transform(),
                                prototype_key=None,
                                children=[
                                    OccurrenceNode(
                                        path=(1, 1, 1),
                                        name="sample_component_a",
                                        source_name="sample_component_a",
                                        transform=_identity_transform(),
                                        local_transform=_identity_transform(),
                                        prototype_key=key_a,
                                    ),
                                    OccurrenceNode(
                                        path=(1, 1, 2),
                                        name="sample_component_b",
                                        source_name="sample_component_b",
                                        transform=_translate_transform(25, 0, 0),
                                        local_transform=_translate_transform(25, 0, 0),
                                        prototype_key=key_b,
                                    ),
                                ],
                            ),
                            OccurrenceNode(
                                path=(1, 2),
                                name="sample_component_c",
                                source_name="sample_component_c",
                                transform=_translate_transform(0, 25, 0),
                                local_transform=_translate_transform(0, 25, 0),
                                prototype_key=key_a,
                            ),
                        ],
                    )
                ],
                prototype_shapes={key_a: shape_a, key_b: shape_b},
                prototype_names={key_a: "sample_component_a", key_b: "sample_component_b"},
            )

            export_scene_3mf(scene, output_path)

            root = _read_model(output_path)
            objects = root.findall("./m:resources/m:object", NS)
            components = root.findall(".//m:component", NS)
            transforms = [component.attrib.get("transform") for component in components if component.attrib.get("transform")]
            self.assertGreater(sum(1 for obj in objects if obj.find("m:mesh", NS) is not None), 1)
            self.assertGreater(sum(1 for obj in objects if obj.find("m:components", NS) is not None), 1)
            self.assertGreater(len(transforms), 0)
            loaded = trimesh.load(output_path, file_type="3mf")
            self.assertGreater(len(getattr(loaded, "geometry", {}) or []), 1)

    def test_sample_components_export_material_assignments(self) -> None:
        with temporary_directory(prefix="cad-3mf-fixture-") as temp_dir:
            output_path = Path(temp_dir) / "sample_components.3mf"
            shape_a = _meshed_box()
            shape_b = _meshed_box(6, 8, 10)
            key_a = _shape_hash(shape_a)
            key_b = _shape_hash(shape_b)
            scene = LoadedStepScene(
                step_path=Path("sample_components.step"),
                roots=[
                    OccurrenceNode(
                        path=(1,),
                        name="sample_component_a",
                        source_name="sample_component_a",
                        transform=_identity_transform(),
                        local_transform=_identity_transform(),
                        prototype_key=key_a,
                    ),
                    OccurrenceNode(
                        path=(2,),
                        name="sample_component_b",
                        source_name="sample_component_b",
                        transform=_translate_transform(25, 0, 0),
                        local_transform=_translate_transform(25, 0, 0),
                        prototype_key=key_b,
                    ),
                ],
                prototype_shapes={key_a: shape_a, key_b: shape_b},
                prototype_names={key_a: "sample_component_a", key_b: "sample_component_b"},
                prototype_colors={key_a: (1.0, 0.0, 0.0, 1.0), key_b: (0.0, 0.0, 1.0, 1.0)},
            )

            export_scene_3mf(scene, output_path)

            root = _read_model(output_path)
            bases = root.findall("./m:resources/m:basematerials/m:base", NS)
            objects = root.findall("./m:resources/m:object", NS)
            triangles = root.findall(".//m:triangle", NS)
            material_colors = {base.attrib.get("displaycolor") for base in bases}
            object_materials = {(obj.attrib.get("pid"), obj.attrib.get("pindex")) for obj in objects if obj.attrib.get("pindex")}
            triangle_materials = {triangle.attrib.get("p1") for triangle in triangles if "p1" in triangle.attrib}
            self.assertIn("#FF0000FF", material_colors)
            self.assertIn("#0000FFFF", material_colors)
            self.assertTrue(object_materials or triangle_materials)
            loaded = trimesh.load(output_path, file_type="3mf")
            self.assertGreater(len(getattr(loaded, "geometry", {}) or []), 1)


if __name__ == "__main__":
    unittest.main()
