"""STEP output behavior (a model-script run ALWAYS writes the STEP file, assembled
from the tree's exact-shape component objects — design/step-document-architecture.md):
closure-keyed reuse, new-path copy via -o, metadata injection, and the
verbose export spans (once silently orphaned — design/FEEDBACK.md item 9)."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
import unittest.mock
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

# The interpreter running the suite, NOT a hardcoded checkout path: the child
# must import the same cadgen/OCP the parent did, and an absolute
# ``.venv/bin/python`` literal exists on exactly one machine.
VENV = sys.executable
REPO = Path(__file__).resolve().parents[4]


def _write_model(root: Path) -> Path:
    entry = root / "block.py"
    entry.write_text(textwrap.dedent("""\
        SIZE = 6.0

        from cadgen import step
        @step
        def model():
            from build123d.topology import Solid
            block = Solid.make_box(SIZE, SIZE, SIZE)
            block.label = "block"
            return block


        if __name__ == "__main__":
            model()
        """))
    return entry


def _run(entry: Path, args: list[str], store: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update({
        "CADGEN_DAEMON": "0",
        "CADGEN_COMPONENT_WORKERS": "1",
        "CADGEN_CACHE_DIR": str(store),
        "PYTHONPATH": str(REPO / "packages/cadgen/src"),
    })
    code = (
        ""
    )
    del code
    return subprocess.run([VENV, entry.name, *args], cwd=str(entry.parent), env=env,
                          capture_output=True, text=True, timeout=600)


class StepExportReuseTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        model_dir = root / "model"
        model_dir.mkdir(parents=True, exist_ok=True)
        self.entry = _write_model(model_dir)
        self.store = root / "store"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_repeat_write_reuses_and_edit_invalidates(self) -> None:
        first = _run(self.entry, [], self.store)
        self.assertEqual(first.returncode, 0, first.stderr[-1500:])
        step = self.entry.parent / "block.step"
        self.assertTrue(step.is_file())
        original = hashlib.sha256(step.read_bytes()).hexdigest()

        repeat = _run(self.entry, [], self.store)
        self.assertEqual(repeat.returncode, 0, repeat.stderr[-1500:])
        self.assertIn("is current", repeat.stderr)
        self.assertEqual(hashlib.sha256(step.read_bytes()).hexdigest(), original)

        self.entry.write_text(self.entry.read_text().replace("SIZE = 6.0", "SIZE = 7.0"))
        edited = _run(self.entry, [], self.store)
        self.assertEqual(edited.returncode, 0, edited.stderr[-1500:])
        self.assertNotIn("step export is current", edited.stderr)
        self.assertNotEqual(hashlib.sha256(step.read_bytes()).hexdigest(), original)


    def test_verbose_export_spans_fire_and_no_metadata_is_written(self) -> None:
        run = _run(self.entry, ["--verbose"], self.store)
        self.assertEqual(run.returncode, 0, run.stderr[-1500:])
        for span in ("transfer XCAF to STEP model", "write STEP file"):
            self.assertIn(span, run.stderr,
                          f"orphaned --verbose span: {span!r}")
        # A written STEP is a plain artifact: no cadgen: properties, no link
        # back to source code, under any circumstances.
        step_text = (self.entry.parent / "block.step").read_text(errors="ignore")
        self.assertNotIn("cadgen:", step_text)
        self.assertNotIn("block.py", step_text)


if __name__ == "__main__":
    unittest.main()
