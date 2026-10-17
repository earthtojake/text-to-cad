"""cadgen's stored mesh bytes (GLB): the Python codec and the shared JS reader read every body alike."""

from __future__ import annotations

import base64
import json
import struct
import unittest

import numpy as np

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.store import meshes  # noqa: E402

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


class MeshCodecContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.python.support.tessellation import part_fixture
        fixture = part_fixture()
        cls.key = fixture["key"]
        cls.payload = base64.b64decode(fixture["glb"])

    def encode(self, **changes) -> bytes:
        """One triangle naming the fixture's part, with ``changes`` to its arguments."""
        arguments = dict(
            part=self.key, positions=np.array([[0, 0, 0], [2, 0, 0], [0, 3, 0]], np.float32),
            normals=np.array([[0, 0, 1]] * 3, np.float32), indices=np.array([0, 1, 2], np.uint32),
            face_ranges=[{"ord": 1, "indexStart": 0, "indexCount": 3}], edges=[],
            bounds={"min": [0, 0, 0], "max": [2, 3, 0]},
        )
        return meshes.encode_payload(**{**arguments, **changes})

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

    def test_a_body_reads_back_its_part_counts_and_faces(self):
        # That the client reads the same facts off the same body is the part-store
        # contract's (tests/python/global/test_cache_root_sync.py).
        facts = meshes.body_facts(self.payload)
        self.assertEqual(facts["part"], self.key)
        counts = ("vertexCount", "indexCount", "faceCount", "edgeCount", "edgePointCount")
        self.assertEqual([facts[name] for name in counts], [3, 3, 1, 1, 3])
        decoded = meshes.decode_payload(self.payload)
        self.assertEqual(decoded.face_ranges(), [{"ord": 1, "color": [0.2, 0.4, 0.6, 1.0], "indexStart": 0,
                                                  "indexCount": 3}])

    def test_a_body_is_glb_whose_json_does_not_grow_with_its_faces_and_edges(self):
        # The JSON chunk holds the body's part and where its tables are, not the tables:
        # 30,000 faces and 45,000 edges add nothing to it. 90,000 vertices are past what
        # u16 indexes, so this body's indices are u32, on both sides.
        from tests.python.support.tessellation import js_reader

        faces, edges = 30_000, 45_000
        payload = self.encode(
            positions=np.zeros((3 * faces, 3), np.float32), normals=np.zeros((3 * faces, 3), np.float32),
            indices=np.arange(3 * faces, dtype=np.uint32),
            face_ranges=[{"ord": n, "indexStart": 3 * (n - 1), "indexCount": 3} for n in range(1, faces + 1)],
            edges=[(n, "feature", np.zeros((2, 3), np.float32)) for n in range(1, edges + 1)],
            bounds={"min": [0, 0, 0], "max": [0, 0, 0]},
        )
        self.assertEqual(payload[:4], b"glTF")
        self.assertLess(struct.unpack_from("<I", payload, 12)[0], 2048)
        self.assertEqual(_json(payload)["accessors"][2]["componentType"], 5125)
        [[facts, part]] = js_reader([payload])
        self.assertEqual(part, self.key, "the client draws it")
        self.assertEqual(facts["decodedBytes"], meshes.body_facts(payload)["decodedBytes"],
                         "and admits it at the size cadgen records")

    def test_malformed_bodies_are_rejected_in_python_and_shared_js(self):
        cad = ["extras", "cadgen"]
        # The shared JS reader's own suite (packages/core tessellationCache.test.js) makes
        # these damages itself; the ones only this list makes are handed to it below.
        shared_cases = [
            ("no part", [*cad, "part"], _DELETE),
            ("a part key without its version", [*cad, "part"], "1" * 64),
            ("reversed bounds", [*cad, "bounds", "min"], [4, 0, 0]),
            ("palette colour", [*cad, "faceColors"], [[0, 1, 0]]),
            ("class names", [*cad, "edgeClasses"], ["none"]),
            ("face table count", [*cad, "faces", "count"], 2),
            ("no edge table", [*cad, "edges"], _DELETE),
            ("unknown extras field", [*cad, "invented"], 1),
            ("other extras", ["extras", "invented"], {}),
            ("accessor max", ["accessors", 0, "max"], [2, 3, 1]),
            ("index type", ["accessors", 2, "componentType"], 5125),
            ("index count", ["accessors", 2, "count"], 6),
            ("buffer view offset", ["bufferViews", 3, "byteOffset"], 84),
            ("buffer length", ["buffers", 0, "byteLength"], 4),
            ("node frame", ["nodes", 0, "scale"], [1, 1, 1]),
            ("primitive mode", ["meshes", 0, "primitives", 0, "mode"], 1),
            ("an extension", ["extensionsUsed"], ["KHR_mesh_quantization"]),
        ]
        only_here = [
            ("bounds object", [*cad, "bounds"], None),
            ("bounds vector", [*cad, "bounds", "min"], [0, 0]),
            ("bounds scalar type", [*cad, "bounds", "min"], [False, 0, 0]),
            ("nonfinite JSON", [*cad, "bounds", "min"], [float("nan"), 0, 0]),
            ("palette boolean", [*cad, "faceColors"], [[1, 0, 0, True]]),
            ("face table view", [*cad, "faces", "bufferView"], 4),
        ]
        payloads = []
        for cases, to_js in ((shared_cases, False), (only_here, True)):
            for label, path, value in cases:
                payload = self.rewritten(path, value)
                with self.subTest(label=label):
                    with self.assertRaises(ValueError):
                        meshes.body_facts(payload)
                    with self.assertRaises(ValueError):
                        meshes.decode_payload(payload)
                if to_js:
                    payloads.append(payload)
        for label, offset, value in (("a TESS body", 0, 0x53534554), ("glTF 1", 4, 1)):
            other_format = bytearray(self.payload)
            other_format[offset:offset + 4] = value.to_bytes(4, "little")
            with self.subTest(label=label), self.assertRaises(ValueError):
                meshes.body_facts(bytes(other_format))
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
                meshes.decode_payload(payload)

        from tests.python.support.tessellation import js_reader
        self.assertEqual(js_reader(payloads), [[None, None]] * len(payloads))

        # cadgen's own check, past what a reader asks: no index reaches past the vertices.
        with self.assertRaisesRegex(ValueError, "indices reach past"):
            meshes.decode_payload(_with_word(self.payload, 2, 2, 3, "<H"))

    def test_absent_colours_and_undrawn_edges_remain_valid(self):
        from tests.python.support.tessellation import js_reader

        payload = self.encode(face_ranges=[{"ord": 1, "indexStart": 0, "indexCount": 3, "color": None}],
                              edges=[(1, "none", np.array([[0, 0, 0], [2, 0, 0]], np.float32))])
        decoded = meshes.decode_payload(payload)
        self.assertEqual(decoded.face_ranges(), [{"ord": 1, "color": None, "indexStart": 0, "indexCount": 3}])
        self.assertEqual(decoded.cad["faceColors"], [])
        self.assertEqual(js_reader([payload])[0][1], self.key)

    def test_a_body_that_leaves_a_face_out_names_it_for_every_reader(self):
        from tests.python.support.tessellation import js_reader

        def encode(unmeshed, second=0):
            return self.encode(face_ranges=[{"ord": 1, "indexStart": 0, "indexCount": 3 - second},
                                            {"ord": 2, "indexStart": 3 - second, "indexCount": second}],
                               unmeshed_faces=unmeshed)

        payload = encode([2])
        self.assertEqual(meshes.decode_payload(payload).unmeshed_faces, [2])
        self.assertEqual(meshes.unmeshed_faces(payload), [2])
        # The record counts it, and the client reads the same count off the body (the
        # part-store contract, tests/python/global/test_cache_root_sync.py).
        self.assertEqual(meshes.body_facts(payload)["unmeshedFaceCount"], 1)
        # A body that leaves nothing out says nothing: no value, no count.
        whole = encode([])
        self.assertNotIn("unmeshedFaces", _json(whole)["extras"]["cadgen"])
        self.assertNotIn("unmeshedFaceCount", meshes.body_facts(whole))
        # A named face is one of the table's empty faces, named once, in order. The shared
        # reader's own suite makes the other damages; this one is handed to it here.
        broken = {}
        for label, value in (("a face with triangles", [1]), ("an empty list", []), ("out of order", [2, 2]),
                             ("not a face", [3]), ("not an ordinal", [0])):
            gltf = _json(payload)
            gltf["extras"]["cadgen"]["unmeshedFaces"] = value
            broken[label] = _with_json(payload, gltf)
            with self.subTest(label=label), self.assertRaises(ValueError):
                meshes.decode_payload(broken[label])
        self.assertEqual(js_reader([broken["not an ordinal"]]), [[None, None]])
        with self.assertRaises(ValueError):
            encode([2], second=3)

    def test_the_writer_refuses_a_body_no_reader_would_take(self):
        self.encode()
        for label, changes in (
            ("bounds not the positions'", {"bounds": {"min": [0, 0, 0], "max": [2, 3, 1]}}),
            ("normals short", {"normals": np.zeros((2, 3), np.float32)}),
            ("faces short of the triangles", {"face_ranges": [{"ord": 1, "indexStart": 0, "indexCount": 0}]}),
            ("edge of one point", {"edges": [(1, "feature", np.zeros((1, 3), np.float32))]}),
            ("unknown edge class", {"edges": [(1, "invented", np.zeros((2, 3), np.float32))]}),
            ("no part", {"part": "part"}),
        ):
            with self.subTest(label=label), self.assertRaises(ValueError):
                self.encode(**changes)

    def test_recursive_json_damage_is_a_clean_validation_failure(self):
        text = b"[" * 2000 + b"0" + b"]" * 2000
        text += b" " * (-len(text) % 4)
        body = struct.pack("<III", 0x46546C67, 2, 20 + len(text)) + struct.pack("<II", len(text), 0x4E4F534A) + text
        with self.assertRaises(ValueError):
            meshes.body_facts(body)


if __name__ == "__main__":
    unittest.main()
