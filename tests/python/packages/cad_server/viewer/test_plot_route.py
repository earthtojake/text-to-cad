"""A KiCad board's ``plot`` and ``drc`` (``GET /api/v1/documents/kicad_pcb/<id>/plot|drc``) against a real
launched server, and the route's rules (``cad_server.viewer.plots``).

A board is opened by its absolute path, as every file is. Its plot is drawn from KiCad's refill of a copy
(stood in for here: KiCad runs in the KiCad suite alone) and kept by the board's bytes, so an edit saved
under the same path is the next answer's new key, and the same bytes are answered without plotting again.
The board is the test board (``tests/python/support/kicad_board.py``), written fresh into a temporary
folder; the cache is the test file's own (``CAD_CACHE_DIR``). A KiCad
schematic's plot is its own route's (``kicad_sch``): every sheet a page, read again on each request.
"""

from __future__ import annotations

import gzip
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.kicad_board import BOARD, write_board
from tests.python.support.kicad_schematic import write_schematic

from cad.engine.formats.kicad import PLOT_SCHEMA_VERSION
from cad_server.viewer import handler as handler_module
from cad_server.viewer.compressed import Coded
from cad_server.viewer.http_app import create_cad_app
from cad_server.viewer.plots import BoardAnswers

# The test board's VBUS track, 1 mm wide as saved; the stand-in refill writes it 0.5 mm, so a plot says
# which bytes it was drawn from.
SAVED = '(width 1) (layer "F.Cu") (net "VBUS")'
REFILLED = '(width 0.5) (layer "F.Cu") (net "VBUS")'


class Refill:
    """KiCad's refill stood in for: a copy of the board with the track changed, or a failure."""

    def __init__(self, fails: bool = False) -> None:
        self.calls, self.fails = 0, fails

    def __call__(self, board: Path, out_dir: Path) -> Path:
        self.calls += 1
        if self.fails:
            raise RuntimeError("no kicad-cli here")
        copy = out_dir / board.name
        copy.write_text(board.read_text(encoding="utf-8").replace(SAVED, REFILLED), encoding="utf-8")
        return copy


def width(body: bytes) -> float:
    payload = json.loads(body)
    tracks = [track for track in payload["board"]["tracks"] if track.get("net") == "VBUS"]
    return tracks[0]["width"]


