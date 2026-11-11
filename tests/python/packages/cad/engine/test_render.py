"""cadgen's stills drawn by OCCT (`engine/render`): the headless context, a document held and drawn
from the engine's meshes, and golden pictures of the material fixture. Each material reaching OCCT's
face aspect is `test_render_material_transport.py`'s; the render process the daemon keeps warm per
served document, and an engine drawing on a display of its own, are `test_render_daemon.py`'s.

Every test that draws makes an OpenGL context (`render/context.py`) and is skipped, saying why,
where none can be made -- but fails on CI with an X display, which was set up to draw
(`tests/python/support/opengl.py`). macOS draws on a hidden Cocoa window. Linux needs an X server
with GLX -- under Xvfb: `xvfb-run -a scripts/test/test-python.sh tests/python/packages/cad/engine/test_render.py`
-- or an OCCT built with EGL; an engine with no display draws on an Xvfb it starts itself
(`test_render_daemon.py`'s `EngineDisplayTest`). Windows draws on a hidden window.

The golden pictures (`render_golden/*.png`) are the material fixture (`test_materials.py`'s bench,
its pane hinged on the plate for a pose) at 320x240, drawn on macOS: one per display mode, and Explode,
Clip, a pose, and an annotation with a measurement; and `cap.png`, Clip's cap on a box holding
another (`CapTest`). A picture matches its golden when at most 1.5%
of its pixels are more than 32 levels from every golden pixel within one pixel of them (anti-aliasing
and drivers apart, a line a pixel over still matches). Where a platform's OpenGL draws a row apart,
the row has a golden of that platform's own (`render_golden/<platform>/<row>.png`), held to the same
bound; a row missed in CI prints the picture it drew (`GOLDEN <platform>/<row>`, base64), that
platform's golden once a person has looked at it. A deliberate change to the look makes them
again: `CAD_RENDER_GOLDENS=write scripts/test/test-python.sh tests/python/packages/cad/engine/test_render.py`.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from cad.engine.render import context
from cad.engine.snapshot import SnapshotRefused, Still, parse_display
from tests.python.support.render_stills import (BENCH, PLATFORM, SIZE, X_VARIABLES, build, drawn, gl, mismatch,
                                                pixels, served, shapes)

GOLDEN = Path(__file__).resolve().parent / "render_golden"
WRITE = os.environ.get("CAD_RENDER_GOLDENS") == "write"

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


class ContextTest(unittest.TestCase):
    def test_a_linux_with_no_display_is_refused_naming_what_to_install(self) -> None:
        # Neither the request's DISPLAY nor the engine's (an Xvfb it starts where one is installed).
        environment = {key: value for key, value in os.environ.items() if key not in X_VARIABLES}
        with mock.patch.object(context, "platform", return_value="linux"), \
                mock.patch.object(context, "_has_xlib", return_value=True), mock.patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(context.Unavailable, "apt-get install xvfb libgl1 libgl1-mesa-dri"):
                context.driver()
            self.assertIn("Xvfb", context.available())

    def test_a_request_with_no_display_draws_on_the_engine_s(self) -> None:
        # A worker adopts its request's environment; the engine's display is what it draws on where that has
        # none, named to OCCT: never this process's DISPLAY, which the request did not give.
        named = []

        def connect(*given):  # the display named, and the authority Xlib reads as it connects
            named.append(([str(arg.ToCString()) for arg in given], os.environ.get("XAUTHORITY")))
            return object()

        environment = {**{key: value for key, value in os.environ.items() if key not in X_VARIABLES},
                       "CAD_ENGINE_DISPLAY": ":42", "CAD_ENGINE_XAUTHORITY": "/engine/cookie", "XAUTHORITY": "/mine"}
        with mock.patch.object(context, "platform", return_value="linux"), \
                mock.patch.dict(os.environ, environment, clear=True), \
                mock.patch.object(context, "_CONNECTION", threading.local()), \
                mock.patch("OCP.Aspect.Aspect_DisplayConnection", side_effect=connect):
            self.assertEqual(context.display(), ":42")
            context._connection()
            context._connection()  # one connection a display, kept
            self.assertEqual(os.environ["XAUTHORITY"], "/mine", "the request's own, put back")
            os.environ["DISPLAY"] = ":5"
            context._connection()  # the request's own, as OCCT reads it
        self.assertEqual(named, [([":42"], "/engine/cookie"), ([], "/mine")])

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

    def test_a_picture_no_stream_takes_is_handed_over_through_a_file(self) -> None:
        # Windows' OCP saves a picture to a file but to no stream (#709): the same pixels either way,
        # and the file gone after.
        from OCP.Image import Image_AlienPixMap, Image_Format
        from OCP.Quantity import Quantity_Color, Quantity_ColorRGBA, Quantity_TOC_RGB

        image = Image_AlienPixMap()
        image.InitZero(Image_Format.Image_Format_RGB, 5, 3, 0, 0)
        image.SetPixelColor(1, 2, Quantity_ColorRGBA(Quantity_Color(1, 0, 0, Quantity_TOC_RGB), 1.0), False)

        class NoStream:
            def Save(self, *args):  # noqa: N802 - OCCT's name
                return False if isinstance(args[0], io.BytesIO) else image.Save(*args)

        folder = tempfile.mkdtemp(prefix="picture-")
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        with mock.patch.object(tempfile, "tempdir", folder):
            found = context.pixels(NoStream())
        np.testing.assert_array_equal(found, context.pixels(image))
        self.assertEqual(found[2, 1].tolist(), [255, 0, 0])
        self.assertEqual(os.listdir(folder), [])

    def test_an_opengl_1_1_context_is_no_canvas_though_it_hands_a_picture_over(self) -> None:
        # Windows' GDI Generic (a CI runner with no GPU driver) is OpenGL 1.1: OCCT draws nothing on
        # it. Once its pictures hand over (#709), its version is what says so.
        from types import SimpleNamespace

        from OCP.Image import Image_AlienPixMap, Image_Format

        image = Image_AlienPixMap()
        image.InitZero(Image_Format.Image_Format_RGB, 16, 16, 0, 0)
        gl = SimpleNamespace(IsGlGreaterEqual=lambda major, minor: (1, 1) >= (major, minor),
                             VersionMajor=lambda: 1, VersionMinor=lambda: 1)
        canvas = SimpleNamespace(pixmap=lambda: image, close=lambda: None,
                                 driver=SimpleNamespace(GetSharedContext=lambda: gl))
        with mock.patch.object(context, "Canvas", return_value=canvas), mock.patch.object(context, "_DRAWS", []):
            self.assertIn("OpenGL 1.1 is older than 2.1", context.available())


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
        from cad.engine.render.service import Held

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
        from cad.engine.snapshot import packet_visibility

        packet = {"annotation": {"marks": []}, "views": [], "hidden": ["block"], "isolated": ["bench"]}
        self.assertEqual(packet_visibility(packet), {"hidden": ["block"], "isolated": ["bench"]})
        self.assertEqual(packet_visibility({"marks": []}), {}, "an annotation file holds none")
        self.assertEqual(parse_display('{"hidden": ["block"]}', False), {"hidden": ["block"]})
        with self.assertRaisesRegex(SnapshotRefused, "display.isolated is a list of part refs"):
            parse_display('{"isolated": "block"}', False)

    def test_the_edge_classes_named_are_the_lines_drawn_and_the_others_are_left_out(self) -> None:
        """``display.edges`` names the edge classes drawn, by the mesh's and the viewer's names for them: with
        ``feature`` alone each part's tangent and seam lines are not drawn, so a cylinder's seam and a fillet's ends
        leave no line on a shaded part; the faces are as they were."""
        self.assertEqual(parse_display("solid,edges=feature", False), {"mode": "solid", "edges": {"classes": ["feature"]}})
        self.assertEqual(parse_display('{"edges": {"classes": ["feature", "seam"]}}', False),
                         {"edges": {"classes": ["feature", "seam"]}})
        for given in ("edges=dotted", '{"edges": "feature"}', '{"edges": {"classes": []}}',
                      '{"edges": {"classes": ["seam", "seam"]}}', '{"edges": {"enabled": true}}'):
            with self.subTest(given=given), self.assertRaisesRegex(
                    SnapshotRefused, "display.edges is .*the edge classes drawn, each once, of feature, tangent, seam"):
                parse_display(given, False)
        every = pixels(self.draw(display={"mode": "solid"})[0])
        scene = self.held.scenes[False]
        drawn = len(scene.shown)
        smooth = sum(1 for index, instance in enumerate(scene.structure["instances"]) if index not in scene.hidden
                     for line in ("tangent", "seam") if line in scene.parts[instance["prototype"]].edges)
        self.assertGreater(smooth, 0, "the fixture has a seam or a tangent line to leave out")
        sharp = pixels(self.draw(display={"mode": "solid", "edges": {"classes": ["feature"]}})[0])
        self.assertEqual(drawn - len(scene.shown), smooth)
        differing = np.abs(sharp.astype(int) - every.astype(int)).max(-1) > 8
        self.assertTrue(0 < differing.mean() < 0.05, "lines gone, and nothing else changed")
        self.assertLess(mismatch(pixels(self.draw(display={"mode": "solid"})[0]), every), 0.001, "and back again")

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

    def test_a_picture_stands_on_the_flat_colour_it_asks_for_and_the_next_on_the_look_s_own(self) -> None:
        """A job's ``output.background``: the backdrop is that colour, flat, to its corners; hidden-line's
        faces, which are the backdrop's colour, take it too; and a picture that asks for none is as before."""
        asked, colour = "#202830", np.array([0x20, 0x28, 0x30])
        plain = pixels(self.draw(display={"mode": "solid"})[0])
        data, report = self.draw(display={"mode": "solid"}, background=asked)
        dark = pixels(data)
        self.assertEqual(report["background"], asked)
        for corner in (dark[0, 0], dark[0, -1], dark[-1, 0], dark[-1, -1]):
            self.assertLessEqual(np.abs(corner.astype(int) - colour).max(), 1)
        self.assertGreater(np.abs(plain[0, 0].astype(int) - colour).max(), 100, "the look's own backdrop is pale")
        # The model is drawn as it was: only what was backdrop changed.
        model = np.abs(plain.astype(int) - plain[0, 0].astype(int)).max(-1) > 40
        same = np.abs(dark[model].astype(int) - plain[model].astype(int)).max(-1) <= 2
        self.assertGreater(same.mean(), 0.75, "but for its edges, and what is seen through its glass")
        hidden = pixels(self.draw(display={"mode": "hidden-line"}, background=asked)[0])
        self.assertGreater((np.abs(hidden.astype(int) - colour).max(-1) <= 1).mean(), 0.9, "faces and backdrop alike")
        again, report = self.draw(display={"mode": "solid"})
        self.assertNotIn("background", report)
        self.assertLess(mismatch(pixels(again), plain), 0.001)

    def test_a_picture_reports_the_camera_it_settled_on_and_that_camera_draws_it_again_exactly(self) -> None:
        """The report's ``settledCamera`` is the fitted camera as a job's view holds one: drawn exactly (no fit)
        it is the same picture, and it frames a picture of fewer parts the same way, where a fit
        would have filled the frame with them."""
        for projection in ("orthographic", "perspective"):
            with self.subTest(projection=projection):
                display = {"mode": "solid", "camera": {"projection": projection}}
                data, report = self.draw((320, 240), display=display, camera="35:20")
                view = report["settledCamera"]
                self.assertEqual(sorted(view), sorted(["position", "target", "up"]
                                                      + (["orthographicHalfHeight"] if projection == "orthographic" else [])))
                again, pinned = self.draw((320, 240), display=display, camera=view, exact=True)
                self.assertLess(mismatch(pixels(again), pixels(data)), 0.001)
                for key, value in view.items():
                    np.testing.assert_allclose(pinned["settledCamera"][key], value, atol=1e-9)

    def test_x_ray_is_the_colour_only_model_and_gives_the_look_back(self) -> None:
        """X-ray draws the look's colour-only model (``look.py``) on OCCT's Phong program: a part's
        material is its colour alone, so the fixture with its materials taken away draws the same;
        and the next mode is drawn under the look's own PBR rig again, as if X-ray never was."""
        from OCP.Graphic3d import Graphic3d_TypeOfShadingModel

        from cad.engine.render.look import LOOK
        from cad.engine.render.service import Held

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
        from cad.engine.render.explode import placed_box

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

    def test_preview_tone_maps_the_model_as_the_viewer_does_and_leaves_its_studio_as_drawn(self) -> None:
        """three's NeutralToneMapping, which OCCT's raster has none of: the sheen a dielectric adds taken
        off a dark colour, a middle one kept, a bright one eased under 1. Laid over the model's pixels
        alone, so the studio's floor and backdrop (drawn in the viewer's finished colours) stay as drawn."""
        from cad.engine.render.occt import neutral

        mapped = neutral(np.array([[0.02, 0.02, 0.02], [0.5, 0.5, 0.5], [1.0, 1.0, 1.0], [4.0, 4.0, 4.0]]))
        np.testing.assert_allclose(mapped[:, 0], [6.25 * 0.02 ** 2, 0.46, 1 - 0.24 ** 2 / 0.44, 1 - 0.24 ** 2 / 3.44],
                                   atol=1e-9)
        found = pixels(self.draw(display={}, preview=True)[0])
        scene = self.held.scenes[True]
        bare = scene.canvas.frame()  # the frame as OCCT draws it, before the painter
        model = scene._tone().any(-1)
        self.assertTrue(0.05 < model.mean() < 0.95, "the model and its studio are both in the frame")
        np.testing.assert_array_equal(found[~model], bare[~model])
        self.assertTrue((found[model].astype(int) <= bare[model].astype(int) + 1).all(), "tone mapping adds no light")
        self.assertLess(found[model].mean(), bare[model].mean() - 2)
        np.testing.assert_array_equal(scene.canvas.frame(), bare, "the studio is put back behind the model")

    def test_a_new_version_s_scenes_are_new_and_draw_as_the_last_did(self) -> None:
        """A version replaced: its scenes let go of whole between pictures and made again, and
        Preview's environment lights the new scene as it lit the last (a scene collected while
        another drew took that one's environment map with it)."""
        from cad.engine.render.service import Held

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
        from cad.engine.render.service import Held

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
        from cad.engine.render.grid import round_step

        for target, expected in ((1.0, (1.0, 1)), (1.4, (1.0, 1)), (1.5, (2.0, 2)), (3.0, (2.0, 2)), (3.3, (5.0, 5)),
                                 (7.0, (5.0, 5)), (7.2, (10.0, 1)), (0.031, (0.02, 2)), (450.0, (500.0, 5))):
            step, digit = round_step(target)
            self.assertAlmostEqual(step, expected[0], msg=target)
            self.assertEqual(digit, expected[1], target)

    def test_the_paper_of_a_model_at_rest(self) -> None:
        from cad.engine.render.grid import paper

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

        from cad.engine.mesh import mesh_shape
        from cad.engine.render.occt import Scene

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
        from cad.engine.render.clip import CAP
        from cad.engine.render.grid import hex_colour, to_linear, to_srgb
        from cad.engine.render.look import LOOK

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


