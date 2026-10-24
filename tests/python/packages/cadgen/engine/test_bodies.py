"""Body retention: a model body whose bytes are what they were is not run; its last run is
replayed, its result the same objects and its trace the one a run leaves -- so names, the
file and the caller's own calls are what they would be had it run."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest import mock

import build123d as bd

from cadgen.engine import build as engine_build
from cadgen.engine import document
from cadgen.engine.kernel import memo

SHARED = """
WIDTH = {width}
"""

LEFT = """
import build123d as bd
from cadgen.engine import xbf
from shared import WIDTH


@xbf("XBF/left.xbf")
def left():
    plate = bd.fillet(bd.Box(WIDTH, 8, 3).edges().filter_by(bd.Axis.Z), 1)
    plate = plate - bd.Cylinder(1.5, 10)
    plate.label = "left"
    return plate
"""

RIGHT = """
import build123d as bd
from cadgen.engine import xbf
from shared import WIDTH


@xbf("XBF/right.xbf")
def right():
    return bd.Box(WIDTH, 4, 4) - bd.Pos(1, 0, 0) * bd.Box(2, 2, 10)
"""

BOUGHT = """
from pathlib import Path

import build123d as bd
from cadgen.engine import xbf, read_step


@xbf("XBF/bought.xbf")
def bought():
    return read_step(Path(__file__).parent / "bought.step")
"""

ROOT = """
import build123d as bd
from cadgen.engine import xbf
from left import left
from right import right
from bought import bought

HOLE = {hole}


@xbf("XBF/root.xbf")
def root():
    before = bd.Box(1, 1, 1)
    one = left().shape
    two = left().shape.moved(bd.Location((0, 20, 0)))
    two.label = "two"
    plate = left().shape.moved(bd.Location((0, 40, 0))) - bd.Pos(3, 40, 0) * bd.Cylinder(HOLE, 10)
    plate.label = "plate"
    after = bd.Box(1, 1, 1).moved(bd.Location((0, -20, 0)))
    after.label = "after"
    before.label = "before"
    return bd.Compound(children=[one, two, plate, right().shape.moved(bd.Location((40, 0, 0))),
                                 bought().shape.moved(bd.Location((-40, 0, 0))), before, after], label="root")
