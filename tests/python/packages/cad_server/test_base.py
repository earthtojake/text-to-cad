"""The base (``cad_server._internal.base``): the one environment, ``cad[build123d]`` at the installation's
release on its Python, made once and reused; an installation that carries the kernel is its own; and
``cad run`` runs the script with its Python.

uv is stood in for (``Fake``): each step it is asked is recorded, ``venv`` makes the environment's
Python as a file, ``pip`` answers what the test gives it. The real uv, a model built in the base and
the engine's kernel processes there are test_environments.py's.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cad/src")

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

    def __call__(self, step: list[str], folder: Path, settings=None) -> subprocess.CompletedProcess:
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
            release=RELEASE, python="3.14.2", executable=str(base.interpreter(self.core)),
            prefix=str(self.core), root=str(self.core / "site-packages"), source=None, arch="arm64", kernel=False)
        self.said: list[str] = []
        self.path = ["/stdlib", "/the-base/site-packages"]

    def made(self, fake: Fake) -> contextlib.ExitStack:
        """``base`` with ``fake`` for uv and the base's import path known."""
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(base, "_uv", fake))
        stack.enter_context(mock.patch.object(base, "find_uv", return_value="uv"))
        stack.enter_context(mock.patch.object(base, "_probe", return_value=(self.path, "3.14.2")))
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
                               "hardlink", f"cad[build123d]=={RELEASE}", "--offline"])
        self.assertEqual(self.said, [f"making the CAD kernel environment, once: cad[build123d] {RELEASE} on Python "
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
        self.assertEqual(self.said[1], "downloading the CAD kernel (about 240 MB) and what it needs, once")

    def test_a_base_that_cannot_be_made_is_refused_in_one_line(self) -> None:
        offline = "error: Failed to fetch: `https://pypi.org/simple/build123d/`\n  Caused by: dns error: failed to lookup address"
        fake = Fake((2, offline), (2, offline))
        with self.made(fake), self.assertRaises(base.Refused) as refused:
            base.ensure(self.installation, told=self.said.append)
        self.assertEqual(str(refused.exception), "the CAD kernel environment needs the network once: Failed to fetch: "
                                                 "`https://pypi.org/simple/build123d/` (dns error: failed to lookup address)")
        self.assertEqual(refused.exception.cause, "network", "a word of ours for telemetry, never read from the line")
        self.assertIsNone(base.complete(base.where(self.installation)), "no marker: the next use makes it again")

    def test_a_cooldown_in_uvs_settings_keeps_out_no_release_of_cads_own(self) -> None:
        """A person's ``exclude-newer`` (a cooldown on new uploads, in their uv.toml) leaves out the release the
        engine runs, which the server line installed without reading it: uv is asked again with the cutoff lifted
        for cad alone, from the step it said so, the steps after asked the same. As uv 0.13 says it; offline,
        with a cold cache, it says no version and no hint."""
        unsatisfiable = (f"error: No solution found when resolving dependencies\n  cause: Because there is no version of "
                         f"cad[build123d]=={RELEASE} and you require cad[build123d]=={RELEASE}, we can conclude that your "
                         "requirements are unsatisfiable.\n")
        filtered = (f"{unsatisfiable}\nhint: `cad` was filtered by `exclude-newer` to only include packages uploaded "
                    f"before 2026-11-19T20:49:10Z. The requested version, v{RELEASE}, was published at "
                    "2026-11-23T17:27:17Z. Consider using `exclude-newer-package` to override the cutoff for this package.\n")
        lifted = ["--exclude-newer-package", "cad=false"]
        for cache, answers, asked in (("warm", [(1, filtered)], ["venv", "pip --offline", "pip --offline"]),
                                      ("cold", [(1, unsatisfiable), (1, filtered)], ["venv", "pip --offline", "pip", "pip"])):
            with self.subTest(cache=cache):
                fake = Fake(*answers)
                with self.made(fake):
                    found = base.ensure(self.installation, told=self.said.append)
                self.assertEqual(fake.asked(), asked)
                self.assertNotIn("cad=false", fake.steps[-2], "asked as given until uv said cad was left out")
                made = [step for step in fake.steps[-1] if step != "--offline"]
                self.assertEqual(made[-2:], lifted, "the cutoff lifted for cad alone")
                self.assertEqual(base.marked(Path(found.prefix))["commands"][1], made, "its marker names that step")
                base._remove(Path(found.prefix))
        # What a cooldown holds back of what cad needs -- not cad's own -- is said with uv's hint; nothing is lifted.
        held = ("error: No solution found when resolving dependencies\n  cause: Because only build123d<0.13.0 is "
                f"available and cad[build123d]=={RELEASE} depends on build123d>=0.13.0, we can conclude that your "
                "requirements are unsatisfiable.\n\nhint: `build123d` was filtered by `exclude-newer` to only include "
                "packages uploaded before 2026-11-19T20:49:10Z. Consider using `exclude-newer-package` to override the "
                "cutoff for this package.\n")
        fake = Fake((1, held), (1, held))
        with self.made(fake), self.assertRaises(base.Refused) as refused:
            base.ensure(self.installation, told=self.said.append)
        self.assertEqual(fake.asked(), ["venv", "pip --offline", "pip"])
        self.assertTrue(str(refused.exception).startswith(
            "a cutoff of uv's settings (exclude-newer) holds back what the CAD kernel environment needs: `build123d` was "
            "filtered by `exclude-newer`"), str(refused.exception))
        self.assertEqual(refused.exception.cause, "resolve")

    def test_an_installation_that_carries_the_kernel_is_its_own_base(self) -> None:
        own = base.Installation(**{**base.dataclasses.asdict(self.installation), "kernel": True})
        fake = Fake()
        with self.made(fake):
            found = base.ensure(own)
        self.assertEqual(found, base.Environment(own.executable, own.prefix, True))
        self.assertEqual(fake.steps, [])

    def test_the_engine_makes_its_base_on_first_need_and_a_follower_hears_its_lines(self) -> None:
        # The engine that finds no base makes it when asked (``Making``), outside the sandbox an agent's command
        # runs in: whoever asks for it follows the making from its first line. That a kernel process's start asks
        # for it, and the engine's own start does not, is test_daemon_server's.
        fake, making = Fake(), base.Making()
        heard: list[str] = []
        with self.made(fake), mock.patch.object(base.Installation, "here", return_value=self.installation), \
                contextlib.redirect_stderr(io.StringIO()) as log:
            self.assertEqual(making.key(), base.where(self.installation).name)
            self.assertIsNone(making.follow(heard.append), "absent: made now, and followed from its first line")
            self.assertFalse(making.start(), "made: nothing to make again")
            self.assertIsNone(making.follow(heard.append), "made: nothing more to hear")
        env = base.where(self.installation)
        self.assertIsNotNone(base.complete(env))
        line = f"making the CAD kernel environment, once: cad[build123d] {RELEASE} on Python 3.14.2, in {env}"
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
        self.assertEqual(asked, [({"op": "base", "key": env.name}, True)], "the running server, which it needs")
        self.assertEqual((found.prefix, own_uv.steps), (str(env), []), "made by the engine, not here")
        self.assertEqual(self.said, ["making the CAD kernel environment, once"])
        refused = {"failed": "the CAD kernel environment needs the network once: dns error", "base": True}
        with self.made(own_uv), mock.patch.object(client, "request", side_effect=engine(refused)), \
                mock.patch.object(base, "where", return_value=self.root / "cache" / base.BASE / "another"), \
                self.assertRaisesRegex(base.Refused, "^the CAD kernel environment needs the network once: dns error$"):
            base.ensure(self.installation, told=self.said.append, engine=True)
        # No server running: its one line, and nothing made here (``cad server start`` starts it).
        with self.made(own_uv), mock.patch.object(client, "request", side_effect=client.NotRunning(client.NOT_RUNNING)), \
                mock.patch.object(base, "where", return_value=self.root / "cache" / base.BASE / "none"), \
                self.assertRaises(client.NotRunning):
            base.ensure(self.installation, told=self.said.append, engine=True)
        # A server that makes another base than this command's (the release installed from elsewhere, or on another
        # Python line), or none:
        # one line, and nothing made here -- only the server makes it.
        for answer in ({"ok": False, "other": True}, {"failed": "unknown request 'base'"}):
            with self.subTest(answer=answer), self.made(own_uv), \
                    mock.patch.object(client, "request", return_value=answer), \
                    mock.patch.object(base, "where", return_value=self.root / "cache" / base.BASE / "other"), \
                    self.assertRaisesRegex(base.Refused, "^the running server is cad of this release installed from "
                                                         "elsewhere or on another Python, .+: run `cad server stop`, "
                                                         "then `cad server start`$"):
                base.ensure(self.installation, told=self.said.append, engine=True)
        self.assertEqual(own_uv.steps, [])

    def test_one_release_has_one_base_per_python_line_wherever_cad_is_installed(self) -> None:
        # An agent app starts the server from uvx's cache; the `cad` in the agent's shell is installed elsewhere
        # (uv's tool folder): on the same Python line both name the one base, which the server makes.
        tool = self.root / "tools" / "cad"
        elsewhere = base.dataclasses.replace(self.installation, python="3.14.0", executable=str(base.interpreter(tool)),
                                             prefix=str(tool), root=str(tool / "site-packages"))
        self.assertEqual(base.where(elsewhere), base.where(self.installation))
        self.assertEqual(base._inputs(self.installation)["python"], "3.14")
        # A cad on another line (pip on a system 3.12) makes its base on that line, so the key says that line: a
        # base made on 3.12 is never found by a cad on 3.14, nor the other way round.
        older = base.dataclasses.replace(elsewhere, python="3.12.10")
        self.assertEqual(base._inputs(older)["python"], "3.12")
        self.assertNotEqual(base.where(older), base.where(self.installation))
        fake = Fake()
        with self.made(fake):
            base.ensure(older, told=self.said.append)
        self.assertEqual(fake.steps[0][:5], ["uv", "venv", "--no-project", "--python", older.executable])
        self.assertEqual(base.complete(base.where(older))["inputs"]["python"], "3.12")
        for other in ({"release": "9.9.10"}, {"source": "file:///wheels/cad-9.9.9-py3-none-any.whl"}):
            with self.subTest(other=other):
                self.assertNotEqual(base.where(base.dataclasses.replace(self.installation, **other)),
                                    base.where(self.installation))

    def test_a_server_on_a_python_newer_than_cads_line_makes_the_base_on_cads_line(self) -> None:
        # `uv tool install cad` takes any Python that meets requires-python, which has no upper bound: on a line
        # newer than the one this release runs on (launch.PYTHON), the kernel may have no wheels yet (OCP had none
        # for 3.15), so the base is made on cad's line, a Python uv manages, and found by every installation of
        # the release as before. The floor's line and cad's own keep the server's own Python.
        from cad_server._internal.launch import PYTHON

        newer = base.dataclasses.replace(self.installation, python="3.15.0b3")
        self.assertEqual(base.where(newer), base.where(self.installation), "one base for the release")
        fake = Fake()
        with self.made(fake):
            base.ensure(newer, told=self.said.append)
        env = base.where(newer)
        self.assertEqual(fake.steps[0], ["uv", "venv", "--no-project", "--python", PYTHON, "--managed-python", str(env)])
        self.assertEqual(self.said, [f"making the CAD kernel environment, once: cad[build123d] {RELEASE} on Python "
                                     f"{PYTHON}, in {env}"])
        for version in ("3.13.1", f"{PYTHON}.0"):
            with self.subTest(version=version):
                own = base.dataclasses.replace(self.installation, python=version)
                self.assertEqual(base.kernel_python(own), (own.executable, (), version))
        self.assertEqual(base.kernel_python(base.dataclasses.replace(self.installation, python="4.0.1"))[:2],
                         (PYTHON, ("--managed-python",)))

    def test_a_request_whose_kernel_process_waits_on_the_making_hears_its_lines(self) -> None:
        # A first build, view or export says nothing of its own while the kernel is fetched: the server says each
        # line of the making to the request that waits on it (``base.TOLD``, set for each request it serves), and
        # the client says it as it comes, whichever command it is (``client._exchange``).
        from cad.engine import client
        from cad_server.engine import daemon

        class Served:
            unsaid, refusal, token = "", None, None

            @staticmethod
            def handle(request, send):
                send({"ok": True, "kernel": base.kernel()["prefix"]})

            @staticmethod
            def ended(request):
                pass

        answered = io.BytesIO()
        with self.kernel(base.Making(), Fake()), mock.patch.object(daemon, "WINDOWS", False):
            daemon._serve(Served(), io.BytesIO(b'{"op": "build"}\n'), answered)
        env = base.where(self.installation)
        line = f"making the CAD kernel environment, once: cad[build123d] {RELEASE} on Python 3.14.2, in {env}"
        frames = [json.loads(frame) for frame in answered.getvalue().splitlines()]
        self.assertEqual(frames, [{"log": line, "stream": "making"}, {"ok": True, "kernel": str(env)}])

        class Connection(io.BytesIO):
            reader, writer = io.BytesIO(answered.getvalue()), io.BytesIO()

        logged: list[dict] = []
        with contextlib.redirect_stderr(io.StringIO()) as said, mock.patch.object(client.places, "WINDOWS", False):
            answer = client._exchange(Connection(), {"op": "build"}, logged.append)
        self.assertEqual((answer, logged), ({"ok": True, "kernel": str(env)}, []))
        self.assertEqual(said.getvalue(), f"cad: {line}\n")

    def kernel(self, making: base.Making, uv) -> contextlib.ExitStack:
        """``base.kernel`` as the engine asks it, its making ``making`` and uv ``uv``, the engine's log
        swallowed."""
        stack = self.made(uv)
        stack.enter_context(mock.patch.object(base, "MAKING", making))
        stack.enter_context(mock.patch.object(base.Installation, "here", return_value=self.installation))
        stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
        return stack

    def refused(self) -> base.Refused:
        with self.assertRaises(base.Refused) as refused:
            base.kernel()
        return refused.exception

    def test_a_failed_making_that_cannot_clear_by_itself_is_told_at_once_until_asked_again(self) -> None:
        # 0.11.9: every cad_show made the base again -- uv's venv and install, offline then online -- and failed
        # the same way: one install 29 times in 50 minutes. A failure that cannot clear by itself is now told at
        # once, uv not run, however long after, until something that could change it happens.
        now = [1000.0]
        making = base.Making(clock=lambda: now[0])

        def uv(step: list[str], folder: Path, settings=None) -> subprocess.CompletedProcess:
            asked.append(step[1])
            return subprocess.CompletedProcess(step, 2, "", "error: Failed to inspect Python interpreter")
        asked: list[str] = []
        with self.kernel(making, uv):
            first = self.refused()
            self.assertEqual(first.cause, "python")
            self.assertTrue(str(first).startswith(f"uv cannot make the CAD kernel environment on "
                                                  f"{self.installation.executable}: Failed to inspect Python "
                                                  "interpreter. "), str(first))
            self.assertTrue(str(first).endswith(". The engine does not try again until it restarts; "
                                                '`cad run -c "import build123d"` tries again, saying each step.'))
            now[0] += 3600
            for _ in range(3):
                later = self.refused()
            self.assertEqual(asked, ["venv"], "made once: the later requests are told the failure, uv not run")
            self.assertEqual(later.cause, "python")
            self.assertIn(": Failed to inspect Python interpreter", str(later))
            self.assertIn(" (its try 60 min ago; nothing made since). The engine does not try again until it restarts; "
                          '`cad run -c "import build123d"` tries again', str(later))
            # Telemetry is told it once, however many requests are.
            self.assertEqual([making.claim(), making.claim()], [True, False])
            # A `cad run` asks the engine's making over its door, which makes it again.
            self.assertIsNotNone(making.follow(lambda _line: None))
            self.assertEqual(asked, ["venv", "venv"])
            self.assertTrue(making.claim(), "a making that failed again is reported again")
            # A base another process made is taken: nothing remembered stands in its way.
            env = base.where(self.installation)
            with self.made(Fake()):
                base.ensure(self.installation, told=lambda _line: None)
            self.assertIsNone(making.remembered())
            self.assertEqual(base.kernel()["prefix"], str(env))

    def test_a_failed_making_that_can_clear_by_itself_is_made_again_after_a_pause(self) -> None:
        offline = "error: Failed to fetch: `https://pypi.org/simple/build123d/`\n  Caused by: dns error: failed to lookup address"
        now = [0.0]
        making = base.Making(clock=lambda: now[0])
        fake = Fake(*[(2, offline)] * 4)
        with self.kernel(making, fake):
            first = self.refused()
            self.assertEqual(first.cause, "network")
            self.assertTrue(str(first).endswith(". The engine tries again on a request 5 min from now; "
                                                '`cad run -c "import build123d"` tries now, saying each step.'), str(first))
            now[0] = base.RETRY_SECONDS - 40
            waiting = self.refused()
            self.assertIn("(its try 4 min ago; nothing made since). The engine tries again on a request 40 s from now",
                          str(waiting))
            self.assertEqual(fake.asked(), ["venv", "pip --offline", "pip"], "told, not made again, within the pause")
            now[0] = base.RETRY_SECONDS
            self.assertEqual(self.refused().cause, "network")
            self.assertEqual(fake.asked(), ["venv", "pip --offline", "pip"] * 2, "made again once the pause is over")

    def test_each_failure_names_its_cause_where_it_is_classified(self) -> None:
        recipe = base.recipe(self.installation)
        install = ["uv", "pip", "install", "--python", "py", f"cad[build123d]=={RELEASE}"]
        unlisted = ("error: No solution found when resolving dependencies\n"
                    f"  ╰─▶ Because there is no version of cad[build123d]=={RELEASE} and you require "
                    f"cad[build123d]=={RELEASE}, we can conclude that your requirements are unsatisfiable.\n")
        for said, code, cause in (("Resolved 41 packages\n", -9, "killed"),
                                  ("error: failed to create directory: Permission denied (os error 13)", 2, "denied"),
                                  ("error: dns error: failed to lookup address", 2, "network"),
                                  (unlisted, 1, "resolve"),
                                  ("error: Failed to download `numpy==2.3.0`\n  Caused by: checksum mismatch", 2, "install")):
            with self.subTest(cause=cause):
                text, found = base._failure(install, said, recipe, code)
                self.assertEqual(found, cause)
                self.assertEqual(text, base.failure(install, said, recipe, code))
        text, _cause = base._failure(install, "error: Failed to download `numpy==2.3.0`\n  Caused by: checksum mismatch",
                                     recipe, 2)
        self.assertEqual(text, "uv could not make the CAD kernel environment, from its cache, then from the network: "
                               "Failed to download `numpy==2.3.0` (checksum mismatch) (the last of what uv said; the rest "
                               "is kept nowhere)")
        text, _cause = base._failure(install, unlisted, recipe, 1)
        self.assertTrue(text.startswith(f"release {RELEASE} is on no package index uv reads: Because there is no version"))
        self.assertTrue(text.endswith("; one of the indexes uv's settings name (UV_INDEX_URL, UV_DEFAULT_INDEX) must hold it"))

    def test_where_the_installation_installs_from(self) -> None:
        tree = self.root / "checkout"
        tree.mkdir()
        wheel = "file:///wheels/cad-9.9.9-py3-none-any.whl"
        for source, requirement in ((None, [f"cad[build123d]=={RELEASE}"]), (str(tree), ["-e", f"{tree}[build123d]"]),
                                    (wheel, [f"cad[build123d] @ {wheel}"])):
            with self.subTest(source=source):
                found = base.Installation(**{**base.dataclasses.asdict(self.installation), "source": source})
                self.assertEqual(found.requirement(), requirement)


class RunTest(unittest.TestCase):
    """``cad run``: a script whose imports use the build123d integration alone run by the base's Python, in
    the caller's folder, the program's own folder last on its path (the library's runner,
    ``cad._internal.program``). Each runs in its own folder: the uv configuration a run's folder reads is part of
    its environment, and a checkout's root pyproject.toml (a uv workspace) is one."""

    def test_the_script_runs_with_the_bases_python(self) -> None:
        with tempfile.TemporaryDirectory() as folder, contextlib.chdir(folder):
            script = Path(folder) / "model.py"
            script.write_text("import build123d\n", encoding="utf-8")
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
                mock.patch.object(run.os, "execv") as execv, contextlib.redirect_stderr(err), \
                tempfile.TemporaryDirectory() as folder, contextlib.chdir(folder):
            (Path(folder) / "model.py").write_text("import build123d\n", encoding="utf-8")
            self.assertEqual(run.main([str(Path(folder) / "model.py")]), 1)
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
    def test_the_spawner_imports_on_a_python_older_than_3_13(self) -> None:
        """Before 3.13 ``subprocess`` names no ``STARTF_FORCEOFFFEEDBACK``, and cad installs on 3.11: the spawner
        imports there all the same, with Win32's own value of the flag, the one 3.13 names (#870)."""
        import importlib
        import sys
        import types

        win32 = types.ModuleType("multiprocessing.popen_spawn_win32")
        win32.Popen = type("Popen", (), {})  # type: ignore[attr-defined]
        stood_in = {"_winapi": types.SimpleNamespace(), "msvcrt": types.SimpleNamespace(),
                    "multiprocessing.popen_spawn_win32": win32}
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.dict(sys.modules, stood_in))
            stack.enter_context(mock.patch.object(subprocess, "STARTUPINFO", lambda **flags: flags, create=True))
            if hasattr(subprocess, "STARTF_FORCEOFFFEEDBACK"):  # Windows on 3.13 or newer: as before 3.13
                stack.callback(setattr, subprocess, "STARTF_FORCEOFFFEEDBACK", subprocess.STARTF_FORCEOFFFEEDBACK)
                del subprocess.STARTF_FORCEOFFFEEDBACK
            sys.modules.pop("cad.engine.windows_spawn", None)
            stack.callback(sys.modules.pop, "cad.engine.windows_spawn", None)
            # Imported afresh, by its name: `from cad.engine import windows_spawn` would hand back the module an
            # earlier test left as the package's attribute.
            windows_spawn = importlib.import_module("cad.engine.windows_spawn")

            self.assertEqual(windows_spawn.STARTF_FORCEOFFFEEDBACK, 0x80)

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
