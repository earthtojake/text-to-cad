"""Real JS TESS bytes cross the Python store and both HTTP cache adapters."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import struct
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory

add_repo_path("packages/cadgen/src")

from cadgen.store import meshes
from cadgen.store.index import entry_path, write_entry
from cadgen.store.objects import object_path, put_object
from cadgen.viewer.tess_cache import read_tess_cache_batch, read_tess_cache_probe

class MeshStoreContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.python.support.tessellation import tessellation_fixture
        cls.fixture = tessellation_fixture()
        cls.key = cls.fixture["key"]
        cls.payload = base64.b64decode(cls.fixture["bytes"])

    def setUp(self):
        self.tmp = generated_cad_directory(prefix="store-tess-v4-")
        self.addCleanup(self.tmp.cleanup)
        self.store = Path(self.tmp.name) / "store"
        self.env = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.store), "CADGEN_MESH_CACHE": "1"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def rewritten_header(self, path, value):
        old_size = struct.unpack_from("<I", self.payload, 8)[0]
        header = json.loads(self.payload[12:12 + old_size])
        target = header
        for item in path[:-1]:
            target = target[item]
        target[path[-1]] = value
        encoded = json.dumps(header, separators=(",", ":")).encode()
        encoded += b" " * (-len(encoded) % 4)
        return self.payload[:8] + struct.pack("<I", len(encoded)) + encoded + self.payload[12 + old_size:]

    def test_real_js_payload_and_memory_facts_match_python_exactly(self):
        row = meshes.payload_record(self.key, self.payload)
        self.assertEqual(row, self.fixture["facts"])
        self.assertEqual(row["edgeSegmentCount"], 2)
        self.assertEqual(meshes.write(self.key, self.payload), row)
        self.assertEqual(meshes.probe(self.key), row)
        self.assertEqual(meshes.read(self.key, expected_object=row["object"], max_bytes=row["byteLength"]), self.payload)
        self.assertEqual(set(path.name for path in self.store.iterdir()), {"objects", "index"})

    def test_probe_never_reads_a_tessellation_body_or_surface(self):
        row = meshes.write(self.key, self.payload)
        original_open = Path.open
        def only_index(path, *args, **kwargs):
            self.assertNotIn("objects", path.parts, "probe must not open even a warm object")
            return original_open(path, *args, **kwargs)
        with mock.patch.object(Path, "open", only_index):
            self.assertEqual(meshes.probe(self.key), row)
            self.assertEqual(read_tess_cache_probe(json.dumps({"tessellationInputs": [self.key]}).encode()),
                             {"entries": {self.key: row}})
        self.assertFalse(object_path(row["surfaceObject"]).exists(), "SURF provenance is not required")

    def test_body_is_bound_to_probed_object_and_admitted_size_before_open(self):
        row = meshes.write(self.key, self.payload)
        original_open = Path.open
        def only_index(path, *args, **kwargs):
            self.assertNotIn("objects", path.parts, "rejected admission must not open a body")
            return original_open(path, *args, **kwargs)
        with mock.patch.object(Path, "open", only_index):
            self.assertIsNone(meshes.read(self.key, expected_object="f" * 64, max_bytes=row["byteLength"]))
            self.assertIsNone(meshes.read(self.key, expected_object=row["object"], max_bytes=row["byteLength"] - 1))

    def test_corrupt_body_is_a_miss_and_can_be_repaired_without_rebinding_inputs(self):
        row = meshes.write(self.key, self.payload)
        damaged = bytearray(self.payload)
        damaged[-1] ^= 1
        object_path(row["object"]).write_bytes(damaged)
        self.assertIsNotNone(meshes.probe(self.key), "same-size damage is checked on admitted body read")
        self.assertIsNone(meshes.read(self.key))
        self.assertEqual(meshes.write(self.key, self.payload), row)
        self.assertEqual(meshes.read(self.key), self.payload)

    def test_same_input_different_mesh_or_surface_does_not_replace_valid_index(self):
        row = meshes.write(self.key, self.payload)
        for name in ("changed", "changedSurface"):
            with self.subTest(name=name), self.assertRaises(meshes.MeshConflictError):
                meshes.write(self.key, base64.b64decode(self.fixture[name]))
            self.assertEqual(meshes.probe(self.key), row)

    def test_corrupt_or_oversized_index_and_false_size_are_misses(self):
        row = meshes.write(self.key, self.payload)
        for field, value in (("decodedBytes", 1), ("byteLength", row["byteLength"] + 4),
                             ("surfaceInput", "b" * 64), ("schemaVersion", 0)):
            broken = copy.deepcopy(row)
            broken[field] = value
            write_entry("mesh", self.key, broken)
            self.assertIsNone(meshes.probe(self.key), field)
        entry_path("mesh", self.key).write_bytes(b" " * (meshes.MAX_INDEX_BYTES + 1))
        self.assertIsNone(meshes.probe(self.key))

    def test_adjacent_binary64_quality_and_legacy_keys_cannot_alias(self):
        import math
        chord = .0015
        other = math.nextafter(chord, math.inf)
        self.assertNotEqual(meshes.tessellation_key("1" * 64, chord), meshes.tessellation_key("1" * 64, other))
        for value in (0, -0.0, -1, math.inf, math.nan, True, "0.0015"):
            with self.assertRaises((ValueError, TypeError)):
                meshes.float64_hex(value)
        self.assertFalse(meshes.valid_key("1" * 64 + "-t2-l1.500000e-3-a3.500000e-1"))
        legacy = bytearray(self.payload)
        legacy[4:8] = (3).to_bytes(4, "little")
        with self.assertRaises(ValueError):
            meshes.payload_record(self.key, legacy)

    def test_admitted_batch_is_exact_object_bound_and_byte_bounded(self):
        row = meshes.write(self.key, self.payload)
        request = {"entries": [{"tessellationInput": self.key, "object": row["object"], "maxBytes": row["byteLength"]}]}
        body = json.dumps(request).encode()
        with mock.patch("cadgen.viewer.tess_cache.TESS_CACHE_BATCH_MAX_BYTES", row["byteLength"] + 16):
            self.assertEqual(int.from_bytes(read_tess_cache_batch(body)[12:16], "little"), row["byteLength"])
        with mock.patch("cadgen.viewer.tess_cache.TESS_CACHE_BATCH_MAX_BYTES", row["byteLength"] + 12):
            self.assertEqual(read_tess_cache_batch(body), b"TESB" + (1).to_bytes(4, "little") + (1).to_bytes(4, "little") + b"\0" * 4)
        request["entries"][0]["object"] = "f" * 64
        self.assertEqual(int.from_bytes(read_tess_cache_batch(json.dumps(request).encode())[12:16], "little"), 0)
        self.assertIsNone(read_tess_cache_batch(b'{"names":[]}'))
        self.assertIsNone(read_tess_cache_probe(json.dumps({"tessellationInputs": [self.key] * 257}).encode()))

    def test_disabling_cache_does_not_create_store_or_read_native_inputs(self):
        with mock.patch.dict(os.environ, {"CADGEN_MESH_CACHE": "0"}):
            self.assertIsNone(meshes.write(self.key, self.payload))
            self.assertIsNone(meshes.probe(self.key))
            self.assertIsNone(meshes.read(self.key))
        self.assertFalse(self.store.exists())

    def test_malformed_render_metadata_is_rejected_in_python_and_shared_js(self):
        cases = [
            ("bounds object", ["bounds"], None),
            ("bounds vector", ["bounds", "min"], [0, 0]),
            ("bounds scalar type", ["bounds", "min"], [False, 0, 0]),
            ("reversed bounds", ["bounds", "min"], [4, 0, 0]),
            ("nonfinite JSON", ["scale"], float("nan")),
            ("infinite scale", ["scale"], float("inf")),
            ("zero scale", ["scale"], 0),
            ("string scale", ["scale"], "1"),
            ("part color", ["partColor"], [1, 0, 0]),
            ("color scalar", ["partColor"], [1, 0, 0, True]),
            ("edge object", ["edges", 0], None),
            ("edge ordinal", ["edges", 0, "ord"], 0),
            ("edge fractional ordinal", ["edges", 0, "ord"], 1.5),
            ("edge absent class", ["edges", 0, "ord"], 2),
            ("edge mismatched class", ["edges", 0, "visibilityClass"], "seam"),
            ("edge nonstring class", ["edges", 0, "visibilityClass"], {}),
            ("duplicate edge", ["edges"], [
                {"ord": 1, "count": 9, "visibilityClass": "boundary"},
                {"ord": 1, "count": 0, "visibilityClass": "boundary"},
            ]),
            ("null class pair", ["edgeClasses"], [None]),
            ("short class pair", ["edgeClasses"], [[1]]),
            ("long class pair", ["edgeClasses"], [[1, "boundary", 2]]),
            ("class ordinal", ["edgeClasses"], [[True, "boundary"]]),
            ("unknown class", ["edgeClasses"], [[1, "invented"]]),
            ("nonstring class", ["edgeClasses"], [[1, {}]]),
            ("duplicate class", ["edgeClasses"], [[1, "boundary"], [1, "boundary"]]),
            ("face object", ["faceRanges"], [None]),
            ("face ordinal", ["faceRanges", 0, "ord"], 0),
            ("face count type", ["faceRanges", 0, "indexCount"], "3"),
            ("face partial triangle", ["faceRanges", 0, "indexCount"], 2),
            ("face outside indices", ["faceRanges", 0, "indexCount"], 6),
            ("face gap", ["faceRanges", 0, "indexStart"], 3),
            ("uncovered indices", ["faceRanges"], []),
            ("face color", ["faceRanges", 0, "color"], [0, 1, 0]),
            ("duplicate face", ["faceRanges"], [
                {"ord": 1, "indexStart": 0, "indexCount": 0},
                {"ord": 1, "indexStart": 0, "indexCount": 3},
            ]),
            ("overlapping ranges", ["faceRanges"], [
                {"ord": 1, "indexStart": 0, "indexCount": 3},
                {"ord": 2, "indexStart": 0, "indexCount": 3},
            ]),
        ]
        payloads = []
        for label, path, value in cases:
            payload = self.rewritten_header(path, value)
            with self.subTest(label=label), self.assertRaises(ValueError):
                meshes.payload_record(self.key, payload)
            payloads.append(base64.b64encode(payload).decode())

        from tests.python.support.tessellation import CODEC
        script = """
