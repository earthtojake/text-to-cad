"""cadgen's telemetry, CAD's usage stats: who decides whether they are sent -- by default once a ``cadgen`` command has
said so, never after a no -- and that they carry counts, times and metadata -- how many people, how often,
on how many files -- and nothing else. The build daemon's counts are ``test_daemon_telemetry.py``'s."""

from __future__ import annotations

import base64
import http.server
import io
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

from cadgen import cli
from cadgen._internal import channel as install_channel
from cadgen.analytics import (KEPT, NOTICE_ENV, PRIVACY_URL, Recorder, _post, choose, died, forget_pending,
                              notice_text, notify, spool, status)
from cadgen.cli import telemetry as telemetry_cli
from cadgen.mcp.shim import initialize_params
from cadgen.mcp.protocol import RequestContext, RpcError
from cadgen.mcp.server import Server
from cadgen.mcp.ui import AppPage
from cadgen.viewer.recents import RecentStore

# Where the notice is said, and the default holds: an install a plugin made (a checkout is a development install,
# never told and sending nothing by default), outside CI. Every test runs there unless it says otherwise.
TOLD = {"CADGEN_INSTALL_CHANNEL": "claude-github", "CI": ""}
QUIET = {"DO_NOT_TRACK": "", "CADGEN_TELEMETRY": "", NOTICE_ENV: "", **TOLD}


class _Tmp(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.path = self.tmp / "settings.json"
        environment = mock.patch.dict("os.environ", QUIET)
        environment.start()
        self.addCleanup(environment.stop)
        # No test reaches the real receiver: a deletion is heard at once unless a test says otherwise.
        self.deleted: list[str] = []
        deletion = mock.patch("cadgen.analytics.request_deletion", side_effect=lambda id: self.deleted.append(id) or True)
        deletion.start()
        self.addCleanup(deletion.stop)
        # What a recorder does in the background (an opt-out's deletion) ends inside the test, under its mocks:
        # a thread still running after them would ask the real receiver.
        begun: list[threading.Thread] = []
        background = Recorder._background
        threads = mock.patch.object(Recorder, "_background", lambda recorder, work: begun.append(background(recorder, work)) or begun[-1])
        threads.start()
        self.addCleanup(threads.stop)
        self.addCleanup(lambda: [thread.join(10) for thread in begun])

    def serve(self, channel: str, client: str = "codex-mcp-client") -> tuple[Server, list[dict]]:
        sent: list[dict] = []
        # The channel the plugin's startup command named, as the server hands it on (`cadgen/_internal/channel.py`).
        with mock.patch.dict("os.environ", {"CADGEN_INSTALL_CHANNEL": channel}):
            recorder = Recorder(path=self.path, send=lambda payload: sent.append(payload) or True)
        (self.tmp / "app").mkdir(exist_ok=True)
        server = Server(page=AppPage(self.tmp / "app"), recents=RecentStore(self.tmp / "state"),
                        analytics=recorder)
        server.handle("initialize", initialize_params({"protocolVersion": "2025-06-18", "capabilities": {},
                                     "clientInfo": {"name": client, "version": "0.159.0"}}), None)
        return server, sent

    def call(self, server: Server, name: str, arguments: dict | None = None) -> dict:
        context = RequestContext(1, {"threadId": "t"})
        arguments = dict(arguments or {})
        if name in ("cad_sync", "cad_capture_reply"):  # as the page sends them: with its app capability
            arguments.setdefault("app", server._app_token)
        return server.handle("tools/call", {"name": name, "arguments": arguments}, context)

    def http(self, server: Server, method: str, url: str, body: dict | None = None, *, agent: bool = False) -> tuple[int, dict | None]:
        """A request the page sends through ``cad_http`` (a POST with the header its client sends)."""
        headers = {"x-cadgen-viewer": "1", "content-type": "application/json"} if body is not None else {}
        if not agent:
            headers["x-cadgen-app"] = server._app_token
        reply = self.call(server, "cad_http", {"method": method, "url": url, "headers": headers,
                                               "body": base64.b64encode(json.dumps(body).encode() if body is not None else b"").decode("ascii")})
        data = base64.b64decode(reply["structuredContent"].get("body") or "")
        return reply["structuredContent"]["status"], json.loads(data) if data else None

    def consent(self, server: Server, share: bool | None = None) -> dict:
        """The app menu's Share anonymous usage data toggle: read, or the person's answer."""
        if share is None:
            return self.http(server, "GET", "/__cad/analytics")[1]
        return self.http(server, "POST", "/__cad/analytics", {"share": share})[1]


class ConsentTest(_Tmp):
    def test_nothing_is_sent_and_no_id_made_until_the_person_is_told_or_says_yes(self) -> None:
        self.assertEqual(status(path=self.path), {"sharing": False, "reason": "untold", "id": None})
        self.assertFalse(self.path.exists())  # no id for someone who was never told
        choose(True, by="app", path=self.path)
        agreed = status(path=self.path)
        self.assertEqual((agreed["sharing"], agreed["reason"]), (True, "choice"))
        self.assertEqual(status(path=self.path)["id"], agreed["id"])  # one id, kept
        self.assertEqual(set(json.loads(self.path.read_text(encoding="utf-8"))["telemetry"]),
                         {"choice", "disclosure", "by", "decidedAt", "id"}, "the id, and nothing kept beside it")

    def test_ci_and_a_development_install_send_nothing_by_default_even_where_the_person_was_told(self) -> None:
        self.assertTrue(notify(io.StringIO(), path=self.path))  # told, by a plugin's command
        self.assertEqual(status(path=self.path)["reason"], "default")
        for name, value in (("CI", "true"), ("CADGEN_INSTALL_CHANNEL", "dev")):
            with self.subTest(name=name), mock.patch.dict("os.environ", {name: value}):
                self.assertEqual(status(path=self.path), {"sharing": False, "reason": "untold", "id": None})
                choose(True, by="cli", path=self.path)  # a yes holds anywhere
                self.assertTrue(status(path=self.path)["sharing"])
                choose(False, by="cli", path=self.path, forget=lambda id: True)
                self.path.write_text(json.dumps({"telemetry": {"notifiedAt": time.time(), "notice": 1}}), encoding="utf-8")

    def test_off_forgets_the_id_and_the_environment_beats_the_choice(self) -> None:
        forgotten = []
        choose(True, by="cli", path=self.path)
        first = status(path=self.path)["id"]
        self.assertTrue(first)
        self.assertEqual(choose(False, by="app", path=self.path, forget=lambda id: forgotten.append(id) or True),
                         {"saved": True, "sharing": False, "forgotten": True})
        self.assertEqual(forgotten, [first])  # the receiver is asked to delete it
        self.assertEqual(status(path=self.path), {"sharing": False, "reason": "choice", "id": None})
        self.assertNotIn(first, self.path.read_text(encoding="utf-8"))
        choose(True, by="cli", path=self.path)
        self.assertNotEqual(status(path=self.path)["id"], first)  # on again is a new install
        # An opt-out the receiver did not hear is asked for again until it is, by id, and nothing else.
        choose(True, by="cli", path=self.path)
        offline = status(path=self.path)["id"]
        self.assertEqual(choose(False, by="app", path=self.path, forget=lambda id: False)["forgotten"], False)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["telemetry"]["forget"], [offline])
        self.assertEqual(status(path=self.path)["id"], None)
        heard = []
        forget_pending(path=self.path, forget=lambda id: heard.append(id) or True)
        self.assertEqual(heard, [offline])
        self.assertNotIn("forget", json.loads(self.path.read_text(encoding="utf-8"))["telemetry"])
        choose(True, by="cli", path=self.path)
        # A yes to less than is sent now counts as no answer; a no is never undone.
        with mock.patch("cadgen.analytics.DISCLOSURE", 2):
            self.assertEqual(status(path=self.path)["reason"], "untold")
            choose(False, by="app", path=self.path, forget=lambda id: True)
        with mock.patch("cadgen.analytics.DISCLOSURE", 3):
            self.assertEqual(status(path=self.path)["reason"], "choice")
        for name, value in (("DO_NOT_TRACK", "1"), ("CADGEN_TELEMETRY", "off")):
            with self.subTest(name=name), mock.patch.dict("os.environ", {name: value}):
                self.assertEqual(status(path=self.path)["reason"], "environment")
                self.assertFalse(status(path=self.path)["sharing"])


