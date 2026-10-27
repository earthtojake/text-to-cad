"""The files no document that the stills draw (`engine/formats`, `render/drawing.py`): each kind read
into what a renderer holds -- a mesh file's parts, colours, materials and placements; a GLB's node
tree and textures through OCCT's glTF reader; a robot posed by the viewer's forward kinematics; a
DXF's pens and curves -- and each drawn as its golden picture.

The fixtures are made here, small: a binary and an ASCII STL, a 3MF of colour groups, base
materials and components, a GLB of a node tree, two materials and a base colour texture, a URDF
of every joint kind (a mimic and a four-bar among them), an SRDF and an SDF over it, a DXF of
lines, arcs, bulges, a block, a solid and a hatch.

`formats_golden/kinematics.json` is the viewer's own forward kinematics on `KINEMATICS`: each
link's world transform (row-major, metres) at three poses, made by origin/main's
`@text-to-cad/core` `lib/urdf/parseUrdf.js` and `kinematics.js` (with jsdom's DOMParser) when the
port was written; the port must agree to 1e-9.

The pictures (`formats_golden/*.png`, 320x240, macOS) match as `test_render.py`'s do: at most 1.5%
of the pixels more than 32 levels from every golden pixel within one pixel. Where a platform's
OpenGL draws a row apart past that bound, the row has a golden of the platform's own (`formats_golden/<platform>/<row>.png`),
held to the same bound. A row missed in CI prints the picture it drew (`GOLDEN <platform>/<row>`,
base64), which is that platform's golden once a person has looked at it. A test that draws makes
an OpenGL context and is skipped, saying why, where none can be made (on CI with a display, fails). A deliberate change to the
look makes them again: `CADGEN_RENDER_GOLDENS=write`.
"""

from __future__ import annotations

import io
import json
import math
import os
import shutil
import struct
import tempfile
import textwrap
import unittest
import zipfile
from pathlib import Path

import numpy as np

from cadgen.engine import formats
from cadgen.engine.formats.buffer import buffer, feature_edges
from cadgen.engine.render import context
from cadgen.engine.snapshot import SnapshotRefused, Still, parse_display, snapshot
from tests.python.support import opengl

GOLDEN = Path(__file__).resolve().parent / "formats_golden"
PLATFORM = context.platform()
WRITE = os.environ.get("CADGEN_RENDER_GOLDENS") == "write"
SIZE = (320, 240)

KINEMATICS = """<?xml version="1.0"?>
<robot name="kinematics" xmlns:tcad="https://text-to-cad.dev/urdf">
  <link name="base"><visual><origin xyz="0 0 0.01"/><geometry><box size="0.3 0.2 0.02"/></geometry></visual></link>
  <link name="turret"><visual><origin xyz="0 0 0.03"/><geometry><cylinder radius="0.04" length="0.06"/></geometry></visual></link>
  <link name="arm"><visual><origin xyz="0.06 0 0" rpy="0 1.5707963 0"/><geometry><cylinder radius="0.012" length="0.12"/></geometry></visual></link>
  <link name="slider"><visual><geometry><box size="0.03 0.03 0.03"/></geometry></visual></link>
  <link name="twin"><visual><origin xyz="0 0.02 0"/><geometry><box size="0.01 0.04 0.01"/></geometry></visual></link>
  <link name="tool"><visual><geometry><sphere radius="0.01"/></geometry></visual></link>
  <link name="ground"><visual><origin xyz="0.1 0 -0.01"/><geometry><box size="0.26 0.02 0.01"/></geometry></visual></link>
  <link name="rocker"><visual><origin xyz="0.04 0 0"/><geometry><box size="0.08 0.015 0.01"/></geometry></visual></link>
  <link name="crank"><visual><origin xyz="0.025 0 0"/><geometry><box size="0.05 0.015 0.01"/></geometry></visual></link>
  <joint name="spin" type="continuous"><parent link="base"/><child link="turret"/><origin xyz="0.05 -0.02 0.02" rpy="0 0 0.3"/><axis xyz="0 0 1"/></joint>
  <joint name="lift" type="revolute"><parent link="turret"/><child link="arm"/><origin xyz="0 0 0.06" rpy="0.2 -0.1 0"/><axis xyz="0 1 0.2"/><limit lower="-1.2" upper="1.4" effort="1" velocity="1"/></joint>
  <joint name="reach" type="prismatic"><parent link="arm"/><child link="slider"/><origin xyz="0.12 0 0" rpy="0 0 0.5"/><axis xyz="1 0 0"/><limit lower="-0.02" upper="0.05" effort="1" velocity="1"/></joint>
  <joint name="mirror" type="revolute"><parent link="arm"/><child link="twin"/><origin xyz="0.08 0 0.015"/><axis xyz="1 0 0"/><limit lower="-1" upper="1" effort="1" velocity="1"/><mimic joint="lift" multiplier="-0.5" offset="0.1"/></joint>
  <joint name="mount" type="fixed"><parent link="slider"/><child link="tool"/><origin xyz="0.02 0.01 0" rpy="0.4 0 0.2"/></joint>
  <joint name="foot" type="fixed"><parent link="base"/><child link="ground"/><origin xyz="-0.12 0.06 0.02" rpy="0 0 -0.4"/></joint>
  <joint name="output_joint" type="revolute"><parent link="ground"/><child link="rocker"/><origin xyz="0.2 0 0" rpy="0 0 1.5707963267948966"/><axis xyz="0 0 1"/><limit lower="-0.5" upper="0.5" effort="1" velocity="1"/></joint>
  <joint name="input_joint" type="revolute"><parent link="ground"/><child link="crank"/><origin xyz="0 0 0" rpy="0 0 1.5253680280265103"/><axis xyz="0 0 1"/><limit lower="-1.5" upper="1.5" effort="1" velocity="1"/>
    <tcad:four_bar driver="output_joint" input_length="0.05" ground_length="0.2" output_length="0.08" coupler_length="0.2" input_zero="1.5253680280265103" output_zero="1.5707963267948966"/>
  </joint>
</robot>
"""

# A 0.26 m two-link arm standing on z = 0: a 0.2 x 0.2 x 0.04 m base and a 0.03 x 0.03 x 0.22 m arm on a
# shoulder at 0.04 m. The viewer draws it in its metres (``ROBOT_SCENE_UNITS``); the stills in millimetres.
ARM = ('<robot name="arm"><link name="base"><visual><origin xyz="0 0 0.02"/><geometry><box size="0.2 0.2 0.04"/>'
       '</geometry></visual></link><link name="arm"><visual><origin xyz="0 0 0.11"/><geometry>'
       '<box size="0.03 0.03 0.22"/></geometry></visual></link><joint name="shoulder" type="revolute">'
       '<parent link="base"/><child link="arm"/><origin xyz="0 0 0.04"/><axis xyz="0 1 0"/>'
       '<limit lower="-1" upper="1" effort="1" velocity="1"/></joint></robot>')

SRDF = """<?xml version="1.0"?>
<robot name="kinematics">
  <group name="arm"><joint name="spin"/><joint name="lift"/><joint name="reach"/></group>
  <group_state name="home" group="arm"><joint name="spin" value="0.5"/><joint name="lift" value="0.3"/></group_state>
  <group_state name="tucked" group="arm"><joint name="lift" value="-1.0"/><joint name="reach" value="-0.02"/></group_state>
</robot>
"""

# A link at 1 m along x and 0.5 m up, its frame turned 90 degrees about z, relative_to a frame of
# the model; a hinge whose pose is its child's and whose axis is expressed in the model's frame.
SDF = """<?xml version="1.0"?>
<sdf version="1.9">
  <model name="hinge">
    <frame name="shelf"><pose>1 0 0.5 0 0 0</pose></frame>
    <link name="post"><visual name="v"><geometry><box><size>0.1 0.1 0.1</size></box></geometry></visual></link>
    <link name="door"><pose relative_to="shelf">0 0 0 0 0 1.5707963267948966</pose>
      <visual name="v"><pose>0.2 0 0 0 0 0</pose><geometry><box><size>0.4 0.02 0.3</size></box></geometry>
        <material><diffuse>0.8 0.2 0.1 1</diffuse></material></visual></link>
    <joint name="swing" type="revolute"><parent>post</parent><child>door</child>
      <axis><xyz expressed_in="__model__">0 0 1</xyz><limit><lower>-2</lower><upper>2</upper></limit></axis></joint>
  </model>
</sdf>
"""

