import os
import unittest
from pathlib import Path
from unittest import mock

import build123d
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

from cadpy_common import step_scene
from cadpy_common.step_scene import (
    LoadedStepScene,
    OccurrenceNode,
    SelectorOptions,
    SelectorProfile,
    adaptive_mesh_resolution_for_scene,
    extract_selectors_from_scene,
    load_step_scene,
    scene_occurrence_shape,
)
from cadpy_common.glb_topology import STEP_TOPOLOGY_SCHEMA_VERSION
from cadpy_common.metadata import DEFAULT_MESH_ANGULAR_TOLERANCE, DEFAULT_MESH_TOLERANCE
from tests.python.support.tmp_root import temporary_directory


class StepSceneSelectorArtifactTests(unittest.TestCase):
    def test_load_step_scene_cached_reuses_brep_scene_cache(self) -> None:
        with temporary_directory(prefix="cad-step-scene-cache-") as temp_dir:
            temp_root = Path(temp_dir)
            step_path = temp_root / "box.step"
            cache_dir = temp_root / "cache"
            build123d.export_step(build123d.Box(1, 1, 1), step_path)

            with mock.patch.dict(os.environ, {"TEXT_TO_CAD_STEP_SCENE_CACHE_DIR": str(cache_dir)}):
                first = step_scene.load_step_scene_cached(step_path)
                self.assertEqual(1, len(first.prototype_shapes))

                with mock.patch.object(step_scene, "load_step_scene", side_effect=AssertionError("cache miss")):
                    cached = step_scene.load_step_scene_cached(step_path)

            self.assertEqual(first.step_hash, cached.step_hash)
            self.assertEqual(1, len(cached.roots))
            self.assertEqual(1, len(cached.prototype_shapes))
            self.assertFalse(scene_occurrence_shape(cached, cached.roots[0]).IsNull())

    def test_step_scene_cache_restores_locations_and_face_color_hashes(self) -> None:
        with temporary_directory(prefix="cad-step-scene-cache-private-") as temp_dir:
            temp_root = Path(temp_dir)
            shape = build123d.Box(1, 1, 1).wrapped
            explorer = TopExp_Explorer(shape, TopAbs_FACE)
            face_hash = step_scene._shape_hash(TopoDS.Face_s(explorer.Current()))
            transform = (
                1.0,
                0.0,
                0.0,
                5.0,
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
            step_path = temp_root / "synthetic.step"
            step_path.write_text("synthetic cache key only", encoding="utf-8")
            scene = LoadedStepScene(
                step_path=step_path,
                roots=[
                    OccurrenceNode(
                        path=(1,),
                        name="moved_box",
                        source_name="box",
                        transform=transform,
                        local_transform=transform,
                        prototype_key=7,
                    )
                ],
                prototype_shapes={7: shape},
                prototype_face_colors={7: {face_hash: (1.0, 0.0, 0.0, 1.0)}},
            )
            cache_root = temp_root / "cache"
            step_hash = "a" * 64

            step_scene._write_step_scene_cache(scene, step_hash=step_hash, root=cache_root)
            cached = step_scene._read_step_scene_cache(step_path, step_hash=step_hash, root=cache_root)

            self.assertIsNotNone(cached)
            assert cached is not None
            self.assertEqual(1, sum(len(colors) for colors in cached.prototype_face_colors.values()))
            located = scene_occurrence_shape(cached, cached.roots[0])
            bounds = Bnd_Box()
            BRepBndLib.Add_s(located, bounds)
            x_min, _y_min, _z_min, x_max, _y_max, _z_max = bounds.Get()
            self.assertGreater(x_min, 4.0)
            self.assertGreater(x_max, 5.0)

    def test_artifact_topology_uses_glb_face_runs_without_duplicate_face_buffers(self) -> None:
        with temporary_directory(prefix="cad-topology-v2-") as temp_dir:
            step_path = Path(temp_dir) / "box.step"
            build123d.export_step(build123d.Box(1, 1, 1), step_path)
            scene = load_step_scene(step_path)

            bundle = extract_selectors_from_scene(
                scene,
                cad_ref="fixtures/box",
                profile=SelectorProfile.ARTIFACT,
                options=SelectorOptions(linear_deflection=0.1, angular_deflection=0.1),
            )

            self.assertEqual(STEP_TOPOLOGY_SCHEMA_VERSION, bundle.manifest["schemaVersion"])
            self.assertTrue(bundle.manifest["capabilities"]["surfaceEdgeRendering"])
            self.assertEqual(".box.step.glb", bundle.manifest["faceProxy"]["source"])
            self.assertIn("faceRuns", bundle.buffers)
            self.assertIn("surfaceHalfEdges", bundle.buffers)
            self.assertTrue(scene.glb_mesh_payloads)
            self.assertNotIn("facePositions", bundle.buffers)
            self.assertNotIn("faceIndices", bundle.buffers)
            self.assertNotIn("faceIds", bundle.buffers)
            face_columns = bundle.manifest["tables"]["faceColumns"]
            triangle_count_column = face_columns.index("triangleCount")
            row_triangle_count = sum(int(row[triangle_count_column]) for row in bundle.manifest["faces"])
            run_triangle_count = sum(int(bundle.buffers["faceRuns"][index + 3]) for index in range(0, len(bundle.buffers["faceRuns"]), 5))
            self.assertEqual(row_triangle_count, run_triangle_count)

    def test_shape_rows_include_occurrence_and_prototype_names(self) -> None:
        transform = (
            1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0,
        )
        scene = LoadedStepScene(
            step_path=Path("labeled.step"),
            roots=[
                OccurrenceNode(
                    path=(1,),
                    name="base:front_left",
                    source_name="base",
                    transform=transform,
                    prototype_key=7,
                )
            ],
            prototype_shapes={7: build123d.Box(1, 1, 1).wrapped},
            prototype_names={7: "base"},
        )

        bundle = extract_selectors_from_scene(
            scene,
            cad_ref="fixtures/labeled",
            profile=SelectorProfile.REFS,
            options=SelectorOptions(linear_deflection=0.1, angular_deflection=0.1),
        )

        shape_columns = bundle.manifest["tables"]["shapeColumns"]
        shape = dict(zip(shape_columns, bundle.manifest["shapes"][0]))
        self.assertEqual("base:front_left", shape["name"])
        self.assertEqual("base", shape["sourceName"])

    def test_adaptive_mesh_resolution_prefers_finer_defaults_for_small_simple_parts(self) -> None:
        with temporary_directory(prefix="cad-adaptive-mesh-") as temp_dir:
            step_path = Path(temp_dir) / "box.step"
            build123d.export_step(build123d.Box(10, 8, 4), step_path)
            scene = load_step_scene(step_path)

            resolution = adaptive_mesh_resolution_for_scene(scene)

            self.assertEqual("extra-fine", resolution.profile)
            self.assertLess(resolution.settings.tolerance, DEFAULT_MESH_TOLERANCE)
            self.assertLess(resolution.settings.angular_tolerance, DEFAULT_MESH_ANGULAR_TOLERANCE)
            self.assertEqual(1, resolution.hints["leafOccurrenceCount"])

    def test_adaptive_mesh_resolution_does_not_coarsen_simple_repeated_assemblies_by_leaf_count_alone(self) -> None:
        box_shape = build123d.Box(10, 8, 4).wrapped
        identity = (
            1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0,
        )
        scene = LoadedStepScene(
            step_path=Path("synthetic-repeated-box.step"),
            roots=[
                OccurrenceNode(
                    path=(index + 1,),
                    name=f"box_{index}",
                    source_name=f"box_{index}",
                    transform=identity,
                    prototype_key=1,
                )
                for index in range(100)
            ],
            prototype_shapes={1: box_shape},
        )

        resolution = adaptive_mesh_resolution_for_scene(scene)

        self.assertEqual("medium", resolution.profile)
        self.assertLess(resolution.settings.tolerance, DEFAULT_MESH_TOLERANCE)
        self.assertEqual(100, resolution.hints["leafOccurrenceCount"])

    def test_adaptive_mesh_resolution_keeps_many_low_curvature_occurrences_balanced(self) -> None:
        with mock.patch.object(
            step_scene,
            "_scene_mesh_resolution_hints",
            return_value={
                "bboxDiag": 190.0,
                "prototypeFaceCount": 420,
                "prototypeEdgeCount": 860,
                "prototypeCurvedFaceCount": 30,
                "prototypeCurvedEdgeCount": 70,
                "occurrenceFaceCount": 2957,
                "occurrenceEdgeCount": 6012,
                "occurrenceCurvedFaceCount": 80,
                "occurrenceCurvedEdgeCount": 120,
                "leafOccurrenceCount": 481,
                "complexityScore": 18083.7,
                "effectiveComplexityScore": 18083.7,
                "curvaturePressureScore": 280.0,
            },
        ):
            resolution = adaptive_mesh_resolution_for_scene(
                LoadedStepScene(step_path=Path("repeated-low-curvature.step"), roots=[], prototype_shapes={})
            )

        self.assertEqual("balanced-assembly", resolution.profile)
        self.assertEqual(0.016, resolution.settings.tolerance)
        self.assertEqual(0.5, resolution.settings.angular_tolerance)

    def test_adaptive_mesh_resolution_uses_large_topology_profile_for_extreme_imports(self) -> None:
        with mock.patch.object(
            step_scene,
            "_scene_mesh_resolution_hints",
            return_value={
                "bboxDiag": None,
                "prototypeFaceCount": 12000,
                "prototypeEdgeCount": 30000,
                "prototypeCurvedFaceCount": 4000,
                "prototypeCurvedEdgeCount": 12000,
                "occurrenceFaceCount": 23000,
                "occurrenceEdgeCount": 59000,
                "occurrenceCurvedFaceCount": 8000,
                "occurrenceCurvedEdgeCount": 24000,
                "leafOccurrenceCount": 120,
                "complexityScore": 60000.0,
                "effectiveComplexityScore": 60000.0,
                "curvaturePressureScore": 38000.0,
            },
        ):
            resolution = adaptive_mesh_resolution_for_scene(
                LoadedStepScene(step_path=Path("huge.step"), roots=[], prototype_shapes={})
            )

        self.assertEqual("large-topology", resolution.profile)
        self.assertGreater(resolution.settings.tolerance, DEFAULT_MESH_TOLERANCE)
        self.assertGreater(resolution.settings.angular_tolerance, DEFAULT_MESH_ANGULAR_TOLERANCE)

    def test_adaptive_mesh_resolution_uses_curvature_pressure_before_raw_counts_explode(self) -> None:
        with mock.patch.object(
            step_scene,
            "_scene_mesh_resolution_hints",
            return_value={
                "bboxDiag": 120.0,
                "prototypeFaceCount": 700,
                "prototypeEdgeCount": 1600,
                "prototypeCurvedFaceCount": 550,
                "prototypeCurvedEdgeCount": 1500,
                "occurrenceFaceCount": 700,
                "occurrenceEdgeCount": 1600,
                "occurrenceCurvedFaceCount": 550,
                "occurrenceCurvedEdgeCount": 1500,
                "leafOccurrenceCount": 8,
                "complexityScore": 2100.0,
                "effectiveComplexityScore": 2100.0,
                "curvaturePressureScore": 3600.0,
            },
        ):
            resolution = adaptive_mesh_resolution_for_scene(
                LoadedStepScene(step_path=Path("curvy.step"), roots=[], prototype_shapes={})
            )

        self.assertEqual("medium", resolution.profile)
        self.assertEqual(0.014, resolution.settings.tolerance)
        self.assertEqual(0.45, resolution.settings.angular_tolerance)


if __name__ == "__main__":
    unittest.main()
