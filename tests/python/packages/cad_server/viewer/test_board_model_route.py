"""A KiCad board in 3D (``GET /api/v1/documents/kicad_pcb/<id>/glb``): KiCad's GLB of it, made in the
background one board at a time, the board asked for last first, and kept by the board's bytes
(``cad_server.viewer.board_models``, ``cad_server._internal.boards.model``).

KiCad is stood in for: the queue's rules with a ``make`` the test holds, and the make itself
(``boards.model``) with a Python process that writes a small GLB where KiCad's would, or waits to be killed.
The board is the test board, written fresh into a temporary folder; the cache is the test's own.
"""

from __future__ import annotations

import gzip
import http.client
import json
import struct
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.kicad_board import BOARD, write_board

from cad_server.viewer import handler as handler_module
from cad_server.viewer.board_models import BoardModels
from cad_server.viewer.http_app import create_cad_app
from cad_server.viewer.plots import BoardAnswers

WAIT = 30


def glb(*names: str) -> bytes:
    """A GLB as KiCad writes one: its root's children, each part named by its reference, the board unnamed."""
    nodes = [{"children": list(range(1, len(names) + 2))}, *({"name": name} for name in names), {"mesh": 0}]
    chunk = json.dumps({"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": nodes}).encode()
    chunk += b" " * (-len(chunk) % 4)
    return b"glTF" + struct.pack("<II", 2, 20 + len(chunk)) + struct.pack("<I", len(chunk)) + b"JSON" + chunk


# KiCad stood in for, as ``cad.kicad._model``'s process: a GLB of J1 and R1 written into OUT_DIR (D1's model
# not found), or, with WAIT, a process that waits to be killed (and says it started).
STAND_IN = """
import json, pathlib, sys, time
board, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
started = pathlib.Path(sys.argv[3]) if len(sys.argv) > 3 else None
if started:
    started.write_text("started")
    time.sleep(120)
target = out / (board.stem + ".glb")
target.write_bytes(bytes.fromhex(sys.argv[4] if len(sys.argv) > 4 else %r))
print(json.dumps({"glb": str(target), "modelled": ["J1", "R1"], "missing": ["D1"]}))
"""


