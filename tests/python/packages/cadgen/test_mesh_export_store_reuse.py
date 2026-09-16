"""Mesh export resolves the STORE tree before touching anything else.

The export fast path, exercised through the `cadgen stl|3mf|glb build` doors.
Doors take DOCUMENTS (design/pose-animation-split.md, CLI/doors follow-on), so
there are exactly two shapes to cover:

* A generated document whose package is current exports straight from it — no
  generator run, no extraction, no source read at all.
* Editing its source does not change the saved document. The door continues to
  export those exact bytes and never contains a model rebuild.

A document with no package at all (an import) compiles one into the shared
store on first use, and every later export reuses it.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path
from tests.python.support.warm_daemon import warm_entries

add_repo_path("packages/cadgen/src")

REPO = Path(__file__).resolve().parents[4]
PYTHON = sys.executable


def _write_model(root: Path, size: float) -> Path:
    entry = root / "block.py"
    entry.write_text(textwrap.dedent(f"""\
        SIZE = {size}

        from cadgen import step
        @step
        def model():
            from build123d.topology import Solid
            block = Solid.make_box(SIZE, SIZE, SIZE)
            block.label = "block"
            return block


        if __name__ == "__main__":
            model()
        """), encoding="utf-8")
    return entry


class MeshExportStoreReuseTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="mesh-export-store-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self.store = self.root / "store"
        self.env = dict(os.environ)
        self.env.update({
            **warm_entries(),
            "CADGEN_COMPONENT_WORKERS": "1",
            "CADGEN_CACHE_DIR": str(self.store),
            "PYTHONPATH": str(REPO / "packages/cadgen/src"),
        })

    def _run(self, argv: list[str], cwd: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [PYTHON, *argv], cwd=str(cwd), env=self.env,
            capture_output=True, text=True, timeout=600,
        )

    def _door(self, fmt: str, target: str, *flags: str) -> subprocess.CompletedProcess:
        module = {"stl": "stl_build", "3mf": "threemf_build", "glb": "glb_build"}[fmt]
        code = f"from cadgen.cli.{module} import main; raise SystemExit(main())"
        return subprocess.run(
            # Keep the positionals contiguous: 3.11 argparse rejects a
            # positional that follows an optional in the middle of the argv.
            [PYTHON, "-c", code, target, *flags, "--verbose"],
            cwd=str(self.root), env=self.env, capture_output=True, text=True, timeout=600,
        )

    def _export(self, fmt: str, target: str, *flags: str) -> subprocess.CompletedProcess:
        proc = self._door(fmt, target, *flags)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return proc

    def _package_dirs(self) -> set[str]:
        """The records in the store: an export of an imported document writes
        exactly one (keyed by the document), and a second export none."""
        records = self.store / "index" / "model"
        if not records.is_dir():
            return set()
        return {p.name for p in records.iterdir() if p.is_file()}

    def test_a_generated_document_exports_current_and_after_source_edit(self) -> None:
        entry = _write_model(self.root, size=6.0)
        build = self._run([entry.name], self.root)
        self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
        step_file = self.root / "block.step"
        self.assertTrue(step_file.is_file(), "model script writes its STEP")

        # The door imports no model module and reads no source: it tessellates
        # the tree behind these bytes and writes the sibling default.
        for fmt in ("stl", "glb", "3mf"):
            current = self._export(fmt, "block.step", "--force")
            # Straight to the tessellator: the tree is already keyed by these
            # bytes, so there is nothing to run, load or extract.
            self.assertIn(f"tessellate + write {fmt}", current.stderr)
            self.assertNotIn("run step model", current.stderr)
            self.assertNotIn("extract exact geometry", current.stderr)
            self.assertNotIn("load STEP", current.stderr)
            self.assertTrue(step_file.with_suffix(f".{fmt}").is_file(), fmt)

        # A door asks one question -- does the store have a tree for this file's
        # bytes? -- and never runs the script. The source moving on is the model's
        # business: the door reads the document as written and rebuilds nothing.
        step_before = step_file.read_bytes()
        stl_before = step_file.with_suffix(".stl").read_bytes()

        _write_model(self.root, size=9.0)
        door = self._door("stl", "block.step")
        self.assertEqual(0, door.returncode, door.stderr)
        self.assertNotIn("stale", door.stderr)
        self.assertNotIn("run step model", door.stderr)
        # Nothing was rebuilt, re-exported, or otherwise touched.
        self.assertEqual(step_before, step_file.read_bytes())
        self.assertEqual(stl_before, step_file.with_suffix(".stl").read_bytes())

    def test_an_imported_document_writes_defaults_then_reuses_one_compilation(self) -> None:
        # A door reads no declarations: a bare door tessellates the document's
        # tree and writes ONE mesh beside it — imported or generated alike.
        entry = _write_model(self.root, size=6.0)
        self.assertEqual(0, self._run([entry.name], self.root).returncode)
        imported = self.root / "imported_block.step"
        imported.write_bytes((self.root / "block.step").read_bytes() + b"\n")
        self.assertFalse(imported.with_suffix(".step.json").exists(), "an import has no sidecar")

        before = self._package_dirs()
        bare = self._export("stl", "imported_block.step")
        self.assertTrue(imported.with_suffix(".stl").is_file(), bare.stderr)
        self.assertIn("wrote STL", bare.stdout + bare.stderr)
        after_first = self._package_dirs()
        self.assertEqual(len(after_first - before), 1, "one store package built by export")

        glb = self._export("glb", "imported_block.step", "out/imported.glb")
        self.assertTrue((self.root / "out/imported.glb").is_file())
        self.assertEqual(self._package_dirs(), after_first, "cross-format export builds nothing")
        self.assertNotIn("extract exact geometry", glb.stderr)
        again = self._export("stl", "imported_block.step", "out/imported.stl")
        self.assertEqual(self._package_dirs(), after_first, "second export builds nothing")
        self.assertNotIn("extract exact geometry", again.stderr)


if __name__ == "__main__":
    unittest.main()
