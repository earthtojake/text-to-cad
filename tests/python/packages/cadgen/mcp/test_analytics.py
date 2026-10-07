"""cadgen's telemetry, CAD's usage stats: who decides whether they are sent -- by default once a ``cadgen`` command has
said so, never after a no -- and that they carry counts, times and metadata -- how many people, how often,
on how many files -- and nothing else. The build daemon's counts are ``test_daemon_telemetry.py``'s."""

from __future__ import annotations

import base64
import http.server
import io
import json
import shutil
import threading
import time
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cadgen import cli
from cadgen.analytics import (CLOSE_SECONDS, NOTICE_ENV, NOTICE_TEXT, PRIVACY_URL, Recorder, _post, choose, forget_pending,
                              notify, status)
from cadgen.cli import telemetry as telemetry_cli
from cadgen.mcp.protocol import RequestContext, RpcError
from cadgen.mcp.server import Server
from cadgen.mcp.ui import AppPage
from cadgen.viewer.recents import RecentStore

# Where the notice is said, and the default holds: an install a plugin made (a checkout is a development install,
# never told and sending nothing by default), outside CI. Every test runs there unless it says otherwise.
TOLD = {"CADGEN_INSTALL_CHANNEL": "claude-github", "CI": ""}
QUIET = {"DO_NOT_TRACK": "", "CADGEN_TELEMETRY": "", "CADGEN_ANALYTICS": "", NOTICE_ENV: "", **TOLD}


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
        server.handle("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                     "clientInfo": {"name": client, "version": "0.159.0"}}, None)
        return server, sent

    def call(self, server: Server, name: str, arguments: dict | None = None) -> dict:
        context = RequestContext(1, {"threadId": "t"})
        return server.handle("tools/call", {"name": name, "arguments": arguments or {}}, context)

    def http(self, server: Server, method: str, url: str, body: dict | None = None) -> tuple[int, dict | None]:
        """A request the page sends through ``cad_http`` (a POST with the header its client sends)."""
        headers = {"x-cadgen-viewer": "1", "content-type": "application/json"} if body is not None else {}
        reply = self.call(server, "cad_http", {"method": method, "url": url, "headers": headers,
                                               "body": base64.b64encode(json.dumps(body).encode() if body is not None else b"").decode("ascii")})
        data = base64.b64decode(reply["structuredContent"].get("body") or "")
        return reply["structuredContent"]["status"], json.loads(data) if data else None

    def consent(self, server: Server, share: bool | None = None) -> dict:
        """The app menu's Share usage stats toggle: read, or the person's answer."""
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
        for name, value in (("DO_NOT_TRACK", "1"), ("CADGEN_TELEMETRY", "off"), ("CADGEN_ANALYTICS", "0")):
            with self.subTest(name=name), mock.patch.dict("os.environ", {name: value}):
                self.assertEqual(status(path=self.path)["reason"], "environment")
                self.assertFalse(status(path=self.path)["sharing"])


class NoMeansNoTest(_Tmp):
    """A no is kept, and nothing undoes it."""

    def test_a_no_survives_restarts_updates_and_a_larger_disclosure(self) -> None:
        choose(False, by="app", path=self.path)  # the menu's toggle, `cadgen analytics off`, or the agent
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
        with self.assertRaises(RpcError):  # a text client has no page: the agent cannot opt in
            self.consent(server, True)
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
        self.call(server, "cad_open", {"path": str(secret)})  # the agent opens one
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
                          payload["client"]["name"]), (3, "app", "claude-directory", "tabs", "codex-mcp-client"))
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

    def test_a_server_nobody_used_sends_nothing(self) -> None:
        # Codex starts a server per thread, and some only to list tools: none of them is a user.
        server, sent = self.serve("claude-directory")
        self.consent(server, True)
        self.call(server, "cad_sync", {"view": "v", "surface": "sidebar"})
        self.assertFalse(server.analytics.flush())
        server.analytics.close()
        self.assertEqual(sent, [])

    def test_a_batch_the_receiver_did_not_take_waits_for_the_next(self) -> None:
        answers: list = [False, True, "refused", True]
        sent: list[dict] = []
        choose(True, by="cli", path=self.path)
        recorder = Recorder(path=self.path, send=lambda payload: sent.append(payload) or answers.pop(0))
        recorder.called("cad_show", True)
        recorder.opened("/work/a.step")
        self.assertFalse(recorder.flush())  # offline: kept
        recorder.called("cad_show", False)
        self.assertTrue(recorder.flush())
        self.assertEqual(sent[1]["events"], [{"name": "files", "kind": "step", "count": 1},
                                             {"name": "tool", "tool": "cad_show", "calls": 2, "errors": 1}])
        # One the receiver refused (a 4xx) is dropped: sent again, it would take what comes next down with it.
        recorder.called("cad_view", True)
        self.assertFalse(recorder.flush())
        recorder.called("cad_show", True)
        self.assertTrue(recorder.flush())
        self.assertEqual([event["tool"] for event in sent[3]["events"]], ["cad_show"])

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
        self.call(server, "cad_show", {"path": "a.step"})
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

    def test_the_agent_can_turn_telemetry_off_but_not_on(self) -> None:
        server, sent = self.serve("claude-directory")
        self.consent(server, True)
        off = self.call(server, "cad_telemetry", {"action": "off"})
        self.assertEqual(off["structuredContent"], {"sharing": False})
        self.assertFalse(status(path=self.path)["sharing"])
        tool = next(tool for tool in server.tools() if tool["name"] == "cad_telemetry")
        self.assertEqual(tool["inputSchema"]["properties"]["action"]["enum"], ["status", "off"])
        self.call(server, "cad_show", {"path": "a.step"})
        server.analytics.flush()
        self.assertEqual(sent, [])
        self.assertNotIn("id", json.loads(self.path.read_text(encoding="utf-8"))["telemetry"])


