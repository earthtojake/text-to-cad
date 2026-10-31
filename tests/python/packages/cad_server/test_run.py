"""``cad run`` runs a program with its own folder LAST on the module search path (the library's
``cad._internal.program``), and the engine's worker seats a model's folder so (``cad.engine.model.seat``):
a project's ``cad.py`` beside a model never stands in for the library, while the model's own modules
still import by their names. A model script that would be imported under the library's name is refused,
saying so, rather than replacing the library in the worker."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.python.support import engine_daemon
from tests.python.support.paths import add_sources

SRC = add_sources()  # the three packages' sources, as PYTHONPATH names them

# What a project's own module named as the library does when it is imported: says so, and fails.
SHADOW = "raise SystemExit('the project imported its own cad.py')\n"
MODEL = """
import build123d as bd
from cad import step

import parts


@step("box.step")
def box():
    return bd.Box(parts.SIZE, 1, 1)


if __name__ == "__main__":
    box()
"""


class ProjectFolderLastTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="run-last-")))
        cls.addClassCleanup(shutil.rmtree, cls.folder, True)
        engine = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        cls.addClassCleanup(shutil.rmtree, engine, True)
        cls.env = engine_daemon.watched({**os.environ, "PYTHONPATH": SRC, "CAD_ENGINE_DIR": str(engine),
                                         "CAD_STATE_DIR": str(cls.folder / "state"),
                                         "CAD_CACHE_DIR": str(cls.folder / "cache"),
                                         "CAD_ENGINE_MESH": "inline"},
                                        cls.addClassCleanup)
        cls.addClassCleanup(engine_daemon.run, [sys.executable, "-m", "cad_server.engine", "stop"], env=cls.env)
        cls.project = cls.folder / "project"
        cls.project.mkdir()
        (cls.project / "cad.py").write_text(SHADOW, encoding="utf-8")
        (cls.project / "parts.py").write_text("SIZE = 3\n", encoding="utf-8")
        (cls.project / "model.py").write_text(textwrap.dedent(MODEL), encoding="utf-8")
        (cls.project / "where.py").write_text("import cad, parts\nprint('LIBRARY ' + cad.__file__)\n", encoding="utf-8")

    @classmethod
    def run_(cls, *args: str):
        return engine_daemon.run([sys.executable, "-m", "cad_server.cli", "run", *args], cwd=cls.project, env=cls.env)

    def test_a_model_beside_a_cad_py_builds_on_the_library_and_imports_its_own_modules(self) -> None:
        done = self.run_("model.py")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("its own cad.py", done.stdout + done.stderr)
        self.assertTrue((self.project / "box.step").is_file(), done.stdout + done.stderr)

    def test_a_module_and_code_run_with_the_working_folder_last(self) -> None:
        for args in (["-m", "where"], ["-c", "import runpy; runpy.run_path('where.py')"]):
            with self.subTest(args=args[0]):
                done = self.run_(*args)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                library = Path(done.stdout.split("LIBRARY ", 1)[1].strip()).resolve()
                self.assertNotEqual(library.parent, self.project)
                self.assertEqual(library.name, "__init__.py")

    def test_a_model_script_named_as_the_library_is_refused(self) -> None:
        named = self.folder / "named"
        named.mkdir()
        (named / "cad.py").write_text(textwrap.dedent(MODEL.replace("import parts\n", "").replace("parts.SIZE", "2")),
                                      encoding="utf-8")
        done = engine_daemon.run([sys.executable, "-m", "cad_server.cli", "run", "cad.py"], cwd=named, env=self.env)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("under the library's own name 'cad'", done.stdout + done.stderr)


if __name__ == "__main__":
    unittest.main()