import fs from 'node:fs';
const api = await import(process.argv[1]);
const results = JSON.parse(fs.readFileSync(0, 'utf8')).map((body) => {
  const bytes = new Uint8Array(Buffer.from(body, 'base64'));
  return [api.tessellationPayloadFacts(bytes), api.decodeComponentTessellation(bytes)];
});
console.log(JSON.stringify(results));
"""
        result = subprocess.run(["node", "--input-type=module", "-e", script, CODEC.as_uri()],
                                input=json.dumps(payloads), text=True, capture_output=True, check=True, timeout=10)
        self.assertEqual(json.loads(result.stdout), [[None, None]] * len(cases))

    def test_hash_valid_unrenderable_payload_is_a_miss_and_repairs(self):
        valid = meshes.write(self.key, self.payload)
        payload = self.rewritten_header(["edgeClasses"], [None])
        broken = copy.deepcopy(valid)
        old_header = broken["headerBytes"]
        broken["object"] = put_object(payload)
        self.assertEqual(broken["object"], hashlib.sha256(payload).hexdigest())
        broken["headerBytes"] = struct.unpack_from("<I", payload, 8)[0]
        broken["byteLength"] = len(payload)
        broken["decodedBytes"] += 8 * (broken["headerBytes"] - old_header)
        write_entry("mesh", self.key, broken)
        self.assertEqual(meshes.probe(self.key), broken, "metadata probe does not open a body")
        self.assertIsNone(meshes.read(self.key, expected_object=broken["object"], max_bytes=len(payload)))
        self.assertEqual(meshes.write(self.key, self.payload), valid)
        self.assertEqual(meshes.read(self.key), self.payload)

    def test_optional_render_metadata_and_unused_edge_classes_remain_valid(self):
        for path, value in ((["partColor"], None), (["faceRanges", 0, "color"], None),
                            (["edges", 0, "visibilityClass"], None),
                            (["edgeClasses"], [[1, "boundary"], [2, "degenerate"]])):
            with self.subTest(path=path):
                row = meshes.payload_record(self.key, self.rewritten_header(path, value))
                self.assertEqual(row["tessellationInput"], self.key)

    def test_recursive_json_damage_is_a_miss_or_clean_validation_failure(self):
        meshes.write(self.key, self.payload)
        entry_path("mesh", self.key).write_bytes(b"[" * 2000 + b"0" + b"]" * 2000)
        self.assertIsNone(meshes.probe(self.key))
        header = b"[" * 2000 + b"0" + b"]" * 2000
        header += b" " * (-len(header) % 4)
        body = self.payload[:8] + struct.pack("<I", len(header)) + header
        with self.assertRaises(ValueError):
            meshes.payload_record(self.key, body)
