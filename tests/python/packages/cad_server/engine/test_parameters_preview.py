"""A model at other values of its parameters, for one page (``cad_server.engine.parameters.Previewing``): built in
the model's warm worker with nothing written -- not its script, not its document, its version, its record or the
engine's cache, not the worker's last run that ``set`` builds again -- held for the page that asked under an id of
its own, read at the document's read routes alone, and let go when the page's values are the document's again,
when the document has a new version, or once nobody reads it. Refused by ``set``'s codes. Per document one
preview builds and the newest waits; a run of the script comes first."""

from __future__ import annotations

import json
import shutil
import tempfile
import threading
import types
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from tests.python.support import engine_daemon
from tests.python.support.parameters import save
from tests.python.support.paths import add_sources

add_sources()

from cad.engine import api, client  # noqa: E402
from cad.engine.ids import model_id  # noqa: E402
from cad.engine.parameters import ParameterRefused  # noqa: E402

SCRIPT = """\
import build123d as bd
from cad import model

from spec import PITCH

WALL = model.param("wall", 2.0, min=1, max=5)
HOLES = model.param("holes", 6, min=3, max=12)


@model
def bracket():
    if WALL > 4.5:
        raise ValueError(f"a wall of {WALL} leaves no room for the holes")
    return bd.Box(PITCH, 10 + HOLES, WALL)


@model
def plate():
    # Reached through globals(): its key falls back to the module's bytes, which a preview leaves as they are.
    return bd.Box(10, 10, globals()["WALL"])
"""
SPEC = 'from cad import model\n\nPITCH = model.param("pitch", 30.0, unit="mm")\n'


class PreviewCase(unittest.TestCase):
    """A model of the class's own folder, built on an engine of the class's own, and a page's reads of it."""

    @classmethod
    def setUpClass(cls) -> None:
        engine_daemon.isolate(cls.addClassCleanup)
        cls.folder = Path(tempfile.mkdtemp(prefix="parameters-preview-")).resolve()
        cls.addClassCleanup(shutil.rmtree, cls.folder, True)
        cls.script = cls.folder / "bracket.py"
        (cls.folder / "spec.py").write_text(SPEC, encoding="utf-8")
        cls.ident = model_id(cls.script, "bracket")
        cls.plate = model_id(cls.script, "plate")

    def setUp(self) -> None:
        self.script.write_text(SCRIPT, encoding="utf-8")
        report = api.build_script(self.script, None, progress=False)
        self.assertTrue(report.ok, report.models)
        self.serving = client.request({"op": "status"}, start=False)["serving"]
        self.token = client.request({"op": "http"}, start=False)["token"]

    def call(self, method: str, route: str, body: object = None, guard: bool = True) -> tuple[int, dict]:
        request = urllib.request.Request(
            f"{self.serving['url']}/api/v1/documents/{route}", method=method,
            data=None if body is None else json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {self.token}", "content-type": "application/json",
                     **({"x-cad-viewer": "1"} if guard else {})})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 - a loopback test
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.loads(error.read() or b"{}")

    def preview(self, values: dict, page: str = "page-a", ident: str | None = None) -> tuple[int, dict]:
        return self.call("POST", f"model/{ident or self.ident}/preview", {"values": values, "page": page})

    def shown(self, values: dict, ident: str | None = None) -> dict:
        status, said = self.preview(values, ident=ident)
        self.assertEqual(status, 200, said)
        self.assertIsNotNone(said["preview"], said)
        return said["preview"]

    def size(self, ident: str) -> list[float]:
        """The z of every part of document (or preview) ``ident``, from its parts' facts."""
        status, structure = self.call("GET", f"model/{ident}/structure")
        self.assertEqual(status, 200, structure)
        status, facts = self.call("GET", f"model/{ident}/measure")
        self.assertEqual(status, 200, facts)
        return sorted(round(row["box"]["max"][2] - row["box"]["min"][2], 6) for row in facts.values())

    def version(self, ident: str | None = None) -> str:
        return client.request({"op": "model_info", "id": ident or self.ident}, start=False)["model"]["version"]

    def wall(self, ident: str | None = None) -> tuple:
        row = next(row for row in api.inspect(ident or self.ident, query="structure", progress=False)["summary"]
                   ["parameters"] if row["name"] == "wall")
        return row["value"], row["writable"]


