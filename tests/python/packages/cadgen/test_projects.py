"""The environment ``cadgen run`` runs a model in (``cadgen._internal.projects``): the script's project
and what it declares, the Python its environment runs, the environment's key and marker, the uv
commands that make it and what is said when uv cannot.

uv is faked: an executable named ``uv`` first on a temporary PATH, which records its arguments and
makes the environment's Python as ``uv venv`` would. The real uv makes environments in test_run.py.
"""

from __future__ import annotations

import importlib.metadata
import json
import os
import re
import sys
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from tests.python.support.paths import add_repo_path, repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal import projects  # noqa: E402

RELEASE = projects.Engine("0.8.3", "0.8.3", "3.13", None, "arm64")

# The fake uv: records its arguments, one JSON list a line, and does what FAKE_UV_FAIL asks of the step it
# names (its words on stderr, exit 1); `uv venv` makes the environment's Python.
FAKE = textwrap.dedent("""\
    import json, os, sys
    args = sys.argv[1:]
    with open(os.environ["FAKE_UV_LOG"], "a", encoding="utf-8") as log:
        log.write(json.dumps(args) + "\\n")
    fail = os.environ.get("FAKE_UV_FAIL", "")
    if fail and args[0] == fail and os.environ.get("FAKE_UV_FAIL_UNLESS", "-") not in args:
        sys.stderr.buffer.write(os.environ["FAKE_UV_SAID"].encode("utf-8"))  # as uv writes: UTF-8, whatever the console's code page
        sys.stderr.buffer.flush()
        sys.exit(1)
    if args[0] == "venv":
        python = os.path.join(args[-1], "Scripts", "python.exe") if os.name == "nt" else os.path.join(args[-1], "bin", "python")
        os.makedirs(os.path.dirname(python), exist_ok=True)
        open(python, "w").close()
""")

CONFLICT = """Using Python 3.13.13 environment at: envs/x
  × No solution found when resolving dependencies:
  ╰─▶ Because cadgen==0.8.3 depends on build123d>=0.13.0,<0.14 and you require
      cadgen==0.8.3, we can conclude that you require build123d>=0.13.0,<0.14.
      And because you require build123d==0.1, we can conclude that your
      requirements are unsatisfiable.
"""
OFFLINE = """error: Failed to fetch: `https://pypi.org/simple/six/`
  Caused by: error sending request for url (https://pypi.org/simple/six/)
  Caused by: tcp connect error
  Caused by: Connection refused (os error 61)
"""
DENIED = """error: Failed to initialize cache at `/Users/me/.cache/uv`
  Caused by: failed to create directory `/Users/me/.cache/uv`: Operation not permitted (os error 1)
"""
NO_PYTHON = """error: No interpreter found for Python 3.12.1 in managed installations

hint: A managed Python download is available for Python 3.12.1, but Python downloads are set to 'never'
"""


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        patch = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / "cache")})
        patch.start()
        self.addCleanup(patch.stop)

    def write(self, relative: str, text: str = "") -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text), encoding="utf-8", newline="\n")  # the bytes as given, on Windows too
        return path

    def fake_uv(self) -> Path:
        """A fake uv first on PATH; its log."""
        folder = self.root / "fake-bin"
        folder.mkdir(exist_ok=True)
        script = folder / "fake_uv.py"
        script.write_text(FAKE, encoding="utf-8")
        if os.name == "nt":
            (folder / "uv.bat").write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
        else:
            uv = folder / "uv"
            uv.write_text(f"#!{sys.executable}\n" + FAKE, encoding="utf-8")
            uv.chmod(0o755)
        log = self.root / "uv.log"
        patch = mock.patch.dict(os.environ, {"PATH": os.pathsep.join((str(folder), os.environ.get("PATH", ""))),
                                             "FAKE_UV_LOG": str(log), "FAKE_UV_FAIL": ""})
        patch.start()
        self.addCleanup(patch.stop)
        return log

    @staticmethod
    def calls(log: Path) -> list[list[str]]:
        return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []


class EngineSaid(unittest.TestCase):
    def test_the_engine_is_what_its_hello_says_and_an_engine_from_before_its_release(self) -> None:
        said = {"release": "0.8.3", "port": 3245, "installation": "0.8.3-dev.20261028", "python": "3.12",
                "source": "/work/text-to-cad/packages/cadgen", "native": {"system": "Darwin", "arch": "arm64"}}
        self.assertEqual(projects.Engine.said(said), projects.Engine("0.8.3", "0.8.3-dev.20261028", "3.12",
                                                                     "/work/text-to-cad/packages/cadgen", "arm64"))
        before = projects.Engine.said({"release": "0.8.2", "port": 3245})
        self.assertEqual(before, projects.Engine("0.8.2", "0.8.2", "%d.%d" % sys.version_info[:2], None, None))
        self.assertEqual(before.requirement(), ["cadgen==0.8.2"])
        with self.assertRaisesRegex(projects.Refused, "the engine on port 3245 names no cadgen release"):
            projects.Engine.said({"release": None, "port": 3245})


class Discovery(Fixture):
    def test_a_script_in_a_bare_folder_is_a_project_of_its_own_that_declares_nothing(self) -> None:
        script = self.write("loose/model.py", "print(1)\n")
        project = projects.find(script)
        self.assertEqual((project.root, project.marked), (script.parent, False))
        self.assertEqual((project.requirements, project.pyproject, project.lock, project.inline), (None, None, None, None))
        self.assertEqual((project.package, project.dependencies(), project.requires_python()), (False, [], []))

    def test_the_project_is_the_nearest_folder_holding_a_marker(self) -> None:
        self.write("robot/pyproject.toml", '[project]\nname = "robot"\nversion = "1"\n')
        script = self.write("robot/parts/arm/model.py")
        self.assertEqual(projects.find(script).root, self.root / "robot")
        self.write("robot/parts/requirements.txt", "six\n")
        nearer = projects.find(script)
        self.assertEqual((nearer.root, nearer.requirements), (self.root / "robot/parts", self.root / "robot/parts/requirements.txt"))
        self.assertIsNone(nearer.pyproject, "the nearest project's files alone")
        self.write("robot/parts/arm/uv.lock", "version = 1\n")
        self.assertEqual(projects.find(script).root, self.root / "robot/parts/arm", "the script's own folder first")

    def test_a_pyproject_installs_its_package_or_its_dependencies(self) -> None:
        script = self.write("pkg/model.py")
        env = self.root / "cache/envs/k"

        def installs() -> list[str]:
            return projects.commands("uv", env, "3.13", RELEASE, projects.find(script))[1][10:]

        self.write("pkg/pyproject.toml", """\
            [build-system]
            requires = ["setuptools"]
            [project]
            name = "pkg"
            version = "1"
            dependencies = ["six"]
        """)
        self.assertTrue(projects.find(script).package)
        self.assertEqual(installs(), ["-e", str(self.root / "pkg")], "a build system: the package, editable")
        self.write("pkg/pyproject.toml", '[project]\nname = "pkg"\nversion = "1"\ndependencies = ["six", "numpy>=2"]\n')
        self.assertFalse(projects.find(script).package)
        self.assertEqual(installs(), ["-r", str(self.root / "pkg/pyproject.toml")],
                         "none: its [project] dependencies, as uv reads a project it does not build (its sources too)")
        self.write("pkg/pyproject.toml", '[project]\nname = "pkg"\nversion = "1"\n[tool.uv]\npackage = true\n')
        self.assertTrue(projects.find(script).package, "tool.uv.package says so")
        self.write("pkg/pyproject.toml", "[tool.ruff]\nline-length = 120\n")
        project = projects.find(script)
        self.assertEqual((project.root, project.table, project.package, installs()),
                         (self.root / "pkg", None, False, []), "a pyproject with no [project] declares nothing")
        self.write("pkg/pyproject.toml", "[project\n")
        with self.assertRaisesRegex(projects.Refused, "pyproject.toml is not TOML"):
            projects.find(script)

    def test_a_requirements_project_lists_its_file(self) -> None:
        script = self.write("req/model.py")
        self.write("req/requirements.txt", "six\n")
        project = projects.find(script)
        self.assertEqual((project.root, project.requirements, project.listed), (self.root / "req", self.root / "req/requirements.txt", b"six\n"))

    def test_inline_script_metadata_is_read_as_pep_723_says(self) -> None:
        script = self.write("inline/model.py", """\
            # /// script
            # requires-python = ">=3.12"
            # dependencies = [
            #   "six",
            # ]
            # ///
            import six
        """)
        project = projects.find(script)
        self.assertEqual(project.dependencies(), ["six"])
        self.assertEqual(project.requires_python(), [">=3.12"])
        self.assertTrue(project.inline.startswith("# /// script\n") and project.inline.endswith("# ///"))
        script.write_text("# /// script\n# dependencies = []\n# ///\nimport os\n# /// script\n# dependencies = []\n# ///\n",
                          encoding="utf-8")
        with self.assertRaisesRegex(projects.Refused, "more than one `# /// script` block"):
            projects.find(script)
        script.write_text("# /// script\n# dependencies = [\n# ///\n", encoding="utf-8")
        with self.assertRaisesRegex(projects.Refused, "is not TOML"):
            projects.find(script)
        script.write_text("# /// script\n# dependencies = 'six'\n# ///\n", encoding="utf-8")
        with self.assertRaisesRegex(projects.Refused, "not a list of requirements"):
            projects.find(script)

    def test_the_projects_own_venv_is_neither_read_nor_written(self) -> None:
        script = self.write("own/model.py")
        self.write("own/requirements.txt", "six\n")
        venv = self.root / "own/.venv"
        (venv / "bin").mkdir(parents=True)
        log = self.fake_uv()
        env = projects.ensure(projects.find(script), RELEASE, "3.13", told=lambda _line: None)
        self.assertEqual(env.parent, self.root / "cache" / "envs")
        self.assertEqual(sorted(path.name for path in venv.rglob("*")), ["bin"])
        self.assertFalse(any(str(venv) in " ".join(call) for call in self.calls(log)))