class NoMeansNoTest(_Tmp):
    """A no is kept, and nothing undoes it."""

    def test_a_no_survives_restarts_updates_and_a_larger_disclosure(self) -> None:
        choose(False, by="app", path=self.path)  # the menu's toggle, `cadgen telemetry off`, or the agent
        no = {"sharing": False, "reason": "choice", "id": None}
        self.assertEqual(status(path=self.path), no)  # a restart: read from the state directory again
        with mock.patch("cadgen.analytics.SCHEMA", 2):  # an update that changes what a batch looks like
            self.assertEqual(status(path=self.path), no)
        with mock.patch("cadgen.analytics.DISCLOSURE", 99), mock.patch("cadgen.analytics.NOTICE", 99):  # one that sends more
            self.assertEqual(status(path=self.path), no)
            self.assertFalse(notify(io.StringIO(), path=self.path))  # nothing to tell someone who said no

    def test_where_no_answer_could_be_kept_nothing_is_said(self) -> None:
        # A file where the state folder would go: no folder can be made, on any platform or user.
        (self.tmp / "taken").write_text("", encoding="utf-8")
        self.assertEqual(status(path=self.tmp / "taken" / "state" / "settings.json")["reason"], "unavailable")
        said = io.StringIO()  # said on every command, it would be noise: never said at all
        self.assertFalse(notify(said, path=self.tmp / "taken" / "state" / "settings.json"))
        self.assertEqual(said.getvalue(), "")
        self.assertEqual(status(path=self.path)["reason"], "untold")
        self.assertEqual(list(self.tmp.glob("settings.json*")), [], "the try leaves nothing behind")
        # The lock every write takes, unopenable (a folder in its place): as good as no folder.
        (self.tmp / "locked").mkdir()
        (self.tmp / "locked" / "settings.lock").mkdir()
        self.assertEqual(status(path=self.tmp / "locked" / "settings.json")["reason"], "unavailable")


class OneAnswerTest(_Tmp):
    """The answer is one, shared by every app and process: none of them undoes another's."""

    def section(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))["telemetry"]

    def test_an_answer_given_meanwhile_is_never_undone(self) -> None:
        choose(True, by="cli", path=self.path)
        choose(False, by="app", path=self.path)  # its id is owed a deletion
        [owed] = self.section()["forget"]

        def meanwhile(install_id: str) -> bool:  # the other app's yes, while this one waits on the receiver
            choose(True, by="viewer", path=self.path)
            return True

        forget_pending(path=self.path, forget=meanwhile)
        self.assertEqual((self.section()["choice"], "forget" in self.section()), ("on", False))
        self.assertNotEqual(self.section()["id"], owed)
        # Settings that are there but cannot be read now are neither asked about nor written over.
        before = self.path.read_bytes()
        with mock.patch("cadgen.settings.Path.read_text", side_effect=PermissionError("held")):
            self.assertEqual(status(path=self.path)["reason"], "unavailable")
            self.assertFalse(choose(False, by="app", path=self.path)["saved"])
        self.assertEqual(self.path.read_bytes(), before)

    def test_an_off_is_kept_before_the_receiver_is_asked(self) -> None:
        choose(True, by="cli", path=self.path)

        def interrupted(install_id: str) -> bool:  # Ctrl-C while the receiver is asked
            self.assertFalse(status(path=self.path)["sharing"])
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            choose(False, by="cli", path=self.path, forget=interrupted)
        self.assertEqual((status(path=self.path)["sharing"], len(self.section()["forget"])), (False, 1))

    def test_a_batch_that_lands_after_an_opt_out_is_deleted_too(self) -> None:
        choose(True, by="cli", path=self.path)
        first = status(path=self.path)["id"]

        def lands_late(payload: dict) -> bool:  # the other app's no reached the receiver first
            choose(False, by="viewer", path=self.path, forget=lambda install_id: True)
            return True

        recorder = Recorder(path=self.path, send=lands_late)
        recorder.called("cad_show", True)
        self.assertTrue(recorder.flush())
        self.assertEqual(self.section()["forget"], [first])  # owed a deletion again

    def test_use_noted_before_a_yes_in_the_other_app_is_never_sent(self) -> None:
        sent: list[dict] = []
        # One reading for every clock call: Windows' clock moves in 16 ms steps, so a quick yes shares the batch's time.
        with mock.patch("cadgen.analytics.time.time", return_value=1_790_000_000.0):
            recorder = Recorder(path=self.path, send=lambda payload: sent.append(payload) or True)
            recorder.called("cad_show", True)  # before any answer
            choose(True, by="viewer", path=self.path)  # the other app's yes
            self.assertFalse(recorder.flush())
            recorder.called("cad_show", True)
            self.assertTrue(recorder.flush())
        self.assertEqual(len(sent), 1)

    def test_only_a_page_answers_and_its_toggle_changes_it_whenever(self) -> None:
        server, sent = self.serve("claude-github", client="some-terminal-agent")
        self.assertEqual(self.http(server, "POST", "/__cad/analytics", {"share": True}, agent=True)[0], 403)
        self.assertEqual(status(path=self.path)["reason"], "untold")
        server, sent = self.serve("claude-github")
        self.consent(server, True)
        self.assertTrue(status(path=self.path)["sharing"])
        self.consent(server, False)  # the app menu's toggle changes it whenever
        self.assertFalse(status(path=self.path)["sharing"])

    def test_the_environment_turns_it_on_too(self) -> None:
        with mock.patch.dict("os.environ", {"CADGEN_TELEMETRY": "1"}):
            found = status(path=self.path)
        self.assertEqual((found["sharing"], found["reason"]), (True, "environment"))
        self.assertTrue(found["id"])