DXF = """0
SECTION
2
TABLES
0
TABLE
2
LAYER
0
LAYER
2
CUT
62
7
0
LAYER
2
BEND
62
1
0
LAYER
2
HIDDEN
62
-3
0
ENDTAB
0
ENDSEC
0
SECTION
2
BLOCKS
0
BLOCK
2
TAB
10
0
20
0
0
LINE
8
0
10
0
20
0
11
6
21
3
0
ENDBLK
0
ENDSEC
0
SECTION
2
ENTITIES
0
LWPOLYLINE
8
CUT
90
4
70
1
10
0
20
0
10
80
20
0
42
0.5
10
80
20
40
10
0
20
40
0
CIRCLE
8
CUT
10
20
20
20
40
8
0
ARC
8
CUT
10
55
20
20
40
10
50
180
51
360
0
LINE
8
BEND
10
40
20
2
11
40
21
38
0
LINE
8
HIDDEN
10
0
20
50
11
80
21
50
0
SOLID
8
CUT
62
5
10
5
20
30
11
15
21
30
12
5
22
35
13
15
23
35
0
INSERT
8
CUT
2
TAB
10
60
20
32
50
90
0
TEXT
8
CUT
10
0
20
-5
40
3
1
NOTE
0
ENDSEC
0
EOF
"""


def gl() -> None:
    """Skip, saying why, where no OpenGL context can be made (on CI with a display, fail)."""
    opengl.require(context.available())


def pixels(data: bytes) -> np.ndarray:
    from PIL import Image

    with Image.open(io.BytesIO(data)) as image:
        return np.asarray(image.convert("RGB")).astype(np.int16)


def mismatch(found: np.ndarray, golden: np.ndarray) -> float:
    if found.shape != golden.shape:
        return 1.0
    height, width = golden.shape[:2]
    padded = np.pad(golden, ((1, 1), (1, 1), (0, 0)), mode="edge")
    best = np.full((height, width), 255, np.int16)
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            best = np.minimum(best, np.abs(found - padded[dy:dy + height, dx:dx + width]).max(-1))
    return float((best > 32).mean())


# --- fixtures --------------------------------------------------------------------------------


def box_soup(size: tuple[float, float, float], at: tuple[float, float, float] = (0, 0, 0)) -> np.ndarray:
    """A box as twelve triangles (M, 3, 3), wound outward."""
    corners = np.array([[x, y, z] for x in (0, 1) for y in (0, 1) for z in (0, 1)], float) - 0.5
    corners = corners * np.array(size) + np.array(at)
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    return np.array([[corners[a], corners[b], corners[c]] for a, b, c, d in faces for a, b, c in ((a, b, c), (a, c, d))])


def cylinder_soup(radius: float, height: float, segments: int = 24, at: tuple = (0, 0, 0)) -> np.ndarray:
    turn = np.linspace(0, 2 * math.pi, segments + 1)
    ring = np.stack([radius * np.cos(turn), radius * np.sin(turn)], 1)
    triangles = []
    for (x0, y0), (x1, y1) in zip(ring[:-1], ring[1:]):
        triangles += [[(x0, y0, 0), (x1, y1, 0), (x1, y1, height)], [(x0, y0, 0), (x1, y1, height), (x0, y0, height)],
                      [(0, 0, height), (x0, y0, height), (x1, y1, height)], [(0, 0, 0), (x1, y1, 0), (x0, y0, 0)]]
    return np.array(triangles, float) + np.array(at)


def write_stl(path: Path, triangles: np.ndarray, *, ascii_: bool = False) -> Path:
    if ascii_:
        rows = ["solid fixture"]
        for triangle in triangles:
            rows += ["facet normal 0 0 0", " outer loop", *(f"  vertex {float(x)!r} {float(y)!r} {float(z)!r}" for x, y, z in triangle),
                     " endloop", "endfacet"]
        path.write_text("\n".join(rows + ["endsolid fixture"]) + "\n", encoding="ascii")
        return path
    facets = np.zeros(len(triangles), [("normal", "<f4", 3), ("corners", "<f4", (3, 3)), ("attribute", "<u2")])
    facets["corners"] = triangles
    path.write_bytes(b"\0" * 80 + struct.pack("<I", len(triangles)) + facets.tobytes())
    return path


