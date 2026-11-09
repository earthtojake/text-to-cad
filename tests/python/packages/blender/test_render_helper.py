"""The render skill's Blender helper (``skills/render/scripts/cad_glb.py``) inside the real bpy, through the real path.

A model with a motion, an ``animation()`` and a nested sub-assembly is built by the checkout's ``cad run`` and
exported to a GLB by ``cad model export`` (finer, ``--tolerance`` and ``--angle``), in a folder of the test's own with
an engine of its own. A script beside a copy of the helper then runs under ``cad run``, which runs it in the blender
integration's environment (bpy 5.2.3 on Python 3.13, without cad, made from PyPI the first time, uv's cache after),
and says what it found as one JSON line. It holds the three import traps the helper exists for: a part the first clip
moves stands where cad placed it (the importer alone poses it at that clip's start), a clip played after another
leaves nothing of the other's pose, in either order, and a clip's frames run from 0 to its duration at the fps given.
The same GLB rewritten as KiCad writes a board (its root with no name, a part named by itself rather than its path, two
parts of one name, no clips) opens too, and a glow on one pin, as the skill's recipe keys it, leaves the other, whose mesh
it shares, as it was. Then a 64x64 Cycles still on the CPU, and an EEVEE one: EEVEE needs an OpenGL context, which a Linux machine with no
GPU may not give, so there alone a failure skips with Blender's reason. The suite is the blender job's alone
(``scripts/test/test-blender.sh``). Never reads ``models/``."""

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

from cad.registry import INTEGRATIONS  # noqa: E402
from cad_server._internal import base, extras  # noqa: E402

HELPER = REPO_ROOT / "skills/render/scripts/cad_glb.py"
# The making of bpy's environment downloads about 430 MB on Linux the first time, inside the runner's 15-minute
# guard of a file; a build, an export and the renders take seconds.
TIMEOUT = 840.0

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

# Everything the helper is asked, as one JSON line; the renders after it.
PROBE = '''
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
import cad_glb  # beside this script: cad run puts its folder first

said = {}
scene = bpy.context.scene


def place(model, path, frame):
    scene.frame_set(frame)
    item = model.objects[path].evaluated_get(bpy.context.evaluated_depsgraph_get())
    return [*item.matrix_world.translation, math.degrees(item.matrix_world.to_euler().z)]


# The importer alone: the arm at the first clip's start.
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(HERE / "scene.glb"))
scene = bpy.context.scene
scene.frame_set(0)
said["imported_arm"] = math.degrees(bpy.data.objects["arm"].matrix_world.to_euler().z)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
model = cad_glb.load(HERE / "scene.glb")
said["root"] = [model.root.name, model.root.parent is None, list(model.root.scale)]
said["objects"] = sorted(model.objects)
said["clips"] = {name: [clip.kind, clip.duration] for name, clip in model.clips.items()}
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
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
nameless = cad_glb.load(HERE / "nameless.glb")
said["nameless"] = {"root": [nameless.root.name, nameless.root.parent is None,
                             nameless.objects.get(nameless.root.name) == nameless.root],
                    "objects": sorted(nameless.objects), "clips": sorted(nameless.clips),
                    "box": [list(nameless.box[0]), list(nameless.box[1])],
                    "arm": place(nameless, "arm", 10)}

# Another rate: the keys and the range at 30 fps.
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
model = cad_glb.load(HERE / "scene.glb", clip="show", fps=30)
said["at_30"] = {"range": [scene.frame_start, scene.frame_end], "fps": scene.render.fps,
                 "pin_2": place(model, "arm/head/pin_2", 60)}

# A still, on the CPU, of the clip's middle: the model in front of a transparent background.
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
engine = sys.argv[1]
scene.render.engine = engine
if engine == "CYCLES":
    scene.cycles.device, scene.cycles.samples, scene.cycles.use_denoising = "CPU", 4, False
else:
    scene.eevee.taa_render_samples = 4
scene.render.filepath = str(HERE / (engine.lower() + ".png"))
bpy.ops.render.render(write_still=True)
image = bpy.data.images.load(scene.render.filepath)
alpha = list(image.pixels)[3::4]
said["render"] = {"size": list(image.size), "covered": sum(1 for value in alpha if value > 0)}
print("PROBE " + json.dumps(said))
'''


def _built_here() -> bool:
    try:
        extras.supported(INTEGRATIONS["blender"], base.Installation.here().arch)
    except extras.Refused:
        return False
    return True


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


@unittest.skipUnless(_built_here(), "bpy has no build for this platform (an Intel Mac, Linux arm64)")
class RenderHelperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        engine_daemon.isolate(cls.addClassCleanup)
        cls.project = Path(tempfile.mkdtemp(prefix="render-helper-")).resolve()
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
        shutil.copy(HELPER, cls.project / "cad_glb.py")
        (cls.project / "probe.py").write_text(textwrap.dedent(PROBE), encoding="utf-8")
        cls.cycles = cls.cad("run", "probe.py", "CYCLES")
        found = re.findall(r"^PROBE (.*)$", cls.cycles.stdout, re.M)
        cls.said = json.loads(found[-1]) if cls.cycles.returncode == 0 and found else None

    @classmethod
    def cad(cls, *args: str):
        return engine_daemon.run([sys.executable, "-m", "cad_server.cli", *args], env=cls.env, cwd=cls.project,
                                 timeout=TIMEOUT)

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

    def test_the_glb_imports_whole_its_root_its_nodes_and_its_clips(self) -> None:
        name, top, scale = self.said["root"]
        self.assertEqual((name, top), ("rig", True))
        self.assertNear(scale, [0.001] * 3, 1e-9, "the root shows the parts' millimetres in metres")
        self.assertEqual(self.said["objects"], ["arm", "arm/bar", "arm/head", "arm/head/pin_1", "arm/head/pin_2",
                                                "base", "rig"])
        self.assertEqual(self.said["clips"], {"sweep": ["motion", 2.0], "show": ["animation", 2.0]})
        self.assertEqual(self.said["fps"], [24, 24])
        self.assertIn("'nothing' is not a clip of this GLB", self.said["unknown"])

    def test_every_part_stands_where_cad_placed_it_not_at_the_first_clips_start(self) -> None:
        # The importer alone poses the arm at sweep's start, -15 degrees: the trap the helper undoes.
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
        self.assertEqual(_png_size(self.project / "cycles.png"), (64, 64))
        self.assertEqual(self.said["render"]["size"], [64, 64])
        covered = self.said["render"]["covered"]
        self.assertTrue(200 < covered < 64 * 64 - 200, f"the model covers {covered} of 4096 pixels")

    def test_an_eevee_still(self) -> None:
        done = self.cad("run", "probe.py", "BLENDER_EEVEE")
        found = re.findall(r"^PROBE (.*)$", done.stdout, re.M)
        if (done.returncode != 0 or not found) and sys.platform.startswith("linux"):
            self.skipTest("EEVEE could not draw on this Linux machine (no GPU's OpenGL): "
                          + (done.stderr.strip().splitlines() or ["no output"])[-1])
        self.assertEqual(done.returncode, 0, done.stdout[-4000:] + done.stderr[-4000:])
        self.assertEqual(_png_size(self.project / "blender_eevee.png"), (64, 64))
        covered = json.loads(found[-1])["render"]["covered"]
        self.assertTrue(200 < covered < 64 * 64 - 200, f"the model covers {covered} of 4096 pixels")


if __name__ == "__main__":
    unittest.main()
