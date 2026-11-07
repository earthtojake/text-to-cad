"""``cad run --with`` and a script's inline metadata (PEP 723): the environment of a model's own packages
beside the base (``cad_server._internal.extras``) -- what names them, how they are keyed, what uv's refusals
are said as -- and, with the real uv and no network (``UV_OFFLINE``), a tiny local package a model imports,
through ``--with`` and through its header, in an environment made once and used again, and what each
document's record says builds it again."""

from __future__ import annotations

import base64
import contextlib
import dataclasses
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from tests.python.support import engine_daemon
from tests.python.support.paths import add_sources

add_sources()

from cad_server._internal import base, extras  # noqa: E402


class NamingTest(unittest.TestCase):
    def test_with_takes_requirements_repeated_or_comma_separated_as_uv_does(self) -> None:
        self.assertEqual(extras.split("pandas>=2,<3,numpy"), ["pandas>=2,<3", "numpy"], "a version's comma is its own")
        self.assertEqual(extras.split("shapely[vectorized,x],scipy"), ["shapely[vectorized,x]", "scipy"])
        from cad_server.cli import run

        plan = run.parse(["--with", "a,b", "--with=c", "-w", "d", "model.py", "--with", "x"])
        self.assertEqual((plan.with_, plan.kind, plan.target, plan.args),
                         (["a", "b", "c", "d"], "script", "model.py", ["--with", "x"]),
                         "the program's own arguments are its own")
        plan = run.parse(["--", "-c", "print(1)"])
        self.assertEqual((plan.kind, plan.target), ("code", "print(1)"))
        with self.assertRaisesRegex(extras.Refused, "^--with takes a requirement"):
            run.parse(["--with", "", "model.py"])

    def test_a_script_or_a_folder_that_is_not_there_is_refused_before_any_environment(self) -> None:
        # The command line's mistake, exit 2, in one line: no environment is made (the installation is never
        # read) and the program's runner never starts, so there is no traceback.
        from cad_server.cli import run

        with tempfile.TemporaryDirectory() as folder, contextlib.chdir(folder), \
                mock.patch.object(base.Installation, "here", side_effect=AssertionError("an environment was asked")):
            Path("there").mkdir()
            for argv, said in ((["missing.py"], "cad run: no such file: missing.py\n"),
                               (["python", "missing.py", "--flag"], "cad run: no such file: missing.py\n"),
                               (["--directory", "gone", "model.py"], "cad run: no such folder: gone\n"),
                               (["--directory", "there", "missing.py"], "cad run: no such file: missing.py\n")):
                with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()) as err:
                    self.assertEqual((run.main(argv), err.getvalue()), (2, said))

    def test_a_script_s_header_names_its_packages_and_its_python(self) -> None:
        folder = Path(tempfile.mkdtemp(prefix="extras-header-"))
        self.addCleanup(shutil.rmtree, folder, True)
        script = folder / "plate.py"
        script.write_text('# /// script\n# requires-python = ">=3.11"\n# dependencies = [\n#   "pandas>=2",\n'
                          '#   "localpkg",\n# ]\n# ///\nimport pandas\n', encoding="utf-8")
        self.assertEqual(extras.header(script),
                         {"dependencies": ["pandas>=2", "localpkg"], "requires-python": ">=3.11"})
        script.write_text("import build123d\n", encoding="utf-8")
        self.assertEqual(extras.header(script), {}, "no block: the base")
        for text, said in (("# /// script\n# dependencies = 'pandas'\n# ///\n", "a list of requirement strings"),
                           ("# /// script\n# dependencies = [\n# ///\n", "is no TOML"),
                           ("# /// script\n# dependencies = []\n# ///\nimport x\n# /// script\n"
                            "# dependencies = []\n# ///\n", "more than one")):
            with self.subTest(said=said):
                script.write_text(text, encoding="utf-8")
                with self.assertRaisesRegex(extras.Refused, said):
                    extras.header(script)

    def test_requires_python_reads_as_pep_440_does(self) -> None:
        for spec, admitted in ((">=3.11,<3.15", True), (">=3.15", False), ("~=3.14", True), ("~=3.13.1", False),
                               ("==3.14.*", True), ("!=3.14.*", False), ("==3.14", False), ("junk", None),
                               (">=3.11.0rc1", True), ("<3.14.0rc1", False), (">=3.15.0a1", False),
                               ("~=3.14.0rc1", True), ("<=3.14.6.dev1", False), ("==3.14.0rc1.*", None)):
            with self.subTest(spec=spec):
                self.assertEqual(extras.admits(spec, "3.14.6"), admitted)

    def test_a_key_is_the_requirements_normalized_and_sorted(self) -> None:
        self.assertEqual(extras.normalized('Pandas_Data.Frame[B, a]>= 2.0 , <3 ; python_version >= "3.8"', "/w"),
                         'pandas-data-frame[a,b]>=2.0,<3; python_version >= "3.8"')
        with self.assertRaisesRegex(extras.Refused, "^--index-url=https://x is no requirement"):
            extras.normalized("--index-url=https://x", "/w")
        with mock.patch.object(extras, "WINDOWS", False):
            self.assertEqual([extras.normalized(item, "/w/project") for item in ("./pkg", "../x.whl", "/abs/y.whl")],
                             ["/w/project/pkg", "/w/x.whl", "/abs/y.whl"])
        with mock.patch.object(extras, "WINDOWS", True):
            self.assertEqual([extras.normalized(item, "C:\\w\\project") for item in
                              (".\\pkg", "..\\x.whl", "D:\\abs\\y.whl", "\\\\server\\share\\z.whl")],
                             ["C:\\w\\project\\pkg", "C:\\w\\x.whl", "D:\\abs\\y.whl", "\\\\server\\share\\z.whl"])
        # A local direct reference, or a file: URL, absolute -- the same key from any folder; a URL as written.
        with mock.patch.object(extras, "WINDOWS", False):
            self.assertEqual([extras.normalized(item, "/w/project") for item in
                              ("Gears @ ./vendor/gears", 'gears @ file:./vendor/gears ; python_version > "3"',
                               "file:../x.whl", "gears @ file:///abs/my%20dir/gears", "https://e.com/a-1.0.whl",
                               "gears @ https://e.com/gears.zip")],
                             ["gears @ /w/project/vendor/gears", 'gears @ /w/project/vendor/gears ; python_version > "3"',
                              "/w/x.whl", "gears @ /abs/my dir/gears", "https://e.com/a-1.0.whl",
                              "gears @ https://e.com/gears.zip"])
            self.assertEqual([extras.local_package(item) for item in
                              ("/w/x.whl", "gears @ /abs/gears", "gears @ https://e.com/gears.zip", "pandas>=2")],
                             ["/w/x.whl", "/abs/gears", None, None])
        with mock.patch.object(extras, "WINDOWS", True):
            self.assertEqual([extras.normalized(item, "C:\\w\\project") for item in
                              ("gears @ .\\vendor\\gears", "gears @ file:///D:/my%20dir/gears")],
                             ["gears @ C:\\w\\project\\vendor\\gears", "gears @ D:\\my dir\\gears"])
        installation = base.Installation.here()
        same = extras.key(installation, ["numpy", "pandas>=2"])
        self.assertEqual(extras.key(installation, ["pandas>=2", "numpy", "numpy"]), same, "each once, in any order")
        self.assertNotEqual(extras.key(installation, ["pandas>=2"]), same)
        self.assertEqual(extras.where(installation, ["numpy"]).parent.name, base.BASE, "beside the base")

    def test_a_local_package_is_keyed_by_what_it_is_now_passing_over_what_no_build_reads(self) -> None:
        folder = Path(tempfile.mkdtemp(prefix="extras-local-")).resolve()
        self.addCleanup(shutil.rmtree, folder, True)
        package = folder / "gears"
        (package / "gears").mkdir(parents=True)
        source = package / "gears" / "__init__.py"
        source.write_text("TEETH = 1\n", encoding="utf-8")
        installation, requirements = base.Installation.here(), [str(package), "pandas>=2"]
        before, key = extras.fingerprints(requirements), extras.key(installation, requirements)
        self.assertEqual(list(before), [str(package)], "only the local one")
        for skipped in ("__pycache__/x.pyc", ".git/index", "build/lib/x.py", "gears.egg-info/PKG-INFO"):
            (package / skipped).parent.mkdir(parents=True, exist_ok=True)
            (package / skipped).write_text("x", encoding="utf-8")
        self.assertEqual(extras.key(installation, requirements), key, "what no build reads changes nothing")
        source.write_text("TEETH = 22\n", encoding="utf-8")
        self.assertNotEqual(extras.key(installation, requirements), key, "an edit is another environment")
        wheel = _wheel(folder)
        was = extras.fingerprint(str(wheel))
        os.utime(wheel, ns=(wheel.stat().st_atime_ns, wheel.stat().st_mtime_ns + 10**9))
        self.assertNotEqual(extras.fingerprint(str(wheel)), was, "a wheel built again at its name")
        self.assertEqual(extras.fingerprint(str(folder / "gone")), "missing")

    def test_the_engine_hands_uv_no_option_of_its_own_as_a_requirement(self) -> None:
        from cad_server.engine.daemon import Daemon

        with self.assertRaisesRegex(extras.Refused, "^--index-url=https://x is no requirement"):
            extras.making(["pandas", "--index-url=https://x"])
        engine = Daemon(cap=1)
        self.addCleanup(engine.shutdown)
        sent: list = []
        engine.base({"op": "base", "key": "k", "with": ["--index-url=https://x"]}, sent.append)
        self.assertEqual(sent, [{"failed": "--index-url=https://x is no requirement: name a package, a pin, extras, "
                                           "or a local path or wheel", "base": True}])

    def test_uv_s_refusals_are_one_line_with_its_reason_or_the_package_its_cache_lacks(self) -> None:
        recipe = extras.recipe(base.Installation.here(), ["build123d<0.1"])
        conflict = ("error: No solution found when resolving dependencies\n"
                    "  cause: Because only cad[build123d]==0.10.0 is available and cad[build123d]==0.10.0 depends on "
                    "build123d>=0.13.0,<0.14, we can conclude that all versions of cad[build123d] depend on "
                    "build123d>=0.13.0,<0.14.\n"
                    "         And because you require build123d<0.1 and cad[build123d], we can conclude that your "
                    "requirements are unsatisfiable.\n")
        said = base.failure(["uv", "pip", "install"], conflict, recipe)
        self.assertRegex(said, r"^build123d<0\.1 cannot be resolved beside cad\[build123d\] \S+: Because only "
                               r"cad\[build123d\]==0\.10\.0 is available .+ your requirements are unsatisfiable\.$")
        uncached = ("error: No solution found when resolving dependencies\n"
                    "  cause: Because notapackage was not found in the cache and you require notapackage, we can "
                    "conclude that your requirements are unsatisfiable.\n\n"
                    "hint: Packages were unavailable because the network was disabled.\n")
        self.assertRegex(base.failure(["uv", "pip", "install"], uncached, recipe),
                         r"^the environment of the model's packages needs the network once, for notapackage, which "
                         r"uv's cache does not hold: ")
        self.assertNotIn("\n", said)

    def test_making_one_removes_releases_older_than_the_one_before_but_the_bases_and_one_a_process_runs_from(self) -> None:
        folder = Path(tempfile.mkdtemp(prefix="extras-collect-"))
        self.addCleanup(shutil.rmtree, folder, True)

        def made(name: str, release: str, given: list[str] | None, local: dict | None = None) -> Path:
            env = folder / name
            base.interpreter(env).parent.mkdir(parents=True)
            base.interpreter(env).write_bytes(b"")
            marker = {"schema": base.SCHEMA, "key": name, "inputs": {"release": release}}
            if given is not None:
                marker.update({"with": given, "local": local or {},
                               "spec": extras.Spec(requirements=tuple(given)).keyed()})
            (env / base.MARKER).write_text(json.dumps(marker), encoding="utf-8")
            return env

        old = made("old", "0.8.0", ["pandas"])
        superseded = made("edited", "0.10.0", ["/w/gears"], {"/w/gears": "before"})
        now = made("now", "0.10.0", ["/w/gears"], {"/w/gears": "after"})
        for name, release, given in (("held", "0.8.0", ["scipy"]), ("same", "0.10.0", ["pandas"]),
                                     ("before", "0.9.0", ["pandas"]), ("base", "0.8.0", None)):
            made(name, release, given)
        with mock.patch("cad_server._internal.switch.last", return_value=None):
            keep = extras.kept(folder, "0.10.0")
        self.assertEqual(keep, {"0.10.0", "0.9.0"}, "the current release and the one before it: the way back")
        with mock.patch("cad_server._internal.switch.last", return_value={"from": "0.8.0", "to": "0.10.0", "ok": True}):
            self.assertEqual(extras.kept(folder, "0.10.0"), {"0.10.0", "0.8.0"}, "the release the update came from")
        with mock.patch("cad_server._internal.releases.running", side_effect=lambda env: Path(env).name == "held"):
            self.assertEqual(sorted(extras._collect(folder, keep, made=now, spec=extras.Spec(requirements=("/w/gears",)),
                                                    inputs={"release": "0.10.0"})), sorted([str(superseded), str(old)]))
        self.assertEqual(sorted(path.name for path in folder.iterdir()), ["base", "before", "held", "now", "same"],
                         "the release before's stay; a base is its release's to remove; one a process runs from "
                         "goes at a later making; the environments of other packages stay")
        self.assertEqual(extras._changed(folder, {"release": "0.10.0"}, extras.Spec(requirements=("/w/gears",)),
                                         {"/w/gears": "later"}),
                         ["/w/gears"], "the line that makes it again names the local package edited")


