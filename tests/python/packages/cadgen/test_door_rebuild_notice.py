"""A door that rebuilds a stale document says so, once, before it starts.

``inspect validate`` and ``inspect interfere`` need the model's in-memory scene.
A CURRENT document is loaded from disk, running no Python; a STALE one -- its
script or a helper it imports changed since the document was written -- is rebuilt
from the script. Until the notice existed that rebuild was silent: a user who
believed validate never runs Python watched fifteen minutes pass and then read a
model import traceback with nothing to attribute it to.

The line is composed in ONE place (``cadgen._internal.doors.announce_rebuild``) and
its reason comes from the freshness authority (``document_staleness``) the no-op
gate uses too, so the two doors cannot disagree about what stale means.

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
from pathlib import Path
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


class StaleRebuildNoticeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.roots = IsolatedCadRoots(self, prefix="cadgen-rebuild-notice-")
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

    def test_a_current_document_is_validated_without_a_rebuild_or_a_notice(self):
        from cadgen._internal import generation_runner

        with mock.patch.object(
            generation_runner, "_run_script_generator_inner",
            side_effect=AssertionError("a current document must not run its script"),
        ):
            report, err = self._validate()
        self.assertTrue(report["ok"], report)
        self.assertNotIn("is stale", err)
        self.assertNotIn("rebuilding", err)

    def test_a_stale_document_announces_the_rebuild_with_the_reason(self):
        self._make_stale()
        report, err = self._validate()
        self.assertTrue(report["ok"], report)
        lines = [line for line in err.splitlines() if "rebuilding from" in line]
        self.assertEqual(len(lines), 1, err)
        self.assertEqual(
            lines[0],
            "inspect validate: part.step is stale (lib/size.py changed after the document was "
            "written); rebuilding from part.py before validating",
        )

    def test_the_notice_names_the_door_that_decided(self):
        self._make_stale()
        err = self._interfere()
        self.assertIn(
            "inspect interfere: part.step is stale (lib/size.py changed after the document was "
            "written); rebuilding from part.py before checking interference",
            err,
        )

    def test_the_no_op_gate_reads_the_same_authority(self):
        from cadgen._internal.doors import StaleDocumentError, document_staleness, require_current_document

        self.assertIsNone(document_staleness(self.document))
        require_current_document(self.document)
        self._make_stale()
        self.assertEqual(
            document_staleness(self.document),
            "lib/size.py changed after the document was written",
        )
        with self.assertRaises(StaleDocumentError) as caught:
            require_current_document(self.document)
        self.assertIn("(lib/size.py changed after the document was written)", str(caught.exception))
        self.assertIn("run python part.py", str(caught.exception))

    def test_a_missing_closure_file_is_named(self):
        from cadgen._internal.doors import document_staleness

        (self.project / "lib" / "size.py").unlink()
        self.assertEqual(document_staleness(self.document), "closure file missing: lib/size.py")


if __name__ == "__main__":
    unittest.main()