class Python(Fixture):
    def test_python_version_within_the_set_is_honoured_as_written(self) -> None:
        self.write("py/model.py")
        self.write("py/.python-version", "# the project's\n3.12\n")
        self.assertEqual(projects.python_for(projects.find(self.root / "py/model.py"), RELEASE), "3.12")
        self.write("py/.python-version", "3.12.4\n")
        self.assertEqual(projects.python_for(projects.find(self.root / "py/model.py"), RELEASE), "3.12.4")
        self.write("py/pyproject.toml", '[project]\nname = "py"\nversion = "1"\nrequires-python = ">=3.13"\n')
        self.assertEqual(projects.python_for(projects.find(self.root / "py/model.py"), RELEASE), "3.12.4",
                         ".python-version first, as uv reads it")

    def test_requires_python_takes_the_newest_line_in_the_set_it_admits(self) -> None:
        self.write("py/model.py")
        lines = projects.supported()
        self.write("py/pyproject.toml", '[project]\nname = "py"\nversion = "1"\nrequires-python = ">=3.11"\n')
        self.assertEqual(projects.python_for(projects.find(self.root / "py/model.py"), RELEASE), lines[-1])
        self.write("py/pyproject.toml", '[project]\nname = "py"\nversion = "1"\nrequires-python = ">=3.11,<3.13"\n')
        self.assertEqual(projects.python_for(projects.find(self.root / "py/model.py"), RELEASE), "3.12")
        # The script's inline requires-python is a constraint too: both hold.
        self.write("py/model.py", '# /// script\n# requires-python = "<3.12"\n# ///\n')
        self.assertEqual(projects.python_for(projects.find(self.root / "py/model.py"), RELEASE), "3.11")

    def test_a_project_that_declares_nothing_takes_the_engines_line(self) -> None:
        self.write("py/model.py")
        self.write("py/requirements.txt", "six\n")
        engine = projects.Engine("0.8.3", "0.8.3", "3.12")
        self.assertEqual(projects.python_for(projects.find(self.root / "py/model.py"), engine), "3.12")

    def test_a_line_outside_the_set_is_refused_naming_the_set(self) -> None:
        self.write("py/model.py")
        with mock.patch.object(projects, "supported", return_value=("3.11", "3.12", "3.13", "3.14")):
            self.write("py/.python-version", "3.10\n")
            with self.assertRaises(projects.Refused) as refused:
                projects.python_for(projects.find(self.root / "py/model.py"), RELEASE)
            self.assertEqual(str(refused.exception), "this project asks for Python 3.10; cadgen runs on 3.11–3.14: "
                                                     "change requires-python or .python-version")
            self.write("py/.python-version", "pypy@3.11\n")
            with self.assertRaisesRegex(projects.Refused, "asks for Python pypy@3.11; cadgen runs on 3.11–3.14"):
                projects.python_for(projects.find(self.root / "py/model.py"), RELEASE)
            (self.root / "py/.python-version").unlink()
            self.write("py/pyproject.toml", '[project]\nname = "py"\nversion = "1"\nrequires-python = ">=3.8,<3.11"\n')
            with self.assertRaisesRegex(projects.Refused, r"^this project asks for Python >=3.8,<3.11; cadgen runs on"):
                projects.python_for(projects.find(self.root / "py/model.py"), RELEASE)
            self.write("py/pyproject.toml", '[project]\nname = "py"\nversion = "1"\nrequires-python = "three"\n')
            with self.assertRaisesRegex(projects.Refused, "requires-python 'three' is no version specifier"):
                projects.python_for(projects.find(self.root / "py/model.py"), RELEASE)

    def test_the_lines_are_those_cadgen_its_ocp_and_build123d_all_admit(self) -> None:
        said = {"cadgen": ">=3.11", "cadquery-ocp-novtk": ">=3.10,<3.15", "build123d": "<3.15,>=3.11"}

        def metadata(name: str):
            if name not in said:
                raise importlib.metadata.PackageNotFoundError(name)
            return {"Requires-Python": said[name]}

        with mock.patch.object(importlib.metadata, "metadata", side_effect=metadata):
            self.assertEqual(projects.supported(), ("3.11", "3.12", "3.13", "3.14"))
            said["build123d"] = ">=3.11,<3.13"
            self.assertEqual(projects.supported(), ("3.11", "3.12"))
            said["build123d"] = ">=3.11"
            said["cadquery-ocp-novtk"] = ">=3.11"
            self.assertEqual(projects.supported(), projects.PYTHONS, "unbounded above: up to the newest cadgen names")
            del said["cadquery-ocp-novtk"]
            self.assertEqual(projects.supported(), projects.PYTHONS, "a distribution that is not installed: the fallback")
        # The fallback starts at cadgen's own floor.
        floor = re.search(r'requires-python = ">=(\d+\.\d+)"', repo_path("packages/cadgen/pyproject.toml").read_text(encoding="utf-8"))[1]
        self.assertEqual(projects.PYTHONS[0], floor)

    def test_a_python_line_meets_a_specifier_when_one_of_its_releases_does(self) -> None:
        cases = {">=3.12.4": ["3.12", "3.13"], "==3.12.*": ["3.12"], "~=3.12": ["3.12", "3.13"], ">3.13": ["3.13"],
                 "!=3.12.*,>=3.11": ["3.11", "3.13"], "<3.12.2": ["3.11", "3.12"], "<=3.11": ["3.11"]}
        for spec, admitted in cases.items():
            with self.subTest(spec=spec):
                self.assertEqual([line for line in ("3.11", "3.12", "3.13") if projects.admits(projects.clauses(spec), line)],
                                 admitted)
        self.assertIsNone(projects.clauses(">=3.12.*"))
        self.assertIsNone(projects.clauses("~=3"))


