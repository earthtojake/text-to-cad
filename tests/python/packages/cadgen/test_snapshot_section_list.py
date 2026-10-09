"""`cadgen step snapshot --mode section` and `--mode list`: cadgen's facts, through the real door.

The cut is cadgen's: an OCCT section of each part's exact BREP (a build-pool job), drawn as a
2D payload the snapshot page paints and written as SVG by cadgen itself. These run the verb on
a tiny assembly built here -- a 20 x 10 x 5 plate at the origin and a radius-5 pin standing at
x = 30 -- and read back what was written:

* the PNG is the cut, framed as a section always was, with the pin a true circle -- and the
  same assembly ten kilometres out draws the same picture;
* an SVG output is cadgen's, so a job with only SVG outputs never starts a browser;
* focus/hide pick what is cut, and a plane that misses says so;
* `--mode list` is answered from the tree and the store, with no browser: the refs every
  selector resolves, the parts' exact boxes, and the stored meshes' counts.
"""

from __future__ import annotations

import json
import math
import re
import unittest
from unittest import mock

from tests.python.support.cad_test_roots import ClassCadRoots
from tests.python.support.paths import add_repo_path
from tests.python.support.png import read_png

add_repo_path("packages/cadgen/src")

SIZE = (400, 300)
PIN = (30.0, 0.0, 5.0)  # centre x, centre y, radius
# Where the far copy of the assembly stands: ten kilometres out along every axis.
FAR = 1e7


def write_assembly(path, at: float = 0.0) -> None:
    from build123d import Compound, Location, Solid
    from cadgen.step_export import export_build123d_step_file

    plate = Solid.make_box(20, 10, 5).moved(Location((at, at, at)))
    plate.label = "plate"
    pin = Solid.make_cylinder(PIN[2], 20).moved(Location((PIN[0] + at, PIN[1] + at, at)))
    pin.label = "pin"
    export_build123d_step_file(Compound(children=[plate, pin], label="asm"), path)


def browser_refused(*_args, **_kwargs):
    raise AssertionError("a browser was started")


class SnapshotSectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._roots = ClassCadRoots(prefix="snapshot-section-")
        cls.workspace = cls._roots.cad_root
        write_assembly(cls.workspace / "asm.step")
        write_assembly(cls.workspace / "far.step", at=FAR)
        import cadgen.step as step_door

        cls.step = step_door
        packet = {"jobs": [
            {"input": "asm.step", "mode": "section", "section": {"plane": "XY", "offset": 2},
             "outputs": [{"path": "cut.png", "width": SIZE[0], "height": SIZE[1]}, {"path": "cut.svg"}]},
            {"input": "asm.step", "mode": "section", "section": {"plane": "XY", "offset": 50},
             "outputs": [{"path": "miss.png", "width": SIZE[0], "height": SIZE[1]}]},
            {"input": "far.step", "mode": "section", "section": {"plane": "XY", "offset": FAR + 2},
             "outputs": [{"path": "far.png", "width": SIZE[0], "height": SIZE[1]}]},
        ]}
        job = cls.workspace / "packet.json"
        job.write_text(json.dumps(packet), encoding="utf-8")
        cls.result = step_door.snapshot(job=job)
        cls.image = read_png((cls.workspace / "cut.png").read_bytes())
        cls.far_image = read_png((cls.workspace / "far.png").read_bytes())
        cls.svg = (cls.workspace / "cut.svg").read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._roots.cleanup()

    def screen(self, x: float, y: float) -> tuple[int, int]:
        """Where the page puts model (x, y): the old framing, 12% of the short side clear."""
        min_x, min_y, max_x, max_y = 0.0, -5.0, 35.0, 10.0
        padding = max(20, min(SIZE) * 0.12)
        scale = min((SIZE[0] - 2 * padding) / (max_x - min_x), (SIZE[1] - 2 * padding) / (max_y - min_y))
        return (round(SIZE[0] / 2 + (x - (min_x + max_x) / 2) * scale),
                round(SIZE[1] / 2 - (y - (min_y + max_y) / 2) * scale))

    def test_every_output_was_written_and_the_miss_is_said(self) -> None:
        self.assertTrue(self.result.ok)
        self.assertEqual(["cut.png", "cut.svg", "far.png", "miss.png"],
                         sorted(file.path.name for file in self.result.files))
        self.assertEqual({"png", "svg"}, {file.kind for file in self.result.files})
        self.assertEqual(SIZE, (self.image.width, self.image.height))
        self.assertEqual(["SECTION XY @ Z=50.000 cuts no material; the section is empty"],
                         list(self.result.warnings))

    def assert_the_exact_cut(self, image) -> None:
        background = image.pixel(2, 2)
        self.assertEqual((255, 255, 255), background)
        # Inside the plate and the pin: the grey fill, not the background.
        for point in ((10.0, 5.0), (PIN[0] + 2.5, PIN[1] - 2.5)):
            x, y = self.screen(*point)
            self.assertLess(sum(image.pixel(x, y)), 3 * 245, f"{point} is not filled")
        # The pin's outline crosses its exact radius at every angle: a dark ring there. (Its
        # upper half: the cut locator sits over the bottom right corner of a small picture.)
        for angle in range(0, 180, 30):
            radians = math.radians(angle + 15)
            x, y = self.screen(PIN[0] + PIN[2] * math.cos(radians), PIN[1] + PIN[2] * math.sin(radians))
            darkest = min(sum(image.pixel(x + dx, y + dy)) for dx in (-1, 0, 1) for dy in (-1, 0, 1))
            self.assertLess(darkest, 3 * 120, f"no outline at {angle + 15} degrees")

    def test_the_png_is_the_exact_cut_where_the_old_framing_put_it(self) -> None:
        self.assert_the_exact_cut(self.image)

    def test_a_cut_ten_kilometres_out_is_drawn_as_cleanly_as_at_the_origin(self) -> None:
        # The page paints in 32-bit floats: drawn in model coordinates this far out, the pin
        # came out jagged and lost its outline. (The framing is centred, so the same pixels.)
        self.assert_the_exact_cut(self.far_image)

    def test_the_svg_draws_the_pin_as_its_exact_circle(self) -> None:
        self.assertIn('transform="scale(1 -1)"', self.svg)
        outlines = re.findall(r'<path d="([^"]+)"[^>]*stroke-width="3"', self.svg)
        curves = [command for outline in outlines for command in re.findall(r"C ([^A-Z]+)", outline)]
        self.assertEqual(4, len(curves), outlines)
        for curve in curves:
            x, y = map(float, curve.split()[4:6])
            self.assertAlmostEqual(PIN[2], math.hypot(x - PIN[0], y - PIN[1]), places=3)

    def test_an_svg_only_job_is_cadgens_alone_and_focus_picks_what_is_cut(self) -> None:
        from cadgen import snapshot_core

        out = self.workspace / "plate-only.svg"
        with mock.patch.object(snapshot_core.BatchSnapshotRenderer, "start", browser_refused):
            result = self.step.snapshot(self.workspace / "asm.step", out, mode="section", section="XY:2",
                                        focus=("#o1.1",))
        self.assertTrue(result.ok)
        svg = out.read_text(encoding="utf-8")
        # The plate's outline: its four corners, one closed loop, whichever corner it starts at.
        [outline] = re.findall(r'<path d="([^"]+)"[^>]*stroke-width="3"', svg)
        self.assertRegex(outline, r"^M [-\d. ]+( L [-\d. ]+){4} Z$")
        corners = {tuple(map(float, point.split())) for point in re.findall(r"[ML] ([-\d.]+ [-\d.]+)", outline)}
        self.assertEqual({(0.0, 0.0), (20.0, 0.0), (20.0, 10.0), (0.0, 10.0)}, corners)
        self.assertNotIn(" C ", svg, "the focused plate has no curve; the pin was cut too")


