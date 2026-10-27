"""cadgen's stills drawn by OCCT (`engine/render`): the headless context, a document held and drawn
from the engine's meshes, the render process the daemon keeps warm per served document, and golden
pictures of the material fixture.

Every test that draws makes an OpenGL context (`render/context.py`) and is skipped, saying why,
where none can be made -- but fails on CI with an X display, which was set up to draw
(`tests/python/support/opengl.py`). macOS draws on a hidden Cocoa window. Linux needs an X server
with GLX -- under Xvfb: `xvfb-run -a scripts/test/test-python.sh tests/python/packages/cadgen/engine/test_render.py`
-- or an OCCT built with EGL; Windows draws on a hidden window.

The golden pictures (`render_golden/*.png`) are the material fixture (`test_materials.py`'s bench,
its pane hinged on the plate for a pose) at 320x240, drawn on macOS: one per display mode, and Explode,
Clip, a pose, and an annotation with a measurement; and `cap.png`, Clip's cap on a box holding
another (`CapTest`). A picture matches its golden when at most 1.5%
of its pixels are more than 32 levels from every golden pixel within one pixel of them (anti-aliasing
and drivers apart, a line a pixel over still matches). Where a platform's OpenGL draws a row apart,
the row has a golden of that platform's own (`render_golden/<platform>/<row>.png`), held to the same
bound; a row missed in CI prints the picture it drew (`GOLDEN <platform>/<row>`, base64), that
platform's golden once a person has looked at it. A deliberate change to the look makes them
again: `CADGEN_RENDER_GOLDENS=write scripts/test/test-python.sh tests/python/packages/cadgen/engine/test_render.py`.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from cadgen.engine.render import context
from cadgen.engine.snapshot import SnapshotRefused, Still, parse_display
from tests.python.support import opengl

SRC = Path(__file__).resolve().parents[5] / "packages" / "cadgen" / "src"
GOLDEN = Path(__file__).resolve().parent / "render_golden"
WRITE = os.environ.get("CADGEN_RENDER_GOLDENS") == "write"
SIZE = (320, 240)
PLATFORM = context.platform()  # a row a platform draws apart has a golden of its own there

# The material fixture: a steel block, a brushed aluminium plate, a PLA part with a lacquered top,
# a glass pane, and two placements of one bracket apart by a look alone. Its pane is hinged on the
# plate's back edge, to pose.
BENCH = """
import build123d as bd
from cadgen.ap242 import mechanism_state
from cadgen.engine import paint, xbf
from bd_materials import FinishedMaterial, metals, plastics, glass
from bd_materials.core import RangeMaterial
from threejs_materials import PbrProperties

LACQUER = FinishedMaterial(RangeMaterial(name="Red lacquer", density=1200),
    pbr=PbrProperties.create("lacquer", color="#cb2727", metalness=0, roughness=0.4,
                             clearcoat=1, clearcoat_roughness=0.05))
STEEL = FinishedMaterial(metals.mild_steel().material,
    pbr=PbrProperties.create("steel", color="#c5c7c8", metalness=1, roughness=0.4))
ALUMINUM = FinishedMaterial(metals.aluminum().material,
    pbr=PbrProperties.create("aluminum", color="#f5f6f6", metalness=1, roughness=0.35, anisotropy=0.3))
PLA = FinishedMaterial(plastics.pla().material,
    pbr=PbrProperties.create("PLA", color="#ededeB", metalness=0, roughness=0.45))
GLASS = FinishedMaterial(glass.soda_lime().material,
    pbr=PbrProperties.create("glass", color="#ffffff", metalness=0, roughness=0.02, ior=1.52,
        transmission=1, attenuation_color=(0.822786, 0.930111, 0.871367), attenuation_distance=0.05))
STAINLESS = FinishedMaterial(metals.stainless().material,
    pbr=PbrProperties.create("stainless", color="#d6d4d1", metalness=1, roughness=0.3, anisotropy=0.3))


@xbf("XBF/bench.xbf")
def bench():
    block = bd.Box(30, 30, 30)
    block.label, block.material = "block", STEEL
    plate = bd.Pos(50, 0, -10) * bd.Box(40, 30, 4)
    plate.label, plate.material = "plate", ALUMINUM
    print_ = bd.Pos(100, 0, 0) * bd.Cylinder(12, 30)
    print_.label, print_.material = "print", PLA
    pane = bd.Box(40, 3, 30, align=(bd.Align.CENTER, bd.Align.MIN, bd.Align.MIN))
    pane.label, pane.material = "pane", GLASS
    pane.color = bd.Color("#ffffff")  # Keep base alpha 1; transmission is the material's.
    paint(print_, print_.faces().sort_by(bd.Axis.Z)[-1], LACQUER)
    left = bd.Pos(0, -50, 0) * bd.Box(10, 10, 10)
    left.label, left.material = "left", STAINLESS
    right = left.moved(bd.Location((20, 0, 0)))
    right.label, right.material = "right", FinishedMaterial(STAINLESS.material, pbr=STAINLESS.pbr.override(roughness=0.2, anisotropy=0))
    bd.RevoluteJoint("hinge", plate, axis=bd.Axis((0, 15, 2), (1, 0, 0)), angular_range=(-90, 90))
    bd.RigidJoint("foot", pane, joint_location=bd.Location((0, 0, 0), (0, 90, 0)))
    plate.joints["hinge"].connect_to(pane.joints["foot"], angle=0)
    root = bd.Compound(children=[block, plate, print_, pane, left, right], label="bench")
    return mechanism_state(root, "open", hinge=60)