def write_3mf(path: Path) -> Path:
    """A plate whose top is painted by a colour group, a peg placed twice by a components object,
    a generated default base material (no colour), metallic display properties; in centimetres."""
    plate = box_soup((6, 4, 0.5), (0, 0, 0.25))
    peg = cylinder_soup(0.5, 1.5, 16)

    def mesh(triangles: np.ndarray, paints: list[str]) -> str:
        points, index = [], {}
        rows = []
        for triangle, paint in zip(triangles, paints):
            ids = []
            for point in map(tuple, triangle):
                if point not in index:
                    index[point] = len(points)
                    points.append(point)
                ids.append(index[point])
            rows.append(f'<triangle v1="{ids[0]}" v2="{ids[1]}" v3="{ids[2]}"{paint}/>')
        return ("<mesh><vertices>" + "".join(f'<vertex x="{x}" y="{y}" z="{z}"/>' for x, y, z in points)
                + "</vertices><triangles>" + "".join(rows) + "</triangles></mesh>")

    top = [' pid="5" p1="1"' if (triangle[:, 2] > 0.4).all() else "" for triangle in plate]
    model = f"""<?xml version="1.0" encoding="UTF-8"?>
<model unit="centimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
       xmlns:m="http://schemas.microsoft.com/3dmanufacturing/material/2015/02">
 <resources>
  <m:pbmetallicdisplayproperties id="4"><m:pbmetallic name="steel" metallicness="1" roughness="0.3"/>
   <m:pbmetallic name="default" metallicness="0" roughness="1"/></m:pbmetallicdisplayproperties>
  <basematerials id="1" m:displaypropertiesid="4"><base name="steel" displaycolor="#8899AA"/><base name="default" displaycolor="#FAFAFB"/></basematerials>
  <m:colorgroup id="5"><m:color color="#20A040FF"/><m:color color="#E03020"/></m:colorgroup>
  <object id="2" type="model" name="plate" pid="1" pindex="1">{mesh(plate, top)}</object>
  <object id="3" type="model" name="peg" pid="1" pindex="0">{mesh(peg, [''] * len(peg))}</object>
  <object id="6" type="model" name="pegs"><components>
   <component objectid="3" transform="1 0 0 0 1 0 0 0 1 -2 0 0.5"/><component objectid="3" transform="1 0 0 0 1 0 0 0 1 2 0 0.5"/>
  </components></object>
 </resources>
 <build><item objectid="2"/><item objectid="6" transform="1 0 0 0 1 0 0 0 1 0 0.5 0"/></build>
</model>"""
    with zipfile.ZipFile(path, "w") as package:
        package.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        package.writestr("_rels/.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                         '<Relationship Target="/3D/3dmodel.model" Id="r0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
        package.writestr("3D/3dmodel.model", model)
    return path


def write_glb(path: Path) -> Path:
    """A node tree (``rig``, turned 45 degrees about glTF's z, holding ``box`` and ``plate``), a cube
    with a base colour texture (a checker with a yellow band along its top rows), a red plate."""
    from PIL import Image

    def cube(size: float) -> tuple:
        h = size / 2
        quads = [((1, 0, 0), [(h, -h, -h), (h, h, -h), (h, h, h), (h, -h, h)]),
                 ((-1, 0, 0), [(-h, h, -h), (-h, -h, -h), (-h, -h, h), (-h, h, h)]),
                 ((0, 1, 0), [(h, h, -h), (-h, h, -h), (-h, h, h), (h, h, h)]),
                 ((0, -1, 0), [(-h, -h, -h), (h, -h, -h), (h, -h, h), (-h, -h, h)]),
                 ((0, 0, 1), [(-h, -h, h), (h, -h, h), (h, h, h), (-h, h, h)]),
                 ((0, 0, -1), [(-h, h, -h), (h, h, -h), (h, -h, -h), (-h, -h, -h)])]
        position, normal, uv, index = [], [], [], []
        for direction, quad in quads:
            base = len(position)
            position += quad
            normal += [direction] * 4
            uv += [(0, 1), (1, 1), (1, 0), (0, 0)]
            index += [base, base + 1, base + 2, base, base + 2, base + 3]
        return (np.array(position, "f4"), np.array(normal, "f4"), np.array(uv, "f4"), np.array(index, "u2"))

    plate = cube(1.0)
    plate = (plate[0] * np.array([0.12, 0.08, 0.01], "f4"),) + plate[1:]
    texture = np.zeros((64, 64, 3), np.uint8)
    ys, xs = np.mgrid[0:64, 0:64]
    texture[((xs // 16 + ys // 16) % 2).astype(bool)] = (230, 90, 40)
    texture[~((xs // 16 + ys // 16) % 2).astype(bool)] = (40, 110, 220)
    texture[:8] = (250, 220, 60)
    picture = io.BytesIO()
    Image.fromarray(texture).save(picture, "PNG")
    blob, views, accessors = bytearray(), [], []

    def view(data: bytes, target: int | None = None) -> int:
        while len(blob) % 4:
            blob.append(0)
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data), **({"target": target} if target else {})})
        blob.extend(data)
        return len(views) - 1

    def accessor(array: np.ndarray, kind: str, component: int, target: int) -> int:
        found = {"bufferView": view(array.tobytes(), target), "componentType": component, "count": len(array), "type": kind}
        if kind == "VEC3":
            found.update(min=array.min(0).tolist(), max=array.max(0).tolist())
        accessors.append(found)
        return len(accessors) - 1

    meshes = []
    for name, (position, normal, uv, index), material in (("box", cube(0.04), 0), ("plate", plate, 1)):
        attributes = {"POSITION": accessor(position, "VEC3", 5126, 34962), "NORMAL": accessor(normal, "VEC3", 5126, 34962),
                      "TEXCOORD_0": accessor(uv, "VEC2", 5126, 34962)}
        meshes.append({"name": name, "primitives": [{"attributes": attributes, "material": material,
                                                     "indices": accessor(index, "SCALAR", 5123, 34963)}]})
    image = view(picture.getvalue())
    gltf = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
            "nodes": [{"name": "rig", "children": [1, 2], "rotation": [0, 0, 0.3826834, 0.9238795]},
                      {"name": "box", "mesh": 0, "translation": [0, 0, 0.025]},
                      {"name": "plate", "mesh": 1, "translation": [0, 0, -0.005]}],
            "meshes": meshes, "accessors": accessors, "bufferViews": views,
            "materials": [{"name": "checker", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}, "metallicFactor": 0,
                                                                      "roughnessFactor": 0.6}},
                          {"name": "red", "pbrMetallicRoughness": {"baseColorFactor": [0.8, 0.1, 0.1, 1], "metallicFactor": 0,
                                                                  "roughnessFactor": 0.5},
                           "extensions": {"KHR_materials_clearcoat": {"clearcoatFactor": 1, "clearcoatRoughnessFactor": 0.1}}}],
            "textures": [{"source": 0}], "images": [{"bufferView": image, "mimeType": "image/png"}],
            "buffers": [{"byteLength": 0}]}
    while len(blob) % 4:
        blob.append(0)
    gltf["buffers"][0]["byteLength"] = len(blob)
    text = json.dumps(gltf).encode()
    text += b" " * (-len(text) % 4)
    body = struct.pack("<II", len(text), 0x4E4F534A) + text + struct.pack("<II", len(blob), 0x004E4942) + bytes(blob)
    path.write_bytes(struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body)
    return path


class FixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.folder = Path(tempfile.mkdtemp(prefix="engine-formats-")).resolve()

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.folder, ignore_errors=True)


# --- buffers, STL, 3MF -------------------------------------------------------------------------


