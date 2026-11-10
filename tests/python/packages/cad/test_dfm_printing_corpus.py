#!/usr/bin/env python3

"""3D printing's planted-defect corpus: parts built with known defects -- and clean controls -- checked for
every technology (each STEP read and measured once, its rules judged per technology; one of them through
``cad.step.dfm`` too, the same verdicts) and a mesh path through ``cad.stl.dfm``, each rule's verdicts
compared with the construction: which rules must fire, where, and that nothing else does.

The ground truth is here, beside the parts: each planted defect is (rule id, the technologies whose
rules have a limit it breaks, its place, a radius). A failure the rules record
(``measurements["rules"]["outcomes"]``) within the radius of a planted defect of its rule is a true
positive; any other is a false positive; a planted defect with none is a false negative. Precision and
recall per rule id are printed to stderr and must be 1.0.

The edge cases: fillets everywhere and a spline-surfaced cup (controls), an inch STEP, a 1.5 mm part and
a 2 m one, an assembly, and the same parts as fine and coarse STLs.
"""

from __future__ import annotations

import math
import sys
import tempfile
import time
import unittest
from collections import defaultdict
from pathlib import Path

import build123d as bd
import numpy as np

import cad
from cad._internal import manufacturing
from cad._internal import meshops_printing as mo
from cad.build123d import _dfm_brep as brep
from cad.build123d import _dfm_printing as measured

A = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)
TOP = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX)
ALL = ("fdm", "sla", "sls", "mjf", "pbf")
SAMPLES = 800


def _named(shape, name: str):
    shape.label = name
    return shape


def _doc(name: str, *parts):
    return bd.Compound(children=list(parts), label=name) if len(parts) > 1 else _named(parts[0], name)


# --- the parts: each (document, planted defects [(rule, technologies, xyz, radius)], mesh planted or None) ---


def features():
    """Small positive and negative features on a 4 mm plate."""
    part = bd.Box(70, 40, 4, align=A)
    part += bd.Pos(-25, 10, 4) * bd.Box(0.4, 12, 8, align=A)                                    # fin 0.4
    cup = bd.Box(10, 10, 8, align=A) - bd.Box(9.4, 9.4, 20, align=A)                            # walls 0.3
    part += bd.Pos(-25, -10, 4) * cup
    part += bd.Pos(-5, 12, 4) * bd.Cylinder(0.2, 4, align=A)                                     # pin 0.4
    part -= bd.Pos(-5, -12, 0) * bd.Cylinder(0.2, 20)                                            # hole 0.4
    part -= bd.Pos(10, 10, 4) * bd.Box(0.3, 12, 2.5, align=TOP)                                  # slot 0.3
    part += bd.Pos(10, -10, 4) * bd.Box(2, 4, 0.05, align=A)                                     # emboss 0.05
    part -= bd.Pos(25, 0, 4) * bd.Box(0.2, 8, 0.2, align=TOP)                                    # engrave 0.2
    planted = [
        ("printing.wall_unsupported", ALL, (-25, 10, 8), 7.0),
        ("printing.wall_supported", ALL, (-25, -10, 8), 8.0),
        ("printing.pin_diameter", ("fdm", "sla", "sls", "mjf", "pbf"), (-5, 12, 6), 3.0),  # FDM: Xometry's 1 mm
        ("printing.pin_aspect", ("pbf",), (-5, 12, 6), 3.0),
        ("printing.hole_diameter", ("fdm", "sla", "sls", "pbf"), (-5, -12, 2), 3.0),
        ("printing.gap", ALL, (10, 10, 2.5), 7.0),
        ("printing.emboss_height", ALL, (10, -10, 4), 4.0),
        ("printing.engrave_depth", ("sla", "sls"), (25, 0, 4), 5.0),
        ("printing.engrave_width", ("sla", "pbf"), (25, 0, 4), 5.0),
        ("printing.gap", ALL, (25, 0, 4), 5.0),
    ]
    # a mesh's walls are read as exact geometry's are, their support off the wall itself; it has no axes: the
    # pin is a thin wall joined at its foot alone, the hole a gap, the steps not measured
    mesh = [
        ("printing.wall_unsupported", ALL, (-25, 10, 8), 7.0),
        ("printing.wall_supported", ALL, (-25, -10, 8), 8.0),
        ("printing.wall_unsupported", ALL, (-5, 12, 6), 3.0),
        ("printing.gap", ALL, (-5, -12, 2), 3.0),
        ("printing.gap", ALL, (10, 10, 2.5), 7.0),
        ("printing.gap", ALL, (25, 0, 4), 5.0),
    ]
    return _doc("features", part), planted, mesh