"""

# Ink on the plate (instance 1, in its own frame: its top face is z 2) and a dimension along its front.
ANNOTATION = {"units": "mm", "parts": {}, "marks": [
    {"id": "m1", "kind": "stroke", "part": "i1", "color": "#ff00ff", "width": 6,
     "points": [-15, -10, 2.05, -5, -1, 2.05, 5, 5, 2.05, 15, 8, 2.05]}]}
MEASUREMENTS = [{"start": [30, -15, -8], "end": [70, -15, -8], "label": "40.0 mm", "color": "#0000ff"}]

ROWS = {
    "solid": {"display": {"mode": "solid"}},
    "shaded": {"display": {"mode": "shaded"}},
    "parts": {"display": {"mode": "parts"}},
    "xray": {"display": {"mode": "xray"}},
    "hidden-line": {"display": {"mode": "hidden-line"}},
    "wireframe": {"display": {"mode": "wireframe"}},
    "exploded": {"display": parse_display("exploded=0.6", grid=False)},
    "clip": {"display": {"mode": "solid", "clip": {"enabled": True, "axis": "x"}}},
    "pose": {"display": {"mode": "solid"}, "pose": "open"},
    "annotation": {"display": {"mode": "solid"}, "annotation": ANNOTATION, "measurements": MEASUREMENTS},
}


def gl() -> None:
    """Skip, saying why, where no OpenGL context can be made (on CI with a display, fail)."""
    opengl.require(context.available())


def pixels(data: bytes) -> np.ndarray:
    from PIL import Image

    with Image.open(io.BytesIO(data)) as image:
        return np.asarray(image.convert("RGB")).astype(np.int16)


def mismatch(found: np.ndarray, golden: np.ndarray) -> float:
    """The share of ``found``'s pixels more than 32 levels (in some channel) from every pixel of
    ``golden`` within one pixel of them."""
    if found.shape != golden.shape:
        return 1.0
    height, width = golden.shape[:2]
    padded = np.pad(golden, ((1, 1), (1, 1), (0, 0)), mode="edge")
    best = np.full((height, width), 255, np.int16)
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            best = np.minimum(best, np.abs(found - padded[dy:dy + height, dx:dx + width]).max(-1))
    return float((best > 32).mean())


def drawn(data: bytes, size: tuple[int, int]) -> np.ndarray:
    """The picture: PNG, the size asked, and more than its backdrop."""
    found = pixels(data)
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and found.shape == (size[1], size[0], 3), found.shape
    backdrop = found[0, 0]
    assert (np.abs(found - backdrop).max(-1) > 8).mean() > 0.01, "a backdrop alone"  # a line drawing covers little
    return found


def shapes(structure: dict) -> int:
    """How many parts a renderer makes shapes of: one per geometry and paints (the fixture's two
    brackets, one geometry apart by a material alone, are one)."""
    return len({(p["key"], json.dumps(p.get("faceColors") or {}, sort_keys=True)) for p in structure["prototypes"]})


def build(folder: Path, source: str, name: str) -> Path:
    from cadgen.engine import build as engine_build

    script = folder / f"{name}.py"
    script.write_text(textwrap.dedent(source), encoding="utf-8")
    reports = engine_build.build(script, None, cwd=folder)
    assert all(report["ok"] for report in reports), reports
    return folder / f"XBF/{name}.xbf"


def served(document: Path) -> tuple[dict, dict[str, bytes]]:
    """The document as the engine serves it, and every part's buffer, meshed in this process."""
    from cadgen.engine.serve import Server

    server = Server(port=0, mesh_mode="inline")
    try:
        doc = server.document(server.add(document))
        server.mesh_all(doc, None)
        structure = server.structure(doc)
        return structure, {p["key"]: server.cache.get(p["key"]) for p in structure["prototypes"]}
    finally:
        server.stop()


