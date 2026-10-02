"""CAD's anonymous analytics: who decides whether they are sent, and that they carry counts, times and
metadata -- how many people, how often, on how many files -- and nothing else."""

from __future__ import annotations

import json
import shutil
import threading
import time
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cadgen.analytics import CLOSE_SECONDS, FILES_PER_BATCH, Recorder, choose, file_code, file_salt, forget_pending, status
from cadgen.mcp.protocol import RequestContext
from cadgen.mcp.server import Server
from cadgen.mcp.ui import AppPage
from cadgen.viewer.recents import RecentStore

QUIET = {"DO_NOT_TRACK": "", "CADGEN_ANALYTICS": ""}


class _Tmp(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.path = self.tmp / "analytics.json"
        environment = mock.patch.dict("os.environ", QUIET)
        environment.start()
        self.addCleanup(environment.stop)
        # No test reaches the real receiver: a deletion is heard at once unless a test says otherwise.
        self.deleted: list[str] = []
        deletion = mock.patch("cadgen.analytics.request_deletion", side_effect=lambda id: self.deleted.append(id) or True)
        deletion.start()
        self.addCleanup(deletion.stop)


class ConsentTest(_Tmp):
    def test_nothing_is_sent_and_no_id_made_until_the_person_says_yes(self) -> None:
        self.assertEqual(status(path=self.path), {"sharing": False, "reason": "unasked", "id": None})
        self.assertFalse(self.path.exists())  # no id for someone who never agreed
        choose(True, by="app", path=self.path)
        agreed = status(path=self.path)
        self.assertEqual((agreed["sharing"], agreed["reason"]), (True, "choice"))
        self.assertEqual(status(path=self.path)["id"], agreed["id"])  # one id, kept
        # A file salt comes with the id, and goes with it: a new install's codes match nothing of the old one's.
        salt = file_salt(self.path)
        self.assertEqual(len(salt), 32)
        choose(False, by="app", path=self.path)
        self.assertIsNone(file_salt(self.path))
        choose(True, by="app", path=self.path)
        self.assertNotEqual(file_code(file_salt(self.path), "/work/bracket.step"), file_code(salt, "/work/bracket.step"))

    def test_off_forgets_the_id_and_the_environment_beats_the_choice(self) -> None:
        forgotten = []
        choose(True, by="cli", path=self.path)
        first = status(path=self.path)["id"]
        self.assertTrue(first)
        self.assertEqual(choose(False, by="app", path=self.path, forget=lambda id: forgotten.append(id) or True),
                         {"sharing": False, "forgotten": True})
        self.assertEqual(forgotten, [first])  # the receiver is asked to delete it
        self.assertEqual(status(path=self.path), {"sharing": False, "reason": "choice", "id": None})
        self.assertNotIn(first, self.path.read_text(encoding="utf-8"))
        choose(True, by="cli", path=self.path)
        self.assertNotEqual(status(path=self.path)["id"], first)  # on again is a new install
        # An opt-out the receiver did not hear is asked for again until it is, by id, and nothing else.
        choose(True, by="cli", path=self.path)
        offline = status(path=self.path)["id"]
        self.assertEqual(choose(False, by="app", path=self.path, forget=lambda id: False)["forgotten"], False)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["forget"], [offline])
        self.assertEqual(status(path=self.path)["id"], None)
        heard = []
        forget_pending(path=self.path, forget=lambda id: heard.append(id) or True)
        self.assertEqual(heard, [offline])
        self.assertNotIn("forget", json.loads(self.path.read_text(encoding="utf-8")))
        choose(True, by="cli", path=self.path)
        # A yes to less than is sent now is asked again; a no is never asked again.
        with mock.patch("cadgen.analytics.DISCLOSURE", 2):
            self.assertEqual(status(path=self.path)["reason"], "unasked")
            choose(False, by="app", path=self.path, forget=lambda id: True)
        with mock.patch("cadgen.analytics.DISCLOSURE", 3):
            self.assertEqual(status(path=self.path)["reason"], "choice")
        for name, value in (("DO_NOT_TRACK", "1"), ("CADGEN_ANALYTICS", "off")):
            with self.subTest(name=name), mock.patch.dict("os.environ", {name: value}):
                self.assertEqual(status(path=self.path)["reason"], "environment")
                self.assertFalse(status(path=self.path)["sharing"])


