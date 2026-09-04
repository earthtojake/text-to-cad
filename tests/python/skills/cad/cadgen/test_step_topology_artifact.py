import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cadgen import step_topology_artifact as step_artifacts
from cadgen._internal import generation
from cadgen.step_targets import ResolvedStepTarget, StepTopologyArtifact


class StepArtifactsTests(unittest.TestCase):
    def test_a_target_resolves_to_its_document_and_never_to_a_script(self) -> None:
        # DOCUMENTS-ONLY (design/pose-animation-split.md, CLI/doors follow-on):
        # the artifact resolver used to walk a target back to a `.py` generator
        # and re-run it, which is how a render could contain a build. That
        # layer is deleted — a spec is built from the document, full stop.
        self.assertFalse(hasattr(step_artifacts, "_python_source_for_target"))
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            step_path = root / "part.step"
            source_path = root / "part.py"
            step_path.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
            source_path.write_text(
                "from cadgen import step\n@step\ndef model():\n    return None\n",
                encoding="utf-8",
            )

            target = ResolvedStepTarget(
                cad_path="part",
                source_path=source_path,
                step_path=step_path,
            )
            spec = step_artifacts._entry_spec_for_target(
                target, mesh_tolerance=None, mesh_angular_tolerance=None
            )
            # Imported, even with a same-stem script sitting right beside it.
            self.assertEqual(spec.source, "imported")
            self.assertIsNone(spec.script_path)
            # Resolved once at the door (a temp dir under macOS's /var symlink).
            self.assertEqual(spec.step_path, step_path.resolve())

    def test_a_missing_document_is_an_error_not_a_generator_hunt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            step_path = root / "part.step"
            generator_path = root / "part.py"
            generator_path.write_text(
                "from cadgen import step\n@step\ndef model():\n    return None\n",
                encoding="utf-8",
            )

            target = ResolvedStepTarget(
                cad_path="part",
                source_path=step_path,
                step_path=step_path,
            )
            with self.assertRaises(FileNotFoundError):
                step_artifacts._entry_spec_for_target(
                    target, mesh_tolerance=None, mesh_angular_tolerance=None
                )

    def test_existing_step_spec_can_reuse_python_backed_glb_when_step_hash_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            step_path = root / "part.step"
            step_path.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")

            spec = generation.EntrySpec(
                source_ref="part.step",
                cad_ref="part",
                source_path=step_path,
                display_name="part",
                source="imported",
                step_path=step_path,
            )
            # An imported spec accepts ANY resolved package — content keying
            # already guarantees the tree is these bytes' render, so no
            # stepHash presence check remains.
            self.assertTrue(
                generation._artifact_source_kind_matches_spec(
                    spec, {"_sourceSidecar": {"sourceKind": "python"}}
                )
            )
            self.assertTrue(
                generation._artifact_source_kind_matches_spec(spec, {})
            )