class PlotRules(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name)
        self.board = write_board(self.folder)
        # Each test's own cache: what one kept is no other's.
        cache = mock.patch.dict("os.environ", {"CAD_CACHE_DIR": str(self.folder / "cache")})
        cache.start()
        self.addCleanup(cache.stop)

    def answered(self, answers: BoardAnswers, product: str = "plot", **options):
        status, body, key = answers.response(product, str(self.board), **options)
        return status, body.data if isinstance(body, Coded) else body, key

    def test_the_plot_is_drawn_from_kicads_refill_and_kept_by_the_boards_bytes(self) -> None:
        refill = Refill()
        answers = BoardAnswers(refill=refill)
        status, body, key = self.answered(answers)
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual((payload["schemaVersion"], payload["kind"], payload["unrouted"]), (PLOT_SCHEMA_VERSION, "board", 1))
        self.assertEqual(payload["pours"], {"refilled": True})
        self.assertEqual(width(body), 0.5, "drawn from the refilled copy")
        self.assertEqual(self.board.read_text(encoding="utf-8"), BOARD, "the person's file is never written")
        # The same bytes: answered from memory, and by a new engine from the disk, without KiCad.
        self.assertEqual(self.answered(answers), (200, body, key))
        self.assertEqual(self.answered(BoardAnswers(refill=refill)), (200, body, key))
        self.assertEqual(refill.calls, 1)
        # A client that names the key it holds is told it is current.
        self.assertEqual(self.answered(answers, if_none_match=f'"{key}"')[0], 304)
        # An edit is a new key: plotted (and refilled) again.
        self.board.write_text(BOARD.replace("blinky", "blinky v2"), encoding="utf-8")
        status, changed, other = self.answered(answers)
        self.assertEqual((status, refill.calls), (200, 2))
        self.assertNotEqual(other, key)
        # The board's document keeps what was made of its bytes as they are now, never of the old ones.
        from cad.engine.formats.kicad.poured import folder

        self.assertEqual(sorted(path.name for path in folder(self.board, other).parent.iterdir()), [other])

    def test_without_kicad_the_board_is_plotted_as_saved_and_says_so(self) -> None:
        refill = Refill(fails=True)
        status, body, _key = self.answered(BoardAnswers(refill=refill))
        self.assertEqual(status, 200)
        pours = json.loads(body)["pours"]
        self.assertFalse(pours["refilled"])
        self.assertIn("no kicad-cli here", pours["warning"])
        self.assertEqual(width(body), 1.0, "drawn as saved")
        # Nothing kept on disk: a new engine tries KiCad again.
        self.answered(BoardAnswers(refill=refill))
        self.assertEqual(refill.calls, 2)

    def test_a_board_that_takes_longer_than_the_hold_is_asked_again(self) -> None:
        release = threading.Event()

        def slow(board: Path, out_dir: Path) -> Path:
            release.wait(10)
            return Refill()(board, out_dir)

        answers = BoardAnswers(refill=slow, hold_seconds=0, retry_ms=250)
        self.assertEqual(self.answered(answers)[:2], (202, {"state": "plotting", "retryMs": 250}))
        release.set()
        answers.hold_seconds = 10
        self.assertEqual(self.answered(answers)[0], 200)

    def test_what_the_route_will_not_take(self) -> None:
        answers = BoardAnswers(refill=Refill())
        self.assertEqual(answers.response("plot", str(self.folder / "other.kicad_pcb")), (404, {"error": "Not found"}, ""))
        for ref, message in (("", r"absolute path of a \.kicad_pcb"), ("blinky.kicad_pcb", r"absolute"),
                             (str(self.folder / "part.step"), r"part\.step is neither")):
            with self.subTest(ref=ref), self.assertRaisesRegex(ValueError, message):
                answers.response("plot", ref)
        (self.folder / "broken.kicad_pcb").write_text("(kicad_sch)", encoding="utf-8")
        status, body, _key = answers.response("plot", str(self.folder / "broken.kicad_pcb"))
        self.assertEqual(status, 400)
        self.assertIn("broken.kicad_pcb is not a KiCad board", body["error"])

    def test_the_drc_is_kicads_check_kept_by_the_boards_bytes_its_items_named(self) -> None:
        found = {"ok": False, "path": str(self.board), "summary": "", "findings": [
            {"severity": "error", "code": "unconnected_items", "message": "Missing connection", "location": "(20, 23) mm",
             "hint": None}],
                 "measurements": {"drc": [{"check": "unconnected", "severity": "error", "type": "unconnected_items",
                                           "description": "Missing connection", "at": [20.0, 23.175], "items": [
                                               {"uuid": "x", "description": "Pad 2 [LED] of D1 on F.Cu", "pos": [20.0, 23.175]},
                                               {"uuid": "7a1c0000-0000-4000-8000-000000000001", "description": "Track",
                                                "pos": [5.0, 15.0]}]}]}}
        calls = []

        def drc(board, board_key):
            calls.append(board_key)
            return json.loads(json.dumps(found))

        with mock.patch("cad_server._internal.boards.drc", drc):
            answers = BoardAnswers(refill=Refill())
            status, body, key = self.answered(answers, "drc")
            self.assertEqual(self.answered(answers, "drc"), (status, body, key))
        self.assertEqual((status, calls), (200, [key]))
        items = json.loads(body)["measurements"]["drc"][0]["items"]
        self.assertEqual([item.get("ref") for item in items], ["#D1.2", "#track:7a1c0000-0000-4000-8000-000000000001"])


class Codings(unittest.TestCase):
    def test_the_coding_is_the_browsers_choice_zstd_first(self) -> None:
        import importlib.util

        from cad_server.viewer.compressed import chosen, encode

        # zstd where the standard library has it: from Python 3.14 (``compression.zstd``); on 3.13, the floor, gzip.
        zstd = importlib.util.find_spec("compression") is not None
        self.assertEqual(chosen("gzip, deflate, br, zstd"), "zstd" if zstd else "gzip")
        self.assertEqual(chosen("gzip, deflate"), "gzip")
        self.assertEqual(chosen("*"), "gzip")
        for accept in ("", "identity", "gzip;q=0", "br"):
            with self.subTest(accept=accept):
                self.assertIsNone(chosen(accept))
        data = b'{"items":[' + b'[1.25,2.5],' * 4000 + b'[0,0]]}'
        self.assertEqual(gzip.decompress(encode(data, "gzip")), data)


