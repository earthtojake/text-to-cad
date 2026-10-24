"""``import build123d`` binds a module the kernel loads into on its first attribute
(``cadgen._internal.lazy_kernel``), installed by the wheel's ``cadgen-lazy-kernel.pth``.

The finder's behaviour is tested on a stand-in package (its name put in ``KERNEL``), so the real
kernel's ~2.5 s is paid only by the subprocess that shows the real one stays untouched."""

from __future__ import annotations

import importlib
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from cadgen._internal import lazy_kernel

PACKAGE = Path(__file__).resolve().parents[4] / "packages" / "cadgen"
SRC = PACKAGE / "src"


class FinderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="lazy-kernel-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        package = self.folder / "standin_kernel"
        (package / "sub").mkdir(parents=True)
        (package / "__init__.py").write_text(textwrap.dedent("""
            import builtins
            builtins.standin_kernel_runs = getattr(builtins, "standin_kernel_runs", 0) + 1
            Box = "a box"
        """), encoding="utf-8")
        (package / "sub" / "__init__.py").write_text("PART = 'a part'\n", encoding="utf-8")
        self.enterContext(mock.patch.object(sys, "path", [str(self.folder), *sys.path]))
        self.enterContext(mock.patch.object(lazy_kernel, "KERNEL", ("standin_kernel",)))
        self.addCleanup(self._forget)
        import builtins

        builtins.standin_kernel_runs = 0
        lazy_kernel.install()

    @staticmethod
    def _forget() -> None:
        import builtins

        for name in [name for name in sys.modules if name.partition(".")[0] == "standin_kernel"]:
            del sys.modules[name]
        builtins.__dict__.pop("standin_kernel_runs", None)
        importlib.invalidate_caches()

    @staticmethod
    def runs() -> int:
        import builtins

        return builtins.standin_kernel_runs

    def test_import_binds_a_module_whose_body_has_not_run(self) -> None:
        import standin_kernel  # noqa: F401

        self.assertIs(type(sys.modules["standin_kernel"]), lazy_kernel.KernelModule)
        self.assertEqual(self.runs(), 0)
        self.assertFalse(lazy_kernel.loaded("standin_kernel"))

    def test_importing_it_again_loads_nothing(self) -> None:
        # A project's helper module imports it as its script did: the import system reads the
        # bound module's __spec__, which the standard library's lazy module would load on.
        import standin_kernel  # noqa: F401
        importlib.import_module("standin_kernel")
        exec("import standin_kernel as again", {})
        self.assertEqual(self.runs(), 0)
        self.assertFalse(lazy_kernel.loaded("standin_kernel"))
        self.assertEqual(sys.modules["standin_kernel"].Box, "a box")
        self.assertEqual(self.runs(), 1)
        self.assertIs(type(sys.modules["standin_kernel"]), type(sys))

    def test_the_first_attribute_loads_it_once(self) -> None:
        import standin_kernel

        self.assertEqual(standin_kernel.Box, "a box")
        self.assertEqual(self.runs(), 1)
        self.assertTrue(lazy_kernel.loaded("standin_kernel"))
        self.assertEqual(standin_kernel.Box, "a box")
        self.assertEqual(self.runs(), 1, "loaded once")

    def test_a_from_import_loads_it_there_and_a_submodule_imports(self) -> None:
        from standin_kernel import Box

        self.assertEqual((Box, self.runs()), ("a box", 1))
        import standin_kernel.sub

        self.assertEqual(standin_kernel.sub.PART, "a part")

    def test_a_submodule_import_loads_its_package_first(self) -> None:
        import standin_kernel.sub

        self.assertEqual((standin_kernel.sub.PART, self.runs()), ("a part", 1))

    def test_installing_twice_is_one_finder_and_other_names_are_not_its(self) -> None:
        lazy_kernel.install()
        lazy_kernel.install()
        self.assertEqual(sum(isinstance(finder, lazy_kernel.LazyKernelFinder) for finder in sys.meta_path), 1)
        self.assertIsNone(lazy_kernel.LazyKernelFinder().find_spec("json"))
        self.assertIsNone(lazy_kernel.LazyKernelFinder().find_spec("standin_kernel.sub"))
        self.assertFalse(lazy_kernel.loaded("no_such_module_here"))


class PthTest(unittest.TestCase):
    """The ``.pth`` the wheel ships, run as the interpreter runs one, before anything is imported:
    ``import build123d`` leaves the kernel untouched until an attribute is read. Run in a
    subprocess: this one may have the kernel loaded already."""

    def run_python(self, code: str) -> str:
        site = Path(tempfile.mkdtemp(prefix="lazy-site-")).resolve()
        self.addCleanup(shutil.rmtree, site, ignore_errors=True)
        shutil.copy(PACKAGE / "cadgen-lazy-kernel.pth", site / "cadgen-lazy-kernel.pth")
        found = subprocess.run([sys.executable, "-c", f"import site; site.addsitedir({str(site)!r}); {code}"],
                               capture_output=True, text=True, cwd=site,
                               env={**os.environ, "PYTHONPATH": str(SRC)})
        self.assertEqual(found.returncode, 0, found.stderr)
        return found.stdout.strip()

    def test_the_installed_cadgen_runs_the_pth_editable_or_not(self) -> None:
        """setup.py ships it in an editable wheel too, so a checkout's ``requirements-dev.txt``
        venv (CI's included) defers the kernel as a user's install does."""
        found = subprocess.run([sys.executable, "-c", "import build123d, sys; print('OCP' in sys.modules)"],
                               capture_output=True, text=True, cwd=tempfile.gettempdir())
        self.assertEqual((found.returncode, found.stdout.strip()), (0, "False"),
                         found.stderr or "no cadgen-lazy-kernel.pth: reinstall requirements-dev.txt")

    def test_the_pth_is_one_import_line(self) -> None:
        self.assertEqual((PACKAGE / "cadgen-lazy-kernel.pth").read_text(encoding="utf-8"),
                         "import cadgen._internal.lazy_kernel\n")

    def test_import_build123d_leaves_the_kernel_untouched(self) -> None:
        self.assertEqual(self.run_python("import build123d as bd; import sys; print('OCP' in sys.modules)"), "False")

    def test_a_second_import_build123d_leaves_the_kernel_untouched(self) -> None:
        self.assertEqual(self.run_python("import build123d as bd; import build123d; import sys; "
                                         "print('OCP' in sys.modules)"), "False")

    def test_the_first_attribute_loads_the_kernel(self) -> None:
        self.assertEqual(self.run_python("import build123d as bd; import sys; bd.Box(1, 1, 1); "
                                         "print('OCP' in sys.modules)"), "True")


if __name__ == "__main__":
    unittest.main()