class ContextTest(unittest.TestCase):
    def test_a_linux_with_no_display_is_refused_naming_xvfb(self) -> None:
        environment = {key: value for key, value in os.environ.items() if key != "DISPLAY"}
        with mock.patch.object(context, "platform", return_value="linux"), \
                mock.patch.object(context, "_has_xlib", return_value=True), mock.patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(context.Unavailable, "Xvfb"):
                context.driver()
            self.assertIn("Xvfb", context.available())

    def test_a_refused_connection_is_asked_again_at_the_next_canvas(self) -> None:
        # One refused connection (an X server busy for a moment) fails that canvas, not the process's.
        gl()
        with mock.patch.object(context, "_CONNECTION", threading.local()), \
                mock.patch("OCP.Aspect.Aspect_DisplayConnection", side_effect=RuntimeError("Can not connect")):
            with self.assertRaisesRegex(context.Unavailable, "Can not connect"):
                context.driver()
        context.Canvas(16, 16).close()
        self.assertIsNone(context.available())

    def test_the_canvases_of_a_thread_share_one_display_connection(self) -> None:
        # One X client per thread, however many scenes it holds: an X server refuses clients past
        # its limit, and every process drawing on it counts against that.
        gl()
        first, second = context.Canvas(16, 16), context.Canvas(24, 16)
        self.addCleanup(first.close)
        self.addCleanup(second.close)
        self.assertIs(first.driver.GetDisplayConnection(), second.driver.GetDisplayConnection())

    def test_a_canvas_draws_at_the_size_asked_whatever_its_window(self) -> None:
        gl()
        canvas = context.Canvas(64, 48)
        self.addCleanup(canvas.close)
        canvas.width, canvas.height = 200, 120
        found = pixels(canvas.png())
        self.assertEqual(found.shape, (120, 200, 3))


class StillTest(unittest.TestCase):
    def test_a_still_travels_as_json(self) -> None:
        still = Still({"mode": "xray"}, {"position": [1, 2, 3], "target": [0, 0, 0], "up": [0, 0, 1],
                                         "orthographicHalfHeight": 4}, True, False, (320, 240), {"hinge": 10},
                      ANNOTATION, MEASUREMENTS)
        self.assertEqual(Still.from_json(json.loads(json.dumps(still.as_json()))), still)


