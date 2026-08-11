import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cadgen import step_artifacts
from cadgen._internal import generation
from cadgen.step_targets import ResolvedStepTarget, StepTopologyArtifact


class StepArtifactsTests(unittest.TestCase):
    def test_existing_step_target_ignores_python_source_for_glb_regeneration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            step_path = root / "part.step"
            source_path = root / "part.py"
            step_path.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
            source_path.write_text("def gen_step():\n    return None\n", encoding="utf-8")

            target = ResolvedStepTarget(
                cad_path="part",
                kind="part",
                source_path=source_path,
                step_path=step_path,
            )
            self.assertIsNone(step_artifacts._python_source_for_target(target))

    def test_explicit_python_target_wins_over_same_stem_step_export(self) -> None:
        # A `<name>.step.py` generator explicitly targeted by the caller keeps
        # resolving to the generator even when its same-stem exported
        # `<name>.step` exists beside it (entry-keyed coexistence).
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            step_path = root / "part.step"
            source_path = root / "part.step.py"
            step_path.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
            source_path.write_text("def gen_step():\n    return None\n", encoding="utf-8")

            target = ResolvedStepTarget(
                cad_path="part",
                kind="part",
                source_path=source_path,
                step_path=step_path,
                explicit_python=True,
            )
            self.assertEqual(step_artifacts._python_source_for_target(target), source_path)

    def test_non_explicit_step_target_with_same_stem_export_stays_imported(self) -> None:
        # Without an explicit .py target, an existing .step file keeps its
        # documented direct-import semantics even when a generator exists.
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            step_path = root / "part.step"
            source_path = root / "part.step.py"
            step_path.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
            source_path.write_text("def gen_step():\n    return None\n", encoding="utf-8")

            target = ResolvedStepTarget(
                cad_path="part",
                kind="part",
                source_path=source_path,
                step_path=step_path,
            )
            self.assertIsNone(step_artifacts._python_source_for_target(target))

    def test_missing_logical_step_finds_step_py_convention_generator(self) -> None:
        # The generator for `<name>.step` is `<name>.step.py` under the entry
        # convention; the fallback must find it when no .step file exists.
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            step_path = root / "part.step"
            generator_path = root / "part.step.py"
            generator_path.write_text("def gen_step():\n    return None\n", encoding="utf-8")

            target = ResolvedStepTarget(
                cad_path="part",
                kind="part",
                source_path=step_path,
                step_path=step_path,
            )
            self.assertEqual(step_artifacts._python_source_for_target(target), generator_path)

    def test_existing_step_spec_can_reuse_python_backed_glb_when_step_hash_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            step_path = root / "part.step"
            step_path.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")

            spec = generation.EntrySpec(
                source_ref="part.step",
                cad_ref="part",
                kind="part",
                source_path=step_path,
                display_name="part",
                source="imported",
                step_path=step_path,
            )
            self.assertFalse(generation._artifact_source_kind_matches_spec(spec, {"sourceKind": "python"}))
            self.assertTrue(
                generation._artifact_source_kind_matches_spec(
                    spec,
                    {
                        "sourceKind": "python",
                        "stepHash": generation.step_file_hash(step_path),
                    },
                )
            )