def spans():
    """A 25 mm bridge, a 10 deg overhang (its tip a 10 deg knife edge) and a 12 mm horizontal hole, three
    parts apart."""
    tunnel = bd.Box(40, 20, 10, align=A) - bd.Box(25, 40, 6, align=A)
    h = 30 * math.tan(math.radians(10))
    wedge = bd.Pos(30, 0, 0) * bd.Rotation(90, 0, 0) * bd.extrude(
        bd.make_face(bd.Polyline((0, 0), (30, h), (0, h), (0, 0))), 10)
    holed = bd.Pos(-45, 0, 0) * (bd.Box(24, 8, 20, align=A) - bd.Pos(0, 0, 10) * bd.Rotation(90, 0, 0) * bd.Cylinder(6, 20))
    planted = [
        ("printing.bridge_length", ("fdm", "sla"), (0, 0, 6), 17.0),
        ("printing.overhang_angle", ("pbf",), (0, 0, 6), 17.0),
        ("printing.overhang_angle", ("fdm", "sla", "pbf"), (45, 0, 2.6), 16.0),
        ("printing.horizontal_hole_diameter", ("pbf",), (-45, 0, 10), 6.0),
        ("printing.horizontal_hole", ("fdm",), (-45, 0, 10), 6.0),           # 12 mm: over FDM's 10
        ("printing.knife_edge", ALL, (60, -5, 5.29), 6.0),                    # its sliver is the knife's alone
    ]
    mesh = [
        ("printing.knife_edge", ALL, (60, -5, 5.29), 6.0),
        ("printing.bridge_length", ("fdm", "sla"), (0, 0, 6), 17.0),
        ("printing.overhang_angle", ("fdm", "sla"), (45, 0, 2.6), 16.0),
        ("printing.bridge_length", ("fdm",), (-45, 0, 15), 6.0),
    ]
    return _doc("spans", _named(tunnel, "tunnel"), _named(wedge, "wedge"), _named(holed, "holed")), planted, mesh


def hollows():
    """A sealed void, a hollow with a 2 mm drain and one with two 5 mm drains, 26 mm cubes, 5 mm walls."""
    def box(x: float):
        return bd.Pos(x, 0, 0) * (bd.Box(26, 26, 26, align=A) - bd.Pos(0, 0, 5) * bd.Box(16, 16, 16, align=A))

    sealed = box(-40)
    small = box(0) - bd.Pos(0, 0, -1) * bd.Cylinder(1, 8, align=A)
    drained = box(40) - bd.Pos(44, 0, -1) * bd.Cylinder(2.5, 8, align=A) - bd.Pos(36, 0, -1) * bd.Cylinder(2.5, 8, align=A)
    planted = [
        ("printing.escape_holes", ("sla", "sls", "mjf", "pbf"), (-40, 0, 13), 9.0),
        ("printing.escape_hole_diameter", ("sla", "sls", "mjf", "pbf"), (0, 0, 13), 9.0),
    ]
    for x in (-40, 0, 40):                                                   # each void's 16 mm ceiling
        planted += [("printing.bridge_length", ("fdm",), (x, 0, 21), 12.0),
                    ("printing.overhang_angle", ("pbf",), (x, 0, 21), 12.0)]
    mesh = [p for p in planted if "pbf" not in p[1] or len(p[1]) > 1]
    return _doc("hollows", _named(sealed, "sealed"), _named(small, "small"), _named(drained, "drained")), planted, mesh


