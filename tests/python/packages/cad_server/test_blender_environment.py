"""An integration whose tool is built for one Python alone: blender's bpy, CPython 3.13
(``cad_server._internal.extras.on``, ``cad_server.cli.run``). What a program's imports choose, the Python its
environment is made on and how uv is asked for it, what is refused in one line before anything is made (a
``--python`` or a ``requires-python`` that leaves that line out, a platform bpy has no build for), its private
settings folders, and ``cad doctor``'s row. A ``--python`` that admits that line is narrowed to it: one
environment for the line, however it is asked for. Its environment is one of cad's like any other: cad pinned in it,
keyed by the release. Nothing is made here: no uv. The real environment, with the real bpy, is the blender
job's (``tests/python/packages/blender``)."""

from __future__ import annotations

import dataclasses
import json
import os
import shutil
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support import engine_daemon
from tests.python.support.paths import add_sources

add_sources()

from cad.registry import INTEGRATIONS  # noqa: E402
from cad_server._internal import base, extras  # noqa: E402

BLENDER = INTEGRATIONS["blender"]
RELEASE = "0.11.3"
# An engine on the Python the server's installations run on, and one on bpy's own line.
SERVER, OWN = "3.14.6", "3.13.5"
BUILT = "macOS arm64, Linux x86-64, Windows x86-64 and Windows arm64"


