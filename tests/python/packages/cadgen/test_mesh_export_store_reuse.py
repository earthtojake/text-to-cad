"""Mesh export resolves the STORE tree before touching anything else.

The export fast path, exercised through the `cadgen stl|3mf|glb build` doors.
Doors take DOCUMENTS (design/pose-animation-split.md, CLI/doors follow-on), so
there are exactly two shapes to cover:

* A document whose package is current exports straight from it — no generator
  run, no extraction, no source read at all. Its DECLARED variants come from
  the sidecar the script run wrote.
* A document whose sidecar closure no longer re-hashes is STALE, and the door
  says so by naming `python <script>` instead of rebuilding. A render or an
  export must never contain a build.

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

add_repo_path("packages/cadgen/src")

REPO = Path(__file__).resolve().parents[4]
PYTHON = sys.executable


def _write_model(root: Path, size: float) -> Path:
    entry = root / "block.py"
    entry.write_text(textwrap.dedent(f"""\
        SIZE = {size}

        from cadgen import glb, step, stl, threemf
        @step
        @stl
        @glb
        @threemf
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
            "CADGEN_DAEMON": "0",
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
            [PYTHON, "-c", code, target, "--verbose", *flags],
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

    def test_a_current_document_exports_from_its_store_package(self) -> None:
        entry = _write_model(self.root, size=6.0)
        build = self._run([entry.name], self.root)
        self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
        step_file = self.root / "block.step"
        self.assertTrue(step_file.is_file(), "model script writes its STEP")

        # The declared variants come from the sidecar the run wrote — the door
        # imports no model module and reads no source.
        for fmt in ("stl", "glb", "3mf"):
            current = self._export(fmt, "block.step", "--force")
            # Straight to the tessellator: the tree is already keyed by these
            # bytes, so there is nothing to run, load or extract.
            self.assertIn(f"tessellate + write {fmt}", current.stderr)
            self.assertNotIn("run step model", current.stderr)
            self.assertNotIn("extract exact geometry", current.stderr)
            self.assertNotIn("load STEP", current.stderr)
            self.assertTrue(step_file.with_suffix(f".{fmt}").is_file(), fmt)

    def test_a_stale_document_is_read_as_written_by_the_door(self) -> None:
        # A door asks one question -- does the store have a tree for this file's
        # bytes? -- and never runs the script. The source moving on is the model's
        # business: the door reads the document as written and rebuilds nothing.
        entry = _write_model(self.root, size=6.0)
        self.assertEqual(0, self._run([entry.name], self.root).returncode)
        step_file = self.root / "block.step"
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

    def test_a_bare_door_needs_declarations_in_the_sidecar(self) -> None:
        # An imported document declares nothing, so there is no variant set to
        # produce — and the answer is a teaching error, not a guessed sibling.
        entry = _write_model(self.root, size=6.0)
        self.assertEqual(0, self._run([entry.name], self.root).returncode)
        imported = self.root / "imported_block.step"
        imported.write_bytes((self.root / "block.step").read_bytes() + b"\n")

        bare = self._door("stl", "imported_block.step")
        self.assertEqual(1, bare.returncode)
        self.assertIn("declare @stl on the model and run python <script>", bare.stderr)
        self.assertIn("explicit OUT", bare.stderr)

    def test_an_imported_document_compiles_once_then_reuses(self) -> None:
        entry = _write_model(self.root, size=6.0)
        self.assertEqual(0, self._run([entry.name], self.root).returncode)
        imported = self.root / "imported_block.step"
        imported.write_bytes((self.root / "block.step").read_bytes() + b"\n")

        before = self._package_dirs()
        self._export("glb", "imported_block.step", "out/imported.glb")
        self.assertTrue((self.root / "out/imported.glb").is_file())
        after_first = self._package_dirs()
        self.assertEqual(len(after_first - before), 1, "one store package built by export")
        again = self._export("stl", "imported_block.step", "out/imported.stl")
        self.assertEqual(self._package_dirs(), after_first, "second export builds nothing")
        self.assertNotIn("extract exact geometry", again.stderr)


if __name__ == "__main__":
    unittest.main()
