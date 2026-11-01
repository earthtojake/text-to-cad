"""The browser viewer's telemetry -- the menu's toggle, the same saved answer as the CAD app's, and what its
page did -- and the update notice the CAD app shows too."""

from __future__ import annotations

import http.client
import io
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import cad_server
from cad_server.analytics import PRIVACY_URL, Recorder
from cad_server.viewer import handler as handler_module
from cad_server.viewer.http_app import create_cad_app

STL = b"solid t\nendsolid t\n"


class _ClientThatLeft:
    """A connection whose page cancelled its fetch: its request arrived, and its ``fails_at``-th write
    onto the socket (the first is the status line and headers) finds it gone, as Windows says it
    (WinError 10053, a ``ConnectionAbortedError``)."""

    def __init__(self, request: bytes, fails_at: int = 1) -> None:
        self._request = io.BytesIO(request)
        self._fails_at = fails_at
        self.writes = 0

    def makefile(self, *_args, **_kwargs):
        return self._request

    def sendall(self, data: bytes) -> None:
        self.writes += 1
        if self.writes >= self._fails_at:
            raise ConnectionAbortedError(10053, "An established connection was aborted by the software in your host machine")

    def settimeout(self, _seconds) -> None:
        pass

    def shutdown(self, _how) -> None:
        pass

    def close(self) -> None:
        pass


class ViewerAnalyticsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = self.tmp / "models"
        (self.root / "parts").mkdir(parents=True)
        (self.root / "parts" / "a.stl").write_bytes(STL)
        # A plugin's install outside CI, where the default holds (a checkout is a development install, which sends
        # nothing by default).
        environment = mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(self.tmp / "state"), "DO_NOT_TRACK": "", "CAD_TELEMETRY": "",
                                                   "CAD_INSTALL_CHANNEL": "claude-github", "CI": ""})
        environment.start()
        self.addCleanup(environment.stop)
        self.state = self.tmp / "state" / "settings.json"
        self.sent: list[dict] = []
        self.app = create_cad_app(host="127.0.0.1", port=0, start=str(self.root))
        self.app.analytics = Recorder(process="viewer", path=self.state, send=lambda payload: self.sent.append(payload) or True)
        self.app.analytics.started(client={"name": "cadgen-viewer", "version": "0"}, presentation="browser")
        self.port = self.serve(self.app)

    def serve(self, app) -> int:
        server = handler_module.serve(app, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server.server_address[1]

    def request(self, method: str, path: str, body: dict | None = None, port: int | None = None,
                guard: bool = True) -> tuple[int, dict | None]:
        connection = http.client.HTTPConnection("127.0.0.1", port or self.port, timeout=10)
        try:
            headers = {"content-type": "application/json"} if body is not None else {}
            if body is not None and guard:
                headers["x-cadgen-viewer"] = "1"
            connection.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
            response = connection.getresponse()
            data = response.read()
            return response.status, json.loads(data) if data else None
        finally:
            connection.close()

    def test_the_viewer_never_asks_and_a_no_is_kept_for_every_cad_app(self) -> None:
        status, settings = self.request("GET", "/api/v1/settings")
        self.assertEqual((status, settings["telemetry"]), (200, {"share": False, "reason": "untold", "policy": PRIVACY_URL}))
        status, answered = self.request("PUT", "/api/v1/settings", {"telemetry": {"share": False}})
        answered = answered["telemetry"]
        self.assertEqual((status, answered["share"], answered["reason"], answered["saved"]), (200, False, "choice", True))
        # The answer is the person's, in the state directory every CAD app reads: the CAD app's
        # server sees the same no. The app menu's toggle changes it whenever.
        self.assertEqual(json.loads(self.state.read_text(encoding="utf-8"))["telemetry"]["choice"], "off")
        self.assertEqual(self.request("PUT", "/api/v1/settings", {"telemetry": {"share": True}})[1]["telemetry"]["share"], True)
        # A change that is not one is refused, and changes nothing.
        for change in ({"telemetry": {"share": "yes"}}, {"telemetry": True}, {"colour": "red"}):
            with self.subTest(change=change):
                self.assertEqual(self.request("PUT", "/api/v1/settings", change)[0], 400)
        self.assertEqual(self.request("GET", "/api/v1/settings")[1]["telemetry"]["share"], True)
        # What a read answers, put back with one value changed, changes that value: the telemetry's
        # read-only reason and policy ride along.
        read = self.request("GET", "/api/v1/settings")[1]
        read["telemetry"]["share"] = False
        status, written = self.request("PUT", "/api/v1/settings", read)
        self.assertEqual((status, written["telemetry"]["share"], written["telemetry"]["reason"]), (200, False, "choice"))
        self.assertEqual(self.request("PUT", "/api/v1/settings", {"telemetry": {"share": True, "colour": 1}})[0], 400)

    def test_what_the_page_did_is_sent_only_with_consent_and_a_file_only_as_a_count(self) -> None:
        # A touch is reported; a model the page shows is counted as it joins the library.
        model = str(self.root / "parts" / "a.stl")
        self.request("POST", "/api/v1/local/activity", {"touched": True})
        self.request("PATCH", "/api/v1/documents", {"action": "open", "path": model})
        self.assertFalse(self.app.analytics.flush())  # nobody told yet: nothing goes
        self.request("PUT", "/api/v1/settings", {"telemetry": {"share": True}})
        self.assertEqual(self.request("POST", "/api/v1/local/activity", {"touched": True})[0], 204)
        self.assertEqual(self.request("PATCH", "/api/v1/documents", {"action": "open", "path": model})[0], 200)
        self.assertEqual(self.request("PATCH", "/api/v1/documents", {"action": "open", "path": "parts/a.stl"})[0], 400)
        self.assertTrue(self.app.analytics.flush())
        [payload] = self.sent
        self.assertEqual((payload["process"], payload["presentation"], payload["client"]["name"]), ("viewer", "browser", "cadgen-viewer"))
        # The file was shown before the yes too: counted once that day, and that count was never sent.
        self.assertEqual(payload["events"], [{"name": "view", "calls": 1}])
        (self.root / "b.stl").write_bytes(STL)
        self.assertEqual(self.request("PATCH", "/api/v1/documents", {"action": "open", "path": str(self.root / "b.stl")})[0], 200)
        self.assertTrue(self.app.analytics.flush())
        self.assertEqual(self.sent[-1]["events"], [{"name": "files", "kind": "stl", "count": 1}])
        self.assertNotIn(".stl", json.dumps(self.sent))

    def test_a_models_page_is_counted_apart_from_an_xbf_file_once_a_day(self) -> None:
        # A model and an actual XBF file are counted separately, each once a day, and never as builds.
        from cad.engine.ids import model_id
        from cad_server.engine.registry import Registry

        script = self.root / "parts.py"
        script.write_text("", encoding="utf-8")
        ident = model_id(script, "cube")
        Registry(self.tmp / "state").put({"id": ident, "kind": "model", "root": str(self.root), "home": "parts.py",
                                          "entry": "cube", "revision": "r1", "built": 1.0})
        self.request("PUT", "/api/v1/settings", {"telemetry": {"share": True}})
        for _ in range(2):  # shown, then again: a reload, the home's card
            self.assertEqual(self.request("PATCH", "/api/v1/documents", {"action": "open", "path": ident})[0], 200)
        # An id no document has is no page shown.
        self.assertEqual(self.request("PATCH", "/api/v1/documents", {"action": "open", "path": model_id(script, "gone")})[0], 200)
        path = self.root / "exported.xbf"
        path.write_bytes(b"file fixture")
        for _ in range(2):
            self.assertEqual(self.request("PATCH", "/api/v1/documents", {"action": "open", "path": str(path)})[0], 200)
        self.assertTrue(self.app.analytics.flush())
        [payload] = self.sent
        self.assertEqual(payload["events"], [{"name": "files", "kind": "model", "count": 1},
                                           {"name": "files", "kind": "xbf", "count": 1}])
        self.assertNotIn(ident, json.dumps(payload))
        self.assertNotIn(str(path), json.dumps(payload))

    def test_a_page_says_its_quick_edits_and_its_crashes_and_a_route_that_breaks_is_one(self) -> None:
        self.request("PUT", "/api/v1/settings", {"telemetry": {"share": True}})
        crash = {"where": "page", "type": "TypeError", "handled": False,
                 "frames": [{"file": "index-Bx3k2.js", "function": "Kt", "line": 1, "column": 48213}]}
        for activity in ({"quickEdit": True}, {"crash": crash},
                         {"crash": {**crash, "message": "reading 'secret'"}},  # not one cadgen would make: dropped
                         {"crash": {**crash, "where": "tool"}}):  # a page speaks only for a page
            self.assertEqual(self.request("POST", "/api/v1/local/activity", activity)[0], 204)
        # A route that breaks for no reason its caller gave is the server's crash; a bad request is not.
        with mock.patch.object(type(self.app), "documents", side_effect=KeyError("secret")):
            self.assertEqual(self.request("GET", "/api/v1/documents")[0], 500)
        self.assertEqual(self.request("PATCH", "/api/v1/documents", {"action": "open", "path": "relative.stl"})[0], 400)
        self.assertTrue(self.app.analytics.flush())
        events = self.sent[-1]["events"]
        self.assertEqual([event for event in events if event["name"] == "feature"], [{"name": "feature", "feature": "quick_edit", "count": 1}])
        crashes = [(event["where"], event["type"]) for event in events if event["name"] == "exception"]
        self.assertEqual(crashes, [("page", "TypeError"), ("route", "KeyError")])
        self.assertNotIn("secret", json.dumps(self.sent))

    def test_a_page_that_leaves_mid_answer_is_no_crash_and_a_route_that_breaks_still_is(self) -> None:
        self.request("PUT", "/api/v1/settings", {"telemetry": {"share": True}})
        handler_class = handler_module.make_handler_class(self.app)
        for path, fails_at in (("/api/v1/server", 1), ("/api/v1/server", 2), ("/api/v1/documents", 1)):
            with self.subTest(path=path, fails_at=fails_at), \
                    mock.patch.object(type(self.app), "documents", side_effect=KeyError("secret")):
                client = _ClientThatLeft(f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n".encode(), fails_at)
                handler_class(client, ("127.0.0.1", 50000), None)  # the server's own path: raises nothing
                # The answer stopped where the page left: the broken route's 400 is not tried after it.
                self.assertEqual(client.writes, fails_at)
        self.assertTrue(self.app.analytics.flush())
        crashes = [(event["where"], event["type"]) for event in self.sent[-1]["events"] if event["name"] == "exception"]
        self.assertEqual(crashes, [("route", "KeyError")], "the route's own mistake, once; never the page leaving")

    def test_the_update_button_reads_whether_a_newer_release_is_out(self) -> None:
        # The CAD app's notice (`cad_server/updates.py`), from the same feed; this page copies its prompt,
        # and nothing it does is kept: there is no answer to post. A Viewer no plugin's server started
        # names no channel: a skills-only install, which nothing else updates.
        (self.tmp / "state").mkdir(exist_ok=True)
        (self.tmp / "state" / "versions.json").write_text(json.dumps({"checked": time.time(), "feed": {"latest": "99.0.0"}}),
                                                          encoding="utf-8")
        with mock.patch.dict(os.environ, {"CAD_INSTALL_CHANNEL": "", "CAD_AUTO_UPDATED": "", "CI": "",
                                          "CAD_UPDATE_CHECK": ""}), \
                mock.patch("cad_server._internal.channel._source_tree", return_value=False):
            status, answer = self.request("GET", "/api/v1/server")
            self.assertEqual((status, answer["notice"], answer["release"]),
                             (200, {"latest": "99.0.0", "version": cad_server.__version__}, cad_server.__version__))
            self.assertEqual(self.request("GET", "/api/v1/server")[1], answer)
            self.assertEqual(self.request("POST", "/api/v1/server", {})[0], 405)
            # Where an update is, read alone: the notice, the release, this start of the engine, the update.
            status, update = self.request("GET", "/api/v1/local/update")
            self.assertEqual((status, update), (200, {key: answer[key] for key in ("notice", "release", "instance", "update")}))
            # Only the engine's application updates: one with no engine under it says so, and starts nothing.
            status, refused = self.request("POST", "/api/v1/local/update", {})
            self.assertEqual((status, set(refused)), (409, {"error", "hint"}))
            self.assertEqual(self.request("PUT", "/api/v1/local/update", {})[0], 405)

    def test_an_app_with_no_recorder_serves_no_analytics(self) -> None:
        # The viewer process and the CAD app's server each attach theirs; an app given none counts nothing.
        port = self.serve(create_cad_app(host="127.0.0.1", port=0))
        self.assertEqual(self.request("GET", "/api/v1/settings", port=port)[1]["telemetry"], None)
        self.assertEqual(self.request("PUT", "/api/v1/settings", {"telemetry": {"share": True}}, port=port)[0], 409)
        self.assertEqual(self.request("POST", "/api/v1/local/activity", {"touched": True}, port=port)[0], 404)


if __name__ == "__main__":
    unittest.main()