class EnsureStepTopologyArtifactDebugTests(unittest.TestCase):
    """`debug` is an opt-in out-param: passing a dict fills in which build strategy
    ensure_step_topology_artifact took, without changing behavior for callers (the
    everyday-usage default) that leave it None."""

    def _spec(self, *, source: str, step_path: Path) -> generation.EntrySpec:
        return generation.EntrySpec(
            source_ref="part.step.py" if source == "generated" else "part.step",
            cad_ref="part",
            kind="part",
            source_path=step_path,
            display_name="part",
            source=source,
            step_path=step_path,
        )

    def _fake_artifact(self, step_path: Path) -> StepTopologyArtifact:
        return StepTopologyArtifact(
            cad_path="part",
            kind="part",
            source_path=step_path,
            step_path=step_path,
            artifact_path=step_path.parent / "package",
            manifest={},
        )

    def test_part_cache_hit_reports_no_regeneration(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            step_path = Path(temp) / "part.step"
            spec = self._spec(source="generated", step_path=step_path)
            fake_artifact = self._fake_artifact(step_path)
            target = ResolvedStepTarget(cad_path="part", kind="part", source_path=step_path, step_path=step_path)

            with (
                mock.patch.object(step_artifacts, "_entry_spec_for_target", return_value=spec),
                mock.patch("cadgen._internal.component_package.is_assembly_package", return_value=False),
                mock.patch.object(step_artifacts, "_current_artifact_for_spec", return_value=fake_artifact),
            ):
                debug: dict[str, object] = {}
                artifact = step_artifacts.ensure_step_topology_artifact(target, debug=debug)

            self.assertIs(artifact, fake_artifact)
            self.assertEqual(debug["source"], "generated")
            self.assertFalse(debug["assembly"])
            self.assertTrue(debug["cacheHit"])
            self.assertNotIn("selectorReextracted", debug)
            self.assertIsInstance(debug["tookMs"], float)
            self.assertGreaterEqual(debug["tookMs"], 0)

    def test_part_cache_miss_triggers_regeneration_and_reports_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            step_path = Path(temp) / "part.step"
            spec = self._spec(source="imported", step_path=step_path)
            fake_artifact = self._fake_artifact(step_path)
            target = ResolvedStepTarget(cad_path="part", kind="part", source_path=step_path, step_path=step_path)

            with (
                mock.patch.object(step_artifacts, "_entry_spec_for_target", return_value=spec),
                mock.patch("cadgen._internal.component_package.is_assembly_package", return_value=False),
                mock.patch.object(step_artifacts, "_current_artifact_for_spec", return_value=None),
                mock.patch.object(step_artifacts, "_scene_for_regeneration", return_value=(spec, mock.Mock())),
                mock.patch.object(step_artifacts, "_generate_part_outputs"),
                mock.patch.object(step_artifacts, "validate_step_topology_artifact", return_value=fake_artifact),
            ):
                debug: dict[str, object] = {}
                artifact = step_artifacts.ensure_step_topology_artifact(target, debug=debug)

            self.assertIs(artifact, fake_artifact)
            self.assertEqual(debug["source"], "imported")
            self.assertFalse(debug["assembly"])
            self.assertFalse(debug["cacheHit"])
            self.assertIsInstance(debug["tookMs"], float)

    def test_debug_none_is_a_no_op(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            step_path = Path(temp) / "part.step"
            spec = self._spec(source="generated", step_path=step_path)
            fake_artifact = self._fake_artifact(step_path)
            target = ResolvedStepTarget(cad_path="part", kind="part", source_path=step_path, step_path=step_path)

            with (
                mock.patch.object(step_artifacts, "_entry_spec_for_target", return_value=spec),
                mock.patch("cadgen._internal.component_package.is_assembly_package", return_value=False),
                mock.patch.object(step_artifacts, "_current_artifact_for_spec", return_value=fake_artifact),
            ):
                artifact = step_artifacts.ensure_step_topology_artifact(target)

            self.assertIs(artifact, fake_artifact)

    def test_assembly_cached_descriptor_is_a_cache_hit_without_selectors(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            step_path = Path(temp) / "asm.step"
            spec = self._spec(source="generated", step_path=step_path)
            target = ResolvedStepTarget(cad_path="asm", kind="assembly", source_path=step_path, step_path=step_path)
            descriptor = {"kind": "component-glb-package"}

            with (
                mock.patch.object(step_artifacts, "_entry_spec_for_target", return_value=spec),
                mock.patch("cadgen._internal.component_package.is_assembly_package", return_value=True),
                mock.patch("cadgen._internal.component_package.read_package_descriptor", return_value=descriptor),
            ):
                debug: dict[str, object] = {}
                artifact = step_artifacts.ensure_step_topology_artifact(target, require_selector=False, debug=debug)

            self.assertEqual(artifact.manifest, descriptor)
            self.assertTrue(debug["assembly"])
            self.assertTrue(debug["cacheHit"])
            self.assertFalse(debug["selectorReextracted"])

    def test_assembly_descriptor_lookup_uses_entry_path_not_step_path(self) -> None:
        # Regression: a generated model's package is keyed by entry_path (<name>.step.py),
        # which differs from step_path (<name>.step). Looking the descriptor up by
        # step_path always misses, forcing a full selector re-extraction/regeneration
        # on every call even when a fresh package already exists.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            step_path = root / "part.step"
            script_path = root / "part.step.py"
            spec = generation.EntrySpec(
                source_ref="part.step.py",
                cad_ref="part",
                kind="assembly",
                source_path=script_path,
                display_name="part",
                source="generated",
                step_path=step_path,
                script_path=script_path,
            )
            target = ResolvedStepTarget(
                cad_path="part", kind="assembly", source_path=script_path, step_path=step_path
            )
            descriptor = {"kind": "component-glb-package"}
            entry_package_dir = step_artifacts.render_package_dir(spec.entry_path)
            step_package_dir = step_artifacts.render_package_dir(spec.step_path)
            self.assertNotEqual(entry_package_dir, step_package_dir)

            def fake_read_package_descriptor(path: Path) -> dict[str, object] | None:
                return descriptor if path == entry_package_dir else None

            with (
                mock.patch.object(step_artifacts, "_entry_spec_for_target", return_value=spec),
                mock.patch("cadgen._internal.component_package.is_assembly_package", return_value=True),
                mock.patch(
                    "cadgen._internal.component_package.read_package_descriptor",
                    side_effect=fake_read_package_descriptor,
                ),
            ):
                debug: dict[str, object] = {}
                artifact = step_artifacts.ensure_step_topology_artifact(target, require_selector=False, debug=debug)

            self.assertEqual(artifact.manifest, descriptor)
            self.assertTrue(debug["cacheHit"])
            self.assertFalse(debug["selectorReextracted"])

    def test_assembly_selector_request_is_reported_as_reextraction(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            step_path = Path(temp) / "asm.step"
            spec = self._spec(source="generated", step_path=step_path)
            target = ResolvedStepTarget(cad_path="asm", kind="assembly", source_path=step_path, step_path=step_path)
            fake_bundle = mock.Mock(manifest={"selectors": True})

            with (
                mock.patch.object(step_artifacts, "_entry_spec_for_target", return_value=spec),
                mock.patch("cadgen._internal.component_package.is_assembly_package", return_value=True),
                mock.patch.object(step_artifacts, "_scene_for_regeneration", return_value=(spec, mock.Mock())),
                mock.patch("cadgen._internal.generation._effective_step_spec_for_scene", return_value=spec),
                mock.patch("cadgen._internal.generation._selector_options_for_part", return_value=mock.Mock()),
                mock.patch("cadgen._internal.step_scene.mesh_step_scene"),
                mock.patch("cadgen._internal.step_scene.extract_selectors_from_scene", return_value=fake_bundle),
            ):
                debug: dict[str, object] = {}
                artifact = step_artifacts.ensure_step_topology_artifact(target, require_selector=True, debug=debug)

            self.assertEqual(artifact.manifest, fake_bundle.manifest)
            self.assertTrue(debug["assembly"])
            self.assertFalse(debug["cacheHit"])
            self.assertTrue(debug["selectorReextracted"])


if __name__ == "__main__":
    unittest.main()
