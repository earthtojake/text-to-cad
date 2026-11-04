"""`cad <type> snapshot --job` replays a board view as a Quick Edit saved it: its window, its Display, its ink.

A Quick Edit on a board writes a job packet (`cad_server.viewer.prompt_files`): each view a plan-view
camera (the window the board view showed, in the plot's plan frame, y up) and the board's Display,
and the annotation once, its marks on the board in the sheet's millimetres (y down). This renders
such a packet through the real Python -> native renderer path and reads the PIXELS back: the window frames
what the camera names, and the ink lands on the board where it was drawn — from below, at its
mirrored place, as the view drew it.

The board is the test board (`tests/python/support/kicad_board.py`): no KiCad, no corpus model.
One packet; no browser or KiCad process.
"""

from __future__ import annotations

import json
import unittest
import tempfile
from pathlib import Path

from tests.python.support.engine_daemon import isolate
from tests.python.support.kicad_board import UUIDS, write_board
from tests.python.support.paths import add_repo_path
from PIL import Image

add_repo_path("packages/cad/src")

SIZE = (400, 300)
# The whole 40 x 30 mm sheet in a 400 x 300 picture: the plan view centred on the sheet's middle
# (20, -15: y up), 16 mm above and below. 9.375 px per mm, the sheet's corner at (12.5, 9.375).
PLAN = {"target": [20, -15, 0], "position": [20, -15, 60], "up": [0, 1, 0], "orthographicHalfHeight": 16}
SCALE, OFFSET_X, OFFSET_Y = 300 / 32, 200 - 20 * 300 / 32, 150 - 15 * 300 / 32
MAGENTA = (255, 0, 255)


def on_screen(x: float, y: float) -> tuple[int, int]:
    """A sheet point (y down) where the plan view above draws it, seen from the top."""
    return round(x * SCALE + OFFSET_X), round(y * SCALE + OFFSET_Y)


def near(pixel, other, tolerance=60) -> bool:
    return sum(abs(a - b) for a, b in zip(pixel, other)) <= tolerance


class BoardJobReplayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        isolate(cls.addClassCleanup)
        cls.folder = tempfile.TemporaryDirectory(prefix="pcb-snapshot-")
        cls.addClassCleanup(cls.folder.cleanup)
        workspace = Path(cls.folder.name)
        board = write_board(workspace)
        # The ink a person drew across the board's top-left, on the sheet.
        annotation = workspace / "board.annotation.json"
        annotation.write_text(json.dumps({"units": "mm", "marks": [
            {"id": "1", "kind": "stroke", "points": [3, 3, 0, 11, 3, 0], "color": "#ff00ff", "width": 14}]}), encoding="utf-8")

        def job(name: str, display: dict) -> dict:
            return {"input": str(board), "camera": PLAN, "display": display,
                    "outputs": [{"path": str(workspace / f"{name}.png"), "width": SIZE[0], "height": SIZE[1]}]}

        packet = workspace / "board.snapshot.json"
        packet.write_text(json.dumps({"annotation": str(annotation), "jobs": [
            job("top", {"mode": "board", "side": "top", "poured": True}),
            # The view's theme as the viewer's packet carries it: KiCad's colours on the dark canvas.
            job("darktop", {"mode": "board", "side": "top", "poured": True, "appearance": "dark"}),
            job("below", {"mode": "copper", "side": "bottom", "poured": False}),
            job("assembly", {"mode": "assembly"}),
            job("placement", {"mode": "placement"}),
            job("outline", {"layers": ["Edge.Cuts"]}),
            # The Layers' own: Dim with the front copper active, and the zones' fill at nothing.
            job("dim", {"mode": "board", "dim": True}),
            # Hidden: the front copper alone, with the outline and the holes through it.
            job("hidden", {"mode": "board", "others": "hidden"}),
            job("nozones", {"mode": "board", "zones": 0}),
            job("unpoured", {"mode": "board", "poured": False}),
            # What a prompt named, lit as the view lit it: the VBUS track, R1, an area round the text, a point.
            {**job("lit", {"mode": "board", "side": "top", "poured": True}),
             "references": [f"#track:{UUIDS['vbus track']}", "#R1", "#F.SilkS@x14y3..x26y7", "#@x5y25", f"#via:{UUIDS['pour']}"]},
        ]}), encoding="utf-8")

        from cad.engine.api import snapshot

        cls.result = snapshot(job=packet, daemon=False)
        cls.images = {p.stem: Image.open(p).convert("RGB") for p in workspace.glob("*.png")}

    def test_each_view_is_written_at_its_size(self) -> None:
        self.assertEqual(11, len(self.result))
        # Every key the command line prints a snapshot by, as every other kind's report has it.
        for drawn in self.result:
            self.assertIs(False, drawn.report["preview"])
        self.assertEqual(["assembly", "below", "darktop", "dim", "hidden", "lit", "nozones", "outline", "placement", "top", "unpoured"], sorted(self.images))
        for name, image in self.images.items():
            self.assertEqual(SIZE, (image.width, image.height), name)

    def test_the_ink_lands_on_the_board_where_it_was_drawn_and_mirrored_from_below(self) -> None:
        top, below = self.images["top"], self.images["below"]
        x, y = on_screen(7, 3)
        mirrored = round((40 - 7) * SCALE + OFFSET_X)
        self.assertTrue(near(top.getpixel((x, y)), MAGENTA), f"the stroke where it was drawn: {top.getpixel((x, y))}")
        self.assertFalse(near(top.getpixel((mirrored, y)), MAGENTA), f"and nowhere else: {top.getpixel((mirrored, y))}")
        self.assertTrue(near(below.getpixel((mirrored, y)), MAGENTA), f"from below, at its mirrored place: {below.getpixel((mirrored, y))}")
        self.assertFalse(near(below.getpixel((x, y)), MAGENTA), f"not where the top view had it: {below.getpixel((x, y))}")

    def test_display_presets_select_copper_and_placement_pads(self) -> None:
        point = on_screen(30, 15)
        copper = (200, 52, 52)
        self.assertTrue(near(self.images["top"].getpixel(point), copper, 25))
        for name in ("assembly", "placement", "outline"):
            self.assertFalse(near(self.images[name].getpixel(point), copper, 25), name)
        pad = on_screen(35.825, 15.3)  # off the airwire through the pin centre
        self.assertTrue(near(self.images["placement"].getpixel(pad), copper, 50))
        self.assertFalse(near(self.images["outline"].getpixel(pad), copper, 50))

    def test_dim_fades_all_but_the_active_layer_and_the_zones_take_their_opacity(self) -> None:
        pour, track = on_screen(8, 22), on_screen(30, 15)  # the GND pour on B.Cu; the VBUS track on F.Cu, active
        top, dim = self.images["top"], self.images["dim"]
        self.assertFalse(near(top.getpixel(pour), dim.getpixel(pour), 30), f"the back pour fades: {top.getpixel(pour)} -> {dim.getpixel(pour)}")
        self.assertTrue(near(top.getpixel(track), dim.getpixel(track), 25), f"the active copper does not: {dim.getpixel(track)}")
        # The zones at 0 draw the pour's fill as no fill at all.
        self.assertTrue(near(self.images["nozones"].getpixel(pour), self.images["unpoured"].getpixel(pour), 10))

    def test_hidden_draws_the_active_layer_alone_but_the_outline_and_the_holes_through_it(self) -> None:
        top, hidden = self.images["top"], self.images["hidden"]
        area = hidden.getpixel(on_screen(30, 26))  # the board's own ground, where no layer of the front draws
        pour, track = on_screen(8, 22), on_screen(30, 15)  # the GND pour on B.Cu; the VBUS track on F.Cu, active
        self.assertTrue(near(hidden.getpixel(pour), area, 12), f"the back pour is gone: {hidden.getpixel(pour)}")
        self.assertTrue(near(hidden.getpixel(track), top.getpixel(track), 25), f"the active copper stays: {hidden.getpixel(track)}")
        # The outline, the via's hole and J1's pad hole as the full board draws them.
        for x, y in ((0.05, 25), (18, 27), (5, 17.54)):
            point = on_screen(x, y)
            self.assertTrue(near(hidden.getpixel(point), top.getpixel(point), 30), f"({x}, {y}) kept: {hidden.getpixel(point)} vs {top.getpixel(point)}")

    def test_what_the_prompt_named_is_lit_and_what_names_nothing_said(self) -> None:
        lit, top = self.images["lit"], self.images["top"]
        blue = (68, 122, 176)  # the light theme's highlight: the viewer's blue darkened to read on white
        for x, y in ((20, 15), (35.825, 15)):  # the VBUS track, R1's pad 2
            point = on_screen(x, y)
            self.assertTrue(near(lit.getpixel(point), blue, 40), f"lit at ({x}, {y}): {lit.getpixel(point)}")
            self.assertFalse(near(top.getpixel(point), blue, 40), f"and only where named: {top.getpixel(point)}")
        # The area's box, an edge of it: (14, 5) on its left side.
        self.assertTrue(near(lit.getpixel(on_screen(14, 5)), blue, 60), lit.getpixel(on_screen(14, 5)))
        [report] = [drawn.report for drawn in self.result if Path(drawn.path).stem == "lit"]
        self.assertTrue(any("is not lit: blinky.kicad_pcb has no via" in warning for warning in report["warnings"]), report["warnings"])

    def test_the_window_is_the_camera_s_on_the_canvas_of_its_appearance(self) -> None:
        top, dark = self.images["top"], self.images["darktop"]
        # The plan view frames the sheet with a millimetre to spare above and below: the corners are the
        # surround, the canvas of the still's appearance — light as every snapshot is unless it says dark.
        self.assertTrue(near(top.getpixel((2, 2)), (255, 255, 255), 6), f"the light canvas: {top.getpixel((2, 2))}")
        self.assertTrue(near(dark.getpixel((2, 2)), (41, 41, 41), 30), f"the dark canvas: {dark.getpixel((2, 2))}")
        # On the board, where nothing is drawn, the board's area: a shade darker than white, a shade lighter than the dark grey.
        self.assertTrue(near(top.getpixel(on_screen(30, 26)), (237, 237, 237), 12), f"the board's area: {top.getpixel(on_screen(30, 26))}")
        self.assertTrue(near(dark.getpixel(on_screen(30, 26)), (62, 62, 62), 30), f"the board's area: {dark.getpixel(on_screen(30, 26))}")
        # KiCad's copper is its red in both: the VBUS track.
        track = on_screen(30, 15)
        self.assertTrue(near(top.getpixel(track), dark.getpixel(track), 25), f"the copper: {top.getpixel(track)} / {dark.getpixel(track)}")

    def test_a_display_string_takes_a_mode_and_an_appearance_as_every_snapshot_s(self) -> None:
        from cad.engine.render.board import display_options
        from cad.engine.snapshot import SnapshotRefused

        self.assertEqual(("copper", "dark"), tuple(display_options("copper,dark")[key] for key in ("mode", "appearance")))
        self.assertEqual(("board", "dark"), tuple(display_options("dark")[key] for key in ("mode", "appearance")))
        self.assertEqual("light", display_options("copper")["appearance"])
        with self.assertRaises(SnapshotRefused):
            display_options("copper,assembly")


