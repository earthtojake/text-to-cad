from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen import step_artifact  # noqa: E402
from cadgen import step_export_target  # noqa: E402
from tests.python.support.cad_test_roots import IsolatedCadRoots  # noqa: E402

# A tiny generated model: gen_step() returns a single labeled solid.
BOX_GENERATOR = """from build123d import Box


def gen_step():
    return Box(10.0, 10.0, 10.0)
"""


class BuildStepArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self._isolated_roots = IsolatedCadRoots(self, prefix="cadart-")
        self._tempdir = self._isolated_roots.temporary_cad_directory(prefix="tmp-cadart-")
        self.temp_root = Path(self._tempdir.name)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_root, ignore_errors=True)
        self._tempdir.cleanup()

    def _materialize_imported_step(self) -> Path:
        generator = self.temp_root / "box.step.py"
        generator.write_text(BOX_GENERATOR)
        imported_step = self.temp_root / "imported.step"
        step_export_target.export_model_to_path(
            repo_root=Path.cwd(),
            step=self.temp_root / "box.step",
            fmt="step",
            out=imported_step,
            source_path=generator,
        )
        self.assertTrue(imported_step.is_file())
        return imported_step

    def test_imported_step_build_infers_kind(self) -> None:
        """Regression: the imported-STEP branch of build_step_artifact (the CAD Viewer's
        on-demand render-package build) must run kind inference, not require a caller
        kind."""
        imported_step = self._materialize_imported_step()

        payload = step_artifact.build_step_artifact(
            repo_root=Path.cwd(),
            step=imported_step,
        )

        self.assertTrue(payload.get("ok"), payload)
        self.assertEqual("part", payload.get("entryKind"))
        package_path = Path(str(payload.get("packagePath")))
        if not package_path.is_absolute():
            package_path = Path.cwd() / package_path
        self.assertTrue(package_path.is_dir(), payload)
        self.assertTrue((package_path / "assembly.json").is_file(), payload)

    def test_imported_step_build_accepts_kind_override(self) -> None:
        imported_step = self._materialize_imported_step()

        payload = step_artifact.build_step_artifact(
            repo_root=Path.cwd(),
            step=imported_step,
            kind="assembly",
            force=True,
        )

        self.assertTrue(payload.get("ok"), payload)
        self.assertEqual("assembly", payload.get("entryKind"))


if __name__ == "__main__":
    unittest.main()
