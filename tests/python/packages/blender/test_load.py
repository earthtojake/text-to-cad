"""``cad.blender.load`` inside the real bpy, through the real path: one script that imports cad, build123d and bpy.

A model with a motion, an ``animation()`` and a nested sub-assembly is built by the checkout's ``cad run`` and
exported to a GLB by ``cad model export`` (finer, ``--tolerance`` and ``--angle``), in a folder of the test's own with
an engine of its own. A probe script then runs under ``cad run``, which makes the environment of cad's blender and
build123d integrations for it (bpy 5.2.3 on Python 3.13, from PyPI the first time, uv's cache after), and says what it
found as one JSON line. In that one process it builds a part with the engine (``@glb``) and another with build123d's
own exporter, loads both, and holds the three import traps ``load`` exists for: a part the first clip moves stands
where the file places it (the importer alone poses it at that clip's start), a clip played after another leaves nothing
of the other's pose, in either order, and a clip's frames run from 0 to its duration at the fps given.

Which object is which node is held on GLBs written here: build123d's (one node with no name and a mesh), the model's
rewritten as KiCad writes a board (its root with no name, a part named by itself rather than its path, two parts of
one name, no clips), and one made by hand whose nodes have no name (a mesh, an empty, a camera, a light), the same
name twice, two names longer than Blender keeps that differ only past where it cuts them, the name Blender gives
another, three scene roots, and clips on a camera, on two of one name and one with no name. A glow on one pin, as
the skill's recipe keys it, leaves the other, whose mesh it shares, as it was.

Then a 64x64 Cycles still on the CPU, and an EEVEE one. EEVEE draws through OpenGL, which a machine with no graphics
library cannot give: there alone its render skips, with Blender's reason, after ``load`` has answered again. On CI
nothing of this suite may skip: its runner fails a run in which a test did (``scripts/test/test-blender.sh``), since
the blender job exists to run it. The suite is that job's alone. Never reads ``models/``."""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import struct
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.python.support import engine_daemon
from tests.python.support.paths import REPO_ROOT, add_sources

add_sources()

from cad_server._internal import base, extras  # noqa: E402

# The making of the environment downloads about 430 MB on Linux the first time, inside the runner's 15-minute guard
# of a file; a build, an export and the renders take seconds.
TIMEOUT = 840.0
# What Blender says, as it stops, where the system gives it no OpenGL to draw EEVEE with: no EGL library at all, or
# a driver older than it needs. Its render alone skips on these.
NO_GRAPHICS = ("Couldn't open libEGL.so.1", "Unsupported graphics card or driver")

# A base and an arm that swings on it, the arm a sub-assembly (a bar and a head of two pins, the head a sub-assembly
# of its own): the arm stands at 30 degrees as written, and the motion `sweep` starts at -15 (swing -45), swings to 90
# (swing 60) and back, so the importer's pose (the clip's start) is 45 degrees from cad's. The animation `show` lifts
# the head 10 mm over its 2 s, and pin_2 5 mm more in its second second.
MODEL = '''
import build123d as bd
from cad import model
from cad.build123d import animation, configuration_sequence, mechanism_state


@model
def rig():
    base = bd.Box(80, 40, 10, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX))
    base.label = "base"
    bar = bd.Box(40, 10, 4, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
    bar.label = "bar"
    pin = bd.Cylinder(2, 6, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    pins = [pin.moved(bd.Location((x, 0, 0))) for x in (0, 8)]
    pins[0].label, pins[1].label = "pin_1", "pin_2"
    head = bd.Compound(children=pins, label="head").moved(bd.Location((30, 0, 4), (0, 0, 1), 90))
    arm = bd.Compound(children=[bar, head], label="arm").moved(bd.Location((-20, 0, 0), (0, 0, 1), 30))
    swing = bd.Axis((-20, 0, 0), (0, 0, 1))
    bd.RevoluteJoint("swing", base, axis=swing, angular_range=(-90, 90))
    bd.RigidJoint("swing", arm, bd.Plane(origin=swing.position, z_dir=swing.direction).location)
    shape = bd.Compound(children=[base, arm], label="rig")
    mechanism_state(shape, "out", swing=60)
    show = animation(shape, "show", duration=2)
    show.translation("arm/head", by=(0, 0, 10))
    show.translation("arm/head/pin_2", by=(0, 0, 5), start=1, end=2)
    return configuration_sequence(shape, "sweep", [(0, {"swing": -45}), (1, "out"), (2, {"swing": -45})])


if __name__ == "__main__":
    rig()
'''