class EnsureStepTopologyArtifactDebugTests(unittest.TestCase):
    """`debug` is an opt-in out-param: passing a dict fills in which build strategy
    ensure_step_topology_artifact took, without changing behavior for callers (the
    everyday-usage default) that leave it None."""

    def _spec(self, *, source: str, step_path: Path) -> generation.EntrySpec:
        return generation.EntrySpec(
            source_ref="part.py" if source == "generated" else "part.step",
            cad_ref="part",
            source_path=step_path,
            display_name="part",
            source=source,
            step_path=step_path,
        )

    def _fake_artifact(self, step_path: Path) -> StepTopologyArtifact:
        return StepTopologyArtifact(
            cad_path="part",
            source_path=step_path,
            step_path=step_path,
            artifact_path=step_path.parent / "package",
            manifest={},
        )

    def test_part_without_package_regenerates_and_reports_it(self) -> None:
        # No tree -> nothing to cache-hit (the tree IS the only
        # artifact form): the entry regenerates and the debug record says so.
        with tempfile.TemporaryDirectory() as temp:
            step_path = Path(temp) / "part.step"
            spec = self._spec(source="imported", step_path=step_path)
            fake_artifact = self._fake_artifact(step_path)
            target = ResolvedStepTarget(cad_path="part", source_path=step_path, step_path=step_path)

            with (
                mock.patch.object(step_artifacts, "_entry_spec_for_target", return_value=spec),
                # First check (fast path): no package yet; second (post-build): built.
                mock.patch(
                    "cadgen._internal.component_package.is_assembly_package",
                    side_effect=[False, True],
                ),
                mock.patch.object(step_artifacts, "_scene_for_regeneration", return_value=(spec, mock.Mock())),
                mock.patch.object(step_artifacts, "_generate_part_outputs"),
                mock.patch.object(step_artifacts, "_assembly_topology_artifact", return_value=fake_artifact),
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
            target = ResolvedStepTarget(cad_path="part", source_path=step_path, step_path=step_path)

            with (
                mock.patch.object(step_artifacts, "_entry_spec_for_target", return_value=spec),
                mock.patch("cadgen._internal.component_package.is_assembly_package", return_value=True),
                mock.patch.object(step_artifacts, "_assembly_topology_artifact", return_value=fake_artifact),
            ):
                artifact = step_artifacts.ensure_step_topology_artifact(target)

            self.assertIs(artifact, fake_artifact)

    def test_assembly_cached_descriptor_is_a_cache_hit_without_selectors(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            step_path = Path(temp) / "asm.step"
            spec = self._spec(source="generated", step_path=step_path)
            target = ResolvedStepTarget(cad_path="asm", source_path=step_path, step_path=step_path)
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

    def test_assembly_descriptor_lookup_hits_for_both_entry_forms(self) -> None:
        # A generated model's package is keyed by the STEP file it produces, so
        # entry_path (<name>.py) and step_path (<name>.step) resolve to the
        # SAME view directory — an assembly.json lookup by either form always hits.
        # (Before the re-key these were two namespaces and step_path lookups
        # missed, forcing a full selector re-extraction on every call.)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            step_path = root / "part.step"
            script_path = root / "part.py"
            from cadgen.metadata import GeneratorMetadata

            spec = generation.EntrySpec(
                source_ref="part.py",
                cad_ref="part",
                source_path=script_path,
                display_name="part",
                source="generated",
                step_path=step_path,
                script_path=script_path,
                generator_metadata=GeneratorMetadata(
                    script_path=script_path,
                    display_name=None,
                    generator_names=("model",),
                    format="step",
                    mesh_tolerance=None,
                    mesh_angular_tolerance=None,
                    entry_function="model",
                    out_target=None,
                    is_decorated=True,
                ),
            )
            target = ResolvedStepTarget(
                cad_path="part", source_path=script_path, step_path=step_path
            )
            descriptor = {"kind": "component-glb-package"}
            entry_package_dir = step_artifacts.result_view_dir(spec.entry_path)
            step_package_dir = step_artifacts.result_view_dir(spec.step_path)
            self.assertEqual(entry_package_dir, step_package_dir)

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

    def test_assembly_mid_write_descriptor_is_retried_not_reextracted(self) -> None:
        # An assembly.json that is momentarily absent (the writer swaps
        # assembly.json atomically) is RE-READ, never re-extracted: the OCP
        # whole-model selector extractor is gone, so waiting for the writer is
        # the only pre-composition behaviour left.
        with tempfile.TemporaryDirectory() as temp:
            step_path = Path(temp) / "asm.step"
            spec = self._spec(source="generated", step_path=step_path)
            target = ResolvedStepTarget(cad_path="asm", source_path=step_path, step_path=step_path)
            descriptor = {"kind": "assembly-package", "components": {"c0": {}}}

            with (
                mock.patch.object(step_artifacts, "_entry_spec_for_target", return_value=spec),
                mock.patch("cadgen._internal.component_package.is_assembly_package", return_value=True),
                mock.patch(
                    "cadgen._internal.component_package.read_package_descriptor",
                    side_effect=[None, None, descriptor],
                ),
            ):
                debug: dict[str, object] = {}
                artifact = step_artifacts.ensure_step_topology_artifact(target, require_selector=True, debug=debug)

            self.assertEqual(artifact.manifest, descriptor)
            self.assertIsNotNone(artifact.selector_bundle)
            self.assertEqual(artifact.selector_bundle.manifest, descriptor)
            self.assertTrue(debug["assembly"])
            self.assertFalse(debug["cacheHit"])
            self.assertTrue(debug["descriptorRetried"])


if __name__ == "__main__":
    unittest.main()
