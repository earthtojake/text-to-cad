"""The snapshot host's side of the shared component-tessellation cache.

The page and the export CLI share ONE on-disk store (~/.cache/cadgen/meshes;
codec in packages/cadgen-js/src/lib/surf/tessellationCache.js). Python never
decodes entries — it stores and serves opaque bytes — so what these tests pin
is the transport contract: name validation (the cache lives OUTSIDE any model
root, so a bad name must be refused, never resolved), the CADGEN_MESH_CACHE=0
bypass, atomic best-effort writes, and read-your-write round-trips.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.snapshot_core import (  # noqa: E402
    TESS_CACHE_BATCH_MAGIC,
    TESS_CACHE_BATCH_PATH,
    TESS_CACHE_BATCH_VERSION,
    TESS_CACHE_ROUTE_PREFIX,
    SnapshotAssetServer,
    _write_http_body,
    read_tessellation_cache_batch,
    read_tessellation_cache_entry,
    write_tessellation_cache_entry,
)


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
        name = "cafe01-l1.500000e-3-a3.500000e-1.tess"
        status, _, _ = self.request("GET", f"{TESS_CACHE_ROUTE_PREFIX}{name}")
        self.assertEqual(status, 404)
        status, _, _ = self.request("POST", f"{TESS_CACHE_ROUTE_PREFIX}{name}", b"TESSbytes")
        self.assertEqual(status, 204)
        status, body, _ = self.request("GET", f"{TESS_CACHE_ROUTE_PREFIX}{name}")
        self.assertEqual((status, body), (200, b"TESSbytes"))
        status, _, _ = self.request("POST", f"{TESS_CACHE_ROUTE_PREFIX}%2e%2e/escape.tess", b"x")
        self.assertEqual(status, 403)
        status, _, headers = self.request("OPTIONS", f"{TESS_CACHE_ROUTE_PREFIX}{name}")
        self.assertEqual(status, 204)
        self.assertIn("POST", headers.get("access-control-allow-methods", ""))

    def test_unknown_paths_404(self) -> None:
        for method, path in (("GET", "/anything"), ("POST", "/__render_asset/inside.step")):
            status, _, _ = self.request(method, path)
            self.assertEqual(status, 404, f"{method} {path}")

    def test_batch_route_round_trip(self) -> None:
        import json

        name = "beef01-l1.500000e-3-a3.500000e-1.tess"
        status, _, _ = self.request("POST", f"{TESS_CACHE_ROUTE_PREFIX}{name}", b"ENTRY")
        self.assertEqual(status, 204)
        body = json.dumps({"names": [name, "missing.tess"]}).encode()
        status, response, _ = self.request("POST", TESS_CACHE_BATCH_PATH, body)
        self.assertEqual(status, 200)
        self.assertEqual(decode_batch(response), [b"ENTRY", None])
        status, _, _ = self.request("POST", TESS_CACHE_BATCH_PATH, b"not json")
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
