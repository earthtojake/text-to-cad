"""A model script is plain Python. One inside a package -- folders holding an ``__init__.py``
-- is that package's module, imported by its dotted name as ``python -m`` imports it: its
relative imports at any depth, a module beside it by its own name and the package by its name
all resolve, in a build, run as ``python model.py``, and in the warm worker build after build;
an edit to a module it imports re-runs its body. A loose script is the module its stem names."""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest import mock

from cad.engine import build as engine_build
from cad.engine import previous, read_xbf
from tests.python.support import engine_daemon
from tests.python.support.paths import add_sources

SRC = add_sources()  # the three packages' sources, as PYTHONPATH names them

MODEL = """
import build123d as bd
from cad.engine import xbf

import helper                       # beside the script, by its own name
import proj.common.dims as dims     # the package, by its name
from .lib import WIDTH              # one level: its own package
from ..common.dims import HEIGHT    # two levels: its package's parent


@xbf("XBF/bracket.xbf")
def bracket():
    return bd.Box(WIDTH, 10, HEIGHT) - bd.Cylinder(helper.RADIUS, dims.HEIGHT * 2)

if __name__ == "__main__":
    bracket()
"""

PACKAGE = {"proj/__init__.py": "", "proj/common/__init__.py": "", "proj/common/dims.py": "HEIGHT = 5\n",
           "proj/parts/__init__.py": "", "proj/parts/lib.py": "WIDTH = 20\n", "proj/parts/helper.py": "RADIUS = 2\n",
           "proj/parts/model.py": MODEL}


def write(root: Path, files: dict[str, str]) -> None:
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text), encoding="utf-8")
        # A rewrite within the same clock tick still reads as a new file.
        os.utime(path, ns=(time.time_ns(), time.time_ns()))


class PackageScriptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="engine-package-")).resolve()
        self.addCleanup(shutil.rmtree, self.root, True)
        write(self.root, PACKAGE)
        self.script = self.root / "proj/parts/model.py"
        self.xbf = self.root / "proj/parts/XBF/bracket.xbf"

    def build(self, script: Path) -> dict:
        [report] = engine_build.build(script, cwd=self.root)
        self.assertTrue(report["ok"], report.get("error"))
        return report

    def test_a_script_in_a_package_is_its_module_and_an_edit_to_what_it_imports_reruns_it(self) -> None:
        cold = self.build(self.script)
        self.assertEqual(cold["bodies"], {"model.py::bracket": "run"})
        module = sys.modules["proj.parts.model"]
        self.assertEqual((Path(module.__file__), module.__package__), (self.script, "proj.parts"))
        self.assertIs(sys.modules["proj.parts"].model, module)
        # The closure keys every module the load imported by its path, the packages' too.
        modules = {path for path, _digest in previous.of(self.xbf)["modules"]}
        self.assertLessEqual({"../lib.py", "../helper.py", "../../common/dims.py", "../../__init__.py"}, modules)
        warm = self.build(self.script)
        self.assertEqual((warm["bodies"], warm["cache"]), ({"model.py::bracket": "loaded"}, {"used": True, "from": "memory"}))
        self.assertFalse(warm["files"][str(self.xbf)]["written"])
        write(self.root, {"proj/common/dims.py": "HEIGHT = 7\n"})
        edited = self.build(self.script)
        self.assertEqual(edited["bodies"], {"model.py::bracket": "run"})
        self.assertIn("../../common/dims.py: HEIGHT changed", edited["cache"]["changed"])
        self.assertAlmostEqual(read_xbf(self.xbf).bounding_box().size.Z, 7)

    def test_a_namespace_package_s_modules_are_the_model_s_imported_again_and_keyed(self) -> None:
        # `lib/` holds no __init__.py: a namespace package, which has no file of its own. Its
        # modules are the model's like any other: an edit to one runs the body, in the warm
        # process, and the closure keys them by their paths.
        write(self.root, {"craft/lib/empennage.py": "SPAN = 4\n", "craft/f14.py": """
            import build123d as bd
            from cad.engine import xbf

            from lib import empennage


            @xbf("XBF/f14.xbf")
            def f14():
                return bd.Box(10, empennage.SPAN, 2)
        """})
        script = self.root / "craft/f14.py"
        xbf = self.root / "craft/XBF/f14.xbf"
        self.build(script)
        self.assertIn("../lib/empennage.py", {path for path, _digest in previous.of(xbf)["modules"]})
        self.assertEqual(self.build(script)["bodies"], {"f14.py::f14": "loaded"})
        write(self.root, {"craft/lib/empennage.py": "SPAN = 9\n"})
        edited = self.build(script)
        self.assertEqual(edited["bodies"], {"f14.py::f14": "run"})
        self.assertIn("../lib/empennage.py: SPAN changed", edited["cache"]["changed"])
        self.assertAlmostEqual(read_xbf(xbf).bounding_box().size.Y, 9)

    def test_a_loose_script_is_the_module_its_stem_names(self) -> None:
        # In the package's tree, but its own folder holds no __init__.py.
        write(self.root, {"proj/tools/holes.py": "RADIUS = 1\n", "proj/tools/plate.py": """
            import build123d as bd
            from cad.engine import xbf

            import holes


            @xbf("XBF/plate.xbf")
            def plate():
                return bd.Box(10, 10, 2) - bd.Cylinder(holes.RADIUS, 4)
        """})
        script = self.root / "proj/tools/plate.py"
        self.build(script)
        module = sys.modules["plate"]
        self.assertEqual((Path(module.__file__), module.__package__), (script, ""))

    def test_two_edits_in_one_second_run_the_second_not_a_pyc_another_tool_left(self) -> None:
        """CPython takes a ``.pyc`` as current by the source's whole-second mtime and its size: an
        edit of the same length inside the second a tool compiled the file would run that tool's
        bytecode. The worker compiles the model's own modules from the bytes on disk."""
        import py_compile

        def same_second_edit(relative: str, old: str, new: str) -> None:
            path = self.root / relative
            stat = path.stat()
            py_compile.compile(str(path), doraise=True)  # another tool compiles the first edit
            text = path.read_text(encoding="utf-8")
            assert len(old) == len(new) and text.count(old) == 1
            path.write_text(text.replace(old, new), encoding="utf-8")  # the same length...
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))  # ...inside the same second

        self.build(self.script)
        same_second_edit("proj/common/dims.py", "HEIGHT = 5", "HEIGHT = 8")  # a module the script imports
        self.build(self.script)
        self.assertAlmostEqual(read_xbf(self.xbf).bounding_box().size.Z, 8)
        same_second_edit("proj/parts/model.py", "bd.Box(WIDTH, 10,", "bd.Box(WIDTH, 30,")  # the script itself
        self.build(self.script)
        self.assertAlmostEqual(read_xbf(self.xbf).bounding_box().size.Y, 30)
        # A loose script is compiled from its source too.
        write(self.root, {"proj/tools/plate.py": """
            import build123d as bd
            from cad.engine import xbf


            @xbf("XBF/plate.xbf")
            def plate():
                return bd.Box(10, 10, 2)
        """})
        loose = self.root / "proj/tools/plate.py"
        plate = self.root / "proj/tools/XBF/plate.xbf"
        self.build(loose)
        same_second_edit("proj/tools/plate.py", "bd.Box(10, 10, 2)", "bd.Box(10, 10, 6)")
        self.build(loose)
        self.assertAlmostEqual(read_xbf(plate).bounding_box().size.Z, 6)

    def test_body_only_imports_track_ordinary_and_editable_source_bytes(self) -> None:
        import py_compile

        helper, editable = self.root / "body_helper.py", self.root / "editable" / "parts.py"
        editable.parent.mkdir()
        helper.write_text("WIDTH=1\n", encoding="utf-8")
        editable.write_text("HEIGHT=1\n", encoding="utf-8")
        script, xbf = self.root / "body.py", self.root / "XBF" / "body.xbf"
        script.write_text("import build123d as bd\nfrom cadgen import xbf\n@xbf('XBF/body.xbf')\n"
                          "def body():\n    from body_helper import WIDTH\n    from body_editable import HEIGHT\n"
                          "    return bd.Box(WIDTH,HEIGHT,1)\n", encoding="utf-8")

        class EditableFinder(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                return importlib.util.spec_from_file_location(fullname, editable) if fullname == "body_editable" else None

        with mock.patch.object(sys, "meta_path", [EditableFinder(), *sys.meta_path]):
            first = self.build(script)
            self.assertEqual({str(helper), str(editable)} - {
                path for path, _digest in first["closure"]["modules"]}, set())
            self.assertTrue(self.build(script)["cache"]["used"])
            for target, text, expected in ((helper, "WIDTH=2\n", (2, 1, 1)),
                                           (editable, "HEIGHT=3\n", (2, 3, 1))):
                stamp = target.stat()
                py_compile.compile(str(target), doraise=True)
                target.write_text(text, encoding="utf-8")
                os.utime(target, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
                edited = self.build(script)
                self.assertEqual(edited["bodies"], {"body.py::body": "run"})
                bounds = read_xbf(xbf).bounding_box().size
                self.assertEqual((bounds.X, bounds.Y, bounds.Z), expected)
            # A body-only import uses the established byte fallback, so comments count too.
            helper.write_text("# comment\nWIDTH=2\n", encoding="utf-8")
            commented = self.build(script)
            self.assertEqual(commented["bodies"], {"body.py::body": "run"})
            self.assertNotEqual(commented["closure"]["key"], edited["closure"]["key"])


class SourceFinderTest(unittest.TestCase):
    def test_source_hash_and_same_run_guard_detect_restored_timestamps(self) -> None:
        from cad.engine import sources

        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "helper.py"
            source.write_text("VALUE=1\n", encoding="utf-8")
            stamp = source.stat()
            # Even file identity and every timestamp can remain identical within one clock tick.
            with mock.patch.object(os, "stat", return_value=stamp):
                first, guard = sources.digest(source), engine_build._stat(source)
                source.write_text("VALUE=2\n", encoding="utf-8")
                os.utime(source, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
                self.assertNotEqual(first, sources.digest(source))
                self.assertNotEqual(guard, engine_build._stat(source))

    def test_source_resolution_handles_namespaces_and_editable_packages_without_execution(self) -> None:
        import zipfile
        from cad.engine import sources

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            namespace = root / "cadgen_fixture_namespace" / "nested" / "parts.py"
            namespace.parent.mkdir(parents=True)
            namespace.write_text("VALUE=1\n", encoding="utf-8")
            package = root / "mapped" / "__init__.py"
            package.parent.mkdir()
            package.write_text("from .dims import WIDTH\nraise AssertionError('package executed')\n", encoding="utf-8")
            dimensions = package.parent / "dims.py"
            dimensions.write_text("WIDTH=2\n", encoding="utf-8")
            archive = root / "sources.zip"
            with zipfile.ZipFile(archive, "w") as zipped:
                zipped.writestr("zip_helper_source.py", "raise AssertionError('zip executed')\n")

            class EditableFinder(importlib.abc.MetaPathFinder):
                def find_spec(self, fullname, path=None, target=None):
                    if fullname == "virtual_helper_source":
                        return importlib.util.spec_from_file_location(fullname, root / "absent.py")
                    return importlib.util.spec_from_file_location(fullname, package) if fullname == "mapped_helper_package" else None

            with mock.patch.object(sys, "path", [str(archive), str(root), *sys.path]), \
                    mock.patch.object(sys, "meta_path", [EditableFinder(), *sys.meta_path]):
                self.assertEqual(sources._files("cadgen_fixture_namespace.nested.parts"), [
                    ("cadgen_fixture_namespace.nested.parts", namespace)])
                self.assertEqual(set(sources.closure_files(package, "mapped_helper_package")), {package, dimensions})
                self.assertEqual(sources._files("zip_helper_source"), [])
                self.assertEqual(sources._files("virtual_helper_source"), [])
            self.assertNotIn("mapped_helper_package", sys.modules)
            self.assertNotIn("cadgen_fixture_namespace", sys.modules)

    def test_an_editable_hook_imports_current_source_once_after_same_size_edits(self) -> None:
        import py_compile

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            source, script = root / "source" / "editable_helper.py", root / "model.py"
            source.parent.mkdir()
            source.write_text("WIDTH=1\nwith open(__file__+'.runs','a') as log: log.write(str(WIDTH)+'\\n')\n", encoding="utf-8")
            script.write_text("from editable_helper import WIDTH\nVALUE=WIDTH\n", encoding="utf-8")
            stamp = source.stat()
            py_compile.compile(str(source), doraise=True)

            class EditableFinder(importlib.abc.MetaPathFinder):
                def find_spec(self, fullname, path=None, target=None):
                    if fullname == "editable_helper":
                        return importlib.util.spec_from_file_location(fullname, source)
                    return None

            self.addCleanup(sys.modules.pop, "editable_helper", None)
            # Hooks installed after an earlier build can precede the existing source finder.
            engine_build._from_source()
            with mock.patch.object(sys, "meta_path", [EditableFinder(), *sys.meta_path]):
                for width in (2, 3):
                    source.write_text(source.read_text(encoding="utf-8").replace(f"WIDTH={width-1}", f"WIDTH={width}"), encoding="utf-8")
                    os.utime(source, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
                    loaded = engine_build.load_script(script)
                    self.assertEqual(loaded.VALUE, width)
                    self.assertIs(type(sys.modules["editable_helper"].__loader__), engine_build._SourceOnlyLoader)
            self.assertEqual(Path(str(source) + ".runs").read_text(encoding="utf-8").splitlines(), ["2", "3"])

    def test_finder_order_and_library_native_and_custom_loaders_are_preserved(self) -> None:
        source_finder = engine_build._FirstPartyFromSource()

        class CustomSource(importlib.machinery.SourceFileLoader):
            pass

        loaders = [importlib.machinery.SourceFileLoader("library", json.__file__),
                   importlib.machinery.ExtensionFileLoader("native", "native.so"),
                   CustomSource("custom", __file__), None]
        for loader in loaders:
            with self.subTest(loader=type(loader).__name__):
                spec = importlib.machinery.ModuleSpec("probe", loader, origin=getattr(loader, "path", None))
                earlier = mock.Mock(find_spec=mock.Mock(return_value=None))
                selected = mock.Mock(find_spec=mock.Mock(return_value=spec))
                later = mock.Mock(find_spec=mock.Mock(side_effect=AssertionError("finder precedence changed")))
                with mock.patch.object(sys, "meta_path", [source_finder, earlier, selected, later]):
                    self.assertIs(source_finder.find_spec("probe", None), spec)
                self.assertIs(spec.loader, loader)
                earlier.find_spec.assert_called_once_with("probe", None, None)
                selected.find_spec.assert_called_once_with("probe", None, None)

    def test_a_delegating_editable_finder_does_not_recurse_or_execute_twice(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder).resolve() / "delegated_helper.py"
            source.write_text("VALUE=7\nwith open(__file__+'.runs','a') as log: log.write('run\\n')\n", encoding="utf-8")

            class Delegate(importlib.abc.MetaPathFinder):
                active = False

                def find_spec(self, fullname, path=None, target=None):
                    if fullname != "delegated_helper" or self.active:
                        return None
                    self.active = True
                    try:
                        return importlib.util.find_spec(fullname)
                    finally:
                        self.active = False

            class Editable(importlib.abc.MetaPathFinder):
                def find_spec(self, fullname, path=None, target=None):
                    return importlib.util.spec_from_file_location(fullname, source) if fullname == "delegated_helper" else None

            self.addCleanup(sys.modules.pop, "delegated_helper", None)
            source_finder = engine_build._FirstPartyFromSource()
            with mock.patch.object(sys, "meta_path", [source_finder, Delegate(), Editable(), *sys.meta_path]):
                module = importlib.import_module("delegated_helper")
                self.assertEqual(module.VALUE, 7)
                self.assertIs(type(module.__loader__), engine_build._SourceOnlyLoader)
                self.assertEqual(Path(str(source) + ".runs").read_text(encoding="utf-8"), "run\n")


class PackageScriptRunTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="engine-package-run-")).resolve()
        self.state = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        self.env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC), "CADGEN_ENGINE_DIR": str(self.state),
                                          "CADGEN_ENGINE_MESH": "inline"}, self.addCleanup)
        self.addCleanup(self._stop)

    def _stop(self) -> None:
        self.python("-m", "cad_server.engine", "stop")
        deadline = time.monotonic() + 20
        while any(self.state.glob("*.door")) and time.monotonic() < deadline:
            time.sleep(0.05)
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.state, ignore_errors=True)

    def python(self, *args: str) -> subprocess.CompletedProcess:
        return engine_daemon.run([sys.executable, *args], cwd=self.root, env=self.env)

    def run_script(self) -> str:
        done = self.python("proj/parts/model.py")
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def test_running_a_script_in_a_package_builds_it_in_the_warm_worker_across_edits(self) -> None:
        write(self.root, PACKAGE)
        self.assertIn("bodies 1 run", self.run_script())
        write(self.root, {"proj/common/dims.py": "HEIGHT = 7\n"})
        edited = self.run_script()
        self.assertIn("bodies 1 run", edited)
        self.assertIn("rebuilt: ../../common/dims.py: HEIGHT changed", edited)
        workers = json.loads(self.python("-m", "cad_server.engine", "status", "--json").stdout)["workers"]
        self.assertEqual([(Path(worker["script"]).name, worker["builds"]) for worker in workers], [("model.py", 2)],
                         "one warm worker built both, not the script's own process")



