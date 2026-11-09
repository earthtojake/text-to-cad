"""An integration whose environment holds no library: blender's bpy, on Python 3.13 without cad
(``cad_server._internal.extras.alone``, ``cad_server.cli.run``) -- what a program's imports choose and what is
refused in one line, its spec, recipe and key, its private settings folders, ``cad doctor``'s row and the
prune; and, with the real uv, a tiny ``bpy`` and its pins in a folder of wheels on a second Python line (3.13, a
managed one uv fetches where it has none: the one download here), run with its folder first, without cad, and
made once."""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from tests.python.support import engine_daemon
from tests.python.support.paths import add_sources

add_sources()

from cad.registry import INTEGRATIONS  # noqa: E402
from cad_server._internal import base, extras  # noqa: E402

BLENDER = INTEGRATIONS["blender"]
RELEASE = "0.11.3"


def _wheel(folder: Path, name: str, version: str, files: dict[str, str], requires_python: str | None = None) -> Path:
    """A tiny pure-Python wheel uv installs with no build and no network: ``name`` at ``version``, holding
    ``files``."""
    stem = name.replace("-", "_")
    info = f"{stem}-{version}.dist-info"
    metadata = f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
    metadata += f"Requires-Python: {requires_python}\n" if requires_python else ""
    contents = {**{path: text.encode() for path, text in files.items()}, f"{info}/METADATA": metadata.encode(),
                f"{info}/WHEEL": b"Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n"}

    def digest(data: bytes) -> str:
        return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()

    path = folder / f"{stem}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as wheel:
        for item, data in contents.items():
            wheel.writestr(item, data)
        wheel.writestr(f"{info}/RECORD", "".join(f"{item},{digest(data)},{len(data)}\n" for item, data in contents.items())
                       + f"{info}/RECORD,,\n")
    return path