# Everything ``load`` is asked, as one JSON line (PROBE), then the render (RENDER). One process: cad, build123d, bpy.
PROBE = '''
import json
import math
import os
import sys
from pathlib import Path

import bpy
import build123d as bd
from mathutils import Vector

import cad
from cad import glb
from cad.blender import load

HERE = Path(__file__).resolve().parent


@glb("crate.glb")
def crate():
    return bd.Box(30, 20, 10)


def place(model, path, frame):
    scene = bpy.context.scene
    scene.frame_set(frame)
    item = model.objects[path].evaluated_get(bpy.context.evaluated_depsgraph_get())
    return [*item.matrix_world.translation, math.degrees(item.matrix_world.to_euler().z)]


def placed(model):
    return {index: [[round(value, 5) for value in row] for row in item.matrix_basis]
            for index, item in model.nodes.items()}


def world(item):
    bpy.context.view_layer.update()
    return [round(value, 5) for value in item.matrix_world.translation]


def fresh():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return bpy.context.scene


def probe():
    said = {"environment": {"python": list(sys.version_info[:2]), "cad": cad.__version__,
                            "config": os.environ.get("BLENDER_USER_CONFIG")}}

    # A part built by the engine from this script, and one by build123d's own exporter: both in this process.
    crate()
    fresh()
    built = load(HERE / "crate.glb")
    said["built"] = {"root": built.root.name, "size": list(built.size)}
    bd.export_gltf(bd.Box(20, 10, 5), str(HERE / "plain.glb"), binary=True)
    fresh()
    plain = load(HERE / "plain.glb")
    said["plain"] = {"root": [plain.root.type, plain.root.parent is None], "nodes": len(plain.nodes),
                     "named": sorted(plain.objects) == [plain.root.name], "size": list(plain.size)}
    (HERE / "after.txt").write_text(str(round(bd.Box(1, 2, 3).volume, 6)))  # the kernel, after bpy has run

    # The importer alone: the arm at the first clip's start.
    scene = fresh()
    bpy.ops.import_scene.gltf(filepath=str(HERE / "scene.glb"))
    scene.frame_set(0)
    said["imported_arm"] = math.degrees(bpy.data.objects["arm"].matrix_world.to_euler().z)

    scene = fresh()
    model = load(HERE / "scene.glb")
    said["root"] = [model.root.name, model.root.parent is None, list(model.root.scale), len(model.roots)]
    said["objects"] = sorted(model.objects)
    said["clips"] = {name: [clip.kind, clip.duration] for name, clip in model.clips.items()}
    said["actions"] = sorted(action.name for action in bpy.data.actions)
    said["tagged"] = sorted(item.name for item in bpy.data.objects if "cad_blender_node" in item)
    said["box"] = [list(model.box[0]), list(model.box[1])]
    said["fps"] = [model.fps, scene.render.fps]
    said["rest"] = {"arm": place(model, "arm", 10), "pin_2": place(model, "arm/head/pin_2", 10)}
    try:
        model.play("nothing")
    except KeyError as error:
        said["unknown"] = str(error)

    orders = {}
    for order in (("sweep", "show"), ("show", "sweep")):
        seen = []
        for name in order:
            model.play(name)
            seen.append({"clip": model.clip, "range": [scene.frame_start, scene.frame_end, scene.frame_current],
                         "arm": [place(model, "arm", frame) for frame in (0, 24, 48)],
                         "pin_2": [place(model, "arm/head/pin_2", frame) for frame in (0, 24, 48)]})
        orders["-".join(order)] = seen
    said["orders"] = orders
    model.play(None)
    said["still"] = {"arm": place(model, "arm", 30), "pin_2": place(model, "arm/head/pin_2", 30)}

    # The glow recipe (references/shots.md) on pin_1: the pins share one mesh, so the look goes on the object's slot.
    pins = [model.objects["arm/head/pin_1"], model.objects["arm/head/pin_2"]]
    looks = [pin.active_material for pin in pins]
    material = pins[0].active_material.copy()
    pins[0].material_slots[0].link = "OBJECT"
    pins[0].material_slots[0].material = material
    bsdf = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Emission Strength"].default_value = 20.0
    said["glow"] = {"shared": pins[0].data == pins[1].data, "lit": pins[0].active_material == material,
                    "other": pins[1].active_material == looks[1] != material}

    # KiCad's way: a root with no name, a part named by itself, two of one name, no clips.
    fresh()
    nameless = load(HERE / "nameless.glb")
    said["nameless"] = {"root": [nameless.root.name, nameless.root.parent is None,
                                 nameless.objects.get(nameless.root.name) == nameless.root],
                        "objects": sorted(nameless.objects), "clips": sorted(nameless.clips),
                        "box": [list(nameless.box[0]), list(nameless.box[1])],
                        "arm": place(nameless, "arm", 10)}

    # A file made by hand (the test's ODD): every node found by its place in the file. Without its clips first:
    # where Blender's importer itself places each node, which the file with clips must show at rest.
    fresh()
    still = placed(load(HERE / "still.glb"))
    scene = fresh()
    odd = load(HERE / "odd.glb")
    nodes = odd.nodes
    said["odd"] = {
        "kinds": {index: item.type for index, item in nodes.items()},
        "parents": {index: next((at for at, other in nodes.items() if other == item.parent), None)
                    for index, item in nodes.items()},
        "names": {index: item.name for index, item in nodes.items()},
        "distinct": len({item.name for item in nodes.values()}),
        "roots": [next(index for index, item in nodes.items() if item == root) for root in odd.roots],
        "root": odd.root == nodes[0],
        "objects": {name: next(index for index, item in nodes.items() if item == found)
                    for name, found in odd.objects.items()},
        "clips": {name: [clip.kind, clip.duration] for name, clip in odd.clips.items()},
        "rest": placed(odd) == still,
        "world": {index: world(nodes[index]) for index in (4, 8)},
    }
    odd.play("go")
    scene.frame_set(24)
    said["odd"]["go"] = {"range": [scene.frame_start, scene.frame_end], "moved": world(nodes[5]), "first": world(nodes[4])}
    odd.play("animation_2")
    scene.frame_set(24)
    said["odd"]["unnamed"] = {"moved": world(nodes[1]), "back": world(nodes[5])}
    odd.play(None)
    said["odd"]["again"] = placed(odd) == still
    try:
        load(HERE / "model.py")
    except ValueError as error:
        said["refused"] = str(error)

    # Another rate: the keys and the range at 30 fps.
    scene = fresh()
    model = load(HERE / "scene.glb", clip="show", fps=30)
    said["at_30"] = {"range": [scene.frame_start, scene.frame_end], "fps": scene.render.fps,
                     "pin_2": place(model, "arm/head/pin_2", 60)}
    print("PROBE " + json.dumps(said), flush=True)
    return model


def render(model, engine):
    """A still of the clip's middle: the model in front of a transparent background."""
    scene = bpy.context.scene
    camera = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
    aim = bpy.data.objects.new("aim", None)
    aim.location = model.center
    view = math.tan(camera.data.angle / 2)
    camera.location = model.center + model.size.length / 2 / view * 1.2 * Vector((1, -1, 0.6)).normalized()
    camera.constraints.new("TRACK_TO").target = aim
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    for item in (camera, aim, sun):
        scene.collection.objects.link(item)
    scene.camera = camera
    scene.frame_set(30)
    scene.render.resolution_x = scene.render.resolution_y = 64
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.engine = engine
    if engine == "CYCLES":
        scene.cycles.device, scene.cycles.samples, scene.cycles.use_denoising = "CPU", 4, False
    else:
        scene.eevee.taa_render_samples = 4
    scene.render.filepath = str(HERE / (engine.lower() + ".png"))
    bpy.ops.render.render(write_still=True)
    image = bpy.data.images.load(scene.render.filepath)
    alpha = list(image.pixels)[3::4]
    print("RENDER " + json.dumps({"size": list(image.size), "covered": sum(1 for value in alpha if value > 0)}),
          flush=True)


if __name__ == "__main__":
    render(probe(), sys.argv[1])
'''

