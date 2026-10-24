"""Quick Edit writes replayable JSON synchronously, never starting a render.

A packet is what ``cadgen snapshot`` reads: ``--annotation PACKET`` draws its ink, and
``--camera authored`` draws the view the ink was drawn in, found in the packet's jobs by label
(``cadgen.engine.snapshot``). Its readers are the replay asserted here.
"""

from __future__ import annotations

import http.client
import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from cadgen.engine.snapshot import _view_of, packet_visibility, parse_annotation, parse_measurements
from cadgen.viewer import handler as handler_module
from cadgen.viewer.http_app import create_cad_app
from cadgen.viewer.prompt_files import PromptFiles

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
ANNOTATION = {"units": "mm", "parts": {}, "marks": [
    {"id": "1", "kind": "stroke", "part": None, "points": [0, 0, 0, 1, 1, 1] * 128, "color": "#ff2d55", "width": 2}]}
CAMERA = {"position": [10, -10, 10], "target": [0, 0, 0], "up": [0, 0, 1]}


class PromptFilesRouteTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.model = self.tmp / "part.stl"
        self.model.write_text("solid part\nendsolid part\n", encoding="utf-8")
        self.notes = self.tmp / "notes.txt"
        self.notes.write_text("not a model\n", encoding="utf-8")
        self.files = self.tmp / "prompt-files"
        app = create_cad_app(host="127.0.0.1", port=0)
        app.prompt_files = PromptFiles(directory=self.files)
        server = handler_module.serve(app, "127.0.0.1", 0)
        self.port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

    def call(self, method: str, path: str, body=None, *, guard: bool = True) -> tuple[int, bytes, str]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {"x-cadgen-viewer": "1", "content-type": "application/json"} if guard else {}
        try:
            connection.request(method, path, body=None if body is None else json.dumps(body), headers=headers)
            response = connection.getresponse()
            return response.status, response.read(), response.getheader("content-type") or ""
        finally:
            connection.close()

    def request(self, **overrides) -> dict:
        return {"acceptInline": True, "name": "part.stl", "input": str(self.model), "annotation": ANNOTATION, "views": [
            {"label": "view 1", "camera": CAMERA, "display": {"appearance": "dark"}, "width": 640, "height": 480},
            {"label": "view 2", "camera": "iso"},
        ], **overrides}

    def test_a_prompt_writes_replayable_json_without_rendering_or_image_files(self) -> None:
        status, body, _ = self.call("POST", "/__cad/prompt-files", self.request())
        answer = json.loads(body)
        snapshot_path = self.files / "part-1.snapshot.json"
        self.assertEqual((status, answer), (200, {"ok": True, "snapshot": str(snapshot_path)}))
        self.assertEqual([path.name for path in self.files.iterdir()], ["part-1.snapshot.json"])
        # Replay from another folder: one file carries the ink and each view it was drawn in.
        packet = json.loads(snapshot_path.read_text(encoding="utf-8"))
        self.assertEqual(parse_annotation(str(snapshot_path)), ANNOTATION)
        view = _view_of(packet, "view 1")
        self.assertEqual((view.camera, view.size), (CAMERA, (640, 480)))
        self.assertEqual(_view_of(packet, "view 2").camera, "iso")
        common = {"output": {"padding": 0, "tightFrame": False}}
        self.assertEqual(packet, {"input": str(self.model), "annotation": ANNOTATION, "jobs": [
            {**common, "camera": CAMERA, "display": {"appearance": "dark"},
             "outputs": [{"path": str(self.files / "part-1-view-1.png"), "label": "view 1", "width": 640, "height": 480}]},
            {**common, "camera": "iso", "outputs": [{"path": str(self.files / "part-1-view-2.png"), "label": "view 2"}]},
        ]})
        status, _, content_type = self.call("GET", "/__cad/prompt-files/part-1.snapshot.json")
        self.assertEqual((status, content_type), (200, "application/json; charset=utf-8"))

    def test_the_parts_hidden_where_the_ink_was_drawn_are_the_packets_and_each_views_own(self) -> None:
        """Each view's display says what it hid and isolated (part refs, as ``--display`` takes them);
        the packet's own are the view the last mark was drawn in, which ``--annotation`` reads."""
        ink = {"units": "mm", "parts": {}, "marks": [{**ANNOTATION["marks"][0], "points": [0, 0, 0, 1, 1, 1], "view": "view 2"}]}
        plain = {"mode": "solid", "grid": False}
        hid = {**plain, "hidden": ["/w/kit.xbf#lid"], "isolated": ["/w/kit.xbf#hand"]}

        def packet(annotation, *displays):
            views = [{"label": f"view {at + 1}", "camera": CAMERA, "display": display} for at, display in enumerate(displays)]
            status, body, _ = self.call("POST", "/__cad/prompt-files", self.request(annotation=annotation, views=views))
            self.assertEqual(status, 200, body)
            answer = json.loads(body)
            return json.loads(answer["inline"] if "inline" in answer else Path(answer["snapshot"]).read_text(encoding="utf-8"))

        drawn = packet(ink, plain, hid)
        self.assertEqual([job["display"] for job in drawn["jobs"]], [plain, hid])
        self.assertEqual((drawn["hidden"], packet_visibility(drawn)), (hid["hidden"], {"hidden": hid["hidden"], "isolated": hid["isolated"]}))
        # Ink drawn where nothing was hidden leaves the packet nothing to hide; no ink, nothing at all.
        self.assertEqual(packet_visibility(packet(ink, hid, plain)), {})
        self.assertNotIn("hidden", packet(None, plain, hid))

    def test_a_prompts_measurements_are_drawn_over_every_view_its_job_renders(self) -> None:
        mark = {"start": [0, 0, 0], "end": [10, 0, 0], "label": "10.00 mm", "color": "#d59090"}
        _, body, _ = self.call("POST", "/__cad/prompt-files", self.request(annotation=None, measurements=[mark]))
        packet = json.loads(json.loads(body)["inline"])
        self.assertEqual(packet["measurements"], [mark])
        self.assertTrue(all("measurements" not in job for job in packet["jobs"]))
        self.assertEqual(parse_measurements(packet["measurements"]), [mark])

    def test_a_drawings_view_is_its_plan_view_and_its_job_carries_ink_and_measurements(self) -> None:
        """A DXF's Quick Edit: the window on screen as a plan-view camera, the ink on the sheet and the
        measurements -- no 3D framing; its label, by which the ink names the view it was drawn in."""
        drawing = self.tmp / "panel.dxf"
        drawing.write_text("0\nSECTION\n", encoding="utf-8")
        plan = {"position": [50, 30, 120], "target": [50, 30, 0], "up": [0, 1, 0], "orthographicHalfHeight": 30}
        mark = {"start": [0, 0, 0], "end": [100, 0, 0], "label": "100.00 mm", "color": "#d59090"}
        status, body, _ = self.call("POST", "/__cad/prompt-files", {
            "name": "panel.dxf", "input": str(drawing), "annotation": ANNOTATION, "measurements": [mark],
            "views": [{"label": "view 1", "camera": plan, "width": 1600, "height": 900}]})
        self.assertEqual(status, 200, body)
        packet = json.loads((self.files / "panel-1.snapshot.json").read_text(encoding="utf-8"))
        self.assertEqual(packet["jobs"][0]["camera"], plan)
        self.assertEqual(parse_measurements(packet["measurements"]), [mark])
        self.assertEqual(parse_annotation(packet), ANNOTATION)
        self.assertNotIn("output", packet["jobs"][0])
        self.assertEqual(packet["jobs"][0]["outputs"], [{"path": str(self.files / "panel-1-view-1.png"), "label": "view 1",
                                                         "width": 1600, "height": 900}])

    def test_a_prompt_without_an_annotation_names_none_and_the_next_prompt_is_numbered_on(self) -> None:
        _, first, _ = self.call("POST", "/__cad/prompt-files", self.request(annotation=None))
        _, second, _ = self.call("POST", "/__cad/prompt-files", self.request(annotation=None))
        self.assertNotIn("annotation", json.loads(first))
        packet = json.loads(json.loads(second)["inline"])
        self.assertIn("part-2-view-1.png", packet["jobs"][0]["outputs"][0]["path"])
        self.assertNotIn("annotation", json.loads(json.loads(first)["inline"]))
        self.assertEqual(list(self.files.glob("*.json")), [])

    def test_already_open_clients_get_a_real_file_unless_they_accept_inline(self) -> None:
        request = self.request(annotation=None, views=[{"label": "current view", "camera": CAMERA}])
        request.pop("acceptInline")
        for acceptance in (None, False, True):
            body_request = request if acceptance is None else {**request, "acceptInline": acceptance}
            status, body, _ = self.call("POST", "/__cad/prompt-files", body_request)
            self.assertEqual(status, 200, body)
            answer = json.loads(body)
            if acceptance is True:
                self.assertIn("inline", answer)
                self.assertNotIn("snapshot", answer)
                packet = json.loads(answer["inline"])
            else:
                self.assertNotIn("inline", answer)
                self.assertTrue(Path(answer["snapshot"]).is_file())
                packet = json.loads(Path(answer["snapshot"]).read_text(encoding="utf-8"))
            self.assertEqual(_view_of(packet, "current view").camera, CAMERA)
        self.assertEqual(len(list(self.files.glob("*.snapshot.json"))), 2)

    def test_inline_cutoff_counts_utf8_bytes_and_both_forms_are_replayable(self) -> None:
        mark = {"start": [0, 0, 0], "end": [1, 0, 0], "label": "", "color": "#ffffff"}
        request = self.request(annotation=None, measurements=[mark], views=[{"label": "current view", "camera": CAMERA}])
        status, body, _ = self.call("POST", "/__cad/prompt-files", request)
        self.assertEqual(status, 200, body)
        base = json.loads(body)["inline"]
        mark["label"] = "a" * (1024 - len(base.encode("utf-8")) - 2) + "é"
        status, body, _ = self.call("POST", "/__cad/prompt-files", request)
        inline = json.loads(body)["inline"]
        self.assertEqual(len(inline.encode("utf-8")), 1024)
        self.assertEqual(list(self.files.glob("*.json")), [])
        self.assertEqual(_view_of(json.loads(inline), "current view").camera, CAMERA)
        mark["label"] += "a"
        status, body, _ = self.call("POST", "/__cad/prompt-files", request)
        self.assertEqual(status, 200, body)
        answer = json.loads(body)
        self.assertNotIn("inline", answer)
        saved = json.loads(Path(answer["snapshot"]).read_text(encoding="utf-8"))
        self.assertEqual(_view_of(saved, "current view").camera, CAMERA)
        self.assertEqual(parse_measurements(saved["measurements"])[0]["label"], mark["label"])

    def test_a_packets_input_is_a_files_path_or_a_documents_id_and_never_a_script(self) -> None:
        ident = "6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab"
        status, body, _ = self.call("POST", "/__cad/prompt-files", self.request(input=ident, name="bracket"))
        self.assertEqual(status, 200, body)
        packet = json.loads(Path(json.loads(body)["snapshot"]).read_text(encoding="utf-8"))
        self.assertEqual(packet["input"], ident)
        script = self.tmp / "parts.py"
        script.write_text("print(1)\n", encoding="utf-8")
        for named in (str(script), f"{script}::cube"):
            status, body, _ = self.call("POST", "/__cad/prompt-files", self.request(input=named))
            self.assertEqual(status, 400, named)

    def test_a_request_snapshot_would_refuse_is_refused_before_anything_renders(self) -> None:
        for request, said in (
            ([], "requested as an object"),
            (self.request(views=[]), "at least one"),
            (self.request(extra=1), "unknown field(s): extra"),
            (self.request(acceptInline="true"), "acceptInline is a boolean"),
            (self.request(sketch=ANNOTATION), "unknown field(s): sketch"),
            (self.request(input="part.stl"), "absolute path"),
            (self.request(input=str(self.tmp / "gone.step")), "no file at"),
            (self.request(views=[{"camera": "iso"}]), "views[0].label"),
            (self.request(views=[{"label": "a", "camera": "iso", "width": 0}]), "views[0].width"),
            (self.request(annotation={"marks": {}}), "annotation is null or an object"),
            # snapshot's own parsers: a camera key it does not take, a display it does not draw
            (self.request(views=[{"label": "a", "camera": {"projection": "perspective"}}]), "camera has no projection"),
            (self.request(views=[{"label": "a", "camera": "iso", "display": {"mode": "sketch"}}]), "no display mode"),
            (self.request(views=[{"label": "a", "camera": "iso", "display": {"hidden": "lid"}}]), "display.hidden is a list of part refs"),
            (self.request(views=[{"label": "a", "camera": "authored"}]), "the view's own camera"),
            (self.request(measurements={}), "measurements is null or a list"),
            # a measurement snapshot would not draw: its own check
            (self.request(measurements=[{"start": [0, 0], "end": [1, 0, 0], "label": "", "color": "#ffffff"}]), "measurements[0].start"),
            # a file snapshot does not draw
            (self.request(input=str(self.notes)), "is no file cadgen snapshot draws"),
        ):
            status, body, _ = self.call("POST", "/__cad/prompt-files", request)
            self.assertEqual(status, 400, request)
            self.assertEqual(json.loads(body)["ok"], False)
            self.assertIn(said, json.loads(body)["error"])
        self.assertEqual(sorted(path.name for path in self.files.iterdir()) if self.files.exists() else [], [])

    def test_retired_save_route_does_not_write(self):
        self.assertEqual(self.call("POST", "/__cad/prompt-files/save", {"kind": "annotation", "data": ANNOTATION})[0], 404)
        self.assertFalse(self.files.exists())

    def test_render_polling_is_not_an_endpoint(self) -> None:
        self.assertEqual(self.call("GET", "/__cad/prompt-files?id=nope")[0], 404)

    def test_files_are_served_from_the_prompt_files_directory_only_and_to_the_viewer_only(self) -> None:
        _, body, _ = self.call("POST", "/__cad/prompt-files", self.request())
        (self.files / "part-1-view-1.png").write_bytes(PNG)
        self.assertEqual(self.call("GET", "/__cad/prompt-files/part-1-view-1.png")[0], 404)
        (self.tmp / "secret.json").write_text("{}", encoding="utf-8")
        for name in ("..%2Fsecret.json", "../secret.json", "missing.png", "part-1.job.txt", ""):
            self.assertEqual(self.call("GET", f"/__cad/prompt-files/{name}")[0], 404, name)
        self.assertEqual(self.call("GET", "/__cad/prompt-files/part-1-current.png", guard=False)[0], 403)
        self.assertEqual(self.call("GET", "/__cad/prompt-files?id=old", guard=False)[0], 404)


if __name__ == "__main__":
    unittest.main()
