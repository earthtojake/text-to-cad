"""`cadgen pcb snapshot --job` replays a board view as a Quick Edit saved it: its window, its Display, its ink.

A Quick Edit on a board writes a job packet (`cadgen.viewer.prompt_files`): each view a plan-view
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

add_repo_path("packages/cadgen/src")

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

        from cadgen.pcb import snapshot

        cls.result = snapshot(job=packet, daemon=False)
        cls.images = {p.stem: Image.open(p).convert("RGB") for p in workspace.glob("*.png")}

    def test_each_view_is_written_at_its_size(self) -> None:
        self.assertEqual(5, len(self.result))
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
        # The plan view frames the sheet with a millimetre to spare above and below: the corners are the surround.
        self.assertTrue(near(top.getpixel((2, 2)), (255, 255, 255), 30), f"the light surround: {top.getpixel((2, 2))}")


class NativeBoardFlow(unittest.TestCase):
    def test_cli_and_mcp_snapshot_use_the_current_native_file(self):
        import os
        import subprocess
        import sys
        from cadgen.mcp.operations import Operations
        from cadgen.jobs import TERMINAL
        isolate(self.addCleanup)
        with tempfile.TemporaryDirectory(prefix="pcb-flow-") as folder:
            root = Path(folder)
            board = write_board(root)
            png = root / "cli.png"
            env = {**os.environ, "CADGEN_LAUNCHER_DIR": str(root / "bin")}
            command = [sys.executable, "-c", "from cadgen.cli import main; raise SystemExit(main())",
                       "pcb", "snapshot", str(board), str(png), "--width", "320", "--height", "240", "--json"]
            done = subprocess.run(command, env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(done.returncode, 0, done.stderr)
            json.loads(done.stdout)
            with Image.open(png) as image:
                self.assertEqual(image.size, (320, 240))
            first = png.read_bytes()
            board.write_text(board.read_text(encoding="utf-8").replace('(width 1) (layer "F.Cu") (net "VBUS")',
                              '(width 3) (layer "F.Cu") (net "VBUS")'), encoding="utf-8")
            jobs = Operations()
            started = jobs.call("cad_snapshot", {"requestId": "native-board-snapshot-1", "source": str(board),
                                "output": str(png), "width": 320, "height": 240})
            with jobs.changed:
                self.assertTrue(jobs.changed.wait_for(lambda: jobs.jobs[started["id"]]["state"] in TERMINAL, timeout=30))
            result = jobs.get(started["id"])
            self.assertEqual(result["state"], "succeeded", result)
            self.assertNotEqual(png.read_bytes(), first)
