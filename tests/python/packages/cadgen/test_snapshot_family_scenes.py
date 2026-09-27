"""`cadgen snapshot` draws a GLB, a mesh and a robot with the scene the CAD Viewer draws.

The snapshot CLI and the viewer build a GLB's, an STL's, a 3MF's and a robot's scene with
ONE builder per family (the viewer's renderer and the snapshot page call the same module).
These render real snapshots through the real headless runtime and read the PIXELS back,
for the things a second, flattened path got wrong and the shared builder gets right:

* a skinned and morphed GLB is drawn deformed at rest, where the GPU draws it, and the
  still is framed on that shape (the flattened copy was the straight, unskinned bar);
* Render keeps a GLB's authored finish, while Solid wears the viewer's surface over it;
* a robot description's colour wins over the colours its link mesh brings;
* an SRDF opens at its `home` group state, exactly as the viewer opens it;
* one decode drawn by two jobs, and one job drawn twice, come out the same.

Every fixture is written here, in a fresh workspace: no corpus model is read.
One browser, one packet: a `--job` file renders every case in a single run.
"""

from __future__ import annotations

import json
import math
import struct
import unittest
from pathlib import Path

from tests.python.support.cad_test_roots import ClassCadRoots
from tests.python.support.paths import add_repo_path
from tests.python.support.png import PngImage, read_png

add_repo_path("packages/cadgen/src")

SIZE = (360, 270)

# --- fixture writers ---------------------------------------------------------------------


def glb_bytes(document: dict, chunks: list[bytes]) -> bytes:
    """A binary glTF from its JSON and its buffer chunks (each padded to 4 bytes)."""
    body = b""
    views = []
    for chunk in chunks:
        views.append({"buffer": 0, "byteOffset": len(body), "byteLength": len(chunk)})
        body += chunk + b"\0" * (-len(chunk) % 4)
    document = {**document, "bufferViews": views, "buffers": [{"byteLength": len(body)}]}
    encoded = json.dumps(document).encode("utf-8")
    encoded += b" " * (-len(encoded) % 4)
    total = 12 + 8 + len(encoded) + 8 + len(body)
    return (struct.pack("<III", 0x46546C67, 2, total) + struct.pack("<II", len(encoded), 0x4E4F534A) + encoded
            + struct.pack("<II", len(body), 0x004E4942) + body)


def floats(values) -> bytes:
    return struct.pack(f"<{len(values)}f", *values)


def vec3_accessor(view: int, values: list[float]) -> dict:
    axes = [values[axis::3] for axis in range(3)]
    return {"bufferView": view, "componentType": 5126, "count": len(values) // 3, "type": "VEC3",
            "min": [min(axis) for axis in axes], "max": [max(axis) for axis in axes]}


RING = [(-0.1, -0.1), (0.1, -0.1), (0.1, 0.1), (-0.1, 0.1)]


def bar_indices() -> list[int]:
    indices = []
    for ring in range(2):
        for side in range(4):
            a, b = ring * 4 + side, ring * 4 + (side + 1) % 4
            indices += [a, b, b + 4, a, b + 4, a + 4]
    return indices + [0, 2, 1, 0, 3, 2, 8, 9, 10, 8, 10, 11]