class Key(Fixture):
    def test_the_key_changes_with_each_input_and_is_stable_otherwise(self) -> None:
        script = self.write("k/model.py")
        self.write("k/requirements.txt", "six\n")
        self.write("k/pyproject.toml", '[project]\nname = "k"\nversion = "1"\n')
        self.write("k/uv.lock", "version = 1\n")

        def key(engine=RELEASE, python="3.13") -> str:
            return projects.key(projects.find(script), engine, python)

        first = key()
        self.assertEqual(key(), first, "stable")
        self.assertRegex(first, r"^[0-9a-f]{16}$")
        changed = {"python": key(python="3.12"),
                   "installation": key(projects.Engine("0.8.3", "0.8.3-dev.20261028", "3.13", None, "arm64")),
                   "source": key(projects.Engine("0.8.3", "0.8.3", "3.13", str(self.root), "arm64")),
                   "arch": key(projects.Engine("0.8.3", "0.8.3", "3.13", None, "x86_64"))}
        for name, text in (("requirements.txt", "six==1.17.0\n"), ("pyproject.toml", '[project]\nname = "k"\nversion = "2"\n'),
                           ("uv.lock", "version = 2\n")):
            before = (self.root / "k" / name).read_text(encoding="utf-8")
            self.write(f"k/{name}", text)
            changed[name] = key()
            self.write(f"k/{name}", before)
        self.assertEqual(key(), first)
        self.write("k/model.py", "# /// script\n# dependencies = ['six']\n# ///\n")
        changed["inline"] = key()
        self.write("k/model.py", "# /// script\n# dependencies = ['six']\n# ///\nprint('the code is no input')\n")
        self.assertEqual(key(), changed["inline"], "the script's code is not an input; its inline block is")
        self.assertEqual(len({first, *changed.values()}), len(changed) + 1, changed)

    def test_folders_that_declare_nothing_share_an_environment_and_projects_never(self) -> None:
        one, two = self.write("a/model.py"), self.write("b/model.py")
        self.assertEqual(projects.key(projects.find(one), RELEASE, "3.13"), projects.key(projects.find(two), RELEASE, "3.13"))
        self.write("a/requirements.txt", "six\n")
        self.write("b/requirements.txt", "six\n")
        self.assertNotEqual(projects.key(projects.find(one), RELEASE, "3.13"), projects.key(projects.find(two), RELEASE, "3.13"),
                            "a project's environment names its folder (its editable install, its relative paths)")
        self.assertEqual(projects.environment(projects.find(one), RELEASE, "3.13").parent, self.root / "cache" / "envs")