class SeeThroughTest(unittest.TestCase):
    """A translucent part lying on an opaque one -- a pane resting on a dark box, as the orbit clock's diffuser rests
    on its baffle -- drawn whole: where its faces lie at the box's depth, it is in front of the box at every pixel
    (``occt.SEE_THROUGH_OFFSET``), never decided pixel by pixel in shards along each one's triangles."""

    def test_a_pane_resting_on_a_box_is_one_colour_through_its_top(self) -> None:
        gl()
        import build123d as bd

        from cad.engine.mesh import mesh_shape
        from cad.engine.render.occt import Scene

        base, pane = mesh_shape(bd.Box(30, 30, 10).wrapped), mesh_shape(bd.Box(20, 20, 4).wrapped)
        identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
        resting = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 7, 1]  # column-major: its bottom on the box's top, z 5
        structure = {"prototypes": [{"key": "base", "color": [0.011, 0.012, 0.014, 1]},
                                    {"key": "pane", "color": [0.9, 0.9, 0.85, 0.5]}],
                     "instances": [{"prototype": 0, "matrix": identity}, {"prototype": 1, "matrix": resting}]}
        scene = Scene(Path("pane.xbf"), {"base": base.to_bytes(), "pane": pane.to_bytes()}, size=SIZE, structure=structure)
        self.addCleanup(scene.canvas.close)
        scene.show({"mode": "solid"})
        scene.frame("iso")
        # Points of the pane's top (z 9) whose ray from the iso camera, (-1, 1, -0.8), leaves through its bottom
        # face (at x - 5, y + 5), clear of its edges: through each, the pane's two faces over the box's top.
        xs, ys = np.meshgrid(np.linspace(-3, 8, 12), np.linspace(-8, 3, 12))
        at = np.rint(scene.project(np.stack([xs.ravel(), ys.ravel(), np.full(xs.size, 9.0)], -1))).astype(int)
        seen = pixels(scene.canvas.png())[at[:, 1], at[:, 0]]
        spread = int(np.abs(seen - np.median(seen, 0)).max())
        self.assertLessEqual(spread, 4, f"the pane over the box varies by {spread} levels: shards where it lies on it")


def setUpModule() -> None:
    # The registry and cache of every engine this module starts are its own, never the developer's
    # (``engine_daemon.isolate``); each test still names its own engine folder.
    from tests.python.support import engine_daemon

    engine_daemon.isolate(unittest.addModuleCleanup)


if __name__ == "__main__":
    unittest.main()
