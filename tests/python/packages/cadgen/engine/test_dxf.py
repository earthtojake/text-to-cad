"""Drawings: ``@dxf`` on a model whose body returns 2D geometry, a derived file of its planar
document written by build123d's own DXF exporter -- a part per layer, millimetres, the drawing
checks; the same bytes cold, warm and from its xbf; an edit that costs what it changed; a child
model's files; and what a DXF cannot hold, refused by name."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from collections import Counter
from pathlib import Path

import ezdxf

from cadgen.engine import api
from cadgen.engine import build as engine_build
from cadgen.engine.export import ExportRefused, translate
from cadgen.engine.export import dxf as engine_dxf
from cadgen.engine.model import dxf

SRC = Path(__file__).resolve().parents[5] / "packages" / "cadgen" / "src"

DRAWINGS = """
import build123d as bd
from cadgen.engine import dxf, xbf

HOLE = {hole}


@xbf("XBF/plate.xbf")
@dxf("plate.dxf")
def plate():
    with bd.BuildSketch() as cut:
        bd.RectangleRounded(80, 50, 8)
        bd.Circle(12, mode=bd.Mode.SUBTRACT)
        with bd.GridLocations(60, 30, 2, 2):
            bd.Circle(HOLE / 2, mode=bd.Mode.SUBTRACT)
    crosshair = bd.Compound([bd.Line((-16, 0), (16, 0)), bd.Line((0, -16), (0, 16))])
    bend = bd.Line((30, -25), (30, 25))
    sheet = cut.sketch
    sheet.label, crosshair.label, bend.label = "CUT", "ENGRAVE", "BEND"
    return bd.Compound(children=[sheet, crosshair, bend], label="plate")


@dxf("gasket.dxf")
def gasket():
    with bd.BuildSketch() as cut:
        bd.Rectangle(60, 40)
        with bd.GridLocations(50, 30, 2, 2):
            bd.Circle(2.25, mode=bd.Mode.SUBTRACT)
    return cut.sketch


@dxf("forward.dxf")
def forward():
    a, b = bd.Rectangle(10, 5).face(), bd.Pos(20, 0) * bd.Circle(3).face()
    mark = bd.Pos(0, 20) * bd.Rot(0, 0, 30) * bd.Rectangle(4, 2).face()
    cut, mark.label = bd.Compound([a, b], label="CUT"), "ENGRAVE"
    return bd.Compound(children=[cut, mark])


@dxf("backward.dxf")
def backward():
    a, b = bd.Rectangle(10, 5).face(), bd.Pos(20, 0) * bd.Circle(3).face()
    mark = bd.Pos(0, 20) * bd.Rot(0, 0, 30) * bd.Rectangle(4, 2).face()
    cut, mark.label = bd.Compound([b, a], label="CUT"), "ENGRAVE"
    return bd.Compound(children=[mark, cut])
"""

REFUSED = """
import build123d as bd
from cadgen.engine import dxf, xbf


@xbf("XBF/solid.xbf")
@dxf("solid.dxf")
def solid():
    return bd.Box(1, 2, 3)


@dxf("lifted.dxf")
def lifted():
    return bd.Pos(0, 0, 5) * bd.Rectangle(10, 5).face()


@dxf("open_cut.dxf")
def open_cut():
    return bd.Compound([bd.Line((0, 0), (10, 0)), bd.Line((10, 0), (10, 5))])


@dxf("doubled.dxf")
def doubled():
    a, b = bd.Rectangle(10, 5).face(), bd.Rectangle(10, 5).face()
    a.label, b.label = "CUT", "CUT"
    return bd.Compound(children=[a, b])


@dxf("slashed.dxf")
def slashed():
    a, b = bd.Rectangle(9, 6).face(), bd.Pos(20, 0) * bd.Circle(3).face()
    a.label, b.label = "CUT/2", "CUT"
    return bd.Compound(children=[a, b])
"""

BRACKET = """
import build123d as bd
from cadgen.engine import xbf


@xbf("XBF/bracket.xbf")
def bracket():
    return bd.Box(40, 20, 3, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)) - bd.Cylinder(3, 10)
"""

FLAT = """
import build123d as bd
from cadgen.engine import dxf

from bracket import bracket


@dxf("flat.dxf")
def flat():
    return bd.Pos(0, 0, -3) * bracket().shape.faces().sort_by(bd.Axis.Z)[-1]
