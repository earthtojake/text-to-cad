"""The mesh writers: stored meshes, placed and coloured, as STL, 3MF and GLB bytes.

Pinned on hand-built cubes, so every number is known: what each format carries
(placements baked in and mirrored safely, colours resolved face > occurrence >
component > part > default, the GLB's Y-up metres, node layout, extras and
finishes, the 3MF's shared vertices and stored zip) and that the same input is
the same bytes. Real geometry runs through the engine in the export suites.
"""

from __future__ import annotations

import io
import json
import struct
import unittest
import xml.etree.ElementTree as ET
import zipfile

import numpy as np

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal.glb_animation import GltfClip, Pivot  # noqa: E402
from cadgen._internal.mesh_formats import (  # noqa: E402
    Tessellation,
    build_primitives,
    decode_tessellation,
    glb_bytes,
    linear_rgb_to_hex,
    stl_bytes,
    threemf_bytes,
)

IDENTITY = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]
# (outward normal, u, v) with u x v = normal, so (0, 1, 2) and (0, 2, 3) wind outward.
FACES = (
    ((1, 0, 0), (0, 1, 0), (0, 0, 1)), ((-1, 0, 0), (0, 0, 1), (0, 1, 0)),
    ((0, 1, 0), (0, 0, 1), (1, 0, 0)), ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
    ((0, 0, 1), (1, 0, 0), (0, 1, 0)), ((0, 0, -1), (0, 1, 0), (1, 0, 0)),
)


def cube(size: float = 10.0, face_colors: dict | None = None, part_color=None) -> Tessellation:
    """A cube centred on the origin, one block of four vertices per face, as OCCT stores one."""
    positions, normals, indices, ranges = [], [], [], []
    for ordinal, (n, u, v) in enumerate(FACES, start=1):
        n, u, v = (np.array(vector, float) for vector in (n, u, v))
        base = len(positions)
        for du, dv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            positions.append((n + du * u + dv * v) * size / 2)
            normals.append(n)
        start = len(indices)
        indices += [base, base + 1, base + 2, base, base + 2, base + 3]
        ranges.append({"ord": ordinal, "color": (face_colors or {}).get(ordinal),
                       "indexStart": start, "indexCount": 6})
    return Tessellation(np.array(positions, np.float32), np.array(normals, np.float32),
                        np.array(indices, np.uint32), ranges, part_color)


def placed(x=0.0, y=0.0, z=0.0, mirror_x=False) -> list[float]:
    matrix = list(IDENTITY)
    matrix[0] = -1.0 if mirror_x else 1.0
    matrix[3], matrix[7], matrix[11] = x, y, z
    return matrix


def occurrence(occurrence_id: str, **fields) -> dict:
    return {"id": occurrence_id, "name": occurrence_id.replace(".", "_"), "component": "c1",
            "transform": IDENTITY, **fields}


def read_glb(data: bytes) -> tuple[dict, bytes]:
    magic, version, total = struct.unpack_from("<III", data)
    assert (magic, version, total) == (0x46546C67, 2, len(data))
    length, kind = struct.unpack_from("<II", data, 12)
    assert kind == 0x4E4F534A and length % 4 == 0
    gltf = json.loads(data[20:20 + length])
    binary_length, binary_kind = struct.unpack_from("<II", data, 20 + length)
    assert binary_kind == 0x004E4942
    return gltf, data[28 + length:28 + length + binary_length]


def accessor(gltf: dict, binary: bytes, index: int) -> np.ndarray:
    entry = gltf["accessors"][index]
    view = gltf["bufferViews"][entry["bufferView"]]
    dtype = {5126: "<f4", 5123: "<u2", 5125: "<u4"}[entry["componentType"]]
    width = {"SCALAR": 1, "VEC3": 3, "VEC4": 4}[entry["type"]]
    return np.frombuffer(binary, dtype, entry["count"] * width, view["byteOffset"] + entry.get("byteOffset", 0))


def read_stl(data: bytes) -> tuple[np.ndarray, np.ndarray]:
    count = struct.unpack_from("<I", data, 80)[0]
    records = np.frombuffer(data, np.dtype([("n", "<f4", 3), ("v", "<f4", 9), ("a", "<u2")]), count, 84)
    assert len(data) == 84 + 50 * count
    return records["n"].astype(np.float64), records["v"].astype(np.float64).reshape(-1, 3, 3)


