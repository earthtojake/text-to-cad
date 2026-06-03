import tempfile
import unittest
from pathlib import Path

from cadpy_common import generation as common_generation
from cadpy_common import step_artifacts as common_step_artifacts
from cadpy_common.package_path import ensure_cadpy_package_path
from cadpy_common.step_targets import ResolvedStepTarget as CommonResolvedStepTarget

ensure_cadpy_package_path()

from cadpy import generation as package_generation
from cadpy import step_artifacts as package_step_artifacts
from cadpy.step_targets import ResolvedStepTarget as PackageResolvedStepTarget


class StepArtifactsTests(unittest.TestCase):
    def test_existing_step_target_ignores_python_source_for_glb_regeneration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            step_path = root / "part.step"
            source_path = root / "part.py"
            step_path.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
            source_path.write_text("def gen_step():\n    return None\n", encoding="utf-8")

            cases = (
                (common_step_artifacts, CommonResolvedStepTarget),
                (package_step_artifacts, PackageResolvedStepTarget),
            )
            for module, target_type in cases:
                with self.subTest(module=module.__name__):
                    target = target_type(
                        cad_path="part",
                        kind="part",
                        source_path=source_path,
                        step_path=step_path,
                    )
                    self.assertIsNone(module._python_source_for_target(target))

    def test_missing_logical_step_can_still_use_python_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            step_path = root / "part.step"
            source_path = root / "part.py"
            source_path.write_text("def gen_step():\n    return None\n", encoding="utf-8")

            cases = (
                (common_step_artifacts, CommonResolvedStepTarget),
                (package_step_artifacts, PackageResolvedStepTarget),
            )
            for module, target_type in cases:
                with self.subTest(module=module.__name__):
                    target = target_type(
                        cad_path="part",
                        kind="part",
                        source_path=step_path,
                        step_path=step_path,
                    )
                    self.assertEqual(module._python_source_for_target(target), source_path)

    def test_existing_step_spec_can_reuse_python_backed_glb_when_step_hash_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            step_path = root / "part.step"
            step_path.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")

            cases = (common_generation, package_generation)
            for module in cases:
                with self.subTest(module=module.__name__):
                    spec = module.EntrySpec(
                        source_ref="part.step",
                        cad_ref="part",
                        kind="part",
                        source_path=step_path,
                        display_name="part",
                        source="imported",
                        step_path=step_path,
                    )
                    self.assertFalse(module._artifact_source_kind_matches_spec(spec, {"sourceKind": "python"}))
                    self.assertTrue(
                        module._artifact_source_kind_matches_spec(
                            spec,
                            {
                                "sourceKind": "python",
                                "stepHash": module.step_file_hash(step_path),
                            },
                        )
                    )


if __name__ == "__main__":
    unittest.main()
