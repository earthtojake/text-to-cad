"""Which directories count as third-party when classifying a generator's source closure.

The classification decides what gets EVICTED from ``sys.modules`` before a build. Getting
it wrong for an installed package is not a near-miss: eviction forces a re-import, and a
C extension re-imported mid-process fails with an error that names something else
entirely (numpy reports a missing ``dtypes`` attribute). This was found by running the
CLI against a real wheel install whose dependencies came from a ``.pth`` line -- a
site-packages that belonged to no interpreter prefix, and so looked like model code.
"""

import sys
import unittest
from pathlib import Path

from cadgen._internal import source_hash


class InterpreterRoots(unittest.TestCase):
    def setUp(self):
        source_hash._interpreter_roots.cache_clear()
        source_hash._excluded_roots.cache_clear()
        source_hash.is_first_party_source_file.cache_clear()
        source_hash._MODULE_FILE_FIRST_PARTY.clear()
        self.addCleanup(source_hash._interpreter_roots.cache_clear)
        self.addCleanup(source_hash._excluded_roots.cache_clear)
        self.addCleanup(source_hash.is_first_party_source_file.cache_clear)
        self.addCleanup(source_hash._MODULE_FILE_FIRST_PARTY.clear)

    def test_a_site_packages_reached_by_pth_is_third_party(self):
        """Not every site-packages belongs to sys.prefix."""
        extra = Path("/tmp/some-other-venv/lib/python3.13/site-packages").resolve()
        sys.path.append(str(extra))
        self.addCleanup(sys.path.remove, str(extra))
        source_hash._interpreter_roots.cache_clear()
        source_hash._excluded_roots.cache_clear()
        source_hash.is_first_party_source_file.cache_clear()

        self.assertFalse(
            source_hash.is_first_party_source_file(extra / "numpy" / "__init__.py"),
            "a site-packages on sys.path must be third-party wherever it came from",
        )

    def test_dist_packages_counts_too(self):
        extra = Path("/tmp/debianish/lib/python3/dist-packages").resolve()
        sys.path.append(str(extra))
        self.addCleanup(sys.path.remove, str(extra))
        source_hash._interpreter_roots.cache_clear()
        source_hash._excluded_roots.cache_clear()
        source_hash.is_first_party_source_file.cache_clear()

        self.assertFalse(source_hash.is_first_party_source_file(extra / "pkg" / "mod.py"))

    def test_ordinary_model_code_is_still_first_party(self):
        """The point of the closure: a generator beside the model must NOT be excluded."""
        self.assertTrue(
            source_hash.is_first_party_source_file(Path("/tmp/models/widget.py").resolve())
        )

    def test_the_running_cadgen_is_never_first_party(self):
        self.assertFalse(
            source_hash.is_first_party_source_file(Path(source_hash.__file__).resolve())
        )


class MainModuleIsNotALauncher(unittest.TestCase):
    """Under the model-script contract ``__main__`` IS the user's model.

    ``_runtime_roots`` used to append ``__main__``'s directory unconditionally,
    so ``python src/model.py`` classified the whole ``src/`` — including
    ``src/lib/`` shared helpers — as runtime, dropped them from the recorded
    closure, and silently disabled staleness detection for exactly the layout
    the cad skill's project-layout reference mandates (while the daemon path, whose ``__main__``
    is the worker, recorded a different closure and therefore a DIFFERENT
    package key for the same source)."""

    def setUp(self):
        source_hash._runtime_roots.cache_clear()
        source_hash._excluded_roots.cache_clear()
        source_hash.is_first_party_source_file.cache_clear()
        source_hash._MODULE_FILE_FIRST_PARTY.clear()
        self.addCleanup(source_hash._runtime_roots.cache_clear)
        self.addCleanup(source_hash._excluded_roots.cache_clear)
        self.addCleanup(source_hash.is_first_party_source_file.cache_clear)
        self.addCleanup(source_hash._MODULE_FILE_FIRST_PARTY.clear)

    def _with_main_file(self, main_file):
        import types

        original = sys.modules.get("__main__")
        stub = types.ModuleType("__main__")
        if main_file is not None:
            stub.__file__ = str(main_file)
        sys.modules["__main__"] = stub
        self.addCleanup(sys.modules.__setitem__, "__main__", original)

    def test_a_model_script_main_does_not_exclude_its_project(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            (src / "lib").mkdir(parents=True)
            script = src / "model.py"
            script.write_text("pass\n", encoding="utf-8")
            helper = src / "lib" / "spec.py"
            helper.write_text("X = 1\n", encoding="utf-8")
            self._with_main_file(script)
            self.assertTrue(source_hash.is_first_party_source_file(script.resolve()))
            self.assertTrue(source_hash.is_first_party_source_file(helper.resolve()))

    def test_a_launcher_main_still_excludes_its_directory(self):
        """A script inside the interpreter's own roots (a console script in the
        venv's bin/) is a launcher; its directory stays runtime."""
        launcher_dir = Path(sys.prefix) / "bin"
        launcher = launcher_dir / "cadgen"
        if not launcher.is_file():
            self.skipTest("no console script in this environment")
        self._with_main_file(launcher)
        self.assertIn(launcher_dir.resolve(), source_hash._runtime_roots())


if __name__ == "__main__":
    unittest.main()