class HeldTest(unittest.TestCase):
    """A document held by a renderer and drawn: the golden pictures, the authored camera, refusals,
    and a new version that keeps what it shares with the last."""

    @classmethod
    def setUpClass(cls) -> None:
        gl()
        from cadgen.engine.render.service import Held

        cls.folder = Path(tempfile.mkdtemp(prefix="engine-render-")).resolve()
        cls.document = build(cls.folder, BENCH, "bench")
        cls.structure, cls.buffers = served(cls.document)
        cls.held = Held(cls.document)
        cls.held.hold(cls.structure, cls.buffers)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.held.close()
        shutil.rmtree(cls.folder, ignore_errors=True)

    def draw(self, size: tuple[int, int] = SIZE, **fields) -> tuple[bytes, dict]:
        return self.held.draw(Still(**{"size": size, **fields}))

    def test_the_material_fixture_draws_as_its_golden_pictures(self) -> None:
        GOLDEN.mkdir(exist_ok=True) if WRITE else None
        for name, row in ROWS.items():
            with self.subTest(row=name):
                data, report = self.draw(**row)
                found = drawn(data, SIZE)
                self.assertEqual((report["renderer"], report["width"], report["height"]), ("occt", *SIZE))
                own = GOLDEN / PLATFORM / f"{name}.png"
                golden = own if own.is_file() else GOLDEN / f"{name}.png"
                if WRITE:
                    golden.write_bytes(data)
                    continue
                share = mismatch(found, pixels(golden.read_bytes()))
                if share > 0.015 and os.environ.get("GITHUB_ACTIONS") == "true":
                    import base64

                    print(f"GOLDEN {PLATFORM}/{name} {base64.b64encode(data).decode()}")
                self.assertLessEqual(share, 0.015, f"{name}: {share:.1%} of its pixels are not the golden's")
        if not WRITE:
            self.assertEqual(sorted(path.stem for path in GOLDEN.glob("*.png")), sorted([*ROWS, "cap"]),
                             "a golden per row, and the cap's")

    def test_hidden_and_isolated_parts_are_left_out_of_every_look(self) -> None:
        # From one camera: the block isolated and the block hidden together cover what the whole
        # bench does, and overlap only along the block's outline; a ref naming nothing is refused.
        view = {"position": [140, -110, 90], "target": [40, 0, 0], "up": [0, 0, 1], "orthographicHalfHeight": 45}

        def covered(display: dict) -> np.ndarray:
            found = pixels(self.draw(display=display, camera=view, exact=True)[0]).astype(int)
            return np.abs(found - found[2, 2]).max(-1) > 24  # off the backdrop, by its corner

        block = covered({"mode": "solid", "isolated": ["block"]})
        others = covered({"mode": "solid", "hidden": ["block"]})
        only_block = block & ~others  # where the block alone stands, in the solid look
        self.assertGreater(only_block.sum(), 1000)
        for mode in ("solid", "xray", "wireframe"):
            with self.subTest(mode=mode):
                whole = covered({"mode": mode})
                alone = covered({"mode": mode, "isolated": ["block"]})
                rest = covered({"mode": mode, "hidden": ["block"]})
                self.assertGreater(alone.sum(), 200, "the block alone is drawn")
                self.assertLess((alone & ~block).mean(), 0.005, "and nothing but the block")
                self.assertLess((rest & only_block).sum(), only_block.sum() * 0.02, "hidden, the block is gone")
                if mode != "xray":  # X-ray blends its parts by what else is drawn: shades, not silhouettes
                    self.assertLess((whole ^ (alone | rest)).mean(), 0.01, "together the whole bench")
        exploded = covered({"mode": "solid", "exploded": {"enabled": True, "amount": 0.5}, "hidden": ["block"]})
        self.assertLess(exploded.sum(), covered({"mode": "solid", "exploded": {"enabled": True, "amount": 0.5}}).sum())
        with self.assertRaisesRegex(SnapshotRefused, "display.hidden: .*nope"):
            covered({"hidden": ["nope"]})
        with self.assertRaisesRegex(SnapshotRefused, "leave nothing of"):
            covered({"isolated": []})
        # A Quick Edit packet carries what the viewer hid and isolated; --display reads the same.
        from cadgen.engine.snapshot import packet_visibility

        packet = {"annotation": {"marks": []}, "views": [], "hidden": ["block"], "isolated": ["bench"]}
        self.assertEqual(packet_visibility(packet), {"hidden": ["block"], "isolated": ["bench"]})
        self.assertEqual(packet_visibility({"marks": []}), {}, "an annotation file holds none")
        self.assertEqual(parse_display('{"hidden": ["block"]}', False), {"hidden": ["block"]})
        with self.assertRaisesRegex(SnapshotRefused, "display.isolated is a list of part refs"):
            parse_display('{"isolated": "block"}', False)

    def test_rows_differ_where_they_should(self) -> None:
        """Each row draws something of its own: the goldens cannot all be one picture."""
        solid = pixels(self.draw(**ROWS["solid"])[0])
        for name in ("exploded", "clip", "pose", "annotation", "wireframe"):
            with self.subTest(row=name):
                self.assertGreater(mismatch(pixels(self.draw(**ROWS[name])[0]), solid), 0.001)
        # The ink: magenta on the plate, the dimension's line blue.
        ink = pixels(self.draw(**ROWS["annotation"])[0])
        for color in ((255, 0, 255), (0, 0, 255)):
            self.assertGreater((np.abs(ink - np.array(color)).max(-1) < 60).sum(), 8, color)

    def test_the_authored_view_is_drawn_exactly(self) -> None:
        """``--camera authored``: the eye, the target and the half height of the view the ink was
        drawn in, no fit: the target at the middle of the picture, the half height to its top edge."""
        view = {"position": [140, -110, 90], "target": [40, 0, 0], "up": [0, 0, 1], "orthographicHalfHeight": 30}
        _data, report = self.draw((320, 240), display={"mode": "solid"}, camera=view, exact=True)
        self.assertEqual(report["camera"], "authored")
        scene = self.held.scenes[False]
        np.testing.assert_allclose(scene.camera["eye"], view["position"])
        middle, top = scene.project(np.array([view["target"], np.array(view["target"]) + scene.camera["up"] * 30]))
        np.testing.assert_allclose(middle, (160, 120), atol=0.5)
        np.testing.assert_allclose(top, (160, 0), atol=0.5)

    def test_x_ray_is_the_colour_only_model_and_gives_the_look_back(self) -> None:
        """X-ray draws the look's colour-only model (``look.py``) on OCCT's Phong program: a part's
        material is its colour alone, so the fixture with its materials taken away draws the same;
        and the next mode is drawn under the look's own PBR rig again, as if X-ray never was."""
        from OCP.Graphic3d import Graphic3d_TypeOfShadingModel

        from cadgen.engine.render.look import LOOK
        from cadgen.engine.render.service import Held

        solid = pixels(self.draw(**ROWS["solid"])[0])
        xray = pixels(self.draw(**ROWS["xray"])[0])
        scene = self.held.scenes[False]
        self.assertEqual(scene.canvas.view.ShadingModel(), Graphic3d_TypeOfShadingModel.Graphic3d_TypeOfShadingModel_Phong)
        self.assertEqual(len(scene.lights), 1 + len(LOOK.xray.lights), "its ambient light and its directional lights")
        self.assertLess(mismatch(pixels(self.draw(**ROWS["solid"])[0]), solid), 0.001, "Solid as before X-ray")
        self.assertEqual(scene.canvas.view.ShadingModel(), Graphic3d_TypeOfShadingModel.Graphic3d_TypeOfShadingModel_Pbr)
        bare = json.loads(json.dumps(self.structure))
        bare["version"] = "bare"
        for prototype in bare["prototypes"]:
            prototype.pop("material", None)
            prototype.pop("faceMaterials", None)
        held = Held(self.document)
        self.addCleanup(held.close)
        held.hold(bare, self.buffers)
        self.assertLess(mismatch(pixels(held.draw(Still(ROWS["xray"]["display"], size=SIZE))[0]), xray), 0.001,
                        "a material is its colour alone")

    def test_every_segment_of_a_zigzag_stroke_is_drawn(self) -> None:
        """A stroke's segments each at the stroke's width, however sharp its turns (a strip with one
        side per point folded every other segment of a zigzag away)."""
        points = np.stack([np.linspace(-15, 15, 7), np.where(np.arange(7) % 2, 8.0, -8.0), np.full(7, 2.05)], 1)
        zigzag = {"units": "mm", "parts": {}, "marks": [{"id": "z", "kind": "stroke", "part": "i1", "color": "#ff00ff",
                                                         "width": 6, "points": points.ravel().tolist()}]}
        found = pixels(self.draw((640, 480), display={"mode": "solid"}, annotation=zigzag)[0])
        scene = self.held.scenes[False]
        placement = scene.placement(1)
        line = scene.project(points @ placement[:3, :3].T + placement[:3, 3])
        ink = np.abs(found - np.array([255, 0, 255])).max(-1) < 60
        for index, (start, end) in enumerate(zip(line[:-1], line[1:])):
            for share in np.linspace(0.2, 0.8, 7):
                x, y = np.rint(start + (end - start) * share).astype(int)
                self.assertTrue(ink[y - 1:y + 2, x - 1:x + 2].any(), f"segment {index}, {share:.0%} along")

    def test_a_portrait_still_is_framed_as_the_page_frames_it(self) -> None:
        """Taller than wide, OCCT spans its scale and its field of view across the width: a preset,
        a fitted camera and a view's own camera each keep the page's framing, the wide bench's
        width at the tight frame's padded edge (4% in from each side), not inside it."""
        size = (90, 160)
        for projection in ("orthographic", "perspective"):
            for camera in ("iso", {"preset": "iso"}):
                with self.subTest(projection=projection, camera=camera):
                    self.draw(size, display={"mode": "solid", "camera": {"projection": projection}}, camera=camera)
                    scene = self.held.scenes[False]
                    found = scene.project(scene.placed_points()) / np.array(size) * 2 - 1
                    self.assertAlmostEqual(float(np.abs(found[:, 0]).max()), 0.92, delta=0.01)
                    self.assertLess(float(np.abs(found[:, 1]).max()), 0.92)
        view = {"position": [140, -110, 90], "target": [40, 0, 0], "up": [0, 0, 1], "orthographicHalfHeight": 30}
        self.draw(size, display={"mode": "solid"}, camera=view, exact=True)
        scene = self.held.scenes[False]
        middle, top = scene.project(np.array([view["target"], np.array(view["target"]) + scene.camera["up"] * 30]))
        np.testing.assert_allclose(middle, (45, 80), atol=0.5)
        np.testing.assert_allclose(top, (45, 0), atol=0.5)

    def test_what_the_document_does_not_offer_is_refused_by_name(self) -> None:
        with self.assertRaisesRegex(SnapshotRefused, "--pose: .*no mechanism state 'shut'"):
            self.draw(display={}, pose="shut")
        with self.assertRaisesRegex(SnapshotRefused, "--pose: .*hinge"):
            self.draw(display={}, pose={"hinge": 400})

    def test_preview_stands_its_floor_at_the_model_s_lowest_point(self) -> None:
        """Preview's floor is under the model wherever it was authored (the viewer's default
        placement, Lowest point): the bench's block reaches 15 below Z=0, and the floor is there,
        not at the document's origin; a pose that moves the lowest point moves the floor with it."""
        from cadgen.engine.render.explode import placed_box

        def lowest(scene) -> float:
            return min(placed_box(scene.boxes[i["prototype"]], scene.placement(n))[0][2]
                       for n, i in enumerate(scene.structure["instances"]) if i["prototype"] in scene.boxes)

        self.draw(display={}, preview=True)
        scene = self.held.scenes[True]
        rest = scene._studio_place()["z"]
        self.assertAlmostEqual(rest, lowest(scene), places=6)
        self.assertLessEqual(rest, -15.0 + 1e-6, "the block's underside, not the document's Z=0")
        floors = {rest}
        for hinge in (-90, 90):
            self.draw(display={}, preview=True, pose={"hinge": hinge})
            self.assertAlmostEqual(scene._studio_place()["z"], lowest(scene), places=6, msg=f"hinge {hinge}")
            floors.add(round(scene._studio_place()["z"], 6))
        self.assertGreater(len(floors), 1, "a pose that moves the lowest point moves the floor")

    def test_preview_keeps_its_studio_and_its_look_between_pictures(self) -> None:
        first = pixels(self.draw(display={}, preview=True)[0])
        scene = self.held.scenes[True]
        stage = list(scene.stage)
        self.assertEqual(len(stage), 2, "Preview's floor and the floor's shadow")
        second = pixels(self.draw(display={}, preview=True, annotation=ANNOTATION)[0])
        self.assertTrue(all(now is then for now, then in zip(scene.stage, stage)) and len(scene.stage) == 2)
        self.assertLess(mismatch(second, first), 0.05, "the same look, with ink")

    def test_a_new_version_s_scenes_are_new_and_draw_as_the_last_did(self) -> None:
        """A version replaced: its scenes let go of whole between pictures and made again, and
        Preview's environment lights the new scene as it lit the last (a scene collected while
        another drew took that one's environment map with it)."""
        from cadgen.engine.render.service import Held

        held = Held(self.document)
        self.addCleanup(held.close)
        held.hold(self.structure, self.buffers)
        still = Still({}, preview=True, size=SIZE)
        first = pixels(held.draw(still)[0])
        modes = pixels(held.draw(Still({"mode": "solid"}, size=SIZE))[0])
        old = dict(held.scenes)
        for version in ("second", "third"):
            held.hold({**self.structure, "version": version}, {})
            self.assertFalse(any(held.scenes.get(look) is scene for look, scene in old.items()), version)
            self.assertLess(mismatch(pixels(held.draw(still)[0]), first), 0.001, version)
            self.assertLess(mismatch(pixels(held.draw(Still({"mode": "solid"}, size=SIZE))[0]), modes), 0.001, version)
            old = dict(held.scenes)

    def test_a_new_version_keeps_the_shapes_it_shares_and_makes_its_scene_at_once(self) -> None:
        from cadgen.engine.render.service import Held

        held = Held(self.document)
        self.addCleanup(held.close)
        self.assertEqual(held.hold(self.structure, self.buffers)["made"], shapes(self.structure))
        held.draw(Still({"mode": "solid"}, size=SIZE))
        scene = held.scenes[False]
        again = held.hold({**self.structure, "version": "next"}, {})
        self.assertEqual((again["made"], again["kept"], again["scene"]), (0, shapes(self.structure), True))
        self.assertIsNot(held.scenes[False], scene, "a scene of the new version, made before any picture asks")
        repainted = json.loads(json.dumps(self.structure))
        repainted["version"] = "repainted"
        repainted["prototypes"][2]["faceColors"] = {}
        self.assertEqual(held.hold(repainted, {})["made"], 1, "a part's paints are its shapes too")
        with self.assertRaisesRegex(KeyError, "no mesh of part"):
            held.hold({**self.structure, "version": "lost", "prototypes": [{**self.structure["prototypes"][0],
                                                                             "key": "0" * 32}]}, {})


