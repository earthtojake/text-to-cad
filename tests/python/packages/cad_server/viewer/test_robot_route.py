"""A robot document (``/api/v1/documents/<urdf|srdf|sdf>/<id>/...``) against a real launched server.

The fixture writes its own descriptions into a fresh temporary folder; nothing here reads the
sample corpus. A description is opened by its absolute path, as every file is: its ``structure``
answers the payload with every mesh by a URL this server serves, and its ``parts/<digest>`` each
primitive's GLB; every refusal asserts the status and the sentence.
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
from urllib.parse import parse_qs, urlparse

from cad_server.viewer import handler as handler_module
from cad_server.viewer.http_app import create_cad_app

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
        shutil.rmtree(self.base, ignore_errors=True)

    def request(self, target: str):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            conn.request("GET", target)
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def open(self, file_param):
        """``POST /api/v1/documents``: ``(status, answer)``."""
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            conn.request("POST", "/api/v1/documents", body=json.dumps({"path": str(file_param)}).encode(),
                         headers={"x-cad-viewer": "1"})
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def robot(self, file_param, mesh=None):
        """The description opened, then its structure, or one primitive's mesh."""
        status, opened = self.open(file_param)
        assert status == 201, opened
        return self.request(f"{opened['api']}/structure" if mesh is None else f"{opened['api']}/parts/{mesh}")


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
        # The primitive: the document's part, by hash. The file: the files route, versioned.
        self.assertEqual(box["mesh"]["format"], "glb")
        api = self.fixture.open(self.fixture.path("arm.urdf"))[1]["api"]
        self.assertTrue(api.startswith("/api/v1/documents/urdf/"), api)
        parsed = urlparse(box["mesh"]["url"])
        self.assertEqual(parsed.path.rsplit("/", 1)[0], f"{api}/parts")
        digest = parsed.path.rsplit("/", 1)[1]
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        self.assertEqual(head["mesh"]["format"], "stl")
        head_url = urlparse(head["mesh"]["url"])
        self.assertEqual(head_url.path, "/api/v1/local/files")
        self.assertEqual(parse_qs(head_url.query)["path"], [self.fixture.path(os.path.join("meshes", "head.stl"))])
        self.assertTrue(parse_qs(head_url.query)["v"][0])
        self.assertNotIn("path", head["mesh"], "the page gets URLs, not the host's paths")

        status, headers, mesh = self.fixture.robot(self.fixture.path("arm.urdf"), mesh=digest)
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "model/gltf-binary")
        self.assertEqual(mesh[:4], b"glTF")
        # The files route serves the link mesh the payload named.
        status, _headers, stl = self.fixture.request(head["mesh"]["url"])
        self.assertEqual((status, stl), (200, b"solid head\nendsolid head\n"))

    def test_a_mesh_the_payload_does_not_name_is_not_served(self) -> None:
        status, _headers, body = self.fixture.robot(self.fixture.path("arm.urdf"), mesh="0" * 64)
        self.assertEqual((status, json.loads(body)["error"]), (404, f"the robot names no mesh {'0' * 64}"))
        status, _headers, body = self.fixture.robot(self.fixture.path("arm.urdf"), mesh="not-a-hash")
        self.assertEqual(status, 400)
        self.assertIn("by its digest", json.loads(body)["error"])

    def test_a_primitive_the_process_let_go_of_is_meshed_again(self) -> None:
        from cad_server import robot_payload

        payload = json.loads(self.fixture.robot(self.fixture.path("arm.urdf"))[2])
        digest = urlparse(payload["visuals"][0]["mesh"]["url"]).path.rsplit("/", 1)[1]
        with robot_payload._LOCK:
            robot_payload._MESHES.pop(digest)
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
        for ref, expected in (("", "absolute path"), ("arm.urdf", "not an absolute path")):
            with self.subTest(ref=ref):
                status, answer = self.fixture.open(ref)
                self.assertEqual(status, 400, answer)
                self.assertIn(expected, answer["error"])
        # A mesh is no robot: its id under a robot's kind is a 404 naming its own.
        Path(self.fixture.path("part.stl")).write_bytes(b"solid p\nendsolid p\n")
        status, mesh = self.fixture.open(self.fixture.path("part.stl"))
        self.assertEqual(status, 201, mesh)
        status, _headers, body = self.fixture.request(f"/api/v1/documents/urdf/{mesh['id']}/structure")
        self.assertEqual((status, json.loads(body)["error"]), (404, f"{mesh['id']} is a stl"))
        status, answer = self.fixture.open(self.fixture.path("absent.urdf"))
        self.assertEqual((status, answer["error"]), (404, f"no CAD file at {self.fixture.path('absent.urdf')}"))


if __name__ == "__main__":
    unittest.main()
