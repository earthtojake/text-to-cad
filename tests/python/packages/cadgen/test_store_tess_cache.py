"""The store's mesh protocol stays below HTTP transports: probes, exact reads, batches, produce."""

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

from cadgen.store import meshes  # noqa: E402
from cadgen.store.tess_cache import (  # noqa: E402
    encode_tessellation_cache_batch,
    is_tessellation_cache_key,
    produce_tess_cache,
    read_tess_cache_batch,
    read_tess_cache_probe,
    read_tessellation_cache,
    tessellation_cache_dir,
)
from tests.python.support.inline_artifacts import inline_artifacts  # noqa: E402
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
        })
        self._environment.start()
        self.addCleanup(self._environment.stop)

    def test_validated_round_trip(self) -> None:
        self.assertTrue(is_tessellation_cache_key(GOOD_KEY))
        meshes.write(GOOD_KEY, PAYLOAD)
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

    def test_produce_meshes_what_a_probe_finds_missing_from_its_surface_alone(self) -> None:
        from build123d import Box, Cylinder
        from cadgen.store import surfaces
        from cadgen.store.build import build_tree_from_compound

        tree, descriptor, _ = build_tree_from_compound(Box(10, 10, 10) - Cylinder(3, 10), root_name="bored")
        producer = surfaces.producer_identity()
        [entry] = descriptor["components"].values()
        surfaces.derive(tree, producer=producer)
        surface_input = surfaces.surface_input(entry, producer)
        wanted = meshes.tessellation_key(surface_input, 5e-4, 0.35)
        coarse = meshes.tessellation_key(surface_input, 2e-3, 1.4)
        unknown = meshes.tessellation_key("f" * 64)
        too_fine = meshes.tessellation_key(surface_input, 1e-6, 0.35)
        older = wanted.replace(f"-t{meshes.TESSELLATOR_VERSION}-", f"-t{meshes.TESSELLATOR_VERSION - 1}-")
        ask = lambda keys: read_tess_cache_probe(json.dumps({"tessellationInputs": keys}).encode())  # noqa: E731
        produce = lambda keys: produce_tess_cache(json.dumps({"tessellationInputs": keys}).encode())  # noqa: E731
        self.assertEqual(ask([wanted])["entries"], {}, "derivation meshed nothing it was not asked for")
        with inline_artifacts() as jobs, mock.patch("cadgen.daemon.broker.job_limit", return_value=2), \
                mock.patch("cadgen.daemon.artifacts.MESHES_PER_STARTED_WORKER", 1):
            self.assertEqual(produce([unknown, too_fine, older]), {"entries": {}},
                             "a surface the store lacks, a finer request or another mesher's key stays missing")
            self.assertEqual(jobs.call_count, 0, "and starts no job: no worker starts for nothing")
            produced = produce([wanted, unknown, coarse, too_fine, older])
            self.assertEqual(list(produced["entries"]), [wanted, coarse])
            requests = [call.args[0] for call in jobs.call_args_list]
            self.assertEqual([request["kind"] for request in requests], ["meshes", "meshes"],
                             "the missing keys are dealt across as many jobs as the pool runs at once")
            self.assertEqual(sorted(key for request in requests for key in request["keys"]),
                             sorted([wanted, coarse]), "each key a job can mesh, once; only those")
            self.assertEqual(ask([wanted, coarse])["entries"], produced["entries"],
                             "the produced meshes are stored, and probe as made")
            body = read_tessellation_cache(wanted, expected_object=produced["entries"][wanted]["object"])
            self.assertEqual(meshes.payload_record(wanted, body), produced["entries"][wanted])
            self.assertEqual(produce([wanted]), {"entries": {wanted: produced["entries"][wanted]}},
                             "asking again reads what is stored")
            self.assertEqual(jobs.call_count, 2, "and starts no job")
            for malformed in (b"{}", b'{"tessellationInputs": [1]}', b"not json"):
                with self.subTest(body=malformed):
                    self.assertIsNone(produce_tess_cache(malformed))

    def test_batch_reads_are_exact_object_and_size_bound(self) -> None:
        meshes.write(GOOD_KEY, PAYLOAD)
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
