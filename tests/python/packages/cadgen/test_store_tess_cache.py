"""The shared v4 tessellation protocol stays below HTTP transports."""

from __future__ import annotations

import base64
import json
import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.store.tess_cache import (  # noqa: E402
    encode_tessellation_cache_batch,
    is_tessellation_cache_key,
    read_tess_cache_batch,
    read_tess_cache_probe,
    read_tessellation_cache,
    tessellation_cache_dir,
    write_tessellation_cache,
)
from tests.python.support.tessellation import tessellation_fixture  # noqa: E402

FIXTURE = tessellation_fixture()
GOOD_KEY = FIXTURE["key"]
PAYLOAD = base64.b64decode(FIXTURE["bytes"])


class TessellationCacheStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="store-tess-cache-")
        self.addCleanup(self._tmp.cleanup)
        self._environment = mock.patch.dict(os.environ, {
            "CADGEN_CACHE_DIR": str(Path(self._tmp.name) / "cache"),
            "CADGEN_MESH_CACHE": "1",
        })
        self._environment.start()
        self.addCleanup(self._environment.stop)

    def test_validated_v4_round_trip(self) -> None:
        self.assertTrue(is_tessellation_cache_key(GOOD_KEY))
        write_tessellation_cache(GOOD_KEY, PAYLOAD)
        row = read_tess_cache_probe(json.dumps({
            "tessellationInputs": [GOOD_KEY],
        }).encode())["entries"][GOOD_KEY]
        self.assertEqual(
            read_tessellation_cache(
                GOOD_KEY, expected_object=row["object"], max_bytes=row["byteLength"],
            ),
            PAYLOAD,
        )

    def test_invalid_keys_are_rejected_before_disk_access(self) -> None:
        for key in ("", ".hidden", "../escape", "sub/key", "a..b", "legacy-t1"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                read_tessellation_cache(key)
        self.assertFalse(Path(tessellation_cache_dir()).exists())

    def test_disabled_cache_drops_reads_and_writes(self) -> None:
        os.environ["CADGEN_MESH_CACHE"] = "0"
        write_tessellation_cache(GOOD_KEY, PAYLOAD)
        self.assertIsNone(read_tessellation_cache(GOOD_KEY))
        self.assertFalse(Path(tessellation_cache_dir()).exists())

    def test_batch_reads_are_exact_object_and_size_bound(self) -> None:
        write_tessellation_cache(GOOD_KEY, PAYLOAD)
        row = read_tess_cache_probe(json.dumps({
            "tessellationInputs": [GOOD_KEY],
        }).encode())["entries"][GOOD_KEY]
        request = {"entries": [{
            "tessellationInput": GOOD_KEY,
            "object": row["object"],
            "maxBytes": row["byteLength"],
        }]}
        body = read_tess_cache_batch(json.dumps(request).encode())
        self.assertEqual(struct.unpack_from("<I", body, 12)[0], len(PAYLOAD))
        request["entries"][0]["maxBytes"] -= 1
        body = read_tess_cache_batch(json.dumps(request).encode())
        self.assertEqual(struct.unpack_from("<I", body, 12)[0], 0)

    def test_shared_framer_preserves_alignment_and_misses(self) -> None:
        body = encode_tessellation_cache_batch([b"A", None, b"BCD", b"WXYZ"])
        self.assertEqual(struct.unpack_from("<III", body), (0x42534554, 1, 4))
        offset = 12
        decoded: list[bytes | None] = []
        for _ in range(4):
            (length,) = struct.unpack_from("<I", body, offset)
            offset += 4
            decoded.append(body[offset:offset + length] if length else None)
            offset += length + (-length % 4)
        self.assertEqual(decoded, [b"A", None, b"BCD", b"WXYZ"])
        self.assertEqual(offset, len(body))


if __name__ == "__main__":
    unittest.main()
