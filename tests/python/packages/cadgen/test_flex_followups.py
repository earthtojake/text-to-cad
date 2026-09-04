"""Follow-ups from the flexibility audit: models inside packages, import-time
errors that read like build errors, a relative store root, an unwritable store,
`store info` listing every index kind, one narration per mesh output.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import unittest
from pathlib import Path

from tests.python.support.paths import REPO_ROOT, add_repo_path
from tests.python.support.tmp_root import temporary_directory

add_repo_path("packages/cadgen/src")

PYTHON = sys.executable

WASHER = """\
from cadgen import build123d as bd
from cadgen import step


@step
def washer():
    return bd.Cylinder(radius=4, height=1)


if __name__ == "__main__":
    washer()
"""

STACK_REL = """\
from cadgen import build123d as bd
from cadgen import step
from .parts.washer import washer


@step
def stack_rel():
    return bd.Compound(children=[washer(), bd.Pos(0, 0, 1) * washer()], label="stack")


if __name__ == "__main__":
    stack_rel()
"""

BROKEN_CHILD = """\
from cadgen import build123d as bd
from cadgen import step


@step(out="")
def broken():
    return bd.Box(1, 1, 1)


if __name__ == "__main__":
    broken()
"""

PARENT_OF_BROKEN = """\
from cadgen import build123d as bd
from cadgen import step
from broken import broken


@step
def parent():
    return bd.Compound(children=[broken()], label="parent")


if __name__ == "__main__":
    parent()
"""

MESH_ONLY = """\
from cadgen import build123d as bd
from cadgen import stl


@stl
def spacer():
    return bd.Box(2, 2, 2)


if __name__ == "__main__":
    spacer()