def bar_glb(*, deformed: bool = False, baked: bool = False) -> bytes:
    """A square bar two units tall (glTF, Y up).

    `deformed`: its top ring is skinned to a joint that RESTS turned 90 degrees about Z
    from where it was bound, and a morph target weighted 1 by default pulls its bottom
    ring down half a unit: drawn as three draws it, an L. `baked`: that L written as a
    plain mesh. Neither: the straight bar, which is what a GLB flattened into mesh data
    without its skin and morph looked like.
    """
    positions = [coordinate for level in (0, 1, 2) for x, z in RING for coordinate in (x, level, z)]
    if baked:
        for vertex in range(12):
            x, y, z = positions[vertex * 3: vertex * 3 + 3]
            if vertex >= 8:  # the tip ring, turned about (0, 1, 0)
                x, y = -(y - 1), 1 + x
            elif vertex < 4:  # the morphed bottom ring
                y -= 0.5
            positions[vertex * 3: vertex * 3 + 3] = [x, y, z]
    indices = bar_indices()
    chunks = [floats(positions), struct.pack(f"<{len(indices)}H", *indices)]
    primitive = {"attributes": {"POSITION": 0}, "indices": 1, "material": 0}
    accessors = [vec3_accessor(0, positions), {"bufferView": 1, "componentType": 5123, "count": len(indices), "type": "SCALAR"}]
    mesh = {"name": "bar", "primitives": [primitive]}
    nodes = [{"name": "bar", "mesh": 0}]
    document = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": nodes, "meshes": [mesh],
                "materials": [{"pbrMetallicRoughness": {"baseColorFactor": [0.18, 0.5, 0.82, 1], "metallicFactor": 0,
                                                        "roughnessFactor": 0.6}, "extras": {"cadSourceColor": True}}],
                "accessors": accessors}
    if deformed:
        deltas = [-0.5 if index < 12 and index % 3 == 1 else 0.0 for index in range(36)]
        chunks.append(floats(deltas))
        accessors.append(vec3_accessor(2, deltas))
        primitive["targets"] = [{"POSITION": 2}]
        mesh["weights"] = [1]
        joints = [joint for vertex in range(12) for joint in ((1 if vertex >= 8 else 0), 0, 0, 0)]
        chunks.append(struct.pack(f"<{len(joints)}B", *joints))
        accessors.append({"bufferView": 3, "componentType": 5121, "count": 12, "type": "VEC4"})
        chunks.append(floats([1.0, 0, 0, 0] * 12))
        accessors.append({"bufferView": 4, "componentType": 5126, "count": 12, "type": "VEC4"})
        chunks.append(floats([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, -1, 0, 1]))
        accessors.append({"bufferView": 5, "componentType": 5126, "count": 2, "type": "MAT4"})
        primitive["attributes"].update({"JOINTS_0": 3, "WEIGHTS_0": 4})
        nodes[0]["skin"] = 0
        nodes += [{"name": "root_joint", "children": [2]},
                  {"name": "tip_joint", "translation": [0, 1, 0], "rotation": [0, 0, math.sqrt(0.5), math.sqrt(0.5)]}]
        document["scenes"][0]["nodes"].append(1)
        document["skins"] = [{"joints": [1, 2], "inverseBindMatrices": 5, "skeleton": 1}]
    return glb_bytes(document, chunks)


def box_triangles(x0, y0, z0, size) -> list[list[float]]:
    x1, y1, z1 = x0 + size, y0 + size, z0 + size
    corners = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    faces = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4), (2, 3, 7), (2, 7, 6), (1, 2, 6), (1, 6, 5), (3, 0, 4), (3, 4, 7)]
    return [[coordinate for corner in face for coordinate in corners[corner]] for face in faces]


def face_normals(triangles: list[list[float]]) -> list[float]:
    normals = []
    for t in triangles:
        u = [t[3 + axis] - t[axis] for axis in range(3)]
        v = [t[6 + axis] - t[axis] for axis in range(3)]
        n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
        length = math.sqrt(sum(value * value for value in n))
        normals += [value / length for value in n] * 3
    return normals


def box_glb(*, color, metallic: float, roughness: float) -> bytes:
    """One box (glTF units) with an authored PBR finish."""
    triangles = box_triangles(-0.5, -0.5, -0.5, 1)
    positions = [coordinate for triangle in triangles for coordinate in triangle]
    return glb_bytes({
        "asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "box", "mesh": 0, "extras": {"cadOccurrenceId": "o1.1"}}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1}, "material": 0}]}],
        "materials": [{"pbrMetallicRoughness": {"baseColorFactor": [*color, 1], "metallicFactor": metallic,
                                                "roughnessFactor": roughness}, "extras": {"cadSourceColor": True}}],
        "accessors": [vec3_accessor(0, positions), vec3_accessor(1, face_normals(triangles))],
    }, [floats(positions), floats(face_normals(triangles))])


def stl_bytes() -> bytes:
    triangles = box_triangles(0, 0, 0, 10) + box_triangles(20, 0, 0, 5)
    body = b"".join(struct.pack("<3f", 0, 0, 0) + floats(triangle) + b"\0\0" for triangle in triangles)
    return b"\0" * 80 + struct.pack("<I", len(triangles)) + body


def box_visual(size, xyz, rgba=None) -> str:
    material = f'<material name="m{rgba.replace(" ", "")}"><color rgba="{rgba}"/></material>' if rgba else ""
    return f'<visual><origin xyz="{xyz}"/><geometry><box size="{size}"/></geometry>{material}</visual>'