def bar():
    """400 mm long: no technology's typical machine holds it, and the powder beds warp it."""
    planted = [("printing.build_volume", ALL, (0, 0, 3), 5.0),
               ("printing.warp_length", ("sls", "mjf"), (0, 0, 3), 5.0)]
    return _doc("bar", bd.Box(400, 20, 6, align=A)), planted, planted


def assembly():
    """Two blocks 0.1 mm apart and a third 2 mm off: the first pair fuses."""
    a = _named(bd.Box(10, 10, 6, align=A), "a")
    b = _named(bd.Pos(10.1, 0, 0) * bd.Box(10, 10, 6, align=A), "b")
    c = _named(bd.Pos(22.1, 0, 0) * bd.Box(10, 10, 6, align=A), "c")
    planted = [("printing.clearance", ALL, (5.05, 0, 3), 6.0)]
    return _doc("assembly", a, b, c), planted, planted


def knives():
    """A phone stand's lip with a cable notch cut through it at 20 deg, which leaves a 20 deg knife edge 10 mm
    long, and a 15 deg wedge standing apart."""
    lip = bd.Box(40, 20, 3, align=A) + bd.Pos(0, 0, 3) * bd.Box(40, 3, 10, align=A)
    notch = bd.Pos(0, -1.5, 3) * bd.Rotation(0, 0, 20) * bd.Box(30, 30, 20, align=(bd.Align.MIN, bd.Align.MAX,
                                                                                   bd.Align.MIN))
    h = 20 * math.tan(math.radians(15))
    wedge = bd.Pos(30, 0, 0) * bd.Rotation(90, 0, 0) * bd.extrude(
        bd.make_face(bd.Polyline((0, 0), (20, 0), (0, h), (0, 0))), 10)
    planted = [("printing.knife_edge", ALL, (8.24, 1.5, 8.0), 3.0),
               ("printing.knife_edge", ALL, (50, -5, 0), 6.0)]
    # each sliver is its knife's, reported once (no wall inside the knife's thin depth), on both paths
    return _doc("knives", _named(lip - notch, "lip"), _named(wedge, "wedge")), planted, planted


def bracket(scale: float = 1.0):
    """An L bracket, every edge rounded; ``scale`` 1 / 25.4 draws it in inches."""
    base = bd.Box(40, 30, 4, align=A) + bd.Pos(-18, 0, 4) * bd.Box(4, 30, 26, align=A)
    base -= bd.Pos(8, 0, 0) * bd.Cylinder(3, 20)
    return bd.scale(bd.fillet(base.edges(), 0.8), scale) if scale != 1.0 else bd.fillet(base.edges(), 0.8)


def controls():
    """Clean: a filleted bracket, a spline-walled cup, a 1.5 mm cube."""
    cup = bd.loft([bd.Pos(0, 0, 0) * bd.Circle(14), bd.Pos(0, 0, 10) * bd.Ellipse(11, 13),
                   bd.Pos(0, 0, 20) * bd.Circle(13)])
    cup = bd.offset(cup.solids()[0], -2, openings=cup.faces().sort_by(bd.Axis.Z)[-1])
    tiny = bd.Pos(90, 0, 0) * bd.Box(1.5, 1.5, 1.5, align=A)
    # the knife's control: the same lip square, its top edges chamfered 45 deg (135 deg of material each)
    lip = bd.Box(40, 20, 3, align=A) + bd.Pos(0, 0, 3) * bd.Box(40, 3, 10, align=A)
    lip = bd.Pos(0, 60, 0) * bd.chamfer(lip.edges().filter_by(bd.Axis.X).group_by(bd.Axis.Z)[-1], 1.0)
    return _doc("controls", _named(bracket(), "bracket"), _named(bd.Pos(50, 0, 0) * cup, "cup"),
                _named(tiny, "tiny"), _named(lip, "lip")), [], []


def huge():
    """A 2 m plate: too big for every machine, and long for the powder beds."""
    planted = [("printing.build_volume", ALL, (0, 0, 2), 10.0),
               ("printing.warp_length", ("sls", "mjf"), (0, 0, 2), 10.0)]
    return _doc("huge", bd.Box(2000, 100, 4, align=A)), planted, None