# A GLB made by hand: nodes with no name, one name twice, a name of 300 characters twice but for its last (Blender
# cuts an object's name at 255 bytes, at 63 before Blender 5, so both are cut to one name and the second is made
# another), a node named as Blender names another (``Mesh_0``), three scene roots, and three clips.
LONG = "p" * 300
HALF = math.sqrt(0.5)
ODD_NODES = [
    {"mesh": 0, "children": [1, 2, 3, 4]},                                             # 0: no name, a mesh
    {"translation": [1, 0, 0]},                                                        # 1: no name, an empty
    {"camera": 0, "translation": [0, 0, 5]},                                           # 2: no name, a camera
    {"extensions": {"KHR_lights_punctual": {"light": 0}}, "translation": [0, 3, 0]},   # 3: no name, a light
    {"name": "twin", "mesh": 0, "translation": [2, 0, 0]},                             # 4
    {"name": "twin", "mesh": 0, "translation": [4, 0, 0], "children": [6, 7, 8]},      # 5: a second root, a second twin
    {"name": LONG + "a", "translation": [0, 0, 1]},                                    # 6
    {"name": LONG + "b", "translation": [0, 0, 2]},                                    # 7: the same first 300 bytes
    {"name": "Mesh_0", "mesh": 0, "translation": [0, 0, 3]},                           # 8: the name Blender gives node 0
    {"name": "eye", "camera": 0, "translation": [0, 0, 9], "rotation": [0, HALF, 0, HALF]},  # 9: a third root
]