"""


def _counts(report: dict) -> tuple[int, int]:
    return report["memo"]["bodies_run"], report["memo"]["bodies_skipped"]


def _replays_unchanged(case: unittest.TestCase) -> None:
    """Body retention is what these tests watch, on unchanged builds too: the whole-model skip
    a warm worker takes when its document holds the model's key (``build._previous``, held by
    test_previous) is set aside, so an unchanged root is replayed as a body."""
    patch = mock.patch.object(engine_build, "_as_built", return_value=False)
    patch.start()
    case.addCleanup(patch.stop)


class BodiesCase(unittest.TestCase):
    def setUp(self) -> None:
        memo.clear()
        engine_build._WRITTEN.clear()
        engine_build._PARTS.clear()
        self.addCleanup(memo.clear)
        _replays_unchanged(self)
        patch = mock.patch.dict(os.environ)
        patch.start()
        self.addCleanup(patch.stop)
        os.environ.pop("CADGEN_ENGINE_BODIES", None)
        os.environ.pop("CADGEN_ENGINE_MEMO", None)
        self.folder = Path(tempfile.mkdtemp(prefix="engine-bodies-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.write("shared.py", SHARED.format(width=10))
        self.write("left.py", LEFT)
        self.write("right.py", RIGHT)
        self.write("bought.py", BOUGHT)
        self.write("root.py", ROOT.format(hole=1.0))
        self.stock(3)

    def write(self, name: str, text: str) -> None:
        path = self.folder / name
        path.write_text(textwrap.dedent(text), encoding="utf-8")
        os.utime(path, ns=(time.time_ns(), time.time_ns()))

    def stock(self, size: float) -> None:
        path = self.folder / "bought.step"
        bd.export_step(bd.Compound(children=[bd.Solid.make_box(size, 2, 2)]), str(path))
        os.utime(path, ns=(time.time_ns(), time.time_ns()))

    def build(self) -> dict:
        report = engine_build.build(self.folder / "root.py", ["root"], cwd=self.folder)[-1]
        self.assertTrue(report["ok"], report)
        return report

    def document(self) -> tuple[bytes, dict]:
        path = self.folder / "XBF/root.xbf"
        loaded = document.load(path)
        return path.read_bytes(), {p.name: (dict(p.face_names), dict(p.edge_names)) for p in loaded.prototypes}


class RetentionTest(BodiesCase):
    def test_names_and_the_file_are_the_same_whether_a_child_ran_or_was_replayed(self) -> None:
        self.build()
        self.write("root.py", ROOT.format(hole=1.25))
        report = self.build()
        self.assertEqual(_counts(report), (1, 3), "the root ran, its three children were replayed")
        replayed = self.document()
        # The same sources built by a process that has run nothing: every body runs.
        memo.clear()
        engine_build._WRITTEN.clear()
        engine_build._PARTS.clear()
        (self.folder / "XBF/root.xbf").unlink()
        self.assertEqual(_counts(self.build()), (4, 0))
        ran = self.document()
        self.assertEqual(replayed[1], ran[1], "every element name")
        self.assertTrue(any(names[0] for names in ran[1].values()))
        self.assertEqual(replayed[0], ran[0], "the xbf's bytes")

    def test_an_edit_in_a_module_two_bodies_import_reruns_both(self) -> None:
        self.build()
        self.write("shared.py", SHARED.format(width=12))
        self.assertEqual(_counts(self.build()), (3, 1), "left, right and the root ran; bought was replayed")

    def test_a_changed_file_input_reruns_the_body_that_reads_it(self) -> None:
        self.build()
        self.stock(5)
        report = self.build()
        # The reader ran, and the root whose result holds it; left and right were replayed.
        self.assertEqual(_counts(report), (2, 2))
        self.assertGreater(report["memo"]["misses"], 0)

    def test_an_edit_in_the_root_reruns_the_root_alone(self) -> None:
        self.build()
        self.write("root.py", ROOT.format(hole=1.5))
        report = self.build()
        self.assertEqual(_counts(report), (1, 3))
        self.assertEqual(_counts(self.build()), (0, 4), "nothing changed: the root and its children are replayed")

    def test_a_replayed_child_placed_twice_is_still_one_prototype(self) -> None:
        self.build()
        self.write("root.py", ROOT.format(hole=1.5))
        report = self.build()
        self.assertEqual(_counts(report), (1, 3))
        self.assertEqual(report["named"], 1, "only the newly cut plate: the replayed child's part is the run's own")
        structure = document.load(self.folder / "XBF/root.xbf").structure()
        by_path = {i["path"]: i["prototype"] for i in structure["instances"]}
        self.assertEqual(by_path["root/left"], by_path["root/two"])
        self.assertNotEqual(by_path["root/left"], by_path["root/plate"])

    def test_the_report_and_the_stats_count_bodies_run_and_skipped(self) -> None:
        before = memo.stats()
        self.assertEqual(_counts(self.build()), (4, 0))
        self.assertEqual(_counts(self.build()), (0, 4))
        after = memo.stats()
        self.assertEqual((after["bodies_run"] - before["bodies_run"], after["bodies_skipped"] - before["bodies_skipped"]),
                         (4, 4))


class OrdinalTest(BodiesCase):
    def test_a_caller_s_calls_are_keyed_alike_whether_its_child_ran_or_was_replayed(self) -> None:
        # The root makes the same box before and after calling its children: a replayed
        # child makes no call, so the root's ordinals -- and what it hits -- are the same.
        self.build()
        self.write("root.py", ROOT.format(hole=1.5))
        replayed = self.build()["memo"]
        memo.clear()
        self.write("root.py", ROOT.format(hole=1.0))
        os.environ["CADGEN_ENGINE_BODIES"] = "0"
        self.build()
        self.write("root.py", ROOT.format(hole=1.5))
        ran = self.build()["memo"]
        self.assertEqual(_counts({"memo": ran}), (4, 0))
        self.assertEqual(replayed["misses"], ran["misses"], "the root missed the same calls")
        root_calls = replayed["hits"] + replayed["misses"]
        self.assertLess(replayed["misses"], root_calls, "its unchanged calls hit")


DIMENSIONS = '''
"""Dimensions the parts share."""
import build123d as bd

WIDTH = 10.0
HEIGHT = {height}
SPARE = 1.0


def plate(width):
    """A plate."""
    return bd.Box(width, 8, {thickness})


def {spare}():
    return SPARE
'''

HELPERS = """
import build123d as bd
from dimensions import plate