CORPUS = (features, spans, hollows, knives, bar, assembly, controls, huge)


def _failures(result) -> list[tuple[str, tuple[float, float, float] | None]]:
    found = []
    for outcome in result.measurements.get("rules", {}).get("outcomes", ()):
        for failure in outcome.get("failures") or ():
            found.append((outcome["rule"], tuple(failure["xyz"]) if failure.get("xyz") else None))
    return found


class Tally:
    def __init__(self) -> None:
        self.tp: dict[str, int] = defaultdict(int)
        self.fp: dict[str, int] = defaultdict(int)
        self.fn: dict[str, int] = defaultdict(int)
        self.misses: list[str] = []

    def score(self, label: str, result, planted: list, technology: str) -> None:
        expected = [entry for entry in planted if technology in entry[1]]
        hit = [False] * len(expected)
        for rule, xyz in _failures(result):
            match = None
            for k, (want, _, center, radius) in enumerate(expected):
                if want == rule and xyz is not None and np.linalg.norm(np.subtract(xyz, center)) <= radius:
                    match = k
                    break
            if match is None:
                self.fp[rule] += 1
                self.misses.append(f"{label} {technology}: unexpected {rule} at {xyz}")
            else:
                hit[match] = True
        for k, entry in enumerate(expected):
            if hit[k]:
                self.tp[entry[0]] += 1
            else:
                self.fn[entry[0]] += 1
                self.misses.append(f"{label} {technology}: missed {entry[0]} at {entry[2]}")

    def table(self) -> str:
        rules = sorted(set(self.tp) | set(self.fp) | set(self.fn))
        lines = [f"{'rule':38} {'tp':>4} {'fp':>4} {'fn':>4} {'precision':>9} {'recall':>7}"]
        for rule in rules:
            tp, fp, fn = self.tp[rule], self.fp[rule], self.fn[rule]
            precision = tp / (tp + fp) if tp + fp else 1.0
            recall = tp / (tp + fn) if tp + fn else 1.0
            lines.append(f"{rule:38} {tp:4d} {fp:4d} {fn:4d} {precision:9.3f} {recall:7.3f}")
        return "\n".join(lines)


class CorpusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.folder = tempfile.TemporaryDirectory(prefix="dfm-printing-corpus-")
        folder = Path(cls.folder.name)
        cls.parts = {}
        for build in CORPUS:
            document, planted, mesh = build()
            step = folder / f"{build.__name__}.step"
            bd.export_step(document, str(step))
            cls.parts[build.__name__] = (document, step, planted, mesh)
        inch = folder / "bracket_inch.step"
        # drawn in inches and declared so: read back, it is the millimetre bracket
        bd.export_step(_named(bracket(1 / 25.4), "bracket"), str(inch), unit=bd.Unit.IN)
        cls.parts["inch"] = (None, inch, [], None)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.folder.cleanup()

    def test_every_planted_defect_and_nothing_else(self) -> None:
        tally, started, facts, results = Tally(), time.monotonic(), {}, {}
        for name, (_, step, planted, _) in self.parts.items():
            # read and measured once, judged per technology: what no option decides (the solids, the voxel
            # fields and their cavities, the holes, the gaps) is not measured again (``measure_each``)
            each = [manufacturing.options("step", "printing", {"technology": technology, "samples": SAMPLES})
                    for technology in ALL]
            reports = measured.measure_each(brep.read("step", step), each)
            for technology, resolved, report in zip(ALL, each, reports):
                result = manufacturing.finish(Path(name), {"process": "printing", **report}, "printing", resolved, False)
                self.assertFalse(result.measurements.get("partial"), f"{name} {technology}: "
                                 f"{result.measurements.get('partial_sections')}")
                tally.score(name, result, planted, technology)
                facts[(name, technology)] = result.measurements
                results[(name, technology)] = result
        print(f"\nprinting corpus, exact geometry ({time.monotonic() - started:.1f} s)\n{tally.table()}",
              file=sys.stderr)
        self.assertEqual(tally.misses, [], "\n".join(tally.misses))
        # through the door a person uses, a technology that is not the first measured: the same verdicts
        public = cad.step.dfm(self.parts["features"][1], process="printing", technology="sls", samples=SAMPLES)
        self.assertEqual(sorted(_failures(public)), sorted(_failures(results[("features", "sls")])))
        self.assertEqual([finding.code for finding in public.findings if finding.severity == "error"],
                         [finding.code for finding in results[("features", "sls")].findings if finding.severity == "error"])
        # the facts the controls and edge cases stand for
        inch = facts[("inch", "fdm")]
        np.testing.assert_allclose(inch["solid"]["bbox_mm"], [40.0, 30.0, 30.0], atol=1e-3,
                                   err_msg="an inch STEP is read in millimetres")
        self.assertTrue(any(item["kind"] == "plate_edge" for item in facts[("controls", "fdm")]["overhangs"]["items"]),
                        "the bracket's bottom rounds meet the plate")
        self.assertGreater(facts[("spans", "fdm")]["stair_stepping"]["area_mm2"], 0, "the 10 deg wedge stair-steps")
        self.assertEqual(facts[("hollows", "sls")]["trapped_volumes"]["sealed_count"], 1)

    def test_the_mesh_path_on_fine_and_coarse_triangles(self) -> None:
        tally, started = Tally(), time.monotonic()
        folder = Path(self.folder.name)
        for name in ("features", "spans", "hollows", "knives", "bar", "assembly", "controls"):
            document, _, _, planted = self.parts[name]
            coarse = ((0.3, "coarse"),) if name in ("spans", "knives", "controls") else ()
            for tolerance, label in ((0.01, "fine"), *coarse):
                stl = folder / f"{name}-{label}.stl"
                bd.export_stl(document, str(stl), tolerance=tolerance, angular_tolerance=0.5 if label == "coarse" else 0.1)
                for technology in (("fdm", "sla") if label == "fine" else ("fdm",)):
                    result = cad.stl.dfm(stl, process="printing", technology=technology, samples=SAMPLES)
                    self.assertFalse(result.measurements.get("partial"), result.measurements.get("partial_sections"))
                    tally.score(f"{name}-{label}", result, planted, technology)
        print(f"\nprinting corpus, meshes ({time.monotonic() - started:.1f} s)\n{tally.table()}", file=sys.stderr)
        self.assertEqual(tally.misses, [], "\n".join(tally.misses))


# --- parity: the same part on both paths ------------------------------------------------------------------------


def _wedge(angle: float):
    """A block whose one side leans out, ``angle`` from the plate: its top edge a tip of that angle."""
    run = 10 / math.tan(math.radians(angle))
    return bd.extrude(bd.Plane.XZ * bd.Polygon((0, 0), (5, 0), (5 + run, 10), (0, 10), align=None), -10)


def _cone(angle: float):
    """A cone flaring upward, its side ``angle`` from the plate all round."""
    return bd.Cone(5, 5 + 10 / math.tan(math.radians(angle)), 10, align=A)


def _facet(angle: float):
    """A block whose underside steps out in two flat faces: one 55 deg from the plate, then one ``angle`` from it
    (400 mm2) -- two planes that meet at less than a mesh's face angle, neither a chord of the other."""
    first, second = 10 / math.tan(math.radians(55)), 10 / math.tan(math.radians(angle))
    return bd.extrude(bd.Plane.XZ * bd.Polygon((0, 0), (10, 0), (10 + first, 10), (10 + first + second, 20),
                                               (10 + first + second, 25), (0, 25), align=None), -20)


