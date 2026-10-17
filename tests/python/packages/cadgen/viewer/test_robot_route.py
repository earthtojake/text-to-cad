"""``GET /__cad/robot`` against a real launched server.

The fixture writes its own descriptions into a fresh temporary folder and points the store
at a temporary directory; nothing here reads the sample corpus and nothing shares a store with
another test file. A description is named by its absolute path, as every file is: the route
answers the payload with every mesh by a URL this server serves, and each primitive's GLB by
its hash; every refusal asserts the status and the sentence.
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
from urllib.parse import parse_qs, quote, urlparse

from cadgen.viewer import handler as handler_module
from cadgen.viewer.http_app import create_cad_app

ARM_URDF = """<?xml version="1.0"?>
<robot name="arm">
  <link name="base"><visual><geometry><box size="0.4 0.4 0.1"/></geometry></visual></link>
  <link name="head"><visual><geometry><mesh filename="meshes/head.stl"/></geometry></visual></link>
  <joint name="nod" type="revolute"><parent link="base"/><child link="head"/><origin xyz="0 0 0.2"/><axis xyz="0 1 0"/>
    <limit lower="-1" upper="1" effort="1" velocity="1"/></joint>
</robot>
"""


class RobotRouteFixture:
    def __init__(self) -> None:
        # Resolved: the payload names meshes by their resolved paths, which on macOS is
        # /private/var where mkdtemp said /var.
        self.base = os.path.realpath(tempfile.mkdtemp())
        self.root = os.path.join(self.base, "project")
        os.makedirs(os.path.join(self.root, "meshes"))
        self._previous_cache = os.environ.get("CADGEN_CACHE_DIR")
        os.environ["CADGEN_CACHE_DIR"] = os.path.join(self.base, "cache")
        Path(self.root, "arm.urdf").write_text(ARM_URDF, encoding="utf-8")
        Path(self.root, "meshes", "head.stl").write_bytes(b"solid head\nendsolid head\n")
        Path(self.root, "lonely.srdf").write_text("<robot name='nobody'><group name='g'><link name='l'/></group></robot>", encoding="utf-8")
        Path(self.root, "notes.urdf").write_text("this is not a robot\n", encoding="utf-8")
        Path(self.root, "part.step").write_text("ISO-10303-21;\n", encoding="utf-8")

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

    def robot(self, file_param, mesh=None):
        query = f"/__cad/robot?file={quote(str(file_param), safe='')}"
        return self.request(query + (f"&mesh={mesh}" if mesh else ""))


class RobotRouteTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = RobotRouteFixture()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fixture.close()


class ItServesTheRobot(RobotRouteTestCase):
    def test_the_payload_names_every_mesh_by_a_url_this_server_answers(self) -> None:
        status, headers, body = self.fixture.robot(self.fixture.path("arm.urdf"))
        self.assertEqual(status, 200, body[:400])
        self.assertEqual(headers["content-type"], "application/json; charset=utf-8")
        payload = json.loads(body)
        self.assertEqual([control["id"] for control in payload["articulation"]["controls"]], ["nod"])
        box, head = payload["visuals"]
        # The primitive: this route, by hash. The file: the asset route, versioned.
        self.assertEqual(box["mesh"]["format"], "glb")
        parsed = urlparse(box["mesh"]["url"])
        self.assertEqual(parsed.path, "/__cad/robot")
        self.assertEqual(parse_qs(parsed.query)["file"], [self.fixture.path("arm.urdf")])
        digest = parse_qs(parsed.query)["mesh"][0]
        self.assertEqual(head["mesh"]["format"], "stl")
        head_url = urlparse(head["mesh"]["url"])
        self.assertEqual(head_url.path, "/__cad/asset")
        self.assertEqual(parse_qs(head_url.query)["file"], [self.fixture.path(os.path.join("meshes", "head.stl"))])
        self.assertTrue(parse_qs(head_url.query)["v"][0])
        self.assertNotIn("path", head["mesh"], "the page gets URLs, not the host's paths")

        status, headers, mesh = self.fixture.robot(self.fixture.path("arm.urdf"), mesh=digest)
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "model/gltf-binary")
        self.assertEqual(mesh[:4], b"glTF")
        # The asset route serves the link mesh the payload named.
        status, _headers, stl = self.fixture.request(head["mesh"]["url"])
        self.assertEqual((status, stl), (200, b"solid head\nendsolid head\n"))

    def test_a_mesh_the_payload_does_not_name_is_not_served(self) -> None:
        status, _headers, body = self.fixture.robot(self.fixture.path("arm.urdf"), mesh="0" * 64)
        self.assertEqual((status, json.loads(body)), (404, {"error": "Not found"}))
        status, _headers, body = self.fixture.robot(self.fixture.path("arm.urdf"), mesh="not-a-hash")
        self.assertEqual(status, 400)
        self.assertIn("by its object hash", json.loads(body)["error"])

    def test_a_swept_primitive_is_meshed_again(self) -> None:
        from cadgen.store.objects import object_path

        payload = json.loads(self.fixture.robot(self.fixture.path("arm.urdf"))[2])
        digest = parse_qs(urlparse(payload["visuals"][0]["mesh"]["url"]).query)["mesh"][0]
        os.remove(object_path(digest))
        status, _headers, mesh = self.fixture.robot(self.fixture.path("arm.urdf"), mesh=digest)
        self.assertEqual((status, mesh[:4]), (200, b"glTF"))


class ItRefuses(RobotRouteTestCase):
    def test_what_cadgen_cannot_resolve_is_a_400_with_the_sentence(self) -> None:
        status, _headers, body = self.fixture.robot(self.fixture.path("lonely.srdf"))
        self.assertEqual(status, 400)
        self.assertIn("lonely.srdf has no paired URDF", json.loads(body)["error"])
        status, _headers, body = self.fixture.robot(self.fixture.path("notes.urdf"))
        self.assertEqual(status, 400)
        self.assertIn("could not be parsed as URDF XML", json.loads(body)["error"])

    def test_a_ref_this_route_will_not_take(self) -> None:
        for ref, expected in (("", "needs ?file="), ("arm.urdf", "not an absolute path"), (self.fixture.path("part.step"), "part.step is not a")):
            with self.subTest(ref=ref):
                status, _headers, body = self.fixture.robot(ref)
                self.assertEqual(status, 400, body[:200])
                self.assertIn(expected, json.loads(body)["error"])
        status, _headers, body = self.fixture.robot(self.fixture.path("absent.urdf"))
        self.assertEqual((status, json.loads(body)), (404, {"error": "Not found"}))


if __name__ == "__main__":
    unittest.main()