class ChoosingTest(unittest.TestCase):
    """What a ``cad run`` line of a program that imports bpy is made of, and what is refused before anything is made.
    Nothing is made: no uv."""

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

    def prepared(self, *argv: str):
        from cad_server.cli import run

        return run.prepare(run.parse(list(argv)), RELEASE)

    def refused(self, *argv: str) -> str:
        with self.assertRaises(extras.Refused) as caught:
            self.prepared(*argv)
        return str(caught.exception)

    def test_an_import_of_bpy_gets_its_own_pins_on_its_own_python_without_cad(self) -> None:
        self.write("scene.py", "import bpy\n")
        self.write("render.py", "import scene\nimport json\n")  # bpy through a helper beside it
        spec = self.prepared("render.py").spec
        self.assertEqual((spec.integrations, spec.python, spec.python_options),
                         (("blender",), "3.13", ("--managed-python",)))
        self.assertEqual(spec, extras.integration_spec(["blender"]), "cad doctor's spec is the run's")
        for argv in (("-c", "import bpy.ops"), ("--with", "bpy", "-c", "print(1)")):
            with self.subTest(argv=argv):
                self.assertEqual(self.prepared(*argv).spec.integrations, ("blender",))
        here = base.Installation.here()
        recipe = extras.recipe(here, spec)
        self.assertEqual(recipe.requirement, BLENDER.requires, "the integration's own pins, and no cad")
        self.assertIsNone(recipe.revise, "nothing resolved again: no pins of cad's to decide")
        self.assertEqual(base.commands("uv", Path("/env"), recipe)[0],
                         ["uv", "venv", "--no-project", "--python", "3.13", "--managed-python", str(Path("/env"))],
                         "a managed Python uv fetches itself: never `uv python install`, which writes python3.13")
        self.assertEqual(recipe.making, "making the blender integration's environment, once: bpy 5.2.3 on Python 3.13 "
                                        f"(Blender as a Python module, about {BLENDER.download_mb} MB to download)")
        self.assertEqual(recipe.downloading,
                         f"downloading bpy 5.2.3 (Blender as a Python module, about {BLENDER.download_mb} MB), once")
        packages = extras.recipe(here, dataclasses.replace(spec, requirements=("pillow",)))
        self.assertEqual(packages.requirement, (*BLENDER.requires, "pillow"))
        self.assertTrue(packages.making.startswith("making the blender integration's environment, once: pillow beside "
                                                   "bpy 5.2.3 on Python 3.13"))
        # --python: its own Python's line passes, a path is taken as named (and checked once made), another is refused.
        self.assertEqual(self.prepared("--python", "3.13.5", "render.py").spec.python_options, ("--managed-python",))
        named = self.prepared("--python", "/opt/py313/bin/python3", "render.py").spec
        self.assertEqual((named.python, named.python_options), ("/opt/py313/bin/python3", ()))
        self.assertEqual(self.refused("--python", "3.14", "render.py"),
                         "render.py uses bpy, which the blender integration runs on Python 3.13: --python 3.14 is "
                         "another; drop --python")

    def test_a_program_that_names_cad_too_is_refused_in_one_line(self) -> None:
        self.write("both.py", "import bpy\nfrom cad import model\n")
        self.assertEqual(self.refused("both.py"),
                         "both.py uses bpy, which the blender integration runs on Python 3.13 without cad, and imports "
                         "cad too: a program that uses bpy uses nothing of cad's -- write what it reads first (cad model "
                         "export ID scene.glb), then run each with cad run on its own")
        self.write("kernel.py", "import bpy\nimport build123d\n")
        self.assertIn("and uses build123d, an integration of cad's:", self.refused("kernel.py"))
        self.write("headed.py", '# /// script\n# dependencies = ["cad[trimesh]"]\n# ///\nimport bpy\n')
        self.assertIn("and its header names cad", self.refused("headed.py"), "a header's cad[...] decides cad's "
                                                                              "integrations, never hides bpy")
        self.write("plain.py", "import bpy\n")
        self.assertIn("and --with names cad; uses trimesh", self.refused("--with", "cad[trimesh]", "plain.py"))
        with self.assertRaisesRegex(extras.Refused, "no environment holds both"):
            extras.alone(["blender", "build123d"])

    def test_a_header_s_requires_python_is_its_python_s(self) -> None:
        for wanted in ("==3.13.*", ">=3.13.5", ">=3.11,<3.14"):
            with self.subTest(wanted=wanted):
                self.write("ok.py", f'# /// script\n# requires-python = "{wanted}"\n# ///\nimport bpy\n')
                self.assertEqual(self.prepared("ok.py").spec.python, "3.13")
        self.write("newer.py", '# /// script\n# requires-python = ">=3.14"\n# ///\nimport bpy\n')
        self.assertEqual(self.refused("newer.py"), "newer.py requires Python >=3.14, and the blender integration's is "
                                                   "3.13: bpy 5.2.3 is built for it alone")

    def test_a_platform_bpy_has_no_build_for_is_refused_by_name_before_anything_is_made(self) -> None:
        here = base.Installation.here()
        spec = extras.integration_spec(["blender"])
        for system, arch, said in (("darwin", "x86_64", "macOS x86-64"), ("linux", "aarch64", "Linux arm64")):
            with self.subTest(platform=said), mock.patch.object(extras, "_system", return_value=system):
                with self.assertRaises(extras.Refused) as caught:
                    extras.ensure(dataclasses.replace(here, arch=arch), spec, told=self.fail)
                self.assertEqual(str(caught.exception), f"bpy 5.2.3 has no build for {said}: the blender integration "
                                                        "runs on macOS arm64, Linux x86-64, Windows x86-64 and Windows arm64")
        self.assertFalse((Path(os.environ["CAD_CACHE_DIR"]) / base.BASE).exists(), "nothing made")
        from cad_server.cli import doctor

        with mock.patch.object(extras, "_system", return_value="darwin"), \
                mock.patch.object(base.Installation, "here", return_value=dataclasses.replace(here, arch="x86_64")):
            row = next(line for line in doctor._integrations() if line[1].startswith("blender "))
        self.assertEqual(row, ("info", "blender bpy 5.2.3 has no build for macOS x86-64: the blender integration runs on "
                                       "macOS arm64, Linux x86-64, Windows x86-64 and Windows arm64"))

    def test_its_key_outlives_a_release_and_no_release_removes_it(self) -> None:
        here = base.Installation.here()
        spec = extras.integration_spec(["blender"])
        later = dataclasses.replace(here, release="0.99.0", name="0.99.0", prefix="/elsewhere", python="3.14.9")
        self.assertEqual(extras.key(here, spec), extras.key(later, spec), "an update keeps it")
        self.assertNotEqual(extras.key(here, Spec := extras.Spec(integrations=("trimesh",))), extras.key(later, Spec),
                            "an environment of cad's is its release's")
        folder = Path(tempfile.mkdtemp(prefix="blender-collect-"))
        self.addCleanup(shutil.rmtree, folder, True)
        for name, inputs in (("alone", extras._inputs(here, spec)), ("old", {"release": "0.1.0"})):
            env = folder / name
            base.interpreter(env).parent.mkdir(parents=True)
            base.interpreter(env).write_bytes(b"")
            (env / base.MARKER).write_text(json.dumps({"schema": base.SCHEMA, "key": name, "inputs": inputs, "with": []}),
                                           encoding="utf-8")
        self.assertEqual(extras._inputs(here, spec), {"schema": base.SCHEMA, "alone": "blender", "arch": here.arch})
        with mock.patch("cad_server._internal.releases.running", return_value=False):
            self.assertEqual(extras._collect(folder, {RELEASE}), [str(folder / "old")])
        self.assertTrue((folder / "alone").is_dir())

    def test_its_settings_folders_are_private_unless_the_caller_set_them(self) -> None:
        from cad.engine.places import cache_dir
        from cad_server.cli import run

        env = run._homes(BLENDER, {"BLENDER_USER_SCRIPTS": "/mine", "PYTHONSAFEPATH": "1", "PATH": "/bin"})
        self.assertEqual((env["BLENDER_USER_SCRIPTS"], env["PATH"]), ("/mine", "/bin"), "the caller's own kept")
        self.assertNotIn("PYTHONSAFEPATH", env, "the script's folder first on its path")
        for variable, folder in (("BLENDER_USER_CONFIG", "user_config"), ("BLENDER_USER_RESOURCES", "user_resources"),
                                 ("BLENDER_USER_DATAFILES", "user_datafiles"), ("BLENDER_USER_EXTENSIONS", "user_extensions")):
            self.assertEqual(env[variable], str(cache_dir() / "homes" / "blender" / folder))
            self.assertTrue(Path(env[variable]).is_dir())
        with mock.patch.dict(os.environ, {"CAD_CACHE_DIR": engine_daemon.unwritable(self.folder)}), \
                mock.patch("tempfile.gettempdir", return_value=str(self.folder / "tmp")):
            sandboxed = run._homes(BLENDER, {})
        self.assertEqual(Path(sandboxed["BLENDER_USER_CONFIG"]).parent, self.folder / "tmp" / "cad-homes-blender",
                         "a sandbox's: the temporary folder")

    def test_cad_doctor_says_where_it_is_and_the_prune_takes_it_unused(self) -> None:
        from cad_server._internal import leftovers
        from cad_server.cli import doctor

        rows = dict((line.split(" ", 1)[0], (status, line)) for status, line in doctor._integrations())
        status, line = rows["blender"]
        self.assertEqual(status, "info")
        self.assertRegex(line, r"^blender bpy 5\.2\.3 on Python 3\.13, made on first need in .+: the first cad run of a "
                               r"program that imports bpy$")
        env = extras.where(base.Installation.here(), extras.integration_spec(["blender"]))
        base.interpreter(env).parent.mkdir(parents=True)
        base.interpreter(env).write_bytes(b"")
        (env / base.MARKER).write_text(json.dumps({"schema": base.SCHEMA, "key": env.name, "with": [],
                                                   "spec": extras.integration_spec(["blender"]).keyed()}), encoding="utf-8")
        self.assertEqual(dict((line.split(" ", 1)[0], status) for status, line in doctor._integrations())["blender"], "ok")
        cache = Path(os.environ["CAD_CACHE_DIR"])
        with mock.patch("cad_server._internal.releases.running", return_value=False):
            self.assertEqual(leftovers.package_environments(cache).recent, [env], "used now: kept")
            self.assertEqual(leftovers.package_environments(cache, now=time.time() + 8 * 86400).paths, [env])


