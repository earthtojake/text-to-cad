"""``GET /__cad/drawing`` against a real launched server.

The fixture writes its own drawings with ezdxf into a fresh temporary root and
points the store at a temporary directory; nothing here reads the sample
corpus and nothing shares a store with another test file.

The denial cases matter most. ``/__cad/drawing`` is a route that turns a
``?file=`` ref into a path the server OPENS, and the store has a read-outside-
root hole in its history of exactly that shape, so every refusal asserts both
the status and that the secret bytes never appear in the body.
"""

from __future__ import annotations

import http.client
import json
import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import quote

import ezdxf

from cadgen.viewer import handler as handler_module
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
    """``base/{root, root-evil, outside}`` behind a live server, plus a store."""

    def __init__(self) -> None:
        self.base = tempfile.mkdtemp()
        self.root = os.path.join(self.base, "root")
        self.evil = os.path.join(self.base, "root-evil")
        self.outside = os.path.join(self.base, "outside")
        for directory in (self.root, self.evil, self.outside):
            os.makedirs(directory)
        self._previous_cache = os.environ.get("CADGEN_CACHE_DIR")
        os.environ["CADGEN_CACHE_DIR"] = os.path.join(self.base, "cache")

        write_drawing(Path(self.root, "plate.dxf"), plate)
        write_drawing(Path(self.root, "nested", "bracket.dxf"), plate)
        write_drawing(Path(self.root, ".hidden", "private.dxf"), plate)
        # A name-prefix sibling of the root: the jupyter_server
        # GHSA-5789-5fc7-67v3 shape, which a naive startswith() lets through.
        write_drawing(Path(self.evil, "stolen.dxf"), plate)
        write_drawing(Path(self.outside, "secret.dxf"), plate)
        # Deliberately secret-free: ezdxf names the offending LINE in its
        # parse error, and that line rides out in the 400's message. That is
        # the teaching part of the error, and the file is one the asset route
        # would have served whole anyway — but a probe file with a secret in
        # it would make this test pass or fail for the wrong reason.
        Path(self.root, "notes.dxf").write_text("this is not a drawing\n", encoding="utf-8")
        Path(self.root, "part.step").write_text(f"ISO-10303-21; {SECRET}\n", encoding="utf-8")
        Path(self.outside, "passwd").write_text(SECRET, encoding="utf-8")

        self.app = create_cad_app(root=self.root, host="127.0.0.1", port=0, dist_dir="")
        self.server = handler_module.serve(self.app, "127.0.0.1", 0)
        self.port = self.server.server_address[1]
        self.app.port = self.port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        if self._previous_cache is None:
            os.environ.pop("CADGEN_CACHE_DIR", None)
        else:
            os.environ["CADGEN_CACHE_DIR"] = self._previous_cache
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
        return self.request(f"/__cad/drawing?file={quote(str(file_param), safe='')}")


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
    def test_an_absolute_ref_inside_the_root_serves_the_payload(self) -> None:
        status, headers, body = self.fixture.drawing(os.path.join(self.fixture.root, "plate.dxf"))
        self.assertEqual(status, 200, body[:400])
        self.assertEqual(headers["content-type"], "application/json; charset=utf-8")
        self.assertEqual(headers["cache-control"], "no-store")
        # The viewer serves bytes to render, never a save-as.
        self.assertNotIn("content-disposition", {name.lower() for name in headers})
        payload = json.loads(body)
        self.assertEqual(payload["schemaVersion"], 1)
        self.assertEqual(payload["units"]["insunits"], 4)
        self.assertEqual(len(payload["bounds"]), 4)
        self.assertTrue(payload["primitives"])
        self.assertIn("CUT", {layer["name"] for layer in payload["layers"]})

    def test_a_root_relative_ref_serves_the_same_payload(self) -> None:
        absolute = self.fixture.drawing(os.path.join(self.fixture.root, "plate.dxf"))
        relative = self.fixture.drawing("plate.dxf")
        self.assertEqual(relative[0], 200, relative[2][:400])
        self.assertEqual(relative[2], absolute[2])

    def test_a_nested_drawing_serves(self) -> None:
        status, _, body = self.fixture.drawing("nested/bracket.dxf")
        self.assertEqual(status, 200, body[:400])
        self.assertTrue(json.loads(body)["primitives"])

    def test_the_body_is_the_compact_encoding_and_the_content_length_matches(self) -> None:
        status, headers, body = self.fixture.drawing("plate.dxf")
        self.assertEqual(status, 200)
        self.assertEqual(int(headers["content-length"]), len(body))
        self.assertNotIn(b", ", body)
        # No gzip: the backend has no compression helper and this route did not
        # invent one. If a helper ever arrives, this is the line to revisit.
        self.assertNotIn("content-encoding", {name.lower() for name in headers})

    def test_two_requests_return_identical_bytes(self) -> None:
        first = self.fixture.drawing("plate.dxf")[2]
        second = self.fixture.drawing("plate.dxf")[2]
        self.assertEqual(first, second)