def holed(width):
    return plate(width) - bd.Cylinder(1, 10)
"""

BRACKET = """
from cadgen.engine import xbf
from dimensions import WIDTH
from helpers import holed


@xbf("XBF/bracket.xbf")
def bracket():
    return holed(WIDTH)
"""

SPACER = """
import build123d as bd
from cadgen.engine import xbf
import dimensions


@xbf("XBF/spacer.xbf")
def spacer():
    return bd.Box(dimensions.HEIGHT, 2, 2)
"""

PROBE = """
import build123d as bd
from cadgen.engine import xbf
import dimensions

WHICH = "HEI" + "GHT"


@xbf("XBF/probe.xbf")
def probe():
    return bd.Box(getattr(dimensions, WHICH), 3, 3)
"""

ASSEMBLY = """
import build123d as bd
from cadgen.engine import xbf
from bracket import bracket
from spacer import spacer


@xbf("XBF/assembly.xbf")
def assembly():
    return bd.Compound(children=[bracket().shape, spacer().shape.moved(bd.Location((30, 0, 0)))], label="assembly")
"""


class SymbolsCase(BodiesCase):
    """A body is keyed by the symbols its code reaches: ``bracket`` reaches ``holed`` and,
    through it, ``plate`` and ``WIDTH``; ``spacer`` reads ``HEIGHT`` off the module;
    ``probe`` reads a name it computes, so its module falls back to its bytes."""

    def setUp(self) -> None:
        super().setUp()
        self.dimensions(height=4.0)
        self.write("helpers.py", HELPERS)
        self.write("bracket.py", BRACKET)
        self.write("spacer.py", SPACER)
        self.write("probe.py", PROBE)
        self.write("assembly.py", ASSEMBLY)

    def dimensions(self, height: float = 4.0, thickness: float = 3.0, spare: str = "spare") -> None:
        self.write("dimensions.py", DIMENSIONS.format(height=height, thickness=thickness, spare=spare))

    def assemble(self) -> tuple[int, int]:
        report = engine_build.build(self.folder / "assembly.py", ["assembly"], cwd=self.folder)[-1]
        self.assertTrue(report["ok"], report)
        return _counts(report)

    def probe(self) -> dict:
        report = engine_build.build(self.folder / "probe.py", ["probe"], cwd=self.folder)[-1]
        self.assertTrue(report["ok"], report)
        return report


class SymbolsTest(SymbolsCase):
    def test_a_constant_edit_runs_the_bodies_that_read_it_and_replays_the_rest(self) -> None:
        self.assertEqual(self.assemble(), (3, 0))
        self.dimensions(height=5.0)
        self.assertEqual(self.assemble(), (2, 1), "spacer reads HEIGHT and the assembly holds it; bracket replayed")

    def test_an_edit_to_a_function_runs_every_body_that_reaches_it(self) -> None:
        self.assemble()
        self.dimensions(thickness=3.5)
        # bracket calls holed, which calls plate: two steps away, still its code.
        self.assertEqual(self.assemble(), (2, 1), "bracket and the assembly ran; spacer replayed")

    def test_comments_blank_lines_and_docstrings_run_nothing(self) -> None:
        self.assemble()
        text = (self.folder / "dimensions.py").read_text(encoding="utf-8")
        text = text.replace('"""Dimensions the parts share."""', '"""What the parts share."""\n\n# in millimetres')
        text = text.replace('    """A plate."""', '    """A plate,\n    drilled by its callers."""\n    # flat')
        self.write("dimensions.py", text)
        self.write("helpers.py", "# helpers\n\n\n" + HELPERS.replace("def holed(width):", 'def holed(width):\n    """Holed."""'))
        self.write("assembly.py", ASSEMBLY.replace("@xbf", "\n# the top\n@xbf"))
        self.assertEqual(self.assemble(), (0, 3))

    def test_a_computed_getattr_falls_back_to_its_module_s_bytes(self) -> None:
        self.probe()
        self.assertEqual(_counts(self.probe()), (0, 1))
        self.dimensions(spare="extra")  # nothing the probe names, but its module's bytes
        report = self.probe()
        self.assertEqual(_counts(report), (1, 0))
        reasons = report["retention"]["fallbacks"]["probe.py::probe"]
        self.assertTrue(any("getattr with a computed name" in reason for reason in reasons), reasons)
        # The assembly's bodies read nothing they cannot follow.
        self.assemble()
        self.dimensions(height=4.0, spare="other")
        self.assertEqual(self.assemble(), (0, 3))

    def test_renaming_runs_the_users_of_what_was_renamed_and_nothing_else(self) -> None:
        self.assemble()
        self.dimensions(spare="renamed")
        self.assertEqual(self.assemble(), (0, 3), "nothing reaches the renamed function")
        self.write("dimensions.py", DIMENSIONS.format(height=4.0, thickness=3.0, spare="renamed")
                   .replace("def plate(", "def slab("))
        self.write("helpers.py", HELPERS.replace("plate", "slab"))
        self.assertEqual(self.assemble(), (2, 1), "bracket reaches it and the assembly holds bracket")


READER = """
import json
import os
from pathlib import Path

