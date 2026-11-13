"""The updater's parts (``cad_server._internal.update``), with uv and the new release's setup stood in for: the
contract -- install the release by its own ``cad setup --add``, then run its own ``cad setup --engine-update`` and
nothing else --, the update a click starts and the automatic one's waiting, and the drain a server's retirement
uses. The whole sequence on a device of versions is test_update_sequence.py's; the update with the real uv, a local
feed and a local index is test_update_end_to_end.py's; a real 0.11.10 updating into this build is
scripts/test/rehearse-update.py's."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cad/src")

from cad_server._internal import installations, releases, update  # noqa: E402


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory(prefix="cadgen-update-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        engine = tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)
        self.addCleanup(lambda: shutil.rmtree(engine, True))
        patched = mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(self.root / "state"),
                                               "CAD_CACHE_DIR": str(self.root / "cache"),
                                               "CAD_ENGINE_DIR": engine})
        patched.start()
        self.addCleanup(patched.stop)
        (self.root / "state").mkdir()

    def release(self, version: str) -> dict:
        """A flat release folder of 0.11.10 or earlier, as its updater made one, and registered."""
        folder = releases.root() / version
        scripts = folder / ("Scripts" if os.name == "nt" else "bin")
        scripts.mkdir(parents=True)
        python, console = releases.base.interpreter(folder), releases.console(folder)
        for path in (python, console):
            path.write_text("", encoding="utf-8")
        (folder / releases.MARKER).write_text(json.dumps({"schema": releases.SCHEMA, "version": version}), encoding="utf-8")
        installations.register(version, (str(console), str(python), str(folder)))
        return {"python": str(python), "cad": str(console), "prefix": str(folder)}

    def installed(self) -> None:
        """The install command ran here: its receipt."""
        (self.root / "state" / "install-receipt.json").write_text('{"schema": 1}', encoding="utf-8")

    def setup_script(self, *lines: str, code: int = 0, said: str = "", log: Path | None = None) -> str:
        """A release's ``cad setup``: its arguments, its standard input and its environment kept in ``log``,
        ``lines`` on stdout, ``said`` on stderr, ``code``."""
        script = self.root / f"setup-{code}.py"
        log = log or self.root / "setup.log"
        script.write_text(
            "import json, os, sys\n"
            f"open({str(log)!r}, 'a', encoding='utf-8').write(json.dumps({{'argv': sys.argv[1:], "
            "'stdin': sys.stdin.read(), 'env': {key: os.environ.get(key) for key in ('PYTHONPATH', "
            "'CAD_INSTALLATION_VERSION', 'CAD_UPDATE_PREPARE', 'CAD_STATE_DIR')}}) + '\\n')\n"
            + "".join(f"print({line!r}, flush=True)\n" for line in lines)
            + (f"print({said!r}, file=sys.stderr)\n" if said else "") + f"sys.exit({code})\n", encoding="utf-8")
        if os.name == "nt":
            command = self.root / f"cad-{code}.cmd"
            command.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
        else:
            command = self.root / f"cad-{code}"
            command.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
            command.chmod(0o755)
        return str(command)

    def runs(self) -> list[dict]:
        log = self.root / "setup.log"
        return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []


class ContractTest(Fixture):
    """What an updater hands a newer release, from this release on: its own install, then its own setup, with one
    argument and nothing else (the module's contract)."""

    def test_install_is_the_release_s_own_add_through_uvx(self) -> None:
        from cad_server._internal import base
        from cad_server._internal.launch import LAUNCHER

        with mock.patch.object(base, "find_uv", return_value="uv"), mock.patch.dict(os.environ, {base.FIND_LINKS_ENV: ""}):
            self.assertEqual(update.install_command("0.11.12"),
                             ["uv", "tool", "run", *LAUNCHER[1:-1], "--from", "cad-server==0.11.12", "cad", "setup",
                              "--add", "--quiet"])
        with mock.patch.object(base, "find_uv", return_value="uv"), mock.patch.dict(os.environ, {base.FIND_LINKS_ENV: "/w"}):
            self.assertIn("--find-links", update.install_command("0.11.12"), "a test's folder of wheels, read beside the index")
        # Present already: nothing run. Its install exits non-zero, or leaves it absent: its last line, refused.
        record = {"python": sys.executable, "cad": sys.executable, "prefix": sys.prefix}
        with mock.patch("cad.engine.places.version_record", return_value=record), \
                mock.patch.object(subprocess, "run", side_effect=AssertionError("present: nothing to install")):
            self.assertEqual(update.install("0.11.12"), record)
        done = subprocess.CompletedProcess([], 1, "", "a line before\nerror: no solution for cad-server==0.11.12\n")
        with mock.patch("cad.engine.places.version_record", return_value=None), \
                mock.patch.object(subprocess, "run", return_value=done), self.assertRaises(base.Refused) as refused:
            update.install("0.11.12")
        self.assertEqual(str(refused.exception), "error: no solution for cad-server==0.11.12")

    def test_its_setup_is_handed_one_argument_and_its_frames_are_read(self) -> None:
        frame = {"progress": {"kind": "update", "stage": "restart", "job": "1.2.0", "outputs": [], "detail": "d",
                              "done": 3, "total": 4, "elapsedMs": 0}}
        command = self.setup_script("not json", json.dumps({"progress": {"kind": "other"}}), json.dumps(frame),
                                    code=1, said="the move failed: no network")
        frames: list[tuple[str, str]] = []
        with mock.patch.dict(os.environ, {"PYTHONPATH": "/somewhere", "CAD_INSTALLATION_VERSION": "1.1.0",
                                          "CAD_UPDATE_PREPARE": "1"}):
            code, said = update.run_setup({"cad": command}, frame=lambda *found: frames.append(found))
        self.assertEqual((code, said, frames), (1, "the move failed: no network", [("restart", "d")]))
        (run,) = self.runs()
        self.assertEqual(run["argv"], ["setup", "--engine-update"])
        self.assertEqual(run["stdin"], "", "standard input closed")
        self.assertEqual(run["env"], {"PYTHONPATH": None, "CAD_INSTALLATION_VERSION": None, "CAD_UPDATE_PREPARE": None,
                                      "CAD_STATE_DIR": os.environ["CAD_STATE_DIR"]},
                         "nothing of this process's import path, version or the legacy caller's prepare step")


class ReleaseFoldersTest(Fixture):
    def test_a_folder_a_process_runs_from_is_kept(self) -> None:
        # The flat folders of 0.11.10 and earlier, and a version's: one a process runs from stays (``legacy.remove``,
        # ``versions.remove``).
        for version in ("1.0.0", "1.1.0"):
            self.release(version)
        self.assertEqual(len(releases.listing()), 2)
        if os.name != "nt":  # a folder named on a process's command line is one that process runs from
            folder = releases.root() / "1.0.0"
            self.assertFalse(releases.running(folder))
            process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", str(releases.console(folder))])
            self.addCleanup(process.wait)
            self.addCleanup(process.kill)
            self.assertTrue(releases.running(folder))
            # Named by a link to it -- a worker started by an alias of an environment's Python -- it is the same.
            other = releases.root() / "1.1.0"
            alias = Path(tempfile.mkdtemp(prefix="alias-")) / "release"
            self.addCleanup(shutil.rmtree, alias.parent, True)
            alias.symlink_to(other, target_is_directory=True)
            self.assertFalse(releases.running(other))
            aliased = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", str(alias / "bin" / "python")])
            self.addCleanup(aliased.wait)
            self.addCleanup(aliased.kill)
            self.assertTrue(releases.running(other))


class DrainTest(unittest.TestCase):
    """What an update's drain waits for (``Daemon.drain``, ``Daemon.working``): a build, draw or export in
    flight and an agent's MCP tool call; never an open page, a held session, nor a page's own calls."""

    def test_the_engine_stops_for_the_switch_once_its_work_in_flight_is_done(self) -> None:
        from cad_server.engine import daemon

        engine = daemon.Daemon(cap=1)
        self.addCleanup(engine.supervisor.stop)
        engine.busy, engine.holders = 1, 2  # a build in flight; two held sessions, which it does not wait for
        closed: list[str] = []
        engine.door = SimpleNamespace(close=lambda: closed.append("door"))
        polled, started = threading.Event(), threading.Event()
        asked: list[int] = []
        working = engine.working

        def counted() -> bool:
            asked.append(1)
            if len(asked) > 2:
                polled.set()
            return working()

        engine.working = counted
        engine.drain(started.set)
        self.assertTrue(polled.wait(30))
        self.assertEqual((closed, started.is_set(), engine.stopping.is_set()), ([], False, False),
                         "a build in flight: the door stays open, and nothing starts")
        sent: list[dict] = []
        engine.handle({"op": "stop", "drain": True}, sent.append)  # a second ask joins the drain running
        self.assertEqual(sent, [{"ok": True, "draining": True}])
        with engine.busy_lock:
            engine.busy = 0  # the build answered
        self.assertTrue(engine.stopping.wait(30))
        self.assertEqual((closed, started.is_set()), (["door"], True))

    def test_its_port_closed_by_the_drain_the_accept_loop_stays_until_the_switch_has_started(self) -> None:
        # Windows' loop (``_accept``), on every system: were it to end at the closed port, the process
        # would exit and take the drain's thread with it, before the switch helper started.
        from cad_server.engine import daemon

        engine = daemon.Daemon(cap=1)
        self.addCleanup(engine.supervisor.stop)
        settled, exited, release = threading.Event(), threading.Event(), threading.Event()
        self.addCleanup(release.set)

        class Stopping(threading.Event):
            def wait(self, timeout: float | None = None) -> bool:
                if threading.current_thread() is loop:
                    settled.set()  # the loop saw the closed port and waits for the drain
                return super().wait(timeout)

        engine.stopping = Stopping()
        port = socket.create_server(("127.0.0.1", 0))
        self.addCleanup(port.close)
        port.settimeout(0.5)
        engine.listener = port

        def accept() -> None:
            try:
                daemon._accept(engine, port)
            finally:
                exited.set()
                settled.set()

        loop = threading.Thread(target=accept, daemon=True)
        loop.start()
        engine.drain(release.wait)  # the switch helper's start, held
        self.assertTrue(settled.wait(30))
        self.assertFalse(exited.is_set(), "the port closed, the loop waits while the switch starts")
        release.set()
        loop.join(30)
        self.assertFalse(loop.is_alive())
        self.assertTrue(engine.stopping.is_set())

    def test_an_agent_s_tool_call_holds_it_and_an_open_session_does_not(self) -> None:
        from cad_server.mcp.http import PAGE_TOOLS, Session, Sessions

        sessions = Sessions(engine=None)
        server = SimpleNamespace(sidebar_views=SimpleNamespace(close=lambda: None))
        sessions.sessions["held"] = Session(server=server, protocol="2025-11-25", client="some-host")  # type: ignore[arg-type]
        self.assertFalse(sessions.working(), "an open session with nothing in flight")
        sessions.sessions["held"].calls = 1  # an agent's cad_show, running
        self.assertTrue(sessions.working())
        self.assertEqual(PAGE_TOOLS, {"cad_http", "cad_sync", "cad_capture_reply"}, "a page's own calls are never counted")


class UpdateJobTest(Fixture):
    def wait(self, job: update.Update, *states: str) -> dict:
        deadline = time.monotonic() + 30
        while (state := job.snapshot())["state"] not in states:
            self.assertLess(time.monotonic(), deadline, state)
            time.sleep(0.01)
        return state

    def test_a_click_installs_the_release_and_runs_its_setup(self) -> None:
        self.installed()
        frame = {"progress": {"kind": "update", "stage": "restart", "job": "1.2.0", "outputs": [], "detail": "",
                              "done": 3, "total": 4, "elapsedMs": 0}}
        command = self.setup_script(json.dumps(frame))
        job = update.Update()
        with mock.patch("cad_server.updates.newest", return_value="1.2.0"), \
                mock.patch.object(update, "install", return_value={"cad": command}) as installed:
            started = job.start(SimpleNamespace(port=4567))
            self.assertEqual((started["state"], started["target"]), ("working", "1.2.0"))
            again = job.start()  # a second click joins the update running
            self.assertEqual((again["state"] in ("working", "restarting"), again["target"]), (True, "1.2.0"))
            assert job.thread is not None
            job.thread.join(30)
        state = job.snapshot()
        self.assertEqual(state["state"], "restarting", state)
        self.assertEqual((state["progress"]["kind"], state["progress"]["stage"]), ("update", "restart"))
        installed.assert_called_once_with("1.2.0")
        self.assertEqual([run["argv"] for run in self.runs()], [["setup", "--engine-update"]])

    def test_nothing_newer_no_install_here_and_a_failure_each_leave_the_server_as_it_was(self) -> None:
        job = update.Update()
        with mock.patch("cad_server.updates.newest", side_effect=AssertionError("no install: no feed read")):
            state = job.start()
        self.assertEqual(state["state"], "failed")
        self.assertIn("there is no install of text-to-cad here to update: the install command installs one", state["error"])
        self.installed()
        job = update.Update()
        with mock.patch("cad_server.updates.newest", return_value=None), mock.patch.object(update, "install") as made:
            self.assertEqual(job.start()["state"], "idle")
        made.assert_not_called()
        command = self.setup_script(code=1, said="text-to-cad 1.2.0 could not be installed: dns error")
        with mock.patch("cad_server.updates.newest", return_value="1.2.0"), \
                mock.patch.object(update, "install", return_value={"cad": command}):
            job.start()
            state = self.wait(job, "failed", "restarting")
        self.assertEqual((state["state"], state["error"]), ("failed", "text-to-cad 1.2.0 could not be installed: dns error"))
        refused = releases.base.Refused("cad-server 1.2.0 needs the network once: dns error")
        with mock.patch("cad_server.updates.newest", return_value="1.2.0"), \
                mock.patch.object(update, "install", side_effect=refused):
            job.start()
            self.assertEqual(self.wait(job, "failed", "restarting")["error"], str(refused))
        self.assertEqual(len(self.runs()), 1, "a release that could not be installed runs no setup")


if __name__ == "__main__":
    unittest.main()
