"""The base (``cadgen._internal.base``): the one environment, ``cadgen[kernel]`` at the installation's
release on its Python, made once and reused; an installation that carries the kernel is its own; and
``cadgen run`` runs the script with its Python.

uv is stood in for (``Fake``): each step it is asked is recorded, ``venv`` makes the environment's
Python as a file, ``pip`` answers what the test gives it. The real uv, a model built in the base and
the engine's kernel processes there are test_environments.py's.
"""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal import base  # noqa: E402
from cadgen.cli import run  # noqa: E402

RELEASE = "9.9.9"


class Fake:
    """uv as the tests see it: each step recorded; ``venv`` makes the environment's Python (a file);
    ``pip`` answers the next of ``answers`` (``(code, stderr)``), else succeeds."""

    def __init__(self, *answers: tuple[int, str]) -> None:
        self.steps: list[list[str]] = []
        self.answers = list(answers)

    def __call__(self, step: list[str], folder: Path) -> subprocess.CompletedProcess:
        self.steps.append(list(step))
        if step[1] == "venv":
            python = base.interpreter(Path(step[-1]))
            python.parent.mkdir(parents=True)
            python.write_text("", encoding="utf-8")
            return subprocess.CompletedProcess(step, 0, "", "")
        code, said = self.answers.pop(0) if self.answers else (0, "")
        return subprocess.CompletedProcess(step, code, "", said)

    def asked(self) -> list[str]:
        """Each step as uv's subcommand, ``pip`` asked offline as ``pip --offline``."""
        return [step[1] + (" --offline" if "--offline" in step else "") for step in self.steps]


