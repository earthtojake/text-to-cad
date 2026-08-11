"""The `<name>.step.js` sidecar convention for imported STEP files.

A generated model declares its parameter/animation module through the render
package descriptor. An imported `.step` has no generator to declare one, so the
viewer looks for a `.js` named after the STEP file, in the same directory. These
tests pin both halves: the catalog entry exposes it as `moduleUrl`, and
`/__cad/asset` will serve it -- but only when the STEP it is named after really
exists, so the convention cannot be used to serve arbitrary workspace JS.
"""

import json
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from server_py import scanner  # noqa: E402

SIDECAR_SOURCE = "export default { manifest: {}, update() {} };\n"


class StepSidecarPaths(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _write(self, name, body=""):
        path = os.path.join(self.root, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(body)
        return path

    def test_sidecar_path_appends_js_to_the_whole_filename(self):
        self.assertEqual(
            scanner.step_sidecar_path("/x/widget.step"), "/x/widget.step.js"
        )
        self.assertEqual(scanner.step_sidecar_path("/x/widget.stp"), "/x/widget.stp.js")

    def test_recognized_only_when_the_step_file_exists_beside_it(self):
        self._write("widget.step", "ISO-10303-21;\n")
        sidecar = self._write("widget.step.js", SIDECAR_SOURCE)
        self.assertTrue(scanner.is_step_sidecar_path(sidecar))

        orphan = self._write("ghost.step.js", SIDECAR_SOURCE)
        self.assertFalse(scanner.is_step_sidecar_path(orphan))

    def test_uppercase_extensions_are_recognized(self):
        self._write("Widget.STP", "ISO-10303-21;\n")
        sidecar = self._write("Widget.STP.js", SIDECAR_SOURCE)
        self.assertTrue(scanner.is_step_sidecar_path(sidecar))

    def test_unrelated_javascript_is_not_a_sidecar(self):
        self._write("widget.step", "ISO-10303-21;\n")
        self.assertFalse(scanner.is_step_sidecar_path(self._write("helper.js")))
        self.assertFalse(scanner.is_step_sidecar_path(self._write("widget.params.js")))


class StepSidecarServing(unittest.TestCase):
    """The `/__cad/asset` gate: a sidecar is served, stray JS is not."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _write(self, name, body=""):
        path = os.path.join(self.root, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(body)
        return path

    def test_sidecar_is_served_and_stray_js_is_not(self):
        self._write("widget.step", "ISO-10303-21;\n")
        sidecar = self._write("widget.step.js", SIDECAR_SOURCE)
        self.assertTrue(scanner.is_served_cad_asset(sidecar))

        # A module the sidecar might try to import is still refused: sidecars
        # must be one self-contained file.
        self.assertFalse(scanner.is_served_cad_asset(self._write("kinematics.js")))
        self.assertFalse(scanner.is_served_cad_asset(self._write("ghost.step.js")))


class StepSidecarCatalogEntry(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _write_step(self, name):
        path = os.path.join(self.root, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("ISO-10303-21;\n")
        # Minimal render package so the entry resolves like a real import.
        pkg = os.path.join(self.root, "__cadgen__", "models", name)
        os.makedirs(pkg, exist_ok=True)
        with open(os.path.join(pkg, "assembly.json"), "w", encoding="utf-8") as handle:
            json.dump({"kind": "assembly-package", "sourceKind": "step"}, handle)
        return path

    def _entry(self, step_path):
        return scanner.create_step_entry(
            self.root,
            self.root,
            step_path,
            os.path.splitext(step_path)[1].lower(),
            include_artifact_status=False,
        )

    def test_imported_step_picks_up_the_neighbouring_sidecar(self):
        step_path = self._write_step("widget.step")
        entry = self._entry(step_path)
        self.assertIsNone(entry.get("moduleUrl"))

        with open(step_path + ".js", "w", encoding="utf-8") as handle:
            handle.write(SIDECAR_SOURCE)
        entry = self._entry(step_path)
        self.assertIn("moduleUrl", entry)
        self.assertIn("widget.step.js", entry["moduleUrl"])


if __name__ == "__main__":
    unittest.main()