class GridPaperTest(unittest.TestCase):
    """The viewer's grid rule (core's stageGrid.js): the round step and the cells of a model at rest."""

    def test_the_step_is_the_round_number_nearest_on_a_log_scale(self) -> None:
        from cadgen.engine.render.grid import round_step

        for target, expected in ((1.0, (1.0, 1)), (1.4, (1.0, 1)), (1.5, (2.0, 2)), (3.0, (2.0, 2)), (3.3, (5.0, 5)),
                                 (7.0, (5.0, 5)), (7.2, (10.0, 1)), (0.031, (0.02, 2)), (450.0, (500.0, 5))):
            step, digit = round_step(target)
            self.assertAlmostEqual(step, expected[0], msg=target)
            self.assertEqual(digit, expected[1], target)

    def test_the_paper_of_a_model_at_rest(self) -> None:
        from cadgen.engine.render.grid import paper

        sheet = paper((0, 0, 0), (100, 60, 30))  # its diagonal 120.4: framing 125.2, a step near 6.26
        self.assertAlmostEqual(sheet.framing, float(np.linalg.norm((100, 60, 30))) * 1.04)
        self.assertEqual((sheet.cell, sheet.every, sheet.major), (5.0, 10, 50.0))
        self.assertAlmostEqual(sheet.fade_start, sheet.framing * 1.5)
        self.assertAlmostEqual(sheet.fade_end, sheet.framing * 6.0)
        small = paper((0, 0, 0), (0.1, 0.1, 0.1))  # each side at least 1, the radius at least 1: framing 2.08
        self.assertEqual((small.cell, small.every), (0.1, 10))
        two = paper((0, 0, 0), (30, 0, 0))  # framing 31.2: a step near 1.56 is 2, a major every 5th
        self.assertEqual((two.cell, two.every, two.major), (2.0, 5, 10.0))


