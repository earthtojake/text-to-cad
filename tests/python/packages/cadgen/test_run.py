"""``cadgen run SCRIPT.py``: a model built in its project's environment, end to end, with the real uv.

The engine is this file's own (``engine_daemon.isolate``, started by nothing but ``cadgen run``). Each
project's environment is made by uv in this file's cache folder from this checkout's cadgen, editable
(the engine runs from a source tree: its hello names it), and the project's requirements; uv is
reached through a wrapper first on PATH that counts what it is asked. The fake-uv contracts (keys,
markers, commands, messages) are test_projects.py's.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support import engine_daemon
from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen import cli  # noqa: E402
from cadgen.cli import run  # noqa: E402
from cadgen.engine import client  # noqa: E402

MODEL = """\
import json
import sys

import build123d as bd
from cadgen import xbf
{imports}

@xbf("XBF/part.xbf")
def part():
    return bd.Box(4, 5, 6)


if __name__ == "__main__":
    part()
    print("RESULT " + json.dumps({{"prefix": sys.prefix, "python": "%d.%d" % sys.version_info[:2], "argv": sys.argv[1:],
                                  "six": {six}}}))
"""


def setUpModule() -> None:
    engine_daemon.isolate(unittest.addModuleCleanup, start=False)


class Arguments(unittest.TestCase):
    def test_the_commands_options_come_before_the_script_and_the_rest_is_the_scripts(self) -> None:
        cases = {("--port", "3600", "--refresh", "model.py", "--port", "5", "-h"): (3600, True, False, ["--port", "5", "-h"]),
                 ("--show-env", "model.py"): (None, False, True, []),
                 ("model.py", "--show-env", "--", "x"): (None, False, False, ["--show-env", "--", "x"]),
                 ("--port=7", "model.py", "a"): (7, False, False, ["a"])}
        for argv, (port, refresh, show, rest) in cases.items():
            with self.subTest(argv=argv):
                own, after = run._split(list(argv))
                parsed = run.build_parser().parse_args(own)
                self.assertEqual((parsed.port, parsed.refresh, parsed.show_env, parsed.script, after),
                                 (port, refresh, show, "model.py", rest))

    def test_a_missing_script_or_one_that_is_no_python_is_refused_before_any_engine(self) -> None:
        folder = Path(tempfile.mkdtemp(prefix="cadgen-run-args-"))
        self.addCleanup(shutil.rmtree, folder, True)
        (folder / "notes.txt").write_text("", encoding="utf-8")
        (folder / "model.py").write_text("", encoding="utf-8")
        for argv, said in ((["run", str(folder / "missing.py")], f"cadgen run: no script {folder / 'missing.py'}"),
                           (["run", str(folder / "notes.txt")],
                            f"cadgen run: {folder / 'notes.txt'} is not a Python script (.py)"),
                           (["run", "--port", "0", str(folder / "model.py")],
                            "cadgen run: --port must be between 1 and 65535")):
            with self.subTest(argv=argv), mock.patch.object(client, "connect") as connect:
                err = io.StringIO()
                with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                    code = cli.main(argv)
                self.assertEqual((code, err.getvalue().strip()), (2, said))
                connect.assert_not_called()


class RunTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="cadgen-run-")).resolve()
        self.addCleanup(shutil.rmtree, self.root, True)
        real = shutil.which("uv")
        if real is None:
            from uv import find_uv_bin  # cadgen's own dependency

            real = find_uv_bin()
        # A uv first on PATH that writes a line of what it is asked, then runs the real one.
        bin_folder, self.log = self.root / "bin", self.root / "uv.log"
        bin_folder.mkdir()
        if os.name == "nt":
            (bin_folder / "uv.bat").write_text(f'@echo off\r\necho %*>>"{self.log}"\r\n"{real}" %*\r\n'
                                               "exit /b %errorlevel%\r\n", encoding="utf-8")
        else:
            wrapper = bin_folder / "uv"
            wrapper.write_text(f"#!/bin/sh\necho \"$*\" >> '{self.log}'\nexec '{real}' \"$@\"\n", encoding="utf-8")
            wrapper.chmod(0o755)
        self.env = engine_daemon.watched({**os.environ, "PATH": os.pathsep.join((str(bin_folder), os.environ["PATH"])),
                                          "CADGEN_VIEWER_WARM": "0"}, self.addCleanup)

    def project(self, name: str, files: dict[str, str], *, six: bool = True) -> Path:
        folder = self.root / name
        folder.mkdir()
        (folder / "model.py").write_text(MODEL.format(imports="import six" if six else "",
                                                      six="six.__version__" if six else "None"), encoding="utf-8")
        for relative, text in files.items():
            (folder / relative).write_text(textwrap.dedent(text), encoding="utf-8")
        return folder

    def run_cli(self, *args: str, cwd: Path):
        return engine_daemon.run([sys.executable, "-m", "cadgen.cli", *args], env=self.env, cwd=str(cwd))

    def asked(self) -> list[str]:
        """What uv was asked, a subcommand a call: ``venv`` or ``pip``."""
        return [line.split()[0] for line in self.log.read_text(encoding="utf-8").splitlines()] if self.log.exists() else []

    @staticmethod
    def result(done) -> dict:
        lines = [line for line in done.stdout.splitlines() if line.startswith("RESULT ")]
        assert len(lines) == 1, (done.stdout, done.stderr)
        return json.loads(lines[0][len("RESULT "):])

    def test_a_model_builds_in_its_projects_environment_made_once(self) -> None:
        if client.request({"op": "stop"}, start=False):  # one another test's run started
            self.assertTrue(client.wait_gone())
        self.assertIsNone(client.request({"op": "status"}, start=False), "no engine runs: cadgen run starts it")
        # The project names cadgen itself, as one written against an older release does: the engine's takes its place.
        project = self.project("robot", {"requirements.txt": "six\ncadgen==0.8.2\n"})
        first = self.run_cli("run", "model.py", "--size", "2", cwd=project)
        self.assertEqual(first.returncode, 0, first.stderr)
        found = self.result(first)
        env = Path(found["prefix"]).resolve()
        self.assertEqual(env.parent, Path(os.environ["CADGEN_CACHE_DIR"]).resolve() / "envs")
        self.assertEqual(found["argv"], ["--size", "2"], "the script's own arguments, as python passes them")
        self.assertTrue(found["six"], "the project's requirement is installed")
        self.assertIn("making this project's environment, once", first.stderr)
        self.assertIn("the project's own cadgen==0.8.2 gives way to the engine's cadgen ", first.stderr)
        self.assertIn("id: ", first.stdout)
        self.assertEqual(self.asked(), ["venv", "pip"])
        status = client.request({"op": "status"}, start=False)
        self.assertIsNotNone(status, "cadgen run started the engine")
        self.assertIn(env, [Path(row["prefix"]).resolve() for row in status["workers"]],
                      "the engine's worker runs in the project's environment")

        shown = self.run_cli("run", "--show-env", "model.py", cwd=project)
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertEqual(Path(shown.stdout.strip()).resolve(), env)
        again = self.run_cli("run", "model.py", cwd=project)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(Path(self.result(again)["prefix"]).resolve(), env)
        self.assertNotIn("making", again.stderr)
        self.assertEqual(self.asked(), ["venv", "pip"], "an unchanged project resolves nothing")

        # --refresh makes it again, never under the engine's worker that runs in it.
        refused = self.run_cli("run", "--refresh", "model.py", cwd=project)
        self.assertEqual(refused.returncode, 1)
        self.assertEqual(refused.stderr.strip().splitlines()[-1],
                         f"cadgen run: the engine on port {os.environ['CADGEN_PORT']} runs model.py in this project's "
                         f"environment: run `cadgen stop --port {os.environ['CADGEN_PORT']}`, then "
                         "`cadgen run --refresh model.py`")
        self.assertEqual(self.asked(), ["venv", "pip"])
        stopped = self.run_cli("stop", cwd=project)
        self.assertEqual(stopped.returncode, 0, stopped.stderr)
        refreshed = self.run_cli("run", "--refresh", "model.py", cwd=project)
        self.assertEqual(refreshed.returncode, 0, refreshed.stderr)
        self.assertEqual(Path(self.result(refreshed)["prefix"]).resolve(), env)
        self.assertEqual(self.asked(), ["venv", "pip", "venv", "pip"])

    def test_a_pin_against_cadgens_kernel_is_refused_in_one_line(self) -> None:
        project = self.project("pinned", {"requirements.txt": "build123d==0.12.0\n"})
        done = self.run_cli("run", "model.py", cwd=project)
        self.assertEqual((done.returncode, done.stdout), (1, ""), done.stderr)
        line = done.stderr.strip().splitlines()[-1]
        self.assertTrue(line.startswith("cadgen run: the project's dependencies conflict with cadgen "), line)
        self.assertIn("; the project pins build123d==0.12.0 (uv: ", line)
        self.assertEqual(self.asked(), ["venv", "pip"])

    def test_a_project_on_python_3_14(self) -> None:
        project = self.project("newest", {".python-version": "3.14\n"}, six=False)
        done = self.run_cli("run", "model.py", cwd=project)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.result(done)["python"], "3.14")
        self.assertIn("id: ", done.stdout)

    def test_cad_run_builds_a_project_through_the_engine_from_the_cad_app(self) -> None:
        """The CAD app's ``cad_run``: the engine runs ``cadgen run`` of the script itself, with its own
        installation and the project's environment, and the operation's result carries the run's output
        and the script's documents (``cadgen.mcp.runs``)."""
        from cadgen.jobs import TERMINAL
        from cadgen.mcp.operations import Operations

        project = self.project("app", {}, six=False)
        jobs = Operations()
        with mock.patch.dict(os.environ, self.env):  # the counting uv first on PATH, the viewer unwarmed
            answer = jobs.call("cad_run", {"requestId": "cad-run-request-0001", "script": str(project / "model.py"),
                                           "args": ["--size", "3"]})
            self.assertEqual(answer["state"], "queued", answer)
            with jobs.changed:
                self.assertTrue(jobs.changed.wait_for(lambda: jobs.jobs[answer["id"]]["state"] in TERMINAL, timeout=600))
            done = jobs.get(answer["id"])
        self.assertEqual(done["state"], "succeeded", done.get("error"))
        result = done["result"]
        lines = [line for line in result["output"].splitlines() if line.startswith("RESULT ")]
        self.assertEqual(len(lines), 1, result["output"])
        found = json.loads(lines[0][len("RESULT "):])
        self.assertEqual(found["argv"], ["--size", "3"], "the script's own arguments")
        self.assertEqual(Path(found["prefix"]).resolve().parent, Path(os.environ["CADGEN_CACHE_DIR"]).resolve() / "envs",
                         "the script ran in its project's environment, as cadgen run runs it")
        self.assertIn("id: ", result["output"])
        self.assertEqual([document["name"] for document in result["documents"]], ["part"])
        self.assertEqual(done["progress"]["kind"], "run")
        self.assertIsNotNone(client.request({"op": "status"}, start=False), "the run started the engine as cadgen run does")


if __name__ == "__main__":
    unittest.main()
