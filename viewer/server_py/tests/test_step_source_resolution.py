"""resolve_step_source precedence: a same-stem generator owns its entry.

A `<name>.step.py` generator beside an exported `<name>.step` is the documented
way to attach a `params` sidecar to an imported STEP. The export is the
generator's output, so the generator -- not the export -- is the source the
render package is keyed by.
"""

import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from server_py.backend import LocalAssetBackend  # noqa: E402

GENERATOR = """from pathlib import Path

from cadgen.step_scene import import_step


def gen_step():
    return {
        "shape": import_step(Path(__file__).parent / "widget.step"),
        "params": "widget.params.js",
    }
"""


class StepSourceResolutionTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.backend = LocalAssetBackend()

    def _resolved_root(self):
        return {"rootPath": self.root}

    def _write(self, name, text=""):
        path = os.path.join(self.root, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def test_imported_step_without_a_generator_resolves_to_itself(self):
        step = self._write("widget.step", "ISO-10303-21;\n")
        resolved = self.backend.resolve_step_source("widget.step", self._resolved_root())
        self.assertEqual(resolved["stepPath"], step)
        self.assertEqual(resolved["sourcePath"], "")
        self.assertFalse(resolved["skipStepWrite"])

    def test_same_stem_generator_wins_over_a_sibling_export(self):
        step = self._write("widget.step", "ISO-10303-21;\n")
        generator = self._write("widget.step.py", GENERATOR)
        # Reached by the .step ref (how the catalog lists an imported model)...
        resolved = self.backend.resolve_step_source("widget.step", self._resolved_root())
        self.assertEqual(resolved["stepPath"], step)
        self.assertEqual(resolved["sourcePath"], generator)
        self.assertTrue(resolved["skipStepWrite"])
        # ...and by the generator ref, which must agree so the freshness check
        # and the build never key on different sources.
        via_py = self.backend.resolve_step_source("widget.step.py", self._resolved_root())
        self.assertEqual(via_py["stepPath"], step)
        self.assertEqual(via_py["sourcePath"], generator)

    def test_a_sibling_python_file_without_gen_step_is_not_a_generator(self):
        self._write("widget.step", "ISO-10303-21;\n")
        self._write("widget.step.py", "value = 1\n")
        resolved = self.backend.resolve_step_source("widget.step", self._resolved_root())
        self.assertEqual(resolved["sourcePath"], "")
        self.assertFalse(resolved["skipStepWrite"])

    def test_generator_with_no_export_on_disk_still_resolves(self):
        generator = self._write("widget.step.py", GENERATOR)
        resolved = self.backend.resolve_step_source("widget.step.py", self._resolved_root())
        self.assertEqual(resolved["stepPath"], os.path.join(self.root, "widget.step"))
        self.assertEqual(resolved["sourcePath"], generator)
        self.assertTrue(resolved["skipStepWrite"])


if __name__ == "__main__":
    unittest.main()