ARM_URDF = f"""<?xml version="1.0"?>
<robot name="arm">
  <link name="base">{box_visual("0.4 0.4 0.1", "0 0 0.05", "0.3 0.3 0.35 1")}</link>
  <link name="upper_arm">{box_visual("0.6 0.08 0.08", "0.3 0 0", "0.9 0.5 0.1 1")}</link>
  <joint name="shoulder" type="revolute"><parent link="base"/><child link="upper_arm"/><origin xyz="0 0 0.2"/>
    <axis xyz="0 1 0"/><limit lower="-1.5708" upper="1.5708" effort="1" velocity="1"/></joint>
</robot>
"""
ARM_SRDF = """<?xml version="1.0"?>
<robot name="arm">
  <group name="arm"><joint name="shoulder"/></group>
  <group_state name="home" group="arm"><joint name="shoulder" value="-0.9"/></group_state>
</robot>
"""
# A link whose mesh brings its own RED and whose description says GREEN.
PAINTED_URDF = f"""<?xml version="1.0"?>
<robot name="painted">
  <link name="base"><visual><geometry><mesh filename="red_box.glb" scale="0.001 0.001 0.001"/></geometry>
    <material name="green"><color rgba="0.1 0.8 0.1 1"/></material></visual></link>
</robot>
"""

# --- pixel helpers -------------------------------------------------------------------------


def near(pixel, other, tolerance=10) -> bool:
    return sum(abs(a - b) for a, b in zip(pixel, other)) <= tolerance


def model_pixels(image: PngImage) -> list[tuple[int, int, int]]:
    """Every pixel that is not the backdrop around the corners (a gradient, so matched loosely)."""
    corners = [image.pixel(0, 0), image.pixel(image.width - 1, 0), image.pixel(0, image.height - 1), image.pixel(image.width - 1, image.height - 1)]
    return [image.pixel(x, y) for y in range(image.height) for x in range(image.width)
            if not any(near(image.pixel(x, y), corner, 24) for corner in corners)]


def ink_box(image: PngImage) -> tuple[int, int, int, int]:
    corners = [image.pixel(0, 0), image.pixel(image.width - 1, image.height - 1)]
    xs, ys = [], []
    for y in range(image.height):
        for x in range(image.width):
            if not any(near(image.pixel(x, y), corner, 24) for corner in corners):
                xs.append(x)
                ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def aspect(image: PngImage) -> float:
    left, top, right, bottom = ink_box(image)
    return (right - left + 1) / (bottom - top + 1)


def mean(pixels) -> tuple[float, float, float]:
    return tuple(sum(pixel[channel] for pixel in pixels) / len(pixels) for channel in range(3))