import build123d as bd
from cadgen.engine import xbf

HERE = Path(__file__).parent
GAP = {gap}


def config():
    try:
        with open(HERE / "data.json", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return {{"width": 2}}


@xbf("XBF/reader.xbf")
def reader():
    return bd.Box(config()["width"], 1, 1)


@xbf("XBF/holder.xbf")
def holder():
    return bd.Compound(children=[reader().shape, bd.Pos(GAP, 0, 0) * bd.Box(1, 1, 1)])


@xbf("XBF/writer.xbf")
def writer():
    with open(HERE / "note.txt", "w", encoding="utf-8") as handle:
        handle.write("built")
    return bd.Box(1, 1, 1)


@xbf("XBF/piped.xbf")
def piped():
    handle = os.open(HERE / "pipe", os.O_RDONLY | os.O_NONBLOCK)
    try:
        data = os.read(handle, 16)
    finally:
        os.close(handle)
    return bd.Box(float(data or 4), 1, 1)
"""


RAW = """
import build123d as bd
from build123d.topology.shape_core import downcast
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
from cadgen.engine import xbf


@xbf("XBF/raw.xbf")
def raw():
    peg = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), 2.0, 5.0).Shape()
    return bd.Compound(children=[bd.Solid(downcast(peg)), bd.Box(3, 3, 3)])
"""


class UncachedTest(BodiesCase):
    def test_the_report_names_each_call_that_ran_uncached_and_the_remedy(self) -> None:
        # A shape OCCT made past the memo's list has no key, so the build123d call given it runs
        # uncached and the body is never retained: the build says which call, how often, and why.
        self.write("raw.py", RAW)
        report = engine_build.build(self.folder / "raw.py", ["raw"], cwd=self.folder)[-1]
        self.assertTrue(report["ok"], report)
        self.assertGreater(report["memo"]["uncached"], 0)
        reasons = report["retention"]["fallbacks"]["raw.py::raw"]
        self.assertTrue(any(reason.startswith("runs build123d's ") and " uncached (" in reason
                            and "make that shape with build123d's operation" in reason for reason in reasons), reasons)


# build123d's sum of sketches starts from an empty one: ``bd.Sketch() + [a, b]`` fuses with an
# empty shape as the boolean's own operand.
SUMMED = """
import build123d as bd
from cadgen.engine import model


@model
def summed():
    teeth = bd.Sketch() + [bd.Rot(0, 0, a) * bd.Rectangle(20, 2) for a in (0, 60, 120)]
    return bd.extrude(teeth, amount=3)