class CapTest(unittest.TestCase):
    """Clip's cap as the viewer draws it: unlit, flat, in the part's colour as a lit face's albedo
    (linear, squared), hiding what is inside the cut part -- a small box held in a big one."""

    def setUp(self) -> None:
        gl()
        import build123d as bd

        from cadgen.engine.mesh import mesh_shape
        from cadgen.engine.render.occt import Scene

        outer, inner = mesh_shape(bd.Box(20, 20, 20).wrapped), mesh_shape(bd.Box(6, 6, 6).wrapped)
        identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
        inside = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, -4, 0, 0, 1]  # column-major: x -7..-1, in the kept half
        self.red, blue = (0.8, 0.1, 0.1), (0.05, 0.2, 0.9)
        structure = {"prototypes": [{"key": "outer", "color": [*self.red, 1]}, {"key": "inner", "color": [*blue, 1]}],
                     "instances": [{"prototype": 0, "matrix": identity}, {"prototype": 1, "matrix": inside}]}
        self.scene = Scene(Path("caps.xbf"), {"outer": outer.to_bytes(), "inner": inner.to_bytes()}, size=SIZE,
                           structure=structure)
        self.addCleanup(self.scene.canvas.close)

    def draw(self, display: dict) -> tuple[np.ndarray, tuple[int, int]]:
        self.scene.show(display)
        self.scene.frame("iso")
        x, y = np.rint(self.scene.project(np.array([[0.0, 0.0, 0.0]]))[0]).astype(int)  # the cut's middle
        return pixels(self.scene.canvas.png()), (x, y)

    def cap(self, found: np.ndarray, at: tuple[int, int]) -> np.ndarray:
        x, y = at
        return found[y - 12:y + 13, x - 12:x + 13].reshape(-1, 3)

    def test_the_cap_is_flat_in_the_part_s_colour_and_hides_what_is_inside(self) -> None:
        from cadgen.engine.render.clip import CAP
        from cadgen.engine.render.grid import hex_colour, to_linear, to_srgb
        from cadgen.engine.render.look import LOOK

        clip = {"enabled": True, "axis": "x"}
        found, at = self.draw({"mode": "solid", "clip": clip})
        golden = GOLDEN / "cap.png"
        if WRITE:
            golden.write_bytes(self.scene.canvas.png())
        else:
            share = mismatch(found, pixels(golden.read_bytes()))
            self.assertLessEqual(share, 0.015, f"cap: {share:.1%} of its pixels are not the golden's")
        expected = np.rint(to_srgb(np.array(self.red) ** LOOK.colour_power) * 255)
        patch = self.cap(found, at)
        self.assertLessEqual(int(np.abs(patch - expected).max()), 3, "unlit, in the red box's colour, the blue unseen")
        plain, _ = self.draw({"mode": "solid", "clip": {**clip, "partColors": False}})
        expected = np.rint(to_srgb(to_linear(hex_colour(CAP))) * 255)
        self.assertLessEqual(int(np.abs(self.cap(plain, at) - expected).max()), 3, "#e9a451 without part colours")
        uncut, _ = self.draw({"mode": "solid"})
        self.assertGreater(int(np.abs(self.cap(uncut, at) - patch).max()), 16, "no clip: the box's lit side")
        self.assertEqual(self.scene.caps, [], "no carrier shown without a clip")
        wire, _ = self.draw({"mode": "wireframe", "clip": clip})
        self.assertEqual(self.scene.caps, [], "nor in Wireframe, which draws no faces")


