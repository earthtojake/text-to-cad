"""Open in's routes: ``GET /api/v1/local/open-in?id=`` lists a document's files -- a model's script
and the files its last build wrote, a file's own path -- with the apps found here for each, and
``POST /api/v1/local/open`` opens one of them in one of those apps. The apps are a fake table and the
opener a recorder: no test starts an app or looks for one."""
from __future__ import annotations

import base64
import http.client
import json
import os
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from cad_server._internal import apps
from cad_server.mcp.tunnel import ViewerTunnel

from .test_http_layer import ServerFixture

apps_open_file = apps.open_file  # the real opener, before the tests replace it with a recorder

MODEL = "6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab"
UNKNOWN = "0f1c2a4e-1b2c-5d3e-8f4a-0123456789ab"
FOUND = {"vscode": "/A/Visual Studio Code.app", "cursor": "/A/Cursor.app", "freecad": "/A/FreeCAD.app",
         "bambu": "/A/BambuStudio.app", "blender": "/A/Blender.app"}
STABLE = apps.KiCad("9.0.6", date(2025, 11, 1), "/K/pcbnew.app", "/K/eeschema.app", False)
NIGHTLY = apps.KiCad("10.99.0-5334-ge37c27a8ce", date(2026, 11, 6), "/N/pcbnew.app", "/N/eeschema.app", True)
WRITE = {"x-cad-viewer": "1", "Content-Type": "application/json"}


def entry(app: str) -> dict:
    return {"id": app, "name": apps.APPS[app]}


class OpenInRoutesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = ServerFixture()
        self.addCleanup(self.fixture.close)
        root = Path(self.fixture.root)
        self.script = root / "bracket.py"
        self.script.write_text("", encoding="utf-8")
        self.xbf, self.step, self.stl = root / "XBF" / "bracket.xbf", root / "bracket.step", root / "bracket.stl"
        self.xbf.parent.mkdir()
        self.xbf.write_bytes(b"x")
        self.step.write_bytes(b"ISO-10303-21;")
        # The engine's record of the model: its script and the files its last build wrote (the
        # STL since deleted, a second STEP the first one's kind already names).
        self.model = {"source": {"name": "bracket", "script": str(self.script)}, "version": "v1", "builtAt": 1.0,
                      "state": "held", "files": [str(self.xbf), str(self.step), str(self.stl), str(root / "b.stp")]}
        self.opener = mock.Mock()
        self.found = dict(FOUND)
        for patch in (mock.patch("cad_server.viewer.model_catalog.request", side_effect=self.engine),
                      mock.patch.object(apps.DETECTED, "found", side_effect=lambda: dict(self.found)),
                      mock.patch.object(apps, "open_file", self.opener)):
            patch.start()
            self.addCleanup(patch.stop)

    def engine(self, ask, start):
        if ask["id"] == MODEL:
            return {"model": self.model}
        return {"failed": f"no document {ask['id']} is held", "state": ""}

    def get(self, ident) -> tuple[int, dict]:
        status, _, body = self.fixture.request("GET", f"/api/v1/local/open-in?id={ident}")
        return status, json.loads(body)

    def post(self, payload, headers=WRITE) -> tuple[int, dict | None]:
        status, _, body = self.fixture.request("POST", "/api/v1/local/open", headers=headers,
                                               body=json.dumps(payload).encode())
        return status, json.loads(body) if body else None

    def step_file(self) -> str:
        status, _, body = self.fixture.request("GET", f"/api/v1/documents?path={self.step}")
        self.assertEqual(status, 200)
        return json.loads(body)["documents"][0]["id"]

    def test_a_models_targets_are_its_script_and_the_files_its_last_build_wrote(self) -> None:
        status, answer = self.get(MODEL)
        self.assertEqual(status, 200)
        self.assertEqual(answer, {"targets": [
            {"target": "source", "kind": "script", "name": "bracket.py", "present": True,
             "apps": [entry("vscode"), entry("cursor")]},
            {"target": "export:xbf", "kind": "xbf", "name": "bracket.xbf", "present": True, "apps": []},
            {"target": "export:step", "kind": "step", "name": "bracket.step", "present": True,
             "apps": [entry("freecad"), entry("bambu")]},
            {"target": "export:stl", "kind": "stl", "name": "bracket.stl", "present": False,
             "apps": [entry("bambu"), entry("freecad"), entry("blender")]},
        ], "fileManager": apps.file_manager()})

    def test_a_model_without_its_script_says_so_and_one_never_built_here_has_its_script_alone(self) -> None:
        self.script.unlink()
        [source, *_] = self.get(MODEL)[1]["targets"]
        self.assertEqual((source["name"], source["present"]), ("bracket.py", False))
        # A model taken up from the engine's cache, no build of it written this run, and no script named.
        self.model = {"source": {"name": "bracket"}, "version": "v1", "state": "held"}
        self.assertEqual(self.get(MODEL)[1]["targets"], [{"target": "source", "kind": "script", "name": "",
                                                          "present": False, "apps": [entry("vscode"), entry("cursor")]}])

    def test_a_files_target_is_the_file_itself(self) -> None:
        ident = self.step_file()
        status, answer = self.get(ident)
        self.assertEqual(status, 200)
        self.assertEqual(answer["targets"], [{"target": "source", "kind": "step", "name": "bracket.step", "present": True,
                                              "apps": [entry("freecad"), entry("bambu")]}])

    def test_an_unknown_document_is_a_404(self) -> None:
        for ident in (UNKNOWN, "bracket", ""):
            with self.subTest(ident=ident):
                status, answer = self.get(ident)
                self.assertEqual(status, 404)
                self.assertIn("error", answer)
        self.assertEqual(self.post({"id": UNKNOWN, "target": "source", "app": "default"})[0], 404)
        self.opener.assert_not_called()

    def test_open_starts_the_found_app_on_the_known_path(self) -> None:
        step = self.step_file()
        for payload, expected in (({"id": MODEL, "target": "export:step", "app": "freecad"}, (str(self.step), FOUND["freecad"])),
                                  ({"id": MODEL, "target": "source", "app": "cursor"}, (str(self.script), FOUND["cursor"])),
                                  ({"id": MODEL, "target": "source", "app": "default"}, (str(self.script), None)),
                                  ({"id": step, "target": "source", "app": "bambu"},
                                   (os.path.normpath(self.fixture.app.file_of(step)), FOUND["bambu"]))):
            with self.subTest(payload=payload):
                self.opener.reset_mock()
                self.assertEqual(self.post(payload), (204, None))
                self.opener.assert_called_once_with(*expected)

    def kicad_file(self, name: str, stamp: int) -> str:
        """A KiCad file of the format ``stamp``, as a document: its id."""
        path = Path(self.fixture.root) / name
        path.write_text(f"({path.suffix[1:]} (version {stamp}))\n", encoding="utf-8")
        status, _, body = self.fixture.request("GET", f"/api/v1/documents?path={path}")
        self.assertEqual(status, 200)
        return json.loads(body)["documents"][0]["id"]

    def listed(self, ident: str) -> dict:
        [target] = self.get(ident)[1]["targets"]
        return target

    def test_a_board_a_stable_can_read_offers_both_kicads_and_withholds_the_default(self) -> None:
        self.found.update(kicad=STABLE, **{"kicad-nightly": NIGHTLY})
        self.assertEqual(self.listed(self.kicad_file("stable.kicad_pcb", 20241229)), {
            "target": "source", "kind": "kicad_pcb", "name": "stable.kicad_pcb", "present": True, "default": False,
            "apps": [{"id": "kicad", "name": "KiCad 9.0.6"}, {"id": "kicad-nightly", "name": "KiCad 10.99 nightly"}]})

    def test_a_nightlys_board_shows_the_stable_refusing_it_and_only_the_nightly_opens_it(self) -> None:
        self.found.update(kicad=STABLE, **{"kicad-nightly": NIGHTLY})
        ident = self.kicad_file("nightly.kicad_pcb", 20261031)
        self.assertEqual(self.listed(ident)["apps"], [{"id": "kicad", "name": "KiCad 9.0.6", "refuses": "newer"},
                                                      {"id": "kicad-nightly", "name": "KiCad 10.99 nightly"}])
        status, answer = self.post({"id": ident, "target": "source", "app": "kicad"})
        self.assertEqual(status, 400)
        self.assertIn("KiCad 9.0.6 cannot open nightly.kicad_pcb", answer["error"])
        self.assertIn("newer KiCad", answer["error"])
        self.assertIn("KiCad", answer["hint"])
        self.opener.assert_not_called()
        self.assertEqual(self.post({"id": ident, "target": "source", "app": "kicad-nightly"}), (204, None))
        self.opener.assert_called_once_with(os.path.normpath(self.fixture.app.file_of(ident)), NIGHTLY)
        # A refused KiCad is not among what an app not offered is told to name instead, nor is the default.
        status, answer = self.post({"id": ident, "target": "source", "app": "vscode"})
        self.assertEqual(status, 400)
        self.assertEqual(answer["hint"], "name one of kicad-nightly")

    def test_a_schematic_is_read_against_the_schematic_formats(self) -> None:
        self.found.update(kicad=STABLE, **{"kicad-nightly": NIGHTLY})
        # 20250114 is a 9.0 schematic, and past a 9.0 board's format.
        current = self.kicad_file("current.kicad_sch", 20250114)
        self.assertEqual(self.listed(current)["apps"], [{"id": "kicad", "name": "KiCad 9.0.6"},
                                                        {"id": "kicad-nightly", "name": "KiCad 10.99 nightly"}])
        self.assertEqual(self.post({"id": current, "target": "source", "app": "kicad"}), (204, None))
        self.opener.assert_called_once_with(os.path.normpath(self.fixture.app.file_of(current)), STABLE)
        self.opener.reset_mock()
        newer = self.kicad_file("newer.kicad_sch", 20261108)  # past both, the nightly built two days before it
        self.assertEqual(self.listed(newer)["apps"], [{"id": "kicad", "name": "KiCad 9.0.6", "refuses": "newer"},
                                                      {"id": "kicad-nightly", "name": "KiCad 10.99 nightly", "refuses": "newer"}])
        self.assertEqual(self.post({"id": newer, "target": "source", "app": "kicad-nightly"})[0], 400)
        self.opener.assert_not_called()

    def test_an_mjcf_opens_in_mujoco_studio_where_the_installation_runs_it(self) -> None:
        path = Path(self.fixture.root) / "scene.xml"
        path.write_text('<mujoco><worldbody><geom type="sphere" size="0.1"/></worldbody></mujoco>\n', encoding="utf-8")
        status, _, body = self.fixture.request("GET", f"/api/v1/documents?path={path}")
        self.assertEqual(status, 200)
        ident = json.loads(body)["documents"][0]["id"]
        self.assertEqual(self.listed(ident), {"target": "source", "kind": "mjcf", "name": "scene.xml", "present": True,
                                              "apps": []}, "no Studio found, none offered")
        studio = apps.Studio("/env/bin/mujoco-studio")
        self.found["mujoco-studio"] = studio
        self.assertEqual(self.listed(ident)["apps"], [{"id": "mujoco-studio", "name": "MuJoCo Studio"}])
        self.assertEqual(self.post({"id": ident, "target": "source", "app": "mujoco-studio"}), (204, None))
        self.opener.assert_called_once_with(os.path.normpath(self.fixture.app.file_of(ident)), studio)

    def test_a_kicad_files_default_handler_stays_withheld_and_refused(self) -> None:
        # Nothing shows that its handler is a KiCad that can open it: with no KiCad here, no app at all, and the
        # default is said not to be offered; an open is refused, and the opener itself refuses it and any plain app.
        ident = self.kicad_file("blinky.kicad_pcb", 20241229)
        self.assertEqual(self.listed(ident), {"target": "source", "kind": "kicad_pcb", "name": "blinky.kicad_pcb",
                                              "present": True, "apps": [], "default": False})
        status, answer = self.post({"id": ident, "target": "source", "app": "default"})
        self.assertEqual(status, 400)
        self.assertIn("never opened in its default app", answer["error"])
        status, answer = self.post({"id": ident, "target": "source", "app": "kicad"})
        self.assertEqual(status, 400)
        self.assertEqual(answer["hint"], "reveal it in the file manager and open it there")
        self.opener.assert_not_called()
        spawn = mock.Mock()
        for name in ("blinky.kicad_pcb", "blinky.kicad_pro", "BLINKY.KICAD_SCH"):
            for app in (None, "/usr/bin/pcbnew"):
                with self.subTest(name=name, app=app), self.assertRaises(PermissionError):
                    apps_open_file(name, app, platform="linux", spawn=spawn)
        spawn.assert_not_called()

    def test_a_kicad_file_gone_is_a_404_not_a_refusal(self) -> None:
        self.found.update(kicad=STABLE)
        ident = self.kicad_file("gone.kicad_pcb", 20261031)
        Path(self.fixture.app.file_of(ident)).unlink()
        self.assertEqual(self.post({"id": ident, "target": "source", "app": "kicad"})[0], 404)
        self.opener.assert_not_called()

    def test_open_refuses_what_the_server_does_not_know(self) -> None:
        step = self.step_file()
        for payload in ({"id": MODEL, "target": "export:step", "app": "orca"},        # not found here
                        {"id": MODEL, "target": "export:step", "app": "vscode"},      # found, not for STEP
                        {"id": MODEL, "target": "export:3mf", "app": "bambu"},        # no such file written
                        {"id": MODEL, "target": str(self.step), "app": "freecad"},    # a path is no target
                        {"id": step, "target": "export:step", "app": "freecad"},      # a file has its source alone
                        {"id": MODEL, "target": "source", "app": "/bin/sh"},
                        {"id": MODEL, "target": "source", "app": "default", "path": "/etc/passwd"},
                        {"id": MODEL, "target": "source"}):
            with self.subTest(payload=payload):
                status, answer = self.post(payload)
                self.assertEqual(status, 400)
                self.assertEqual(set(answer), {"error", "hint"})
        # The file of a target it has, gone.
        self.assertEqual(self.post({"id": MODEL, "target": "export:stl", "app": "bambu"})[0], 404)
        self.script.unlink()
        self.assertEqual(self.post({"id": MODEL, "target": "source", "app": "default"})[0], 404)
        self.opener.assert_not_called()

    def test_open_needs_the_write_header_and_only_posts(self) -> None:
        payload = {"id": MODEL, "target": "source", "app": "vscode"}
        self.assertEqual(self.post(payload, headers={"Content-Type": "application/json"})[0], 403)
        self.assertEqual(self.fixture.request("GET", "/api/v1/local/open")[0], 405)
        self.assertEqual(self.fixture.request("POST", "/api/v1/local/open-in", headers=WRITE, body=b"{}")[0], 405)
        self.opener.assert_not_called()

    def test_both_routes_are_reachable_through_the_cad_apps_tunnel(self) -> None:
        tunnel = ViewerTunnel(app=self.fixture.app)
        reply = tunnel.serve(method="GET", url=f"http://cad.invalid/api/v1/local/open-in?id={MODEL}", headers={}, body=b"")
        self.assertEqual(reply["status"], 200)
        self.assertEqual(json.loads(base64.b64decode(reply["body"])), self.get(MODEL)[1])
        body = json.dumps({"id": MODEL, "target": "export:step", "app": "bambu"}).encode()
        reply = tunnel.serve(method="POST", url="http://cad.invalid/api/v1/local/open", headers=WRITE, body=body)
        self.assertEqual(reply["status"], 204)
        self.opener.assert_called_once_with(str(self.step), FOUND["bambu"])