class ItRefusesWhatItShould(DrawingRouteTestCase):
    def test_a_dot_dot_walk_out_of_the_root_is_forbidden(self) -> None:
        for ref in (
            "../outside/secret.dxf",
            "nested/../../outside/secret.dxf",
            "..%2Foutside%2Fsecret.dxf",
            "....//outside/secret.dxf",
        ):
            with self.subTest(ref=ref):
                status, _, body = self.fixture.drawing(ref)
                self.assertDenied(status, body, {403, 404})
                self.assertNotIn(b'"primitives"', body)

    def test_an_absolute_path_outside_the_root_is_forbidden(self) -> None:
        for path in (
            os.path.join(self.fixture.outside, "secret.dxf"),
            os.path.join(self.fixture.evil, "stolen.dxf"),
        ):
            with self.subTest(path=path):
                status, _, body = self.fixture.drawing(path)
                self.assertEqual(status, 403, body[:400])
                self.assertNotIn(b'"primitives"', body)

    def test_a_hidden_component_is_a_miss_not_a_drawing(self) -> None:
        status, _, body = self.fixture.drawing(".hidden/private.dxf")
        self.assertEqual(status, 404, body[:400])
        self.assertNotIn(b'"primitives"', body)

    def test_another_extension_is_a_400_that_says_what_the_route_takes(self) -> None:
        for ref in ("part.step", os.path.join(self.fixture.outside, "passwd")):
            with self.subTest(ref=ref):
                status, _, body = self.fixture.drawing(ref)
                self.assertDenied(status, body, {400})
                self.assertIn(b".dxf", body)

    def test_no_file_parameter_says_what_to_send(self) -> None:
        status, _, body = self.fixture.request("/__cad/drawing")
        self.assertEqual(status, 400, body[:400])
        self.assertIn(b"?file=", body)

    def test_a_missing_drawing_is_a_404(self) -> None:
        status, _, body = self.fixture.drawing("absent.dxf")
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(body), {"error": "Not found"})

    def test_a_dxf_that_is_not_a_dxf_is_a_400_carrying_the_reason(self) -> None:
        status, _, body = self.fixture.drawing("notes.dxf")
        self.assertDenied(status, body, {400})
        message = json.loads(body)["error"]
        self.assertIn("notes.dxf", message)
        self.assertIn("audit", message, "the error must say what to do about it")

    def test_a_null_byte_in_the_ref_is_refused(self) -> None:
        status, _, body = self.fixture.drawing("plate\x00.dxf")
        self.assertDenied(status, body, {400})

    def test_the_route_is_get_only(self) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", self.fixture.port, timeout=10)
        try:
            conn.request("POST", "/__cad/drawing?file=plate.dxf", headers={"x-cadgen-viewer": "1"})
            response = conn.getresponse()
            body = response.read()
        finally:
            conn.close()
        self.assertEqual(response.status, 405)
        self.assertNotIn(b'"primitives"', body)


class ItStaysOffTheKernelAndTheReloadCounter(DrawingRouteTestCase):
    def test_the_route_is_counted_by_the_development_reload_gate(self) -> None:
        """Not an uncounted poll: a render is work a restart would throw away.

        ``_UNCOUNTED_ROUTES`` exists for the watcher's own poll and for routes
        that PARK; this one burns CPU, like a compile, and a restart mid-render
        wastes it.
        """
        from cadgen.viewer.http_app import _UNCOUNTED_ROUTES

        self.assertNotIn("/__cad/drawing", _UNCOUNTED_ROUTES)

    def test_serving_a_drawing_does_not_load_the_cad_kernel(self) -> None:
        import sys

        self.fixture.drawing("plate.dxf")
        self.assertEqual(
            [name for name in ("OCP", "build123d", "cadquery") if name in sys.modules],
            [],
            "the drawing route must not wake the kernel",
        )


if __name__ == "__main__":
    unittest.main()