class LibraryRootsTest(unittest.TestCase):
    """What counts as the model's own code: a site-packages folder another environment lends this
    one -- a ``.pth`` line or PYTHONPATH, as a scratch venv borrowing the repo's OCP and build123d
    has it -- is library code, as this interpreter's own site-packages is."""

    def test_a_borrowed_site_packages_is_library_code(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="engine-roots-")).resolve()
        self.addCleanup(shutil.rmtree, root, True)
        write(root, {"lent/lib/python3/site-packages/borrowed.py": "", "model/own.py": ""})
        probe = ("import sys; from cad.engine.kernel.trace import first_party_file; "
                 "print(first_party_file(sys.argv[1]), first_party_file(sys.argv[2]))")
        lent = root / "lent" / "lib" / "python3" / "site-packages"
        done = subprocess.run([sys.executable, "-c", probe, str(lent / "borrowed.py"), str(root / "model" / "own.py")],
                              env={**os.environ, "PYTHONPATH": os.pathsep.join([str(SRC), str(lent)])},
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.split(), ["False", "True"])

    def test_a_project_inside_its_own_virtual_environment_is_the_model_s_and_its_edits_rebuild(self) -> None:
        # The worker runs the project's Python, so its prefix is the project's venv: a venv at proj
        # with the project in proj/work (or `python -m venv .`) holds the model's own code. Only the
        # venv's library folders are library code; a script that does lie in one is said.
        from cad.engine.kernel import trace

        root = Path(tempfile.mkdtemp(prefix="engine-venv-project-")).resolve()
        self.addCleanup(shutil.rmtree, root, True)
        prefix, site = root / "proj", root / "proj" / "lib" / "python3" / "site-packages"
        write(root, {"proj/pyvenv.cfg": "include-system-site-packages = false\n", "proj/work/helpers.py": "WIDTH = 3\n",
                     "proj/lib/python3/site-packages/installed.py": "",
                     "proj/lib/python3/site-packages/shipped.py": "import build123d as bd\nfrom cadgen import model\n"
                                                                  "@model\ndef shipped():\n    return bd.Box(1, 1, 1)\n",
                     "proj/work/block.py": """
            import build123d as bd
            from cadgen import model

            import helpers


            @model
            def block():
                return bd.Box(helpers.WIDTH, 2, 1)
        """})

        def forget() -> None:
            for cache in (trace._library_roots, trace._first_party, trace.first_party_file):
                cache.cache_clear()

        forget()
        self.addCleanup(forget)
        script, lines = prefix / "work" / "block.py", []
        with mock.patch.object(sys, "prefix", str(prefix)), mock.patch.object(sys, "exec_prefix", str(prefix)), \
                mock.patch.object(sys, "path", [*sys.path, str(site)]):
            self.assertEqual([trace.first_party_file(str(path)) for path in (script, prefix / "work" / "helpers.py",
                                                                             site / "installed.py")], [True, True, False])
            [cold] = engine_build.build(script, cwd=script.parent, log=lines.append)
            self.assertTrue(cold["ok"], cold.get("error"))
            write(root, {"proj/work/helpers.py": "WIDTH = 5\n"})
            [edited] = engine_build.build(script, cwd=script.parent, log=lines.append)
            self.assertEqual(edited["bodies"], {"block.py::block": "run"})
            self.assertIn("helpers.py: WIDTH changed", edited["cache"]["changed"])
            self.assertEqual(lines, [], "the project's own script is no library's")
            [shipped] = engine_build.build(site / "shipped.py", cwd=site, log=lines.append)
        self.assertTrue(shipped["ok"], shipped.get("error"))
        said = (f"cadgen: shipped.py lies in a library folder, {site}: edits to it and to what it "
                "imports rebuild nothing; keep the project outside the interpreter's library folders")
        self.assertEqual(lines, [said])
        # On Windows the venv's standard library folder (proj\Lib) holds its site-packages too: the
        # deepest folder is named, whichever order the roots come in.
        for roots in ((prefix / "lib", site), (site, prefix / "lib")):
            lines.clear()
            with mock.patch.object(trace, "_library_roots", lambda roots=roots: roots):
                engine_build.build(site / "shipped.py", cwd=site, log=lines.append)
            self.assertEqual(lines, [said], roots)


def setUpModule() -> None:
    # The registry and cache of every engine this module starts are its own, never the developer's
    # (``engine_daemon.isolate``); each test still names its own engine folder.
    from tests.python.support import engine_daemon

    engine_daemon.isolate(unittest.addModuleCleanup)


if __name__ == "__main__":
    unittest.main()