class Held:
    """A ``make`` the test holds: each call says it started, then waits to be released (or cancelled)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.started = threading.Event()
        self.release = threading.Event()
        self.lock = threading.Lock()
        self.running = 0
        self.most = 0
        self.cancels: list[threading.Event] = []

    def __call__(self, board: Path, board_key: str, cancel: threading.Event, stage) -> dict:
        with self.lock:
            self.calls.append((board.parent.name, board_key))
            self.cancels.append(cancel)
            self.running += 1
            self.most = max(self.most, self.running)
        stage("export")
        self.started.set()
        try:
            while not self.release.wait(0.05):
                if cancel.is_set():
                    from cad_server._internal.boards import Cancelled

                    raise Cancelled()
            return {"modelled": ["J1"], "missing": ["D1", "R1"]}
        finally:
            with self.lock:
                self.running -= 1


class Case(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name)
        self.board = write_board(self.folder)
        cache = mock.patch.dict("os.environ", {"CAD_CACHE_DIR": str(self.folder / "cache")})
        cache.start()
        self.addCleanup(cache.stop)

    def until(self, condition, what: str) -> None:
        done = threading.Event()
        for _ in range(WAIT * 20):
            if condition():
                return
            done.wait(0.05)
        self.fail(f"never {what}")


class Rules(Case):
    def models(self, make, **options) -> BoardModels:
        memory: dict[tuple[str, str], dict] = {}
        return BoardModels(key=BoardAnswers().key, make=make, kept=lambda board, key: memory.get((str(board), key)),
                           read=lambda board, key: b"", retry_ms=50, **options)

    def test_one_board_at_a_time_the_one_asked_for_last_first(self) -> None:
        for name in ("a", "b", "c"):
            (self.folder / name).mkdir()
        boards = [write_board(self.folder / name) for name in ("a", "b", "c")]
        held = Held()
        models = self.models(held)
        status, body, _key = models.status(str(boards[0]))
        self.assertEqual((status, body["state"]), (202, "queued"))
        self.assertTrue(held.started.wait(WAIT))
        self.assertEqual(models.status(str(boards[0]))[1]["progress"], {"kind": "board-model", "stage": "export"})
        # B then C asked for while A is made: C, the last, is next.
        models.status(str(boards[1]))
        models.status(str(boards[2]))
        held.release.set()
        self.until(lambda: all(models.status(str(board))[0] == 200 for board in boards), "made all three")
        self.assertEqual([folder for folder, _key in held.calls], ["a", "c", "b"])
        self.assertEqual(held.most, 1, "never two at once")
        status, body, key = models.status(str(boards[2]))
        self.assertEqual(body, {"state": "ready", "key": key, "modelled": ["J1"], "missing": ["D1", "R1"]})

    def test_a_changed_board_stops_the_make_of_its_old_bytes(self) -> None:
        held = Held()
        models = self.models(held)
        _status, _body, old = models.status(str(self.board))
        self.assertTrue(held.started.wait(WAIT))
        self.board.write_text(BOARD.replace("blinky", "blinky v2"), encoding="utf-8")
        status, body, new = models.status(str(self.board))
        self.assertNotEqual(old, new)
        self.assertEqual(status, 202)
        self.until(lambda: held.cancels[0].is_set(), "stopped the stale make")
        self.until(lambda: len(held.calls) == 2, "made the new bytes")
        self.assertEqual(held.calls[1][1], new)
        held.release.set()
        self.until(lambda: models.status(str(self.board))[0] == 200, "made it")
        self.assertEqual(models.status(str(self.board))[2], new)

    def test_what_it_will_not_take_and_what_kicad_refuses(self) -> None:
        def refuses(board, key, cancel, stage):
            raise RuntimeError("kicad-cli pcb export glb failed: no board")

        models = self.models(refuses)
        self.assertEqual(models.status(str(self.folder / "other.kicad_pcb")), (404, {"error": "Not found"}, ""))
        with self.assertRaisesRegex(ValueError, r"load\.kicad_sch is not one"):
            (self.folder / "load.kicad_sch").write_text("(kicad_sch)", encoding="utf-8")
            models.status(str(self.folder / "load.kicad_sch"))
        models.status(str(self.board))
        self.until(lambda: models.status(str(self.board))[0] == 400, "refused")
        self.assertIn("KiCad could not draw the board in 3D: kicad-cli pcb export glb failed", models.status(str(self.board))[1]["error"])


class Made(Case):
    """``boards.model``: KiCad's process stood in for, the model kept gzipped beside the board's plot."""

    def stand_in(self, *extra: str):
        def argv(python, board, out_dir):
            return [sys.executable, "-c", STAND_IN % glb("J1", "R1").hex(), str(board), str(out_dir), *extra]

        return mock.patch.multiple("cad_server._internal.boards", _python=lambda: sys.executable, _model_argv=argv)

    def test_the_model_is_kept_by_the_boards_bytes_and_pruned_with_them(self) -> None:
        from cad.engine.formats.kicad.poured import folder, key

        from cad_server._internal import boards

        board_key = key(self.board)
        stages: list[str] = []
        with self.stand_in():
            made = boards.model(self.board, board_key, stage=stages.append)
        self.assertEqual((made, stages), ({"modelled": ["J1", "R1"], "missing": ["D1"]}, ["kicad", "export"]))
        self.assertEqual(gzip.decompress(boards.model_bytes(self.board, board_key)), glb("J1", "R1"))
        self.assertEqual(boards.model_kept(self.board, board_key), made)
        self.assertEqual(self.board.read_text(encoding="utf-8"), BOARD, "the board is never written")
        # Kept: answered again without KiCad.
        with mock.patch("cad_server._internal.boards._model_argv", side_effect=AssertionError("made twice")):
            self.assertEqual(boards.model(self.board, board_key), made)
        # A new revision's products prune the old one's model with its plot.
        self.board.write_text(BOARD.replace("blinky", "blinky v2"), encoding="utf-8")
        with self.stand_in():
            boards.model(self.board, key(self.board))
        self.assertEqual([path.name for path in folder(self.board, key(self.board)).parent.iterdir()], [key(self.board)])

    def test_a_kicad_glb_names_its_parts_by_reference(self) -> None:
        from cad.kicad._export import missing_parts
        from cad.kicad._model import part_nodes

        self.assertEqual(part_nodes(glb("J1", "R1")), ["J1", "R1"])
        self.assertEqual(part_nodes(b"not a glb"), [])
        said = "Could not add 3D model for C10.\nCould not add 3D model for C2.\nCould not add 3D model for C2.\n"
        self.assertEqual(missing_parts(said), ["C2", "C10"])

    def test_a_cancelled_make_kills_kicads_process(self) -> None:
        from cad.engine.formats.kicad.poured import key

        from cad_server._internal import boards

        started = self.folder / "started"
        cancel = threading.Event()
        failed: list[BaseException] = []

        def run() -> None:
            try:
                with self.stand_in(str(started)):
                    boards.model(self.board, key(self.board), cancel=cancel)
            except BaseException as error:  # noqa: BLE001 - what the make raised, read below
                failed.append(error)

        thread = threading.Thread(target=run)
        thread.start()
        self.until(started.is_file, "started KiCad")
        cancel.set()
        thread.join(WAIT)
        self.assertFalse(thread.is_alive(), "the make waited out the process")
        self.assertEqual([type(error).__name__ for error in failed], ["Cancelled"])
        self.assertIsNone(boards.model_kept(self.board, key(self.board)))


class Route(Case):
    """The route over HTTP, against a real server: the model's bytes, and the board's 2D plot beside a make."""

    def serve(self, models=None) -> str:
        app = create_cad_app(host="127.0.0.1", port=0, dist_dir="")

        def refill(board: Path, out_dir: Path) -> Path:
            (out_dir / board.name).write_bytes(board.read_bytes())
            return out_dir / board.name

        app.boards = BoardAnswers(refill=refill, hold_seconds=30)
        app.board_models = models or BoardModels(key=app.boards.key, retry_ms=50)
        server = handler_module.serve(app, "127.0.0.1", 0)
        self.port = server.server_address[1]
        app.port = self.port
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        status, _, body = self.request("POST", "/api/v1/documents", {"path": str(self.board)})
        self.assertEqual(status, 201, body[:400])
        return json.loads(body)["api"]

    def request(self, method: str, target: str, body: dict | None = None, headers: dict | None = None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=WAIT)
        try:
            conn.request(method, target, body=None if body is None else json.dumps(body).encode(),
                         headers={**({"x-cad-viewer": "1"} if method == "POST" else {}), **(headers or {})})
            response = conn.getresponse()
            return response.status, {name.lower(): value for name, value in response.getheaders()}, response.read()
        finally:
            conn.close()

    def test_the_board_in_3d_is_made_in_the_background_and_answered_from_the_disk(self) -> None:
        argv = lambda python, board, out_dir: [sys.executable, "-c", STAND_IN % glb("J1", "R1").hex(), str(board), str(out_dir)]  # noqa: E731
        patched = mock.patch.multiple("cad_server._internal.boards", _python=lambda: sys.executable, _model_argv=argv)
        patched.start()
        self.addCleanup(patched.stop)
        api = self.serve()
        status, _, body = self.request("GET", f"{api}/glb?prepare=1")
        self.assertIn(status, (200, 202), body[:400])
        answers: list[dict] = []
        self.until(lambda: answers.append(json.loads(self.request("GET", f"{api}/glb?prepare=1")[2])) or answers[-1]["state"] == "ready",
                   "made the model")
        ready = answers[-1]
        self.assertEqual((ready["modelled"], ready["missing"]), (["J1", "R1"], ["D1"]))
        status, headers, coded = self.request("GET", f"{api}/glb", headers={"accept-encoding": "gzip, deflate"})
        self.assertEqual((status, headers["content-type"], headers["content-encoding"]), (200, "model/gltf-binary", "gzip"))
        self.assertEqual(headers["etag"], f'"{ready["key"]}"')
        self.assertEqual(gzip.decompress(coded), glb("J1", "R1"))
        status, headers, plain = self.request("GET", f"{api}/glb")
        self.assertEqual((status, plain, "content-encoding" in headers), (200, glb("J1", "R1"), False))
        self.assertEqual(self.request("GET", f"{api}/glb", headers={"if-none-match": f'"{ready["key"]}"'})[0], 304)
        self.assertEqual(self.board.read_text(encoding="utf-8"), BOARD, "the board is never written")
        # Its routes name it; a schematic has no 3D model.
        schematic = self.folder / "blinky.kicad_sch"
        schematic.write_text("(kicad_sch (version 20250114) (generator \"eeschema\"))", encoding="utf-8")
        status, _, body = self.request("POST", "/api/v1/documents", {"path": str(schematic)})
        status, _, body = self.request("GET", f"{json.loads(body)['api']}/glb")
        self.assertEqual((status, json.loads(body)["hint"]), (404, "a kicad_sch's routes are plot, drc, glb, source"))

    def test_the_2d_plot_is_answered_while_the_3d_model_is_made(self) -> None:
        held = Held()
        self.addCleanup(held.release.set)
        api = self.serve(BoardModels(key=BoardAnswers().key, make=held, kept=lambda board, key: None, retry_ms=50))
        self.assertEqual(self.request("GET", f"{api}/glb?prepare=1")[0], 202)
        self.assertTrue(held.started.wait(WAIT), "the make started")
        status, _, body = self.request("GET", f"{api}/plot")
        self.assertEqual(status, 200, body[:400])
        self.assertEqual(json.loads(body)["kind"], "board")
        self.assertEqual((held.running, held.release.is_set()), (1, False), "drawn while the 3D make still runs")
        status, _, body = self.request("GET", f"{api}/glb?prepare=1")
        self.assertEqual((status, json.loads(body)["state"]), (202, "exporting"))
