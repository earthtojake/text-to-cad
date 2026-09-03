"""A generated model must never be exported by copying its own previous output.

Regression for #308. A model-script run with an explicit write reported ``outcome: built`` and rewrote
``<name>.step`` with the geometry of the PREVIOUS build, so an edited generator kept
producing the old part and `validate`, `snapshot` and the Viewer all inherited it with
nothing raised. The reporter only caught it by comparing a direct ``model()`` call
against the exported file by face count.

The export path takes ``scene.source_compound`` when a generator ran, and otherwise copies
``spec.step_path``. That copy is correct for an IMPORTED source, whose ``step_path`` is the
authored input. For a GENERATED source the same path is its own output, so the copy quietly
reproduces stale geometry. Guarding it turns a silent wrong answer into a loud one.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import repo_path  # noqa: F401  (path bootstrap)

from cadgen.step_export_target import _export_scene


class _Spec:
    def __init__(self, source: str, step_path: Path) -> None:
        self.source = source
        self.kind = "part"
        self.source_ref = "models/part.py"
        self.step_path = step_path
        self.color = None


class _SceneWithoutGeneratorOutput:
    """What the export sees when the scene came from cache rather than a fresh run."""

    source_compound = None
    source_path = ""
    source_hash = ""


class GeneratedStepExportGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(self.enterContext(__import__("tempfile").TemporaryDirectory()))
        self.existing = self.tmp / "part.step"
        self.existing.write_text("ISO-10303-21;\n-- stale geometry from the previous build\n", encoding="utf-8")
        self.out = self.tmp / "out.step"

    def test_a_generated_entry_refuses_to_copy_its_own_previous_output(self) -> None:
        spec = _Spec("generated", self.existing)
        with self.assertRaises(RuntimeError) as caught:
            _export_scene("step", spec, _SceneWithoutGeneratorOutput(), self.out, logger=mock.Mock())
        message = str(caught.exception)
        self.assertIn("refusing to export a generated model", message)
        # The message has to name the model and say what to do, or it reads as an internal fault.
        self.assertIn("models/part.py", message)
        self.assertIn("cadgen store gc", message)
        self.assertFalse(self.out.exists(), "a refused export must leave no output behind")

    def test_an_imported_entry_still_copies(self) -> None:
        # The branch exists for imported sources, whose step_path is the authored input rather
        # than a build product. That path stays exactly as it was.
        spec = _Spec("imported", self.existing)
        result = _export_scene("step", spec, _SceneWithoutGeneratorOutput(), self.out, logger=mock.Mock())
        self.assertEqual(self.out, result)
        self.assertIn("stale geometry", self.out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
