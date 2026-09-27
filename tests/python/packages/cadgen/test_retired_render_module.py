"""A leftover ``<name>.step.js`` is named on every run, and the build goes on.

Animation used to be a companion ES module discovered by convention beside the
document. It is now ``@step(animation=...)``, embedded in the document's
sidecar, and nothing looks for the file any more. So a project carrying one
across the cutover would get exactly the failure law 10 forbids: a model that
used to articulate renders inert, at exit 0, with no message anywhere.

The file is read by nothing, so the document a build writes is correct without
it: a stray file is not a reason to refuse the build. It is a reason to say so,
once per run on stderr, naming the replacement -- including on the run that
rebuilds NOTHING, because a model whose tree is already current takes the no-op
path and would otherwise sail past the check.

The viewer says nothing: it shows the document it is handed, and the absence of
the routine is visible there already. The build is the one announcement.
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

CADGEN_SRC = add_repo_path("packages/cadgen/src")

MODEL = """\
from cadgen import step


@step(out="part.step")
def model():
    from build123d.topology import Solid

    block = Solid.make_box(4, 4, 4)
    block.label = "block"
    return block


if __name__ == "__main__":
    model()
"""

RETIRED_MODULE = "export const clips = { spin: { duration: 1, update() {} } };\n"


class RetiredRenderModuleWarns(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="retired-render-module-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self.script = self.root / "part.py"
        self.script.write_text(MODEL, encoding="utf-8")
        self.document = self.root / "part.step"
        self.companion = self.root / "part.step.js"
        self.env = dict(os.environ)
        self.env.update({
            "CADGEN_DAEMON": "0",
            "CADGEN_COMPONENT_WORKERS": "1",
            "CADGEN_CACHE_DIR": str(self.root / "store"),
            "PYTHONPATH": str(CADGEN_SRC),
        })

    def _build(self) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(self.script)],
            cwd=str(self.root), env=self.env,
            capture_output=True, text=True, timeout=600,
        )

    def test_the_build_warns_names_the_decorator_and_still_writes_the_document(self) -> None:
        self.companion.write_text(RETIRED_MODULE, encoding="utf-8")
        built = self._build()
        output = built.stdout + built.stderr

        self.assertEqual(0, built.returncode, output)
        self.assertIn("warning:", built.stderr)
        self.assertIn("part.step.js", built.stderr)
        self.assertIn("@step(animation=...)", built.stderr)
        self.assertIn("kinematics", built.stderr)
        # It says what is lost and that it is a migration to do: the build is the only
        # place this is announced, so a remark that reads as optional goes undone.
        self.assertIn("missing from this model", built.stderr)
        self.assertIn("Migrate it now", built.stderr)
        # A stray file nothing reads does not stop the build.
        self.assertTrue(self.document.is_file(), "the build did not write its document")

    def test_the_no_op_run_warns_too(self) -> None:
        clean = self._build()
        self.assertEqual(0, clean.returncode, clean.stdout + clean.stderr)
        self.assertNotIn("retired render module", clean.stderr)

        # Nothing about the model changed, so this run rebuilds nothing at all.
        # The warning still has to land: a check that only ran when geometry
        # was recomputed would let the stale file go unmentioned on later runs.
        self.companion.write_text(RETIRED_MODULE, encoding="utf-8")
        again = self._build()
        self.assertEqual(0, again.returncode, again.stdout + again.stderr)
        self.assertIn("part.step.js", again.stderr)
        self.assertEqual(1, again.stderr.count("retired render module"), again.stderr)


if __name__ == "__main__":
    unittest.main()
