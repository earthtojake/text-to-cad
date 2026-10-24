"""``GET /__cad/drawing`` against a real launched server, and the answers it holds.

The fixture writes its own drawings with ezdxf into a fresh temporary folder and
points the store at a temporary directory, which the route never writes: it holds
its answers in memory, by the bytes it read. Nothing here reads the sample
corpus. A drawing is named by its absolute path, as every file is; every refusal
asserts both the status and that the secret bytes never appear in the body.
"""

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
from urllib.parse import quote

from unittest import mock

import ezdxf

from cadgen.drawing_payload import DRAWING_PAYLOAD_SCHEMA_VERSION
from cadgen.viewer import handler as handler_module
from cadgen.viewer.drawings import HELD, DrawingRenders
from cadgen.viewer.http_app import create_cad_app

SECRET = "TOP-SECRET-BYTES"


def write_drawing(path: Path, build) -> Path:
    document = ezdxf.new("R2010", setup=True)
    document.header["$INSUNITS"] = 4
    build(document, document.modelspace())
    path.parent.mkdir(parents=True, exist_ok=True)
    document.saveas(str(path))
    return path


def plate(document, modelspace) -> None:
    document.layers.add("CUT", color=1)
    modelspace.add_lwpolyline(
        [(0, 0), (40, 0), (40, 20), (0, 20)], close=True, dxfattribs={"layer": "CUT"}
    )
    modelspace.add_circle((20, 10), 4, dxfattribs={"layer": "CUT"})
    modelspace.add_text("PLATE", height=3).set_placement((2, 22))


class DrawingRouteFixture:
    """``base/project`` behind a live server."""

    def __init__(self) -> None:
        self.base = tempfile.mkdtemp()
        self.root = os.path.join(self.base, "project")
        os.makedirs(self.root)

        write_drawing(Path(self.root, "plate.dxf"), plate)
        write_drawing(Path(self.root, "nested", "bracket.dxf"), plate)
        write_drawing(Path(self.root, ".worktree", "private.dxf"), plate)
        # Deliberately secret-free: ezdxf names the offending LINE in its
        # parse error, and that line rides out in the 400's message.
        Path(self.root, "notes.dxf").write_text("this is not a drawing\n", encoding="utf-8")
        Path(self.root, "part.step").write_text(f"ISO-10303-21; {SECRET}\n", encoding="utf-8")
        Path(self.root, "passwd").write_text(SECRET, encoding="utf-8")

        self.app = create_cad_app(host="127.0.0.1", port=0, dist_dir="")
        self.server = handler_module.serve(self.app, "127.0.0.1", 0)
        self.port = self.server.server_address[1]
        self.app.port = self.port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def path(self, rel: str) -> str:
        return os.path.join(self.root, rel)

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        shutil.rmtree(self.base, ignore_errors=True)

    def request(self, target: str):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            conn.request("GET", target)
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def drawing(self, file_param):
        """The answer, asked again while the drawing renders (202), as the client asks."""
        while True:
            status, headers, body = self.request(f"/__cad/drawing?file={quote(str(file_param), safe='')}")
            if status != 202:
                return status, headers, body


class DrawingRouteTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = DrawingRouteFixture()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fixture.close()

    def assertDenied(self, status, body, expected) -> None:
        self.assertIn(status, expected, body[:400])
        self.assertNotIn(SECRET.encode("ascii"), body)


