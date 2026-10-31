"""The update path's parts, with the engine and uv stood in for: the switch (``cadgen._internal.switch``)
-- its flip of ``current`` and its way back --, the update a click starts (``cadgen._internal.update``),
and the release folders kept and removed (``cadgen._internal.releases``). The whole path with the real
uv, a local feed and a local index is test_update_end_to_end.py's."""

from __future__ import annotations

import json
import os
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

add_repo_path("packages/cadgen/src")

from cadgen._internal import installations, releases, switch, update  # noqa: E402
from cadgen.engine import client  # noqa: E402


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory(prefix="cadgen-update-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        engine = tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)
        self.addCleanup(lambda: __import__("shutil").rmtree(engine, True))
        patched = mock.patch.dict(os.environ, {"CADGEN_STATE_DIR": str(self.root / "state"),
                                               "CADGEN_CACHE_DIR": str(self.root / "cache"),
                                               "CADGEN_ENGINE_DIR": engine})
        patched.start()
        self.addCleanup(patched.stop)

    def release(self, version: str) -> dict:
        """A release's folder, made as ``releases.make`` makes one, and registered."""
        folder = releases.where(version)
        scripts = folder / ("Scripts" if os.name == "nt" else "bin")
        scripts.mkdir(parents=True)
        python, console = releases.base.interpreter(folder), releases.console(folder)
        for path in (python, console):
            path.write_text("", encoding="utf-8")
        (folder / releases.MARKER).write_text(json.dumps({"schema": releases.SCHEMA, "version": version}), encoding="utf-8")
        installations.register(version, (str(console), str(python), str(folder)))
        return {"python": str(python), "cadgen": str(console), "prefix": str(folder)}


class SwitchTest(Fixture):
    def started(self, works: set[str]):
        """``switch._started`` stood in for: the engine of each release in ``works`` answers."""
        tried: list[str] = []

        def started(version: str, port, told) -> tuple[bool, str]:
            tried.append(version)
            return (True, "") if version in works else (False, f"cadgen {version}'s engine did not start")

        return tried, mock.patch.object(switch, "_started", side_effect=started)

    def test_the_switch_flips_current_and_keeps_the_release_before(self) -> None:
        for version in ("1.0.0", "1.1.0", "1.2.0"):
            self.release(version)
        installations.point("1.1.0")
        tried, started = self.started({"1.2.0"})
        with started, mock.patch.object(client, "wait_gone", return_value=True), \
                mock.patch.object(releases, "running", return_value=False):
            done = switch.switch("1.2.0", port=4321, previous="1.1.0", told=lambda _line: None)
        self.assertTrue(done["ok"], done)
        self.assertEqual((tried, installations.current_version()), (["1.2.0"], "1.2.0"))
        self.assertIsInstance(done["gapMs"], int)
        self.assertEqual(sorted(release["version"] for release in releases.listing()), ["1.1.0", "1.2.0"],
                         "the release before stays; one older goes")
        self.assertEqual(sorted(record["version"] for record in installations.records()), ["1.1.0", "1.2.0"])
        self.assertEqual(switch.last()["to"], "1.2.0")

    def test_a_release_whose_engine_does_not_answer_is_switched_back(self) -> None:
        for version in ("1.1.0", "1.2.0"):
            self.release(version)
        installations.point("1.1.0")
        tried, started = self.started({"1.1.0"})
        with started, mock.patch.object(client, "wait_gone", return_value=True), \
                mock.patch.object(client, "request", return_value=None) as asked:
            done = switch.switch("1.2.0", port=4321, previous="1.1.0", told=lambda _line: None)
        self.assertFalse(done["ok"])
        self.assertTrue(done["restored"])
        self.assertEqual(done["error"], "cadgen 1.2.0's engine did not start")
        self.assertEqual((tried, installations.current_version()), (["1.2.0", "1.1.0"], "1.1.0"))
        asked.assert_any_call({"op": "stop"}, start=False)  # whatever of the new release answered, stopped first
        self.assertEqual(len(releases.listing()), 2, "nothing is removed when the switch fails")
        self.assertFalse(switch.last()["ok"])

    def test_with_no_engine_running_the_next_client_starts_the_release(self) -> None:
        self.release("1.1.0")
        self.release("1.2.0")
        installations.point("1.1.0")
        with mock.patch.object(client, "request", return_value=None):
            done = switch.handover("1.2.0", told=lambda _line: None)
        self.assertEqual((done["ok"], done["gapMs"], installations.current_version()), (True, None, "1.2.0"))
        with mock.patch.object(client, "request", return_value=None):
            self.assertIsNone(switch.handover("1.2.0", told=lambda _line: None), "nothing to do the second time")

    def test_a_running_engine_drains_and_this_process_switches_it(self) -> None:
        self.release("1.1.0")
        later = self.release("1.2.0")
        installations.point("1.1.0")
        status = {"ok": True, "pid": 7, "prefix": str(releases.where("1.1.0")), "serving": {"port": 4567}}
        with mock.patch.object(client, "request", side_effect=[status, {"ok": True, "draining": True}]) as asked, \
                mock.patch.object(switch, "switch", return_value={"ok": True}) as switched:
            switch.handover("1.2.0", told=lambda _line: None)
        self.assertEqual(asked.call_args_list[1].args[0], {"op": "stop", "drain": True})
        switched.assert_called_once_with("1.2.0", port=4567, previous="1.1.0", told=mock.ANY)
        # The engine already that release's: nothing to switch.
        with mock.patch.object(client, "request", return_value={**status, "prefix": later["prefix"]}), \
                mock.patch.object(switch, "switch") as switched:
            self.assertIsNone(switch.handover("1.2.0", told=lambda _line: None))
        switched.assert_not_called()
        self.assertEqual(installations.current_version(), "1.2.0")

    def test_the_helper_starts_detached_from_the_engine_it_replaces(self) -> None:
        with mock.patch.object(subprocess, "Popen") as popen:
            switch.spawn("1.2.0", port=4567, previous="1.1.0")
        argv = popen.call_args.args[0]
        self.assertEqual(argv[:4], [sys.executable, "-P", "-m", "cadgen.cli"])
        self.assertEqual(argv[4:], ["update", "--switch", "1.2.0", "--port", "4567", "--previous", "1.1.0"])
        options = popen.call_args.kwargs
        if os.name == "nt":
            self.assertEqual(options["creationflags"], switch.DETACHED_PROCESS | switch.CREATE_NEW_PROCESS_GROUP)
        else:
            self.assertTrue(options["start_new_session"])
        self.assertEqual(options["stdin"], subprocess.DEVNULL)


class ReleaseFoldersTest(Fixture):
    def test_a_folder_a_process_runs_from_is_kept(self) -> None:
        for version in ("1.0.0", "1.1.0"):
            self.release(version)
        with mock.patch.object(releases, "running", side_effect=lambda folder: str(folder).endswith("1.0.0")):
            self.assertEqual(releases.collect({"1.1.0"}), [])
        self.assertEqual(len(releases.listing()), 2)
        if os.name != "nt":  # a folder named on a process's command line is one that process runs from
            folder = releases.where("1.0.0")
            self.assertFalse(releases.running(folder))
            process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", str(releases.console(folder))])
            self.addCleanup(process.wait)
            self.addCleanup(process.kill)
            self.assertTrue(releases.running(folder))


class DrainTest(unittest.TestCase):
    """What an update's drain waits for (``Daemon.drain``, ``Daemon.working``): a build, draw or export in
    flight and an agent's MCP tool call; never an open page, a held session, nor a page's own calls."""

    def test_the_engine_stops_for_the_switch_once_its_work_in_flight_is_done(self) -> None:
        from cadgen.engine import daemon

        engine = daemon.Daemon(cap=1)
        self.addCleanup(engine.pool.stop)
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

    def test_an_agent_s_tool_call_holds_it_and_an_open_session_does_not(self) -> None:
        from cadgen.mcp.http import PAGE_TOOLS, Session, Sessions

        sessions = Sessions(engine=None)
        server = SimpleNamespace(operations=SimpleNamespace(keeps_alive=lambda: False),
                                 sidebar_views=SimpleNamespace(close=lambda: None))
        sessions.sessions["held"] = Session(server=server, protocol="2025-11-25", client="some-host")  # type: ignore[arg-type]
        self.assertFalse(sessions.working(), "an open session with nothing in flight")
        sessions.sessions["held"].calls = 1  # an agent's cad_show, running
        self.assertTrue(sessions.working())
        self.assertEqual(PAGE_TOOLS, {"cad_http", "cad_sync", "cad_capture_reply"}, "a page's own calls are never counted")


class Server:
    """The engine's HTTP server as the update sees it: its port, and its drain."""

    def __init__(self) -> None:
        self.port = 4567
        self.retired: list = []

    def retire(self, then=None) -> None:
        self.retired.append(then)


class UpdateJobTest(Fixture):
    def setup_script(self, *lines: str, code: int = 0, said: str = "") -> str:
        """A release's ``cadgen setup --engine-update``: ``lines`` on stdout, ``said`` on stderr, ``code``."""
        script = self.root / ("setup.py")
        script.write_text("import sys\n" + "".join(f"print({line!r}, flush=True)\n" for line in lines)
                          + (f"print({said!r}, file=sys.stderr)\n" if said else "") + f"sys.exit({code})\n", encoding="utf-8")
        if os.name == "nt":
            command = self.root / "cadgen.cmd"
            command.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
        else:
            command = self.root / "cadgen"
            command.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
            command.chmod(0o755)
        return str(command)

    def wait(self, job: update.Update, *states: str) -> dict:
        deadline = time.monotonic() + 30
        while (state := job.snapshot())["state"] not in states:
            self.assertLess(time.monotonic(), deadline, state)
            time.sleep(0.01)
        return state

    def test_a_click_installs_the_release_sets_it_up_and_hands_the_engine_to_the_helper(self) -> None:
        self.release("1.1.0")
        installations.point("1.1.0")
        frame = {"progress": {"kind": "update", "stage": "apps", "job": "1.2.0", "outputs": [], "detail": "",
                              "done": 2, "total": 4, "elapsedMs": 0}}
        command = self.setup_script(json.dumps(frame))
        job, server = update.Update(), Server()
        with mock.patch("cadgen.updates.newest", return_value="1.2.0"), \
                mock.patch.object(releases, "make", return_value={"cadgen": command}) as made, \
                mock.patch.object(switch, "spawn") as spawned:
            started = job.start(server)
            self.assertEqual((started["state"], started["target"]), ("working", "1.2.0"))
            again = job.start(server)  # a second click joins the update running
            self.assertEqual((again["state"] in ("working", "restarting"), again["target"]), (True, "1.2.0"))
            state = self.wait(job, "restarting", "failed")
            self.assertEqual(state["state"], "restarting", state)
            self.assertEqual((state["progress"]["kind"], state["progress"]["stage"]), ("update", "restart"))
            assert job.thread is not None
            job.thread.join(10)
            made.assert_called_once_with("1.2.0", told=mock.ANY)
            (then,) = server.retired
            then()  # the engine drained: its helper starts
        spawned.assert_called_once_with("1.2.0", port=4567, previous="1.1.0")

    def test_nothing_newer_starts_nothing_and_a_failed_setup_says_its_line_and_keeps_the_engine(self) -> None:
        job, server = update.Update(), Server()
        with mock.patch("cadgen.updates.newest", return_value=None), mock.patch.object(releases, "make") as made:
            self.assertEqual(job.start(server)["state"], "idle")
        made.assert_not_called()
        command = self.setup_script(code=1, said="the CAD kernel environment needs the network once: dns error")
        with mock.patch("cadgen.updates.newest", return_value="1.2.0"), \
                mock.patch.object(releases, "make", return_value={"cadgen": command}):
            job.start(server)
            state = self.wait(job, "failed", "restarting")
        self.assertEqual((state["state"], state["error"]),
                         ("failed", "the CAD kernel environment needs the network once: dns error"))
        self.assertEqual(server.retired, [], "the engine stays as it was")
        refused = releases.base.Refused("cadgen 1.2.0 needs the network once: dns error")
        with mock.patch("cadgen.updates.newest", return_value="1.2.0"), mock.patch.object(releases, "make", side_effect=refused):
            job.start(server)
            self.assertEqual(self.wait(job, "failed", "restarting")["error"], str(refused))


if __name__ == "__main__":
    unittest.main()
