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

from cadgen._internal import step_scene
from cadgen._internal import step_scene_mesh
from cadgen._internal.step_scene import (
    LoadedStepScene,
    OccurrenceNode,
    adaptive_mesh_resolution_for_scene,
    load_step_scene,
    scene_occurrence_shape,
)
from cadgen._internal.glb_topology import STEP_TOPOLOGY_SCHEMA_VERSION
from tests.python.support.tmp_root import temporary_directory


# The adaptive resolver returns a PROFILE and the hints behind it, and nothing
# else: the deflection numbers it used to carry reached no tessellator and are
# gone. The profile is load-bearing because
# generation_spec._edge_visibility_classes_for_resolution turns it into the
# edge classes a tree renders, so these tests assert profiles and hints.


class StepSceneSelectorArtifactTests(unittest.TestCase):
    def test_load_step_scene_cached_reads_the_render_package(self) -> None:
        # The tree IS the warm-load store: once an entry is built,
        # loading its scene must not touch the text-STEP parser again.
        with temporary_directory(prefix="cad-step-scene-package-") as temp_dir:
            temp_root = Path(temp_dir)
            step_path = temp_root / "box.step"
            build123d.export_step(build123d.Box(1, 1, 1), step_path)

            first = step_scene.load_step_scene_cached(step_path)
            self.assertEqual(1, len(first.prototype_shapes))

            from cadgen.step_artifact_cli import build_step_artifact

            build_step_artifact(repo_root=temp_root, step=step_path)
            with mock.patch(
                "cadgen._internal.step_scene_package.load_step_scene",
                side_effect=AssertionError("package miss"),
            ):
                cached = step_scene.load_step_scene_cached(step_path)

            self.assertEqual(first.step_hash, cached.step_hash)
            self.assertEqual(1, len(cached.roots))
            self.assertEqual(1, len(cached.prototype_shapes))
            self.assertFalse(scene_occurrence_shape(cached, cached.roots[0]).IsNull())

    def test_package_roundtrip_restores_locations_and_face_colors(self) -> None:
        # scene -> compound -> package -> scene: placements and per-face colors
        # survive (colors ride the component .surf, keyed by face ordinal).
        with temporary_directory(prefix="cad-step-scene-package-rt-") as temp_dir:
            temp_root = Path(temp_dir)
            shape = build123d.Box(1, 1, 1).wrapped
            explorer = TopExp_Explorer(shape, TopAbs_FACE)
            face_hash = step_scene._shape_hash(TopoDS.Face_s(explorer.Current()))
            transform = (
                1.0, 0.0, 0.0, 5.0,
                0.0, 1.0, 0.0, 0.0,
                0.0, 0.0, 1.0, 0.0,
                0.0, 0.0, 0.0, 1.0,
            )
            step_path = temp_root / "synthetic.step"
            step_path.write_text("synthetic package key only", encoding="utf-8")
            from cadgen._internal.step_scene_loader import _location_from_transform_matrix

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
                        location=_location_from_transform_matrix(transform),
                    )
                ],
                prototype_shapes={7: shape},
                prototype_face_colors={7: {face_hash: (1.0, 0.0, 0.0, 1.0)}},
            )

            from cadgen._internal.step_hash import step_file_hash
            from tests.python.support.store_fixtures import build_view
            from cadgen._internal.step_scene_mesh import scene_to_build123d_compound
            from cadgen._internal.step_scene_package import scene_from_render_package
            from cadgen.catalog import result_view_dir
            from cadgen.coordination import artifact_build
            from cadgen.coordination.kinds import STEP_PACKAGE

            compound = scene_to_build123d_compound(scene)
            package_dir = result_view_dir(step_path)
            step_hash = step_file_hash(step_path)
            from cadgen.store.records import write_record

            with artifact_build(STEP_PACKAGE, package_dir):
                built = build_view(
                    compound,
                    package_dir=package_dir,
                    root_name="synthetic",
                    single_component=False,
                    provenance={"stepHash": step_hash, "sourceKind": "step"},
                )
            write_record(
                step_path,
                {"sourceKind": "step", "entryKind": "assembly", "tree": built["tree"], "closure": {"hash": step_hash, "files": [], "static": True}, "children": [], "outputs": {}, "stepHash": step_hash},
            )

            from cadgen.store.records import note_document_tree

            note_document_tree(step_hash, built["tree"])  # the artifact side: these bytes -> this tree
            restored = scene_from_render_package(step_path, step_hash=step_hash)
            self.assertIsNotNone(restored)
            assert restored is not None
            self.assertEqual(
                1, sum(len(colors) for colors in restored.prototype_face_colors.values())
            )
            self.assertEqual(
                [(1.0, 0.0, 0.0, 1.0)],
                [next(iter(colors.values())) for colors in restored.prototype_face_colors.values()],
            )
            located = scene_occurrence_shape(restored, restored.roots[0])
            bounds = Bnd_Box()
            BRepBndLib.Add_s(located, bounds)
            x_min, _y_min, _z_min, x_max, _y_max, _z_max = bounds.Get()
            self.assertGreater(x_min, 4.0)
            self.assertGreater(x_max, 5.0)

    def test_adaptive_mesh_resolution_prefers_finer_defaults_for_small_simple_parts(self) -> None:
        with temporary_directory(prefix="cad-adaptive-mesh-") as temp_dir:
            step_path = Path(temp_dir) / "box.step"
            build123d.export_step(build123d.Box(10, 8, 4), step_path)
            scene = load_step_scene(step_path)

            resolution = adaptive_mesh_resolution_for_scene(scene)

            self.assertEqual("extra-fine", resolution.profile)
            self.assertEqual(1, resolution.hints["leafOccurrenceCount"])

    def test_adaptive_mesh_resolution_scales_scores_up_for_meter_scale_models(self) -> None:
        # Size reaches the profile through the score scale factor alone: a
        # model past 1.5 m has its complexity and curvature scores multiplied
        # by 1.35 before they meet the ladder's thresholds.
        with temporary_directory(prefix="cad-adaptive-mesh-") as temp_dir:
            step_path = Path(temp_dir) / "big_box.step"
            build123d.export_step(build123d.Box(2600, 1300, 1300), step_path)
            scene = load_step_scene(step_path)

            resolution = adaptive_mesh_resolution_for_scene(scene)

            diagonal = float(resolution.hints["bboxDiag"])
            self.assertGreater(diagonal, 1500.0)
            self.assertAlmostEqual(
                resolution.hints["effectiveComplexityScore"],
                round(float(resolution.hints["complexityScore"]) * 1.35, 3),
                places=3,
            )

    def test_adaptive_mesh_resolution_keeps_diagonal_for_high_face_count_scenes(self) -> None:
        # A face-count guard used to skip the bbox/diagonal computation for
        # scenes with >=8000 occurrence faces, so bboxDiag came back None and
        # the size scale factor silently no-oped on exactly the scenes that
        # need it (e.g. a full launch stack with dozens of engines). 1,400
        # instances x 6 faces = 8,400 occurrence faces, spread over ~14 m.
        box_shape = build123d.Box(10.0, 8.0, 4.0).wrapped

        def translated(tx: float) -> tuple[float, ...]:
            return (
                1.0, 0.0, 0.0, tx,
                0.0, 1.0, 0.0, 0.0,
                0.0, 0.0, 1.0, 0.0,
                0.0, 0.0, 0.0, 1.0,
            )

        scene = LoadedStepScene(
            step_path=Path("synthetic-stack.step"),
            roots=[
                OccurrenceNode(
                    path=(index + 1,),
                    name=f"box_{index}",
                    source_name=f"box_{index}",
                    transform=translated(index * 10.0),
                    prototype_key=1,
                )
                for index in range(1400)
            ],
            prototype_shapes={1: box_shape},
        )

        resolution = adaptive_mesh_resolution_for_scene(scene)

        self.assertGreaterEqual(resolution.hints["occurrenceFaceCount"], 8000)
        diagonal = resolution.hints["bboxDiag"]
        self.assertIsNotNone(diagonal)
        self.assertGreater(float(diagonal), 1500.0)
        self.assertAlmostEqual(
            resolution.hints["effectiveComplexityScore"],
            round(float(resolution.hints["complexityScore"]) * 1.35, 3),
            places=3,
        )

    def test_adaptive_mesh_resolution_leaves_desk_scale_scores_unscaled(self) -> None:
        with temporary_directory(prefix="cad-adaptive-mesh-") as temp_dir:
            step_path = Path(temp_dir) / "medium_box.step"
            build123d.export_step(build123d.Box(200, 120, 80), step_path)
            scene = load_step_scene(step_path)

            resolution = adaptive_mesh_resolution_for_scene(scene)

            self.assertEqual(
                resolution.hints["complexityScore"],
                resolution.hints["effectiveComplexityScore"],
            )

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
        self.assertEqual(100, resolution.hints["leafOccurrenceCount"])

    def test_adaptive_mesh_resolution_keeps_many_low_curvature_occurrences_balanced(self) -> None:
        with mock.patch.object(
            step_scene_mesh,
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

    def test_adaptive_mesh_resolution_uses_large_topology_profile_for_extreme_imports(self) -> None:
        with mock.patch.object(
            step_scene_mesh,
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

    def test_adaptive_mesh_resolution_uses_curvature_pressure_before_raw_counts_explode(self) -> None:
        with mock.patch.object(
            step_scene_mesh,
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


if __name__ == "__main__":
    unittest.main()
