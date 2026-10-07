"""The browser viewer's telemetry -- the menu's toggle, the same saved answer as the CAD app's, and what its
page did -- and the update notice the CAD app shows too."""

from __future__ import annotations

import http.client
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import cadgen
from cadgen.analytics import Recorder
from cadgen.viewer import handler as handler_module
from cadgen.viewer.http_app import create_cad_app

STL = b"solid t\nendsolid t\n"


class ViewerAnalyticsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = self.tmp / "models"
        (self.root / "parts").mkdir(parents=True)
        (self.root / "parts" / "a.stl").write_bytes(STL)
        # A plugin's install outside CI, where the default holds (a checkout is a development install, which sends
        # nothing by default).
        environment = mock.patch.dict(os.environ, {"CADGEN_STATE_DIR": str(self.tmp / "state"), "DO_NOT_TRACK": "", "CADGEN_TELEMETRY": "",
                                                   "CADGEN_ANALYTICS": "", "CADGEN_INSTALL_CHANNEL": "claude-github", "CI": ""})
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
        status, consent = self.request("GET", "/__cad/analytics")
        self.assertEqual((status, consent["ask"], consent["sharing"], consent["reason"]), (200, False, False, "untold"))
        status, answered = self.request("POST", "/__cad/analytics", {"share": False})
        self.assertEqual((status, answered["ask"], answered["sharing"], answered["reason"]), (200, False, False, "choice"))
        self.assertEqual(self.request("GET", "/__cad/analytics")[1]["ask"], False)
        # The answer is the person's, in the state directory every CAD app reads: the CAD app's
        # server sees the same no.
        self.assertEqual(json.loads(self.state.read_text(encoding="utf-8"))["telemetry"]["choice"], "off")
        # A card still up in another view answers nothing now; the app menu's toggle changes it whenever.
        self.assertEqual(self.request("POST", "/__cad/analytics", {"share": True, "card": True})[1]["sharing"], False)
        self.assertEqual(self.request("POST", "/__cad/analytics", {"share": True})[1]["sharing"], True)

    def test_a_web_page_cannot_answer_for_the_person(self) -> None:
        # Without the viewer's own header (no page from another site can send it), a POST changes nothing.
        self.assertEqual(self.request("POST", "/__cad/analytics", {"share": True}, guard=False)[0], 403)
        self.assertEqual(self.request("GET", "/__cad/analytics")[1]["reason"], "untold")
        self.assertFalse(self.state.exists())

    def test_what_the_page_did_is_sent_only_with_consent_and_a_file_only_as_a_count(self) -> None:
        # A touch is reported; a model the page shows is counted as it joins the library.
        model = str(self.root / "parts" / "a.stl")
        self.request("POST", "/__cad/analytics/activity", {"touched": True})
        self.request("POST", "/__cad/recents", {"action": "open", "path": model})
        self.assertFalse(self.app.analytics.flush())  # nobody told yet: nothing goes
        self.request("POST", "/__cad/analytics", {"share": True})
        self.assertEqual(self.request("POST", "/__cad/analytics/activity", {"touched": True})[0], 204)
        self.assertEqual(self.request("POST", "/__cad/recents", {"action": "open", "path": model})[0], 200)
        self.assertEqual(self.request("POST", "/__cad/recents", {"action": "open", "path": "parts/a.stl"})[0], 400)
        self.assertTrue(self.app.analytics.flush())
        [payload] = self.sent
        self.assertEqual((payload["process"], payload["presentation"], payload["client"]["name"]), ("viewer", "browser", "cadgen-viewer"))
        # The file was shown before the yes too: counted once that day, and that count was never sent.
        self.assertEqual(payload["events"], [{"name": "view", "calls": 1}])
        (self.root / "b.stl").write_bytes(STL)
        self.assertEqual(self.request("POST", "/__cad/recents", {"action": "open", "path": str(self.root / "b.stl")})[0], 200)
        self.assertTrue(self.app.analytics.flush())
        self.assertEqual(self.sent[-1]["events"], [{"name": "files", "kind": "stl", "count": 1}])
        self.assertNotIn(".stl", json.dumps(self.sent))

    def test_told_before_it_started_the_viewer_counts_by_default(self) -> None:
        # A `cadgen` command said it before this viewer started (``cadgen/analytics.py``: ``notify``).
        self.state.parent.mkdir(parents=True, exist_ok=True)
        self.state.write_text(json.dumps({"telemetry": {"notifiedAt": time.time() - 3600, "notice": 1}}), encoding="utf-8")
        self.assertEqual(self.request("GET", "/__cad/analytics")[1]["reason"], "default")
        model = str(self.root / "parts" / "a.stl")
        self.request("POST", "/__cad/analytics/activity", {"touched": True})
        self.request("POST", "/__cad/recents", {"action": "open", "path": model})
        self.assertTrue(self.app.analytics.flush())
        self.assertEqual(self.sent[0]["events"], [{"name": "files", "kind": "stl", "count": 1}, {"name": "view", "calls": 1}])

    def test_the_update_button_reads_whether_a_newer_release_is_out(self) -> None:
        # The CAD app's notice (`cadgen/updates.py`), from the same feed; this page copies its prompt,
        # and nothing it does is kept: there is no answer to post. A Viewer no plugin's server started
        # names no channel: a skills-only install, which nothing else updates.
        (self.tmp / "state").mkdir(exist_ok=True)
        (self.tmp / "state" / "versions.json").write_text(json.dumps({"checked": time.time(), "feed": {"latest": "99.0.0"}}),
                                                          encoding="utf-8")
        with mock.patch.dict(os.environ, {"CADGEN_INSTALL_CHANNEL": "", "CADGEN_AUTO_UPDATED": "", "CI": "",
                                          "CADGEN_UPDATE_CHECK": ""}), \
                mock.patch("cadgen._internal.channel._source_tree", return_value=False):
            status, answer = self.request("GET", "/__cad/version")
            self.assertEqual((status, answer["notice"]["text"]), (200, f"A new version v99.0.0 of text-to-cad is available (currently on v{cadgen.__version__})"))
            self.assertEqual(self.request("GET", "/__cad/version")[1], answer)
            self.assertNotEqual(self.request("POST", "/__cad/version", {})[0], 200)

    def test_an_app_with_no_recorder_serves_no_analytics(self) -> None:
        # The viewer process and the CAD app's server each attach theirs; an app given none counts nothing.
        port = self.serve(create_cad_app(host="127.0.0.1", port=0))
        self.assertEqual(self.request("GET", "/__cad/analytics", port=port)[0], 404)
        self.assertEqual(self.request("POST", "/__cad/analytics/activity", {"touched": True}, port=port)[0], 405)


if __name__ == "__main__":
    unittest.main()