class PlotRoute(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name)
        self.board = write_board(self.folder)
        # Each test's own cache: what one kept is no other's.
        cache = mock.patch.dict("os.environ", {"CAD_CACHE_DIR": str(self.folder / "cache")})
        cache.start()
        self.addCleanup(cache.stop)
        app = create_cad_app(host="127.0.0.1", port=0, dist_dir="")
        app.boards = BoardAnswers(refill=Refill(), hold_seconds=30)
        server = handler_module.serve(app, "127.0.0.1", 0)
        self.port = server.server_address[1]
        app.port = self.port
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

    def request(self, method: str, target: str, body: dict | None = None, headers: dict | None = None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            conn.request(method, target, body=None if body is None else json.dumps(body).encode(),
                         headers={**({"x-cad-viewer": "1"} if method == "POST" else {}), **(headers or {})})
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def opened(self, path: Path, kind: str = "kicad_pcb") -> str:
        status, _, body = self.request("POST", "/api/v1/documents", {"path": str(path)})
        self.assertEqual(status, 201, body[:400])
        reply = json.loads(body)
        self.assertEqual(reply["kind"], kind)
        return reply["api"]

    def test_a_board_opened_by_its_path_answers_its_plot_as_the_file_is_now(self) -> None:
        api = self.opened(self.board)
        status, headers, first = self.request("GET", f"{api}/plot")
        self.assertEqual(status, 200, first[:400])
        self.assertEqual(headers["content-type"], "application/json; charset=utf-8")
        self.assertEqual(json.loads(first)["kind"], "board")
        self.assertNotIn("content-encoding", {name.lower() for name in headers}, "no coding asked, none sent")
        tag = headers["etag"]
        # Compressed for a browser that takes it, the same bytes once decoded; a client naming the key is told
        # it is current.
        status, coded_headers, coded = self.request("GET", f"{api}/plot", headers={"accept-encoding": "gzip, deflate"})
        self.assertEqual((status, coded_headers["content-encoding"], coded_headers["etag"]), (200, "gzip", tag))
        self.assertEqual(gzip.decompress(coded), first)
        self.assertLess(len(coded), len(first) / 3)
        self.assertEqual(self.request("GET", f"{api}/plot", headers={"if-none-match": tag})[0], 304)
        self.board.write_text(BOARD.replace('(width 1) (layer "F.Cu") (net "VBUS")',
                                            '(width 0.4) (layer "F.Cu") (net "VBUS")'), encoding="utf-8")
        status, headers, changed = self.request("GET", f"{api}/plot")
        self.assertEqual(status, 200)
        self.assertNotEqual(first, changed)
        self.assertNotEqual(headers["etag"], tag)
        # Its routes are its plot, its DRC and its source; another kind's read is a 404 naming them.
        status, _, body = self.request("GET", f"{api}/drawing")
        self.assertEqual((status, json.loads(body)["hint"]), (404, "a kicad_pcb's routes are plot, models, drc, source"))

    def test_a_boards_models_are_answered_by_document_ids_as_the_files_are_now(self) -> None:
        library = self.folder / "library"
        (library / "Resistor_SMD.3dshapes").mkdir(parents=True)
        # Bytes, with both line endings: the source route serves the file as it is, on every platform.
        (library / "Resistor_SMD.3dshapes" / "R_0603_1608Metric.step").write_bytes(b"ISO-10303-21;\r\nresistor\n")
        env = mock.patch.dict("os.environ", {"CAD_KICAD_3DMODELS": str(library)})
        env.start()
        self.addCleanup(env.stop)
        api = self.opened(self.board)
        status, _, body = self.request("GET", f"{api}/models")
        self.assertEqual(status, 200, body[:400])
        table = json.loads(body)["models"]
        resistor = table["${KICAD9_3DMODEL_DIR}/Resistor_SMD.3dshapes/R_0603_1608Metric.wrl"]
        self.assertEqual((resistor["file"], resistor["api"]), ("R_0603_1608Metric.step", f"/api/v1/documents/step/{resistor['document']}"))
        # D1's model is the project's own, not there yet: missing, and no path in the answer.
        self.assertEqual(table["${KIPRJMOD}/models/led.step"], {"file": "led.step", "missing": "not-found"})
        self.assertNotIn(json.dumps(str(self.folder))[1:-1].encode(), body)
        # The engine's STEP routes know the resolved file by its id from now on.
        status, _, step = self.request("GET", f"{resistor['api']}/source")
        self.assertEqual((status, step), (200, b"ISO-10303-21;\r\nresistor\n"))
        # The table is the files as they are now: the model added is the next answer's.
        (self.folder / "models").mkdir()
        (self.folder / "models" / "led.step").write_bytes(b"ISO-10303-21; led\n")
        led = json.loads(self.request("GET", f"{api}/models")[2])["models"]["${KIPRJMOD}/models/led.step"]
        self.assertEqual((led["file"], led["api"].startswith("/api/v1/documents/step/")), ("led.step", True))

    def test_a_schematic_answers_every_sheet_a_page(self) -> None:
        schematic = write_schematic(self.folder / "divider")
        status, _, body = self.request("GET", f"{self.opened(schematic.with_name('load.kicad_sch'), 'kicad_sch')}/plot")
        self.assertEqual(status, 200, body[:400])
        payload = json.loads(body)
        self.assertEqual((payload["kind"], [page["path"] for page in payload["sheets"]]), ("schematic", ["/", "/Load/"]))
        # Each page on KiCad's drawing sheet, as KiCad's schematic editor shows it: its frame and its title block.
        # Each sheet's title block is its own file's.
        for page, shown in zip(payload["sheets"], ({"Title: Divider", "Id: 1/2"}, {"Sheet: /Load/", "Id: 2/2"})):
            [sheet] = [layer for layer in page["layers"] if layer["id"] == "drawing_sheet"]
            texts = {item["text"] for item in sheet["items"] if item["t"] == "text"}
            self.assertTrue(shown | {"A", "1"} <= texts, texts)
        # The viewer reads the sheet on screen alone: with the hierarchy's index first, then without it.
        api = self.opened(schematic, "kicad_sch")
        status, _, body = self.request("GET", f"{api}/plot?sheet=/Load/")
        page = json.loads(body)
        self.assertEqual((status, [sheet["path"] for sheet in page["sheets"]]), (200, ["/Load/"]))
        self.assertEqual([sheet["path"] for sheet in page["schematic"]["sheets"]], ["/", "/Load/"])
        status, _, body = self.request("GET", f"{api}/plot?sheet=%2F&index=0")
        page = json.loads(body)
        self.assertEqual((status, [sheet["path"] for sheet in page["sheets"]], "schematic" in page), (200, ["/"], False))
        status, _, body = self.request("GET", f"{api}/plot?sheet=/Power/")
        self.assertEqual(status, 400, body[:400])
        self.assertIn("has no sheet /Power/", json.loads(body)["error"])

    def test_a_file_that_is_no_board_is_a_400_saying_why(self) -> None:
        broken = self.folder / "broken.kicad_pcb"
        broken.write_text("(kicad_sch)", encoding="utf-8")
        status, _, body = self.request("GET", f"{self.opened(broken)}/plot")
        self.assertEqual(status, 400, body[:400])
        self.assertIn("broken.kicad_pcb is not a KiCad board", json.loads(body)["error"])


class SchematicReads(unittest.TestCase):
    """A schematic's hierarchy is parsed once per revision of its files: a page asked for again, or
    another page, reads none of them; an edit to any sheet, or a file beside them, reads it anew."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = write_schematic(Path(self.tmp.name) / "divider")

    def test_the_hierarchy_is_read_once_per_revision(self) -> None:
        import os

        from cad.engine.formats.kicad import schematic
        from cad_server.viewer.plots import SchematicAnswers

        answers = SchematicAnswers()
        real = schematic.read_schematic_index
        with mock.patch.object(schematic, "read_schematic_index", side_effect=real) as reads:
            page = lambda sheet, index=True: json.loads(answers.payload(str(self.root), sheet, index))  # noqa: E731
            first = page("/")
            self.assertEqual([sheet["path"] for sheet in first["schematic"]["sheets"]], ["/", "/Load/"])
            self.assertNotIn("schematic", page("/Load/", False))
            self.assertEqual(page("/"), first)
            self.assertEqual(reads.call_count, 1)
            # An edit to the child sheet (a new stamp) reads the hierarchy again.
            child = self.root.with_name("load.kicad_sch")
            stat = child.stat()
            os.utime(child, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
            page("/Load/", False)
            self.assertEqual(reads.call_count, 2)
            page("/Load/", False)
            self.assertEqual(reads.call_count, 2)
            # So does a file put beside them (the folder's stamp).
            (self.root.parent / "notes.txt").write_text("x", encoding="utf-8")
            folder = self.root.parent.stat()
            os.utime(self.root.parent, ns=(folder.st_atime_ns, folder.st_mtime_ns + 1_000_000))
            page("/")
            self.assertEqual(reads.call_count, 3)


if __name__ == "__main__":
    unittest.main()