class ItServesTheDrawing(DrawingRouteTestCase):
    def test_a_drawing_named_by_its_absolute_path_serves_the_payload(self) -> None:
        status, headers, body = self.fixture.drawing(self.fixture.path("plate.dxf"))
        self.assertEqual(status, 200, body[:400])
        self.assertEqual(headers["content-type"], "application/json; charset=utf-8")
        self.assertEqual(headers["cache-control"], "no-store")
        # The viewer serves bytes to render, never a save-as.
        self.assertNotIn("content-disposition", {name.lower() for name in headers})
        payload = json.loads(body)
        self.assertEqual(payload["schemaVersion"], DRAWING_PAYLOAD_SCHEMA_VERSION)
        self.assertEqual(payload["units"]["insunits"], 4)
        self.assertEqual(len(payload["bounds"]), 4)
        self.assertTrue(payload["primitives"])
        self.assertIn("CUT", {layer["name"] for layer in payload["layers"]})
        # The body is the compact encoding, and the same bytes every time.
        self.assertEqual(int(headers["content-length"]), len(body))
        self.assertNotIn(b", ", body)
        self.assertNotIn("content-encoding", {name.lower() for name in headers})
        self.assertEqual(self.fixture.drawing(self.fixture.path("plate.dxf"))[2], body)

    def test_a_drawing_anywhere_serves(self) -> None:
        # Nested, or under a hidden folder: a file that is named is never refused for where it is.
        for rel in ("nested/bracket.dxf", ".worktree/private.dxf"):
            with self.subTest(rel=rel):
                status, _, body = self.fixture.drawing(self.fixture.path(rel))
                self.assertEqual(status, 200, body[:400])
                self.assertTrue(json.loads(body)["primitives"])


class ItRefusesWhatItShould(DrawingRouteTestCase):
    def test_a_ref_that_is_not_an_absolute_path_is_a_400(self) -> None:
        for ref in ("plate.dxf", "../project/plate.dxf"):
            with self.subTest(ref=ref):
                status, _, body = self.fixture.drawing(ref)
                self.assertEqual(status, 400, body[:400])
                self.assertIn(b"absolute path", body)

    def test_another_extension_is_a_400_that_says_what_the_route_takes(self) -> None:
        for rel in ("part.step", "passwd"):
            with self.subTest(rel=rel):
                status, _, body = self.fixture.drawing(self.fixture.path(rel))
                self.assertDenied(status, body, {400})
                self.assertIn(b".dxf", body)

    def test_no_file_parameter_says_what_to_send(self) -> None:
        status, _, body = self.fixture.request("/__cad/drawing")
        self.assertEqual(status, 400, body[:400])
        self.assertIn(b"?file=", body)

    def test_a_missing_drawing_is_a_404(self) -> None:
        status, _, body = self.fixture.drawing(self.fixture.path("absent.dxf"))
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(body), {"error": "Not found"})

    def test_a_dxf_that_is_not_a_dxf_is_a_400_carrying_the_reason(self) -> None:
        status, _, body = self.fixture.drawing(self.fixture.path("notes.dxf"))
        self.assertDenied(status, body, {400})
        message = json.loads(body)["error"]
        self.assertIn("notes.dxf", message)
        self.assertIn("audit", message, "the error must say what to do about it")

    def test_a_null_byte_in_the_ref_is_refused(self) -> None:
        status, _, body = self.fixture.drawing(self.fixture.path("plate\x00.dxf"))
        self.assertDenied(status, body, {400})

    def test_the_route_is_get_only(self) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", self.fixture.port, timeout=10)
        try:
            conn.request("POST", f"/__cad/drawing?file={quote(self.fixture.path('plate.dxf'), safe='')}",
                         headers={"x-cadgen-viewer": "1"})
            response = conn.getresponse()
            body = response.read()
        finally:
            conn.close()
        self.assertEqual(response.status, 405)
        self.assertNotIn(b'"primitives"', body)


class OneRenderPerDrawing(unittest.TestCase):
    """A render runs off the request, once per drawing's bytes, and every request joins it.

    The render is held on an event, so "still rendering" is a state the test sets rather than a
    race it hopes to win; the answer comes from the render itself, then from memory.
    """

    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.drawing = write_drawing(self.base / "plate.dxf", plate)
        self.release = threading.Event()
        self.calls = []

    def render(self, outcome):
        def rendered(path, data):
            self.calls.append((path, data))
            self.release.wait(30)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        return mock.patch("cadgen.drawing_payload.build_drawing_payload", side_effect=rendered)

    def test_requests_while_it_renders_join_it_and_the_next_has_its_payload(self) -> None:
        renders = DrawingRenders(hold_seconds=0, retry_ms=750)
        with self.render({"payload": 1}):
            self.assertEqual(renders.response(str(self.drawing)), (202, {"state": "drawing", "retryMs": 750}))
            self.assertEqual(renders.response(str(self.drawing))[0], 202)
            self.assertTrue(renders.any_in_flight())
            self.release.set()
            renders.hold_seconds = 30
            self.assertEqual(renders.response(str(self.drawing)), (200, b'{"payload":1}'))
        # Rendered once, from the bytes the request read.
        self.assertEqual(self.calls, [(str(self.drawing), self.drawing.read_bytes())])
        self.assertFalse(renders.any_in_flight())

    def test_a_drawing_that_will_not_render_is_reported_to_the_request_that_follows(self) -> None:
        crashes = []
        renders = DrawingRenders(hold_seconds=0, on_crash=crashes.append)
        with self.render(RuntimeError("ezdxf tripped")):
            self.assertEqual(renders.response(str(self.drawing))[0], 202)
            self.release.set()
            renders.hold_seconds = 30
            self.assertEqual(renders.response(str(self.drawing)), (400, {"error": "ezdxf tripped"}))
            self.assertEqual(renders.response(str(self.drawing)), (400, {"error": "ezdxf tripped"}))
        self.assertEqual([str(error) for error in crashes], ["ezdxf tripped"], "a bug is counted once, by the render")