def _primitives() -> dict:
    """name: (shape, technology, the verdicts its construction calls for, whether its coarse STL is read too).
    One defect each, or none."""
    shell = bd.Sphere(12) - bd.Sphere(9)
    warning, error = "warning", "error"
    return {
        "cube": (bd.Box(15, 15, 15, align=A), "fdm", [], False),
        "fin": (bd.Box(16, 16, 4, align=A) + bd.Pos(0, 0, 4) * bd.Box(0.7, 16, 8, align=A), "sla",
                [("printing.wall_unsupported", error)], False),                    # 0.7: over 0.5, under 1.0
        # two holes countersunk 90 deg to a 0.6 mm land: joined to the plate all round, a supported wall (SLA's
        # 0.5) at both holes and on both paths
        "lands": (bd.Box(40, 30, 2.2, align=A) - bd.Pos(-12, 0, 0) * bd.Cylinder(1.6, 10)
                  - bd.Pos(12, 0, 0) * bd.Cylinder(1.6, 10) - bd.Pos(-12, 0, 0.6) * bd.Cone(1.6, 3.2, 1.6, align=A)
                  - bd.Pos(12, 0, 0.6) * bd.Cone(1.6, 3.2, 1.6, align=A), "sla", [], False),
        "thinbox": (bd.Box(16, 16, 16, align=A) - bd.Pos(0, 0, 0.5) * bd.Box(15.4, 15.4, 16, align=A), "sla",
                    [("printing.wall_supported", error)], False),                  # 0.3 walls joined on three sides
        "wedge44": (_wedge(44), "fdm", [("printing.knife_edge", warning), ("printing.overhang_angle", warning)], False),
        "wedge45": (_wedge(45), "fdm", [], False),
        "wedge46": (_wedge(46), "fdm", [], False),
        # a flat overhang well under the limit, beside a face it meets at under a mesh's face angle: an overhang
        # on both paths, never "at the limit" (a wedge's meets the plate's face, a facet's a 55 deg one)
        **{f"wedge{angle}": (_wedge(angle), "fdm", [("printing.knife_edge", warning), ("printing.overhang_angle", warning)],
                             False) for angle in (25, 30)},
        **{f"facet55_{angle}": (_facet(angle), "fdm", [("printing.overhang_angle", warning)], False)
           for angle in (25, 30, 35, 40)},
        # a 1 mm plate with a 30 deg tip: the tip's edge is 1 mm long, shorter than its sliver is deep -- a knife
        # on both paths, never a wall of nothing
        "arrow": (bd.extrude(bd.Polygon((0, -6), (30, -6), (30 + 6 / math.tan(math.radians(15)), 0), (30, 6), (0, 6),
                                        align=None), 1), "fdm", [("printing.knife_edge", warning)], False),
        "cone43": (_cone(43), "fdm", [("printing.knife_edge", warning), ("printing.overhang_angle", warning)], True),
        "cone45": (_cone(45), "fdm", [], True),
        "tee": (bd.Box(5, 5, 16, align=A) + bd.Pos(0, 0, 16) * bd.Box(24, 5, 2, align=A), "sla",
                [("printing.cantilever_length", warning), ("printing.overhang_angle", warning)], False),
        "bridge": (bd.Box(30, 10, 10, align=A) - bd.Box(20, 10, 6, align=A), "fdm",
                   [("printing.bridge_length", warning)], False),
        "sphere": (shell, "sls", [("printing.escape_holes", error)], False),
        "sphere_2mm": (shell - bd.Pos(0, 0, 10) * bd.Cylinder(1, 6), "sls",
                       [("printing.escape_hole_diameter", warning)], True),
        "sphere_3.5mm": (shell - bd.Pos(0, 0, 10) * bd.Cylinder(1.75, 6), "sls", [], False),  # at the limit
        "flat_hollow": (bd.Box(50, 50, 16) - bd.Box(40, 40, 6) - bd.Pos(0, 0, 5) * bd.Cylinder(1, 8), "sls",
                        [("printing.escape_hole_diameter", warning)], False),      # 6 mm high behind a 2 mm vent
        "void": (bd.Box(40, 40, 40) - bd.Sphere(1.5), "sls", [("printing.escape_holes", error)], False),
        "skin": (bd.Box(30, 30, 30) - bd.Pos(2.3, -3.1, 3.7) * bd.Sphere(11), "sla",  # 0.3 mm over the cavity
                 [("printing.escape_holes", error), ("printing.hollow_wall", warning),
                  ("printing.overhang_angle", warning), ("printing.wall_supported", error)], True),
        "slot": (bd.Box(16, 16, 8, align=A) - bd.Pos(0, 0, 3) * bd.Box(0.3, 16, 8, align=A), "sls",
                 [("printing.gap", error)], False),
    }


