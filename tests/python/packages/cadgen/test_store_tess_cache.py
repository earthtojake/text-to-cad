"""The shared store boundary for opaque component-tessellation cache bytes."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.store.tess_cache import (  # noqa: E402
    encode_tessellation_cache_batch,
    is_tessellation_cache_key,
    read_tessellation_cache,
    tessellation_cache_dir,
    write_tessellation_cache,
)

GOOD_KEY = "c0ffee-t1-l1.500000e-3-a3.500000e-1"


class TessellationCacheStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="store-tess-cache-")
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

    def test_validated_key_round_trip_preserves_opaque_bytes(self) -> None:
        payload = b"\x00\x01binary\xff"
        self.assertTrue(is_tessellation_cache_key(GOOD_KEY))
        write_tessellation_cache(GOOD_KEY, payload)
        self.assertEqual(read_tessellation_cache(GOOD_KEY), payload)

    def test_invalid_keys_are_rejected_before_disk_access(self) -> None:
        for key in ("", ".hidden", "../escape", "sub/key", "a..b", "key.tess\n"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                read_tessellation_cache(key)
        self.assertFalse(Path(tessellation_cache_dir()).exists())

    def test_corrupt_index_and_missing_object_are_cache_misses(self) -> None:
        from cadgen.store.index import write_entry
        from cadgen.store.objects import put_object

        index_path = Path(tessellation_cache_dir()) / GOOD_KEY
        index_path.parent.mkdir(parents=True)
        index_path.write_text("not json", encoding="utf-8")
        self.assertIsNone(read_tessellation_cache(GOOD_KEY))
        index_path.write_text('{"object":"not-a-digest"}', encoding="utf-8")
        self.assertIsNone(read_tessellation_cache(GOOD_KEY))
        write_entry("mesh", GOOD_KEY, {"object": put_object(b"")})
        self.assertIsNone(read_tessellation_cache(GOOD_KEY))

    def test_disabled_cache_drops_reads_and_writes(self) -> None:
        os.environ["CADGEN_MESH_CACHE"] = "0"
        write_tessellation_cache(GOOD_KEY, b"payload")
        self.assertIsNone(read_tessellation_cache(GOOD_KEY))
        self.assertFalse(Path(tessellation_cache_dir()).exists())

    def test_shared_framer_preserves_alignment_and_misses(self) -> None:
        import struct

        body = encode_tessellation_cache_batch([b"A", None, b"BCD", b"WXYZ"])
        self.assertEqual(struct.unpack_from("<III", body), (0x42534554, 1, 4))
        offset = 12
        decoded: list[bytes | None] = []
        for _ in range(4):
            (length,) = struct.unpack_from("<I", body, offset)
            offset += 4
            decoded.append(body[offset : offset + length] if length else None)
            offset += length + (-length % 4)
        self.assertEqual(decoded, [b"A", None, b"BCD", b"WXYZ"])
        self.assertEqual(offset, len(body))


if __name__ == "__main__":
    unittest.main()
