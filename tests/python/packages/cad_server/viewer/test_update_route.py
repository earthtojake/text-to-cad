"""The viewer's update button, as the engine serves it: ``GET /api/v1/server``'s ``cadUpdate`` (``auto_update.button``),
and ``POST /api/v1/local/update``, which begins a person's update as ``cad update`` does (the engine's ``update``: a
stand-in here, so nothing is installed) or puts a failure away, behind the same credentials and guard header as every
route that changes something, and refused where cad cannot update itself. A real engine's HTTP server, on a computer of
its own: a temporary state folder and a uv tool's environment of its own; no test runs uv or reaches the network."""
from __future__ import annotations

import http.client
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import cad_server
from cad_server import updates
from cad_server._internal import auto_update, store

RECEIPT = '[tool]\nrequirements = [{ name = "cad" }]\nentrypoints = [{ name = "cad" }]\n'


class UpdateRouteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from cad_server._internal.engine_host import http_factory
        from cad.engine.serve import Server

        cls.server = Server(isolated=True, mesh_mode="inline", http_factory=http_factory)
        cls.server.start()
        cls.app = cls.server.http.app

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.stop()

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.tool = self.tmp / "tools" / "cad"
        self.tool.mkdir(parents=True)
        (self.tool / "uv-receipt.toml").write_text(RECEIPT, encoding="utf-8")
        uv = self.tmp / "bin" / ("uv.exe" if os.name == "nt" else "uv")
        uv.parent.mkdir()
        uv.write_text("", encoding="utf-8")
        uv.chmod(0o755)
        self.state = self.tmp / "state"
        for patch in (mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(self.state)}),
                      mock.patch.object(sys, "prefix", str(self.tool)),
                      mock.patch.object(sys, "_base_executable", str(self.tmp / "python3"), create=True),
                      mock.patch.object(cad_server, "__version__", "0.1.0"),
                      mock.patch.object(updates, "checking", return_value=True),
                      mock.patch.object(auto_update, "find_uv", return_value=str(uv)),
                      mock.patch.object(auto_update, "carried_uv", return_value=None),
                      mock.patch.object(store, "switches", return_value=True),
                      mock.patch.object(updates, "feed", return_value={"latest": "0.2.0", "lines": {"0": "0.2.0"}})):
            patch.start()
            self.addCleanup(patch.stop)
        self.asked: list[bool] = []
        self.server.update = self.engine_update
        self.addCleanup(setattr, self.server, "update", None)

    def engine_update(self, begin: bool = True) -> dict:
        """The engine's ``Daemon.update``, as the route asks it: ``True`` a person's update, begun at once (its record
        kept underway, as ``auto_update.begin`` keeps it); ``False`` begins nothing."""
        self.asked.append(begin)
        if not begin:
            return {"ok": True, "version": "0.1.0", "last": auto_update.last(), "waiting": None}
        self.keep(outcome="underway", at=time.time(), beat=time.time(), asked=True, phase="building")
        return {"ok": True, "updating": "0.2.0", "from": "0.1.0", "since": time.time()}

    def ask(self, method: str, path: str, body: dict | None = None, *, link: bool = True, guard: bool = True):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=20)
        headers = {"Host": f"127.0.0.1:{self.server.port}", "Content-Type": "application/json",
                   **({"Authorization": f"Bearer {self.app.link()}"} if link else {}), **({"x-cad-viewer": "1"} if guard else {})}
        try:
            conn.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers=headers)
            response = conn.getresponse()
            data = response.read()
            return response.status, json.loads(data) if data else None
        finally:
            conn.close()

    def keep(self, **record) -> None:
        auto_update._keep(self.state / auto_update.RECORD, {
            "release": "0.2.0", "wanted": "0.2.0", "from": "0.1.0", "at": time.time() - 60, "tries": 1,
            "installer": "uv", "asked": False, **record})

    def test_the_server_says_what_the_button_shows(self) -> None:
        status, answer = self.ask("GET", "/api/v1/server")
        self.assertEqual(status, 200)
        self.assertEqual(answer["cadUpdate"], {"version": "0.1.0", "latest": "0.2.0", "state": "idle"})
        self.assertEqual(answer["release"], cad_server.__version__)
        self.keep(outcome="failed", ended=time.time(), cause="in_use")
        update = self.ask("GET", "/api/v1/server")[1]["cadUpdate"]
        self.assertEqual((update["state"], update["cause"]), ("failed", "in_use"), "from the record: a reload says it too")
        with mock.patch.object(sys, "prefix", str(self.tmp)):
            self.assertIsNone(self.ask("GET", "/api/v1/server")[1]["cadUpdate"], "no global install: no button")

    def test_a_click_begins_a_person_s_update_and_the_page_follows_it(self) -> None:
        self.keep(outcome="failed", ended=time.time(), cause="network")
        status, answer = self.ask("POST", "/api/v1/local/update", {})
        self.assertEqual((status, answer["cadUpdate"]["state"], answer["cadUpdate"]["asked"]), (202, "working", True),
                         "begun at once: the failure gone")
        self.assertEqual(self.asked, [True])
        self.assertEqual(self.ask("GET", "/api/v1/server")[1]["cadUpdate"]["state"], "working")

    def test_a_failure_is_put_away_for_every_page(self) -> None:
        at = time.time() - 60
        self.keep(outcome="failed", ended=time.time(), cause="disk_full", at=at)
        self.assertNotIn("dismissed", self.ask("GET", "/api/v1/server")[1]["cadUpdate"])
        status, answer = self.ask("POST", "/api/v1/local/update", {"dismiss": at})
        self.assertEqual((status, answer["cadUpdate"]["state"], answer["cadUpdate"]["dismissed"]), (200, "failed", True))
        self.assertEqual(self.asked, [], "nothing asked of the engine")
        update = self.ask("GET", "/api/v1/server")[1]["cadUpdate"]
        self.assertEqual((update["state"], update["dismissed"]), ("failed", True), "put away for every page, and a reload")
        for body in ({"dismiss": "now"}, {"dismiss": True}, {"target": "1.0.0"}, ["x"]):
            with self.subTest(body=body):
                self.assertEqual(self.ask("POST", "/api/v1/local/update", body)[0], 400)

    def test_refused_without_the_credential_or_the_guard_header(self) -> None:
        for name, kwargs in (("no credential", {"link": False}), ("no guard header", {"guard": False})):
            with self.subTest(name):
                status, _ = self.ask("POST", "/api/v1/local/update", {}, **kwargs)
                self.assertEqual(status, 403)
        self.assertEqual(self.ask("GET", "/api/v1/server", link=False)[0], 403)
        self.assertEqual(self.asked, [], "nothing asked of the engine")

    def test_refused_where_cad_cannot_update_itself_saying_why(self) -> None:
        with mock.patch.object(sys, "prefix", str(self.tmp)):
            status, answer = self.ask("POST", "/api/v1/local/update", {})
        self.assertEqual((status, answer["error"]), (409, auto_update.NOT_THE_TOOL))
        with mock.patch.object(updates, "checking", return_value=False):
            self.assertEqual(self.ask("POST", "/api/v1/local/update", {})[1]["error"], auto_update.CHECK_OFF)
        with mock.patch.object(auto_update, "find_uv", return_value=None), \
                mock.patch.object(auto_update, "carried_uv", return_value=None):
            status, answer = self.ask("POST", "/api/v1/local/update", {})
        self.assertEqual((status, answer["cause"], answer["said"]),
                         (409, "no_installer", "uv cannot be found, so no update can begin"))
        with mock.patch.object(store, "switches", return_value=False):
            status, answer = self.ask("POST", "/api/v1/local/update", {})
        self.assertEqual((status, answer["cause"], answer["said"]), (409, "no_switch", auto_update.in_words("no_switch")))
        self.assertEqual(self.asked, [], "nothing asked of the engine")
        self.server.update = None
        self.assertEqual(self.ask("POST", "/api/v1/local/update", {})[0], 409, "no engine under the page")


if __name__ == "__main__":
    unittest.main()