#: The verdicts that do not turn with how the part stands: a wall, a cavity, a gap are the part's own.
_PLACED = ("printing.wall", "printing.escape", "printing.gap", "printing.hollow_wall")
#: What a mesh may say it could not judge (``mesh_at_limit``) where exact geometry gives a verdict: an angle
#: within its own chords' turn of the limit.
_ANGLES = {("printing.overhang_angle", "warning"), ("printing.knife_edge", "warning")}


class ParityTest(unittest.TestCase):
    """The same part read as exact geometry and as its STL gives the same verdicts -- the same rule ids at the
    same severities, and the ones its construction calls for -- fine and coarse, turned about Z and about an
    odd axis; and the verdicts that are the part's own (walls, cavities, gaps) do not turn with it. Where a
    mesh cannot tell an angle from its limit (its chords turn as far as the angle stands off it) it says so
    (``mesh_at_limit``) in place of that verdict, and gives no other."""

    def alike(self, mesh, exact, why: str) -> None:
        """The STL's verdicts are exact geometry's (``exact``, its result), but for an angle the mesh says it
        could not judge -- and it may say so only of an angle that stands within the tolerance it states of the
        limit, which is never more than the mesh's chords turn an angle by (``CHORD_CAP_DEG``)."""
        found, wanted = self.verdicts(mesh), self.verdicts(exact)
        if found == wanted:
            return
        self.assertFalse(set(found) - set(wanted), f"{why}: a verdict exact geometry does not give")
        dropped = set(wanted) - set(found)
        self.assertLessEqual(dropped, _ANGLES, f"{why}: a verdict the STL does not give")
        self.assertIn("mesh_at_limit", [finding.code for finding in mesh.findings], why)
        # how far under its limit each dropped verdict's angle stands on exact geometry, and the band the mesh states
        measured = exact.measurements
        off = {"printing.overhang_angle": [finding.limit - finding.value for finding in exact.findings
                                           if finding.code == "printing.overhang_angle"],
               "printing.knife_edge": [measured["knife_edges"]["knife_below_deg"] - item["angle_deg"]
                                       for item in measured["knife_edges"]["items"]]}
        stated = {"printing.overhang_angle": mesh.measurements["overhangs"]["at_limit_tolerance_deg"],
                  "printing.knife_edge": mesh.measurements["knife_edges"]["at_limit_tolerance_deg"]}
        for rule, _severity in dropped:
            self.assertLessEqual(stated[rule], mo.CHORD_CAP_DEG + 0.05, f"{why}: {rule}'s stated tolerance")
            self.assertLessEqual(max(off[rule]), stated[rule], f"{why}: {rule} dropped {max(off[rule]):g} deg under "
                                 f"its limit, past the {stated[rule]:g} deg the mesh states")

    @staticmethod
    def verdicts(result) -> list[tuple[str, str]]:
        return sorted({(finding.code, finding.severity) for finding in result.findings
                       if finding.code.startswith("printing.")})

    def both(self, shape, name: str, technology: str, tolerance: float, angular: float) -> tuple:
        from cad.build123d._dfm_check import checked

        shape.label = name
        exact = checked(shape, "printing", {"technology": technology, "samples": SAMPLES})
        path = Path(self.folder.name) / f"{name}-{tolerance}.stl"
        bd.export_stl(shape, str(path), tolerance=tolerance, angular_tolerance=angular)
        mesh = cad.stl.dfm(path, process="printing", technology=technology, samples=SAMPLES)
        for result in (exact, mesh):
            self.assertFalse(result.measurements.get("partial"), (name, result.measurements.get("partial_sections")))
        return exact, mesh

    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory(prefix="dfm-printing-parity-")
        self.addCleanup(self.folder.cleanup)

    def test_the_primitives_read_alike_as_step_and_as_stl(self) -> None:
        started, checks = time.monotonic(), 0
        odd = bd.Axis((0, 0, 0), (1, 2, 3))
        turned_z = ("thinbox", "wedge45", "cone45")
        turned_odd = ("fin", "thinbox", "flat_hollow", "void")
        for name, (shape, technology, expected, curved) in _primitives().items():
            meshes = [("fine", 0.01, 0.1), *([("coarse", 0.1, 0.4)] if curved else [])]
            for label, tolerance, angular in meshes:
                exact, mesh = self.both(shape, name, technology, tolerance, angular)
                checks += 2
                with self.subTest(part=name, mesh=label):
                    self.assertEqual(self.verdicts(exact), sorted(expected), "exact geometry")
                    if label == "fine":
                        self.assertEqual(self.verdicts(mesh), sorted(expected), "the STL")
                    self.alike(mesh, exact, "the STL")
            placed = [verdict for verdict in expected if verdict[0].startswith(_PLACED)]
            for way, axis in ((("about z", bd.Axis.Z),) if name in turned_z else ()) + \
                    ((("about an odd axis", odd),) if name in turned_odd else ()):
                exact, mesh = self.both(shape.rotate(axis, 37), f"{name}-turned", technology, 0.01, 0.1)
                checks += 2
                with self.subTest(part=name, turned=way):
                    self.alike(mesh, exact, "both paths, turned")
                    if axis is bd.Axis.Z:  # the plate's own axis: nothing of the part changes
                        self.assertEqual(self.verdicts(exact), sorted(expected))
                    self.assertEqual([v for v in self.verdicts(exact) if v[0].startswith(_PLACED)], sorted(placed),
                                     "a wall, a cavity and a gap are the part's own, however it stands")
        print(f"\nprinting parity: {checks} checks of {len(_primitives())} primitives "
              f"({time.monotonic() - started:.1f} s)", file=sys.stderr)

    def test_what_a_mesh_cannot_tell_from_its_limit_it_says(self) -> None:
        # a 45 deg cone's triangles read 44 to 45.4 deg: at the limit within the mesh's own accuracy -- said (an
        # info), never an overhang, a knife edge or a hair of a wall, coarse or fine
        for tolerance, angular in ((0.01, 0.1), (0.1, 0.4)):
            exact, mesh = self.both(_cone(45), "cone", "fdm", tolerance, angular)
            self.assertEqual((self.verdicts(exact), self.verdicts(mesh)), ([], []))
            said = [finding for finding in mesh.findings if finding.code == "mesh_at_limit"]
            self.assertEqual([finding.severity for finding in said], ["info"])
            self.assertGreater(mesh.measurements["overhangs"]["at_limit_area_mm2"], 50.0)
            self.assertEqual(mesh.measurements["overhangs"]["down_facing_area_below_limit_mm2"], 0.0)
            self.assertEqual(mesh.measurements["support_volume"]["estimated_support_volume_mm3"], 0.0)
            self.assertEqual(exact.measurements["support_volume"]["estimated_support_volume_mm3"], 0.0)
            self.assertGreater(mesh.measurements["wall_thickness"]["min_mm"], 0.8, "no sliver at the rim read as a wall")

    def test_a_part_tilted_a_fraction_of_a_degree_and_moved_keeps_its_own_verdicts(self) -> None:
        # the fin 0.3 deg off the plate's axes and far from the origin: its wall is the same wall, on both paths
        shape, technology, expected, _ = _primitives()["fin"]
        moved = bd.Pos(1000, -700, 300) * shape.rotate(bd.Axis.X, 0.3).rotate(bd.Axis.Y, 0.05)
        exact, mesh = self.both(moved, "fin-tilted", technology, 0.01, 0.1)
        for result in (exact, mesh):
            walls = [verdict for verdict in self.verdicts(result) if verdict[0].startswith(_PLACED)]
            self.assertEqual(walls, expected)
        thin = min(item["thickness_mm"] for item in mesh.measurements["wall_thickness"]["items"])
        self.assertAlmostEqual(thin, 0.7, delta=2e-3)


if __name__ == "__main__":
    unittest.main()