class Placement(unittest.TestCase):
    def test_every_placement_is_baked_in_and_a_mirror_still_faces_outward(self):
        descriptor = {"components": {"c1": {}}, "occurrences": [
            occurrence("o1.1"),
            occurrence("o1.2", transform=placed(30, 0, 0, mirror_x=True)),
        ]}
        normals, triangles = read_stl(stl_bytes(build_primitives(descriptor, {"c1": cube()}), name="pair"))
        self.assertEqual(24, len(triangles))
        for centre in ((0, 0, 0), (30, 0, 0)):
            mine = np.abs(triangles.mean(axis=1) - centre).max(axis=1) <= 5
            self.assertEqual(12, int(mine.sum()))
            volume = np.einsum("ij,ij->i", triangles[mine, 0], np.cross(triangles[mine, 1], triangles[mine, 2])).sum() / 6
            self.assertAlmostEqual(1000.0, volume, places=3)
            # The stored facet normal is the winding's, and it points away from the cube.
            outward = triangles[mine].mean(axis=1) - centre
            self.assertTrue((np.einsum("ij,ij->i", normals[mine], outward) > 0).all())
            winding = np.cross(triangles[mine, 1] - triangles[mine, 0], triangles[mine, 2] - triangles[mine, 0])
            self.assertTrue((np.einsum("ij,ij->i", normals[mine], winding) > 0).all())

    def test_the_stl_names_the_model_in_a_header_no_reader_mistakes_for_ascii(self):
        data = stl_bytes(build_primitives({"components": {"c1": {}}, "occurrences": [occurrence("o1")]},
                                          {"c1": cube()}), name='bad/name"')
        self.assertEqual(b"cad bad-name-", data[:13])
        self.assertEqual(b"\0" * 67, data[13:80])


class Colour(unittest.TestCase):
    def colours(self, descriptor: dict, tessellation: Tessellation, **options) -> set[str]:
        return {primitive.color for primitive in build_primitives(descriptor, {"c1": tessellation}, **options)}

    def test_each_face_takes_the_first_colour_its_source_defines(self):
        red, half_grey = [1.0, 0.0, 0.0, 1.0], [0.5, 0.5, 0.5, 1.0]
        self.assertEqual("#bcbcbc", linear_rgb_to_hex(half_grey))  # linear in, sRGB out
        components = {"c1": {"color": [0.0, 0.0, 1.0, 1.0]}}
        face_red = cube(face_colors={1: red})
        cases = [
            # The face's own colour beats everything the occurrence says.
            ({"components": components, "occurrences": [occurrence("o1", baseColor="#00FF00", color=half_grey)]},
             face_red, {"#ff0000", "#00ff00"}),
            # A named material's baseColor beats the occurrence's STEP colour.
            ({"components": components, "occurrences": [occurrence("o1", baseColor="#00FF00", color=half_grey)]},
             cube(), {"#00ff00"}),
            ({"components": components, "occurrences": [occurrence("o1", color=half_grey)]}, cube(), {"#bcbcbc"}),
            ({"components": components, "occurrences": [occurrence("o1")]}, cube(), {"#0000ff"}),
            ({"components": {"c1": {}}, "occurrences": [occurrence("o1")]}, cube(part_color=half_grey), {"#bcbcbc"}),
            ({"components": {"c1": {}}, "occurrences": [occurrence("o1")]}, cube(), {"#d4d4d8"}),
        ]
        for descriptor, tessellation, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(expected, self.colours(descriptor, tessellation))
        self.assertEqual({"#123456"}, self.colours({"components": {"c1": {}}, "occurrences": [occurrence("o1")]},
                                                   cube(), default_color="#123456"))

    def test_one_colour_is_one_static_primitive_until_a_finish_tells_them_apart(self):
        two = {"components": {"c1": {}}, "occurrences": [
            occurrence("o1"), occurrence("o2", transform=placed(20))]}
        self.assertEqual(1, len(build_primitives(two, {"c1": cube()})))
        two["occurrences"][1].update(material={"roughness": 0.1, "metalness": 0.9}, materialId="steel",
                                     materialName="Steel")
        primitives = build_primitives(two, {"c1": cube()})
        self.assertEqual(2, len(primitives))
        self.assertEqual([None, {"roughness": 0.1, "metalness": 0.9}], [p.material for p in primitives])


