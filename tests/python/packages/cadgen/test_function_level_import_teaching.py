"""A sibling import inside the model function names the rule it broke.

The loader seeds the generator's folder onto ``sys.path`` for the module body
only. ``from lib import x`` at the top of a helper works; the same line inside
the model function, run by the pipeline from another directory (the warm
daemon's worker, a CLI invocation), fails -- and used to fail with a bare
``ModuleNotFoundError: No module named 'lib'`` that named neither the rule nor
the fix (w16 BUGS.md #1).
"""

from __future__ import annotations

import os
import tempfile
import textwrap
import unittest
from pathlib import Path


class FunctionLevelImportTeachingTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="cadgen-lazy-import-")
        self.root = Path(self._tmp.name)
        self.project = self.root / "proj"
        (self.project / "lib").mkdir(parents=True)
        (self.project / "lib" / "__init__.py").write_text("", encoding="utf-8")
        (self.project / "lib" / "dims.py").write_text("def size():\n    return 5\n", encoding="utf-8")
        self._env = {k: os.environ.get(k) for k in ("CADGEN_CACHE_DIR", "CADGEN_DAEMON")}
        os.environ["CADGEN_CACHE_DIR"] = str(self.root / "cache")
        os.environ["CADGEN_DAEMON"] = "0"
        self._cwd = os.getcwd()
        os.chdir(self.root)  # NOT the project: the script's folder is off sys.path, as in a worker

    def tearDown(self) -> None:
        os.chdir(self._cwd)
        for key, value in self._env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmp.cleanup()

    def _model(self, name: str, body: str) -> Path:
        path = self.project / f"{name}.py"
        path.write_text(textwrap.dedent(body), encoding="utf-8")
        return path

    def test_sibling_import_inside_the_function_teaches_the_rule(self) -> None:
        from cadgen.generation import generate_step_targets

        script = self._model(
            "lazy_import",
            '''
            from cadgen import build123d as bd
            from cadgen import step

            @step(out="lazy_import.step")
            def lazy_import():
                from lib import dims
                return bd.Box(dims.size(), 5, 5)


            if __name__ == "__main__":
                lazy_import()
            ''',
        )
        with self.assertRaises(RuntimeError) as raised:
            generate_step_targets([str(script)], force=True)
        message = str(raised.exception)
        self.assertIn("`import lib` ran inside the model function", message)
        self.assertIn("module top level", message)
        self.assertIsInstance(raised.exception.__cause__, ModuleNotFoundError)

    def test_a_genuinely_missing_package_keeps_its_own_error(self) -> None:
        from cadgen.generation import generate_step_targets

        script = self._model(
            "missing_dep",
            '''
            from cadgen import build123d as bd
            from cadgen import step

            @step(out="missing_dep.step")
            def missing_dep():
                import no_such_third_party_package_xyz
                return bd.Box(5, 5, 5)


            if __name__ == "__main__":
                missing_dep()
            ''',
        )
        with self.assertRaises(ModuleNotFoundError):
            generate_step_targets([str(script)], force=True)


if __name__ == "__main__":
    unittest.main()