class PreviewTest(PreviewCase):
    def test_a_preview_is_the_model_at_those_values_and_nothing_else_changes(self) -> None:
        before, version = self.script.read_bytes(), self.version()
        self.assertEqual(self.size(self.ident), [2.0])
        shown = self.shown({"wall": 3.25, "holes": 6})
        self.assertEqual((shown["values"], shown["basis"]), ({"wall": 3.25}, version), "only what differs is previewed")
        self.assertTrue(shown["id"].startswith(f"{self.ident}~preview-"))
        self.assertEqual(self.size(shown["id"]), [3.25], "the preview's geometry is the model at those values")
        status, structure = self.call("GET", f"model/{shown['id']}/structure")
        self.assertEqual({row["name"]: row["value"] for row in structure["parameters"]}["wall"], 3.25)
        # Nothing else saw it: the script, the document, its version, its parameters, every other read.
        self.assertEqual(self.script.read_bytes(), before)
        self.assertEqual(self.version(), version)
        self.assertEqual(self.size(self.ident), [2.0])
        self.assertEqual(self.wall(), (2.0, True))
        self.assertEqual(api.inspect(self.ident, query="summary", progress=False)["summary"]["bounds"]["size"][2], 2.0)
        for route in (f"{shown['id']}", f"{shown['id']}/version", f"model/{shown['id']}/kinematics"):
            self.assertEqual(self.call("GET", route)[0], 404, route)
        self.assertEqual(self.call("POST", f"{shown['id']}/exports", {"source": {"doc": shown["id"]}})[0], 404)
        self.assertEqual(self.call("POST", f"model/{shown['id']}/parameters", {"values": {"wall": 3}})[0], 404)
        # The last run is the worker's still: a set writes the literal where that run recorded it, from 2.0.
        answer = save(self.ident, wall=2.5)
        self.assertEqual([(row["from"], row["to"]) for row in answer["written"]], [(2.0, 2.5)])
        self.assertEqual(self.script.read_bytes(), before.replace(b'"wall", 2.0', b'"wall", 2.5'))
        self.assertEqual(self.call("GET", f"model/{shown['id']}/structure")[0], 404, "a new version lets it go")

    def test_a_value_tried_before_is_the_memo_s(self) -> None:
        first = self.shown({"wall": 3.0})
        self.shown({"wall": 3.5})
        again = self.shown({"wall": 3.0})
        self.assertGreater(first["memo"]["misses"], 0)
        self.assertEqual(again["memo"]["misses"], 0, again["memo"])
        self.assertGreater(again["memo"]["hits"], 0)
        # The document's own values again: nothing built, the page's previews let go.
        status, said = self.preview({"wall": 2.0})
        self.assertEqual((status, said), (200, {"id": self.ident, "preview": None}))
        self.assertEqual(self.call("GET", f"model/{again['id']}/structure")[0], 404)

    def test_a_body_keyed_by_its_module_s_bytes_is_built_at_the_values_asked(self) -> None:
        self.assertEqual(self.size(self.plate), [2.0])
        self.assertEqual(self.size(self.shown({"wall": 4.0}, ident=self.plate)["id"]), [4.0])
        self.assertEqual(self.size(self.shown({"wall": 1.5}, ident=self.plate)["id"]), [1.5])

    def test_each_refusal_says_its_code_and_nothing_is_held(self) -> None:
        before = self.script.read_bytes()
        for values, status, code in (({"depth": 3}, 400, "unknown_parameter"), ({"pitch": 3}, 409, "not_writable"),
                                     ({"wall": 9}, 400, "out_of_range"), ({"wall": "3"}, 400, "not_a_number")):
            with self.subTest(values=values):
                got, said = self.preview(values)
                self.assertEqual((got, said.get("code")), (status, code), said)
        got, said = self.preview({"wall": 4.8})
        self.assertEqual((got, said["code"]), (409, "build_failed"))
        self.assertIn("ValueError: a wall of 4.8 leaves no room for the holes", said["detail"])
        self.assertEqual(self.size(self.ident), [2.0], "the document is as it was")
        # Bytes as they are: a text-mode append writes Windows' line ending, which the comparison below would not expect.
        with self.script.open("ab") as script:
            script.write(b"# edited, and not run\n")
        got, said = self.preview({"wall": 3.0})
        self.assertEqual((got, said["code"]), (409, "script_changed"))
        self.assertEqual(self.script.read_bytes(), before + b"# edited, and not run\n")

    def test_the_route_needs_the_guard_and_takes_values_and_a_page_alone(self) -> None:
        route = f"model/{self.ident}/preview"
        self.assertEqual(self.call("POST", route, {"values": {"wall": 3}, "page": "p"}, guard=False)[0], 403)
        self.assertEqual(self.call("POST", route, {"values": {"wall": 3}})[0], 400, "a page token is needed")
        self.assertEqual(self.call("POST", route, {"values": {"wall": 3}, "page": "../x"})[0], 400)
        self.assertEqual(self.call("POST", route, {"values": {"wall": 3}, "page": "p", "path": "x"})[0], 400)
        self.assertEqual(self.call("GET", route)[0], 405)
        self.assertEqual(self.call("POST", f"xbf/{self.ident}/preview", {"values": {}, "page": "p"})[0], 404)

    def test_a_document_no_live_worker_built_is_not_previewed(self) -> None:
        self.assertTrue(api.stop())
        engine_daemon.start()  # the document read from the engine's cache, served: no worker built it
        client.request({"op": "serve", "path": self.ident}, start=False)
        self.serving = client.request({"op": "status"}, start=False)["serving"]
        self.token = client.request({"op": "http"}, start=False)["token"]
        got, said = self.preview({"wall": 3.0})
        self.assertEqual((got, said.get("code")), (409, "no_worker"), said)