class BaseTest(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory(prefix="cadgen-base-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        cache = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / "cache")})
        cache.start()
        self.addCleanup(cache.stop)
        self.core = self.root / "core"
        # A release installed from the index with its core alone, as uvx installs the plugin's server.
        self.installation = base.Installation(
            release=RELEASE, name=RELEASE, python="3.14.2", executable=str(base.interpreter(self.core)),
            prefix=str(self.core), root=str(self.core / "site-packages"), source=None, arch="arm64", kernel=False)
        self.said: list[str] = []
        self.path = ["/stdlib", "/the-base/site-packages"]

    def made(self, fake: Fake) -> contextlib.ExitStack:
        """``base`` with ``fake`` for uv and the base's import path known."""
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(base, "_uv", fake))
        stack.enter_context(mock.patch.object(base, "find_uv", return_value="uv"))
        stack.enter_context(mock.patch.object(base, "_path", return_value=self.path))
        return stack

    def test_the_base_is_made_once_with_the_kernel_and_reused_after(self) -> None:
        fake = Fake()
        with self.made(fake):
            self.assertIsNone(base.ensure(self.installation, make=False), "not made, and not made by asking")
            found = base.ensure(self.installation, told=self.said.append)
            again = base.ensure(self.installation, told=self.said.append)
        self.assertEqual(found, again)
        env = Path(found.prefix)
        self.assertEqual(env, base.where(self.installation))
        self.assertEqual(env.parent, self.root / "cache" / base.BASE)
        self.assertEqual((found.python, found.own, found.path), (str(base.interpreter(env)), False, tuple(self.path)))
        self.assertEqual(fake.asked(), ["venv", "pip --offline"], "made once, from uv's cache: nothing asked again")
        venv, pip = fake.steps
        self.assertEqual(venv, ["uv", "venv", "--no-project", "--python", self.installation.executable, str(env)],
                         "on the installation's own Python")
        self.assertEqual(pip, ["uv", "pip", "install", "--python", str(base.interpreter(env)), "--link-mode",
                               "hardlink", f"cadgen[kernel]=={RELEASE}", "--offline"])
        self.assertEqual(self.said, [f"making the CAD kernel environment, once: cadgen[kernel] {RELEASE} on Python "
                                     f"3.14.2, in {env}"])
        # Its marker names the installation it belongs to: a process there reaches that engine.
        home = base.home(str(env))
        self.assertEqual((home["executable"], home["prefix"], home["root"]),
                         (self.installation.executable, self.installation.prefix, self.installation.root))
        self.assertIsNone(base.home(str(self.core)), "an environment no marker names is its own installation")

    def test_the_network_is_asked_only_for_what_uvs_cache_lacks_and_said_first(self) -> None:
        fake = Fake((2, "error: Network connectivity is disabled, but the requested data wasn't found in the cache"))
        with self.made(fake):
            base.ensure(self.installation, told=self.said.append)
        self.assertEqual(fake.asked(), ["venv", "pip --offline", "pip"])
        self.assertEqual(self.said[1], "downloading the CAD kernel (about 220 MB) and what it needs, once")

    def test_a_base_that_cannot_be_made_is_refused_in_one_line(self) -> None:
        offline = "error: Failed to fetch: `https://pypi.org/simple/build123d/`\n  Caused by: dns error: failed to lookup address"
        fake = Fake((2, offline), (2, offline))
        with self.made(fake), self.assertRaises(base.Refused) as refused:
            base.ensure(self.installation, told=self.said.append)
        self.assertEqual(str(refused.exception), "the CAD kernel environment needs the network once: Failed to fetch: "
                                                 "`https://pypi.org/simple/build123d/` (dns error: failed to lookup address)")
        self.assertIsNone(base.complete(base.where(self.installation)), "no marker: the next use makes it again")

    def test_an_installation_that_carries_the_kernel_is_its_own_base(self) -> None:
        own = base.Installation(**{**base.dataclasses.asdict(self.installation), "kernel": True})
        fake = Fake()
        with self.made(fake):
            found = base.ensure(own)
        self.assertEqual(found, base.Environment(own.executable, own.prefix, True))
        self.assertEqual(fake.steps, [])

    def test_where_the_installation_installs_from(self) -> None:
        tree = self.root / "checkout"
        tree.mkdir()
        wheel = "file:///wheels/cadgen-9.9.9-py3-none-any.whl"
        for source, requirement in ((None, [f"cadgen[kernel]=={RELEASE}"]), (str(tree), ["-e", f"{tree}[kernel]"]),
                                    (wheel, [f"cadgen[kernel] @ {wheel}"])):
            with self.subTest(source=source):
                found = base.Installation(**{**base.dataclasses.asdict(self.installation), "source": source})
                self.assertEqual(found.requirement(), requirement)


class RunTest(unittest.TestCase):
    """``cadgen run``: the arguments run by the base's Python, in the caller's folder."""

    def test_the_script_runs_with_the_bases_python(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / "model.py"
            script.write_text("", encoding="utf-8")
            with mock.patch.object(run.os, "execv") as execv, mock.patch("subprocess.call", return_value=0) as call:
                self.assertEqual(run.main([str(script), "--size", "2"]), 1 if os.name != "nt" else 0)
        found = base.ensure(make=False)
        command = [found.python, str(script), "--size", "2"]
        if os.name == "nt":
            call.assert_called_once_with(command)
        else:
            execv.assert_called_once_with(found.python, command)

    def test_a_base_that_cannot_be_made_runs_nothing_and_says_why(self) -> None:
        err = io.StringIO()
        with mock.patch.object(base, "ensure", side_effect=base.Refused("the CAD kernel environment needs the network "
                                                                        "once: dns error")), \
                mock.patch.object(run.os, "execv") as execv, contextlib.redirect_stderr(err):
            self.assertEqual(run.main(["model.py"]), 1)
        execv.assert_not_called()
        self.assertEqual(err.getvalue(), "cadgen run: the CAD kernel environment needs the network once: dns error\n")


class SpawnTest(unittest.TestCase):
    """The engine's spawn pools in the base (``cadgen.engine.serve._spawn_in``): on Windows their processes
    run the base by its real interpreter, which its ``pyvenv.cfg`` names, never through the venv's
    launcher (the pool's handles would go to the launcher)."""

    def test_the_real_interpreter_behind_a_virtual_environment(self) -> None:
        from cadgen.engine import serve

        with tempfile.TemporaryDirectory(prefix="cadgen-venv-") as scratch:
            root = Path(scratch)
            home = root / "python"
            home.mkdir()
            (home / "python.exe").write_bytes(b"")
            venv = root / "base"
            (venv / "Scripts").mkdir(parents=True)
            launcher = venv / "Scripts" / "python.exe"
            launcher.write_bytes(b"")
            self.assertIsNone(serve._venv_interpreter(str(launcher)), "no pyvenv.cfg: no virtual environment")
            (venv / "pyvenv.cfg").write_text(f"home = {home}\nimplementation = CPython\n", encoding="utf-8")
            self.assertEqual(serve._venv_interpreter(str(launcher)), str(home / "python.exe"))
            (home / "python.exe").unlink()
            self.assertIsNone(serve._venv_interpreter(str(launcher)), "a home with no interpreter")


if __name__ == "__main__":
    unittest.main()