class BeforeTelemetryTest(_Tmp):
    """cadgen 0.7.7 to 0.7.15 kept the answer as `analytics`: only its no carries over."""

    def legacy(self, section: dict) -> None:
        self.path.write_text(json.dumps({"analytics": section}), encoding="utf-8")

    def test_an_old_no_still_holds_until_the_person_answers_again(self) -> None:
        self.legacy({"choice": "off", "disclosure": 1, "by": "app", "decidedAt": 1})
        self.assertFalse(notify(io.StringIO(), path=self.path))  # nothing to tell someone who said no
        self.assertEqual(status(path=self.path), {"sharing": False, "reason": "choice", "id": None})
        choose(True, by="cli", path=self.path)  # a yes given now, here, wins
        self.assertEqual(status(path=self.path)["reason"], "choice")
        self.assertTrue(status(path=self.path)["sharing"])

    def test_an_old_yes_carries_nothing(self) -> None:
        self.legacy({"choice": "on", "disclosure": 1, "by": "app", "decidedAt": 1, "id": "old", "salt": "0" * 64})
        self.assertEqual(status(path=self.path), {"sharing": False, "reason": "untold", "id": None})

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
        self.assertEqual(said.getvalue(), NOTICE_TEXT + "\n")
        found = status(path=self.path)
        self.assertEqual((found["sharing"], found["reason"]), (True, "default"))
        # A choice, either way, keeps when it was said: a yes to less than is sent later falls back to the default.
        choose(True, by="cli", path=self.path)
        with mock.patch("cadgen.analytics.DISCLOSURE", 2):
            self.assertEqual(status(path=self.path)["reason"], "default")
        choose(False, by="cli", path=self.path, forget=lambda id: True)
        self.assertIn("notifiedAt", json.loads(self.path.read_text(encoding="utf-8"))["telemetry"])

    def test_a_larger_default_is_said_again_before_it_is_sent(self) -> None:
        notify(io.StringIO(), path=self.path)
        with mock.patch("cadgen.analytics.NOTICE", 2):
            self.assertEqual(status(path=self.path)["reason"], "untold")
            self.assertTrue(notify(io.StringIO(), path=self.path))
            self.assertEqual(status(path=self.path)["reason"], "default")

    def test_nothing_is_said_where_nothing_would_be_sent_by_default(self) -> None:
        for name, value in (("CI", "true"), ("CADGEN_INSTALL_CHANNEL", "dev"), ("DO_NOT_TRACK", "1"),
                            ("CADGEN_TELEMETRY", "0"), ("CADGEN_TELEMETRY", "1"), ("CADGEN_ANALYTICS", "0"),
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
            for argv in (["doctor"], ["step", "snapshot", "a.step"], ["viewer"], ["mcp"], ["daemon"], ["telemetry", "off"]):
                cli.main(argv)
            cli.main(["--help"])
        self.assertEqual(told.call_count, 3)

    def test_the_old_command_names_the_new_one(self) -> None:
        err = io.StringIO()
        with mock.patch("sys.stderr", err):
            self.assertEqual(cli.main(["analytics", "off"]), 2)
        self.assertIn("cadgen telemetry", err.getvalue())

    def test_cadgen_telemetry_says_it_where_a_person_looks(self) -> None:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict("os.environ", {"CADGEN_STATE_DIR": str(self.tmp)}), \
                mock.patch("sys.stdout", out), mock.patch("sys.stderr", err):
            self.assertEqual(telemetry_cli.main([]), 0)
        self.assertEqual(err.getvalue(), NOTICE_TEXT + "\n")
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
            self.assertFalse(self.call(server, "cad_telemetry").get("isError"))
            self.assertFalse(self.call(server, "cad_telemetry", {"action": "off"}).get("isError"))
            # CAD's own tools are untouched, and the recorder's own methods return quietly.
            self.assertIn("isError", self.call(server, "cad_show", {"path": "missing.step"}))
            server.analytics.called("cad_show", True)
            self.assertFalse(server.analytics.flush())
            server.analytics.close()

    def test_no_tool_call_waits_on_the_network(self) -> None:
        server, sent = self.serve("claude-directory")
        self.consent(server, True)
        release = threading.Event()
        with mock.patch("cadgen.analytics.request_deletion", side_effect=lambda id: release.wait(10)):
            began = time.monotonic()
            self.consent(server, False)  # its deletion hangs in the background
            self.assertLess(time.monotonic() - began, 1)
            release.set()

    def test_an_exiting_server_waits_for_its_last_send_only_so_long(self) -> None:
        hang = threading.Event()
        choose(True, by="cli", path=self.path)
        recorder = Recorder(path=self.path, send=lambda payload: hang.wait(30))
        recorder.started(client={"name": "codex-mcp-client"}, presentation="tabs")
        recorder.called("cad_show", True)
        began = time.monotonic()
        recorder.close()
        self.assertLess(time.monotonic() - began, CLOSE_SECONDS + 1)
        hang.set()


if __name__ == "__main__":
    unittest.main()