RENDER = """\
import json
import os
import sys

FIRST = sys.path[0]
import bpy
import helper
import sysconfig

installed = os.listdir(sysconfig.get_paths()["purelib"])  # the environment's own, not what PYTHONPATH names
library = any(name.lower().startswith(("c" + "ad-", "c" + "ad_server-")) for name in installed)
print(json.dumps({"python": list(sys.version_info[:2]), "bpy": bpy.VERSION, "first": FIRST, "helper": helper.NAME,
                  "library": library, "config": os.environ.get("BLENDER_USER_CONFIG"),
                  "scripts": os.environ.get("BLENDER_USER_SCRIPTS"), "args": sys.argv[1:]}))
"""


def _built_here() -> bool:
    try:
        extras.supported(BLENDER, base.Installation.here().arch)
    except extras.Refused:
        return False
    return True


@unittest.skipUnless(_built_here(), "bpy has no build for this platform (an Intel Mac, Linux arm64): the refusal is "
                                    "ChoosingTest's; every CI runner has one")
class RunTest(unittest.TestCase):
    """The real uv: a fake bpy and its pins from a folder of wheels (``--no-index``), on a managed Python 3.13."""

    @classmethod
    def setUpClass(cls) -> None:
        engine_daemon.isolate(cls.addClassCleanup)
        cls.project = Path(tempfile.mkdtemp(prefix="blender-run-")).resolve()
        cls.addClassCleanup(shutil.rmtree, cls.project, True)
        cls.wheels = cls.project / "wheels"
        cls.wheels.mkdir()
        for requirement in BLENDER.requires:
            name, version = requirement.split("==")
            module = name.replace("-", "_")
            files = {f"{module}/__init__.py": f"VERSION = {version!r}\n"}
            _wheel(cls.wheels, name, version, files, "==3.13.*" if name == "bpy" else None)
        cls.env = engine_daemon.watched({**os.environ, "CAD_ENGINE_MESH": "inline"}, cls.addClassCleanup)

    def run_(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        return engine_daemon.run([sys.executable, "-m", "cad_server.cli", "run", "--no-index", "--find-links",
                                  str(self.wheels), *args], env=env or self.env, cwd=self.project)

    def test_a_script_that_imports_bpy_runs_on_its_python_without_cad_its_folder_first_made_once(self) -> None:
        scripts = self.project / "scenes"
        scripts.mkdir()
        (scripts / "render.py").write_text(RENDER, encoding="utf-8")
        (scripts / "helper.py").write_text('NAME = "beside"\n', encoding="utf-8")
        first = self.run_("scenes/render.py", "--frames", "4", env={**self.env, "BLENDER_USER_SCRIPTS": "/mine"})
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertIn("cad run: making the blender integration's environment, once: bpy 5.2.3 on Python 3.13 (",
                      first.stderr)
        said = json.loads(first.stdout.strip().splitlines()[-1])
        cache = Path(os.environ["CAD_CACHE_DIR"])
        self.assertEqual(said, {"python": [3, 13], "bpy": "5.2.3", "first": str(scripts), "helper": "beside",
                                "library": False, "config": str(cache / "homes" / "blender" / "user_config"),
                                "scripts": "/mine", "args": ["--frames", "4"]})
        again = self.run_("scenes/render.py")
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertNotIn("making", again.stderr, "made once, used again")
        made = [marker for path in (cache / base.BASE).iterdir() if (marker := base.complete(path))]
        self.assertEqual(len(made), 1)
        self.assertEqual(sorted(made[0]["inputs"]), ["alone", "arch", "schema"], "no release: an update keeps it")
        self.assertNotIn("installation", made[0], "no release's to remove with it")
        self.assertEqual((made[0]["with"], made[0]["integrations"]), ([], ["blender"]))
        self.assertTrue(made[0]["python_version"].startswith("3.13."))


if __name__ == "__main__":
    unittest.main()
