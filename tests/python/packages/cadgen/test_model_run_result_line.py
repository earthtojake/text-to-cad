"""What a model run answers on stdout, and which models a file may hold.

Two contracts that only show up when a script is run as a script:

*The result line names a document.* `outcome document` is the whole stdout of a
model run, and `--json` carries the same path in `document`. A mesh-only model
declares no STEP, so it names the mesh it wrote -- a path the caller can open.
The tree hash is not a document: it names nothing on disk.

*A file may hold several models.* Two `@step` models in one file have always
worked; so must two `@dxf` models, and a `@dxf` beside a `@step`. The gate is
asked by model identity (`script::fn`), and a bare script path is ambiguous in a
multi-model file -- asking with one refuses before the drawing reaches its gate.
"""

from __future__ import annotations

import json
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


class _ModelRunCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="model-result-line-")
        self.addCleanup(self._tmp.cleanup)
        self.project = Path(self._tmp.name).resolve()
        self.env = dict(os.environ)
        self.env.update({
            **warm_entries(),
            "CADGEN_COMPONENT_WORKERS": "1",
            "CADGEN_CACHE_DIR": str(self.project / "store"),
            "PYTHONPATH": str(REPO / "packages/cadgen/src"),
        })

    def _write(self, name: str, body: str) -> None:
        (self.project / name).write_text(textwrap.dedent(body), encoding="utf-8")

    def _run(self, *argv: str) -> subprocess.CompletedProcess:
        proc = subprocess.run(
            [PYTHON, *argv], cwd=str(self.project), env=self.env,
            capture_output=True, text=True, timeout=600,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return proc

    def _lines(self, proc: subprocess.CompletedProcess) -> list[str]:
        return [line for line in proc.stdout.splitlines() if line.strip()]


class ModelRunResultLineTest(_ModelRunCase):
    def test_the_result_line_names_a_document_for_every_decorator_shape(self) -> None:
        """One test, one store, one run per shape.

        The contract is a single sentence -- the result line names a path the caller can
        open, never the tree hash -- and it was being asked three times, each from its own
        empty store, each paying a cold kernel import and a full mesh write. The three
        shapes it has to hold for are just three fixtures.
        """
        self._write("spacer.py", """\
            from cadgen import build123d as bd
            from cadgen import stl


            @stl
            def spacer():
                return bd.Box(10, 10, 10)


            if __name__ == "__main__":
                spacer()
            """)
        self._write("multi.py", """\
            from cadgen import build123d as bd
            from cadgen import glb, stl


            @stl(out="STL/multi.stl")
            @glb
            def multi():
                return bd.Box(10, 10, 10)


            if __name__ == "__main__":
                multi()
            """)
        self._write("withstep.py", """\
            from cadgen import build123d as bd
            from cadgen import step, stl


            @step
            @stl
            def withstep():
                return bd.Box(10, 10, 10)


            if __name__ == "__main__":
                withstep()
            """)

        # A mesh-only model declares no STEP, so it names the mesh it wrote.
        self.assertEqual(self._lines(self._run("spacer.py")), ["built spacer.stl"])
        self.assertTrue((self.project / "spacer.stl").is_file())

        # The no-op run names the same document, and --json carries it beside the tree
        # hash it must not be confused with.
        payload = json.loads(self._run("spacer.py", "--json").stdout.strip())
        self.assertEqual(payload["outcome"], "current")
        self.assertEqual(payload["document"], "spacer.stl")
        self.assertNotEqual(payload["document"], payload["tree"])

        # Several mesh formats: the FIRST declared one, at the path it declared.
        payload = json.loads(self._run("multi.py", "--json").stdout.strip())
        self.assertEqual(payload["document"], "STL/multi.stl")
        self.assertTrue((self.project / "STL/multi.stl").is_file())
        self.assertTrue((self.project / "multi.glb").is_file())

        # A STEP beside meshes: the STEP is the document.
        payload = json.loads(self._run("withstep.py", "--json").stdout.strip())
        self.assertEqual(payload["document"], "withstep.step")


class SeveralModelsInOneFileTest(_ModelRunCase):
    def test_two_drawings_in_one_file_both_build(self) -> None:
        self._write("twod.py", """\
            from cadgen import build123d as bd
            from cadgen import dxf


            @dxf
            def a():
                return bd.Rectangle(10, 10)


            @dxf
            def b():
                return bd.Rectangle(20, 20)


            if __name__ == "__main__":
                a()
                b()
            """)

        self.assertEqual(self._lines(self._run("twod.py")), ["built a.dxf", "built b.dxf"])
        self.assertTrue((self.project / "a.dxf").is_file())
        self.assertTrue((self.project / "b.dxf").is_file())

        # Each drawing has its own record, so the rerun is a no-op for both.
        self.assertEqual(self._lines(self._run("twod.py")), ["current a.dxf", "current b.dxf"])

    def test_a_drawing_beside_a_part_in_one_file_both_build(self) -> None:
        self._write("both.py", """\
            from cadgen import build123d as bd
            from cadgen import dxf, step


            @step
            def part():
                return bd.Box(10, 10, 10)


            @dxf
            def draw():
                return bd.Rectangle(10, 10)


            if __name__ == "__main__":
                part()
                draw()
            """)

        self.assertEqual(
            self._lines(self._run("both.py")), ["built part.step", "built draw.dxf"]
        )
        self.assertTrue((self.project / "part.step").is_file())
        self.assertTrue((self.project / "draw.dxf").is_file())


if __name__ == "__main__":
    unittest.main()
