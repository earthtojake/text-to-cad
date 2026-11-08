"""``cadgen``, the library's earlier import name, is the library itself (``src/cadgen/__init__.py``).

Every top-level name of ``cadgen`` is ``cad``'s own, and every module ``cadgen.<x>`` is the module object
``cad.<x>``: imported once, under its own name, and handed out as it is -- never a second copy whose
classes and memo would be strangers to the first. It is deprecated, and importing it says so once per
process, as any alias of the library does (``cad._internal.aliases.warn``).

Run in a fresh interpreter each: this one has imported ``cad`` already, and the alias must hold whichever
name a process imports first.
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

from tests.python.support.paths import SOURCE_PATH


SAID = "cadgen is deprecated; use cad"


def run(code: str) -> dict:
    """``code``'s last line as JSON, every warning an error but the one this file expects."""
    done = subprocess.run([sys.executable, "-W", "error", "-W", f"ignore:{SAID}", "-c", textwrap.dedent(code)],
                          capture_output=True, text=True, env={**os.environ, "PYTHONPATH": SOURCE_PATH}, timeout=120)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


class AliasTest(unittest.TestCase):
    def test_every_module_of_cadgen_is_the_library_s_own_module(self) -> None:
        found = run("""
            import json, sys
            import cadgen.build123d
            import cad, cad.build123d
            from cadgen.step import read
            from cadgen.engine.model import Model
            import cad.step, cad.engine.model
            print(json.dumps({
                "build123d": cadgen.build123d is cad.build123d,
                "step": sys.modules["cadgen.step"] is cad.step and read is cad.step.read,
                "model": sys.modules["cadgen.engine.model"] is cad.engine.model and Model is cad.engine.model.Model,
                "named": [cad.build123d.__name__, Model.__module__],
                "copies": sorted({module.__file__ for name, module in sys.modules.items()
                                  if name.startswith("cadgen.") and getattr(module, "__file__", None)}
                                 - {module.__file__ for name, module in sys.modules.items()
                                    if name.startswith("cad.") and getattr(module, "__file__", None)}),
            }))
        """)
        self.assertEqual(found, {"build123d": True, "step": True, "model": True,
                                 "named": ["cad.build123d", "cad.engine.model"],
                                 "copies": []})

    def test_every_top_level_name_is_the_library_s(self) -> None:
        found = run("""
            import json
            import cadgen
            import cad
            print(json.dumps({
                "same": all(getattr(cadgen, name) is getattr(cad, name) for name in cad.__all__),
                "dir": dir(cadgen) == dir(cad),
                "version": cadgen.__version__ == cad.__version__,
            }))
        """)
        self.assertEqual(found, {"same": True, "dir": True, "version": True})

    def test_a_model_written_against_cadgen_builds_names_as_cad(self) -> None:
        found = run("""
            import json
            from cadgen import model, step
            import cad
            print(json.dumps({"model": model is cad.model, "step": step is cad.step}))
        """)
        self.assertEqual(found, {"model": True, "step": True})

    def test_a_module_neither_name_has_is_not_found_under_the_name_asked(self) -> None:
        found = run("""
            import json
            try:
                import cadgen.no_such_module_here
            except ModuleNotFoundError as error:
                missing = error.name
            print(json.dumps({"missing": missing}))
        """)
        self.assertEqual(found, {"missing": "cadgen.no_such_module_here"})


class WarningTest(unittest.TestCase):
    def run_script(self, source: str, *options: str) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "old.py").write_text(source, encoding="utf-8")
            return subprocess.run([sys.executable, *options, "old.py"], capture_output=True, text=True, cwd=folder,
                                  env={**os.environ, "PYTHONPATH": SOURCE_PATH}, timeout=120)

    def test_it_warns_once_a_process_naming_cad_at_the_line_that_imported_it(self) -> None:
        for source, line in (("import cadgen\nimport cadgen.step\nfrom cadgen import model\nimport cadgen\n", 1),
                             ("from cadgen import model\nimport cadgen\n", 1),
                             ("import cad\nimport cadgen.build123d\n", 2),
                             ("import cad\n\nfrom cadgen.step import read\n", 3)):
            with self.subTest(source=source):
                done = self.run_script(source)
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(done.stdout, "")
                self.assertEqual([line_ for line_ in done.stderr.splitlines() if "CadDeprecationWarning" in line_],
                                 [f"old.py:{line}: CadDeprecationWarning: {SAID}"])

    def test_it_is_an_error_where_the_warning_is_as_any_alias_s_is(self) -> None:
        done = self.run_script("import cadgen\n", "-W", "error::cad.CadDeprecationWarning")
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertEqual(done.stderr.splitlines()[-1], f"cad._internal.aliases.CadDeprecationWarning: {SAID}")

    def test_the_library_says_nothing_of_it_and_does_not_load_it(self) -> None:
        found = subprocess.run([sys.executable, "-W", "error", "-c",
                                "import sys, cad, cad.engine.api, cad.engine.build, cad.step, cad.build123d\n"
                                "print('cadgen' in sys.modules)\n"], capture_output=True, text=True,
                               env={**os.environ, "PYTHONPATH": SOURCE_PATH}, timeout=120)
        self.assertEqual((found.returncode, found.stdout.strip()), (0, "False"), found.stderr)


class EarlierProgramTest(unittest.TestCase):
    """A program written for cadgen 0.7 that ``cad run`` runs (``cad._internal.program``) stops at its first
    import of a name 0.8 took out, as Python says it, then names the guide from 0.7 to 0.8; any other import
    failure is said as Python says it alone."""

    def run_program(self, source: str) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / "model.py"
            script.write_text(source, encoding="utf-8")
            return subprocess.run([sys.executable, "-P", "-m", "cad._internal.program", str(script)],
                                  capture_output=True, text=True, cwd=folder, timeout=120,
                                  env={**os.environ, "PYTHONPATH": SOURCE_PATH})

    def test_a_name_0_7_had_names_the_guide(self) -> None:
        guide = "https://github.com/earthtojake/text-to-cad/blob/main/docs/migrations/migrating-0.7-to-0.8.md"
        for source, said in (("from cadgen import read_scene\n", "cannot import name 'read_scene' from 'cadgen'"),
                             ("import cadgen.no_such_module_here\n", "No module named 'cadgen.no_such_module_here'")):
            with self.subTest(source=source):
                done = self.run_program(source)
                self.assertEqual(done.returncode, 1, done.stderr)
                *failure, last = done.stderr.rstrip().splitlines()
                self.assertIn(said, failure[-1])
                self.assertTrue(last.endswith(guide), done.stderr)

    def test_another_import_failure_names_no_guide(self) -> None:
        done = self.run_program("from no_such_module_here import x\n")
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn("No module named 'no_such_module_here'", done.stderr)
        self.assertNotIn("migrating", done.stderr)


if __name__ == "__main__":
    unittest.main()