class NoMeansNoTest(_Tmp):
    """A no -- or closing the card -- is kept, and the CAD app never asks again."""

    def test_a_no_survives_restarts_updates_and_a_larger_disclosure(self) -> None:
        choose(False, by="app", path=self.path)  # No thanks, or the card's X
        no = {"sharing": False, "reason": "choice", "id": None}
        self.assertEqual(status(path=self.path), no)  # a restart: read from the state directory again
        with mock.patch("cadgen.analytics.SCHEMA", 2):  # an update that changes what a batch looks like
            self.assertEqual(status(path=self.path), no)
        with mock.patch("cadgen.analytics.DISCLOSURE", 99):  # an update that sends more: re-asks only a yes
            self.assertEqual(status(path=self.path), no)

    def test_where_no_answer_could_be_kept_nobody_is_asked(self) -> None:
        # A file where the state folder would go: no folder can be made, on any platform or user.
        (self.tmp / "taken").write_text("")
        self.assertEqual(status(path=self.tmp / "taken" / "state" / "analytics.json")["reason"], "unavailable")
        self.assertEqual(status(path=self.path)["reason"], "unasked")
        self.assertEqual(list(self.tmp.glob("analytics.json*")), [], "the try leaves nothing behind")


class ServerCountsTest(_Tmp):
    def serve(self, install: str | None) -> tuple[Server, list[dict]]:
        sent: list[dict] = []
        recorder = Recorder(install=install, path=self.path, send=lambda payload: sent.append(payload) or True)
        (self.tmp / "app").mkdir(exist_ok=True)
        server = Server(launch_cwd=str(self.tmp), page=AppPage(self.tmp / "app"), recents=RecentStore(self.tmp / "state"),
                        analytics=recorder)
        server.handle("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                     "clientInfo": {"name": "codex-mcp-client", "version": "0.159.0"}}, None)
        return server, sent

    def call(self, server: Server, name: str, arguments: dict | None = None) -> dict:
        context = RequestContext(1, {"threadId": "t"}, None)
        return server.handle("tools/call", {"name": name, "arguments": arguments or {}}, context)

    def test_a_yes_sends_use_files_and_metadata_and_nothing_the_person_made(self) -> None:
        server, sent = self.serve("store")
        self.assertEqual(self.call(server, "cad_consent")["structuredContent"]["ask"], True)  # a directory install is asked too
        self.call(server, "cad_consent", {"share": True})
        secret = self.tmp / "secret-bracket.step"
        secret.write_text("ISO-10303-21;", encoding="utf-8")
        self.call(server, "cad_open", {"path": str(secret)})  # the agent opens one
        self.call(server, "cad_recents", {})  # the home's polling: never counted
        # A view's syncs: plumbing, never a tool count; a touch is view activity, and the file it shows
        # (one a person browsed to) is a file worked on.
        for _ in range(3):
            self.call(server, "cad_sync", {"view": "v", "surface": "thread", "model": str(self.tmp / "secret-plate.STL")})
        self.call(server, "cad_sync", {"view": "v", "surface": "thread", "model": str(secret), "focused": True})
        self.assertTrue(server.analytics.flush())
        [payload] = sent
        events = payload["events"]
        self.assertEqual([(event["name"], event.get("tool"), event.get("calls")) for event in events if event["name"] != "file"],
                         [("tool", "cad_open", 1), ("view", None, 1)])
        files = sorted((event["kind"], event["file"]) for event in events if event["name"] == "file")
        salt = file_salt(self.path)
        self.assertEqual(files, sorted([("step", file_code(salt, str(secret))), ("stl", file_code(salt, str(self.tmp / "secret-plate.STL")))]))
        self.assertTrue(all(len(code) == 16 for _, code in files))
        self.assertEqual((payload["source"], payload["presentation"], payload["client"]["name"]),
                         ("store", "tabs", "codex-mcp-client"))
        self.assertNotIn("secret", json.dumps(payload))
        self.assertNotIn(str(self.tmp), json.dumps(payload))
        # The same files on screen the same day are not sent again, and a batch with no use is not sent.
        self.call(server, "cad_sync", {"view": "v", "surface": "thread", "model": str(secret)})
        self.assertFalse(server.analytics.flush())
        self.assertEqual(len(sent), 1)
        # A host's free-text name becomes a token the receiver takes: ASCII, as its check reads it.
        recorder = Recorder(path=self.path)
        recorder.started(client={"name": "Café Studio", "version": "1.105 (Universal)"}, presentation="inline")
        self.assertEqual(recorder._context["client"], {"name": "Caf-Studio", "version": "1.105-Universal-"})

    def test_a_server_nobody_used_sends_nothing(self) -> None:
        # Codex starts a server per thread, and some only to list tools: none of them is a user.
        server, sent = self.serve("store")
        self.call(server, "cad_consent", {"share": True})
        self.call(server, "cad_sync", {"view": "v", "surface": "sidebar"})
        self.assertFalse(server.analytics.flush())
        server.analytics.close()
        self.assertEqual(sent, [])

    def test_a_batch_the_receiver_did_not_take_waits_for_the_next(self) -> None:
        answers = [False, True]
        sent: list[dict] = []
        recorder = Recorder(path=self.path, send=lambda payload: sent.append(payload) or answers.pop(0))
        choose(True, by="cli", path=self.path)
        recorder.called("cad_show", True)
        recorder.opened("/work/a.step")
        self.assertFalse(recorder.flush())  # offline: kept
        recorder.called("cad_show", False)
        self.assertTrue(recorder.flush())
        tools = [event for event in sent[1]["events"] if event["name"] == "tool"]
        self.assertEqual(tools, [{"name": "tool", "tool": "cad_show", "calls": 2, "errors": 1}])
        self.assertEqual(len([event for event in sent[1]["events"] if event["name"] == "file"]), 1)

    def test_files_past_a_batchs_room_go_in_the_next(self) -> None:
        sent: list[dict] = []
        recorder = Recorder(path=self.path, send=lambda payload: sent.append(payload) or True)
        choose(True, by="cli", path=self.path)
        for index in range(FILES_PER_BATCH + 8):
            recorder.opened(f"/work/part-{index}.step")
        recorder.opened("/work/notes.txt")  # not a CAD file: not noted
        self.assertTrue(recorder.flush())
        self.assertTrue(recorder.flush())
        self.assertEqual([len(payload["events"]) for payload in sent], [FILES_PER_BATCH, 8])

    def test_a_manual_install_asks_once_and_sends_only_after_yes(self) -> None:
        server, sent = self.serve(None)
        self.call(server, "cad_show", {"path": "a.step"})
        self.assertEqual(self.call(server, "cad_consent")["structuredContent"]["ask"], True)
        server.analytics.flush()
        self.assertEqual(sent, [])
        answer = self.call(server, "cad_consent", {"share": True})["structuredContent"]
        self.assertEqual((answer["ask"], answer["sharing"]), (False, True))
        self.call(server, "cad_view")
        server.analytics.flush()
        self.assertEqual([event.get("tool") for event in sent[0]["events"]], ["cad_view"])

    def test_the_agent_can_turn_analytics_off_but_not_on(self) -> None:
        server, sent = self.serve("store")
        self.call(server, "cad_consent", {"share": True})
        off = self.call(server, "cad_analytics", {"action": "off"})
        self.assertEqual(off["structuredContent"], {"sharing": False})
        self.assertFalse(status(path=self.path)["sharing"])
        tool = next(tool for tool in server.tools() if tool["name"] == "cad_analytics")
        self.assertEqual(tool["inputSchema"]["properties"]["action"]["enum"], ["status", "off"])
        self.call(server, "cad_show", {"path": "a.step"})
        server.analytics.flush()
        self.assertEqual(sent, [])
        self.assertIsNone(file_salt(self.path))


class NeverInTheWayTest(_Tmp):
    """Analytics never fail, slow or clutter what CAD does."""

    serve = ServerCountsTest.serve
    call = ServerCountsTest.call

    def test_a_broken_analytics_layer_fails_nothing_and_logs_nothing_a_host_shows(self) -> None:
        server, sent = self.serve("store")
        with mock.patch("cadgen.analytics.status", side_effect=RuntimeError("broken")), \
                mock.patch("cadgen.analytics.choose", side_effect=RuntimeError("broken")), \
                self.assertNoLogs("cadgen.analytics", level="INFO"):
            # The tools answer as if nothing were wrong: off, and nothing to ask.
            self.assertEqual(self.call(server, "cad_consent")["structuredContent"]["ask"], False)
            self.assertEqual(self.call(server, "cad_consent", {"share": True})["structuredContent"]["sharing"], False)
            self.assertFalse(self.call(server, "cad_analytics").get("isError"))
            self.assertFalse(self.call(server, "cad_analytics", {"action": "off"}).get("isError"))
            # CAD's own tools are untouched, and the recorder's own methods return quietly.
            self.assertIn("isError", self.call(server, "cad_show", {"path": "missing.step"}))
            server.analytics.called("cad_show", True)
            self.assertFalse(server.analytics.flush())
            server.analytics.close()

    def test_no_tool_call_waits_on_the_network(self) -> None:
        server, sent = self.serve("store")
        self.call(server, "cad_consent", {"share": True})
        release = threading.Event()
        with mock.patch("cadgen.analytics.request_deletion", side_effect=lambda id: release.wait(10)):
            began = time.monotonic()
            self.call(server, "cad_consent", {"share": False})  # its deletion hangs in the background
            self.assertLess(time.monotonic() - began, 1)
            release.set()

    def test_an_exiting_server_waits_for_its_last_send_only_so_long(self) -> None:
        hang = threading.Event()
        recorder = Recorder(path=self.path, send=lambda payload: hang.wait(30))
        choose(True, by="cli", path=self.path)
        recorder.started(client={"name": "codex-mcp-client"}, presentation="tabs")
        recorder.called("cad_show", True)
        began = time.monotonic()
        recorder.close()
        self.assertLess(time.monotonic() - began, CLOSE_SECONDS + 1)
        hang.set()


if __name__ == "__main__":
    unittest.main()
