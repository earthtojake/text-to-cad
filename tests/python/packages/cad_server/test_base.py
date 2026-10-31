"""The base (``cad_server._internal.base``): the one environment, ``texttocad[build123d]`` at the installation's
release on its Python, made once and reused; an installation that carries the kernel is its own; and
``cad run`` runs the script with its Python.

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
import threading
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/texttocad/src")

from cad_server._internal import base  # noqa: E402
from cad.engine import places  # noqa: E402
from cad_server.cli import run  # noqa: E402

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
        cache = mock.patch.dict(os.environ, {"CAD_CACHE_DIR": str(self.root / "cache")})
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
                               "hardlink", f"texttocad[build123d]=={RELEASE}", "--offline"])
        self.assertEqual(self.said, [f"making the CAD kernel environment, once: texttocad[build123d] {RELEASE} on Python "
                                     f"3.14.2, in {env}"])
        # Its marker names the installation it belongs to: a process there reaches that engine.
        home = places.home(str(env))
        self.assertEqual((home["executable"], home["prefix"], home["root"]),
                         (self.installation.executable, self.installation.prefix, self.installation.root))
        self.assertIsNone(places.home(str(self.core)), "an environment no marker names is its own installation")

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

    def test_the_engine_makes_its_base_in_the_background_and_a_follower_hears_its_lines(self) -> None:
        # The engine that finds no base makes it (``Making``), outside the sandbox an agent's command runs in:
        # whoever asks for it follows the making from its first line, and the engine is told once it is made
        # (``made``: its standby stands then). Its start at the engine's own start is test_daemon's.
        fake, making, made = Fake(), base.Making(), threading.Event()
        making.made = made.set
        heard: list[str] = []
        with self.made(fake), mock.patch.object(base.Installation, "here", return_value=self.installation), \
                contextlib.redirect_stderr(io.StringIO()) as log:
            self.assertEqual(making.key(), base.where(self.installation).name)
            self.assertIsNone(making.follow(heard.append), "absent: made now, and followed from its first line")
            self.assertTrue(made.wait(30))
            self.assertFalse(making.start(), "made: nothing to make again")
            self.assertIsNone(making.follow(heard.append), "made: nothing more to hear")
        env = base.where(self.installation)
        self.assertIsNotNone(base.complete(env))
        line = f"making the CAD kernel environment, once: texttocad[build123d] {RELEASE} on Python 3.14.2, in {env}"
        self.assertEqual(heard, [line])
        self.assertEqual(log.getvalue(), f"cad: {line}\n", "the engine's log")
        self.assertEqual(fake.asked(), ["venv", "pip --offline"])
        self.assertEqual(making.status()["state"], "made")

    def test_cad_run_has_the_device_s_engine_make_the_base_and_hears_its_making(self) -> None:
        # A sandboxed `cad run` cannot write the cache folder: the engine, which a host's CAD app started
        # outside the sandbox, makes the base, and the command says each line of it as it comes.
        from cad.engine import client

        env = base.where(self.installation)
        engine_uv, own_uv, asked = Fake(), Fake(), []

        def engine(answer):
            def request(message, on_log=lambda _frame: None, *, start=True, on_progress=None):
                asked.append((message, start))
                on_log({"log": "making the CAD kernel environment, once"})
                if answer.get("ok"):
                    with mock.patch.object(base, "_uv", engine_uv):
                        base.ensure(self.installation, told=lambda _line: None)
                return answer
            return request

        with self.made(own_uv), mock.patch.object(client, "request", side_effect=engine({"ok": True, "base": True})):
            found = base.ensure(self.installation, told=self.said.append, engine=True)
        self.assertEqual(asked, [({"op": "base", "key": env.name}, False)], "a running engine, never one started")
        self.assertEqual((found.prefix, own_uv.steps), (str(env), []), "made by the engine, not here")
        self.assertEqual(self.said, ["making the CAD kernel environment, once"])
        refused = {"failed": "the CAD kernel environment needs the network once: dns error", "base": True}
        with self.made(own_uv), mock.patch.object(client, "request", side_effect=engine(refused)), \
                mock.patch.object(base, "where", return_value=self.root / "cache" / base.BASE / "another"), \
                self.assertRaisesRegex(base.Refused, "^the CAD kernel environment needs the network once: dns error$"):
            base.ensure(self.installation, told=self.said.append, engine=True)
        # No engine running, one of another installation's, one that makes no base: the command makes it.
        for answer in (None, {"ok": False, "other": True}, {"failed": "unknown request 'base'"}):
            with self.subTest(answer=answer):
                folder = self.root / "cache" / base.BASE / f"own-{len(own_uv.steps)}"
                with self.made(own_uv), mock.patch.object(client, "request", return_value=answer), \
                        mock.patch.object(base, "where", return_value=folder):
                    self.assertEqual(base.ensure(self.installation, told=self.said.append, engine=True).prefix,
                                     str(folder))
        self.assertEqual(own_uv.asked(), ["venv", "pip --offline"] * 3)

    def test_where_the_installation_installs_from(self) -> None:
        tree = self.root / "checkout"
        tree.mkdir()
        wheel = "file:///wheels/texttocad-9.9.9-py3-none-any.whl"
        for source, requirement in ((None, [f"texttocad[build123d]=={RELEASE}"]), (str(tree), ["-e", f"{tree}[build123d]"]),
                                    (wheel, [f"texttocad[build123d] @ {wheel}"])):
            with self.subTest(source=source):
                found = base.Installation(**{**base.dataclasses.asdict(self.installation), "source": source})
                self.assertEqual(found.requirement(), requirement)


class RunTest(unittest.TestCase):
    """``cad run``: the arguments run by the base's Python, in the caller's folder, the program's own folder last
    on its path (the library's runner, ``cad._internal.program``)."""

    def test_the_script_runs_with_the_bases_python(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / "model.py"
            script.write_text("", encoding="utf-8")
            with mock.patch.object(run.os, "execv") as execv, mock.patch("subprocess.call", return_value=0) as call:
                self.assertEqual(run.main([str(script), "--size", "2"]), 1 if os.name != "nt" else 0)
        found = base.ensure(make=False)
        command = [found.python, "-P", "-m", "cad._internal.program", str(script), "--size", "2"]
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
        self.assertEqual(err.getvalue(), "cad run: the CAD kernel environment needs the network once: dns error\n")


class SpawnTest(unittest.TestCase):
    """The engine's spawn pools in the base (``cad.engine.serve._spawn_in``): on Windows their processes
    run the base by its real interpreter, which its ``pyvenv.cfg`` names, never through the venv's
    launcher (the pool's handles would go to the launcher)."""

    def test_the_real_interpreter_behind_a_virtual_environment(self) -> None:
        from cad.engine import serve

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

    @unittest.skipIf(os.name == "nt", "Windows starts real processes: test_environments.py measures through the pool")
    def test_a_pool_process_on_windows_is_the_real_interpreter_told_its_environment(self) -> None:
        """Windows' process start, with Windows' modules stood in: the real interpreter, its command line,
        and ``__PYVENV_LAUNCHER__`` naming the environment's own Python, as CPython starts its own's."""
        import sys
        import types

        created: list[tuple] = []
        winapi = types.SimpleNamespace(CreatePipe=lambda _attributes, _size: (11, 12),
                                       CreateProcess=lambda *args: created.append(args) or (21, 22, 4321, 23),
                                       CloseHandle=lambda _handle: None)
        scratch = tempfile.TemporaryDirectory(prefix="cadgen-spawn-")
        self.addCleanup(scratch.cleanup)
        sent = os.open(os.path.join(scratch.name, "to-child"), os.O_WRONLY | os.O_CREAT)  # the pipe to the child
        msvcrt = types.SimpleNamespace(open_osfhandle=lambda _handle, _flags: sent)
        win32 = types.ModuleType("multiprocessing.popen_spawn_win32")
        win32.Popen = type("Popen", (), {})  # type: ignore[attr-defined]
        win32._close_handles = lambda *_handles: None  # type: ignore[attr-defined]
        venv, real = r"C:\base\Scripts\python.exe", r"C:\python\python.exe"
        stood_in = {"_winapi": winapi, "msvcrt": msvcrt, "multiprocessing.popen_spawn_win32": win32}
        with mock.patch.dict(sys.modules, stood_in), \
                mock.patch.object(subprocess, "STARTUPINFO", lambda **flags: flags, create=True), \
                mock.patch.object(subprocess, "STARTF_FORCEOFFFEEDBACK", 0x80, create=True):
            sys.modules.pop("cad.engine.windows_spawn", None)
            from cad.engine import windows_spawn

            try:
                context = windows_spawn.context(venv, real)
                # The process object goes to the child pickled: its class is one the child imports.
                started = context.Process._Popen(context.Process(target=print))
            finally:
                sys.modules.pop("cad.engine.windows_spawn", None)
        [(executable, line, _process, _thread, inherit, _flags, env, _folder, _startup)] = created
        self.assertEqual((executable, inherit, env["__PYVENV_LAUNCHER__"]), (real, False, venv))
        self.assertTrue(line.startswith(f'"{real}" '), line)
        self.assertIn("--multiprocessing-fork", line)
        self.assertEqual((started.pid, started.sentinel), (4321, 21))
        self.assertEqual(context.get_start_method(), "spawn")


if __name__ == "__main__":
    unittest.main()