class ChoosingTest(unittest.TestCase):
    """What a ``cad run`` line's environment is made of (``run.prepare``, ``extras.integrations``): cad's
    integrations from the program's imports, a header that names ``cad[...]`` deciding them, a project's packages
    where no header is, and cad's pin. Nothing is made: no uv."""

    RELEASE = "0.10.0"

    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="extras-choose-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, True)
        here = os.getcwd()
        self.addCleanup(os.chdir, here)
        os.chdir(self.folder)

    def write(self, name: str, text: str) -> Path:
        path = self.folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text), encoding="utf-8")
        return path

    def spec(self, *argv: str) -> extras.Spec:
        from cad_server.cli import run

        found = run.prepare(run.parse(list(argv)), self.RELEASE).spec
        assert isinstance(found, extras.Spec)
        return found

    def test_the_scan_finds_an_integration_through_local_imports_and_cad_s_names(self) -> None:
        from cad_server._internal import scan

        self.write("lib/__init__.py", "from .shapes import plate\n")
        self.write("lib/shapes.py", "def plate():\n    import build123d as bd  # inside a body, as a model's\n"
                                    "    return bd.Box(1, 1, 1)\n")
        self.write("boards.py", "from cad import kicad_pcb as board\n\nwith board.edit('b.kicad_pcb') as b:\n    pass\n")
        self.write("model.py", "import numpy\nfrom lib import plate\nimport boards\n")
        self.write("plain.py", "import json\nfrom cad import model\n")
        self.write("attribute.py", "import cad.kicad_pcb\n\nwith cad.kicad_pcb.edit('x.kicad_pcb') as b:\n    pass\n")
        self.write("schematic.py", "from cad.kicad_sch import edit\n\nwith edit('d.kicad_sch') as s:\n    pass\n")
        self.write("dynamic.py", "import importlib\nimportlib.import_module('build' + '123d')\n")
        self.assertEqual(scan.scan(script=self.folder / "model.py"), {"build123d", "kicad"})
        self.assertEqual(scan.scan(script=self.folder / "plain.py"), set(), "the core alone")
        self.assertEqual(scan.scan(script=self.folder / "attribute.py"), {"kicad"})
        self.assertEqual(scan.scan(script=self.folder / "schematic.py"), {"kicad"}, "a schematic's edit, as a board's")
        self.assertEqual(scan.scan(script=self.folder / "dynamic.py"), set(), "an import by name is not seen")
        self.assertEqual(scan.scan(module="lib", cwd=self.folder), {"build123d"})
        self.assertEqual(scan.scan(code="import OCP.TopoDS", cwd=self.folder), {"build123d"})
        # cad's own namespace of an integration (the registry's) is that integration, however it is imported.
        for code, found in (("from cad.build123d import paint", {"build123d"}), ("from cad import build123d", {"build123d"}),
                            ("import cad.kicad._session", {"kicad"}), ("from cadgen.build123d import memo", {"build123d"}),
                            ("from cad import step, model", set())):
            with self.subTest(code=code):
                self.assertEqual(scan.scan(code=code, cwd=self.folder), found)
        self.assertEqual(self.spec("model.py").integrations, ("build123d", "kicad"))
        self.assertTrue(self.spec("--with", "build123d", "plain.py").integrations == ("build123d",),
                        "a requirement that is an integration's distribution is that integration")

    def test_a_name_of_cad_s_needs_what_the_registry_and_the_alias_table_say(self) -> None:
        # A model that reads a STEP and never imports build123d itself still needs it (the reader's integration,
        # the registry's), however the read is spelled: 0.11's, a module's import of it, and 0.10's alias.
        from cad_server._internal import scan

        for code, found in (
                ("from cad import model, step\n@model\ndef h():\n    return step.read('p.step')\n", {"build123d"}),
                ("from cad import model, read_step\n@model\ndef h():\n    return read_step('p.step')\n", {"build123d"}),
                ("import cad.step\ncad.step.read('p.step')\n", {"build123d"}),
                ("from cad.step import read\n", {"build123d"}),
                ("import cad as c\nc.read_xbf('p.xbf')\n", {"build123d"}),
                ("from cad import stl\nstl.read('p.stl')\n", {"build123d"}),
                ("from cad import memo\n", {"build123d"}),
                ("from cad.ap242 import posed\n", {"build123d"}),
                # A manufacturing check: exact geometry is measured by build123d, a mesh by trimesh.
                ("from cad import step\nstep.dfm('p.step')\n", {"build123d"}),
                ("from cad import stl\nstl.dfm('p.stl')\n", {"trimesh"}),
                # The engine runs a type's export, snapshot and inspect: the program needs none of its own.
                ("from cad import step\nstep.export('p.step', 'p.glb')\n", set()),
                ("from cad import export\nexport('p.xbf', 'p.step')\n", set()),
                ("from cad import kicad_pcb\nkicad_pcb.read('b.kicad_pcb')\n", set())):
            with self.subTest(code=code):
                self.assertEqual(scan.scan(code=code, cwd=self.folder), found)
        self.write("read.py", "from pathlib import Path\nfrom cad import model, step\n\n@model\ndef holder():\n"
                              "    return step.read(Path(__file__).parent / 'part.step')\n")
        self.assertTrue(self.spec("read.py").default(), "a STEP read runs on the base: cad[build123d]")

    def test_a_command_an_integration_declares_adds_it_and_any_other_adds_nothing(self) -> None:
        from cad_server.cli import run

        self.assertEqual(self.spec("kicad-cli", "version").integrations, ("kicad",), "kicad-cli is the kicad integration's")
        self.assertEqual(self.spec("kicad-cli.exe", "version").integrations, ("kicad",), "as Windows spells it")
        self.assertEqual(self.spec("--with", "cad[kicad]", "kicad-cli", "version").integrations, ("kicad",),
                         "an explicit --with still works")
        self.assertEqual(self.spec("--with", "cad[trimesh]", "kicad-cli").integrations, ("kicad", "trimesh"))
        self.assertEqual(self.spec("--with", "cad[kicad]", "ruff", "check").integrations, ("kicad",))
        for argv in (("ruff", "check"), ("kicad", "version"), ("./kicad-cli", "version")):
            with self.subTest(argv=argv):
                self.assertEqual(self.spec(*argv).integrations, (), "a command no integration declares adds nothing")
        # The declared one runs through the library's module for it, in the environment's Python, never a file
        # on PATH; another is the environment's own file, or none.
        python = str(self.write("env/bin/python", ""))
        self.assertEqual(run._command(run.parse(["kicad-cli", "pcb", "render", "b.kicad_pcb"]), python),
                         [python, "-P", "-m", "cad.kicad._command", "kicad-cli", "pcb", "render", "b.kicad_pcb"])
        self.assertIsNone(run._command(run.parse(["ruff", "check"]), python))
        ruff = self.write("env/bin/ruff", "")
        self.assertEqual(run._command(run.parse(["ruff", "check"]), python), [str(ruff), "check"])

    def test_a_header_that_names_cad_decides_the_integrations_outright(self) -> None:
        self.write("forced.py", """\
            # /// script
            # dependencies = ["cad[kicad]", "pandas"]
            # ///
            import build123d
        """)
        self.write("core.py", """\
            # /// script
            # dependencies = ["cad"]
            # ///
            import build123d
        """)
        self.assertEqual((self.spec("forced.py").integrations, self.spec("forced.py").requirements),
                         (("kicad",), ("pandas",)), "the header's set, no scan; cad is pinned, never a requirement")
        self.assertEqual(self.spec("core.py").integrations, (), "a bare cad: the core alone")
        self.assertEqual(self.spec("--with", "cad[build123d]", "core.py").integrations, ("build123d",),
                         "--with adds on top")
        self.assertTrue(self.spec(str(self.write("m.py", "import build123d\n"))).default(), "the base")

    def test_cad_pinned_to_the_device_s_release_is_kept_and_another_release_is_refused(self) -> None:
        for pin in ("cad[build123d]", f"cad[build123d]=={self.RELEASE}"):
            with self.subTest(pin=pin):
                self.write("pinned.py", f'# /// script\n# dependencies = ["{pin}"]\n# ///\n')
                self.assertEqual(self.spec("pinned.py").integrations, ("build123d",), "the device's pin either way")
        for pin in ("cad[build123d]==0.9.0", "cad>=1", "cad @ https://example.com/cad.whl"):
            with self.subTest(pin=pin):
                self.write("pinned.py", f'# /// script\n# dependencies = ["{pin}"]\n# ///\n')
                with self.assertRaisesRegex(extras.Refused, rf"^pinned\.py's header pins cad to .+, and this device "
                                                            rf"runs cad {re.escape(self.RELEASE)}: drop the pin"):
                    self.spec("pinned.py")
        self.write("plain.py", "import build123d\n")
        with self.assertRaisesRegex(extras.Refused, r"^--with cad==0\.9\.0 pins cad to ==0\.9\.0"):
            self.spec("--with", "cad==0.9.0", "plain.py")

    def test_a_project_is_read_where_no_header_is_and_a_header_wins(self) -> None:
        self.write("pyproject.toml", """\
            [project]
            name = "gearbox"
            version = "0.1"
            dependencies = ["pandas", "cad[kicad]"]

            [build-system]
            requires = ["setuptools"]
            build-backend = "setuptools.build_meta"
        """)
        self.write("src/model.py", "import build123d\n")
        self.write("src/headed.py", '# /// script\n# dependencies = ["numpy"]\n# ///\nimport build123d\n')
        spec = self.spec("--with", "scipy", "src/model.py")
        self.assertEqual((spec.integrations, spec.editable, spec.requirements),
                         (("build123d", "kicad"), (str(self.folder),), ("scipy",)),
                         "the project installed editable, its cad's integrations with the scan's; --with on top")
        spec = self.spec("src/headed.py")
        self.assertEqual((spec.integrations, spec.editable, spec.requirements), (("build123d",), (), ("numpy",)),
                         "a script with a header runs in its own environment: the project is not read")
        self.assertEqual(self.spec("--no-project", "src/model.py").editable, ())
        self.write("pyproject.toml", '[project]\nname = "loose"\nversion = "0.1"\ndependencies = ["cad==0.9.0"]\n')
        with self.assertRaisesRegex(extras.Refused, rf"pyproject\.toml pins cad to ==0\.9\.0, and this device runs "
                                                    rf"cad {re.escape(self.RELEASE)}"):
            self.spec("src/model.py")
        self.write("pyproject.toml", '[project]\nname = "loose"\nversion = "0.1"\ndependencies = ["pandas"]\n')
        spec = self.spec("src/model.py")
        self.assertEqual((spec.editable, spec.files), ((), (str(self.folder / "pyproject.toml"),)),
                         "an unpackaged project: its dependencies alone")

    def test_uv_s_options_are_handed_to_uv_as_given_and_only_the_making_reads_some(self) -> None:
        self.write("m.py", "import build123d\n")
        spec = self.spec("--index-url", "https://example.com/simple", "-f", "wheels", "--offline", "--resolution=lowest",
                         "-p", "3.13", "--managed-python", "m.py")
        self.assertEqual(spec.options, ("--index-url=https://example.com/simple",
                                        f"--find-links={self.folder / 'wheels'}", "--resolution=lowest"))
        self.assertEqual((spec.transient, spec.python, spec.python_options), (("--offline",), "3.13",
                                                                              ("--managed-python",)))
        installation = base.Installation.here()
        self.assertEqual(extras.key(installation, spec), extras.key(installation, dataclasses.replace(spec, transient=())),
                         "what only the making reads keys nothing")
        self.assertEqual(extras.Spec.from_dict(spec.as_dict()), spec, "as the door carries it")
        with self.assertRaisesRegex(extras.Refused, "is no requirement"):
            extras.Spec.from_dict({**spec.as_dict(), "requirements": ["--index-url=https://x"]})

    def test_uv_s_settings_in_the_caller_s_environment_reach_the_making_and_key_it(self) -> None:
        self.write("m.py", "import build123d\n")
        extra = "https://extra.example.com/simple"
        with mock.patch.dict(os.environ, {"UV_EXTRA_INDEX_URL": extra, "UV_CACHE_DIR": str(self.folder / "c")}):
            spec = self.spec("m.py")
        self.assertIn(f"UV_EXTRA_INDEX_URL={extra}", spec.environment)
        self.assertFalse(any(item.startswith("UV_CACHE_DIR=") for item in spec.environment), "the engine's own")
        self.assertFalse(spec.default(), "another index: not the base")
        installation = base.Installation.here()
        without = dataclasses.replace(spec, environment=tuple(item for item in spec.environment
                                                              if not item.startswith("UV_EXTRA_INDEX_URL=")))
        self.assertNotEqual(extras.key(installation, spec), extras.key(installation, without))
        asked: list = []

        def uv(step, folder, settings=None):
            asked.append((step[1], str(folder), base.uv_environment(settings)))
            return subprocess.CompletedProcess(step, 1, "", "error: stop here")

        with mock.patch.object(base, "_uv", side_effect=uv), mock.patch.object(base, "find_uv", return_value="uv"), \
                mock.patch.dict(os.environ, {"UV_EXTRA_INDEX_URL": "https://the-engine-s-own.example.com"}), \
                self.assertRaises(extras.Refused):
            extras.ensure(installation, spec, told=lambda _line: None)
        step, folder, environment = asked[0]
        self.assertEqual((step, folder, environment["UV_EXTRA_INDEX_URL"]), ("venv", str(self.folder), extra),
                         "uv runs in the run's folder, with the caller's settings, never the engine's")

    def test_a_project_s_lock_and_uv_configuration_are_read_and_its_cad_is_the_device_s(self) -> None:
        self.write("pyproject.toml", '[project]\nname = "p"\nversion = "0.1"\ndependencies = ["cad"]\n\n'
                                     '[tool.uv]\nindex-url = "https://private.example.com/simple"\n')
        self.write("m.py", "import build123d\n")
        with self.assertRaisesRegex(extras.Refused, r"^--locked: .+ has no uv\.lock to read$"):
            self.spec("--locked", "m.py")
        spec = self.spec("m.py")
        self.assertEqual((spec.config, spec.lock, spec.folder), ((str(self.folder / "pyproject.toml"),), None,
                                                                  str(self.folder)))
        lock = self.write("uv.lock", 'version = 1\nrequires-python = ">=3.14"\n\n[[package]]\nname = "cad"\n'
                                     'version = "0.10.0"\nsource = { registry = "https://pypi.org/simple" }\n')
        spec = self.spec("--frozen", "--group", "dev", "m.py")
        self.assertEqual((spec.lock, spec.lock_options, spec.editable, spec.files),
                         (str(lock), ("--frozen", "--group=dev"), (), ()), "the locked set, in place of a resolution")
        installation = base.Installation.here()
        before = extras.key(installation, spec)
        lock.write_text(lock.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        self.assertNotEqual(extras.key(installation, spec), before, "the key covers the lock's content")
        lock.write_text(lock.read_text(encoding="utf-8").replace('"0.10.0"', '"0.9.0"'), encoding="utf-8")
        with self.assertRaisesRegex(extras.Refused, r"uv\.lock pins cad to ==0\.9\.0, and this device runs cad 0\.10\.0"):
            self.spec("m.py")

    def test_cad_requirement_prints_the_device_s_exact_requirement(self) -> None:
        from cad_server.cli import requirement

        installation = base.Installation.here()
        self.assertEqual(requirement.requirement(["kicad,build123d"])["requirement"],
                         " ".join(installation.requirement(("build123d", "kicad"))))
        release = dataclasses.replace(installation, source=None, release="0.10.0")
        with mock.patch.object(base.Installation, "here", return_value=release):
            self.assertEqual(requirement.requirement(["build123d"]),
                             {"requirement": "cad[build123d]==0.10.0", "indexes": [], "findLinks": []})
            self.assertEqual(requirement.requirement([])["requirement"], "cad==0.10.0")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(requirement.main(["build123d"]), 0)
            self.assertEqual(out.getvalue(), "cad[build123d]==0.10.0\n")
        with self.assertRaisesRegex(ValueError, "nope: no integration of cad's; it has build123d"):
            requirement.requirement(["nope"])


def _wheel(folder: Path, width: int = 42, requires: tuple[str, ...] = (), version: str = "0.1") -> Path:
    """A tiny pure-Python package as a wheel uv installs with no build and no network: ``localpkg`` at
    ``version`` (its ``VERSION``), its ``WIDTH`` the one given, depending on ``requires``."""
    path = folder / f"localpkg-{version}-py3-none-any.whl"
    info = f"localpkg-{version}.dist-info"
    metadata = f"Metadata-Version: 2.1\nName: localpkg\nVersion: {version}\n" + "".join(f"Requires-Dist: {item}\n"
                                                                                       for item in requires)
    files = {"localpkg/__init__.py": f"WIDTH = {width}\nVERSION = {version!r}\n".encode(),
             f"{info}/METADATA": metadata.encode(),
             f"{info}/WHEEL": b"Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n"}

    def digest(data: bytes) -> str:
        return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()

    record = "".join(f"{name},{digest(data)},{len(data)}\n" for name, data in files.items())
    with zipfile.ZipFile(path, "w") as wheel:
        for name, data in files.items():
            wheel.writestr(name, data)
        wheel.writestr(f"{info}/RECORD", record + f"{info}/RECORD,,\n")
    return path


PLATE = """{header}import localpkg
from cad import model


@model
def plate():
    import build123d as bd

    return bd.Box(localpkg.WIDTH, 10, 2)


if __name__ == "__main__":
    plate()
"""


class RunWithTest(unittest.TestCase):
    """The real uv, offline: nothing here reaches the network."""

    @classmethod
    def setUpClass(cls) -> None:
        engine_daemon.isolate(cls.addClassCleanup)
        cls.project = Path(tempfile.mkdtemp(prefix="run-with-")).resolve()
        cls.addClassCleanup(shutil.rmtree, cls.project, True)
        cls.wheel = _wheel(cls.project)
        cls.env = engine_daemon.watched({**os.environ, "UV_OFFLINE": "1", "CAD_ENGINE_MESH": "inline"},
                                        cls.addClassCleanup)

    def run_(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
        return engine_daemon.run([sys.executable, "-m", "cad_server.cli", "run", *args], env=self.env,
                                 cwd=cwd or self.project)

    def test_a_project_s_lock_is_installed_exactly_and_its_uv_configuration_is_read(self) -> None:
        # Its packages come from a folder of wheels its pyproject.toml's [tool.uv] names, which no index serves.
        locked, unlocked = self.project / "locked", self.project / "unlocked"
        for folder in (locked, unlocked):
            (folder / "wheels").mkdir(parents=True)
            _wheel(folder / "wheels", version="0.1")
            (folder / "pyproject.toml").write_text(
                '[project]\nname = "gearbox"\nversion = "0.1"\nrequires-python = ">=3.14"\n'
                'dependencies = ["localpkg"]\n\n[tool.uv]\nfind-links = ["wheels"]\n', encoding="utf-8")
        made = subprocess.run([base.find_uv(), "lock", "--offline"], cwd=locked, capture_output=True, text=True,
                              env=self.env)
        self.assertEqual(made.returncode, 0, made.stderr)
        for folder in (locked, unlocked):
            _wheel(folder / "wheels", version="0.2")  # newer than the lock's
        said = "import localpkg; print(localpkg.VERSION)"
        done = self.run_("-c", said, cwd=locked)
        self.assertEqual((done.returncode, done.stdout.strip()), (0, "0.1"), done.stderr)
        self.assertIn(f"the locked set of {locked / 'uv.lock'}", done.stderr)
        done = self.run_("-c", said, cwd=unlocked)
        self.assertEqual((done.returncode, done.stdout.strip()), (0, "0.2"),
                         "no lock: a resolution, through the project's own [tool.uv] find-links\n" + done.stderr)
        # A lock out of date with its project: --locked refuses it, in uv's words, and nothing runs.
        project = locked / "pyproject.toml"
        project.write_text(project.read_text(encoding="utf-8").replace('["localpkg"]', '["localpkg>=0.2"]'),
                           encoding="utf-8")
        done = self.run_("--locked", "-c", "print('ran')", cwd=locked)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertNotIn("ran", done.stdout)
        self.assertRegex(done.stderr.strip().splitlines()[-1],
                         r"^cad run: uv could not export .+uv\.lock: The lockfile at `uv\.lock` needs to be updated, "
                         r"but `--locked` was provided")

    def rebuild(self, done: subprocess.CompletedProcess) -> str | None:
        from cad.engine import records

        ident = re.search(r"id: ([0-9a-f-]{36})", done.stdout).group(1)
        return records.command(records.current(), records.current().get(ident))

    def test_a_local_package_through_with_and_through_the_header_in_one_environment_made_once(self) -> None:
        from cad.engine.records import rerun

        (self.project / "plate.py").write_text(PLATE.format(header=""), encoding="utf-8")
        first = self.run_("--with", f"./{self.wheel.name}", "plate.py")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertIn("cad run: making the environment of the model's packages, once: ", first.stderr)
        self.assertRegex(first.stdout, r"bounds 42\D+10\D+2 mm", "the model imported its package")
        self.assertNotIn("cad here is", first.stderr, "of one release with the server: no update notice")
        self.assertEqual(self.rebuild(first), rerun(self.project / "plate.py", given=[str(self.wheel)]),
                         "built with --with: cad run --with it again")
        again = self.run_("--with", str(self.wheel), "plate.py")
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertNotIn("making", again.stderr, "made once, used again")
        self.assertIn("took plate.py::plate warm", again.stdout, "a warm worker of that environment's Python")
        # Its header names the same package: the same environment, and `cad run` alone builds it again.
        header = f"# /// script\n# dependencies = [{str(self.wheel)!r}]\n# ///\n".replace("'", '"')
        (self.project / "headed.py").write_text(PLATE.format(header=header), encoding="utf-8")
        headed = self.run_("headed.py")
        self.assertEqual(headed.returncode, 0, headed.stdout + headed.stderr)
        self.assertNotIn("making", headed.stderr)
        self.assertEqual(self.rebuild(headed), rerun(self.project / "headed.py"))
        made = [path for path in (Path(os.environ["CAD_CACHE_DIR"]) / base.BASE).iterdir()
                if (base.complete(path) or {}).get("with") == [str(self.wheel)]]
        self.assertEqual(len(made), 1, "one environment")

    def test_a_program_s_header_names_the_packages_a_model_it_calls_is_built_again_with(self) -> None:
        # The header is the check script's; the model is model_part.py's, whose own script names no package.
        from cad.engine import records
        from cad.engine.ids import model_id

        (self.project / "model_part.py").write_text(PLATE.format(header=""), encoding="utf-8")
        (self.project / "check.py").write_text(f"# /// script\n# dependencies = ['{self.wheel}']\n# ///\n"
                                               "import model_part\n\nmodel_part.plate()\n", encoding="utf-8")
        done = self.run_("check.py")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        held = records.current().get(model_id(self.project / "model_part.py", "plate"))
        self.assertEqual(records.command(records.current(), held),
                         records.rerun(self.project / "model_part.py", given=[str(self.wheel)]),
                         "cad run --with the program's packages and the model's own script")

    def test_an_edited_local_package_makes_its_environment_again_and_says_so(self) -> None:
        folder = self.project / "edited"
        folder.mkdir()
        wheel = _wheel(folder)
        said = "import localpkg; print(localpkg.WIDTH)"
        first = self.run_("--with", str(wheel), "-c", said)
        self.assertEqual((first.returncode, first.stdout.strip()), (0, "42"), first.stderr)
        _wheel(folder, width=142)  # built again at its name, as a build tool does
        stamp = wheel.stat()
        os.utime(wheel, ns=(stamp.st_atime_ns, stamp.st_mtime_ns + 10**9))
        again = self.run_("--with", str(wheel), "-c", said)
        self.assertEqual((again.returncode, again.stdout.strip()), (0, "142"), again.stderr)
        self.assertIn(f"cad run: making the environment of the model's packages again, as {wheel} changed: ",
                      again.stderr)
        warm = self.run_("--with", str(wheel), "-c", said)
        self.assertEqual((warm.returncode, warm.stdout.strip()), (0, "142"), warm.stderr)
        self.assertNotIn("making", warm.stderr, "unchanged: the environment used again")

    def test_an_integration_a_package_pulls_in_is_added_and_resolved_again_with_cad_s_pins(self) -> None:
        folder = self.project / "pulls"
        folder.mkdir()
        wheel = _wheel(folder, requires=("build123d",))
        # Nothing the scan sees names build123d: the package's own dependency pulls it in.
        done = self.run_("--with", str(wheel), "-c", "import importlib, localpkg; "
                                                     "print(importlib.import_module('build' + '123d').__name__)")
        self.assertEqual((done.returncode, done.stdout.strip()), (0, "build123d"), done.stderr)
        self.assertRegex(done.stderr, r"cad run: build123d came in through another package: resolving again with "
                                      r"cad\[build123d\] \S+, so cad's pins decide it")
        made = [base.complete(path) for path in (Path(os.environ["CAD_CACHE_DIR"]) / base.BASE).iterdir()
                if (base.complete(path) or {}).get("with") == [str(wheel)]]
        self.assertEqual([marker["integrations"] for marker in made], [["build123d"]])

    def test_an_import_the_scan_cannot_see_ends_in_one_line_naming_the_extra(self) -> None:
        done = self.run_("-c", "import importlib; importlib.import_module('build' + '123d')")
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertEqual(done.stderr.strip().splitlines()[-1],
                         "build123d comes with cad's build123d integration: add `cad[build123d]` to the script's header")

    def test_what_uv_cannot_do_is_said_in_one_line(self) -> None:
        (self.project / "plain.py").write_text("print('ran')\n", encoding="utf-8")
        for requirement, said in (("build123d<0.1", r"cad run: build123d<0\.1 cannot be resolved beside "
                                                    r"cad\[build123d\] \S+: Because .+unsatisfiable\.$"),
                                  ("notapackage-xyz", r"cad run: the environment of the model's packages needs the "
                                                      r"network once, for notapackage-xyz, which uv's cache does "
                                                      r"not hold: ")):
            with self.subTest(requirement=requirement):
                done = self.run_("--with", requirement, "plain.py")
                self.assertEqual(done.returncode, 1, done.stdout)
                lines = [line for line in done.stderr.splitlines() if line.startswith("cad run: ")]
                self.assertRegex(lines[-1], said)
                self.assertNotIn("Traceback", done.stderr)
                self.assertNotIn("ran", done.stdout)
        (self.project / "newer.py").write_text('# /// script\n# requires-python = ">=3.99"\n# ///\nprint("ran")\n',
                                               encoding="utf-8")
        done = self.run_("newer.py")
        self.assertEqual((done.returncode, done.stderr.strip()),
                         (1, f"cad run: newer.py requires Python >=3.99, and the server's is "
                             f"{'.'.join(map(str, sys.version_info[:3]))}"))


if __name__ == "__main__":
    unittest.main()