class ServerCountsTest(_Tmp):
    def test_a_yes_sends_use_files_counted_and_metadata_and_nothing_the_person_made(self) -> None:
        server, sent = self.serve("claude-directory")
        self.assertNotIn("ask", self.consent(server))  # nothing in a CAD app asks: a command tells
        self.consent(server, True)
        secret, plate = self.tmp / "secret-bracket.step", self.tmp / "secret-plate.STL"
        secret.write_text("ISO-10303-21;", encoding="utf-8")
        plate.write_bytes(b"solid t\nendsolid t\n")
        self.call(server, "cad_open", {"source": str(secret)})  # the agent opens one
        # The view adds the models it shows to the library (one a person browsed to as well): files
        # worked on. The home's re-reads of the library are plumbing, never counted.
        for model in (secret, plate):
            self.http(server, "POST", "/__cad/recents", {"action": "open", "path": str(model)})
        self.http(server, "GET", "/__cad/recents")
        # A view's syncs: plumbing, never a tool count. One nobody touched notes nothing (a view left
        # open sends nothing); a touch is view activity.
        for _ in range(3):
            self.call(server, "cad_sync", {"view": "v", "surface": "thread", "model": str(self.tmp / "secret-idle.step")})
        self.call(server, "cad_sync", {"view": "v", "surface": "thread", "model": str(plate), "focused": True})
        self.assertTrue(server.analytics.flush())
        [payload] = sent
        # One event per thing counted, its counts added up: the files by format, never by name.
        self.assertEqual(payload["events"], [
            {"name": "files", "kind": "step", "count": 1},
            {"name": "files", "kind": "stl", "count": 1},
            {"name": "tool", "tool": "cad_open", "calls": 1, "errors": 0},
            {"name": "view", "calls": 1},
        ])
        self.assertEqual((payload["schema"], payload["process"], payload["channel"], payload["presentation"],
                          payload["client"]["name"]), (8, "app", "claude-directory", "tabs", "codex-mcp-client"))
        # Under an id of its own, stamped with the time it was made: a random id, and a whole second.
        self.assertEqual(str(uuid.UUID(payload["batch"], version=4)), payload["batch"])
        self.assertIsInstance(payload["at"], int)
        self.assertLessEqual(abs(payload["at"] - time.time()), 60)
        self.assertNotIn("secret", json.dumps(payload))
        self.assertNotIn(str(self.tmp), json.dumps(payload))
        # A batch with no use is not sent.
        self.call(server, "cad_sync", {"view": "v", "surface": "thread", "model": str(secret)})
        self.assertFalse(server.analytics.flush())
        self.assertEqual(len(sent), 1)
        # A host's free-text name becomes a token the receiver takes: ASCII, as its check reads it.
        recorder = Recorder(path=self.path)
        recorder.started(client={"name": "Café Studio", "version": "1.105 (Universal)"}, presentation="inline")
        self.assertEqual(recorder._context["client"], {"name": "Caf-Studio", "version": "1.105-Universal-"})

    def test_a_views_controls_are_counted_by_name_and_seconds_only_with_consent(self) -> None:
        # The page's report of what a person used (`@text-to-cad/ui`'s `usage/controls.js`), through the CAD app's
        # own route: counted only under the person's yes.
        server, sent = self.serve("claude-directory")
        report = {"controls": [{"control": "pencil", "count": 2, "seconds": 95}, {"control": "display_xray", "count": 1, "seconds": 0}]}
        self.assertEqual(self.http(server, "POST", "/__cad/analytics/activity", report)[0], 204)
        self.assertFalse(server.analytics.flush(), "nobody told, nothing said yes: nothing goes")
        self.consent(server, True)
        for activity in (report, {"controls": [
            {"control": "pencil", "count": 0, "seconds": 300},  # on all the next minute: its seconds alone
            {"control": "secret-bracket.step", "count": 1, "seconds": 0},  # a name not on the list
            {"control": "display_mode", "count": 1, "seconds": 0, "value": "xray"},  # nothing beside the three
            {"control": "measure", "count": 1.5, "seconds": 0}, {"control": "measure", "count": True, "seconds": 0},
            {"control": "clip", "count": 1, "seconds": 7200},  # more than one report says
            {"control": "explode", "count": 0, "seconds": 0},
        ]}):
            self.assertEqual(self.http(server, "POST", "/__cad/analytics/activity", activity)[0], 204)
        # The agent cannot speak for the person's hands.
        self.assertEqual(self.http(server, "POST", "/__cad/analytics/activity", report, agent=True)[0], 403)
        self.assertTrue(server.analytics.flush())
        self.assertEqual(sent[-1]["schema"], 8)
        self.assertEqual([event for event in sent[-1]["events"] if event["name"] == "control"], [
            {"name": "control", "control": "display_xray", "count": 1, "seconds": 0},
            {"name": "control", "control": "pencil", "count": 2, "seconds": 395},
        ])
        self.assertNotIn("secret", json.dumps(sent))
        # Off, nothing more is noted or sent.
        self.consent(server, False)
        self.http(server, "POST", "/__cad/analytics/activity", report)
        self.assertFalse(server.analytics.flush())
        self.assertEqual(len(sent), 1)

    def test_a_window_of_controls_goes_in_one_batch(self) -> None:
        # One event per control a window used, beside the rest: past schema 6's 64, within one batch.
        choose(True, by="cli", path=self.path)
        sent: list[dict] = []
        recorder = Recorder(process="viewer", path=self.path, send=lambda payload: sent.append(payload) or True)
        from cadgen.analytics import CONTROLS
        for control in sorted(CONTROLS):
            recorder.controlled(control, 1)
        self.assertTrue(recorder.flush())
        self.assertEqual(len(sent[0]["events"]), len(CONTROLS))
        self.assertLessEqual(len(json.dumps(sent[0]).encode()), 64 * 1024, "the receiver's MAX_BYTES")
        self.assertFalse(recorder.flush(), "all of it went")

    def test_a_server_nobody_used_sends_nothing(self) -> None:
        # Codex starts a server per thread, and some only to list tools: none of them is a user.
        server, sent = self.serve("claude-directory")
        self.consent(server, True)
        self.call(server, "cad_sync", {"view": "v", "surface": "sidebar"})
        self.assertFalse(server.analytics.flush())
        server.analytics.close()
        self.assertEqual(sent, [])

    def test_a_batch_the_receiver_did_not_take_is_sent_again_whole_before_anything_newer(self) -> None:
        # Offline twice, then back: the receiver may have taken a batch whose answer was lost, so the batch goes
        # again byte for byte, its id and all, and what came since goes in a later batch of its own.
        answers: list = [False, False, True, True, "refused", True]
        sent: list[str] = []
        choose(True, by="cli", path=self.path)
        recorder = Recorder(path=self.path, send=lambda payload: sent.append(json.dumps(payload)) or answers.pop(0))
        recorder.called("cad_show", True)
        recorder.opened("/work/a.step")
        self.assertFalse(recorder.flush())  # offline: kept whole
        recorder.called("cad_show", False, "no_file")
        self.assertFalse(recorder.flush())  # still offline: the kept one is all that is tried
        self.assertEqual(sent, [sent[0]] * 2)
        recorder.called("cad_view", True)
        self.assertTrue(recorder.flush())
        self.assertEqual(sent[:3], [sent[0]] * 3)
        first, later = json.loads(sent[0]), json.loads(sent[3])
        self.assertEqual(first["events"], [{"name": "files", "kind": "step", "count": 1},
                                           {"name": "tool", "tool": "cad_show", "calls": 1, "errors": 0}])
        self.assertNotEqual(later["batch"], first["batch"])
        self.assertEqual(later["events"], [{"name": "tool", "tool": "cad_show", "calls": 1, "errors": 1},
                                           {"name": "tool", "tool": "cad_view", "calls": 1, "errors": 0},
                                           {"name": "tool_failure", "tool": "cad_show", "reason": "no_file", "count": 1}])
        # One the receiver refused (a 4xx) is dropped: sent again, it would take what comes next down with it.
        recorder.called("cad_view", True)
        self.assertFalse(recorder.flush())
        recorder.called("cad_show", True)
        self.assertTrue(recorder.flush())
        self.assertEqual([event["tool"] for event in json.loads(sent[5])["events"]], ["cad_show"])
        self.assertEqual(len(sent), 6)

    def test_a_batch_not_taken_is_kept_whole_at_exit_and_dropped_by_a_no(self) -> None:
        sent: list[str] = []
        answers: list = [False]
        choose(True, by="cli", path=self.path)
        recorder = Recorder(path=self.path, send=lambda payload: sent.append(json.dumps(payload)) or answers.pop(0))
        recorder.called("cad_show", True)
        self.assertFalse(recorder.flush())
        recorder.called("cad_view", True)
        recorder.close()  # the batch owed, then what came since: each whole, in that order
        following: list[str] = []
        Recorder(path=self.path, send=lambda payload: following.append(json.dumps(payload)) or True).send_kept()
        self.assertEqual(following[0], sent[0])
        self.assertEqual([event["tool"] for event in json.loads(following[1])["events"]], ["cad_view"])
        self.assertEqual(len(following), 2)
        # A no said elsewhere while a batch is owed: never sent, nor kept.
        answers.append(False)
        recorder = Recorder(path=self.path, send=lambda payload: sent.append(json.dumps(payload)) or answers.pop(0))
        recorder.called("cad_show", True)
        self.assertFalse(recorder.flush())
        choose(False, by="cli", path=self.path, forget=lambda id: True)
        self.assertFalse(recorder.flush())
        recorder.close()
        self.assertEqual(len(sent), 2)
        self.assertFalse((self.tmp / KEPT).exists())

    def test_a_batch_on_its_way_as_the_process_exits_is_kept_whole(self) -> None:
        # The exit comes while the send is still out; it fails after: the batch is kept all the same, as it was.
        choose(True, by="cli", path=self.path)
        out, exiting, sent = threading.Event(), threading.Event(), []

        def send(payload: dict) -> bool:
            sent.append(json.dumps(payload))
            out.set()
            exiting.wait(10)
            return False

        recorder = Recorder(path=self.path, send=send)
        recorder.called("cad_show", True)
        flushing = threading.Thread(target=recorder.flush)
        flushing.start()
        self.assertTrue(out.wait(10))
        recorder.close()
        exiting.set()
        flushing.join(10)
        following: list[str] = []
        Recorder(path=self.path, send=lambda payload: following.append(json.dumps(payload)) or True).send_kept()
        self.assertEqual(following, sent)

    def test_a_failed_call_says_why_by_a_word_chosen_where_it_failed_never_what_it_said(self) -> None:
        server, sent = self.serve("claude-directory")
        self.consent(server, True)
        notes = self.tmp / "secret-notes.txt"
        notes.write_text("not CAD", encoding="utf-8")
        for arguments in ({}, {"source": "secret.step"}, {"source": str(self.tmp / "secret-missing.step")}, {"source": str(notes)}):
            self.assertTrue(self.call(server, "cad_open", arguments)["isError"])
        self.assertTrue(self.call(server, "cad_screenshot", {"view": "cad-1-gone"})["isError"])  # no viewer in this thread
        with mock.patch.object(Server, "_tool_cad_view", side_effect=KeyError("secret")), self.assertRaises(KeyError):
            self.call(server, "cad_view", {})  # cadgen's own bug: a crash, and a reason
        self.assertTrue(server.analytics.flush())
        [payload] = sent
        failures = {(event["tool"], event["reason"]): event["count"] for event in payload["events"] if event["name"] == "tool_failure"}
        self.assertEqual(failures, {("cad_open", "no_path"): 1, ("cad_open", "relative_path"): 1, ("cad_open", "no_file"): 1,
                                    ("cad_open", "not_cad"): 1, ("cad_screenshot", "no_view"): 1, ("cad_view", "bug"): 1})
        tools = {event["tool"]: event["errors"] for event in payload["events"] if event["name"] == "tool"}
        self.assertEqual(tools, {"cad_open": 4, "cad_screenshot": 1, "cad_view": 1})
        self.assertEqual([event["type"] for event in payload["events"] if event["name"] == "exception"], ["KeyError"])
        self.assertNotIn("secret", json.dumps(payload))
        # A reason outside the vocabulary is no reason: counted as ``other``, never sent as given.
        server.analytics.called("cad_show", False, "No file at /Users/someone/secret.step")
        server.analytics.flush()
        self.assertIn({"name": "tool_failure", "tool": "cad_show", "reason": "other", "count": 1}, sent[-1]["events"])

    def test_a_call_no_tool_answered_is_a_failed_call_never_by_a_name_cadgen_has_no_tool_by(self) -> None:
        # Answered with an error before any tool runs, each is counted all the same: a tool of cadgen's this host was
        # not listed (a text host shows no views) as its own, no view; a name cadgen has no tool by, or none at all,
        # as `cad_unknown`'s -- never the host's string; arguments that are no object as that tool's bad request.
        server, sent = self.serve("claude-directory", client="some-agent")
        self.assertTrue(server.text, "no extension, no known launcher: a text host")
        choose(True, by="cli", path=self.path)
        context = RequestContext(1, {"threadId": "t"})
        for params in ({"name": "cad_view", "arguments": {}}, {"name": "cad_secret_bracket", "arguments": {}},
                       {"name": None}, {"name": "cad_show", "arguments": ["secret"]}):
            with self.subTest(params=params), self.assertRaises(RpcError) as refused:
                server.handle("tools/call", params, context)
            self.assertEqual(refused.exception.code, -32602)
        self.assertTrue(server.analytics.flush())
        [payload] = sent
        self.assertEqual(payload["events"], [
            {"name": "tool", "tool": "cad_show", "calls": 1, "errors": 1},
            {"name": "tool", "tool": "cad_unknown", "calls": 2, "errors": 2},
            {"name": "tool", "tool": "cad_view", "calls": 1, "errors": 1},
            {"name": "tool_failure", "tool": "cad_show", "reason": "bad_request", "count": 1},
            {"name": "tool_failure", "tool": "cad_unknown", "reason": "bad_request", "count": 2},
            {"name": "tool_failure", "tool": "cad_view", "reason": "no_view", "count": 1},
        ])
        self.assertNotIn("secret", json.dumps(payload))

    def test_every_failure_names_its_reason_where_it_is_raised_from_the_vocabulary(self) -> None:
        import ast
        import inspect

        from cadgen import analytics
        from cadgen.mcp import server as server_module, views

        # Each ToolFailed and NoAnswer names its reason as a word where it is raised, never a message.
        named = set()
        for module in (server_module, views):
            for node in ast.walk(ast.parse(inspect.getsource(module))):
                if isinstance(node, ast.Call) and getattr(node.func, "id", None) in ("ToolFailed", "NoAnswer"):
                    self.assertEqual(len(node.args), 2, ast.unparse(node))
                    reason = node.args[1]
                    if isinstance(reason, ast.Constant):
                        named.add(reason.value)
                    else:  # a NoAnswer's, passed on
                        self.assertEqual(ast.unparse(reason), "failure.reason")
        self.assertLessEqual(named | {"bug"}, analytics.FAILURES)

    def test_a_batch_that_failed_while_the_person_chose_is_not_kept_past_the_choice(self) -> None:
        sent: list[dict] = []
        # Two answers can share a clock tick (Windows' is 16 ms): what a batch keeps follows this process's
        # own choices, not their times.
        with mock.patch("cadgen.analytics.time.time", return_value=1_790_000_000.0):
            choose(True, by="cli", path=self.path)
            first = status(path=self.path)["id"]

            def answer(payload: dict) -> bool:
                sent.append(payload)
                if len(sent) == 1:  # the person says no, then yes, while this batch is on its way
                    recorder.choose(False, by="app")
                    recorder.choose(True, by="app")
                    recorder.called("cad_view", True)
                    recorder.opened(str(self.tmp / "new.step"))
                    return False
                return True

            recorder = Recorder(path=self.path, send=answer)
            recorder.called("cad_show", False)
            recorder.opened(str(self.tmp / "old.step"))
            self.assertFalse(recorder.flush())
            self.assertTrue(recorder.flush())

        self.assertNotEqual(sent[1]["install"], first)
        self.assertEqual(sent[1]["events"], [{"name": "files", "kind": "step", "count": 1},
                                             {"name": "tool", "tool": "cad_view", "calls": 1, "errors": 0}])
        self.assertFalse(recorder.flush())

    def test_only_a_receiver_that_read_the_batch_refuses_it(self) -> None:
        # A 404 (no receiver deployed there yet), a firewall's 403, a 429 or a 5xx is no refusal: the batch,
        # or the deletion an opt-out owes, is kept and tried again. A 400 means it was read: dropped.
        codes = iter([404, 403, 429, 503, 400])

        class Answer(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                self.rfile.read(int(self.headers["content-length"]))
                self.send_response(next(codes))
                self.send_header("content-length", "0")
                self.end_headers()

            def log_message(self, *args) -> None:
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Answer)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_address[1]}/v1/events"
        self.assertEqual([_post(url, {}) for _ in range(5)], ["failed", "failed", "failed", "failed", "refused"])

    def test_files_are_counted_once_a_day_by_format_and_never_named(self) -> None:
        sent: list[dict] = []
        choose(True, by="cli", path=self.path)
        recorder = Recorder(path=self.path, send=lambda payload: sent.append(payload) or True)
        for name in ("/work/a.step", "/work/./a.step", "/work/b.STP", "/work/c.stl", "/work/notes.txt"):
            recorder.opened(name)  # one file however a view spells it; a file CAD does not show is none
        self.assertTrue(recorder.flush())
        self.assertEqual(sent[-1]["events"], [{"name": "files", "kind": "step", "count": 2},
                                              {"name": "files", "kind": "stl", "count": 1}])
        recorder.opened("/work/a.step")  # shown again today: counted already
        self.assertFalse(recorder.flush())
        with mock.patch("cadgen.analytics._day", return_value="2999-01-01"):
            recorder.opened("/work/a.step")  # a new day's
        self.assertTrue(recorder.flush())
        self.assertEqual(sent[-1]["events"], [{"name": "files", "kind": "step", "count": 1}])
        self.assertNotIn("/work", json.dumps(sent))
        # Past a day's room, a process tells files apart no more; past a batch's, events wait for the next.
        with mock.patch("cadgen.analytics.FILES_PER_DAY", 3), mock.patch("cadgen.analytics._day", return_value="3000-01-01"):
            for index in range(5):
                recorder.opened(f"/work/part-{index}.glb")
        with mock.patch("cadgen.analytics.MAX_EVENTS", 2):
            for tool in ("cad_open", "cad_show"):
                recorder.called(tool, True)
            self.assertTrue(recorder.flush())
            self.assertTrue(recorder.flush())
        self.assertEqual([[event["name"] for event in payload["events"]] for payload in sent[-2:]],
                         [["files", "tool"], ["tool"]])
        self.assertEqual(sent[-2]["events"][0], {"name": "files", "kind": "glb", "count": 3})

    def test_counts_go_from_the_notice_on_without_a_restart(self) -> None:
        server, sent = self.serve("claude-github")
        self.call(server, "cad_show", {"source": "a.step"})
        self.assertEqual(self.consent(server), {"sharing": False, "reason": "untold", "policy": PRIVACY_URL})
        self.assertFalse(server.analytics.flush())
        self.call(server, "cad_view")  # noted before anyone was told
        self.assertTrue(notify(io.StringIO(), path=self.path))  # a skill's first `cadgen` command
        # The running CAD app sends from the notice on, with no restart -- and never what it noted before.
        self.assertEqual(self.consent(server), {"sharing": True, "reason": "default", "policy": PRIVACY_URL})
        self.assertFalse(server.analytics.flush())
        self.assertEqual(sent, [])
        model = self.tmp / "bracket.step"
        model.write_text("ISO-10303-21;", encoding="utf-8")
        self.call(server, "cad_view")
        self.http(server, "POST", "/__cad/recents", {"action": "open", "path": str(model)})
        self.assertTrue(server.analytics.flush())
        self.assertEqual(sent[0]["events"], [{"name": "files", "kind": "step", "count": 1},
                                             {"name": "tool", "tool": "cad_view", "calls": 1, "errors": 0}])
        self.assertEqual(sent[0]["install"], status(path=self.path)["id"])

    def test_the_agent_can_turn_telemetry_off_but_not_on_without_any_view(self) -> None:
        for client in ("codex-mcp-client", "some-cli"):
            with self.subTest(client=client):
                server, sent = self.serve("claude-directory", client)
                server.analytics.choose(True, by="app")
                identity = status(path=self.path)["id"]
                deleted = threading.Event()
                def delete(ident):
                    self.deleted.append(ident)
                    deleted.set()
                    return True
                deletion = mock.patch("cadgen.analytics.request_deletion", side_effect=delete)
                deletion.start()
                self.addCleanup(deletion.stop)
                self.assertEqual(self.http(server, "GET", "/__cad/analytics", agent=True)[1]["sharing"], True)
                with mock.patch.object(server.analytics, "choose", wraps=server.analytics.choose) as choose:
                    code, off = self.http(server, "POST", "/__cad/analytics", {"share": False}, agent=True)
                    choose.assert_called_once_with(False, by="agent")
                self.assertEqual(code, 200)
                self.assertEqual((off["sharing"], off["saved"]), (False, True))
                self.assertFalse(status(path=self.path)["sharing"])
                self.assertNotIn("id", json.loads(self.path.read_text(encoding="utf-8"))["telemetry"])
                # Wait for the actual deletion worker, not a clock interval.
                self.assertTrue(deleted.wait(10))
                deletion.stop()
                self.assertIn(identity, self.deleted)
                self.assertEqual(self.http(server, "POST", "/__cad/analytics", {"share": True}, agent=True)[0], 403)
                for payload in ({"share": 0}, {}, {"share": False, "by": "app"}, {"share": "false"}):
                    self.assertEqual(self.http(server, "POST", "/__cad/analytics", payload, agent=True)[0], 403)
                server.analytics.flush()
                self.assertEqual(sent, [])
                with self.assertRaisesRegex(RpcError, "unknown tool"):
                    self.call(server, "cad_telemetry")

    def test_agent_opt_out_reports_when_the_choice_cannot_be_saved(self) -> None:
        server, _ = self.serve("claude-directory")
        server.analytics.choose(True, by="app")
        with mock.patch("cadgen.settings.write_bytes_atomic", side_effect=OSError("read only")):
            code, answer = self.http(server, "POST", "/__cad/analytics", {"share": False}, agent=True)
        self.assertEqual((code, answer["sharing"], answer["saved"]), (200, False, False))