"""


class EmptyShapeTest(BodiesCase):
    def test_a_sum_that_starts_from_an_empty_sketch_is_keyed_and_replays(self) -> None:
        self.write("summed.py", SUMMED)
        statuses = []
        for _ in range(2):
            report = engine_build.build(self.folder / "summed.py", ["summed"], cwd=self.folder)[-1]
            self.assertTrue(report["ok"], report)
            self.assertEqual((report["memo"]["uncached"], report["retention"]["fallbacks"]), (0, {}))
            statuses.append(report["bodies"]["summed.py::summed"])
        self.assertEqual(statuses, ["run", "replayed"])


class ReadTracingTest(unittest.TestCase):
    """A file a body reads itself is one of its inputs, by its bytes (``_audited``,
    ``_ReadInput``): the body is replayed while they stay and runs when they change or the
    file goes; a file opened for writing is no input; a pipe keeps the body running."""

    def setUp(self) -> None:
        memo.clear()
        self.addCleanup(memo.clear)
        _replays_unchanged(self)
        self.folder = Path(tempfile.mkdtemp(prefix="engine-reads-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.script = self.folder / "reader.py"
        self.data = self.folder / "data.json"

    def put(self, path: Path, text: str) -> None:
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8")
            os.utime(path, ns=(time.time_ns(), time.time_ns()))

    def build(self, width: int | None, gap: int = 10, model: str = "holder") -> dict:
        self.put(self.script, textwrap.dedent(READER.format(gap=gap)))
        if width is None:
            self.data.unlink(missing_ok=True)
        else:
            self.put(self.data, json.dumps({"width": width}))
        report = engine_build.build(self.script, [model], cwd=self.folder)[-1]
        self.assertTrue(report["ok"], report)
        return report

    def width(self, model: str = "holder") -> float:
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib

        bounds = Bnd_Box()
        BRepBndLib.Add_s(document.load(self.folder / f"XBF/{model}.xbf").prototypes[0].shape, bounds)
        return bounds.CornerMax().X() - bounds.CornerMin().X()

    def test_a_body_that_loads_a_file_replays_on_a_no_op(self) -> None:
        first = self.build(3)
        self.assertEqual(first["retention"]["reads"], {"reader.py::reader": ["data.json"]})
        self.assertEqual(first["retention"]["fallbacks"], {})
        again = self.build(3)
        self.assertEqual(_counts(again), (0, 2), "a no-op replays the holder and the reader")
        self.assertEqual(again["retention"]["reads"], {"reader.py::reader": ["data.json"]})

    def test_it_runs_when_the_file_s_bytes_change(self) -> None:
        self.build(3)
        changed = self.build(5)
        self.assertEqual(_counts(changed), (2, 0), "the reader runs, and its holder")
        self.assertAlmostEqual(self.width(), 5.0, places=3)
        self.assertEqual(_counts(self.build(5)), (0, 2))
        # The holder's code and the file change together: the holder runs, and the reader's
        # check reads the new file inside it -- the engine's read, not the holder's.
        self.assertEqual(_counts(self.build(7, gap=12)), (2, 0))
        self.assertEqual(_counts(self.build(7, gap=12)), (0, 2))
        self.assertAlmostEqual(self.width(), 7.0, places=3)

    def test_a_file_touched_with_the_same_bytes_is_hashed_once(self) -> None:
        self.build(3)
        os.utime(self.data, ns=(time.time_ns() + 10**9, time.time_ns() + 10**9))
        with mock.patch.object(memo, "_read_digest", wraps=memo._read_digest) as digest:
            self.assertEqual(_counts(self.build(3)), (0, 2), "the same bytes under a new mtime")
            self.assertEqual(digest.call_count, 1)
            self.assertEqual(_counts(self.build(3)), (0, 2))
            self.assertEqual(digest.call_count, 1, "the new stat was kept: no second hash")

    def test_it_runs_when_the_file_is_deleted_and_when_it_comes_back(self) -> None:
        self.build(3)
        gone = self.build(None)
        self.assertEqual(_counts(gone), (2, 0))
        self.assertAlmostEqual(self.width(), 2.0, places=3)
        self.assertEqual(_counts(self.build(None)), (0, 2), "still missing: replayed")
        self.assertEqual(_counts(self.build(6)), (2, 0), "the file came back")
        self.assertAlmostEqual(self.width(), 6.0, places=3)

    def test_a_file_opened_for_writing_changes_nothing(self) -> None:
        first = self.build(3, model="writer")
        self.assertEqual(first["retention"]["reads"], {})
        self.assertEqual(first["retention"]["fallbacks"], {})
        self.assertEqual(_counts(self.build(3, model="writer")), (0, 1))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "no named pipes on this platform")
    def test_a_pipe_read_always_runs_and_is_reported(self) -> None:
        os.mkfifo(self.folder / "pipe")
        self.build(3, model="piped")
        again = self.build(3, model="piped")
        self.assertEqual(_counts(again), (1, 0))
        self.assertEqual(again["retention"]["reads"], {})
        self.assertEqual(again["retention"]["fallbacks"],
                         {"reader.py::piped": ["reads pipe, not a regular file: it runs on every build"]})


if __name__ == "__main__":
    unittest.main()