"""


def _write(path: Path, text: str) -> Path:
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    os.utime(path, ns=(time.time_ns(), time.time_ns()))  # a rewrite in the same tick is a new file
    return path


def _built(script: Path, *functions: str) -> dict[str, dict]:
    reports = engine_build.build(script, list(functions) or None, cwd=script.parent)
    return {report["model"].rsplit("::", 1)[-1]: report for report in reports}


def _entities(path: Path) -> Counter:
    return Counter((entity.dxftype(), entity.dxf.layer) for entity in ezdxf.readfile(str(path)).modelspace())


class DrawingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.folder = Path(tempfile.mkdtemp(prefix="engine-dxf-")).resolve()
        cls.script = _write(cls.folder / "drawings.py", DRAWINGS.format(hole=5))
        cls.reports = _built(cls.script)
        cls.plate = cls.folder / "plate.dxf"
        cls.bytes = cls.plate.read_bytes()

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.folder, ignore_errors=True)

    def test_a_drawing_is_a_layer_per_part_in_millimetres_and_checks_clean(self) -> None:
        report = self.reports["plate"]
        self.assertTrue(report["ok"], report)
        self.assertEqual([Path(path).name for path in report["files"]], ["plate.xbf", "plate.dxf"])
        self.assertEqual(ezdxf.readfile(str(self.plate)).header["$INSUNITS"], 4)
        # Curves stay curves: the rounded corners ARCs, the holes CIRCLEs; open lines on their layers.
        self.assertEqual(_entities(self.plate), Counter({("ARC", "CUT"): 4, ("LINE", "CUT"): 4, ("CIRCLE", "CUT"): 5,
                                                         ("LINE", "ENGRAVE"): 2, ("LINE", "BEND"): 1}))
        self.assertEqual(engine_dxf.validate_dxf_file(self.plate), [])
        # One shape is the layer CUT, and a model with no @xbf writes its DXF alone.
        self.assertEqual(set(_entities(self.folder / "gasket.dxf")), {("LINE", "CUT"), ("CIRCLE", "CUT")})
        self.assertFalse((self.folder / "XBF/gasket.xbf").exists())

    def test_the_order_of_layers_and_edges_is_the_content_s(self) -> None:
        self.assertTrue(self.reports["forward"]["ok"] and self.reports["backward"]["ok"], self.reports)
        self.assertEqual((self.folder / "forward.dxf").read_bytes(), (self.folder / "backward.dxf").read_bytes())
        lines = [line.strip() for line in self.bytes.decode("utf-8").split("\n")]
        for header, value in (("$FINGERPRINTGUID", "{00000000-0000-0000-0000-000000000000}"),
                              ("$TDCREATE", "2451545.0"), ("$TDUUPDATE", "2451545.0")):
            self.assertEqual(lines[lines.index(header) + 2], value, header)
        start = lines.index("CLASSES")
        names = [lines[at + 2] for at in range(start, lines.index("ENDSEC", start)) if lines[at] == "CLASS"]
        self.assertEqual(names, sorted(names))
        volatile = "0\nSECTION\n2\nHEADER\n9\n$VERSIONGUID\n2\n{1D5A0B2C-0000-0000-0000-000000000001}\n0\nENDSEC\n"
        with self.assertRaisesRegex(engine_dxf.DxfDeterminismError, r"\$VERSIONGUID"):
            engine_dxf._check_pinned(volatile, "rig")

    def test_the_bytes_are_one_cold_warm_and_from_the_xbf(self) -> None:
        # A fresh process -- its own hash seed, its memo cold, the body run (no xbf to take) --
        # finds these bytes in the drawing and leaves it, stat and all.
        xbf = self.folder / "XBF/plate.xbf"
        document, stat = xbf.read_bytes(), self.plate.stat().st_mtime_ns
        xbf.unlink()
        probe = "import json, drawings; print(json.dumps(drawings.plate.build(daemon=False).models[0]['files']))"
        done = subprocess.run([sys.executable, "-B", "-c", probe], cwd=self.folder, capture_output=True, text=True,
                              env={**os.environ, "PYTHONPATH": str(SRC)}, timeout=600)
        self.assertEqual(done.returncode, 0, done.stderr)
        files = json.loads(done.stdout.strip().splitlines()[-1])
        self.assertEqual({Path(path).name: row["written"] for path, row in files.items()},
                         {"plate.xbf": True, "plate.dxf": False})
        self.assertEqual((xbf.read_bytes(), self.plate.stat().st_mtime_ns), (document, stat))
        # Warm: a file gone is written again from the replayed body, the same bytes.
        self.plate.unlink()
        warm = _built(self.script, "plate")["plate"]
        self.assertEqual(warm["bodies"], {"drawings.py::plate": "replayed"})
        self.assertEqual(self.plate.read_bytes(), self.bytes)
        # And an export of the xbf, read from the file, writes them: `cadgen export plate.xbf
        # plate.dxf` in a process that never built it.
        again = self.folder / "again.dxf"
        translate(self.folder / "XBF/plate.xbf", None, again)
        self.assertEqual(again.read_bytes(), self.bytes)
        [written] = api.export(self.folder / "XBF/plate.xbf", self.folder / "verb.dxf", daemon=False)
        self.assertEqual((written.kind, written.path.read_bytes()), ("dxf", self.bytes))

    def test_a_drawing_takes_out_alone_and_a_dxf_path(self) -> None:
        with self.assertRaisesRegex(TypeError, "unexpected keyword argument.*layer"):
            dxf("a.dxf", layer="CUT")
        with self.assertRaisesRegex(ValueError, r"must end in \.dxf"):
            dxf(out="a.step")


class DrawingEditTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="engine-dxf-edit-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)

    def test_an_edit_costs_what_it_changed(self) -> None:
        script = _write(self.folder / "drawings.py", DRAWINGS.format(hole=5))
        cold = _built(script, "plate", "gasket")
        first = (self.folder / "plate.dxf").read_bytes()
        self.assertEqual(cold["plate"]["memo"]["hits"], 0)
        _write(script, DRAWINGS.format(hole=6))
        edited = _built(script, "plate", "gasket")
        # The holes are made again; the outline, the cut-out and the marks are the memo's.
        self.assertGreater(edited["plate"]["memo"]["misses"], 0)
        self.assertGreater(edited["plate"]["memo"]["hits"], edited["plate"]["memo"]["misses"])
        self.assertTrue(edited["plate"]["files"][str(self.folder / "plate.dxf")]["written"])
        self.assertNotEqual((self.folder / "plate.dxf").read_bytes(), first)
        # A model the edit does not reach is replayed, its file kept.
        self.assertEqual(edited["gasket"]["bodies"], {"drawings.py::gasket": "replayed"})
        self.assertFalse(edited["gasket"]["files"][str(self.folder / "gasket.dxf")]["written"])
        # Put back, it is the first drawing again, every call a hit.
        _write(script, DRAWINGS.format(hole=5))
        back = _built(script, "plate")["plate"]
        self.assertEqual(back["memo"]["misses"], 0)
        self.assertEqual((self.folder / "plate.dxf").read_bytes(), first)

    def test_a_model_the_drawing_calls_writes_its_own_files(self) -> None:
        _write(self.folder / "bracket.py", BRACKET)
        [report] = _built(_write(self.folder / "flat.py", FLAT)).values()
        self.assertTrue(report["ok"], report)
        self.assertEqual([Path(path).name for path in report["child_models"]["bracket.py::bracket"]["files"]],
                         ["bracket.xbf"])
        self.assertEqual(sorted(path.relative_to(self.folder).as_posix() for path in self.folder.rglob("*")
                                if path.is_file()), ["XBF/bracket.xbf", "bracket.py", "flat.dxf", "flat.py"])
        self.assertEqual(_entities(self.folder / "flat.dxf"), Counter({("LINE", "CUT"): 4, ("CIRCLE", "CUT"): 1}))


class RefusedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.folder = Path(tempfile.mkdtemp(prefix="engine-dxf-refused-")).resolve()
        cls.reports = _built(_write(cls.folder / "refused.py", REFUSED))

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.folder, ignore_errors=True)

    def refused(self, name: str) -> str:
        report = self.reports[name]
        self.assertFalse(report["ok"], report)
        self.assertFalse((self.folder / f"{name}.dxf").exists(), "nothing is written")
        return report["error"]

    def test_a_3d_document_is_refused_by_the_build_and_the_export(self) -> None:
        self.assertIn("solid is 3D: a DXF is drawn from 2D geometry a model returns", self.refused("solid"))
        # The xbf, written first, is no planar document either.
        with self.assertRaisesRegex(ExportRefused, "solid.xbf is 3D"):
            translate(self.folder / "XBF/solid.xbf", None, self.folder / "solid.dxf")

    def test_an_edge_off_the_plane_is_refused_by_its_name(self) -> None:
        error = self.refused("lifted")
        self.assertRegex(error, r"lifted: e:lifted\.\S+ \(edge \d+ of lifted/\w+\) is off the XY plane")
        self.assertIn("z=5", error)

    def test_what_the_drawing_checks_find_refuses_the_file(self) -> None:
        self.assertIn("[error] open_cut_profile: cut layer 'CUT'", self.refused("open_cut"))
        self.assertIn("[error] duplicate_entity", self.refused("doubled"))
        self.assertIn("'CUT/2' names a layer, and a DXF layer name may not hold '/'", self.refused("slashed"))


class DrawingChecksTest(unittest.TestCase):
    """The checks, on documents made here: what each finds, and what it lets through."""

    def document(self, units: int = 4) -> ezdxf.document.Drawing:
        document = ezdxf.new("R2010", setup=True)
        document.header["$INSUNITS"] = units
        return document

    def codes(self, document: ezdxf.document.Drawing, **options: bool) -> set[str]:
        return {finding.code for finding in engine_dxf.validate_drawing_document(document, **options)}

    def test_layer_intent_is_read_from_whole_tokens(self) -> None:
        for name, intent in (("BEND", "bend"), ("bend-lines", "bend"), ("ENGRAVE_TEXT", "engrave"),
                             ("REF_GEOMETRY", "reference"), ("DIMENSIONS", "reference"), ("CUT_SECTION", "cut"),
                             ("PREFORM", "cut"), ("KEYNOTES", "cut")):
            self.assertEqual(engine_dxf.layer_intent(name), intent, name)

    def test_a_cut_chain_closes_through_ends_a_rounding_apart_and_fails_open(self) -> None:
        document = self.document()
        modelspace = document.modelspace()
        # Two ends of one corner, under a micron apart, either side of a rounding boundary.
        for start, end in (((0, 0), (10.0000004, 0)), ((10.0000006, 0), (10, 10)), ((10, 10), (0, 10)),
                           ((0, 10), (0, 0))):
            modelspace.add_line(start, end, dxfattribs={"layer": "CUT"})
        self.assertEqual(self.codes(document), set())
        modelspace.add_line((20, 0), (30, 0), dxfattribs={"layer": "CUT"})
        self.assertEqual(self.codes(document), {"open_cut_profile"})
        modelspace.add_line((20, 5), (30, 5), dxfattribs={"layer": "SCORE_BEND"})
        self.assertEqual(self.codes(document), {"open_cut_profile"}, "open geometry on a bend layer is allowed")

    def test_units_degenerate_entities_duplicates_and_an_empty_drawing_are_errors(self) -> None:
        document = self.document(units=0)
        modelspace = document.modelspace()
        modelspace.add_line((1, 1), (1, 1))
        modelspace.add_circle((5, 5), 2)
        modelspace.add_circle((5, 5), 2)
        self.assertEqual(self.codes(document), {"units_not_set", "zero_length_entity", "duplicate_entity"})
        self.assertEqual(self.codes(self.document()), {"empty_drawing"})

    def test_a_file_that_says_it_is_a_drawing_needs_no_closed_cuts(self) -> None:
        document = self.document()
        modelspace = document.modelspace()
        modelspace.add_line((0, 0), (10, 0), dxfattribs={"layer": "OUTLINE"})
        self.assertEqual(self.codes(document), {"open_cut_profile"})
        self.assertEqual(self.codes(document, drawing=True), {"drawing_document"})
        modelspace.add_linear_dim(base=(0, 5), p1=(0, 0), p2=(10, 0)).render()
        self.assertEqual(self.codes(document), {"drawing_document"})
        # A layer the file does not plot, or draws dashed, is construction, not a cut path.
        layered = self.document()
        layered.layers.add("KORPUS").dxf.plot = 0
        layered.modelspace().add_line((0, 0), (10, 0), dxfattribs={"layer": "KORPUS"})
        self.assertEqual(self.codes(layered), set())


if __name__ == "__main__":
    unittest.main()