def _glb(gltf: dict, binary: bytes = b"") -> bytes:
    """A GLB of a glTF document and its binary chunk."""
    text = json.dumps(gltf).encode()
    text += b" " * (-len(text) % 4)
    binary += b"\0" * (-len(binary) % 4)
    chunk = struct.pack("<I4s", len(binary), b"BIN\0") + binary if binary else b""
    return (struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(text) + len(chunk)) + struct.pack("<I4s", len(text), b"JSON")
            + text + chunk)


def _odd(clips: bool) -> bytes:
    """The hand-made GLB (``ODD_NODES``): one triangle for every mesh; with ``clips``, three of them, each a
    second long -- ``go`` moves the first twin and a camera with no name and turns the camera ``eye``; a second
    ``go`` moves the second twin; one with no name moves the empty with no name. A translation's keys are (0, 1, 0)
    then (0, 2, 0): in Blender, 2 up at its end."""
    points = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    times = struct.pack("<2f", 0.0, 1.0)
    moves = struct.pack("<6f", 0, 1, 0, 0, 2, 0)
    turns = struct.pack("<8f", 0, HALF, 0, HALF, 0, 1, 0, 0)
    binary = points + times + moves + turns
    gltf = {
        "asset": {"version": "2.0"},
        "extensionsUsed": ["KHR_lights_punctual"],
        "extensions": {"KHR_lights_punctual": {"lights": [{"type": "point"}]}},
        "scene": 0, "scenes": [{"nodes": [0, 5, 9]}], "nodes": ODD_NODES,
        "cameras": [{"type": "perspective", "perspective": {"yfov": 0.7, "znear": 0.1}}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 36}, {"buffer": 0, "byteOffset": 36, "byteLength": 8},
                        {"buffer": 0, "byteOffset": 44, "byteLength": 24}, {"buffer": 0, "byteOffset": 68, "byteLength": 32}],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3", "min": [0, 0, 0], "max": [1, 1, 0]},
            {"bufferView": 1, "componentType": 5126, "count": 2, "type": "SCALAR", "min": [0], "max": [1]},
            {"bufferView": 2, "componentType": 5126, "count": 2, "type": "VEC3"},
            {"bufferView": 3, "componentType": 5126, "count": 2, "type": "VEC4"},
        ],
    }
    if clips:
        move, turn = {"input": 1, "output": 2}, {"input": 1, "output": 3}
        gltf["animations"] = [
            {"name": "go", "samplers": [move, turn],
             "channels": [{"sampler": 0, "target": {"node": 4, "path": "translation"}},
                          {"sampler": 1, "target": {"node": 9, "path": "rotation"}},
                          {"sampler": 0, "target": {"node": 2, "path": "translation"}}]},
            {"name": "go", "samplers": [move], "channels": [{"sampler": 0, "target": {"node": 5, "path": "translation"}}]},
            {"samplers": [move], "channels": [{"sampler": 0, "target": {"node": 1, "path": "translation"}}]},
        ]
    return _glb(gltf, binary)