class RenderProcessTest(unittest.TestCase):
    """The render process, as the daemon talks to it: a version held, frames answered with PNG
    bytes, and gone after a frame that leaves it over its memory cap."""

    def setUp(self) -> None:
        gl()
        self.folder = Path(tempfile.mkdtemp(prefix="engine-render-process-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.document = build(self.folder, BENCH, "bench")
        self.structure, self.buffers = served(self.document)

    def start(self, cap: str):
        from cadgen.engine.render.service import RenderProcess

        process = RenderProcess(self.document, {**os.environ, "PYTHONPATH": str(SRC), "CADGEN_ENGINE_WORKER_RSS_MB": cap})
        self.addCleanup(process.stop)
        keys = sorted(self.buffers)
        answer, _ = process.ask({"op": "hold", "path": str(self.document), "structure": self.structure,
                                 "meshes": [[key, len(self.buffers[key])] for key in keys]},
                                b"".join(self.buffers[key] for key in keys))
        self.assertEqual(answer["held"]["made"], shapes(self.structure))
        return process

    def test_frames_are_answered_warm_and_a_process_over_its_cap_retires(self) -> None:
        process = self.start("0")
        still = Still({"mode": "solid"}, size=SIZE).as_json()
        first, data = process.ask({"op": "frame", "still": still})
        drawn(data, SIZE)
        second, _ = process.ask({"op": "frame", "still": still})
        self.assertEqual((first["done"]["process"]["frames"], second["done"]["process"]["frames"]), (1, 2))
        self.assertNotIn("sceneMs", second["done"]["timings"], "the second picture is drawn on the first's scene")
        refused, _ = process.ask({"op": "frame", "still": {**still, "pose": "shut"}})
        self.assertIn("no mechanism state 'shut'", refused["refused"])
        capped = self.start("1")
        answer, _ = capped.ask({"op": "frame", "still": still})
        self.assertIn("CADGEN_ENGINE_WORKER_RSS_MB", answer["done"]["retired"])
        self.assertEqual(capped.process.wait(timeout=30), 0, "gone once it has answered")


PAIR = """
import build123d as bd
from cadgen.engine import xbf

SIZE = {size}


@xbf("XBF/pair.xbf")
def pair():
    block = bd.Box(SIZE, 4, 2)
    block.label = "block"
    peg = bd.Pos(20, 0, 0) * bd.Cylinder(2, 5)
    peg.label = "peg"
    return bd.Compound(children=[block, peg], label="pair")

if __name__ == "__main__":
    pair()
"""


class DaemonRenderTest(unittest.TestCase):
    """`cadgen snapshot` drawn by OCCT through the daemon: a render process per served
    document, warm from its second picture, sent its file's new version by the next picture with
    only the parts it lacks, gone with the daemon; and in this process with ``daemon=False`` from Python. Nothing is written but
    the pictures, and the daemon's door, lock and clients' pipes."""

    def setUp(self) -> None:
        gl()
        self.folder = Path(tempfile.mkdtemp(prefix="engine-render-daemon-")).resolve()
        self.state = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        self.env = {**os.environ, "PYTHONPATH": str(SRC), "CADGEN_ENGINE_DIR": str(self.state),
                    "CADGEN_ENGINE_MESH": "inline"}
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.state, ignore_errors=True)
        self.addCleanup(self.cli, "stop")

    def cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-m", "cadgen.engine", *args], cwd=self.folder, env=self.env,
                              capture_output=True, text=True, timeout=300)

    def snapshot(self, out: str, *flags: str) -> dict:
        done = self.cli("snapshot", "XBF/pair.xbf", out, "--width", "200", "--height", "150", "--json", *flags)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout.strip().splitlines()[-1])

    def build(self, size: int, *, daemon: bool = True) -> None:
        (self.folder / "pair.py").write_text(textwrap.dedent(PAIR.format(size=size)), encoding="utf-8")
        # ``python pair.py`` asks the daemon; ``Model.build(daemon=False)`` builds in its own process.
        argv = ["pair.py"] if daemon else ["-B", "-c", "import pair; pair.pair.build(daemon=False)"]
        done = subprocess.run([sys.executable, *argv], cwd=self.folder, env=self.env, capture_output=True, text=True,
                              timeout=300)
        self.assertEqual(done.returncode, 0, done.stderr)

    def renders(self) -> list[dict]:
        return json.loads(self.cli("status", "--json").stdout)["renders"]

    def test_a_served_document_is_drawn_warm_and_follows_its_builds(self) -> None:
        self.build(10)
        first = self.snapshot("first.png")
        self.assertEqual(first["renderer"], "occt")
        pid = first["process"]["pid"]
        warm = self.snapshot("warm.png")
        self.assertEqual(warm["process"]["pid"], pid)
        self.assertFalse({"meshMs", "holdMs", "sceneMs"} & set(warm["timings"]), warm["timings"])
        self.build(14)  # the file is rewritten: the next picture reads it, and makes the new part alone
        version = f"{(self.folder / 'XBF/pair.xbf').stat().st_mtime_ns}-{(self.folder / 'XBF/pair.xbf').stat().st_size}"
        edited = self.snapshot("edited.png")
        self.assertEqual(edited["process"]["pid"], pid, "the same process, sent the file's new version")
        [render] = self.renders()
        self.assertEqual((render["version"], render["held"]["made"], render["held"]["kept"]), (version, 1, 1))
        self.assertNotEqual((self.folder / "edited.png").read_bytes(), (self.folder / "first.png").read_bytes())
        # A model, by its id, is drawn from the document its worker holds, in that worker.
        from cadgen.engine.ids import model_id

        done = self.cli("snapshot", model_id(self.folder / "pair.py", "pair"), "model.png", "--width", "200", "--height",
                        "150", "--json")
        self.assertEqual(done.returncode, 0, done.stderr)
        model = json.loads(done.stdout.strip().splitlines()[-1])
        self.assertEqual((model["renderer"], "process" in model), ("occt", False))
        # The daemon's socket (on Windows the port file standing in for it) and its lock, nothing else.
        self.assertEqual({path.suffix or path.name for path in self.state.iterdir()},
                         {".port", ".lock"} if os.name == "nt" else {".door", ".lock", "clients"})
        self.assertEqual(sorted(path.relative_to(self.folder).as_posix() for path in self.folder.rglob("*") if path.is_file()),
                         ["XBF/pair.xbf", "edited.png", "first.png", "model.png", "pair.py", "warm.png"])
        self.cli("stop")
        if os.name != "nt":  # os.kill(pid, 0) asks after a process on POSIX alone
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline and _alive(pid):
                time.sleep(0.1)
            self.assertFalse(_alive(pid), "gone with the daemon")

    def test_daemon_false_draws_in_this_process(self) -> None:
        # A seam of the Python function's alone: no command draws outside the engine.
        self.build(10, daemon=False)
        code = ("import json; from cadgen.engine import api; print(json.dumps(api.snapshot('XBF/pair.xbf', "
                "'cold.png', width=200, height=150, display='exploded=0.5', daemon=False).report))")
        done = subprocess.run([sys.executable, "-c", code], cwd=self.folder, env=self.env, capture_output=True,
                              text=True, timeout=300)
        self.assertEqual(done.returncode, 0, done.stderr)
        report = json.loads(done.stdout.strip().splitlines()[-1])
        self.assertEqual((report["renderer"], report["exploded"]), ("occt", 0.5))
        self.assertNotIn("process", report)
        self.assertEqual([path for path in self.state.iterdir() if path.suffix == ".door"], [], "no daemon started")


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def setUpModule() -> None:
    # The registry and cache of every engine this module starts are its own, never the developer's
    # (``engine_daemon.isolate``); each test still names its own engine folder.
    from tests.python.support import engine_daemon

    engine_daemon.isolate(unittest.addModuleCleanup)


if __name__ == "__main__":
    unittest.main()