class SenderTest(_Tmp):
    """Every batch says who sent it (``PROCESSES``), whichever process holds the recorder: the engine
    serves the browser viewer's page and the CAD app's sessions alike, each with a recorder of its own, and
    what commands and scripts counted goes as `cli`, whichever of them sends it."""

    def engine(self, send):
        """The engine's two recorders (``EngineApp``): the CAD app's sessions' and the browser viewer's page's, over
        this test's settings, sending through ``send``."""
        import types

        from cadgen.viewer import engine_app

        def made(**options):
            return Recorder(**{**options, "path": self.path, "send": send})

        server = types.SimpleNamespace(port=4242, touch=mock.Mock(), url="http://127.0.0.1:4242")
        with mock.patch("cadgen.analytics.Recorder", side_effect=made):
            engine = engine_app.EngineApp(server, "127.0.0.1")
        self.addCleanup(engine.analytics.close)
        self.addCleanup(engine.viewer_analytics.close)
        return engine

    def test_each_batch_names_its_sender(self) -> None:
        from cadgen import __version__
        from cadgen.viewer import engine_app

        choose(True, by="cli", path=self.path)
        sent: list[dict] = []
        engine = self.engine(lambda payload: sent.append(payload) or True)
        with mock.patch.object(engine_app, "ViewerApp"):
            page = engine.default_app(dist=str(self.tmp))
        self.assertIs(page.analytics, engine.viewer_analytics, "the browser viewer's page counts as the viewer")
        for recorder in (page.analytics, engine.analytics):  # the page's, then the CAD app's sessions'
            recorder.viewed()
            self.assertTrue(recorder.flush())
        # The sender a command starts sends as `cli` (``test_engine_telemetry``).
        viewer, app = sent
        self.assertEqual([viewer["process"], app["process"]], ["viewer", "app"])
        # The viewer's batches are the browser page's usage: their client is the viewer itself, of this version, shown
        # in a browser -- as `cadgen viewer` said of itself before the engine served its page, and as PostHog tells
        # the viewer's use from the apps' by client. The CAD app's names the agent app a session's initialize does
        # (``Server``), none before.
        self.assertEqual((viewer["client"], viewer["presentation"]),
                         ({"name": "cadgen-viewer", "version": __version__}, "browser"))
        self.assertEqual([key for key in ("client", "presentation") if key in app], [])

    def test_a_batch_names_the_version_its_installation_runs_as(self) -> None:
        # A development install's own `<version>-dev.<time>` (what the `cadgen` command tells it, and its engine is
        # named by): a send forced from one is told apart from the release's, which names its own.
        from cadgen import __version__

        choose(True, by="cli", path=self.path)
        for named, version in (("0.8.0-dev.20261026120000", "0.8.0-dev.20261026120000"), ("", __version__)):
            sent: list[dict] = []
            with self.subTest(named=named), mock.patch.dict("os.environ", {"CADGEN_INSTALLATION_VERSION": named}):
                recorder = Recorder(path=self.path, send=sent.append)
                recorder.called("cad_show", True)
                recorder.flush()
                self.assertEqual([payload["version"] for payload in sent], [version])

    def test_what_commands_and_scripts_counted_goes_as_a_cli_batch_never_in_an_apps(self) -> None:
        """The spool holds what `python model.py` and `cadgen` commands counted: builds, the engine's health, a worker
        that died, a command's crash. The recorder that drains it -- the engine's for the CAD app's sessions, or
        the viewer's -- sends it as a batch of its own, the process `cli`, naming no client or presentation: no
        agent app built any of it, and its own batch keeps saying which one looked."""
        choose(True, by="cli", path=self.path)
        sent: list[dict] = []
        engine = self.engine(lambda payload: sent.append(payload) or True)
        app, viewer = engine.analytics, engine.viewer_analytics
        app.started(client={"name": "codex-mcp-client", "version": "0.159.0"}, presentation="tabs")  # a session's initialize
        app.called("cad_show", True)
        self.assertTrue(spool({"builds": [{"kind": "xbf", "via": "script", "outcome": "crashed", "seconds": 1.5}],
                               "health": {"workers": 1, "crashes": 1}, "crashes": [died(-11)]}, path=self.path))
        self.assertTrue(app.flush())
        commands, own = sent  # the spool's batch, then the app's own
        self.assertEqual((commands["process"], commands["schema"], commands["version"], commands["channel"]),
                         ("cli", own["schema"], own["version"], own["channel"]))
        self.assertEqual({key for key in ("client", "presentation") if key in commands}, set())
        self.assertEqual([event["name"] for event in commands["events"]], ["build", "health", "exception"])
        self.assertEqual((commands["events"][0]["via"], commands["events"][2]["type"]), ("script", "WorkerDied"))
        self.assertEqual((own["process"], own["client"]["name"], own["presentation"], own["events"]),
                         ("app", "codex-mcp-client", "tabs", [{"name": "tool", "tool": "cad_show", "calls": 1, "errors": 0}]))
        # Two batches of one install, each under an id of its own, from two senders.
        self.assertEqual(commands["install"], own["install"])
        self.assertNotEqual(commands["batch"], own["batch"])
        self.assertNotEqual(commands["session"], own["session"])
        # The viewer's recorder likewise: the spool's batch is `cli`, its own the browser page's (`cadgen-viewer`).
        viewer.viewed()
        self.assertTrue(spool({"features": ["drawing"]}, path=self.path))
        self.assertTrue(viewer.flush())
        commands, own = sent[2:]
        self.assertEqual((commands["process"], commands.get("client"), commands["events"]),
                         ("cli", None, [{"name": "feature", "feature": "drawing", "count": 1}]))
        self.assertEqual((own["process"], own["client"]["name"], own["presentation"], own["events"]),
                         ("viewer", "cadgen-viewer", "browser", [{"name": "view", "calls": 1}]))
        # With nothing spooled, an app's flush sends its own batch alone; with nothing of its own, the spool's alone.
        app.viewed()
        self.assertTrue(app.flush())
        self.assertTrue(spool({"features": ["drawing"]}, path=self.path))
        self.assertFalse(app.flush(), "nothing of the app's own")
        self.assertEqual([batch["process"] for batch in sent[4:]], ["app", "cli"])

    def test_the_spools_batch_is_kept_and_sent_again_as_the_apps_own_is(self) -> None:
        """The `cli` batch an app's recorder sends for the spool is kept whole when the receiver does not take it,
        sent again before anything newer, kept beside the settings as the process exits, and cleared by a no
        said in the app -- as the app's own is, and apart from it."""
        choose(True, by="cli", path=self.path)
        sent: list[dict] = []
        taking = {"now": False}
        app = Recorder(process="app", path=self.path, send=lambda payload: sent.append(payload) or taking["now"])
        app.started(client={"name": "codex-mcp-client", "version": "0.159.0"}, presentation="tabs")
        app.called("cad_show", True)
        self.assertTrue(spool({"features": ["kinematics"]}, path=self.path))
        self.assertFalse(app.flush())  # the receiver is down: both batches are kept, each whole
        commands, own = sent
        self.assertEqual((commands["process"], own["process"]), ("cli", "app"))
        taking["now"] = True
        app.called("cad_show", False, "no_file")
        self.assertTrue(app.flush())
        # Each sent again byte for byte, its id and all, before the app's new batch; nothing new rides in them.
        self.assertEqual(sent[2:4], [commands, own])
        self.assertEqual([event["name"] for event in sent[4]["events"]], ["tool", "tool_failure"])
        self.assertEqual(len(sent), 5)
        # The process exits with the spool's batch not taken: kept beside the settings under its own context, for
        # the next process that sends (``send_kept``).
        taking["now"] = False
        self.assertTrue(spool({"features": ["drawing"]}, path=self.path))
        self.assertFalse(app.flush())
        app.close()
        [kept] = [json.loads(line)["batch"] for line in (self.tmp / KEPT).read_text(encoding="utf-8").splitlines()]
        self.assertEqual((kept["process"], kept.get("client"), kept["events"]),
                         ("cli", None, [{"name": "feature", "feature": "drawing", "count": 1}]))
        # A no the app could not keep holds for the spool's sender too: nothing more goes from this process.
        taking["now"] = True
        app = Recorder(process="app", path=self.path, send=lambda payload: sent.append(payload) or taking["now"])
        with mock.patch("cadgen.settings.write_bytes_atomic", side_effect=OSError("read only")):
            self.assertFalse(app.choose(False, by="app")["saved"])
        self.assertTrue(spool({"features": ["drawing"]}, path=self.path), "the settings still say yes")
        app.called("cad_show", True)
        self.assertFalse(app.flush())
        self.assertEqual(len(sent), 6, "neither the spool's batch nor the app's own")