"""


class FollowUps(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = temporary_directory(prefix="cadgen-followups-")
        self.root = Path(self._tmp.name)
        self.store = self.root / "store"
        self.env = dict(os.environ)
        self.env.update(
            {
                "CADGEN_DAEMON": "0",
                "CADGEN_CACHE_DIR": str(self.store),
                "PYTHONPATH": str(REPO_ROOT / "packages/cadgen/src"),
            }
        )

    def tearDown(self) -> None:
        for folder in (self.store,):
            if folder.exists():
                os.chmod(folder, stat.S_IRWXU)
        self._tmp.cleanup()

    def run_in(self, cwd: Path, *argv: str, env: dict | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            [PYTHON, *argv], cwd=str(cwd), env=env or self.env, capture_output=True, text=True, timeout=600
        )

    # ---- item 4: models inside packages -------------------------------------------------

    def _package(self) -> Path:
        pkg = self.root / "proj" / "pkg"
        (pkg / "parts").mkdir(parents=True)
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "parts" / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "parts" / "washer.py").write_text(WASHER, encoding="utf-8")
        (pkg / "stack_rel.py").write_text(STACK_REL, encoding="utf-8")
        return pkg

    def test_a_child_inside_a_package_builds_by_path_in_the_worker(self) -> None:
        # `python pkg/stack_rel.py` cannot work for ANY Python file with a relative
        # import (Python runs it as __main__ with no package); cadgen's own loader
        # is what runs a child, and it keeps the package context.
        pkg = self._package()
        top = pkg.parent / "top.py"
        top.write_text(
            "from cadgen import build123d as bd\nfrom cadgen import step\nfrom pkg.stack_rel import stack_rel\n\n\n"
            "@step\ndef top():\n    return bd.Compound(children=[stack_rel()], label='top')\n\n\n"
            "if __name__ == '__main__':\n    top()\n",
            encoding="utf-8",
        )
        completed = self.run_in(pkg.parent, "top.py")
        self.assertEqual(completed.returncode, 0, completed.stderr[-3000:])
        self.assertTrue((pkg.parent / "top.step").is_file())
        self.assertTrue((pkg / "stack_rel.step").is_file(), "the child inside the package built in its worker")
        self.assertTrue((pkg / "parts" / "washer.step").is_file(), "and its relative import resolved")

    def test_a_relative_import_inside_a_package_builds_under_dash_m(self) -> None:
        pkg = self._package()
        completed = self.run_in(pkg.parent, "-m", "pkg.stack_rel")
        self.assertEqual(completed.returncode, 0, completed.stderr[-3000:])
        self.assertTrue((pkg / "stack_rel.step").is_file())

    # ---- item 6: import-time validation errors read like build errors -------------------

    def test_a_bad_decorator_argument_in_the_run_script_is_one_line(self) -> None:
        src = self.root / "src"
        src.mkdir()
        (src / "broken.py").write_text(BROKEN_CHILD, encoding="utf-8")
        completed = self.run_in(src, "broken.py")
        self.assertEqual(completed.returncode, 1)
        lines = [line for line in completed.stderr.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1, completed.stderr)
        self.assertTrue(lines[0].startswith("[python broken.py] FAILED: TypeError: @step out= must be a non-empty path string"), lines[0])
        self.assertNotIn("Traceback", completed.stderr)
        verbose = self.run_in(src, "broken.py", "--verbose")
        self.assertEqual(verbose.returncode, 1)
        self.assertIn("Traceback", verbose.stderr)

    def test_a_parent_importing_a_broken_child_reports_it_as_its_own_failure(self) -> None:
        src = self.root / "src"
        src.mkdir()
        (src / "broken.py").write_text(BROKEN_CHILD, encoding="utf-8")
        (src / "parent.py").write_text(PARENT_OF_BROKEN, encoding="utf-8")
        completed = self.run_in(src, "parent.py")
        self.assertEqual(completed.returncode, 1)
        self.assertIn("[python parent.py] FAILED: TypeError: @step out= must be a non-empty path string", completed.stderr)
        self.assertIn("broken.py", completed.stderr, "the failure names the child that raised")

    # ---- item 9: a relative CADGEN_CACHE_DIR is one store from every cwd -------------------

    def test_a_relative_store_root_is_absolutized_once(self) -> None:
        src = self.root / "src"
        src.mkdir()
        (src / "washer.py").write_text(WASHER, encoding="utf-8")
        env = dict(self.env)
        env["CADGEN_CACHE_DIR"] = "../relative-store"  # relative to src/
        built = self.run_in(src, "washer.py", env=env)
        self.assertEqual(built.returncode, 0, built.stderr[-3000:])
        self.assertTrue((self.root / "relative-store" / "index" / "model").is_dir())
        env["CADGEN_CACHE_DIR"] = str(self.root / "relative-store")
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        why = self.run_in(elsewhere, "-m", "cadgen.cli", "store", "why", str(src / "washer.py"), env=env)
        self.assertIn("verdict current", why.stdout, why.stdout + why.stderr)

    # ---- item 13: an unwritable store is one sentence ----------------------------------------

    @unittest.skipIf(os.name == "nt" or os.geteuid() == 0, "a read-only folder needs POSIX permissions and a non-root user")
    def test_an_unwritable_store_is_one_sentence(self) -> None:
        src = self.root / "src"
        src.mkdir()
        (src / "washer.py").write_text(WASHER, encoding="utf-8")
        self.store.mkdir()
        os.chmod(self.store, stat.S_IRUSR | stat.S_IXUSR)
        probe = self.store / ".probe"
        try:
            probe.write_text("x")
        except PermissionError:
            pass
        else:
            probe.unlink()
            self.skipTest("this filesystem does not enforce a read-only folder")
        completed = self.run_in(src, "washer.py")
        self.assertEqual(completed.returncode, 1)
        self.assertIn("StoreUnwritableError: the store at", completed.stderr)
        self.assertIn("CADGEN_CACHE_DIR", completed.stderr)
        self.assertNotIn("pathlib", completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)

    # ---- items 11 and 12 ----------------------------------------------------------------------

    def test_a_mesh_only_build_names_each_output_once(self) -> None:
        src = self.root / "src"
        src.mkdir()
        (src / "spacer.py").write_text(MESH_ONLY, encoding="utf-8")
        completed = self.run_in(src, "spacer.py")
        self.assertEqual(completed.returncode, 0, completed.stderr[-3000:])
        narration = [line for line in completed.stderr.splitlines() if "spacer.stl" in line and "wrote" in line]
        self.assertEqual(len(narration), 1, completed.stderr)

    def test_store_info_lists_every_index_kind(self) -> None:
        src = self.root / "src"
        src.mkdir()
        (src / "washer.py").write_text(WASHER, encoding="utf-8")
        self.assertEqual(self.run_in(src, "washer.py").returncode, 0)
        info = self.run_in(src, "-m", "cadgen.cli", "store", "info")
        for kind in ("model", "document", "output", "component", "op", "mesh"):
            self.assertIn(f"index/{kind}", info.stdout, info.stdout)
        self.assertRegex(info.stdout, r"index/document\s+1 ")
        self.assertRegex(info.stdout, r"index/output\s+1 ")


if __name__ == "__main__":
    unittest.main()