class ThreeMf(unittest.TestCase):
    def test_a_stored_zip_of_one_object_per_primitive_with_its_vertices_shared(self):
        descriptor = {"components": {"c1": {}}, "occurrences": [
            occurrence("o1"), occurrence("o2", transform=placed(20), baseColor="#336699")]}
        archive = zipfile.ZipFile(io.BytesIO(threemf_bytes(build_primitives(descriptor, {"c1": cube()}),
                                                         name="two & cubes")))
        self.assertEqual(["[Content_Types].xml", "_rels/.rels", "3D/3dmodel.model"], archive.namelist())
        for info in archive.infolist():
            self.assertEqual((zipfile.ZIP_STORED, (1980, 1, 1, 0, 0, 0)), (info.compress_type, info.date_time))
        namespace = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
        model = ET.fromstring(archive.read("3D/3dmodel.model"))
        self.assertEqual("millimeter", model.get("unit"))
        self.assertEqual("two & cubes", model.find("m:metadata", namespace).text)
        bases = model.findall("m:resources/m:basematerials/m:base", namespace)
        self.assertEqual(["#336699FF", "#D4D4D8FF"], [base.get("displaycolor") for base in bases])
        objects = model.findall("m:resources/m:object", namespace)
        self.assertEqual(["0", "1"], [obj.get("pindex") for obj in objects])
        for obj in objects:
            # A cube's 24 face-local corners are 8 points: what a slicer welds on.
            self.assertEqual(8, len(obj.findall("m:mesh/m:vertices/m:vertex", namespace)))
            self.assertEqual(12, len(obj.findall("m:mesh/m:triangles/m:triangle", namespace)))
        self.assertEqual(2, len(model.findall("m:build/m:item", namespace)))
        x = sorted({float(vertex.get("x")) for vertex in objects[0].iter(f"{{{namespace['m']}}}vertex")})
        self.assertEqual([15.0, 25.0], x)


class Glb(unittest.TestCase):
    def test_a_static_file_is_y_up_metres_one_node_per_primitive_declaring_its_space(self):
        descriptor = {"components": {"c1": {}}, "occurrences": [
            occurrence("o1", transform=placed(0, 30, 40)),
            occurrence("o2", baseColor="#FF8000", material={"roughness": 0.2, "metalness": 1.0, "clearcoat": 0.5,
                                                            "clearcoatRoughness": 0.1}, color=[1, 1, 1, 0.5])]}
        gltf, binary = read_glb(glb_bytes(build_primitives(descriptor, {"c1": cube()}), name="part"))
        self.assertNotIn("extensionsRequired", gltf)
        self.assertEqual(["KHR_materials_clearcoat"], gltf["extensionsUsed"])
        self.assertEqual(2, len(gltf["nodes"]))
        for index, node in enumerate(gltf["nodes"]):
            self.assertEqual("part", node["name"])
            self.assertEqual({"cadOccurrenceId": f"step:{index}", "cadSourceKind": "step", "cadUnits": "m",
                              "cadUpAxis": "y"}, node["extras"])
            self.assertNotIn("translation", node)
        # Primitives sort by colour: the plain default grey, then the coated orange.
        plain, coated = gltf["materials"]
        self.assertEqual("BLEND", coated["alphaMode"])
        self.assertEqual(0.5, coated["pbrMetallicRoughness"]["baseColorFactor"][3])
        self.assertEqual({"clearcoatFactor": 0.5, "clearcoatRoughnessFactor": 0.1},
                         coated["extensions"]["KHR_materials_clearcoat"])
        self.assertEqual((0.42, 0.03), (plain["pbrMetallicRoughness"]["roughnessFactor"],
                                        plain["pbrMetallicRoughness"]["metallicFactor"]))
        self.assertTrue(all(material["extras"] == {"cadSourceColor": True} for material in gltf["materials"]))
        red, green, blue, _alpha = plain["pbrMetallicRoughness"]["baseColorFactor"]
        self.assertAlmostEqual(((212 / 255 + 0.055) / 1.055) ** 2.4, red, places=6)
        # CAD (x, y, z) mm -> glTF (x, z, -y) m: the cube placed at y=30, z=40 mm.
        position = gltf["meshes"][0]["primitives"][0]["attributes"]["POSITION"]
        self.assertEqual([-0.005, 0.035, -0.035], [round(v, 6) for v in gltf["accessors"][position]["min"]])
        self.assertEqual([0.005, 0.045, -0.025], [round(v, 6) for v in gltf["accessors"][position]["max"]])
        indices = gltf["meshes"][0]["primitives"][0]["indices"]
        self.assertEqual(5123, gltf["accessors"][indices]["componentType"])
        self.assertTrue((accessor(gltf, binary, indices) < 24).all())

    def test_an_animated_file_turns_its_parts_about_a_pivot_node_pair(self):
        descriptor = {"components": {"c1": {}}, "occurrences": [occurrence("o1.1"), occurrence("o1.2")]}
        primitives = build_primitives(descriptor, {"c1": cube()}, per_occurrence=True)
        half = [0.0, 0.3826834, 0.0, 0.9238795]
        rate = [0.0, 0.25, 0.0, -0.5]
        pivot = Pivot(members=("o1.2",), times=[0.0, 0.5, 1.0], translations=[0.01, 0.0, 0.0] * 3,
                      rotations=[0.0, 0.0, 0.0, 1.0, *half, 0.0, 0.7071068, 0.0, 0.7071068],
                      child_translation=[-0.01, 0.0, 0.0], translations_in=[0.0] * 9, translations_out=[0.0] * 9,
                      rotations_in=rate * 3, rotations_out=[0.0] * 12)
        gltf, binary = read_glb(glb_bytes(primitives, name="part", animation=GltfClip("turn", 1.0, pivots=[pivot])))
        nodes = gltf["nodes"]
        self.assertEqual(["o1_1", "o1_2", "pivot 0 offset", "pivot 0"], [node["name"] for node in nodes])
        self.assertEqual(["o1.1", "o1.2"], [node["extras"]["cadOccurrenceId"] for node in nodes[:2]])
        # The part sits under the -pivot node, which sits under the pivot at its rest pose.
        self.assertEqual(([1], [-0.01, 0.0, 0.0]), (nodes[2]["children"], nodes[2]["translation"]))
        self.assertEqual(([2], [0.01, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0]),
                         (nodes[3]["children"], nodes[3]["translation"], nodes[3]["rotation"]))
        self.assertEqual([0, 3], gltf["scenes"][0]["nodes"])
        (clip,) = gltf["animations"]
        self.assertEqual("turn", clip["name"])
        self.assertEqual([{"node": 3, "path": "translation"}, {"node": 3, "path": "rotation"}],
                         [channel["target"] for channel in clip["channels"]])
        rotation = clip["samplers"][clip["channels"][1]["sampler"]]
        self.assertEqual("CUBICSPLINE", rotation["interpolation"])
        times = gltf["accessors"][rotation["input"]]
        self.assertEqual(([0.0], [1.0], 3), (times["min"], times["max"], times["count"]))
        # Each key's in-tangent, value and out-tangent in turn.
        self.assertEqual(("VEC4", 9), (gltf["accessors"][rotation["output"]]["type"],
                                       gltf["accessors"][rotation["output"]]["count"]))
        output = accessor(gltf, binary, rotation["output"]).reshape(3, 3, 4)
        np.testing.assert_allclose(half, output[1, 1], atol=1e-6)
        np.testing.assert_allclose(rate, output[1, 0], atol=1e-6)
        np.testing.assert_allclose([0.0] * 4, output[1, 2])

    def test_a_pivot_carrying_a_part_the_file_does_not_hold_is_refused(self):
        primitives = build_primitives({"components": {"c1": {}}, "occurrences": [occurrence("o1")]},
                                      {"c1": cube()}, per_occurrence=True)
        pivot = Pivot(members=("o9",), times=[0.0, 1.0], translations=[0.0] * 6, rotations=[0.0, 0.0, 0.0, 1.0] * 2,
                      child_translation=[0.0, 0.0, 0.0], translations_in=[0.0] * 6, translations_out=[0.0] * 6,
                      rotations_in=[0.0] * 8, rotations_out=[0.0] * 8)
        with self.assertRaisesRegex(ValueError, "carries 'o9', which no primitive declared"):
            glb_bytes(primitives, animation=GltfClip("x", 1.0, pivots=[pivot]))