def _nameless(source: Path, target: Path) -> None:
    """``source`` as KiCad writes a board's GLB: the root with no name, each part named by itself (``pin_1``, not
    ``arm/head/pin_1``), the bar named ``base`` as the base is (KiCad names 72 lenses ``lens``), and no clips."""
    raw = source.read_bytes()
    (length,) = struct.unpack_from("<I", raw, 12)
    gltf = json.loads(raw[20:20 + length])
    gltf.pop("animations", None)
    for node in gltf["nodes"]:
        node["name"] = "base" if node["name"] == "arm/bar" else node["name"].rsplit("/", 1)[-1]
    del gltf["nodes"][gltf["scenes"][gltf.get("scene", 0)]["nodes"][0]]["name"]
    text = json.dumps(gltf).encode()
    text += b" " * (-len(text) % 4)
    rest = raw[20 + length:]
    target.write_bytes(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(text) + len(rest))
                       + struct.pack("<I4s", len(text), b"JSON") + text + rest)


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", path
    return struct.unpack(">II", data[16:24])


class LoadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            extras.supported(("blender",), base.Installation.here().arch)
        except extras.Refused as refused:
            raise unittest.SkipTest(str(refused)) from None
        engine_daemon.isolate(cls.addClassCleanup)
        cls.project = Path(tempfile.mkdtemp(prefix="blender-load-")).resolve()
        cls.addClassCleanup(shutil.rmtree, cls.project, True)
        cls.env = engine_daemon.watched({**os.environ, "CAD_ENGINE_MESH": "inline"}, cls.addClassCleanup)
        (cls.project / "model.py").write_text(MODEL, encoding="utf-8")
        built = cls.cad("run", "model.py")
        ids = re.findall(r"^\s*id: (\S+)$", built.stdout, re.M)
        if built.returncode != 0 or not ids:
            raise AssertionError(f"the model did not build:\n{built.stdout}\n{built.stderr}")
        exported = cls.cad("model", "export", ids[0], "scene.glb", "--tolerance", "0.05", "--angle", "10")
        if exported.returncode != 0:
            raise AssertionError(f"the GLB was not exported:\n{exported.stdout}\n{exported.stderr}")
        _nameless(cls.project / "scene.glb", cls.project / "nameless.glb")
        (cls.project / "odd.glb").write_bytes(_odd(clips=True))
        (cls.project / "still.glb").write_bytes(_odd(clips=False))
        (cls.project / "probe.py").write_text(textwrap.dedent(PROBE), encoding="utf-8")
        cls.cycles = cls.cad("run", "probe.py", "CYCLES")
        cls.said, cls.rendered = cls.lines(cls.cycles)

    @classmethod
    def cad(cls, *args: str):
        return engine_daemon.run([sys.executable, "-m", "cad_server.cli", *args], env=cls.env, cwd=cls.project,
                                 timeout=TIMEOUT)

    @staticmethod
    def lines(done) -> tuple[dict | None, dict | None]:
        """What a probe's run said: ``load``'s answers (PROBE) and its render's (RENDER), None for one it did not
        reach."""
        found = {name: json.loads(text) for name, text in re.findall(r"^(PROBE|RENDER) (.*)$", done.stdout, re.M)}
        return found.get("PROBE"), found.get("RENDER")

    def setUp(self) -> None:
        self.assertIsNotNone(self.said, f"the probe failed:\n{self.cycles.stdout[-4000:]}\n{self.cycles.stderr[-4000:]}")

    def assertNear(self, found, expected, tolerance, message=None) -> None:
        self.assertEqual(len(found), len(expected), message)
        for got, want in zip(found, expected):
            self.assertLessEqual(abs(got - want), tolerance, f"{message}: {found} is not {expected}")

    def assertPlaced(self, found, expected, message, degrees=1e-3) -> None:
        """A world position in metres (to a micrometre: Blender's floats are 32-bit) and a turn about Z in degrees."""
        self.assertNear(found[:3], expected[:3], 1e-6, message)
        self.assertNear(found[3:], expected[3:], degrees, message)

    def test_one_script_imports_cad_build123d_and_bpy_in_an_environment_of_cad_s_on_python_3_13(self) -> None:
        release = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        cache = Path(os.environ["CAD_CACHE_DIR"])
        self.assertEqual(self.said["environment"], {"python": [3, 13], "cad": release,
                                                    "config": str(cache / "homes" / "blender" / "user_config")})
        self.assertIn("cad run: making the environment of the blender and build123d integrations, once: "
                      f"cad[blender,build123d] {release}", self.cycles.stderr)
        # A model the engine built from that script, in a worker of that Python, and one build123d exported itself:
        # the kernel beside bpy, and still working after it.
        self.assertEqual(self.said["built"]["root"], "crate")
        self.assertNear(self.said["built"]["size"], [0.03, 0.02, 0.01], 1e-6, "the engine's GLB, in metres")
        self.assertEqual((self.project / "after.txt").read_text(encoding="utf-8"), "6.0")
        made = [marker for path in (cache / base.BASE).iterdir() if (marker := base.complete(path))
                and "blender" in (marker.get("integrations") or ())]
        self.assertEqual(len(made), 1, "one environment, made once")
        self.assertEqual((made[0]["integrations"], made[0]["inputs"]["release"]), (["blender", "build123d"], release))
        self.assertTrue(made[0]["python_version"].startswith("3.13."))

    def test_build123d_s_own_glb_opens_its_one_node_with_no_name(self) -> None:
        # ``export_gltf`` writes one node with no name that carries the mesh: Blender names its object after the mesh.
        plain = self.said["plain"]
        self.assertEqual((plain["root"], plain["nodes"], plain["named"]), (["MESH", True], 1, True))
        self.assertNear(plain["size"], [0.02, 0.01, 0.005], 1e-6, "the box, in metres")
        self.assertRegex(self.said["refused"], r"^model\.py is not a GLB \(binary glTF\)")

    def test_every_node_is_found_by_its_place_in_the_file_whatever_blender_names_its_object(self) -> None:
        odd = self.said["odd"]
        kinds = {int(index): kind for index, kind in odd["kinds"].items()}
        self.assertEqual(kinds, {0: "MESH", 1: "EMPTY", 2: "CAMERA", 3: "LIGHT", 4: "MESH", 5: "MESH", 6: "EMPTY",
                                 7: "EMPTY", 8: "MESH", 9: "CAMERA"}, "each node's own object, a node with no name too")
        self.assertEqual({int(index): parent for index, parent in odd["parents"].items()},
                         {0: None, 1: 0, 2: 0, 3: 0, 4: 0, 5: None, 6: 5, 7: 5, 8: 5, 9: None})
        self.assertEqual((odd["roots"], odd["root"], odd["distinct"]), ([0, 5, 9], True, 10), "three roots, ten objects")
        # By name: a name given twice is its last node's, and so is the name Blender gave a node with none when
        # another node bears it; a long name is its own node's, not its neighbour's, though Blender cut both short.
        names = {int(index): name for index, name in odd["names"].items()}
        self.assertTrue(all(len(names[index]) < len(LONG) for index in (6, 7)) and names[6] != names[7], names)
        self.assertEqual({name: at for name, at in odd["objects"].items() if name in ("twin", "Mesh_0", "eye")},
                         {"twin": 5, "Mesh_0": 8, "eye": 9})
        self.assertEqual((odd["objects"][LONG + "a"], odd["objects"][LONG + "b"]), (6, 7))
        for index in (1, 2, 3):
            self.assertEqual(odd["objects"][names[index]], index, "a node with no name, by the name Blender gave it")
        # Where the file places them: glTF's (x, y, z) is Blender's (x, -z, y).
        self.assertEqual({int(index): at for index, at in odd["world"].items()}, {4: [2.0, 0.0, 0.0], 8: [4.0, -3.0, 0.0]})

    def test_a_clip_moves_its_own_nodes_and_every_node_rests_where_the_importer_places_it(self) -> None:
        odd = self.said["odd"]
        self.assertEqual(odd["clips"], {"go": ["", 1.0], "animation_2": ["", 1.0]}, "a name given twice, the last")
        # A camera a clip turns, and a camera under a mesh that a clip moves, rest as Blender's importer places them
        # in the same file without its clips: its own turn of a camera's object among them.
        self.assertTrue(odd["rest"] and odd["again"], "at rest, and again after two clips")
        # A clip's key is the node's whole translation: (0, 2, 0) in the file is 2 up in Blender.
        self.assertEqual(odd["go"], {"range": [0, 24], "moved": [0.0, 0.0, 2.0], "first": [2.0, 0.0, 0.0]},
                         "the second `go` moves the second twin and leaves the first")
        self.assertEqual(odd["unnamed"], {"moved": [0.0, 0.0, 2.0], "back": [4.0, 0.0, 0.0]})

    def test_the_glb_imports_whole_its_root_its_nodes_and_its_clips(self) -> None:
        name, top, scale, roots = self.said["root"]
        self.assertEqual((name, top, roots), ("rig", True, 1))
        self.assertNear(scale, [0.001] * 3, 1e-9, "the root shows the parts' millimetres in metres")
        self.assertEqual(self.said["objects"], ["arm", "arm/bar", "arm/head", "arm/head/pin_1", "arm/head/pin_2",
                                                "base", "rig"])
        self.assertEqual(self.said["clips"], {"sweep": ["motion", 2.0], "show": ["animation", 2.0]})
        self.assertEqual(self.said["actions"], ["show", "sweep"], "each clip's action bears its name")
        self.assertEqual(self.said["tagged"], [], "no object keeps the tag it was found by")
        self.assertEqual(self.said["fps"], [24, 24])
        self.assertIn("'nothing' is not a clip of this GLB", self.said["unknown"])

    def test_every_part_stands_where_cad_placed_it_not_at_the_first_clips_start(self) -> None:
        # The importer alone poses the arm at sweep's start, -15 degrees: the trap load undoes.
        self.assertNear([self.said["imported_arm"]], [-15.0], 1.0, "the importer poses the arm at sweep's start")
        # cad's arm: at (-20, 0, 0) mm, turned 30 degrees; pin_2 at (-20 + 30 cos 30 - 8 sin 30, 30 sin 30 + 8 cos 30, 4)
        # mm, turned 30 + 90. Nothing plays: a later frame changes nothing.
        pin = [(-20 + 30 * math.cos(math.radians(30)) - 8 * math.sin(math.radians(30))) / 1000,
               (30 * math.sin(math.radians(30)) + 8 * math.cos(math.radians(30))) / 1000, 0.004]
        for when in ("rest", "still"):
            with self.subTest(when=when):
                self.assertPlaced(self.said[when]["arm"], [-0.02, 0.0, 0.0, 30.0], "the arm")
                self.assertPlaced(self.said[when]["pin_2"], pin + [120.0], "pin_2")

    def test_the_box_is_the_written_poses_in_metres(self) -> None:
        low, high = self.said["box"]
        self.assertNear(low, [-0.04, -0.02, -0.01], 1e-6, "the base's corner")
        # The far corner: the base's x, the arm's bar or pin_2 in y (24.7 mm, meshed), the pins' tops in z.
        self.assertNear(high, [0.04, 0.0247, 0.01], 3e-4, "the far corner")

    def test_a_clip_plays_alone_from_frame_0_whichever_played_before(self) -> None:
        sweep_arm = [[-0.02, 0.0, 0.0, -15.0], [-0.02, 0.0, 0.0, 90.0], [-0.02, 0.0, 0.0, -15.0]]
        rest_pin = (-20 + 30 * math.cos(math.radians(30)) - 8 * math.sin(math.radians(30))) / 1000
        for order, seen in self.said["orders"].items():
            for clip in seen:
                with self.subTest(order=order, clip=clip["clip"]):
                    self.assertEqual(clip["range"], [0, 48, 0], "frames 0 to 2 s at 24 fps, from frame 0")
                    if clip["clip"] == "sweep":
                        for found, expected in zip(clip["arm"], sweep_arm):
                            # LINEAR keys within a tenth of a degree of the bake.
                            self.assertPlaced(found, expected, "the arm swings", degrees=0.2)
                        self.assertNear([clip["pin_2"][0][2]], [0.004], 1e-6, "show's lift is gone")
                    else:
                        for found in clip["arm"]:
                            self.assertPlaced(found, [-0.02, 0.0, 0.0, 30.0], "sweep's swing is gone")
                        # The head lifts 10 mm over 2 s; pin_2 5 mm more in the second second.
                        self.assertNear([pin[2] for pin in clip["pin_2"]], [0.004, 0.009, 0.019], 2e-4, "pin_2 lifts")
                        self.assertNear([clip["pin_2"][0][0]], [rest_pin], 1e-6, "pin_2 where cad placed it")

    def test_the_fps_given_keys_the_clip_and_sets_its_range(self) -> None:
        self.assertEqual(self.said["at_30"]["range"], [0, 60])
        self.assertEqual(self.said["at_30"]["fps"], 30)
        self.assertNear([self.said["at_30"]["pin_2"][2]], [0.019], 2e-4, "the clip's end is its last frame")

    def test_a_glb_whose_root_has_no_name_opens_its_parts_where_it_places_them(self) -> None:
        said = self.said["nameless"]
        name, top, found = said["root"]
        self.assertTrue(top and found, f"the root {name!r} is the model's and the top object")
        self.assertEqual(said["objects"], sorted(["arm", "base", "head", "pin_1", "pin_2", name]))
        self.assertEqual(said["clips"], [])
        # Both parts named base are in the box: it is the named GLB's.
        self.assertNear(said["box"][0] + said["box"][1], self.said["box"][0] + self.said["box"][1], 1e-6, "the box")
        self.assertPlaced(said["arm"], [-0.02, 0.0, 0.0, 30.0], "the arm")

    def test_a_glow_on_one_part_leaves_another_of_its_mesh_as_it_was(self) -> None:
        self.assertEqual(self.said["glow"], {"shared": True, "lit": True, "other": True})

    def test_a_cycles_still_on_the_cpu(self) -> None:
        self.assertIsNotNone(self.rendered, f"Cycles did not render:\n{self.cycles.stderr[-4000:]}")
        self.assertEqual(self.cycles.returncode, 0, self.cycles.stderr[-4000:])
        self.assertEqual(_png_size(self.project / "cycles.png"), (64, 64))
        self.assertEqual(self.rendered["size"], [64, 64])
        covered = self.rendered["covered"]
        self.assertTrue(200 < covered < 64 * 64 - 200, f"the model covers {covered} of 4096 pixels")

    def test_an_eevee_still(self) -> None:
        done = self.cad("run", "probe.py", "BLENDER_EEVEE")
        said, rendered = self.lines(done)
        self.assertNotIn("cad run: making", done.stderr, "the environment was made once: this run uses it again")
        # load answered again before any render: a failure of ours is never taken for a machine without graphics.
        self.assertEqual(said, self.said, done.stdout[-4000:] + done.stderr[-4000:])
        if rendered is None:
            reason = next((line.strip() for line in done.stderr.splitlines() if any(sign in line for sign in NO_GRAPHICS)),
                          None)
            if reason is not None:
                self.skipTest(f"EEVEE cannot draw here, a machine with no OpenGL for Blender: {reason}")
        self.assertIsNotNone(rendered, f"EEVEE did not render (exit {done.returncode}):\n{done.stderr[-4000:]}")
        self.assertEqual(done.returncode, 0, done.stderr[-4000:])
        self.assertEqual(_png_size(self.project / "blender_eevee.png"), (64, 64))
        self.assertTrue(200 < rendered["covered"] < 64 * 64 - 200, f"the model covers {rendered['covered']} of 4096 pixels")


if __name__ == "__main__":
    unittest.main()