class SnapshotFamilySceneTests(unittest.TestCase):
    """One browser launch; every case is a job in the same packet."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._roots = ClassCadRoots(prefix="snapshot-family-scenes-")
        workspace = cls._roots.cad_root
        (workspace / "deformed.glb").write_bytes(bar_glb(deformed=True))
        (workspace / "baked.glb").write_bytes(bar_glb(baked=True))
        (workspace / "straight.glb").write_bytes(bar_glb())
        (workspace / "mirror.glb").write_bytes(box_glb(color=(0.95, 0.95, 0.95), metallic=1, roughness=0.05))
        (workspace / "matte.glb").write_bytes(box_glb(color=(0.95, 0.95, 0.95), metallic=0, roughness=1))
        (workspace / "part.stl").write_bytes(stl_bytes())
        (workspace / "arm.urdf").write_text(ARM_URDF, encoding="utf-8")
        (workspace / "arm.srdf").write_text(ARM_SRDF, encoding="utf-8")
        (workspace / "painted.urdf").write_text(PAINTED_URDF, encoding="utf-8")
        (workspace / "red_box.glb").write_bytes(box_glb(color=(0.85, 0.05, 0.05), metallic=0, roughness=0.6))

        # No guides: a silhouette is then everything that is not the backdrop.
        plain = {"grid": {"enabled": False}, "axes": {"enabled": False}}

        def job(name: str, source: str, display=None, camera="iso", **extra):
            return {"input": source, "display": {"mode": "solid", **plain, **(display or {})}, **extra,
                    "outputs": [{"path": f"{name}.png", "width": SIZE[0], "height": SIZE[1], "camera": camera}]}

        # Radians to degrees exactly as the viewer converts an SRDF state (x * 180 / pi), so the
        # two routes to the same pose are the same numbers.
        home_degrees = -0.9 * 180 / math.pi
        jobs = [
            job("deformed", "deformed.glb", camera="front"),
            job("baked", "baked.glb", camera="front"),
            job("straight", "straight.glb", camera="front"),
            job("mirror-solid", "mirror.glb"),
            job("matte-solid", "matte.glb"),
            job("mirror-render", "mirror.glb", {"mode": "render"}),
            job("matte-render", "matte.glb", {"mode": "render"}),
            job("painted", "painted.urdf"),
            job("srdf", "arm.srdf"),
            job("urdf-home", "arm.urdf", jointValues={"shoulder": home_degrees}),
            job("urdf-rest", "arm.urdf"),
            job("stl-first", "part.stl"),
            job("stl-again", "part.stl"),
            {"input": "part.stl", "display": {"mode": "solid", **plain}, "outputs": [
                {"path": "stl-front.png", "width": SIZE[0], "height": SIZE[1], "camera": "front"},
                {"path": "stl-top.png", "width": SIZE[0], "height": SIZE[1], "camera": "top"}]},
        ]
        packet = workspace / "packet.json"
        packet.write_text(json.dumps({"jobs": jobs}), encoding="utf-8")

        from cadgen.cli.snapshot import snapshot

        cls.result = snapshot(job=packet)
        cls.names = sorted(Path(file.path).name for file in cls.result.files)
        cls.bytes = {name: (workspace / name).read_bytes() for name in cls.names}
        cls.images = {name[:-4]: read_png(data) for name, data in cls.bytes.items()}
        cls.listing = snapshot(target=workspace / "mirror.glb", mode="list")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._roots.cleanup()

    def test_every_output_was_written_at_its_size(self) -> None:
        self.assertTrue(self.result.ok)
        self.assertEqual(15, len(self.names), self.names)
        for name, image in self.images.items():
            with self.subTest(output=name):
                self.assertEqual(SIZE, (image.width, image.height))
                self.assertTrue(model_pixels(image), f"{name} drew nothing")

    def test_a_skinned_and_morphed_glb_is_drawn_deformed_and_framed_on_what_is_drawn(self) -> None:
        # Seen from the front the L is 1.1 wide and 1.6 tall; the straight bar 0.2 by 2.
        deformed, baked, straight = (aspect(self.images[name]) for name in ("deformed", "baked", "straight"))
        self.assertAlmostEqual(deformed, baked, delta=0.03, msg="drawn where its skin and morph put it")
        self.assertAlmostEqual(deformed, 1.1 / 1.6, delta=0.05)
        self.assertLess(straight, 0.2, "the flattened copy's straight, unskinned bar is a different picture")

    def test_render_keeps_a_glb_s_authored_finish_and_solid_wears_the_viewer_s(self) -> None:
        self.assertEqual(self.bytes["mirror-solid.png"], self.bytes["matte-solid.png"],
                         "Inspect replaces how a surface answers light, and keeps only its colour")
        mirror, matte = (mean(model_pixels(self.images[name])) for name in ("mirror-render", "matte-render"))
        self.assertGreater(sum(abs(a - b) for a, b in zip(mirror, matte)), 60,
                           f"Render shows the finish the file authored: mirror {mirror}, matte {matte}")

    def test_a_robot_description_s_colour_wins_over_its_link_mesh_s_own(self) -> None:
        pixels = model_pixels(self.images["painted"])
        green = sum(1 for r, g, b in pixels if g > r + 40)
        red = sum(1 for r, g, b in pixels if r > g + 40)
        self.assertGreater(green, 200, f"green {green}, red {red}")
        self.assertEqual(0, red, "the mesh's own red never shows through the description's green")

    def test_an_srdf_opens_at_its_home_state_as_the_viewer_opens_it(self) -> None:
        self.assertEqual(self.bytes["srdf.png"], self.bytes["urdf-home.png"])
        self.assertNotEqual(self.bytes["srdf.png"], self.bytes["urdf-rest.png"])

    def test_one_decode_drawn_twice_and_one_scene_from_two_cameras(self) -> None:
        self.assertEqual(self.bytes["stl-first.png"], self.bytes["stl-again.png"])
        self.assertNotEqual(self.bytes["stl-front.png"], self.bytes["stl-top.png"])

    def test_list_mode_lists_what_the_scene_drew(self) -> None:
        self.assertEqual([("#o1.1", "box", 12)], [(part["ref"], part["name"], part["triangleCount"]) for part in self.listing.parts])


if __name__ == "__main__":
    unittest.main()