class ChoosingTest(unittest.TestCase):
    def setUp(self) -> None:
        engine_daemon.isolate(self.addCleanup)
        self.folder = Path(tempfile.mkdtemp(prefix="blender-choose-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, True)
        here = os.getcwd()
        self.addCleanup(os.chdir, here)
        os.chdir(self.folder)

    def write(self, name: str, text: str) -> Path:
        path = self.folder / name
        path.write_text(textwrap.dedent(text), encoding="utf-8")
        return path

    def prepared(self, *argv: str, engine: str = SERVER):
        from cad_server.cli import run

        return run.prepare(run.parse(list(argv)), RELEASE, engine)

    def refused(self, *argv: str) -> str:
        with self.assertRaises(extras.Refused) as caught:
            self.prepared(*argv)
        return str(caught.exception)

    def test_a_program_that_uses_blender_is_made_an_environment_of_cad_s_on_python_3_13(self) -> None:
        self.write("scene.py", "import bpy\n")
        self.write("render.py", "import scene\nimport json\n")  # bpy through a helper beside it
        self.write("both.py", "import build123d as bd\nfrom cad import model\nfrom cad.blender import load\n")
        spec = self.prepared("render.py").spec
        self.assertEqual((spec.integrations, spec.python, spec.python_options),
                         (("blender",), "3.13", ("--managed-python",)))
        here = dataclasses.replace(base.Installation.here(), python=SERVER)
        # But for uv's settings in the caller's environment, cad doctor's spec is the run's.
        self.assertEqual(dataclasses.replace(spec, environment=()), extras.integration_spec(here, ["blender"]))
        # Beside any other integration, its namespace in the library counting as an import of bpy does.
        both = self.prepared("both.py")
        self.assertEqual((both.spec.integrations, both.spec.python, both.line),
                         (("blender", "build123d"), "3.13", ("3.13", "blender")))
        for argv in (("-c", "import bpy.ops"), ("--with", "bpy", "-c", "print(1)"), ("--with", "cad[blender]", "-c", "1")):
            with self.subTest(argv=argv):
                self.assertEqual(self.prepared(*argv).spec.integrations, ("blender",))
        # cad is pinned in it as in any environment, and uv is asked for a Python it manages itself: never
        # `uv python install`, which writes a python3.13 among the person's commands.
        recipe = extras.recipe(here, both.spec)
        self.assertEqual(recipe.requirement, tuple(here.requirement(("blender", "build123d"))))
        self.assertEqual(base.commands("uv", Path("/env"), recipe)[0],
                         ["uv", "venv", "--no-project", "--python", "3.13", "--managed-python", str(Path("/env"))])
        self.assertIn(f"{BLENDER.holds}", recipe.making)
        # An engine on that line already makes it on its own Python, as it makes any other.
        own = self.prepared("both.py", engine=OWN).spec
        self.assertEqual((own.integrations, own.python, own.python_options), (("blender", "build123d"), None, ()))
        self.assertEqual(self.prepared("both.py", engine=OWN).given, [], "nothing to say again but the script")
        self.assertEqual(self.prepared("both.py").given, [], "the line is the integration's, not the command line's")

    def test_a_python_named_on_the_command_line_is_taken_on_its_line_and_refused_on_another(self) -> None:
        self.write("render.py", "import bpy\n")
        named = self.prepared("--python", "3.13.5", "render.py")
        self.assertEqual((named.spec.python, named.spec.python_options, named.given), ("3.13.5", (), ["--python=3.13.5"]))
        path = self.prepared("--python", "/opt/py/bin/python3", "render.py").spec
        self.assertEqual((path.python, path.python_options),  # absolute against the caller's folder; its version is
                         (extras.absolute("/opt/py/bin/python3", os.getcwd()), ()))  # read once it is made
        for given in ("3.14", "cpython-3.12", ">=3.14"):
            with self.subTest(given=given):
                self.assertEqual(self.refused("--python", given, "render.py"),
                                 "render.py uses cad's blender integration, which runs on Python 3.13 alone: --python "
                                 f"{given} is another; drop --python")
        # A request every 3.13 meets is no request beyond the line: the one environment no --python makes, on a
        # Python uv manages -- never a second one, nor one uv would make on a 3.14 for `>=3.12`, with no bpy in it.
        inferred = self.prepared("render.py").spec
        for given in ("3.13", "3", "cpython@3.13", "cpython-3.13", "cp3.13", ">=3.12", "==3.13.*", ">=3.11,<3.15"):
            with self.subTest(given=given):
                spec = self.prepared("--python", given, "render.py").spec
                self.assertEqual((spec.python, spec.python_options), ("3.13", ("--managed-python",)))
                self.assertEqual(extras.key(base.Installation.here(), spec),
                                 extras.key(base.Installation.here(), inferred))
                self.assertEqual(self.prepared("--python", given, "render.py", engine=OWN).spec.python, None,
                                 "on an engine of that line, its own Python, as with no --python")
        # One only some 3.13s meet is narrowed to them; a kind of Python named is kept.
        self.assertEqual(self.prepared("--python", ">=3.13.5", "render.py").spec.python, ">=3.13.5,==3.13.*")
        kind = self.prepared("--python", "3.13", "--no-managed-python", "render.py").spec
        self.assertEqual((kind.python, kind.python_options), ("3.13", ("--no-managed-python",)))
        self.assertEqual(extras.narrowed("3.12", "3.13"), "3.12", "another line, which cad run refuses first")

    def test_a_header_s_requires_python_that_leaves_3_13_out_is_refused(self) -> None:
        for wanted in ("==3.13.*", ">=3.13.5", ">=3.11,<3.14"):
            with self.subTest(wanted=wanted):
                self.write("ok.py", f'# /// script\n# requires-python = "{wanted}"\n# ///\nimport bpy\n')
                self.assertEqual(self.prepared("ok.py").spec.python, "3.13")
        self.write("newer.py", '# /// script\n# requires-python = ">=3.14"\n# ///\nimport bpy\n')
        self.assertEqual(self.refused("newer.py"), "newer.py requires Python >=3.14, and cad's blender integration, "
                                                   "which it uses, runs on Python 3.13 alone")
        # A header that names cad's integrations decides them, as for any script: one that leaves blender out
        # gets no bpy, and its run says which extra to name (cad._internal.integrations.missing).
        self.write("headed.py", '# /// script\n# dependencies = ["cad[trimesh]"]\n# ///\nimport bpy\n')
        headed = self.prepared("headed.py")
        self.assertEqual((headed.spec.integrations, headed.spec.python, headed.line), (("trimesh",), None, None))

    def test_a_platform_bpy_has_no_build_for_is_refused_by_name_before_anything_is_made(self) -> None:
        here = base.Installation.here()
        spec = extras.integration_spec(dataclasses.replace(here, python=SERVER), ["blender", "build123d"])
        for system, arch, said in (("darwin", "x86_64", "macOS x86-64"), ("linux", "aarch64", "Linux arm64")):
            with self.subTest(platform=said), mock.patch.object(extras, "_system", return_value=system):
                with self.assertRaises(extras.Refused) as caught:
                    extras.ensure(dataclasses.replace(here, arch=arch), spec, told=self.fail)
                self.assertEqual(str(caught.exception),
                                 f"cad's blender integration has no build for {said}: it runs on {BUILT}")
        self.assertFalse((Path(os.environ["CAD_CACHE_DIR"]) / base.BASE).exists(), "nothing made")
        from cad_server.cli import doctor

        with mock.patch.object(extras, "_system", return_value="darwin"), \
                mock.patch.object(base.Installation, "here", return_value=dataclasses.replace(here, arch="x86_64")):
            row = next(line for line in doctor._integrations() if line[1].startswith("blender "))
        self.assertEqual(row, ("info", "blender not made: cad's blender integration has no build for macOS x86-64: it "
                                       f"runs on {BUILT}"))
        for system, arch in (("darwin", "arm64"), ("linux", "x86_64"), ("win32", "AMD64"), ("win32", "ARM64")):
            with self.subTest(built=(system, arch)), mock.patch.object(extras, "_system", return_value=system):
                extras.supported(spec.integrations, arch)

    def test_its_environment_is_its_release_s_as_any_other_is(self) -> None:
        here = dataclasses.replace(base.Installation.here(), python=SERVER)
        spec = extras.integration_spec(here, ["blender"])
        later = dataclasses.replace(here, release="0.99.0", name="0.99.0")
        self.assertNotEqual(extras.key(here, spec), extras.key(later, spec), "cad is pinned in it: an update makes its own")
        self.assertEqual(extras._called(spec, "cad[blender] 0.11.3")[0], "the blender integration's environment")
        import cad.registry

        other = dataclasses.replace(BLENDER, name="other", python="3.12")
        with mock.patch.object(cad.registry, "INTEGRATIONS", {**INTEGRATIONS, "other": other}), \
                self.assertRaisesRegex(extras.Refused, "^cad's other integration runs on Python 3.12 alone and its "
                                                       "blender integration on Python 3.13 alone: no environment holds "
                                                       "both$"):
            extras.python_line(["blender", "other", "build123d"])

    def test_its_settings_folders_are_private_unless_the_caller_set_them(self) -> None:
        from cad.engine.places import cache_dir
        from cad_server.cli import run

        homes = run._homes(("blender", "build123d"), {"BLENDER_USER_SCRIPTS": "/mine", "PATH": "/bin"})
        self.assertEqual(sorted(homes), ["BLENDER_USER_CONFIG", "BLENDER_USER_DATAFILES", "BLENDER_USER_EXTENSIONS",
                                         "BLENDER_USER_RESOURCES"], "the caller's own BLENDER_USER_SCRIPTS kept")
        for variable, folder in (("BLENDER_USER_CONFIG", "user_config"), ("BLENDER_USER_RESOURCES", "user_resources"),
                                 ("BLENDER_USER_DATAFILES", "user_datafiles"), ("BLENDER_USER_EXTENSIONS", "user_extensions")):
            self.assertEqual(homes[variable], str(cache_dir() / "homes" / "blender" / folder))
            self.assertTrue(Path(homes[variable]).is_dir())
        self.assertEqual(run._homes(("build123d", "trimesh"), {}), {}, "a tool with no settings of its own")
        with mock.patch.dict(os.environ, {"CAD_CACHE_DIR": engine_daemon.unwritable(self.folder)}), \
                mock.patch("tempfile.gettempdir", return_value=str(self.folder / "tmp")):
            sandboxed = run._homes(("blender",), {})
        self.assertEqual(Path(sandboxed["BLENDER_USER_CONFIG"]).parent, self.folder / "tmp" / "cad-homes-blender",
                         "a sandbox's: the temporary folder")

    def test_cad_doctor_gives_it_the_row_every_integration_has(self) -> None:
        from cad_server._internal import integration_env
        from cad_server.cli import doctor

        rows = dict((line.split(" ", 1)[0], (status, line)) for status, line in doctor._integrations())
        status, line = rows["blender"]
        if integration_env.carries("blender"):  # a development environment on Python 3.13 with the extra
            self.assertEqual((status, line), ("ok", "blender this installation carries it (cad[blender])"))
        else:
            self.assertEqual(status, "info")
            # No command of cad's needs it: a run of a script that imports bpy makes it (the registry says so).
            self.assertRegex(line, r"^blender cad\[blender\] \S+, made on first need in .+: the first `cad run` of a "
                                   r"program that imports bpy and no other integration$")
        if "kicad" in rows and rows["kicad"][0] == "info":
            self.assertTrue(rows["kicad"][1].endswith(": the first command that needs it"), rows["kicad"])

    def test_cad_doctor_says_an_environment_whose_python_is_gone_is_made_again(self) -> None:
        from cad_server._internal import integration_env
        from cad_server.cli import doctor

        if integration_env.carries("blender"):
            self.skipTest("this installation carries the blender integration itself")
        _state, folder, _release = integration_env.found("blender")
        env = Path(folder)
        env.mkdir(parents=True)
        (env / base.MARKER).write_text(json.dumps({"schema": base.SCHEMA, "key": env.name, "with": []}),
                                       encoding="utf-8")  # made, and its Python since uninstalled
        row = next(line for status, line in doctor._integrations() if line.startswith("blender "))
        self.assertRegex(row, r"^blender cad\[blender\] \S+ in .+ has lost its Python: made again on first need, the "
                              r"first `cad run` of a program that imports bpy and no other integration$")


if __name__ == "__main__":
    unittest.main()