class InstallChannelTest(_Tmp):
    """Where the install came from (`cadgen/_internal/channel.py`): only the CAD server is told, by its plugin; it
    writes the channel down for its installation, and every recorder of it -- the engine's for the CAD app's
    sessions and for the browser viewer, the sender a command starts -- reports that, unless its process was told
    one itself."""

    def setUp(self) -> None:
        super().setUp()
        self.record = self.tmp / install_channel.RECORD  # beside the settings, where a recorder given them reads it
        # Not a source tree: a checkout is a development install, whatever the record says.
        for patched in (mock.patch("cadgen._internal.channel._source_tree", return_value=False),
                        mock.patch.object(install_channel, "_record_path", return_value=self.record)):
            patched.start()
            self.addCleanup(patched.stop)
        choose(True, by="cli", path=self.path)

    def started(self, process: str, channel: str = "") -> tuple[Recorder, list[dict]]:
        sent: list[dict] = []
        with mock.patch.dict("os.environ", {"CADGEN_INSTALL_CHANNEL": channel}):
            recorder = Recorder(process=process, path=self.path, send=lambda payload: sent.append(payload) or True)
        return recorder, sent

    def channel_of(self, recorder: Recorder, sent: list[dict]) -> str:
        recorder.called("cad_show", True)
        self.assertTrue(recorder.flush())
        return sent[-1]["channel"]

    def server_starts(self, channel: str) -> str | None:
        with mock.patch.dict("os.environ", {"CADGEN_INSTALL_CHANNEL": channel}):
            return install_channel.remember(path=self.record)

    def test_every_process_of_the_installation_reports_the_channel_its_plugins_server_wrote_down(self) -> None:
        sender, from_sender = self.started("cli")  # the telemetry sender a command starts
        viewer, from_viewer = self.started("viewer")
        # The CAD app's sessions' recorder, in an engine a `python model.py` started: told nothing, as the engine's
        # environment is whoever started it -- a plugin names only its own server, which runs in another process.
        app, from_app = self.started("app")
        told, from_told = self.started("viewer", "codex-github")  # a Viewer the CAD server started: told its own
        # A skills-only install: no plugin's server ever ran from it.
        self.assertEqual([self.channel_of(*started) for started in ((sender, from_sender), (viewer, from_viewer),
                                                                      (app, from_app))], ["unknown"] * 3)
        self.assertEqual(self.server_starts("claude-github"), "claude-github")
        self.assertEqual(json.loads(self.record.read_text(encoding="utf-8")),
                         {install_channel.installation(): "claude-github"})
        # Read again for each batch: the sender, the Viewer and the engine were running before the server started.
        self.assertEqual(self.channel_of(sender, from_sender), "claude-github")
        self.assertEqual(self.channel_of(viewer, from_viewer), "claude-github")
        self.assertEqual(self.channel_of(app, from_app), "claude-github", "the CAD app's batches say its plugin's channel")
        self.assertEqual(self.channel_of(told, from_told), "codex-github")  # what a process was told comes first
        # Two plugins pinning one release share its installation: the server that started last is written down.
        self.server_starts("agent-plugins")
        self.assertEqual(self.channel_of(sender, from_sender), "agent-plugins")

    def test_the_record_holds_closed_tokens_for_the_newest_installations_and_never_fails_anything(self) -> None:
        self.assertIsNone(self.server_starts(""))  # nothing named, nothing written
        self.assertFalse(self.record.exists())
        self.record.write_text("not json", encoding="utf-8")
        self.assertIsNone(install_channel.recorded(path=self.record))
        self.assertIsNone(self.server_starts("Not A Channel!"))
        self.assertEqual(self.server_starts("claude-github"), "claude-github")  # a broken record is written afresh
        with mock.patch("cadgen._internal.atomic_replace.write_bytes_atomic") as write:
            self.assertEqual(self.server_starts("claude-github"), "claude-github")
        write.assert_not_called()  # what the record holds already is not written again
        for index in range(install_channel.KEPT_INSTALLATIONS + 3):
            with mock.patch.object(install_channel, "installation", return_value=f"install-{index}"):
                self.server_starts("codex-github")
        kept = json.loads(self.record.read_text(encoding="utf-8"))
        self.assertEqual(list(kept), [f"install-{index}" for index in range(3, install_channel.KEPT_INSTALLATIONS + 3)])
        # A value no plugin could name is no channel, whatever wrote it.
        self.record.write_text(json.dumps({install_channel.installation(): "unknown"}), encoding="utf-8")
        self.assertIsNone(install_channel.recorded(path=self.record))
        with mock.patch("cadgen._internal.channel._load", side_effect=PermissionError):
            self.assertIsNone(install_channel.recorded(path=self.record))
            self.assertIsNone(self.server_starts("claude-github"))

    def test_a_development_install_stays_one(self) -> None:
        # A development install's own server writes `dev` down for its installation, so its engine, which takes no
        # channel from whoever started it, still sends nothing by default.
        self.path.write_text(json.dumps({"telemetry": {"notifiedAt": time.time(), "notice": 1}}), encoding="utf-8")
        with mock.patch.dict("os.environ", {"CADGEN_INSTALL_CHANNEL": ""}):
            self.assertEqual(status(path=self.path)["reason"], "default")
            self.server_starts("dev")
            self.assertEqual(install_channel.channel(), "dev")
            self.assertEqual(status(path=self.path), {"sharing": False, "reason": "untold", "id": None})

    def test_the_cad_server_writes_its_channel_down_as_it_starts(self) -> None:
        environment = {**os.environ, "CADGEN_INSTALL_CHANNEL": "claude-github", "CADGEN_STATE_DIR": str(self.tmp),
                       "DO_NOT_TRACK": "1", "CADGEN_UPDATE_CHECK": "0"}
        # A host that starts a server only to list its tools, and closes it at once.
        subprocess.run([sys.executable, "-m", "cadgen.cli", "mcp"], stdin=subprocess.DEVNULL, capture_output=True,
                       env=environment, timeout=120, check=True)
        self.assertEqual(json.loads(self.record.read_text(encoding="utf-8")),
                         {install_channel.installation(): "claude-github"})


