"""A door reads the document as written; it never rebuilds a model.

``inspect validate`` and ``inspect interfere`` need the model's in-memory scene.
They load the document on disk — current or not — and run no Python: a door asks
one question (does the store have a tree for these bytes?) and a source that has
moved on since the document was written is the model's business, not the door's
(STORE.md §9). ``document_staleness`` still answers that question for the viewer's
badge, so the reason it gives is pinned here too.

Real fixture, real script run: the document is built cold in a subprocess, then
the door is called in-process with stderr captured.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from tests.python.support.paths import add_repo_path
from tests.python.support.cad_test_roots import IsolatedCadRoots

add_repo_path("packages/cadgen/src")

MODEL = """\
from build123d import Box

from cadgen import step
from lib import size


@step
def model():
    return Box(size.WIDTH, 8.0, 4.0)


if __name__ == "__main__":
    model()
"""

HELPER = "WIDTH = {width}\n"


class DoorReadsTheDocumentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.roots = IsolatedCadRoots(self, prefix="cadgen-door-reads-")
        self.project = self.roots.cad_root / "proj"
        (self.project / "lib").mkdir(parents=True)
        (self.project / "lib" / "__init__.py").write_text("", encoding="utf-8")
        (self.project / "lib" / "size.py").write_text(HELPER.format(width=10.0), encoding="utf-8")
        self.script = self.project / "part.py"
        self.script.write_text(MODEL, encoding="utf-8")
        self.document = self.project / "part.step"
        os.chdir(self.project)
        self._build()

    def _build(self) -> None:
        env = dict(os.environ)
        env["CADGEN_DAEMON"] = "0"
        env["PYTHONPATH"] = os.pathsep.join(
            [str(add_repo_path("packages/cadgen/src")), *([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])]
        )
        result = subprocess.run(
            [sys.executable, str(self.script)],
            cwd=self.project,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.document.is_file())

    def _validate(self) -> tuple[dict, str]:
        from cadgen.validity import inspect_validity

        err = io.StringIO()
        with mock.patch.dict(os.environ, {"CADGEN_VALIDATE_WORKERS": "1"}), \
                redirect_stdout(io.StringIO()), redirect_stderr(err):
            report = inspect_validity("part.step")
        return report, err.getvalue()

    def _interfere(self) -> str:
        from cadgen.interference import inspect_interference

        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            inspect_interference("part.step")
        return err.getvalue()

    def _make_stale(self) -> None:
        # A SEMANTIC change to an imported helper, written after the document.
        time.sleep(0.05)
        (self.project / "lib" / "size.py").write_text(HELPER.format(width=12.0), encoding="utf-8")

    def _never_runs_the_script(self):
        from cadgen._internal import generation_runner

        return mock.patch.object(
            generation_runner, "_run_script_generator_inner",
            side_effect=AssertionError("a door must not run the model's script"),
        )

    def test_a_current_document_is_validated_without_running_python(self):
        with self._never_runs_the_script():
            report, err = self._validate()
        self.assertTrue(report["ok"], report)
        self.assertNotIn("rebuilding", err)

    def test_a_stale_document_is_read_as_written_no_rebuild_no_notice(self):
        # The document's bytes still have their tree in the store (the model wrote
        # them), so the door reads it. The new WIDTH is the model's to build.
        self._make_stale()
        with self._never_runs_the_script():
            report, err = self._validate()
            interfere_err = self._interfere()
        self.assertTrue(report["ok"], report)
        self.assertNotIn("is stale", err + interfere_err)
        self.assertNotIn("rebuilding", err + interfere_err)

    def test_document_staleness_still_names_the_reason_for_the_badge(self):
        from cadgen._internal.doors import document_staleness

        self.assertIsNone(document_staleness(self.document))
        self._make_stale()
        self.assertEqual(
            document_staleness(self.document),
            "lib/size.py changed after the document was written",
        )

    def test_a_missing_closure_file_is_named(self):
        from cadgen._internal.doors import document_staleness

        (self.project / "lib" / "size.py").unlink()
        self.assertEqual(document_staleness(self.document), "closure file missing: lib/size.py")


if __name__ == "__main__":
    unittest.main()