class HeldByItsBytes(unittest.TestCase):
    """An answer is held in memory by the bytes it was rendered from: the last ``HELD``, the one
    asked for least recently going first; nothing is written anywhere."""

    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.renders = DrawingRenders(hold_seconds=30)
        self.rendered = []
        from cadgen import drawing_payload

        real = drawing_payload.build_drawing_payload

        def counted(path, data):
            self.rendered.append(Path(path).name)
            return real(path, data)

        patcher = mock.patch("cadgen.drawing_payload.build_drawing_payload", side_effect=counted)
        patcher.start()
        self.addCleanup(patcher.stop)

    def drawing(self, name: str, radius: float) -> Path:
        def build(document, modelspace) -> None:
            plate(document, modelspace)
            modelspace.add_circle((5, 5), radius, dxfattribs={"layer": "CUT"})

        return write_drawing(self.base / name, build)

    def answer(self, path: Path) -> bytes:
        status, body = self.renders.response(str(path))
        self.assertEqual(status, 200, body)
        return body

    def test_the_same_bytes_anywhere_are_answered_from_memory_and_new_bytes_are_drawn(self) -> None:
        first = self.drawing("plate.dxf", 1)
        body = self.answer(first)
        self.assertEqual(json.loads(body)["schemaVersion"], DRAWING_PAYLOAD_SCHEMA_VERSION)
        os.utime(first, ns=(time.time_ns(), time.time_ns()))  # touched: the same bytes
        copy = self.base / "copy.dxf"
        copy.write_bytes(first.read_bytes())
        self.assertEqual((self.answer(first), self.answer(copy)), (body, body))
        self.assertEqual(self.rendered, ["plate.dxf"])
        self.drawing("plate.dxf", 2)  # rewritten: other bytes, drawn again
        self.assertNotEqual(self.answer(first), body)
        self.assertEqual(self.rendered, ["plate.dxf", "plate.dxf"])
        self.assertEqual(sorted(path.name for path in self.base.iterdir()), ["copy.dxf", "plate.dxf"],
                         "the route writes nothing beside the drawings")

    def test_it_holds_the_last_answers_asked_for(self) -> None:
        paths = [self.drawing(f"d{index}.dxf", 1 + index) for index in range(HELD + 1)]
        for path in paths[:HELD]:
            self.answer(path)
        self.answer(paths[0])  # asked for again: the most recent now
        self.answer(paths[HELD])  # one more: the least recently asked for, d1, goes
        self.rendered.clear()
        self.answer(paths[0])
        self.answer(paths[HELD])
        self.assertEqual(self.rendered, [])
        self.answer(paths[1])
        self.assertEqual(self.rendered, ["d1.dxf"])


class ItStaysOffTheKernel(DrawingRouteTestCase):
    def test_serving_a_drawing_does_not_load_the_cad_kernel(self) -> None:
        import sys

        self.fixture.drawing(self.fixture.path("plate.dxf"))
        self.assertEqual(
            [name for name in ("OCP", "build123d", "cadquery") if name in sys.modules],
            [],
            "the drawing route must not wake the kernel",
        )


if __name__ == "__main__":
    unittest.main()