class Making(Fixture):
    def test_the_uv_commands_for_a_release_and_for_a_source(self) -> None:
        script = self.write("cmd/model.py", "# /// script\n# dependencies = ['six']\n# ///\n")
        self.write("cmd/requirements.txt", "numpy\n")
        self.write("cmd/pyproject.toml", '[build-system]\nrequires = ["setuptools"]\n[project]\nname = "c"\nversion = "1"\n')
        project = projects.find(script)
        env = self.root / "cache/envs/k"
        python = str(projects.interpreter(env))
        venv, install = projects.commands("uv", env, "3.12", RELEASE, project)
        self.assertEqual(venv, ["uv", "venv", "--no-project", "--managed-python", "--python", "3.12", str(env)])
        self.assertEqual(install, ["uv", "pip", "install", "--python", python, "--link-mode", "hardlink",
                                   "--override", str(env / projects.OVERRIDE), "cadgen==0.8.3",
                                   "-r", str(self.root / "cmd/requirements.txt"), "-e", str(self.root / "cmd"), "six"])
        tree = projects.Engine("0.8.3", "0.8.3-dev.1", "3.13", str(self.root))
        self.assertEqual(projects.commands("uv", env, "3.12", tree, project)[1][9:11], ["-e", str(self.root)])
        wheel = self.write("dist/cadgen-0.8.3-py3-none-any.whl")
        built = projects.Engine("0.8.3", "0.8.3-dev.1", "3.13", str(wheel))
        self.assertEqual(projects.commands("uv", env, "3.12", built, project)[1][9], str(wheel))

    def test_an_environment_is_made_once_and_taken_from_its_marker_after(self) -> None:
        log = self.fake_uv()
        script = self.write("once/model.py")
        self.write("once/requirements.txt", "six\n")
        said: list[str] = []
        env = projects.ensure(projects.find(script), RELEASE, "3.13", told=said.append)
        key = projects.key(projects.find(script), RELEASE, "3.13")
        self.assertEqual(env, self.root / "cache" / "envs" / key)
        self.assertEqual([call[:2] for call in self.calls(log)], [["venv", "--no-project"], ["pip", "install"]])
        self.assertEqual(len(said), 1)
        self.assertIn("making this project's environment, once: Python 3.13, cadgen 0.8.3", said[0])
        marker = json.loads((env / projects.MARKER).read_text(encoding="utf-8"))
        self.assertEqual((marker["schema"], marker["key"], marker["release"]), (projects.SCHEMA, key, "0.8.3"))
        self.assertEqual(marker["inputs"], projects.inputs(projects.find(script), RELEASE, "3.13"))
        self.assertEqual((marker["inputs"]["python"], marker["inputs"]["root"]), ("3.13", str(self.root / "once")))
        self.assertEqual([call[1:] for call in marker["commands"]], self.calls(log))
        self.assertTrue(projects.complete(env, key))
        # Unchanged: taken from its marker, uv not asked.
        self.assertEqual(projects.ensure(projects.find(script), RELEASE, "3.13", told=said.append), env)
        self.assertEqual(len(self.calls(log)), 2)
        self.assertEqual(len(said), 1)
        # A dependency changed: another environment.
        self.write("once/requirements.txt", "six==1.17.0\n")
        other = projects.ensure(projects.find(script), RELEASE, "3.13", told=said.append)
        self.assertNotEqual(other, env)
        self.assertEqual(len(self.calls(log)), 4)
        self.assertTrue(projects.complete(env, key), "the old one is left as it was")

    def test_the_engines_cadgen_takes_the_place_of_any_cadgen_the_project_names(self) -> None:
        log = self.fake_uv()
        script = self.write("own/model.py", "# /// script\n# dependencies = ['cadgen>=0.8']\n# ///\n")
        self.write("own/requirements.txt", "six\ncadgen==0.8.2  # the one it was written against\n-r more.txt\ncadgen\n")
        self.write("own/pyproject.toml", '[project]\nname = "own"\nversion = "1"\ndependencies = ["CadGen[x]<0.8", "cad_gen"]\n')
        project = projects.find(script)
        self.assertEqual(projects.declared(project), ["cadgen==0.8.2", "CadGen[x]<0.8", "cadgen>=0.8"],
                         "as written, a bare cadgen aside (the engine's satisfies it), cad_gen another name")
        said: list[str] = []
        env = projects.ensure(project, RELEASE, "3.13", told=said.append)
        self.assertEqual(said[1], "the project's own cadgen==0.8.2 and CadGen[x]<0.8 and cadgen>=0.8 gives way to the "
                                  "engine's cadgen 0.8.3")
        self.assertEqual((env / projects.OVERRIDE).read_text(encoding="utf-8"), "cadgen==0.8.3\n")
        # A source stands in place of every requirement on cadgen as itself: a tree editable, a wheel by its URL.
        tree = projects.Engine("0.8.3", "0.8.3-dev.1", "3.13", str(self.root))
        self.assertEqual(tree.override(), f"-e {self.root.as_uri()}")
        wheel = self.write("dist/cadgen-0.8.3-py3-none-any.whl")
        self.assertEqual(projects.Engine("0.8.3", "0.8.3-dev.1", "3.13", str(wheel)).override(),
                         f"cadgen @ {wheel.as_uri()}")
        install = self.calls(log)[1]
        self.assertEqual(install[install.index("--override") + 1], str(env / projects.OVERRIDE))
        self.assertEqual(projects.declared(projects.find(self.write("bare/model.py"))), [])

    def test_an_incomplete_environment_is_made_again_and_refresh_makes_it_again(self) -> None:
        log = self.fake_uv()
        script = self.write("again/model.py")
        project = projects.find(script)
        env = projects.environment(project, RELEASE, "3.13")
        (env / "lib").mkdir(parents=True)
        (env / "lib" / "half-installed").write_text("", encoding="utf-8")
        self.assertFalse(projects.complete(env, env.name))
        self.assertEqual(projects.ensure(project, RELEASE, "3.13", told=lambda _line: None), env)
        self.assertFalse((env / "lib" / "half-installed").exists(), "what was there is removed first")
        self.assertEqual(len(self.calls(log)), 2)
        (env / "made-before").write_text("", encoding="utf-8")
        self.assertEqual(projects.ensure(project, RELEASE, "3.13", refresh=True, told=lambda _line: None), env)
        self.assertFalse((env / "made-before").exists())
        self.assertEqual(len(self.calls(log)), 4)
        self.assertTrue(projects.complete(env, env.name))
        # A marker of another key, or none, is no complete environment.
        (env / projects.MARKER).write_text(json.dumps({"schema": projects.SCHEMA, "key": "other"}), encoding="utf-8")
        self.assertFalse(projects.complete(env, env.name))

    def test_a_removal_a_scanner_holds_up_goes_on_after_a_wait_and_any_other_failure_is_said(self) -> None:
        env = self.root / "cache/envs/held"
        (env / "bin").mkdir(parents=True)
        held = PermissionError(13, "in use")
        held.winerror = 32  # what Windows says of a file another process has open
        real, calls = projects.shutil.rmtree, []

        def rmtree(path, *args, **kwargs):
            calls.append(path)
            if len(calls) == 1:
                raise held
            real(path, *args, **kwargs)

        with mock.patch.object(projects.shutil, "rmtree", side_effect=rmtree), \
                mock.patch.object(projects.time, "sleep") as slept:
            projects._remove(env)
        self.assertFalse(env.exists())
        self.assertEqual((len(calls), slept.call_args_list), (2, [mock.call(projects.REMOVE_DELAYS[0])]))
        env.mkdir(parents=True)
        with mock.patch.object(projects.shutil, "rmtree", side_effect=OSError(16, "Resource busy")), \
                mock.patch.object(projects.time, "sleep") as slept, self.assertRaises(projects.Refused) as refused:
            projects._remove(env)
        slept.assert_not_called()
        self.assertEqual(str(refused.exception), f"cannot remove the environment at {env} to make it again: Resource busy")

    def test_a_sandbox_that_denies_the_cache_folder_is_said_as_one(self) -> None:
        # A complete environment's run reads alone; making one writes the cache folder, which a sandbox
        # that forbids writing outside its own refuses.
        project = projects.find(self.write("boxed/model.py"))
        denied = PermissionError(1, "Operation not permitted")
        with mock.patch.object(Path, "mkdir", side_effect=denied), self.assertRaises(projects.Refused) as refused:
            projects.ensure(project, RELEASE, "3.13", told=lambda _line: None)
        self.assertEqual(str(refused.exception), f"the system denies cadgen the environments' folder "
                                                 f"{self.root / 'cache' / 'envs'} (Operation not permitted); a sandbox "
                                                 "that forbids it does: run this once outside it, or with its permission")
        import cadgen.engine.file_lock as file_lock

        with mock.patch.object(file_lock, "exclusive", side_effect=denied), self.assertRaises(projects.Refused) as refused:
            projects.ensure(project, RELEASE, "3.13", told=lambda _line: None)
        self.assertIn("the system denies cadgen the environments' folder", str(refused.exception))

    def test_what_uv_could_not_do_is_said_in_one_line(self) -> None:
        log = self.fake_uv()
        script = self.write("fails/model.py")
        self.write("fails/requirements.txt", "build123d==0.1\n")
        project = projects.find(script)
        cases = (
            ("pip", CONFLICT, "the project's dependencies conflict with cadgen 0.8.3"),
            ("pip", OFFLINE, "the project's environment needs the network once: Failed to fetch: "
                             "`https://pypi.org/simple/six/` (Connection refused (os error 61))"),
            ("venv", NO_PYTHON, "uv cannot provide Python 3.13 for this project's environment: No interpreter found for "
                                "Python 3.12.1 in managed installations (hint: A managed Python download is available "
                                "for Python 3.12.1, but Python downloads are set to 'never')"),
            ("venv", DENIED, "the system denies uv what the project's environment needs (Failed to initialize cache at "
                             "`/Users/me/.cache/uv` (failed to create directory `/Users/me/.cache/uv`: Operation not "
                             "permitted (os error 1))); a sandbox that forbids it does: run this once outside it, or with "
                             "its permission"),
            ("pip", "error: Distribution not found at: file:///nowhere\n",
             "uv could not make this project's environment: Distribution not found at: file:///nowhere"),
        )
        for step, said, words in cases:
            with self.subTest(step=step, words=words), \
                    mock.patch.dict(os.environ, {"FAKE_UV_FAIL": step, "FAKE_UV_SAID": said}):
                with self.assertRaises(projects.Refused) as refused:
                    projects.ensure(project, RELEASE, "3.13", told=lambda _line: None)
                line = str(refused.exception)
                self.assertTrue(line.startswith(words), line)
                self.assertNotIn("\n", line)
                self.assertFalse(projects.complete(projects.environment(project, RELEASE, "3.13"), "x"))
        self.assertTrue(self.calls(log))
        conflict = projects.failure(["uv", "pip", "install"], CONFLICT, RELEASE, "3.13")
        self.assertIn("; the project pins build123d==0.1 (uv: Because cadgen==0.8.3 depends on build123d>=0.13.0,<0.14 "
                      "and you require cadgen==0.8.3, we can conclude", conflict)
        with mock.patch.object(projects, "_kernel", return_value="build123d>=0.13.0,<0.14 and cadquery-ocp-novtk>=8.0,<8.1"):
            self.assertTrue(projects.failure(["uv", "pip", "install"], CONFLICT, RELEASE, "3.13").startswith(
                "the project's dependencies conflict with cadgen 0.8.3: cadgen 0.8.3 needs build123d>=0.13.0,<0.14 and "
                "cadquery-ocp-novtk>=8.0,<8.1; the project pins build123d==0.1 (uv: "))

    def test_an_index_page_from_before_the_release_is_fetched_again_once(self) -> None:
        log = self.fake_uv()
        project = projects.find(self.write("fresh/model.py"))
        unlisted = ("  × No solution found when resolving dependencies:\n  ╰─▶ Because there is no version of\n"
                    "      cadgen==0.8.3 and you require cadgen==0.8.3, we can conclude that your\n"
                    "      requirements are unsatisfiable.\n")
        with mock.patch.dict(os.environ, {"FAKE_UV_FAIL": "pip", "FAKE_UV_SAID": unlisted,
                                          "FAKE_UV_FAIL_UNLESS": "--refresh-package"}):
            env = projects.ensure(project, RELEASE, "3.13", told=lambda _line: None)
        calls = self.calls(log)
        self.assertEqual([call[:2] for call in calls], [["venv", "--no-project"], ["pip", "install"], ["pip", "install"]])
        self.assertEqual(calls[2], [*calls[1], "--refresh-package", "cadgen"])
        marker = json.loads((env / projects.MARKER).read_text(encoding="utf-8"))
        self.assertEqual(marker["commands"][1][-2:], ["--refresh-package", "cadgen"])
        with mock.patch.dict(os.environ, {"FAKE_UV_FAIL": "pip", "FAKE_UV_SAID": unlisted}), \
                self.assertRaises(projects.Refused) as refused:
            projects.ensure(project, RELEASE, "3.13", refresh=True, told=lambda _line: None)
        self.assertEqual(str(refused.exception), "cadgen 0.8.3, the engine's, is on no package index uv reads: Because "
                                                 "there is no version of cadgen==0.8.3 and you require cadgen==0.8.3, we "
                                                 "can conclude that your requirements are unsatisfiable.")
        self.assertEqual(len(self.calls(log)), 6, "asked once more, never again")

    def test_uv_is_the_one_on_path_else_the_one_cadgen_depends_on(self) -> None:
        self.fake_uv()
        self.assertEqual(Path(projects.find_uv()).parent, self.root / "fake-bin")
        with mock.patch.object(projects.shutil, "which", return_value=None):
            found = projects.find_uv()
            self.assertTrue(Path(found).is_file(), found)
            with mock.patch.dict(sys.modules, {"uv": None}), self.assertRaises(projects.Refused) as refused:
                projects.find_uv()
        self.assertIn("cadgen depends on the uv package", str(refused.exception))


if __name__ == "__main__":
    unittest.main()
