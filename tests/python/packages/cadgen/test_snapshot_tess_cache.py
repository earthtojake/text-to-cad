"""The snapshot host's side of the shared component-tessellation cache.

The page and the export CLI share the immutable object/index store. Payloads
are TESS v4 with exact input, surface and quality identity. Probes return small
metadata before admitted body reads, and batch responses have a fixed byte cap.
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
from tests.python.support.tessellation import tessellation_fixture
from tests.python.support.tmp_root import generated_cad_directory

FIXTURE = tessellation_fixture()
PAYLOAD = base64.b64decode(FIXTURE["bytes"])
NAME = FIXTURE["key"] + ".tess"
ADMITTED = {"tessellationInput": FIXTURE["key"], "object": FIXTURE["facts"]["object"], "maxBytes": len(PAYLOAD)}
ADMISSION_QUERY = f"?object={ADMITTED['object']}&maxBytes={ADMITTED['maxBytes']}"

from cadgen.snapshot_core import (  # noqa: E402
    TESS_CACHE_BATCH_MAGIC,
    BatchSnapshotRenderer,
    SnapshotError,
    TESS_CACHE_BATCH_PATH,
    TESS_CACHE_BATCH_VERSION,
    TESS_CACHE_ROUTE_PREFIX,
    SnapshotAssetServer,
    _write_http_body,
    read_tessellation_cache_batch,
    read_tessellation_cache_entry,
    write_tessellation_cache_entry,
)
from cadgen.assets import browser_runtime_dir  # noqa: E402


class AssetServerIsMandatoryTest(unittest.TestCase):
    """The loopback server is the only transport for bulk mesh bytes.

    The old behaviour was a silent fallback to Playwright's route, which hands
    an intercepted request's body to the driver as escaped text in one protocol
    message — that killed the renderer on real assemblies and reported it as a
    lost driver connection. A snapshot that cannot bind a local socket has to
    say so.
    """

    def test_start_fails_loudly_when_the_loopback_server_cannot_bind(self):
        renderer = BatchSnapshotRenderer(Path("."))
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

    def test_tess_cache_round_trip_and_preflight(self) -> None:
        name = NAME
        status, _, _ = self.request("GET", f"{TESS_CACHE_ROUTE_PREFIX}{name}{ADMISSION_QUERY}")
        self.assertEqual(status, 404)
        status, _, _ = self.request("POST", f"{TESS_CACHE_ROUTE_PREFIX}{name}", PAYLOAD)
        self.assertEqual(status, 204)
        status, body, _ = self.request("GET", f"{TESS_CACHE_ROUTE_PREFIX}{name}{ADMISSION_QUERY}")
        self.assertEqual((status, body), (200, PAYLOAD))
        status, _, _ = self.request("POST", f"{TESS_CACHE_ROUTE_PREFIX}%2e%2e/escape.tess", b"x")
        self.assertEqual(status, 403)
        status, _, headers = self.request("OPTIONS", f"{TESS_CACHE_ROUTE_PREFIX}{name}")
        self.assertEqual(status, 204)
        self.assertIn("POST", headers.get("access-control-allow-methods", ""))

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
        from cadgen.viewer.tess_cache import TESS_CACHE_METADATA_MAX_BYTES

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

        name = NAME
        status, _, _ = self.request("POST", f"{TESS_CACHE_ROUTE_PREFIX}{name}", PAYLOAD)
        self.assertEqual(status, 204)
        body = json.dumps({"entries": [ADMITTED, {**ADMITTED, "object": "f" * 64}]}).encode()
        status, response, _ = self.request("POST", TESS_CACHE_BATCH_PATH, body)
        self.assertEqual(status, 200)
        self.assertEqual(decode_batch(response), [PAYLOAD, None])
        status, _, _ = self.request("POST", TESS_CACHE_BATCH_PATH, b"not json")
        self.assertEqual(status, 400)


class SnapshotBrowserTessCacheIntegrationTest(unittest.TestCase):
    """The real snapshot page must adopt what its real HTTP provider writes."""

    def test_cold_surface_write_is_a_warm_hit_after_the_surface_is_gone(self) -> None:
        repo = Path(__file__).resolve().parents[4]
        surface_bytes = (
            repo / "packages/cadgen-js/src/lib/surf/fixtures/cam_follower_roller.surf"
        ).read_bytes()

        async def exercise(root: Path) -> None:
            asset_root = root / "assets"
            asset_root.mkdir()
            surface_path = asset_root / "roller.surf"
            surface_path.write_bytes(surface_bytes)
            surface_input = "d" * 64
            surface_object = hashlib.sha256(surface_bytes).hexdigest()
            descriptor = {
                "kind": "assembly-package",
                "components": {"roller": {
                    "surfaceInput": surface_input,
                    "surfaceObject": surface_object,
                }},
                "occurrences": [{
                    "id": "o1.1", "name": "roller", "component": "roller",
                    "transform": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
                }],
                "assembly": {"root": {
                    "id": "o1", "name": "fixture", "nodeType": "assembly",
                    "children": [{
                        "id": "o1.1", "name": "roller", "nodeType": "part", "children": [],
                    }],
                }},
            }
            job = {
                "kind": "step",
                "resolved": {
                    "kind": "step",
                    "rootPath": str(asset_root),
                    "package": {
                        "descriptor": descriptor,
                        "componentUrls": {"roller": "/__render_asset/roller.surf"},
                    },
                },
                "outputs": [{
                    "path": str(root / "out.png"), "width": 64, "height": 64, "camera": "iso",
                }],
            }
            renderer = BatchSnapshotRenderer(browser_runtime_dir(None))
            try:
                cold = await renderer.render(job)
                self.assertTrue(cold["ok"])
                self.assertEqual(
                    {"secure": True, "subtle": True},
                    await renderer.page.evaluate(
                        "({secure: isSecureContext, subtle: !!globalThis.crypto?.subtle})"
                    ),
                )
                mesh_entries = list((root / "cache/index/mesh").iterdir())
                self.assertEqual(len(mesh_entries), 1)
                cached_index = mesh_entries[0].read_bytes()

                # A warm success now proves the browser read the exact persisted
                # TESS body: the only SURF URL the fallback could use is gone.
                surface_path.unlink()
                warm = await renderer.render(job)
                self.assertTrue(warm["ok"])
                self.assertEqual(mesh_entries[0].read_bytes(), cached_index)
            finally:
                await renderer.close()

        with generated_cad_directory(prefix="snapshot-browser-cache-") as temporary:
            root = Path(temporary).resolve()
            with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(root / "cache")}):
                asyncio.run(exercise(root))


if __name__ == "__main__":
    unittest.main()
