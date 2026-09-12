"""The snapshot host's side of the shared component-tessellation cache.

The page and the export CLI share ONE on-disk store (~/.cache/cadgen/meshes;
codec in packages/core/src/lib/surf/tessellationCache.js). Python never
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

import cadgen.snapshot_core as snapshot_core  # noqa: E402
from cadgen.snapshot_core import (  # noqa: E402
    TESS_CACHE_BATCH_MAGIC,
    TESS_CACHE_BATCH_PATH,
    TESS_CACHE_BATCH_VERSION,
    TESS_CACHE_ROUTE_PREFIX,
    SnapshotAssetServer,
    read_tessellation_cache_batch,
    read_tessellation_cache_entry,
    write_tessellation_cache_entry,
)


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



class SnapshotCacheBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory(prefix="snapshot-cache-boundary-")
        self.addCleanup(self._tmp.cleanup)
        self._environment = mock.patch.dict(
            os.environ,
            {
                "CADGEN_CACHE_DIR": str(Path(self._tmp.name) / "cache"),
                "CADGEN_MESH_CACHE": "1",
            },
        )
        self._environment.start()
        self.addCleanup(self._environment.stop)

    def test_snapshot_cache_boundary_does_not_reach_into_viewer(self) -> None:
        source = Path(snapshot_core.__file__).read_text(encoding="utf-8")
        self.assertNotIn(
            "cadgen.viewer",
            source,
            "snapshot cache I/O belongs to cadgen.store, independent of the HTTP host",
        )

    def test_snapshot_and_http_hosts_share_exact_store_bytes(self) -> None:
        import json

        from cadgen.viewer.tess_cache import (
            read_tess_cache_batch,
            read_tess_cache_entry,
            write_tess_cache_entry,
        )

        name = "feed01-t1-l1.500000e-3-a3.500000e-1.tess"
        route = f"{TESS_CACHE_ROUTE_PREFIX}{name}"
        payload = b"\x00shared\xff"
        self.assertTrue(write_tessellation_cache_entry(route, payload))
        self.assertEqual(read_tess_cache_entry(route), (200, payload))
        self.assertEqual(write_tess_cache_entry(route, b"second"), 204)
        self.assertEqual(read_tessellation_cache_entry(route), b"second")
        request = json.dumps({"names": [name, "missing.tess"]}).encode()
        self.assertEqual(read_tessellation_cache_batch(request), read_tess_cache_batch(request))

    def test_snapshot_transport_refuses_malformed_cache_names(self) -> None:
        for name in (
            "../escape.tess",
            "%2e%2e%2fescape.tess",
            "%zz.tess",
            "%C0%AF.tess",
            "a.tess%0A",
        ):
            route = f"{TESS_CACHE_ROUTE_PREFIX}{name}"
            with self.subTest(name=name):
                self.assertIsNone(read_tessellation_cache_entry(route))
                self.assertFalse(write_tessellation_cache_entry(route, b"payload"))


if __name__ == "__main__":
    unittest.main()