class BeforeTelemetryTest(_Tmp):
    """cadgen 0.7.7 to 0.7.15 kept the answer as `analytics`, for a few days: none of it carries over."""

    def legacy(self, section: dict) -> None:
        self.path.write_text(json.dumps({"analytics": section}), encoding="utf-8")

    def test_an_old_answer_carries_nothing(self) -> None:
        for choice in ("on", "off"):
            self.legacy({"choice": choice, "disclosure": 1, "by": "app", "decidedAt": 1, "id": "old", "salt": "0" * 64})
            self.assertEqual(status(path=self.path), {"sharing": False, "reason": "untold", "id": None})
        # Told, as anyone is: on by default, an old no or not.
        self.assertTrue(notify(io.StringIO(), path=self.path))
        self.assertEqual((status(path=self.path)["sharing"], status(path=self.path)["reason"]), (True, "default"))

    def test_a_no_here_also_stops_an_older_cadgen_and_deletes_what_it_sent(self) -> None:
        # A plugin not yet updated runs 0.7.x beside this cadgen (`uvx cadgen telemetry off` runs the newest) and
        # reads only `analytics`: its yes would go on sending, under an id this no deletes too.
        self.legacy({"choice": "on", "disclosure": 1, "by": "app", "decidedAt": 1, "id": "old", "salt": "0" * 64})
        asked: list[str] = []
        self.assertTrue(choose(False, by="cli", path=self.path, forget=lambda id: asked.append(id) or True)["forgotten"])
        self.assertEqual(asked, ["old"])
        kept = json.loads(self.path.read_text(encoding="utf-8"))["analytics"]
        self.assertEqual((kept["choice"], "id" in kept, "salt" in kept), ("off", False, False))  # what 0.7.x reads as no
        # Where no earlier cadgen answered, none of its settings is written.
        alone = self.tmp / "alone.json"
        choose(False, by="cli", path=alone)
        self.assertNotIn("analytics", json.loads(alone.read_text(encoding="utf-8")))