class SnapshotListTests(unittest.TestCase):
    """`--mode list` on a STEP model is cadgen's answer from the tree and the store: no browser."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._roots = ClassCadRoots(prefix="snapshot-list-")
        cls.workspace = cls._roots.cad_root
        write_assembly(cls.workspace / "asm.step")
        import cadgen.step as step_door
        from cadgen import snapshot_core

        cls.step = step_door
        with mock.patch.object(snapshot_core.BatchSnapshotRenderer, "start", browser_refused):
            cls.listing = step_door.snapshot(cls.workspace / "asm.step", mode="list")
            cls.focused = step_door.snapshot(cls.workspace / "asm.step", mode="list", focus=("#o1.2",))

    @classmethod
    def tearDownClass(cls) -> None:
        cls._roots.cleanup()

    def test_each_part_is_listed_with_its_exact_box_and_its_mesh_counts(self) -> None:
        self.assertTrue(self.listing.ok)
        self.assertEqual((), self.listing.files)
        rows = {row["ref"]: row for row in self.listing.parts}
        self.assertEqual(["#o1.1", "#o1.2"], list(rows))
        self.assertEqual({"ref", "name", "triangleCount", "vertexCount", "bounds"}, set(rows["#o1.1"]))
        self.assertEqual(("plate", "pin"), (rows["#o1.1"]["name"], rows["#o1.2"]["name"]))
        self.assertEqual({"min": [0, 0, 0], "max": [20, 10, 5]}, rows["#o1.1"]["bounds"])
        # The pin's exact box, from its BREP, placed at x = 30: not a tessellation's.
        self.assertEqual({"min": [25, -5, 0], "max": [35, 5, 20]}, rows["#o1.2"]["bounds"])
        # A box is two triangles a face, each face its own four vertices.
        self.assertEqual((12, 24), (rows["#o1.1"]["triangleCount"], rows["#o1.1"]["vertexCount"]))
        self.assertGreater(rows["#o1.2"]["triangleCount"], 12)

    def test_a_listed_ref_is_one_every_selector_resolves(self) -> None:
        from cadgen._internal.doors import document_snapshot
        from cadgen.assembly_lookup import assembly_occurrence_rows
        from cadgen.store.view import view_dir_for

        document, tree = document_snapshot(self.workspace / "asm.step")
        package = view_dir_for(tree, document_hash=document)
        descriptor = json.loads((package / "assembly.json").read_text(encoding="utf-8"))
        rows = assembly_occurrence_rows(descriptor, package)
        self.assertEqual([(f"#{row['id']}", row["name"]) for row in rows],
                         [(row["ref"], row["name"]) for row in self.listing.parts])

    def test_focus_lists_only_what_it_keeps(self) -> None:
        self.assertEqual(["#o1.2"], [row["ref"] for row in self.focused.parts])

    def test_listing_a_stored_model_loads_no_kernel(self) -> None:
        # The rows are read from the tree, its SURFs and the mesh index: a process that lists
        # (the snapshot CLI) never pays for OCCT. Run where nothing else has loaded it.
        import os
        import subprocess
        import sys

        from tests.python.support.paths import repo_path

        source = str(repo_path("packages/cadgen/src"))
        env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [source, os.environ.get("PYTHONPATH")]))}
        script = (
            "import json, sys\n"
            "from pathlib import Path\n"
            "from cadgen._internal.doors import document_snapshot\n"
            "from cadgen.store.view import view_dir_for\n"
            "from cadgen.snapshot_parts import list_rows\n"
            "from cadgen.tessellation_policy import DEFAULT_TESSELLATION\n"
            "document, tree = document_snapshot(Path(sys.argv[1]))\n"
            "package = view_dir_for(tree, document_hash=document)\n"
            "descriptor = json.loads((package / 'assembly.json').read_text())\n"
            "rows = list_rows(descriptor, package, selection=None, tessellation=DEFAULT_TESSELLATION)\n"
            "print(json.dumps([len(rows), sorted(name for name in sys.modules if name.split('.')[0] in ('OCP', 'build123d'))]))\n"
        )
        done = subprocess.run([sys.executable, "-c", script, str(self.workspace / "asm.step")],
                              capture_output=True, text=True, check=True, cwd=self.workspace, env=env)
        self.assertEqual([2, []], json.loads(done.stdout.strip().splitlines()[-1]), done.stderr)


class FilterOccurrencesTests(unittest.TestCase):
    ROWS = [{"id": "o1.1", "name": "plate"}, {"id": "o1.2.1", "name": "pin"}, {"id": "o1.2.2", "name": "nut"}]

    def keep(self, **selection):
        from cadgen.snapshot_parts import filter_occurrences

        return [row["id"] for row in filter_occurrences(self.ROWS, selection)]

    def test_a_ref_matches_its_id_its_group_or_its_name(self) -> None:
        self.assertEqual(["o1.1", "o1.2.1", "o1.2.2"], self.keep())
        self.assertEqual(["o1.2.1", "o1.2.2"], self.keep(focus=["#o1.2"]))
        self.assertEqual(["o1.2.2"], self.keep(focus=["nut"]))
        self.assertEqual(["o1.1", "o1.2.2"], self.keep(hide="#o1.2.1"))
        with self.assertRaisesRegex(ValueError, "No renderable parts remain"):
            self.keep(focus=["#o9"])


if __name__ == "__main__":
    unittest.main()
