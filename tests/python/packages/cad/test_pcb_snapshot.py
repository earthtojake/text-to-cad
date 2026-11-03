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
from tests.python.support.kicad_board import write_board
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
            job("below", {"mode": "copper", "side": "bottom", "poured": False}),
            job("assembly", {"mode": "assembly"}),
            job("placement", {"mode": "placement"}),
            job("outline", {"layers": ["Edge.Cuts"]}),
        ]}), encoding="utf-8")

        from cad.engine.api import snapshot

        cls.result = snapshot(job=packet, daemon=False)
        cls.images = {p.stem: Image.open(p).convert("RGB") for p in workspace.glob("*.png")}

    def test_each_view_is_written_at_its_size(self) -> None:
        self.assertEqual(5, len(self.result))
        # Every key the command line prints a snapshot by, as every other kind's report has it.
        for drawn in self.result:
            self.assertIs(False, drawn.report["preview"])
        self.assertEqual(["assembly", "below", "outline", "placement", "top"], sorted(self.images))
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

    def test_the_window_is_the_camera_s(self) -> None:
        top = self.images["top"]
        # The plan view frames the sheet with a millimetre to spare above and below: the corners are the
        # surround, KiCad's canvas (the board's background), off the page the board is drawn on.
        self.assertTrue(near(top.getpixel((2, 2)), (0, 16, 35), 30), f"KiCad's canvas: {top.getpixel((2, 2))}")
        # On the board, where nothing is drawn, the board's area shadow lies over that canvas (KiCad's 35% grey).
        self.assertTrue(near(top.getpixel(on_screen(30, 26)), (35, 45, 58), 30), f"the board's area: {top.getpixel(on_screen(30, 26))}")


if __name__ == "__main__":
    unittest.main()