class BufferTest(unittest.TestCase):
    def test_a_box_s_edges_are_its_twelve_folds_and_a_cylinder_has_no_seam(self) -> None:
        triangles = box_soup((2, 3, 4))
        segments, kinds = feature_edges(triangles.reshape(-1, 3), np.arange(36).reshape(-1, 3))
        self.assertEqual((len(segments), set(kinds.tolist())), (12, {1}))
        cylinder = cylinder_soup(5, 10)
        segments, _kinds = feature_edges(cylinder.reshape(-1, 3), np.arange(len(cylinder) * 3).reshape(-1, 3))
        self.assertEqual(len(segments), 48, "two rims of 24 segments: 15-degree facets fold under 16")
        open_fan = cylinder[3::4][:6]  # six bottom triangles: a fan with an open rim
        segments, kinds = feature_edges(open_fan.reshape(-1, 3), np.arange(18).reshape(-1, 3))
        self.assertEqual(sorted(set(kinds.tolist())), [5], "an open fan's rim and its two sides are boundaries")

    def test_no_normal_drawn_is_of_no_length(self) -> None:
        """A triangle of no area is not drawn, and a given normal of no length is its vertex's
        triangles' own: one zero normal is enough for OCCT to draw none of the face it is in."""
        soup = np.concatenate([box_soup((2, 3, 4)), np.array([[[0, 0, 0], [1, 1, 1], [2, 2, 2]]], float)])
        mesh, _uv = buffer(soup.reshape(-1, 3), np.arange(len(soup) * 3).reshape(-1, 3))
        self.assertEqual(mesh.triangles, 12)
        self.assertGreater(float(np.linalg.norm(mesh.normals, axis=1).min()), 0.99)
        flat = box_soup((2, 3, 4)).reshape(-1, 3)
        given = np.tile([0.0, 0.0, 1.0], (len(flat), 1))
        given[5] = 0.0
        mesh, _uv = buffer(flat, np.arange(len(flat)).reshape(-1, 3), normals=given)
        self.assertGreater(float(np.linalg.norm(mesh.normals, axis=1).min()), 0.99)

    def test_many_corners_in_one_cell_fall_back_to_flat_normals(self) -> None:
        """A mesh whose corners pile into one hash cell must not make the crease pass allocate the
        square of the group size; past the pair budget it draws flat (per-face) normals instead."""
        from cadgen.engine.formats.buffer import CREASE_PAIRS_MAX, _unit_normals, creased_normals

        clustered = np.random.default_rng(0).uniform(1e-4, 9e-3, (1200, 3, 3))  # all corners in one 1e-2 cell
        group = len(clustered) * 3
        self.assertGreater(group * group, CREASE_PAIRS_MAX, "the fixture must exceed the pair budget")
        normals = creased_normals(clustered)
        self.assertEqual(normals.shape, (group, 3))
        flat = np.repeat(_unit_normals(clustered), 3, axis=0)
        self.assertTrue(np.array_equal(normals, flat), "over the budget the crease is dropped for flat normals")
        spread = np.array([[[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[10, 0, 0], [11, 0, 0], [10, 1, 0]]], float)
        self.assertEqual(creased_normals(spread).shape, (6, 3))  # a small spread mesh still creases

    def test_normals_crease_at_thirty_degrees_and_a_dense_mesh_is_flat(self) -> None:
        cylinder = cylinder_soup(5, 10, segments=24)
        mesh, _uv = buffer(cylinder.reshape(-1, 3), np.arange(len(cylinder) * 3).reshape(-1, 3))
        side = mesh.normals.reshape(-1, 3, 3)[0::4]  # each side quad's first triangle
        self.assertTrue(np.allclose(side[:, :, 2], 0, atol=1e-6), "the side's normals stay level")
        self.assertGreater(np.abs(side[:, 0] - side[:, 1]).max(), 0.1, "smoothed round the side, not flat")
        caps = mesh.normals.reshape(-1, 3, 3)[2::4]
        self.assertTrue(np.allclose(caps[:, :, 2], 1, atol=1e-6), "the cap's corners keep the cap's normal")
        dense = np.concatenate([box_soup((1, 1, 1), (2 * at, 0, 0)) for at in range(900)])  # 10,800 triangles
        mesh, _uv = buffer(dense.reshape(-1, 3), np.arange(len(dense) * 3).reshape(-1, 3))
        flat = mesh.normals.reshape(-1, 3, 3)
        self.assertTrue(np.allclose(flat[:, 0], flat[:, 1]) and np.allclose(flat[:, 0], flat[:, 2]))


class GlbWholeFromItselfTest(unittest.TestCase):
    """The OCCT GLB reader refuses a file that names a buffer or image outside itself."""

    def test_an_embedded_buffer_passes_and_an_external_uri_is_refused(self) -> None:
        from cadgen.engine.formats import FormatError
        from cadgen.engine.formats.glb import _whole_from_itself

        _whole_from_itself(Path("m.glb"), {"buffers": [{"byteLength": 36}]})  # embedded BIN chunk: no uri
        _whole_from_itself(Path("m.glb"), {"buffers": [{"uri": "data:application/octet-stream;base64,AAAA"}]})
        for item in ({"buffers": [{"uri": "../outside.bin"}]},
                     {"buffers": [{"uri": "side.bin"}]},
                     {"images": [{"uri": "/etc/hosts"}]},
                     {"buffers": [{"uri": "data:text/plain,not-base64"}]}):
            with self.assertRaisesRegex(FormatError, "outside the GLB"):
                _whole_from_itself(Path("m.glb"), item)


class MeshFileTest(FixtureTest):
    def test_an_stl_reads_alike_binary_or_ascii_as_one_part_in_the_fill(self) -> None:
        triangles = np.concatenate([box_soup((20, 10, 4)), cylinder_soup(3, 12, at=(0, 0, 2))])
        binary = formats.read(write_stl(self.folder / "part.stl", triangles))
        text = formats.read(write_stl(self.folder / "text.stl", triangles, ascii_=True))
        self.assertEqual(binary.structure["kind"], "stl")
        self.assertEqual(binary.buffers.keys().__len__(), 1)
        self.assertEqual([p["color"] for p in binary.structure["prototypes"]], [None])
        from cadgen.engine.mesh import Mesh

        first, second = (Mesh.from_bytes(next(iter(found.buffers.values()))) for found in (binary, text))
        np.testing.assert_allclose(first.positions, second.positions, atol=1e-5)  # a binary STL's floats are 32-bit
        self.assertEqual((first.triangles, len(first.edges)), (second.triangles, len(second.edges)))
        self.assertEqual(binary.structure["tree"], {"name": "part", "prototype": 0, "instance": 0})
        (self.folder / "empty.stl").write_bytes(b"\0" * 80 + struct.pack("<I", 0))
        with self.assertRaisesRegex(formats.FormatError, "no triangles"):
            formats.read(self.folder / "empty.stl")

    def test_a_3mf_places_its_objects_in_millimetres_with_their_colours(self) -> None:
        found = formats.read(write_3mf(self.folder / "kit.3mf"))
        structure = found.structure
        self.assertEqual([p["name"] for p in structure["prototypes"]], ["plate", "peg"])
        plate, peg = structure["prototypes"]
        self.assertIsNone(plate["color"], "the generated default base material is no colour")
        linear = [round(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4, 6) for c in (0xE0 / 255, 0x30 / 255, 0x20 / 255)]
        self.assertEqual(list(plate["faceColors"].values()), [[*linear, 1.0]], "the top's colour group, linear")
        self.assertEqual(peg["material"]["pbr"]["values"]["metalness"], 1, "the steel base material's display properties")
        self.assertAlmostEqual(peg["color"][0], 0.246201, places=5)
        matrices = [np.array(instance["matrix"]).reshape(4, 4).T for instance in structure["instances"]]
        self.assertEqual([tuple(m[:3, 3]) for m in matrices], [(0, 0, 0), (-20, 5, 5), (20, 5, 5)], "centimetres")
        self.assertEqual([instance["palette"] for instance in structure["instances"]], [0, 1, 2])
        self.assertEqual(structure["tree"]["children"][1]["name"], "Object 2")
        from cadgen.engine.mesh import Mesh

        mesh = Mesh.from_bytes(found.buffers[plate["key"]])
        self.assertAlmostEqual(float(np.ptp(mesh.positions[:, 0])), 60.0, places=4)


# --- GLB -------------------------------------------------------------------------------------------


class GlbTest(FixtureTest):
    def test_a_glb_is_read_by_occt_with_its_tree_materials_and_texture(self) -> None:
        found = formats.read(write_glb(self.folder / "rig.glb"))
        structure = found.structure
        self.assertEqual(structure["tree"]["name"], "rig")
        self.assertEqual([child["name"] for child in structure["tree"]["children"]], ["box", "plate"])
        box, plate = structure["prototypes"]
        checker = next(iter(box["faceMaterials"].values()))
        red = next(iter(plate["faceMaterials"].values()))
        self.assertEqual((checker["material"]["name"], checker["pbr"]["values"]["roughness"]), ("checker", 0.6))
        self.assertEqual((red["material"]["name"], plate["faceColors"]["1"][:3],
                          red["pbr"]["values"]["clearcoat"], red["pbr"]["values"]["clearcoatRoughness"]),
                         ("red", [0.8, 0.1, 0.1], 1.0, 0.1))
        textured = found.shapes[box["key"]]
        self.assertEqual(len(textured.textures), 1, "the checker's base colour texture, by its paint")
        self.assertNotIn(plate["key"], found.shapes, "an untextured part is made as a document's is")
        # glTF's y up and metres as z up and millimetres: the box 40 mm, its centre 25 mm along glTF z (-y).
        matrix = np.array(structure["instances"][0]["matrix"]).reshape(4, 4).T
        self.assertTrue(np.allclose(matrix[:3, :3] @ matrix[:3, :3].T, np.eye(3), atol=1e-9), "a rigid placement")
        from cadgen.engine.mesh import Mesh

        positions = Mesh.from_bytes(found.buffers[box["key"]]).positions @ matrix[:3, :3].T + matrix[:3, 3]
        np.testing.assert_allclose(np.ptp(positions, 0).max(), 40 * math.sqrt(2), atol=1e-3)
        np.testing.assert_allclose(positions.mean(0), (0, -25, 0), atol=1e-3)

    def test_a_packet_s_camera_for_a_glb_is_in_the_millimetres_the_viewer_draws(self) -> None:
        """The viewer draws glTF's metres as millimetres, so a Quick Edit packet's camera for a GLB is in
        millimetres already (``millimetresPerSceneUnit`` 1, though ``clip.at`` is in the file's metres): the
        viewer's front view of the rig, its half height the preset's, replayed through ``--job`` is the
        preset ``front``'s picture."""
        from cadgen.engine.snapshot import draw_pictures, job_pictures

        gl()
        path = write_glb(self.folder / "rig.glb")
        # From the front the rig is the plate's 120 x 80 mm footprint turned 45 degrees -- 100 sqrt(2) mm across
        # and tall, about the origin -- with the box inside it, which the preset frames over 92 % of the height.
        half = 100 * math.sqrt(2) / (2 * 0.92)
        camera = {"position": [0, -500, 0], "target": [0, 0, 0], "up": [0, 0, 1], "orthographicHalfHeight": half}
        pictures = {}
        for name, view in (("front", {"camera": "front", "output": {"transparent": True}}),
                           ("viewer", {"camera": camera, "output": {"transparent": True, "padding": 0, "tightFrame": False}})):
            out = self.folder / f"glb_{name}.png"
            draw_pictures(job_pictures({"input": str(path), "jobs": [
                {**view, "outputs": [{"path": str(out), "width": 240, "height": 180}]}]}), daemon=False)
            pictures[name] = pixels(out.read_bytes())
        self.assertLessEqual(mismatch(pictures["viewer"], pictures["front"]), 0.002, "a GLB's camera in millimetres, as the viewer's")


# --- robots ----------------------------------------------------------------------------------------


class RobotTest(FixtureTest):
    def test_the_forward_kinematics_are_the_viewer_s(self) -> None:
        from cadgen.engine.formats.robot import read_urdf

        path = self.folder / "kinematics.urdf"
        path.write_text(KINEMATICS, encoding="utf-8")
        robot = read_urdf(path)
        for row in json.loads((GOLDEN / "kinematics.json").read_text(encoding="utf-8")):
            values, _named = robot.values(row["values"])
            placed = robot.placements(values)
            for link, matrix in row["links"].items():
                with self.subTest(pose=row["values"], link=link):
                    mine = placed[link].copy()
                    mine[:3, 3] /= 1000
                    np.testing.assert_allclose(mine, np.array(matrix).reshape(4, 4), atol=1e-9)

    def test_a_pose_is_refused_by_name_and_an_srdf_opens_at_home(self) -> None:
        (self.folder / "kinematics.urdf").write_text(KINEMATICS, encoding="utf-8")
        (self.folder / "kinematics.srdf").write_text(SRDF, encoding="utf-8")
        found = formats.read(self.folder / "kinematics.urdf")
        for pose, why in (({"elbow": 3}, "no joint 'elbow'"), ({"mirror": 3}, "'mirror' follows 'lift'"),
                          ({"input_joint": 3}, "follows its driver 'output_joint'"), ({"lift": 200}, "past its limits"),
                          ({"foot": 1}, "is fixed"), ("home", "no group state")):
            with self.subTest(pose=pose), self.assertRaisesRegex(ValueError, why):
                found.pose(found.structure, pose)
        srdf = formats.read(self.folder / "kinematics.srdf")
        posed = srdf.pose(srdf.structure, "tucked")
        self.assertEqual(posed["kinematics"]["pose"]["configuration"], "arm/tucked")
        self.assertAlmostEqual(posed["kinematics"]["pose"]["values"]["spin"], math.degrees(0.5), msg="home under the state")
        self.assertAlmostEqual(posed["kinematics"]["pose"]["values"]["lift"], math.degrees(-1.0))
        self.assertNotEqual(srdf.structure["instances"][1]["matrix"], found.structure["instances"][1]["matrix"],
                            "the SRDF opens at its home state")

    def test_an_sdf_places_its_links_by_their_frames(self) -> None:
        path = self.folder / "hinge.sdf"
        path.write_text(SDF, encoding="utf-8")
        found = formats.read(path)
        door = np.array(found.structure["instances"][1]["matrix"]).reshape(4, 4).T
        np.testing.assert_allclose(door[:3, 3], (1000, 200, 500), atol=1e-6)  # its visual 0.2 m along the door's turned x
        self.assertAlmostEqual(found.structure["prototypes"][1]["name"], "box")
        swung = found.pose(found.structure, {"swing": 90})
        door = np.array(swung["instances"][1]["matrix"]).reshape(4, 4).T
        np.testing.assert_allclose(door[:3, 3], (800, 0, 500), atol=1e-6)  # turned about z through the joint: the door's frame

    def test_a_robot_job_leaves_out_the_visuals_its_view_hid(self) -> None:
        """A robot's view says what it hid as the viewer's visual ids (``selection.hide``: ``arm:v1``); each
        instance carries its visual's id, so a job drawn with the arm hidden is the robot without its arm."""
        from cadgen.engine.snapshot import draw_pictures, hidden_instances, job_pictures

        base = '<link name="base"><visual><geometry><box size="0.2 0.2 0.05"/></geometry></visual></link>'
        arm = ('<link name="arm"><visual><origin xyz="0 0 0.15"/><geometry><box size="0.04 0.04 0.3"/></geometry></visual>'
               '</link><joint name="shoulder" type="revolute"><parent link="base"/><child link="arm"/>'
               '<axis xyz="0 1 0"/><limit lower="-1" upper="1" effort="1" velocity="1"/></joint>')
        whole, alone = self.folder / "two_links.urdf", self.folder / "base_alone.urdf"
        whole.write_text(f'<robot name="r">{base}{arm}</robot>', encoding="utf-8")
        alone.write_text(f'<robot name="r">{base}</robot>', encoding="utf-8")
        structure = formats.read(whole).structure
        self.assertEqual([instance["visual"] for instance in structure["instances"]], ["base:v1", "arm:v1"])
        self.assertEqual(hidden_instances(structure, {"hidden": ["arm:v1"]}, whole.name), {1})
        with self.assertRaisesRegex(SnapshotRefused, "arm:v2"):
            hidden_instances(structure, {"hidden": ["arm:v2"]}, whole.name)
        gl()
        outputs = {name: self.folder / f"robot_{name}.png" for name in ("hidden", "alone")}
        job = {"camera": "iso", "jointValues": {"shoulder": 30}, "outputs": [{"path": str(outputs["hidden"]),
                                                                              "width": 240, "height": 180}]}
        packet = {"input": str(whole), "jobs": [{**job, "selection": {"hide": ["arm:v1"]}}]}
        draw_pictures(job_pictures(packet), daemon=False)
        draw_pictures(job_pictures({"input": str(alone), "jobs": [{**job, "jointValues": None, "outputs": [
            {"path": str(outputs["alone"]), "width": 240, "height": 180}]}]}), daemon=False)
        self.assertLessEqual(mismatch(pixels(outputs["hidden"].read_bytes()), pixels(outputs["alone"].read_bytes())), 0.001)

    def test_a_clip_at_the_robot_s_mid_height_in_metres_keeps_its_lower_half(self) -> None:
        """``display.clip.at`` is in the robot's metres, as the viewer reads it, though the stills draw the
        robot in millimetres: a plane at mid-height keeps the lower half of the robot, from ``--display`` and
        from a Quick Edit packet's view replayed through ``--job`` alike."""
        from cadgen.engine.snapshot import draw_pictures, job_pictures

        gl()
        path = self.folder / "arm.urdf"
        path.write_text(ARM, encoding="utf-8")
        clip = {"enabled": True, "axis": "z", "at": 0.13}  # the viewer's number: metres, mid-height

        def rows(picture: Path) -> tuple[int, int]:
            from PIL import Image

            with Image.open(picture) as image:
                alpha = np.asarray(image.convert("RGBA"))[..., 3]
            hit = np.flatnonzero((alpha > 0).any(1))
            return int(hit[0]), int(hit[-1])

        def job(name: str, display: dict, transparent: bool) -> Path:
            out = self.folder / f"{name}.png"
            packet = {"input": str(path), "jobs": [{"camera": "front", "display": display,
                                                     "output": {"transparent": transparent},
                                                     "outputs": [{"path": str(out), "width": 240, "height": 180}]}]}
            draw_pictures(job_pictures(packet), daemon=False)
            return out

        whole, cut = rows(job("whole", {}, True)), rows(job("cut", {"clip": clip}, True))
        self.assertEqual(whole[1], cut[1], "the base stands where it stood")
        self.assertAlmostEqual((cut[1] - cut[0] + 1) / (whole[1] - whole[0] + 1), 0.5, delta=0.02,
                               msg="the plane at 0.13 m keeps the lower half of the 0.26 m robot")
        direct = self.folder / "direct.png"
        snapshot(path, direct, display={"clip": clip}, camera="front", size=(240, 180), daemon=False)
        replayed = job("replayed", {"clip": clip}, False)
        self.assertLessEqual(mismatch(pixels(direct.read_bytes()), pixels(replayed.read_bytes())), 0.001)

    def test_a_packet_s_camera_and_measurement_in_metres_draw_the_viewer_s_front_view(self) -> None:
        """A Quick Edit packet's camera and Measure's points are in the viewer's scene coordinates -- a
        robot's metres -- though the stills draw the robot in millimetres: the viewer's front view of the
        0.26 m arm, its half height the preset's, replayed through ``--job`` is the preset ``front``'s
        picture; the same numbers in millimetres are read as metres and leave a speck; and a dimension from
        the shoulder to the arm's top is drawn between those two heights, beside the arm."""
        from PIL import Image

        from cadgen.engine.snapshot import draw_pictures, job_pictures

        gl()
        path = self.folder / "arm.urdf"
        path.write_text(ARM, encoding="utf-8")
        half = 0.13 / 0.92  # the preset's frame: the 0.26 m arm over 92 % of the height (PADDING 0.04 a side)
        camera = {"position": [0, -1, 0.13], "target": [0, 0, 0.13], "up": [0, 0, 1], "orthographicHalfHeight": half}
        dimension = [{"start": [0, 0, 0.04], "end": [0, 0, 0.26], "label": "0.22 m", "color": "#ff2d55"}]

        def job(name: str, camera, exact: bool, **fields) -> np.ndarray:
            out = self.folder / f"camera_{name}.png"
            output = {"transparent": True, **({"padding": 0, "tightFrame": False} if exact else {})}
            view = {"camera": camera, "output": output, "outputs": [{"path": str(out), "width": 480, "height": 360}], **fields}
            draw_pictures(job_pictures({"input": str(path), "jobs": [view]}), daemon=False)
            with Image.open(out) as image:
                return np.asarray(image.convert("RGBA")).astype(np.int16)

        def rows(picture: np.ndarray) -> tuple[int, int]:
            hit = np.flatnonzero((picture[..., 3] > 0).any(1))
            return (int(hit[0]), int(hit[-1])) if hit.size else (0, 0)

        front, viewer = job("front", "front", False), job("viewer", camera, True)
        self.assertLessEqual(mismatch(viewer[..., :3], front[..., :3]), 0.002, "the viewer's camera, in metres, is the front view")
        speck = job("millimetres", {**camera, "position": [0, -1000, 130], "target": [0, 0, 130],
                                    "orthographicHalfHeight": half * 1000}, True)
        self.assertLess(rows(speck)[1] - rows(speck)[0], 4, "the same numbers in millimetres are read as metres")
        self.assertGreater(mismatch(speck[..., :3], front[..., :3]), 0.05)
        measured = job("measured", camera, True, measurements=dimension)
        ink = (np.abs(measured[..., :3] - viewer[..., :3]).max(-1) > 16) | (np.abs(measured[..., 3] - viewer[..., 3]) > 16)
        ink_rows, ink_cols = np.flatnonzero(ink.any(1)), np.flatnonzero(ink.any(0))
        per_mm = 360 / (2 * half * 1000)
        top, shoulder = 180 - (260 - 130) * per_mm, 180 + (130 - 40) * per_mm  # the ends' rows
        self.assertTrue(abs(ink_rows[0] - top) < 5 and abs(ink_rows[-1] - shoulder) < 5,
                        f"the dimension spans rows {ink_rows[0]}-{ink_rows[-1]}, not {top:.0f}-{shoulder:.0f}")
        self.assertTrue(234 <= ink_cols[0] and ink_cols[-1] <= 270, f"beside the arm, columns {ink_cols[0]}-{ink_cols[-1]}")

    def test_a_package_mesh_is_found_in_the_package_the_description_is_in(self) -> None:
        """``package://NAME/...`` (#611): the package's folder is the nearest above the description named
        NAME, or holding a ``package.xml`` that names it; no such folder, or a path out of it, is refused."""
        from cadgen.engine.formats.robot import RobotError

        def described(package: Path, uri: str, kind: str = "urdf") -> Path:
            path = package / kind / f"arm.{kind}"
            path.parent.mkdir(parents=True, exist_ok=True)
            mesh = f'<mesh filename="{uri}" scale="0.001 0.001 0.001"/>'
            path.write_text(f'<robot name="arm"><link name="base"><visual><geometry>{mesh}</geometry></visual></link></robot>'
                            if kind == "urdf" else
                            f'<sdf version="1.9"><model name="arm"><link name="base"><visual name="shell"><geometry><mesh>'
                            f'<uri>{uri}</uri><scale>0.001 0.001 0.001</scale></mesh></geometry></visual></link></model></sdf>',
                            encoding="utf-8")
            return path

        workspace = self.folder / "ros_ws" / "src"
        for folder, manifest in (("arm_description", None), ("arm-description-main", "arm_description")):
            package = workspace / folder
            (package / "meshes").mkdir(parents=True)
            mesh = write_stl(package / "meshes" / "base.stl", box_soup((40, 20, 10)))
            if manifest:
                (package / "package.xml").write_text(f"<package format='3'><name>{manifest}</name></package>",
                                                     encoding="utf-8")
            for kind in ("urdf", "sdf"):
                with self.subTest(package=folder, kind=kind):
                    found = formats.read(described(package, "package://arm_description/meshes/base.stl", kind))
                    self.assertIn(str(mesh.resolve()), found.files)  # read there, and read again when it changes
                    self.assertEqual([prototype["name"] for prototype in found.structure["prototypes"]], ["base"])
        lone = workspace / "loose"
        for uri, said in (("package://gripper/meshes/base.stl", "no folder named 'gripper'"),
                          ("package://arm_description/../../loose/base.stl", "climbs out of its package")):
            with self.subTest(uri=uri), self.assertRaisesRegex(RobotError, said):
                formats.read(described(lone if "gripper" in uri else workspace / "arm_description", uri))


# --- DXF -------------------------------------------------------------------------------------------


class DxfTest(FixtureTest):
    def test_a_dxf_is_read_in_its_pens_and_what_it_does_not_draw_is_counted(self) -> None:
        path = self.folder / "plate.dxf"
        path.write_text(DXF.replace("0\nENDSEC\n0\nEOF", "0\nPOINT\n8\nCUT\n10\n1\n20\n1\n0\nENDSEC\n0\nEOF"),
                        encoding="ascii")
        drawing = formats.read(path)
        pens = sorted((pen or "ink") for _points, pen in drawing.lines)
        self.assertEqual(pens, ["#ff0000", "ink", "ink", "ink", "ink"], "the hidden layer draws nothing; BEND is red")
        self.assertEqual([pen for _triangles, pen in drawing.fills], ["#0000ff"])
        self.assertEqual(drawing.skipped, {"POINT": 1})
        (note,) = drawing.texts
        self.assertEqual((note.lines, note.starts, note.direction, note.height), (["NOTE"], [(0.0, -5.0)], (1.0, 0.0), 3.0))
        # The bulge (0.5 on a 40 chord) bows out 10; the words reach a quarter of their height below their baseline.
        np.testing.assert_allclose(drawing.bounds, (0, -5.75, 90, 40), atol=1e-6)
        outline = max((points for points, _pen in drawing.lines), key=len)
        self.assertGreater(len(outline), 40, "the bulge drawn as an arc")
        tab = [points for points, _pen in drawing.lines if len(points) == 2 and np.allclose(points[0], (60, 32))]
        np.testing.assert_allclose(tab[0][1], (57, 38), atol=1e-9)  # the block's line turned 90 degrees at (60, 32)

    def test_a_spline_of_fit_points_is_the_cubic_cad_programs_make(self) -> None:
        """Through every fit point, ezdxf's ``fit_points_to_cad_cv`` -- the curve the viewer's
        reader draws -- unbent at its ends, or leaving them along the tangents the entity gives."""
        from ezdxf.math import fit_points_to_cad_cv

        from cadgen.engine.formats.dxf import Entity, _interpolated

        fits = [(5, 55), (20, 65), (35, 52), (50, 66), (75, 56)]
        for codes, tangents in (([], None), ([(12, "1"), (22, "1"), (13, "1"), (23, "-0.5")], [(1, 1, 0), (1, -0.5, 0)])):
            curve = _interpolated(Entity("SPLINE", codes), fits)
            for point in fits:
                self.assertLess(float(np.linalg.norm(curve - point, axis=1).min()), 1e-9, point)
            theirs = fit_points_to_cad_cv([(x, y, 0) for x, y in fits], tangents=tangents).approximate(2000)
            theirs = np.array([(point.x, point.y) for point in theirs])
            apart = np.linalg.norm(curve[:, None] - theirs[None], axis=2).min(1).max()
            self.assertLess(float(apart), 0.05, f"{tangents}: {apart} from ezdxf's curve")


# --- pictures --------------------------------------------------------------------------------------


# --- units -----------------------------------------------------------------------------------------


class UnitTest(FixtureTest):
    """A length asked of a file -- where ``display.clip.at`` stands -- is in the file's unit, as the
    viewer reads one (``sceneUnits.js``); a packet's camera, Measure's points and the ink are in the viewer's
    scene coordinates, the file's unit but a GLB's millimetre. Each reader says what one of each is in the
    millimetres drawn, and the stills read those lengths through it."""

    def test_each_reader_says_what_one_of_the_file_s_units_is_in_millimetres(self) -> None:
        write_stl(self.folder / "part.stl", box_soup((20, 10, 4)))
        write_3mf(self.folder / "kit.3mf")  # its model unit is the centimetre
        write_glb(self.folder / "rig.glb")
        (self.folder / "kinematics.urdf").write_text(KINEMATICS, encoding="utf-8")
        found = {name: (structure["millimetresPerUnit"], structure["millimetresPerSceneUnit"])
                 for name in ("part.stl", "kit.3mf", "rig.glb", "kinematics.urdf")
                 for structure in [formats.read(self.folder / name).structure]}
        self.assertEqual(found, {"part.stl": (1.0, 1.0), "kit.3mf": (10.0, 10.0), "rig.glb": (1000.0, 1.0),
                                 "kinematics.urdf": (1000.0, 1000.0)})

    def test_a_camera_s_lengths_are_read_in_the_viewer_s_scene_coordinates(self) -> None:
        from cadgen.engine.render.occt import camera_in_millimetres

        camera = {"position": [0, -1, 0.13], "target": [0, 0, 0.13], "up": [0, 0, 1], "orthographicHalfHeight": 0.16,
                  "zoom": 1.5, "name": "view 1"}
        self.assertEqual(camera_in_millimetres(camera, 1000.0), {**camera, "position": [0.0, -1000.0, 130.0],
                                                                 "target": [0.0, 0.0, 130.0], "orthographicHalfHeight": 160.0})
        self.assertIs(camera_in_millimetres(camera, 1.0), camera, "a document's and a GLB's millimetres are the scene's")
        self.assertEqual(camera_in_millimetres({"preset": "front", "direction": [0, -1, 0]}, 1000.0),
                         {"preset": "front", "direction": [0, -1, 0]}, "a direction carries no length")

    def test_the_clip_s_plane_stands_at_its_at_in_the_file_s_unit(self) -> None:
        from types import SimpleNamespace

        from cadgen.engine.render.clip import plane

        bounds = (np.zeros(3), np.array([200.0, 200.0, 260.0]))  # a 0.26 m robot, drawn in millimetres
        robot = SimpleNamespace(millimetres_per_unit=1000.0, rest_bounds=lambda: bounds)
        self.assertAlmostEqual(plane(robot, {"axis": "z", "at": 0.13}).Location().Z(), 130.0)
        self.assertAlmostEqual(plane(robot, {"axis": "z"}).Location().Z(), 130.0, msg="without at, the middle at rest")
        self.assertEqual(plane(robot, {"axis": "z", "at": 0.13, "invert": True}).Axis().Direction().Z(), 1.0,
                         "invert keeps the upper side")
        document = SimpleNamespace(millimetres_per_unit=1.0, rest_bounds=lambda: bounds)
        self.assertAlmostEqual(plane(document, {"axis": "y", "at": 12.5}).Location().Y(), 12.5,
                               msg="a document's millimetres")


class PictureTest(FixtureTest):
    """Each kind drawn as its golden, and what a kind does not offer refused by name."""

    @classmethod
    def setUpClass(cls) -> None:
        gl()
        super().setUpClass()
        folder = cls.folder
        write_stl(folder / "part.stl", np.concatenate([box_soup((20, 10, 4)), cylinder_soup(3, 12, at=(0, 0, 2))]))
        write_3mf(folder / "kit.3mf")
        write_glb(folder / "rig.glb")
        (folder / "kinematics.urdf").write_text(KINEMATICS, encoding="utf-8")
        (folder / "plate.dxf").write_text(DXF, encoding="ascii")
        cls.rows = {
            "stl": (folder / "part.stl", {}),
            "stl-wireframe": (folder / "part.stl", {"display": {"mode": "wireframe"}}),
            "3mf": (folder / "kit.3mf", {}),
            "3mf-parts": (folder / "kit.3mf", {"display": {"mode": "parts", "grid": True}}),
            "glb": (folder / "rig.glb", {}),
            "urdf": (folder / "kinematics.urdf", {"pose": {"spin": 75, "lift": 40, "reach": 0.03, "output_joint": 20}}),
            "dxf": (folder / "plate.dxf", {}),
            "dxf-dark": (folder / "plate.dxf", {"display": {"appearance": "dark"}}),
        }

    def draw(self, path: Path, **fields) -> tuple[bytes, dict]:
        from cadgen.engine.render.service import holder

        held = holder(path)
        try:
            held.open()
            return held.draw(Still(**{"size": SIZE, **fields}))
        finally:
            held.close()

    def test_each_kind_draws_as_its_golden(self) -> None:
        GOLDEN.mkdir(exist_ok=True) if WRITE else None
        for name, (path, fields) in self.rows.items():
            with self.subTest(row=name):
                data, report = self.draw(path, **fields)
                self.assertEqual((report["renderer"], report["width"], report["height"]), ("occt", *SIZE))
                own = GOLDEN / PLATFORM / f"{name}.png"
                golden = own if own.is_file() else GOLDEN / f"{name}.png"
                if WRITE:
                    golden.write_bytes(data)
                    continue
                share = mismatch(pixels(data), pixels(golden.read_bytes()))
                if share > 0.015 and os.environ.get("GITHUB_ACTIONS") == "true":
                    import base64

                    print(f"GOLDEN {PLATFORM}/{name} {base64.b64encode(data).decode()}")
                self.assertLessEqual(share, 0.015, f"{name}: {share:.1%} of its pixels are not the golden's")
        if not WRITE:
            self.assertEqual(sorted(path.stem for path in GOLDEN.glob("*.png")), sorted(self.rows))

    def test_the_glb_texture_is_drawn_in_the_lit_looks_alone(self) -> None:
        """The checker's texture in Solid; in Parts the cube one flat palette colour, no checker
        under it (the texture is not modulated by the fill)."""
        textured = pixels(self.draw(self.folder / "rig.glb")[0])
        yellow = (np.abs(textured - np.array([250, 220, 60])).max(-1) < 70).sum()
        self.assertGreater(yellow, 50, "the texture's yellow band")
        parts = pixels(self.draw(self.folder / "rig.glb", display={"mode": "parts"})[0])
        # The checker is orange and blue: in Parts, no pixel is far bluer than it is red.
        blue = ((parts[..., 2] - parts[..., 0]) > 90).sum()
        self.assertLess(blue, 5, "Parts paints over the texture")

    def test_a_drawing_takes_its_appearance_as_the_word_or_the_json(self) -> None:
        # `--display dark` and `--display '{"appearance": "dark"}'` draw one picture; a 3D mode is
        # refused naming the two words a drawing takes.
        path = self.folder / "plate.dxf"

        def drawn(display: str) -> bytes:
            out = self.folder / "appearance.png"
            snapshot(path, out, display=parse_display(display, False), size=SIZE, daemon=False)  # as the verb parses it
            return out.read_bytes()

        word, json_form, light = drawn("dark"), drawn('{"appearance": "dark"}'), drawn("light")
        self.assertEqual(word, json_form)
        self.assertNotEqual(word, light)
        with self.assertRaisesRegex(SnapshotRefused, r"is a drawing.*display.mode does not apply.*light or dark"):
            drawn("xray")

    def test_a_drawings_quick_edit_is_drawn_back_in_its_window_with_its_ink(self) -> None:
        """A drawing's Quick Edit view is the window on screen as a plan view: ``--job`` draws that window
        with the ink on the sheet and Measure's dimensions over it, ``--camera authored`` the view the ink
        was last drawn in, the same picture; a camera that is no plan view is refused by name."""
        from cadgen.engine.formats.dxf import read_dxf
        from cadgen.engine.snapshot import draw_pictures, job_pictures

        path = self.folder / "plate.dxf"
        x0, y0, x1, y1 = read_dxf(path).bounds
        cx, cy, half = (x0 + x1) / 2, (y0 + y1) / 2, (y1 - y0) / 4  # the middle, zoomed in twice
        plan = {"position": [cx, cy, 100], "target": [cx, cy, 0], "up": [0, 1, 0], "orthographicHalfHeight": half}
        stroke = {"id": "m1", "kind": "stroke", "part": None, "points": [cx - half, cy, 0, cx + half, cy, 0],
                  "color": "#ff00ff", "width": 20, "view": "view 1"}
        words = {"id": "m2", "kind": "text", "part": None, "text": "here", "color": "#00a000", "view": "view 1",
                 "points": [cx - half, cy + half / 2, 0, cx, cy + half / 2, 0, cx, cy, 0, cx - half, cy, 0]}
        dimension = {"start": [cx - half, cy - half / 2, 0], "end": [cx + half, cy - half / 2, 0], "label": "40 mm",
                     "color": "#0000ff"}
        window = self.folder / "window.png"
        packet = {"input": str(path), "annotation": {"units": "mm", "parts": {}, "marks": [stroke, words]},
                  "measurements": [dimension],
                  "jobs": [{"camera": plan, "outputs": [{"path": str(window), "label": "view 1", "width": 320,
                                                         "height": 240}]}]}
        [drawn] = draw_pictures(job_pictures(packet), daemon=False)
        self.assertEqual((drawn["camera"], drawn["width"], drawn["height"]), ("plan", 320, 240))
        found, whole = pixels(window.read_bytes()), pixels(self.draw(path)[0])
        red, green, blue = found[..., 0], found[..., 1], found[..., 2]
        # The window, not the whole drawing, each measured against the picture itself, so no renderer's
        # line weight decides it: the stroke, its window's width long, spans three quarters of the
        # picture's width (the whole drawing fitted, a third); and the sheet's own lines (its
        # unsaturated ink), zoomed on its sparse middle, are a quarter of the whole drawing's share
        # from the same renderer (fitted, nine tenths).
        stroked = np.where((np.minimum(red, blue) - green > 120).any(0))[0]
        self.assertTrue(0.7 < (stroked.max() - stroked.min() + 1) / found.shape[1] < 0.85,
                        "the stroke spans the window's width, not the whole drawing's")

        def lines(picture: np.ndarray) -> float:
            off = np.abs(picture - picture[0, 0]).max(-1) > 32
            return float((off & (picture.max(-1) - picture.min(-1) <= 40)).mean())

        self.assertLess(lines(found), 0.5 * lines(whole), "the window, not the whole drawing")
        for what, inked, at_least in (("the stroke", np.minimum(red, blue) - green > 120, 300),
                                      ("the words", green - np.maximum(red, blue) > 60, 20),
                                      ("the dimension", blue - np.maximum(red, green) > 60, 20)):
            self.assertGreater(int(inked.sum()), at_least, what)
        authored = self.folder / "authored.png"
        snapshot(path, authored, camera="authored", daemon=False, annotation=packet["annotation"],
                 annotation_source=packet, measurements=packet["measurements"])
        self.assertLessEqual(mismatch(pixels(authored.read_bytes()), found), 0.001)
        tilted = {**plan, "position": [cx + 10, cy, 100]}
        for camera in ("top", tilted, {**plan, "orthographicHalfHeight": 0}):
            with self.subTest(camera=camera), self.assertRaisesRegex(SnapshotRefused, "its camera is a plan view"):
                job_pictures({**packet, "jobs": [{**packet["jobs"][0], "camera": camera}]})

    def test_what_a_kind_does_not_offer_is_refused_by_name_and_keeps_the_earlier_picture(self) -> None:
        out = self.folder / "stale.png"
        for path, options, why in (
                (self.folder / "part.stl", {"pose": {"a": 1}}, "is a mesh and has none"),
                (self.folder / "part.stl", {"display": {"mode": "parts"}}, "places 1 part"),
                (self.folder / "plate.dxf", {"display": {"mode": "xray"}}, "is a drawing.*display.mode does not apply"),
                (self.folder / "plate.dxf", {"camera": "iso"}, "is a drawing, seen from above: its camera is a plan view"),
                (self.folder / "kinematics.urdf", {"pose": {"lift": 200}}, "--pose: joint 'lift' at 200 is past its limits")):
            out.write_bytes(b"before")
            with self.subTest(path=path.name, options=options), self.assertRaisesRegex(SnapshotRefused, why):
                snapshot(path, out, size=SIZE, daemon=False, **options)
            self.assertEqual(out.read_bytes(), b"before", f"{path.name}: a refused snapshot keeps the picture at OUT")


class DaemonFileTest(unittest.TestCase):
    """A file drawn through the daemon: a render process of its own reads it, warm from its second
    picture, and reads it again when the file changes. Nothing is written but the pictures."""

    def setUp(self) -> None:
        import subprocess
        import sys

        gl()
        self.folder = Path(tempfile.mkdtemp(prefix="engine-formats-daemon-")).resolve()
        self.state = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        source = Path(__file__).resolve().parents[5] / "packages" / "cadgen" / "src"
        env = {**os.environ, "PYTHONPATH": str(source), "CADGEN_ENGINE_DIR": str(self.state)}
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.state, ignore_errors=True)

        def cli(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run([sys.executable, "-m", "cadgen.engine", *args], cwd=self.folder, env=env,
                                  capture_output=True, text=True, timeout=300)

        self.cli = cli
        self.addCleanup(cli, "stop")

    def snapshot(self, out: str) -> dict:
        done = self.cli("snapshot", "part.stl", out, "--width", "200", "--height", "150", "--json")
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout.strip().splitlines()[-1])

    def test_a_file_is_read_by_a_render_process_of_its_own_and_again_when_it_changes(self) -> None:
        write_stl(self.folder / "part.stl", box_soup((20, 10, 4)))
        first = self.snapshot("first.png")
        self.assertEqual((first["renderer"], first["kind"]), ("occt", "stl"))
        self.assertIn("openMs", first["timings"])
        warm = self.snapshot("warm.png")
        self.assertEqual(warm["process"]["pid"], first["process"]["pid"])
        self.assertFalse({"openMs", "sceneMs"} & set(warm["timings"]), warm["timings"])
        write_stl(self.folder / "part.stl", np.concatenate([box_soup((20, 10, 4)), cylinder_soup(3, 12, at=(0, 0, 2))]))
        changed = self.snapshot("changed.png")
        self.assertEqual(changed["process"]["pid"], first["process"]["pid"])
        self.assertIn("openMs", changed["timings"], "read again: the file changed")
        self.assertNotEqual((self.folder / "changed.png").read_bytes(), (self.folder / "first.png").read_bytes())
        self.assertEqual(sorted(path.name for path in self.folder.iterdir()), ["changed.png", "first.png", "part.stl", "warm.png"])
        # The daemon's socket (on Windows the port file standing in for it) and its lock, nothing else.
        self.assertEqual({path.suffix or path.name for path in self.state.iterdir()},
                         {".port", ".lock"} if os.name == "nt" else {".door", ".lock", "clients"})


def setUpModule() -> None:
    # The registry and cache of every engine this module starts are its own, never the developer's
    # (``engine_daemon.isolate``); each test still names its own engine folder.
    from tests.python.support import engine_daemon

    engine_daemon.isolate(unittest.addModuleCleanup)


if __name__ == "__main__":
    unittest.main()