class NoticeTest(_Tmp):
    """What is sent by default is said once, by a ``cadgen`` command, before anything is sent."""

    def test_said_once_on_stderr_and_kept_as_said(self) -> None:
        said = io.StringIO()
        self.assertTrue(notify(said, path=self.path))
        self.assertFalse(notify(said, path=self.path))  # once
        self.assertEqual(said.getvalue(), notice_text() + "\n")
        found = status(path=self.path)
        self.assertEqual((found["sharing"], found["reason"]), (True, "default"))
        # A choice, either way, keeps when it was said: a yes to less than is sent later falls back to the default.
        choose(True, by="cli", path=self.path)
        with mock.patch("cadgen.analytics.DISCLOSURE", 2):
            self.assertEqual(status(path=self.path)["reason"], "default")
        choose(False, by="cli", path=self.path, forget=lambda id: True)
        self.assertIn("notifiedAt", json.loads(self.path.read_text(encoding="utf-8"))["telemetry"])

    def test_its_off_command_runs_the_installation_that_said_it_when_pasted(self) -> None:
        from cadgen._internal import installations
        from cadgen.analytics import off_command

        uvx = "uvx --no-config --managed-python --python 3.13 --from"
        script = self.tmp / "bin" / ("cadgen.exe" if os.name == "nt" else "cadgen")
        script.parent.mkdir()
        script.write_text("#!/bin/sh\n", encoding="utf-8")
        script.chmod(0o755)
        launcher = self.tmp / "launcher"
        env = {"CADGEN_STATE_DIR": str(self.tmp / "state"), "CADGEN_LAUNCHER_DIR": str(launcher),
               "CADGEN_INSTALLATION_VERSION": "", "PATH": str(self.tmp / "nowhere")}
        made = self.tmp / "uv" / "archive-v0" / "abc"  # an environment uvx made
        record = made / "lib" / "site-packages" / "cadgen-0.8.0.dist-info"
        record.mkdir(parents=True)
        with mock.patch.dict("os.environ", env), mock.patch("sys.prefix", str(made)), \
                mock.patch("sysconfig.get_path", return_value=str(record.parent)) as site:
            # Installed from an index: the release's own requirement, which uvx reuses.
            self.assertEqual(off_command(), f"{uvx} cadgen==0.8.0 cadgen telemetry off")
            self.assertEqual(site.call_args.kwargs["vars"], {"base": str(made), "platbase": str(made)})
            # From a wheel -- a development install's, whose number no index has: that wheel, while it is there.
            wheel = self.tmp / "wheels" / "cadgen-0.8.0-py3-none-any.whl"
            wheel.parent.mkdir()
            wheel.write_bytes(b"")
            (record / "direct_url.json").write_text(json.dumps({"url": wheel.as_uri(), "archive_info": {}}), encoding="utf-8")
            self.assertEqual(off_command(), f"{uvx} {wheel} cadgen telemetry off")
            # Registered (its CAD app's server started, or `cadgen doctor` ran): the `cadgen` command, by the version
            # the record names -- by its path while it is not the `cadgen` on PATH.
            python, console = made / "bin" / "python", made / "bin" / "cadgen"
            for path in (python, console):
                path.parent.mkdir(exist_ok=True)
                path.write_text("", encoding="utf-8")
            installations.register("0.8.0-dev.20261026120000", (str(console), str(python), str(made)))
            self.assertEqual(off_command(), f"{uvx} {wheel} cadgen telemetry off", "no `cadgen` command to run it")
            installations.write_proxy()
            proxy = installations.proxy_path()
            self.assertEqual(off_command(), f"{proxy} +0.8.0-dev.20261026120000 telemetry off")
            with mock.patch.dict("os.environ", {"PATH": str(launcher)}):
                self.assertEqual(off_command(), "cadgen +0.8.0-dev.20261026120000 telemetry off")
            wheel.unlink()  # the wheel gone and nothing registered: this interpreter, as it runs now
            installations.forget("0.8.0-dev.20261026120000")
            with mock.patch("sys.argv", ["/x/cadgen/cli/__main__.py"]), mock.patch("sys.executable", "/venv/bin/python"):
                self.assertEqual(off_command(), "/venv/bin/python -m cadgen.cli telemetry off")
        with mock.patch.dict("os.environ", env):
            # The cadgen on PATH is the one that runs; one off PATH is named by its path.
            with mock.patch("sys.argv", [str(script)]):
                with mock.patch.dict("os.environ", {"PATH": str(script.parent)}):
                    self.assertEqual(off_command(), "cadgen telemetry off")
                with mock.patch.dict("os.environ", {"PATH": str(self.tmp)}):
                    self.assertEqual(off_command(), f"{script.resolve()} telemetry off")
            with mock.patch("sys.argv", ["/x/cadgen/cli/__main__.py"]), mock.patch("sys.executable", "/venv/bin/python"):
                self.assertEqual(off_command(), "/venv/bin/python -m cadgen.cli telemetry off")
            self.assertIn(f"Turn off: {off_command()} · {PRIVACY_URL}", notice_text())

    def test_a_larger_default_is_said_again_before_it_is_sent(self) -> None:
        notify(io.StringIO(), path=self.path)
        with mock.patch("cadgen.analytics.NOTICE", 2):
            self.assertEqual(status(path=self.path)["reason"], "untold")
            self.assertTrue(notify(io.StringIO(), path=self.path))
            self.assertEqual(status(path=self.path)["reason"], "default")

    def test_nothing_is_said_where_nothing_would_be_sent_by_default(self) -> None:
        for name, value in (("CI", "true"), ("CADGEN_INSTALL_CHANNEL", "dev"), ("DO_NOT_TRACK", "1"),
                            ("CADGEN_TELEMETRY", "0"), ("CADGEN_TELEMETRY", "1"),
                            (NOTICE_ENV, "0")):
            with self.subTest(name=name, value=value), mock.patch.dict("os.environ", {name: value}):
                said = io.StringIO()
                self.assertFalse(notify(said, path=self.path))
                self.assertEqual(said.getvalue(), "")
        self.assertEqual(status(path=self.path)["reason"], "untold")
        # Nor to someone who already chose.
        for share in (True, False):
            choose(share, by="cli", path=self.path, forget=lambda id: True)
            with self.subTest(share=share):
                self.assertFalse(notify(io.StringIO(), path=self.path))

    def test_every_command_says_it_but_the_servers_and_telemetry_itself(self) -> None:
        with mock.patch("cadgen.analytics.notify") as told, mock.patch.object(cli, "_run", return_value=0), \
                mock.patch("sys.stdout", io.StringIO()):
            for argv in (["doctor"], ["dxf", "snapshot", "a.dxf"], ["viewer"], ["mcp"], ["server"], ["telemetry", "off"]):
                cli.main(argv)
            cli.main(["--help"])
        self.assertEqual(told.call_count, 3)

    def test_cadgen_telemetry_says_it_where_a_person_looks(self) -> None:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict("os.environ", {"CADGEN_STATE_DIR": str(self.tmp)}), \
                mock.patch("sys.stdout", out), mock.patch("sys.stderr", err):
            self.assertEqual(telemetry_cli.main([]), 0)
        self.assertEqual(err.getvalue(), notice_text() + "\n")
        self.assertRegex(out.getvalue(), r"^Telemetry is on: by default, since cadgen said so on \d{4}-\d{2}-\d{2}\.\n")


