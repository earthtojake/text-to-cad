"""The store's part protocol stays below HTTP transports: probes, exact reads, batches."""

from __future__ import annotations

import base64
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

_CADGEN_SRC = str(add_repo_path("packages/cadgen/src"))

from cadgen.store.tess_cache import (  # noqa: E402
    encode_tessellation_cache_batch,
    read_part_object,
    read_tess_cache_batch,
    read_tess_cache_probe,
    tess_cache_name,
)
from tests.python.support.tessellation import part_fixture, store_part  # noqa: E402

FIXTURE = part_fixture()
KEY = FIXTURE["key"]
GLB = base64.b64decode(FIXTURE["glb"])
TABLE = base64.b64decode(FIXTURE["selectors"])


def probe_body(*keys) -> bytes:
    return json.dumps({"parts": list(keys)}).encode()


class PartTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="store-tess-cache-")
        self.addCleanup(self._tmp.cleanup)
        self.store = Path(self._tmp.name) / "cache"
        self._environment = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.store)})
        self._environment.start()
        self.addCleanup(self._environment.stop)

    def test_a_probed_part_reads_back_both_its_objects(self) -> None:
        self.assertEqual(store_part(), FIXTURE["record"])
        record = read_tess_cache_probe(probe_body(KEY, "2" * 64 + KEY[64:], 7))["entries"]
        self.assertEqual(record, {KEY: FIXTURE["record"]}, "a missing part is absent")
        for suffix, payload in ((".glb", GLB), (".selectors.json", TABLE)):
            role = tess_cache_name(KEY + suffix)[1]
            facts = FIXTURE["record"][role]
            self.assertEqual(read_part_object(KEY + suffix, expected_object=facts["object"],
                                              max_bytes=facts["byteLength"]), payload)

    def test_a_probe_and_a_refused_read_open_no_object(self) -> None:
        record = store_part()
        original_open = Path.open

        def only_index(path, *args, **kwargs):
            self.assertNotIn("objects", path.parts, "an object was opened")
            return original_open(path, *args, **kwargs)

        with mock.patch.object(Path, "open", only_index):
            self.assertEqual(read_tess_cache_probe(probe_body(KEY)), {"entries": {KEY: record}})
            facts = record["glb"]
            self.assertIsNone(read_part_object(f"{KEY}.glb", expected_object="f" * 64, max_bytes=facts["byteLength"]))
            self.assertIsNone(read_part_object(f"{KEY}.glb", expected_object=facts["object"],
                                               max_bytes=facts["byteLength"] - 1))
            self.assertIsNone(read_part_object(f"{KEY}.selectors.json", expected_object=facts["object"],
                                               max_bytes=facts["byteLength"]), "each object is its own role's")

    def test_a_name_that_names_no_part_object_is_refused_before_disk_access(self) -> None:
        self.assertEqual(tess_cache_name(f"{KEY}.glb"), (KEY, "glb"))
        self.assertEqual(tess_cache_name(f"{KEY}.selectors.json"), (KEY, "selectors"))
        older = f"{KEY[:64]}-v0"
        for name in ("", ".hidden", "../escape", f"sub/{KEY}.glb", KEY, f"{KEY}.surf", f"{older}.glb",
                     f"{KEY.upper()}.glb", f"{KEY}.glb/..", f"{KEY}.selectors"):
            with self.subTest(name=name):
                self.assertIsNone(tess_cache_name(name))
                self.assertIsNone(read_part_object(name, expected_object="0" * 64, max_bytes=1))
        self.assertFalse(self.store.exists())

    def test_batch_reads_are_exact_object_and_size_bound(self) -> None:
        facts = store_part()["glb"]
        request = {"entries": [{"part": KEY, "object": facts["object"], "maxBytes": facts["byteLength"]}]}

        def served(changes=None, cap=None) -> int:
            entry = {**request["entries"][0], **(changes or {})}
            body = json.dumps({"entries": [entry]}).encode()
            if cap is None:
                return struct.unpack_from("<I", read_tess_cache_batch(body), 12)[0]
            with mock.patch("cadgen.store.tess_cache.TESS_CACHE_BATCH_MAX_BYTES", cap):
                return struct.unpack_from("<I", read_tess_cache_batch(body), 12)[0]

        self.assertEqual(served(), len(GLB))
        self.assertEqual(served({"maxBytes": len(GLB) - 1}), 0)
        self.assertEqual(served({"object": "f" * 64}), 0)
        self.assertEqual(served({"object": FIXTURE["record"]["selectors"]["object"]}), 0, "a batch serves meshes")
        # The container's own framing counts against its budget: 12 bytes of header, 4 per entry.
        self.assertEqual(served(cap=len(GLB) + 16), len(GLB))
        self.assertEqual(served(cap=len(GLB) + 15), 0)
        self.assertIsNone(read_tess_cache_batch(b'{"names":[]}'))
        self.assertIsNone(read_tess_cache_batch(json.dumps({"entries": request["entries"] * 257}).encode()))
        self.assertIsNone(read_tess_cache_probe(probe_body(*[KEY] * 257)))

    def test_serving_stored_parts_never_imports_numpy(self) -> None:
        # The CAD Viewer's server probes and batch-reads stored meshes and never views their
        # arrays, so numpy stays out of that process. A fresh interpreter: this one has it.
        facts = store_part()["glb"]
        entry = {"part": KEY, "object": facts["object"], "maxBytes": facts["byteLength"]}
        code = (
            f"import json, sys; sys.path.insert(0, {_CADGEN_SRC!r})\n"
            "from cadgen.store.tess_cache import read_tess_cache_batch, read_tess_cache_probe\n"
            f"probed = read_tess_cache_probe({probe_body(KEY)!r})\n"
            f"batch = read_tess_cache_batch({json.dumps({'entries': [entry]}).encode()!r})\n"
            "print(json.dumps({'probed': len(probed['entries']), 'served': int.from_bytes(batch[12:16], 'little'),"
            " 'numpy': 'numpy' in sys.modules}))\n"
        )
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"probed": 1, "served": len(GLB), "numpy": False})

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
