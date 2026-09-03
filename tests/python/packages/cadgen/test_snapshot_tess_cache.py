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


class TessellationCacheRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory(prefix="tess-cache-")
        self.addCleanup(self._tmp.cleanup)
        # Resolved: Windows hands tempfile a path through %TMP%, which is
        # commonly spelled with 8.3 short components (``C:\Users\RUNNER~1\...``)
        # while Path.home() comes back long, and the guard below compares them.
        self.home = Path(self._tmp.name).resolve()
        # Every root override cleared and the home pointed at the sandbox, so
        # cache_root() takes its LAST branch (~/.cache/cadgen) on both platforms
        # and lands inside the temp dir. LOCALAPPDATA has to go too: on Windows
        # it is consulted BEFORE the home, so leaving it set wrote the runner's
        # real user cache. USERPROFILE (and the HOMEDRIVE+HOMEPATH pair behind
        # it) likewise -- ``~`` expansion reads HOME on POSIX and those on
        # Windows.
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
        # Guard the assumption this suite rests on: nothing it writes escapes.
        self.assertEqual(Path.home().resolve(), self.home)

    def route(self, name: str) -> str:
        return f"{TESS_CACHE_ROUTE_PREFIX}{name}"




    def test_empty_body_is_accepted_and_dropped(self) -> None:
        pathname = self.route("c0-l1.000000e-3-a3.500000e-1.tess")
        self.assertTrue(write_tessellation_cache_entry(pathname, None))
        self.assertTrue(write_tessellation_cache_entry(pathname, b""))
        self.assertIsNone(read_tessellation_cache_entry(pathname))

    def test_batch_mixes_hits_misses_and_refused_names_as_misses(self) -> None:
        import json

        write_tessellation_cache_entry(self.route("hit1-l1.000000e-3-a3.500000e-1.tess"), b"AAA")
        write_tessellation_cache_entry(self.route("hit2-l1.000000e-3-a3.500000e-1.tess"), b"BBBBB")
        body = json.dumps({
            "names": [
                "hit1-l1.000000e-3-a3.500000e-1.tess",
                "missing-l1.000000e-3-a3.500000e-1.tess",
                "../escape.tess",  # refused name = miss, never an error
                "hit2-l1.000000e-3-a3.500000e-1.tess",
                42,  # non-string = miss
            ],
        }).encode()
        entries = decode_batch(read_tessellation_cache_batch(body))
        self.assertEqual(entries, [b"AAA", None, None, b"BBBBB", None])

    def test_batch_rejects_malformed_requests(self) -> None:
        self.assertIsNone(read_tessellation_cache_batch(b"not json"))
        self.assertIsNone(read_tessellation_cache_batch(b"{}"))
        self.assertIsNone(read_tessellation_cache_batch(b'{"names": "x"}'))
        import json

        too_many = json.dumps({"names": ["a.tess"] * 5000}).encode()
        self.assertIsNone(read_tessellation_cache_batch(too_many))

    def test_batch_with_cache_disabled_is_all_misses(self) -> None:
        write_tessellation_cache_entry(self.route("c0-l1.000000e-3-a3.500000e-1.tess"), b"X")
        with mock.patch.dict(os.environ, {"CADGEN_MESH_CACHE": "0"}):
            entries = decode_batch(read_tessellation_cache_batch(
                b'{"names": ["c0-l1.000000e-3-a3.500000e-1.tess"]}',
            ))
        self.assertEqual(entries, [None])


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