class _Worker:
    label, leased, op, environment, python, python_key = "/s.py", False, None, {}, None, None

    def __init__(self) -> None:
        self.state = {"last_run": {"request": {"script": "/s.py", "cwd": None, "env": {}}}}


class LatestWinsTest(unittest.TestCase):
    """``Previewing`` on a stand-in daemon whose worker's build is a gate the test opens."""

    def setUp(self) -> None:
        from cad.engine import parameters
        from cad_server.engine.parameters import Previewing, Setting

        folder = Path(tempfile.mkdtemp(prefix="parameters-preview-unit-")).resolve()
        self.addCleanup(shutil.rmtree, folder, True)
        script = folder / "s.py"
        script.write_bytes(b"W = 2.0\n")
        row = {"name": "wall", "value": 2.0, "kind": "float", "min": None, "max": None, "step": None, "unit": None,
               "file": str(script), "line": 1, "span": [4, 7], "digest": parameters.digest(b"W = 2.0\n"), "reason": None}
        self.worker = _Worker()
        self.built: list[dict] = []
        self.gate = threading.Event()
        self.started = threading.Event()

        test = self

        class Leased:
            def request(self, order, _send):
                test.built.append(order["values"])
                test.started.set()
                test.gate.wait(10)
                return {"done": {"ok": True, "structure": {"prototypes": []}, "shapes": [], "timings": {"total": 0.1},
                                 "memo": {}}}

        leased = Leased()
        self.worker_proc = leased
        self.held: dict[str, object] = {}
        server = types.SimpleNamespace(
            preview_shapes=lambda _ident, _held=(): {}, keep_preview=lambda ident, _s, _h: self.held.__setitem__(ident, 1),
            drop_previews=lambda idents: [self.held.pop(ident, None) for ident in idents], preview_read=lambda _i: 0.0)
        models = types.SimpleNamespace(live=lambda _ident: {"rows": [row], "worker": self.worker, "name": "m",
                                                            "script": str(script)},
                                       row=lambda _ident: {"version": "v1"})
        daemon = types.SimpleNamespace(models=models, server=server, busy_lock=threading.Lock(), busy=0, worked=0.0,
                                       supervisor=types.SimpleNamespace(live=lambda *_a: self.worker),
                                       lease=lambda *_a, **_k: self.worker, release=lambda _w: None)
        self.worker.request = leased.request  # type: ignore[attr-defined]
        self.previewing = daemon.previewing = Previewing(daemon)
        self.setting = daemon.setting = Setting(daemon)

    def ask(self, wall: float, answers: dict, page: str = "p") -> threading.Thread:
        def run() -> None:
            try:
                answers[wall] = self.previewing.preview("doc", {"wall": wall}, page)
            except ParameterRefused as refused:
                answers[wall] = refused.code
        thread = threading.Thread(target=run)
        thread.start()
        return thread

    def waiting(self) -> bool:
        with self.previewing.lock:
            slot = self.previewing.slots.get("doc") or {}
            return slot.get("waiting") is not None

    def test_one_builds_the_newest_waits_and_the_rest_are_superseded_unbuilt(self) -> None:
        answers: dict = {}
        threads = [self.ask(3.0, answers)]
        self.assertTrue(self.started.wait(10))
        for before, wall in ((None, 3.1), (3.1, 3.2), (3.2, 3.3)):
            threads.append(self.ask(wall, answers))
            while (before is not None and before not in answers) or not self.waiting():
                threading.Event().wait(0.01)
        self.gate.set()
        for thread in threads:
            thread.join(10)
        self.assertEqual(self.built, [{"wall": 3.0}, {"wall": 3.3}], "the first and the newest alone")
        self.assertEqual({wall: answers[wall].get("superseded", False) for wall in (3.1, 3.2)}, {3.1: True, 3.2: True})
        self.assertEqual(answers[3.3]["preview"]["values"], {"wall": 3.3})
        self.assertEqual(len(self.held), 2, "the page holds the last two")

    def test_a_run_of_the_script_comes_first(self) -> None:
        answers: dict = {}
        first = self.ask(3.0, answers)
        self.assertTrue(self.started.wait(10))
        waiting = self.ask(3.5, answers)
        while not self.waiting():
            threading.Event().wait(0.01)
        with self.setting.building("/s.py"):
            waiting.join(10)
            self.assertEqual(answers[3.5], "busy", "the waiting preview yields to the build")
            self.assertEqual(self.previewing.preview("doc", {"wall": 2.0}, "p"), {"id": "doc", "preview": None})
            refused = self.ask(4.0, answers)
            refused.join(10)
            self.assertEqual(answers[4.0], "busy", "and one asked while it runs is refused")
        self.gate.set()
        first.join(10)
        self.assertEqual(self.built, [{"wall": 3.0}])

    def test_previews_nobody_reads_are_let_go(self) -> None:
        import time

        from cad_server.engine.parameters import PREVIEW_IDLE

        self.gate.set()
        self.previewing.preview("doc", {"wall": 3.0}, "p")
        self.assertEqual(len(self.held), 1)
        self.previewing.expire(time.monotonic() + PREVIEW_IDLE / 2)
        self.assertEqual(len(self.held), 1)
        self.previewing.expire(time.monotonic() + PREVIEW_IDLE + 1)
        self.assertEqual((self.held, self.previewing.pages), ({}, {}))


if __name__ == "__main__":
    unittest.main()
