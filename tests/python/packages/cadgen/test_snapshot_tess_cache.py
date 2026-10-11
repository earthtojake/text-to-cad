"""The snapshot host's side of the store's component meshes.

The page draws the meshes cadgen stores, the ones the viewer and mesh exports
use: GLB bodies with exact input, surface and quality identity. Probes return small
metadata before admitted body reads, batch responses have a fixed byte cap, and
the host meshes on request what a probe found missing; the page never writes.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")
from tests.python.support.inline_artifacts import inline_artifacts
from tests.python.support.tessellation import tessellation_fixture
from tests.python.support.tmp_root import generated_cad_directory

FIXTURE = tessellation_fixture()
PAYLOAD = base64.b64decode(FIXTURE["bytes"])
NAME = FIXTURE["key"] + ".glb"
ADMITTED = {"tessellationInput": FIXTURE["key"], "object": FIXTURE["facts"]["object"], "maxBytes": len(PAYLOAD)}
ADMISSION_QUERY = f"?object={ADMITTED['object']}&maxBytes={ADMITTED['maxBytes']}"

from cadgen.tessellation_policy import snapshot_tessellation  # noqa: E402
from cadgen.snapshot_core import (  # noqa: E402
    BatchSnapshotRenderer,
    SnapshotError,
    TESS_CACHE_BATCH_PATH,
    TESS_CACHE_ROUTE_PREFIX,
    SnapshotAssetServer,
    _write_http_body,
    read_tessellation_cache_batch,
    read_tessellation_cache_entry,
)
from cadgen.store import meshes  # noqa: E402
from cadgen.assets import browser_runtime_dir  # noqa: E402
# The TESB framing is the store's; the snapshot host only routes to it.
from cadgen.store.tess_cache import TESS_CACHE_BATCH_MAGIC, TESS_CACHE_BATCH_VERSION  # noqa: E402


class AssetServerIsMandatoryTest(unittest.TestCase):
    """The loopback server is the only transport for bulk mesh bytes.

    The old behaviour was a silent fallback to Playwright's route, which hands
    an intercepted request's body to the driver as escaped text in one protocol
    message — that killed the renderer on real assemblies and reported it as a
    lost driver connection. A snapshot that cannot bind a local socket has to
    say so.
    """

    def test_start_fails_loudly_when_the_loopback_server_cannot_bind(self):
        # The real bundled runtime, not a placeholder path: start() validates the browser
        # bundle before it binds anything, so a made-up directory would fail on the wrong
        # precondition and never reach the socket this test is about.
        renderer = BatchSnapshotRenderer(browser_runtime_dir())
        with mock.patch(
            "cadgen.snapshot_core.SnapshotAssetServer",
            side_effect=OSError("Address family not supported"),
        ):
            with self.assertRaises(SnapshotError) as caught:
                asyncio.run(renderer.start())
        message = str(caught.exception)
        self.assertIn("loopback HTTP server", message)
        self.assertIn("Address family not supported", message)
        self.assertFalse(renderer.started)
        self.assertIsNone(renderer.asset_server)


class LargeHttpBodyTest(unittest.TestCase):
    def test_response_writes_are_bounded_views_of_the_original_body(self):
        body = b"x" * (16 * 1024 * 1024 + 3)
        chunks = []

        class BoundedSocket:
            def write(self, chunk):
                self_outer.assertLessEqual(len(chunk), 16 * 1024 * 1024)
                self_outer.assertIs(chunk.obj, body)
                chunks.append(chunk)

        self_outer = self
        _write_http_body(BoundedSocket(), body)
        self.assertEqual([len(chunk) for chunk in chunks], [16 * 1024 * 1024, 3])
        self.assertEqual(b"".join(chunks), body)


def decode_batch(body: bytes) -> list[bytes | None]:
    """Reference decoder for the TESB container (the JS codec is authoritative;
    this mirrors it so the Python framing is pinned from both sides)."""
    import struct

    magic, version, count = struct.unpack_from("<III", body, 0)
    assert magic == TESS_CACHE_BATCH_MAGIC and version == TESS_CACHE_BATCH_VERSION
    entries: list[bytes | None] = []
    offset = 12
    for _ in range(count):
        (length,) = struct.unpack_from("<I", body, offset)
        offset += 4
        if length == 0:
            entries.append(None)
            continue
        entries.append(body[offset:offset + length])
        offset += length + ((-length) % 4)
    return entries


class SnapshotAssetServerTests(unittest.TestCase):
    """The loopback bulk-bytes server: same containment as the CDP route,
    CORS for the intercepted page origin, and the tess-cache round trip."""

    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory(prefix="asset-server-")
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name).resolve()
        # Same sandbox as TessellationCacheRouteTests above: this suite round
        # trips the tess cache, so the Windows home spellings and LOCALAPPDATA
        # have to be redirected too or the writes land in the real user cache.
        drive, tail = os.path.splitdrive(str(self.home))
        patcher = mock.patch.dict(
            os.environ,
            {
                "HOME": str(self.home),
                "USERPROFILE": str(self.home),
                "HOMEDRIVE": drive,
                "HOMEPATH": tail,
                "CADGEN_CACHE_DIR": "",
                "XDG_CACHE_HOME": "",
                "LOCALAPPDATA": "",
            },
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.root = self.home / "modelroot"
        self.root.mkdir()
        (self.root / "inside.step").write_bytes(b"ISO-10303-21;")
        (self.home / "outside.secret").write_bytes(b"nope")
        self.active_root: Path | None = self.root
        self.server = SnapshotAssetServer(lambda: self.active_root)
        self.addCleanup(self.server.close)

    def request(self, method: str, path: str, body: bytes | None = None):
        import urllib.error
        import urllib.request

        req = urllib.request.Request(f"{self.server.base_url}{path}", data=body, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status, response.read(), dict(response.headers)
        except urllib.error.HTTPError as error:
            return error.code, error.read(), dict(error.headers)

    def test_the_bind_never_names_the_host_by_reverse_dns(self) -> None:
        # http.server's own bind calls socket.getfqdn, which waits 35 s on a Mac
        # whose resolver does not answer: every snapshot waited on it.
        with mock.patch("socket.getfqdn", side_effect=AssertionError("a reverse DNS lookup at bind")):
            server = SnapshotAssetServer(lambda: None)
        server.close()

    def test_render_asset_containment(self) -> None:
        status, body, headers = self.request("GET", "/__render_asset/inside.step")
        self.assertEqual((status, body), (200, b"ISO-10303-21;"))
        self.assertEqual(headers.get("access-control-allow-origin"), "*")
        self.assertEqual(headers.get("cache-control"), "no-store")
        status, _, _ = self.request("GET", "/__render_asset/%2e%2e/outside.secret")
        self.assertIn(status, (403, 404), "traversal must never serve bytes")
        self.active_root = None
        status, _, _ = self.request("GET", "/__render_asset/inside.step")
        self.assertEqual(status, 404)

    def test_tess_cache_reads_and_preflight_and_no_writes(self) -> None:
        name = NAME
        status, _, _ = self.request("GET", f"{TESS_CACHE_ROUTE_PREFIX}{name}{ADMISSION_QUERY}")
        self.assertEqual(status, 404)
        status, _, _ = self.request("POST", f"{TESS_CACHE_ROUTE_PREFIX}{name}", PAYLOAD)
        self.assertEqual(status, 405, "the page never writes a mesh")
        self.assertIsNone(meshes.probe(FIXTURE["key"]))
        meshes.write(FIXTURE["key"], PAYLOAD)
        status, body, _ = self.request("GET", f"{TESS_CACHE_ROUTE_PREFIX}{name}{ADMISSION_QUERY}")
        self.assertEqual((status, body), (200, PAYLOAD))
        status, _, headers = self.request("OPTIONS", f"{TESS_CACHE_ROUTE_PREFIX}{name}")
        self.assertEqual(status, 204)
        self.assertIn("POST", headers.get("access-control-allow-methods", ""))

    def test_produce_route_meshes_a_derived_surface_and_reports_why_it_cannot(self) -> None:
        import json

        from build123d import Box
        from cadgen.store import surfaces
        from cadgen.store.build import build_tree_from_compound

        tree, descriptor, _ = build_tree_from_compound(Box(4, 5, 6), root_name="block")
        producer = surfaces.producer_identity()
        surfaces.derive(tree, producer=producer)
        [entry] = descriptor["components"].values()
        key = meshes.tessellation_key(surfaces.surface_input(entry, producer))
        produce = json.dumps({"tessellationInputs": [key]}).encode()
        with inline_artifacts():
            with mock.patch("cadgen.store.surfaces.produce_meshes", side_effect=ValueError("OCCT did not mesh 1 face(s)")):
                status, body, _ = self.request("POST", "/__tess_cache/produce", produce)
            self.assertEqual(status, 500)
            self.assertIn(b"OCCT did not mesh 1 face(s)", body)
            status, body, _ = self.request("POST", "/__tess_cache/produce", produce)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["entries"], {key: meshes.probe(key)})
        status, _, _ = self.request("POST", "/__tess_cache/produce", b"not json")
        self.assertEqual(status, 400)

    def test_unadmitted_reads_never_reach_the_cache(self) -> None:
        from urllib.parse import urlencode

        for digest, limit in ((None, None), (ADMITTED["object"], None), (None, "1"),
                              (ADMITTED["object"].upper(), "1"), (" " + ADMITTED["object"], "1"),
                              (ADMITTED["object"], "0"), (ADMITTED["object"], "-1"),
                              (ADMITTED["object"], "9007199254740992")):
            query = urlencode({key: value for key, value in (("object", digest), ("maxBytes", limit)) if value is not None})
            with self.subTest(digest=digest, limit=limit), mock.patch(
                "cadgen.snapshot_core.read_tessellation_cache_entry", side_effect=AssertionError("unadmitted cache read"),
            ):
                status, _, _ = self.request("GET", f"{TESS_CACHE_ROUTE_PREFIX}{NAME}?{query}")
            self.assertEqual(status, 400)

    def test_oversized_metadata_headers_are_rejected_without_reading_a_body(self) -> None:
        import http.client
        from cadgen.store.tess_cache import TESS_CACHE_METADATA_MAX_BYTES

        for path in ("/__tess_cache/probe", TESS_CACHE_BATCH_PATH):
            with self.subTest(path=path):
                connection = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=2)
                try:
                    connection.putrequest("POST", path)
                    connection.putheader("Content-Length", str(TESS_CACHE_METADATA_MAX_BYTES + 1))
                    connection.endheaders()
                    response = connection.getresponse()
                    self.assertEqual(response.status, 413)
                    response.read()
                    self.assertEqual(connection.sock.recv(1), b"", "unread metadata must close the connection")
                finally:
                    connection.close()

    def test_unknown_paths_404(self) -> None:
        for method, path in (("GET", "/anything"), ("POST", "/__render_asset/inside.step")):
            status, _, _ = self.request(method, path)
            self.assertEqual(status, 404, f"{method} {path}")

    def test_batch_route_round_trip(self) -> None:
        import json

        meshes.write(FIXTURE["key"], PAYLOAD)
        body = json.dumps({"entries": [ADMITTED, {**ADMITTED, "object": "f" * 64}]}).encode()
        status, response, _ = self.request("POST", TESS_CACHE_BATCH_PATH, body)
        self.assertEqual(status, 200)
        self.assertEqual(decode_batch(response), [PAYLOAD, None])
        status, _, _ = self.request("POST", TESS_CACHE_BATCH_PATH, b"not json")
        self.assertEqual(status, 400)


class SnapshotBrowserTessCacheIntegrationTest(unittest.TestCase):
    """The real snapshot page draws the meshes the build pool makes for its host."""

    def test_a_cold_render_has_the_build_pool_mesh_and_a_warm_one_reads_that_mesh(self) -> None:
        async def exercise(root: Path) -> None:
            from build123d import Box, Cylinder
            from cadgen.store import surfaces
            from cadgen.store.build import build_tree_from_compound

            tree, geometry, _ = build_tree_from_compound(Box(20, 20, 10) - Cylinder(4, 10), root_name="bored")
            producer = surfaces.producer_identity()
            [(cid, entry)] = geometry["components"].items()
            [record] = surfaces.derive(tree, producer=producer).values()
            asset_root = root / "assets"
            asset_root.mkdir()
            descriptor = {
                "kind": "assembly-package",
                "components": {cid: {"surfaceInput": record["surfaceInput"], "surfaceObject": record["object"]}},
                "occurrences": [{
                    "id": "o1.1", "name": "part", "component": cid,
                    "transform": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
                }],
                "assembly": {"root": {
                    "id": "o1", "name": "fixture", "nodeType": "assembly",
                    "children": [{
                        "id": "o1.1", "name": "part", "nodeType": "part", "children": [],
                    }],
                }},
            }
            job = {
                "kind": "step",
                "resolved": {
                    "kind": "step",
                    "rootPath": str(asset_root),
                    # The tolerances the page draws at are cadgen's, named in the job.
                    "tessellation": snapshot_tessellation({}),
                    "package": {
                        "descriptor": descriptor,
                        # Nothing serves a surf here: the page draws only the stored mesh.
                        "componentUrls": {cid: "/__render_asset/part.surf"},
                    },
                },
                "outputs": [{
                    "path": str(root / "out.png"), "width": 64, "height": 64, "camera": "iso",
                }],
            }
            mesh_index = root / "cache/index/mesh"
            self.assertFalse(mesh_index.exists(), "deriving the surface meshed nothing")
            renderer = BatchSnapshotRenderer(browser_runtime_dir(None))
            try:
                with mock.patch("cadgen.store.surfaces.produce_meshes",
                                side_effect=AssertionError("the host meshed in its own process")):
                    cold = await renderer.render(job)
                self.assertTrue(cold["ok"])
                self.assertEqual(
                    {"secure": True, "subtle": True},
                    await renderer.page.evaluate(
                        "({secure: isSecureContext, subtle: !!globalThis.crypto?.subtle})"
                    ),
                )
                mesh_entries = list(mesh_index.iterdir())
                self.assertEqual(len(mesh_entries), 1, "the build pool meshed the one component the page asked for")
                stored = mesh_entries[0].read_bytes()
                with mock.patch("cadgen.daemon.artifacts.submit_artifact",
                                side_effect=AssertionError("a stored mesh is asked for nothing")):
                    warm = await renderer.render(job)
                self.assertTrue(warm["ok"])
                self.assertEqual([path.read_bytes() for path in mesh_index.iterdir()], [stored])
            finally:
                await renderer.close()

        with generated_cad_directory(prefix="snapshot-browser-cache-") as temporary:
            root = Path(temporary).resolve()
            # A one-shot build-pool worker meshes for the page, as it does wherever no daemon runs.
            with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(root / "cache"), "CADGEN_DAEMON": "0"}):
                asyncio.run(exercise(root))


if __name__ == "__main__":
    unittest.main()