class BoardDisplayTest(unittest.TestCase):
    """The Display a snapshot reads, as the viewer's `plot2d/boardDisplay.js` reads it."""

    LAYERS = [{"id": "area", "kind": "area"}, {"id": "B.Cu", "kind": "copper"},
              {"id": "Edge.Cuts", "kind": "outline"}, {"id": "F.Cu", "kind": "copper"}, {"id": "vias", "kind": "via"}]

    def test_a_set_naming_the_old_drawing_sheet_draws_the_rest(self) -> None:
        from cad.engine.render.board import display_options, viewed_layers

        drawn = lambda value: [layer["id"] for layer in viewed_layers(self.LAYERS, display_options(value))]
        self.assertEqual(["area", "B.Cu", "Edge.Cuts", "F.Cu", "vias"], drawn({}))
        # A set saved when a board had a drawing sheet still draws what else it names, and is not refused.
        self.assertEqual(["F.Cu"], drawn({"layers": ["sheet", "F.Cu"]}))

    def test_the_active_layer_tops_the_stack_and_the_layers_own_are_checked(self) -> None:
        from cad.engine.render.board import active_layer, display_options, viewed_layers
        from cad.engine.snapshot import SnapshotRefused

        drawn = lambda value: [layer["id"] for layer in viewed_layers(self.LAYERS, display_options(value))]
        self.assertEqual(["area", "Edge.Cuts", "F.Cu", "B.Cu", "vias"], drawn({"active": "B.Cu"}))
        self.assertEqual("F.Cu", active_layer(self.LAYERS, display_options({})))
        self.assertEqual("B.Cu", active_layer(self.LAYERS, display_options({"side": "bottom"})))
        self.assertEqual("F.Cu", active_layer(self.LAYERS, display_options({"active": "area"})), "the board's area is no active layer")
        # Others: three choices; the earlier dim switch read as they say it, true as dimmed.
        self.assertEqual(["dimmed", "shown", "hidden", "hidden"], [display_options(value)["others"] for value in
                         ({"dim": True}, {"dim": False}, {"others": "hidden"}, {"others": "hidden", "dim": True})])
        self.assertNotIn("dim", display_options({"dim": True}))
        for wrong in ({"dim": "yes"}, {"zones": 2}, {"tracks": True}, {"active": 3}, {"others": "faded"}):
            with self.assertRaises(SnapshotRefused):
                display_options(wrong)

if __name__ == "__main__":
    unittest.main()