class Determinism(unittest.TestCase):
    def test_the_same_meshes_are_the_same_bytes_in_every_format(self):
        descriptor = {"components": {"c1": {"color": [0.2, 0.4, 0.6, 1.0]}}, "occurrences": [
            occurrence("o1", transform=placed(1.5, -2.25, 3.125, mirror_x=True)), occurrence("o2")]}

        def write_all():
            primitives = build_primitives(descriptor, {"c1": cube(7.3, face_colors={2: [0.9, 0.1, 0.3, 1.0]})})
            return stl_bytes(primitives, name="d"), threemf_bytes(primitives, name="d"), glb_bytes(primitives, name="d")

        self.assertEqual(write_all(), write_all())

    def test_a_stored_body_decodes_to_the_arrays_it_was_written_from(self):
        from cadgen.store.meshes import encode_payload

        source = cube(face_colors={3: [0.1, 0.2, 0.3, 1.0]})
        payload = encode_payload(
            surface_input="a" * 64, surface_object="b" * 64, chord=0.0015, angle=0.35,
            positions=source.positions, normals=source.normals, indices=source.indices,
            face_ranges=source.face_ranges, edges=[], bounds={"min": [-5.0] * 3, "max": [5.0] * 3},
            scale=17.3, part_color=[1, 0, 0, 1],
        )
        decoded = decode_tessellation(payload)
        np.testing.assert_array_equal(source.positions, decoded.positions)
        np.testing.assert_array_equal(source.normals, decoded.normals)
        np.testing.assert_array_equal(source.indices, decoded.indices)
        self.assertEqual(decoded.indices.dtype, np.uint32, "the body's u16 indices are widened for the writers")
        self.assertEqual(source.face_ranges, decoded.face_ranges)
        self.assertEqual([1, 0, 0, 1], decoded.part_color)


if __name__ == "__main__":
    unittest.main()
