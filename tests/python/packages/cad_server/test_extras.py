"""``cad run --with`` and a script's inline metadata (PEP 723): the environment of a model's own packages
beside the base (``cad_server._internal.extras``) -- what names them, how they are keyed, what uv's refusals
are said as -- and, with the real uv and no network (``UV_OFFLINE``), a tiny local package a model imports,
through ``--with`` and through its header, in an environment made once and used again, and what each
document's record says builds it again."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
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
        self.assertEqual(extras.arguments(["--with", "a,b", "--with=c", "model.py", "--with", "x"]),
                         (["a", "b", "c"], ["model.py", "--with", "x"]), "the program's own arguments are its own")
        self.assertEqual(extras.arguments(["--", "-c", "print(1)"]), ([], ["-c", "print(1)"]))
        with self.assertRaisesRegex(extras.Refused, "^--with takes a requirement"):
            extras.arguments(["--with"])

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

    def test_making_one_removes_other_releases_environments_but_the_bases_and_one_a_process_runs_from(self) -> None:
        folder = Path(tempfile.mkdtemp(prefix="extras-collect-"))
        self.addCleanup(shutil.rmtree, folder, True)

        def made(name: str, release: str, given: list[str] | None, local: dict | None = None) -> Path:
            env = folder / name
            base.interpreter(env).parent.mkdir(parents=True)
            base.interpreter(env).write_bytes(b"")
            marker = {"schema": base.SCHEMA, "key": name, "inputs": {"release": release}}
            if given is not None:
                marker.update({"with": given, "local": local or {}})
            (env / base.MARKER).write_text(json.dumps(marker), encoding="utf-8")
            return env

        old = made("old", "0.9.0", ["pandas"])
        superseded = made("edited", "0.10.0", ["/w/gears"], {"/w/gears": "before"})
        now = made("now", "0.10.0", ["/w/gears"], {"/w/gears": "after"})
        for name, release, given in (("held", "0.9.0", ["scipy"]), ("same", "0.10.0", ["pandas"]),
                                     ("base", "0.9.0", None)):
            made(name, release, given)
        with mock.patch("cad_server._internal.releases.running", side_effect=lambda env: Path(env).name == "held"):
            self.assertEqual(sorted(extras._collect(folder, "0.10.0", made=now, requirements=["/w/gears"],
                                                    inputs={"release": "0.10.0"})), sorted([str(superseded), str(old)]))
        self.assertEqual(sorted(path.name for path in folder.iterdir()), ["base", "held", "now", "same"],
                         "a base is its release's to remove; one a process runs from goes at a later making; the "
                         "environments of other packages stay")
        self.assertEqual(extras._changed(folder, {"release": "0.10.0"}, ["/w/gears"], {"/w/gears": "later"}),
                         ["/w/gears"], "the line that makes it again names the local package edited")


def _wheel(folder: Path, width: int = 42) -> Path:
    """A tiny pure-Python package as a wheel uv installs with no build and no network: ``localpkg``, its
    ``WIDTH`` the one given."""
    path = folder / "localpkg-0.1-py3-none-any.whl"
    files = {"localpkg/__init__.py": f"WIDTH = {width}\n".encode(),
             "localpkg-0.1.dist-info/METADATA": b"Metadata-Version: 2.1\nName: localpkg\nVersion: 0.1\n",
             "localpkg-0.1.dist-info/WHEEL": b"Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\n"
                                              b"Tag: py3-none-any\n"}

    def digest(data: bytes) -> str:
        return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()

    record = "".join(f"{name},{digest(data)},{len(data)}\n" for name, data in files.items())
    with zipfile.ZipFile(path, "w") as wheel:
        for name, data in files.items():
            wheel.writestr(name, data)
        wheel.writestr("localpkg-0.1.dist-info/RECORD", record + "localpkg-0.1.dist-info/RECORD,,\n")
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

    def run_(self, *args: str) -> subprocess.CompletedProcess:
        return engine_daemon.run([sys.executable, "-m", "cad_server.cli", "run", *args], env=self.env, cwd=self.project)

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
