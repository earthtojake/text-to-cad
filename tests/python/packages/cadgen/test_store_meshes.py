"""cadgen's stored mesh bytes (GLB) cross the Python store, both HTTP adapters and the shared JS reader."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import struct
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory

_CADGEN_SRC = str(add_repo_path("packages/cadgen/src"))

from cadgen.store import meshes
from cadgen.store.index import entry_path, write_entry
from cadgen.store.objects import object_path, put_object
from cadgen.store.tess_cache import read_tess_cache_batch, read_tess_cache_probe

_DELETE = object()


def _json(payload: bytes) -> dict:
    return json.loads(payload[20:20 + struct.unpack_from("<I", payload, 12)[0]])


def _with_json(payload: bytes, gltf: dict) -> bytes:
    """The body with its JSON chunk replaced by ``gltf`` and its BIN chunk kept."""
    old = struct.unpack_from("<I", payload, 12)[0]
    text = json.dumps(gltf, separators=(",", ":")).encode()
    text += b" " * (-len(text) % 4)
    rest = payload[20 + old:]
    return (struct.pack("<III", 0x46546C67, 2, 20 + len(text) + len(rest))
            + struct.pack("<II", len(text), 0x4E4F534A) + text + rest)


def _with_word(payload: bytes, view: int | str, word: int, value: int, fmt: str = "<I") -> bytes:
    """The body with one word of a buffer view (its index, or a table's name) set to ``value``."""
    views = _json(payload)["bufferViews"]
    entry = views[view] if isinstance(view, int) else next(item for item in views if item.get("name") == view)
    offset = 28 + struct.unpack_from("<I", payload, 12)[0] + entry["byteOffset"] + struct.calcsize(fmt) * word
    data = bytearray(payload)
    struct.pack_into(fmt, data, offset, value)
    return bytes(data)


class MeshStoreContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.python.support.tessellation import tessellation_fixture
        cls.fixture = tessellation_fixture()
        cls.key = cls.fixture["key"]
        cls.payload = base64.b64decode(cls.fixture["bytes"])

    def setUp(self):
        self.tmp = generated_cad_directory(prefix="store-tess-")
        self.addCleanup(self.tmp.cleanup)
        self.store = Path(self.tmp.name) / "store"
        self.env = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.store)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def rewritten(self, path, value):
        gltf = _json(self.payload)
        target = gltf
        for item in path[:-1]:
            target = target[item]
        if value is _DELETE:
            del target[path[-1]]
        else:
            target[path[-1]] = value
        return _with_json(self.payload, gltf)

    def test_python_payload_and_memory_facts_match_the_js_reader_exactly(self):
        from tests.python.support.tessellation import js_reader

        row = meshes.payload_record(self.key, self.payload)
        self.assertEqual(row, self.fixture["facts"])
        [[facts, decodes]] = js_reader([self.payload])
        self.assertTrue(decodes)
        self.assertEqual({"schemaVersion": row["schemaVersion"], "object": row["object"], **facts}, row)
        self.assertEqual((row["vertexCount"], row["indexCount"], row["faceCount"], row["edgeCount"],
                          row["edgePointCount"]), (3, 3, 1, 1, 3))
        self.assertEqual(meshes.write(self.key, self.payload), row)
        self.assertEqual(meshes.probe(self.key), row)
        self.assertEqual(meshes.read(self.key, expected_object=row["object"], max_bytes=row["byteLength"]), self.payload)
        self.assertEqual(set(path.name for path in self.store.iterdir()), {"objects", "index"})

    def test_a_body_is_glb_whose_json_does_not_grow_with_its_faces_and_edges(self):
        # The JSON chunk holds the body's identity and where its tables are, not the
        # tables: 30,000 faces and 45,000 edges add nothing to it. 90,000 vertices are
        # past what u16 indexes, so this body's indices are u32, on both sides.
        from tests.python.support.tessellation import js_reader

        faces, edges = 30_000, 45_000
        key = meshes.tessellation_key("2" * 64)
        payload = meshes.encode_payload(
            surface_input="2" * 64, surface_object="b" * 64, chord=meshes.DEFAULT_CHORD, angle=meshes.DEFAULT_ANGLE,
            positions=np.zeros((3 * faces, 3), np.float32), normals=np.zeros((3 * faces, 3), np.float32),
            indices=np.arange(3 * faces, dtype=np.uint32),
            face_ranges=[{"ord": n, "indexStart": 3 * (n - 1), "indexCount": 3} for n in range(1, faces + 1)],
            edges=[(n, "feature", np.zeros((2, 3), np.float32)) for n in range(1, edges + 1)],
            bounds={"min": [0, 0, 0], "max": [0, 0, 0]}, scale=1.0,
        )
        self.assertEqual(payload[:4], b"glTF")
        self.assertLess(struct.unpack_from("<I", payload, 12)[0], 2048)
        self.assertEqual(_json(payload)["accessors"][2]["componentType"], 5125)
        row = meshes.write(key, payload)
        self.assertEqual(meshes.read(key, expected_object=row["object"], max_bytes=row["byteLength"]), payload)
        [[facts, decodes]] = js_reader([payload])
        self.assertTrue(decodes, "the client draws it")
        self.assertEqual(facts["decodedBytes"], row["decodedBytes"], "and admits it at the size cadgen recorded")

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
                             ("surfaceInput", "b" * 64), ("schemaVersion", 1), ("edgePointCount", 1)):
            broken = copy.deepcopy(row)
            broken[field] = value
            write_entry("mesh", self.key, broken)
            self.assertIsNone(meshes.probe(self.key), field)
        entry_path("mesh", self.key).write_bytes(b" " * (meshes.MAX_INDEX_BYTES + 1))
        self.assertIsNone(meshes.probe(self.key))

    def test_adjacent_binary64_quality_and_other_formats_cannot_alias(self):
        import math
        chord = .0015
        other = math.nextafter(chord, math.inf)
        self.assertNotEqual(meshes.tessellation_key("1" * 64, chord), meshes.tessellation_key("1" * 64, other))
        for value in (0, -0.0, -1, math.inf, math.nan, True, "0.0015"):
            with self.assertRaises((ValueError, TypeError)):
                meshes.float64_hex(value)
        self.assertFalse(meshes.valid_key("1" * 64 + "-t2-l1.500000e-3-a3.500000e-1"))
        self.assertFalse(meshes.valid_key(self.key.replace("-p6-", "-p5-")), "a TESS v5 key is another format's")
        self.assertTrue(meshes.obsolete_key(self.key.replace("-p6-", "-p5-")))
        for offset, value in ((0, 0x53534554), (4, 1)):  # a TESS magic; glTF 1
            other_format = bytearray(self.payload)
            other_format[offset:offset + 4] = value.to_bytes(4, "little")
            with self.assertRaises(ValueError):
                meshes.payload_record(self.key, bytes(other_format))

    def test_admitted_batch_is_exact_object_bound_and_byte_bounded(self):
        row = meshes.write(self.key, self.payload)
        request = {"entries": [{"tessellationInput": self.key, "object": row["object"], "maxBytes": row["byteLength"]}]}
        body = json.dumps(request).encode()
        with mock.patch("cadgen.store.tess_cache.TESS_CACHE_BATCH_MAX_BYTES", row["byteLength"] + 16):
            self.assertEqual(int.from_bytes(read_tess_cache_batch(body)[12:16], "little"), row["byteLength"])
        with mock.patch("cadgen.store.tess_cache.TESS_CACHE_BATCH_MAX_BYTES", row["byteLength"] + 12):
            self.assertEqual(read_tess_cache_batch(body), b"TESB" + (1).to_bytes(4, "little") + (1).to_bytes(4, "little") + b"\0" * 4)
        request["entries"][0]["object"] = "f" * 64
        self.assertEqual(int.from_bytes(read_tess_cache_batch(json.dumps(request).encode())[12:16], "little"), 0)
        self.assertIsNone(read_tess_cache_batch(b'{"names":[]}'))
        self.assertIsNone(read_tess_cache_probe(json.dumps({"tessellationInputs": [self.key] * 257}).encode()))

    def test_serving_stored_bodies_never_imports_numpy(self):
        # The CAD Viewer's server probes and batch-reads stored meshes and never views their
        # arrays, so numpy stays out of that process. A fresh interpreter: this one has it.
        row = meshes.write(self.key, self.payload)
        entry = {"tessellationInput": self.key, "object": row["object"], "maxBytes": row["byteLength"]}
        code = (
            f"import json, sys; sys.path.insert(0, {_CADGEN_SRC!r})\n"
            "from cadgen.store.tess_cache import read_tess_cache_batch, read_tess_cache_probe\n"
            f"probed = read_tess_cache_probe({json.dumps({'tessellationInputs': [self.key]}).encode()!r})\n"
            f"batch = read_tess_cache_batch({json.dumps({'entries': [entry]}).encode()!r})\n"
            "print(json.dumps({'probed': len(probed['entries']), 'served': int.from_bytes(batch[12:16], 'little'),"
            " 'numpy': 'numpy' in sys.modules}))\n"
        )
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"probed": 1, "served": len(self.payload), "numpy": False})

    def test_malformed_bodies_are_rejected_in_python_and_shared_js(self):
        cad = ["extras", "cadgen"]
        json_cases = [
            ("bounds object", [*cad, "bounds"], None),
            ("bounds vector", [*cad, "bounds", "min"], [0, 0]),
            ("bounds scalar type", [*cad, "bounds", "min"], [False, 0, 0]),
            ("reversed bounds", [*cad, "bounds", "min"], [4, 0, 0]),
            ("nonfinite JSON", [*cad, "scale"], float("nan")),
            ("infinite scale", [*cad, "scale"], float("inf")),
            ("zero scale", [*cad, "scale"], 0),
            ("string scale", [*cad, "scale"], "1"),
            ("part color", [*cad, "partColor"], [1, 0, 0]),
            ("color scalar", [*cad, "partColor"], [1, 0, 0, True]),
            ("absent part color", [*cad, "partColor"], _DELETE),
            ("palette colour", [*cad, "faceColors"], [[0, 1, 0]]),
            ("class names", [*cad, "edgeClasses"], ["none"]),
            ("face table count", [*cad, "faces", "count"], 2),
            ("face table view", [*cad, "faces", "bufferView"], 4),
            ("no edge table", [*cad, "edges"], _DELETE),
            ("unknown extras field", [*cad, "invented"], 1),
            ("other extras", ["extras", "invented"], {}),
            ("wrong surface version", [*cad, "payloadVersion"], 5),
            ("accessor max", ["accessors", 0, "max"], [2, 3, 1]),
            ("index type", ["accessors", 2, "componentType"], 5125),
            ("index count", ["accessors", 2, "count"], 6),
            ("buffer view offset", ["bufferViews", 3, "byteOffset"], 84),
            ("buffer length", ["buffers", 0, "byteLength"], 4),
            ("node frame", ["nodes", 0, "scale"], [1, 1, 1]),
            ("primitive mode", ["meshes", 0, "primitives", 0, "mode"], 1),
            ("an extension", ["extensionsUsed"], ["KHR_mesh_quantization"]),
        ]
        payloads = []
        for label, path, value in json_cases:
            payload = self.rewritten(path, value)
            with self.subTest(label=label), self.assertRaises(ValueError):
                meshes.payload_record(self.key, payload)
            payloads.append(payload)
        table_cases = [
            ("face ordinal", "cadgen.faces", 0, 0),
            ("face range start", "cadgen.faces", 1, 3),
            ("face partial triangle", "cadgen.faces", 2, 2),
            ("face range short", "cadgen.faces", 2, 0),
            ("face colour past the palette", "cadgen.faces", 3, 2),
            ("edge ordinal", "cadgen.edges", 0, 0),
            ("edge points start", "cadgen.edges", 1, 1),
            ("edge of one point", "cadgen.edges", 2, 1),
            ("edge class past the names", "cadgen.edges", 3, 8),
        ]
        for label, view, word, value in table_cases:
            payload = _with_word(self.payload, view, word, value)
            with self.subTest(label=label), self.assertRaises(ValueError):
                meshes.payload_record(self.key, payload)
            payloads.append(payload)

        from tests.python.support.tessellation import js_reader
        self.assertEqual(js_reader(payloads), [[None, False]] * len(payloads))

        # cadgen's own check, past what a reader asks: no index reaches past the vertices.
        with self.assertRaisesRegex(ValueError, "indices reach past"):
            meshes.payload_record(self.key, _with_word(self.payload, 2, 2, 3, "<H"))

    def test_hash_valid_unrenderable_payload_is_a_miss_and_repairs(self):
        valid = meshes.write(self.key, self.payload)
        payload = self.rewritten(["extras", "cadgen", "edgeClasses"], ["none"])
        broken = copy.deepcopy(valid)
        broken["object"] = put_object(payload)
        self.assertEqual(broken["object"], hashlib.sha256(payload).hexdigest())
        broken["byteLength"] = len(payload)
        write_entry("mesh", self.key, broken)
        self.assertEqual(meshes.probe(self.key), broken, "metadata probe does not open a body")
        self.assertIsNone(meshes.read(self.key, expected_object=broken["object"], max_bytes=len(payload)))
        self.assertEqual(meshes.write(self.key, self.payload), valid)
        self.assertEqual(meshes.read(self.key), self.payload)

    def test_absent_colours_and_undrawn_edges_remain_valid(self):
        from tests.python.support.tessellation import js_reader

        payload = meshes.encode_payload(
            surface_input="1" * 64, surface_object="a" * 64, chord=0.0015, angle=0.005,
            positions=np.array([[0, 0, 0], [2, 0, 0], [0, 3, 0]], np.float32),
            normals=np.array([[0, 0, 1]] * 3, np.float32), indices=np.array([0, 1, 2], np.uint32),
            face_ranges=[{"ord": 1, "indexStart": 0, "indexCount": 3, "color": None}],
            edges=[(1, "none", np.array([[0, 0, 0], [2, 0, 0]], np.float32))],
            bounds={"min": [0, 0, 0], "max": [2, 3, 0]}, scale=1.0, part_color=None,
        )
        decoded = meshes.decode_payload(payload)
        self.assertEqual(decoded.face_ranges(), [{"ord": 1, "color": None, "indexStart": 0, "indexCount": 3}])
        self.assertIsNone(decoded.cad["partColor"])
        self.assertEqual(js_reader([payload])[0][1], True)

    def test_a_body_that_leaves_a_face_out_names_it_for_every_reader(self):
        from tests.python.support.tessellation import js_reader

        def encode(unmeshed, second=0):
            return meshes.encode_payload(
                surface_input="1" * 64, surface_object="a" * 64, chord=0.0015, angle=0.005,
                positions=np.array([[0, 0, 0], [2, 0, 0], [0, 3, 0]], np.float32),
                normals=np.array([[0, 0, 1]] * 3, np.float32), indices=np.array([0, 1, 2], np.uint32),
                face_ranges=[{"ord": 1, "indexStart": 0, "indexCount": 3 - second},
                             {"ord": 2, "indexStart": 3 - second, "indexCount": second}],
                edges=[], bounds={"min": [0, 0, 0], "max": [2, 3, 0]}, scale=1.0, unmeshed_faces=unmeshed,
            )

        payload = encode([2])
        self.assertEqual(meshes.decode_payload(payload).unmeshed_faces, [2])
        self.assertEqual(meshes.unmeshed_faces(payload), [2])
        record = meshes.write(self.key, payload)
        self.assertEqual(record["unmeshedFaceCount"], 1)
        self.assertEqual(meshes.probe(self.key), record)
        self.assertEqual(meshes.stored_unmeshed_faces(self.key), [2])
        [[facts, decodes]] = js_reader([payload])
        self.assertTrue(decodes)
        self.assertEqual({"schemaVersion": record["schemaVersion"], "object": record["object"], **facts}, record)
        # A body that leaves nothing out says nothing: no value, no count.
        whole = encode([])
        self.assertNotIn("unmeshedFaces", _json(whole)["extras"]["cadgen"])
        self.assertNotIn("unmeshedFaceCount", meshes.payload_record(self.key, whole))
        # A named face is one of the table's empty faces, named once, in order.
        for label, value in (("a face with triangles", [1]), ("an empty list", []), ("out of order", [2, 2]),
                             ("not a face", [3]), ("not an ordinal", [0])):
            gltf = _json(payload)
            gltf["extras"]["cadgen"]["unmeshedFaces"] = value
            broken = _with_json(payload, gltf)
            with self.subTest(label=label), self.assertRaises(ValueError):
                meshes.payload_record(self.key, broken)
            self.assertEqual(js_reader([broken]), [[None, False]], label)
        with self.assertRaises(ValueError):
            encode([2], second=3)
        forged = {**record, "unmeshedFaceCount": 0}
        write_entry("mesh", self.key, forged)
        self.assertIsNone(meshes.probe(self.key), "a record counting no unmeshed face is not one")

    def test_the_writer_refuses_a_body_no_reader_would_take(self):
        def encode(**changes):
            arguments = dict(
                surface_input="1" * 64, surface_object="a" * 64, chord=0.0015, angle=0.005,
                positions=np.array([[0, 0, 0], [2, 0, 0], [0, 3, 0]], np.float32),
                normals=np.array([[0, 0, 1]] * 3, np.float32), indices=np.array([0, 1, 2], np.uint32),
                face_ranges=[{"ord": 1, "indexStart": 0, "indexCount": 3}], edges=[],
                bounds={"min": [0, 0, 0], "max": [2, 3, 0]}, scale=1.0,
            )
            return meshes.encode_payload(**{**arguments, **changes})

        encode()
        for label, changes in (
            ("bounds not the positions'", {"bounds": {"min": [0, 0, 0], "max": [2, 3, 1]}}),
            ("normals short", {"normals": np.zeros((2, 3), np.float32)}),
            ("faces short of the triangles", {"face_ranges": [{"ord": 1, "indexStart": 0, "indexCount": 0}]}),
            ("edge of one point", {"edges": [(1, "feature", np.zeros((1, 3), np.float32))]}),
            ("unknown edge class", {"edges": [(1, "invented", np.zeros((2, 3), np.float32))]}),
        ):
            with self.subTest(label=label), self.assertRaises(ValueError):
                encode(**changes)

    def test_recursive_json_damage_is_a_miss_or_clean_validation_failure(self):
        meshes.write(self.key, self.payload)
        entry_path("mesh", self.key).write_bytes(b"[" * 2000 + b"0" + b"]" * 2000)
        self.assertIsNone(meshes.probe(self.key))
        text = b"[" * 2000 + b"0" + b"]" * 2000
        text += b" " * (-len(text) % 4)
        body = struct.pack("<III", 0x46546C67, 2, 20 + len(text)) + struct.pack("<II", len(text), 0x4E4F534A) + text
        with self.assertRaises(ValueError):
            meshes.payload_record(self.key, body)
