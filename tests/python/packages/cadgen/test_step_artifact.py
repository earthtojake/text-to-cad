from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen import step_artifact_cli  # noqa: E402
from cadgen import step_export_target  # noqa: E402
from tests.python.support.cad_test_roots import IsolatedCadRoots  # noqa: E402

# A tiny generated model: model() returns a single labeled solid.
BOX_GENERATOR = """from build123d import Box


from cadgen import step
@step
def model():
    return Box(10.0, 10.0, 10.0)


if __name__ == "__main__":
    model()
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
        generator = self.temp_root / "box.py"
        generator.write_text(BOX_GENERATOR, encoding="utf-8")
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

        # force=True: this fixture is deliberately a cadgen-EXPORTED file being
        # re-imported, which the generated-step guard otherwise refuses
        # (test_generated_step_fidelity pins that refusal).
        payload = step_artifact_cli.build_step_artifact(
            repo_root=Path.cwd(),
            step=imported_step,
            force=True,
        )

        self.assertTrue(payload.get("ok"), payload)
        self.assertEqual("part", payload.get("entryKind"))
        # The payload names the RESULT — the tree these bytes compiled to — not a
        # directory: nothing of the sort exists in the store.
        from cadgen.store.objects import has_object
        from cadgen.store.trees import get_tree

        tree = str(payload.get("tree") or "")
        self.assertTrue(tree, payload)
        self.assertTrue(has_object(tree), payload)
        self.assertTrue(get_tree(tree).get("components"), payload)

    def test_imported_step_build_accepts_kind_override(self) -> None:
        imported_step = self._materialize_imported_step()

        payload = step_artifact_cli.build_step_artifact(
            repo_root=Path.cwd(),
            step=imported_step,
            kind="assembly",
            force=True,
        )

        self.assertTrue(payload.get("ok"), payload)
        # The override is accepted (it steers how the build packages its own
        # geometry), but entryKind is read off the tree: one solid, one
        # occurrence, so a part -- the same answer inspect and a model run give.
        self.assertEqual("part", payload.get("entryKind"))


if __name__ == "__main__":
    unittest.main()