class NeverInTheWayTest(_Tmp):
    """Telemetry never fails, slows or clutters what CAD does."""

    serve = ServerCountsTest.serve
    call = ServerCountsTest.call

    def test_a_broken_telemetry_layer_fails_nothing_and_logs_nothing_a_host_shows(self) -> None:
        server, sent = self.serve("claude-directory")
        with mock.patch("cadgen.analytics.status", side_effect=RuntimeError("broken")), \
                mock.patch("cadgen.analytics.choose", side_effect=RuntimeError("broken")), \
                self.assertNoLogs("cadgen.analytics", level="INFO"):
            # The tools answer as if nothing were wrong: off.
            self.assertEqual(self.consent(server)["sharing"], False)
            self.assertEqual(self.consent(server, True)["sharing"], False)
            self.assertFalse(self.http(server, "GET", "/__cad/analytics", agent=True)[1]["sharing"])
            self.assertFalse(self.http(server, "POST", "/__cad/analytics", {"share": False}, agent=True)[1]["sharing"])
            # CAD's own tools are untouched, and the recorder's own methods return quietly.
            self.assertIn("isError", self.call(server, "cad_show", {"source": "missing.step"}))
            server.analytics.called("cad_show", True)
            self.assertFalse(server.analytics.flush())
            server.analytics.close()

    def test_no_tool_call_waits_on_the_network(self) -> None:
        server, sent = self.serve("claude-directory")
        self.consent(server, True)
        release, asked, finished = threading.Event(), threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def deletion(_id) -> None:  # the network, hanging until the test lets it go
            asked.set()
            release.wait(30)
            finished.set()

        with mock.patch("cadgen.analytics.request_deletion", side_effect=deletion):
            self.consent(server, False)  # its deletion hangs in the background
            self.assertTrue(asked.wait(30), "the deletion was asked")
            self.assertFalse(finished.is_set(), "the call answered while the deletion still hung")
            release.set()
            self.assertTrue(finished.wait(30))

    def test_an_exiting_process_waits_on_nothing_and_the_next_one_sends_its_last_batch(self) -> None:
        hang = threading.Event()
        self.addCleanup(hang.set)
        choose(True, by="cli", path=self.path)
        asked: list[dict] = []
        exiting = Recorder(path=self.path, send=lambda payload: asked.append(payload) or hang.wait(30))
        exiting.started(client={"name": "codex-mcp-client"}, presentation="tabs")
        exiting.called("cad_show", True)
        exiting.close()  # the network hangs: an exit never asks it
        self.assertEqual(asked, [], "an exit sends nothing")
        self.assertTrue((self.tmp / KEPT).exists())
        sent: list[dict] = []
        answers = [False, True]  # offline first: kept again, then taken
        following = Recorder(process="viewer", path=self.path, send=lambda payload: sent.append(payload) or answers.pop(0))
        following.send_kept()
        following.send_kept()
        self.assertEqual(len(sent), 2)
        self.assertEqual(sent[0], sent[1])
        self.assertEqual((sent[1]["process"], sent[1]["session"], sent[1]["client"]),
                         ("app", exiting._session, {"name": "codex-mcp-client", "version": ""}))
        self.assertEqual(sent[1]["events"], [{"name": "tool", "tool": "cad_show", "calls": 1, "errors": 0}])
        following.send_kept()
        self.assertEqual(len(sent), 2)  # sent once taken, never again

    def test_a_previous_schema_batch_is_retried_unchanged_by_a_new_sender(self) -> None:
        choose(True, by="cli", path=self.path)
        with mock.patch("cadgen.analytics.SCHEMA", 7):
            old = Recorder(path=self.path, send=lambda payload: True)
            old.built("xbf", "script", "ok", seconds=1.0)
            old.close()
        [kept] = [json.loads(line)["batch"] for line in (self.tmp / KEPT).read_text(encoding="utf-8").splitlines()]
        self.assertEqual((kept["schema"], kept["events"][0]["kind"]), (7, "xbf"))
        sent: list[dict] = []
        Recorder(path=self.path, send=lambda payload: sent.append(payload) or True).send_kept()
        self.assertEqual(sent, [kept], "a persisted batch keeps its schema, kind and deduplication identity")

    def test_a_kept_batch_is_sent_only_under_the_answer_it_was_kept_under(self) -> None:
        choose(True, by="cli", path=self.path)
        exiting = Recorder(path=self.path, send=lambda payload: True)
        exiting.called("cad_show", True)
        exiting.close()
        choose(False, by="app", path=self.path, forget=lambda id: True)  # a no deletes what was kept
        self.assertFalse((self.tmp / KEPT).exists())
        exiting = Recorder(path=self.path, send=lambda payload: True)
        exiting.called("cad_show", True)
        exiting.close()  # under a no: nothing to keep
        self.assertFalse((self.tmp / KEPT).exists())
        choose(True, by="cli", path=self.path)
        exiting = Recorder(path=self.path, send=lambda payload: True)
        exiting.called("cad_show", True)
        exiting.close()
        with mock.patch.dict("os.environ", {"CADGEN_TELEMETRY": "0"}):  # a process that may not send leaves them
            Recorder(path=self.path, send=lambda payload: self.fail("sent")).send_kept()
        self.assertTrue((self.tmp / KEPT).exists())
        with mock.patch("cadgen.analytics.time.time", return_value=time.time() + 60):
            choose(True, by="app", path=self.path)  # another answer since: what was kept under the last is not sent
        Recorder(path=self.path, send=lambda payload: self.fail("sent")).send_kept()
        self.assertFalse((self.tmp / KEPT).exists())

    def test_a_started_recorder_sends_what_was_kept_a_moment_after_it_starts(self) -> None:
        choose(True, by="cli", path=self.path)
        exiting = Recorder(path=self.path, send=lambda payload: True)
        exiting.called("cad_show", True)
        exiting.close()
        sent = threading.Event()
        started = Recorder(path=self.path, send=lambda payload: sent.set() or True, kept_after=0)
        started.start()
        self.addCleanup(started.close)
        self.assertTrue(sent.wait(10))


if __name__ == "__main__":
    unittest.main()
