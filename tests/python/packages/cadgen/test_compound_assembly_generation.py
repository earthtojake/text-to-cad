from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
import warnings
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal import generation
from cadgen.metadata import parse_generator_metadata
from cadgen.step_export import _create_bin_xcaf_doc, export_build123d_step_scene
from cadgen._internal.step_scene import LoadedStepScene, _bbox_from_shape, scene_leaf_occurrences, scene_occurrence_shape


def _rounded_color(color: tuple[float, ...]) -> tuple[float, ...]:
    return tuple(round(component, 3) for component in color)


def _srgb_to_linear(component: float) -> float:
    if component <= 0.04045:
        return component / 12.92
    return ((component + 0.055) / 1.055) ** 2.4


class CompoundAssemblyGenerationTests(unittest.TestCase):
    def test_step_payload_rejects_legacy_output_field(self) -> None:
        with self.assertRaisesRegex(TypeError, "unsupported field\\(s\\): step_output"):
            generation._normalize_step_payload(
                {"shape": object(), "step_output": "legacy.step"},
                script_path=Path("part.py"),
            )

    def test_step_payload_rejects_assembly_mates_envelope_field(self) -> None:
        # assembly_mates is hard-deprecated as an envelope field. Semantic mates now
        # ride on the returned shape (compound.assembly_mates) and are collected at
        # export, so a gen_step() envelope must never carry an assembly_mates key.
        with self.assertRaisesRegex(TypeError, "unsupported field\\(s\\): assembly_mates"):
            generation._normalize_step_payload(
                {
                    "shape": object(),
                    "assembly_mates": [{"sourceLabel": "servo_to_bracket"}],
                },
                script_path=Path("assembly.py"),
            )

    def test_shape_assembly_mates_attribute_round_trips_to_scene(self) -> None:
        # Mates set on the returned compound survive STEP-scene export onto
        # scene.assembly_mates with canonical m{n} ids — the replacement for the
        # removed assembly_mates envelope field.
        import build123d

        with tempfile.TemporaryDirectory(prefix="cadgen-compound-") as tempdir:
            left = build123d.Box(1, 1, 1)
            left.label = "servo"
            right = build123d.Pos(2, 0, 0) * build123d.Box(1, 1, 1)
            right.label = "bracket"
            shape = build123d.Compound(children=[left, right], label="assembly")
            shape.assembly_mates = [
                {
                    "sourceLabel": "servo_to_bracket",
                    "relation": "rigid",
                    "fixed": "servo:mount",
                    "moving": "bracket:foot",
                }
            ]

            scene = export_build123d_step_scene(
                shape,
                Path(tempdir) / "assembly.step",
                text_to_cad_entry_kind="assembly",
            )

        self.assertEqual(
            [
                {
                    "id": "m1",
                    "label": "m1",
                    "sourceLabel": "servo_to_bracket",
                    "relation": "rigid",
                    "fixed": "servo:mount",
                    "moving": "bracket:foot",
                }
            ],
            scene.assembly_mates,
        )

    def test_dxf_payload_rejects_legacy_output_field(self) -> None:
        with self.assertRaisesRegex(TypeError, "unsupported field\\(s\\): dxf_output"):
            generation._normalize_dxf_payload(
                {"document": object(), "dxf_output": "legacy.dxf"},
                script_path=Path("part.py"),
            )

    def test_metadata_rejects_legacy_output_fields(self) -> None:
        cases = [
            ("gen_step", "return {'shape': object(), 'step_output': 'legacy.step'}", "step_output"),
            ("gen_dxf", "return {'document': object(), 'dxf_output': 'legacy.dxf'}", "dxf_output"),
        ]
        for function_name, return_line, field_name in cases:
            with self.subTest(function_name=function_name), tempfile.TemporaryDirectory(prefix="cadgen-output-field-") as tempdir:
                script_path = Path(tempdir) / "part.py"
                script_path.write_text(
                    "\n".join(
                        [
                            "def gen_step():",
                            "    return {'shape': object()}",
                            "",
                            f"def {function_name}():",
                            f"    {return_line}",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )

                with self.assertRaisesRegex(ValueError, f"unsupported field\\(s\\): {field_name}"):
                    parse_generator_metadata(script_path)

    def test_run_selected_specs_preserves_action_stdout(self) -> None:
        spec = SimpleNamespace(source_ref="part.py")
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            generation._run_selected_specs(
                [spec],
                action=lambda _spec, _progress_sink=None: print("generator summary"),
                logger=generation.CliLogger("test", stream=io.StringIO()),
                success_message=None,
            )

        self.assertEqual("generator summary\n", stdout.getvalue())

    def test_compound_with_explicit_children_is_discovered_as_assembly(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cadgen-compound-") as tempdir:
            script_path = Path(tempdir) / "robot_arm.py"
            script_path.write_text(
                "\n".join(
                    [
                        "from build123d import Compound",
                        "",
                        "def gen_step():",
                        "    parts = []",
                        "    assembly = Compound(",
                        "        obj=parts,",
                        "        children=parts,",
                        "        label='robot_arm_static_display_pose',",
                        "    )",
                        "    return assembly",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            metadata = parse_generator_metadata(script_path)

        self.assertIsNotNone(metadata)
        self.assertEqual("assembly", metadata.kind)

    def test_compound_with_literal_obj_sequence_is_discovered_as_assembly(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cadgen-compound-") as tempdir:
            script_path = Path(tempdir) / "compound_arm.py"
            script_path.write_text(
                "\n".join(
                    [
                        "from build123d import Box, Compound",
                        "",
                        "def gen_step():",
                        "    left = Box(1, 1, 1)",
                        "    right = Box(1, 1, 1)",
                        "    return Compound(obj=[left, right], label='compound_arm')",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            metadata = parse_generator_metadata(script_path)

        self.assertIsNotNone(metadata)
        self.assertEqual("assembly", metadata.kind)

    def test_childless_compound_obj_sequence_is_runtime_assembly(self) -> None:
        import build123d

        left = build123d.Box(1, 1, 1)
        right = build123d.Box(1, 1, 1)
        shape = build123d.Compound(obj=[left, right], label="compound_arm")

        self.assertEqual("assembly", generation._shape_payload_entry_kind(shape, fallback="part"))

    def test_labeled_childless_compound_does_not_warn_without_color(self) -> None:
        import build123d

        left = build123d.Box(1, 1, 1)
        right = build123d.Box(1, 1, 1)
        shape = build123d.Compound(obj=[left, right], label="compound_arm")

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _create_bin_xcaf_doc(shape)

        messages = [str(item.message) for item in caught]
        self.assertNotIn("Unknown Compound type, color not set", messages)

    def test_colored_bare_compound_leaf_keeps_color_and_does_not_warn(self) -> None:
        # A boolean/chamfer chain can return a bare `Compound` (not
        # Part/Sketch/Curve). Exported alone — the per-component doc path —
        # this used to warn "Unknown Compound type, color not set" and ship
        # the geometry uncolored. The solids inside must get the color.
        import build123d

        solid = build123d.Solid.make_box(1, 1, 1)
        shape = build123d.Compound(obj=[solid])
        self.assertNotIsInstance(shape, build123d.Part)
        shape.label = "bare_leaf"
        shape.color = build123d.Color(1, 0, 0)

        with tempfile.TemporaryDirectory(prefix="cadgen-compound-") as tempdir:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                scene = export_build123d_step_scene(
                    shape,
                    Path(tempdir) / "bare_leaf.step",
                    text_to_cad_entry_kind="part",
                )

        messages = [str(item.message) for item in caught]
        self.assertNotIn("Unknown Compound type, color not set", messages)

        colors = {
            tuple(round(component, 3) for component in color)
            for color in scene.prototype_colors.values()
        }

        def collect(node):
            if node.color is not None:
                colors.add(tuple(round(component, 3) for component in node.color))
            for child in node.children:
                collect(child)

        for root in scene.roots:
            collect(root)
        self.assertIn((1.0, 0.0, 0.0, 1.0), colors)

    def test_colored_child_shapes_survive_compound_assembly_export(self) -> None:
        import build123d

        with tempfile.TemporaryDirectory(prefix="cadgen-compound-") as tempdir:
            left = build123d.Box(1, 1, 1)
            left.label = "red_child"
            left.color = build123d.Color(1, 0, 0)
            right = build123d.Pos(2, 0, 0) * build123d.Box(1, 1, 1)
            right.label = "blue_child"
            right.color = build123d.Color(0, 0, 1)
            shape = build123d.Compound(children=[left, right], label="colored_assembly")

            scene = export_build123d_step_scene(
                shape,
                Path(tempdir) / "colored_assembly.step",
                text_to_cad_entry_kind="assembly",
            )

        colors = {
            tuple(round(component, 3) for component in color)
            for color in scene.prototype_colors.values()
        }
        colors.update(
            tuple(round(component, 3) for component in node.color)
            for root in scene.roots
            for node in root.children
            if node.color is not None
        )

        self.assertEqual(1, len(scene.roots))
        self.assertEqual(2, len(scene.roots[0].children))
        self.assertIn((1.0, 0.0, 0.0, 1.0), colors)
        self.assertIn((0.0, 0.0, 1.0, 1.0), colors)

    def test_nested_colored_compound_keeps_parent_transform(self) -> None:
        import build123d

        with tempfile.TemporaryDirectory(prefix="cadgen-compound-") as tempdir:
            child = build123d.Box(1, 1, 1)
            child.label = "motor_body"
            child.color = build123d.Color(0.1, 0.2, 0.3)
            expected_color = _rounded_color(child.color)
            expected_linear_color = _rounded_color(
                (
                    *(_srgb_to_linear(component) for component in expected_color[:3]),
                    expected_color[3],
                )
            )
            nested = build123d.Compound(children=[child], label="imported_motor")
            placed = build123d.Pos(20, 0, 0) * nested
            placed.label = "placed_motor"
            root = build123d.Compound(children=[placed], label="arm")

            scene = export_build123d_step_scene(
                root,
                Path(tempdir) / "arm.step",
                text_to_cad_entry_kind="assembly",
            )

        leaves = scene_leaf_occurrences(scene)
        self.assertEqual(1, len(leaves))
        bbox = _bbox_from_shape(scene_occurrence_shape(scene, leaves[0]))
        self.assertGreater(bbox["min"][0], 19.0)
        self.assertLess(bbox["max"][0], 21.0)
        self.assertIn(
            _rounded_color(leaves[0].color),
            {expected_color, expected_linear_color},
        )

    def test_shape_payload_can_export_with_assembly_entry_kind(self) -> None:
        import build123d

        with tempfile.TemporaryDirectory(prefix="cadgen-compound-") as tempdir:
            script_path = Path(tempdir) / "robot_arm.py"
            script_path.write_text("def gen_step():\n    return None\n", encoding="utf-8")
            output_path = script_path.with_suffix(".step")
            scene = LoadedStepScene(step_path=output_path.resolve(), roots=[], prototype_shapes={})
            left = build123d.Box(1, 1, 1)
            right = build123d.Box(1, 1, 1)
            shape = build123d.Compound(children=[left, right], label="robot_arm")

            with (
                mock.patch.object(
                    generation,
                    "python_source_hash",
                    return_value=SimpleNamespace(
                        source_path="robot_arm.py",
                        source_hash="hash-123",
                    ),
                ),
                mock.patch.object(generation, "build_build123d_step_scene", return_value=scene) as build_scene,
            ):
                result = generation._write_shape_step_payload(
                    {"shape": shape},
                    output_path=output_path,
                    script_path=script_path,
                    logger=generation.CliLogger("test"),
                    entry_kind="assembly",
                )

        # gen_step builds the scene in memory (no STEP write); the entry kind is marked
        # on the scene, and the pre-bake compound is stashed for the package/STEP jobs.
        self.assertIs(result, scene)
        self.assertEqual("python", build_scene.call_args.kwargs["source_kind"])
        self.assertEqual("assembly", getattr(scene, "text_to_cad_entry_kind", None))
        self.assertEqual("shape", getattr(scene, "step_payload_kind", None))
        self.assertIs(shape, getattr(scene, "source_compound", None))

    def test_effective_spec_follows_runtime_shape_entry_kind(self) -> None:
        step_path = Path("/tmp/compound.step")
        scene = LoadedStepScene(step_path=step_path, roots=[], prototype_shapes={})
        scene.text_to_cad_entry_kind = "assembly"
        spec = generation.EntrySpec(
            source_ref="compound.py",
            cad_ref="compound",
            kind="part",
            source_path=Path("/tmp/compound.py"),
            display_name="compound",
            source="generated",
            step_path=step_path,
            script_path=Path("/tmp/compound.py"),
        )

        effective = generation._effective_step_spec_for_scene(spec, scene)

        self.assertEqual("assembly", effective.kind)
        self.assertEqual("part", spec.kind)

    def test_artifact_outputs_use_runtime_shape_entry_kind(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cadgen-compound-") as tempdir:
            step_path = Path(tempdir) / "compound.step"
            script_path = Path(tempdir) / "compound.py"
            scene = LoadedStepScene(step_path=step_path.resolve(), roots=[], prototype_shapes={})
            scene.text_to_cad_entry_kind = "assembly"
            scene.source_kind = "python"
            scene.source_path = "compound.py"
            scene.source_hash = "source-hash"
            spec = generation.EntrySpec(
                source_ref="compound.py",
                cad_ref="compound",
                kind="part",
                source_path=script_path,
                display_name="compound",
                source="generated",
                step_path=step_path,
                script_path=script_path,
            )
            with (
                mock.patch.object(generation, "_existing_topology_artifact_matches_spec_without_scene", return_value=False),
                mock.patch.object(generation, "_existing_topology_artifact_matches_options", return_value=False),
                mock.patch.object(generation, "_selector_options_for_part", return_value=generation.SelectorOptions()),
                mock.patch.object(generation, "_run_artifact_jobs", return_value={}) as run_jobs,
            ):
                result = generation._generate_part_outputs(
                    spec,
                    entries_by_step_path={step_path.resolve(): spec},
                    preloaded_scene=scene,
                    require_step_file=False,
                    force=True,
                )

            # The runtime compound is an assembly, so the effective spec adopts that kind
            # (introspect-children emit) even though the authored spec said "part".
            self.assertEqual("assembly", result.spec.kind)
            # The package is the render artifact; generation returns no selector bundle.
            self.assertIsNone(result.selector_bundle)
            run_jobs.assert_called_once()

if __name__ == "__main__":
    unittest.main()