class OpenInCredentialsTest(unittest.TestCase):
    """The engine admits both routes by the credentials every route takes."""

    @classmethod
    def setUpClass(cls) -> None:
        from cad.engine.serve import Server
        from cad_server._internal.engine_host import http_factory

        cls.server = Server(isolated=True, mesh_mode="inline", http_factory=http_factory)
        with mock.patch.object(apps.DETECTED, "warm"):  # nothing here looks for this computer's apps
            cls.server.start()
        cls.link = cls.server.http.app.link()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.stop()

    def ask(self, method: str, path: str, headers: dict, body: bytes = b"") -> int:
        conn = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=20)
        try:
            conn.request(method, path, body=body or None,
                         headers={"Host": f"127.0.0.1:{self.server.port}", **headers})
            response = conn.getresponse()
            response.read()
            return response.status
        finally:
            conn.close()

    def test_refused_without_credentials(self) -> None:
        body = json.dumps({"id": UNKNOWN, "target": "source", "app": "default"}).encode()
        with mock.patch.object(apps, "open_file") as opener, mock.patch.object(apps.DETECTED, "found", return_value={}):
            for headers, statuses in (({}, (403, 403)), ({"Authorization": f"Bearer {self.link}"}, (404, 404))):
                with self.subTest(credential=bool(headers)):
                    self.assertEqual((self.ask("GET", f"/api/v1/local/open-in?id={UNKNOWN}", headers),
                                      self.ask("POST", "/api/v1/local/open", {**headers, **WRITE}, body)), statuses)
            opener.assert_not_called()


if __name__ == "__main__":
    unittest.main()
