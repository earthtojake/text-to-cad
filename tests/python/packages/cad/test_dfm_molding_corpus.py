#!/usr/bin/env python3

"""Injection molding's planted-defect corpus: parts built with a known defect, and clean controls, checked
the way an agent checks them (``cad.step.dfm(..., process="molding")``), every verdict compared with the
construction's ground truth.

The ground truth is the construction's, here: each part says which rules must fail and in what region (a
box in millimetres: a finding's place -- its face's centre for a ref -- must fall in it), and which must not
fail anywhere. A rule failing outside every region it is expected in is a false positive; an expected region
no failure falls in, a miss. Precision and recall per rule are printed to stderr and held at 1.0 on this
corpus.
"""

from __future__ import annotations

import math
import sys
import tempfile
import unittest
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import build123d as bd

import cad
from cad.build123d import _dfm_brep

Box3 = tuple[tuple[float, float, float], tuple[float, float, float]]
EVERYWHERE: Box3 = ((-1e6, -1e6, -1e6), (1e6, 1e6, 1e6))

# --- the parts ---------------------------------------------------------------------------------------------


def _concave_edges(shape):
    part = _dfm_brep.parts_of(shape, name="p").parts[0]
    return [part.edges()[edge.ordinal - 1] for edge in _dfm_brep.edges(part) if edge.concave]


def tray(draft: float = 3.0, wall: float = 2.0, fillet: float = 1.0, x: float = 60.0, y: float = 40.0,
         h: float = 20.0):
    """An open-top tray, ``wall`` thick everywhere, its outer and inner walls flaring ``draft`` deg toward the
    opening (+z), its internal corners filleted ``fillet`` (0: sharp)."""
    outer = bd.extrude(bd.Rectangle(x, y), h, taper=-draft)
    inset = wall / math.cos(math.radians(draft)) - wall * math.tan(math.radians(draft))
    cavity = bd.Pos(0, 0, wall) * bd.extrude(bd.Rectangle(x - 2 * inset, y - 2 * inset), h, taper=-draft)
    part = outer - cavity
    if fillet:
        part = part.solids()[0].fillet(fillet, _concave_edges(part))
    return part


def plate(x: float = 80.0, y: float = 60.0, t: float = 2.0, draft: float = 3.0):
    """A flat plate on z = 0, its edges drafted."""
    return bd.extrude(bd.Rectangle(x, y), t, taper=draft)


def side_hole():
    """A clean tray with a through hole in its +x wall: a side action along +x releases it."""
    return tray() - bd.Pos(30.0, 0.0, 10.0) * bd.Rotation(0, 90, 0) * bd.Cylinder(2.0, 12.0)


def snap_lip():
    """A clean tray with a snap lip on its inner +y wall, 5 mm below the rim: its underside is trapped
    inside, released by a lifter."""
    inner_y = 20.0 + 15.0 * math.tan(math.radians(3.0)) - 2.0 / math.cos(math.radians(3.0))
    return tray() + bd.Pos(0.0, inner_y - 0.6, 15.0) * bd.Box(10.0, 2.0, 1.5)


def ribbed(thickness: float, height: float = 5.0):
    """A 2 mm plate with two ribs ``thickness`` thick and ``height`` tall standing on its top."""
    part = plate()
    for x in (-20.0, 20.0):
        part = part + bd.Pos(x, 0.0, 2.0 + height / 2) * bd.Box(thickness, 50.0, height)
    return part


def bossed(outer: float, inner: float):
    """A 2 mm plate with a boss of radius ``outer`` 8 mm tall, cored to radius ``inner`` down to the plate."""
    boss = bd.Pos(0.0, 0.0, 2.0 + 4.0) * bd.Cylinder(outer, 8.0)
    hole = bd.Pos(0.0, 0.0, 2.0 + 4.0) * bd.Cylinder(inner, 8.0)
    return plate() + boss - hole


def thick_pad():
    """A 2 mm plate with a 20 x 20 mm pad 6 mm high on top: an 8 mm section stepping abruptly from 2."""
    return plate() + bd.Pos(0.0, 0.0, 5.0) * bd.Box(20.0, 20.0, 6.0)


def bracket(inner: float = 0.0, outer: float = 0.0):
    """An L bracket, 2 mm legs 30 mm long, 20 mm deep along the pull; its inside corner filleted ``inner``,
    its outside ``outer``."""
    profile = bd.Polygon((0, 0), (30, 0), (30, 2), (2, 2), (2, 30), (0, 30), align=None)
    part = bd.extrude(profile, 20.0)
    if inner:
        corner = [edge for edge in part.edges() if abs(edge.center().X - 2) < 1e-6 and abs(edge.center().Y - 2) < 1e-6]
        part = part.fillet(inner, corner)
    if outer:
        corner = [edge for edge in part.edges() if abs(edge.center().X) < 1e-6 and abs(edge.center().Y) < 1e-6]
        part = part.fillet(outer, corner)
    return part


def filleted_all():
    """A clean tray with its outside edges rounded as well."""
    part = tray()
    convex = [e for e in part.edges() if e.center().Z < 19.0 and e.center().Z > 0.5 or e.center().Z < 0.01]
    try:
        return part.fillet(0.8, [e for e in convex if e.geom_type == bd.GeomType.LINE])
    except Exception:  # noqa: BLE001 - the kernel declined a round: keep the inside fillets alone
        return part


def dome():
    """A dome shell of a spline profile revolved about z, 2 mm thick, open below: freeform faces drafted
    all over."""
    outer = bd.Spline((30, 0), (24, 9), (13, 15), (0, 17))
    inner = bd.Spline((28, 0), (22.2, 8.0), (12, 13.4), (0, 15))
    profile = bd.make_face(bd.Wire([bd.Edge.make_line((0, 0), (0, 0)) if False else outer,
                                    bd.Edge.make_line((0, 17), (0, 15)), inner.reversed() if hasattr(inner, "reversed") else inner,
                                    bd.Edge.make_line((28, 0), (30, 0))]))
    return bd.revolve(bd.Plane.XZ * profile, bd.Axis.Z)


def cone_bossed(outer: float, inner: float, draft: float = 1.0):
    """A 2 mm plate with a boss drafted ``draft`` deg (a cone, radius ``outer`` at its root, 8 mm tall), cored
    by a cone of root radius ``inner`` drafted the same way down to the plate: a drafted boss is a boss."""
    lean = 8.0 * math.tan(math.radians(draft))
    up = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)
    boss = bd.Pos(0.0, 0.0, 2.0) * bd.Cone(outer, outer - lean, 8.0, align=up)
    hole = bd.Pos(0.0, 0.0, 2.0) * bd.Cone(inner, inner + lean, 8.0, align=up)
    return plate() + boss - hole


def floor_hole():
    """A clean tray with a drafted 6 mm hole through its floor along the pull: a shut-off, so the parting
    stays flat at the rim."""
    up = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)
    return tray() - bd.Pos(0.0, 0.0, -0.5) * bd.Cone(3.0, 3.0 + 3.0 * math.tan(math.radians(3.0)), 3.0, align=up)


def hooked_lid():
    """A 60 x 40 x 2 mm lid with two snap hooks 48 mm apart hanging 10 mm below it, each catch pointing in
    under the lid: two undercuts, each at its own hook."""
    part = plate(60.0, 40.0, 2.0, draft=1.0)
    for side in (-1.0, 1.0):
        arm = bd.Pos(side * 24.0, 0.0, -10.0) * bd.extrude(bd.Rectangle(1.0, 8.0), 10.0)
        catch = bd.Pos(side * 23.0, 0.0, -10.0) * bd.extrude(bd.Rectangle(1.2, 8.0), 1.2)
        part = part + arm + catch
    return part


def tray_ribs():
    """A clean (filleted, drafted) tray with two undrafted 2 mm ribs (as thick as its wall) standing sharp on
    its floor."""
    part = tray()
    for x in (-10.0, 10.0):
        part = part + bd.Pos(x, 0.0, 2.0) * bd.Box(2.0, 24.0, 5.0, align=(bd.Align.CENTER, bd.Align.CENTER,
                                                                          bd.Align.MIN))
    return part


def rib_into_wall():
    """A clean box (2 deg) with a square-ended rib run 0.1 mm into its drafted walls: buried at the floor, a
    hair off the walls above it, the gap opening along the pull -- a crevice, no undercut."""
    box = bd.extrude(bd.Rectangle(60, 40), 30, taper=-2) - \
        bd.Pos(0, 0, 2) * bd.extrude(bd.Rectangle(56, 36), 28, taper=-2)
    return box + bd.Pos(0, 0, 5) * bd.Box(1.2, 36.2, 6)


SLOTS_X = (-25.0, 5.0, 30.0)


def housing():
    """A 120 x 80 x 30 housing, 2 mm walls drafted 2 deg: three ribs across and two along (1.2 mm, 0.6 of the
    wall), crossing each other and run into the walls; two cored bosses; three slots through its +y wall, which
    one slide along +y forms."""
    up = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)
    part = bd.extrude(bd.Rectangle(120, 80), 30, taper=-2) - \
        bd.Pos(0, 0, 2) * bd.extrude(bd.Rectangle(116, 76), 28, taper=-2)
    for x in (-40.0, 0.0, 40.0):
        part += bd.Pos(x, 0, 2) * bd.Box(1.2, 76, 8, align=up)
    for y in (-20.0, 20.0):
        part += bd.Pos(0, y, 2) * bd.Box(116, 1.2, 8, align=up)
    for x in (-20.0, 20.0):
        part += bd.Pos(x, 0, 2) * (bd.Cylinder(3, 8, align=up) - bd.Cylinder(1.3, 8, align=up))
    for x in SLOTS_X:
        part -= bd.Pos(x, 40, 18) * bd.Box(1.5, 10, 8)
    return part


def assembly():
    """Two parts: ``plain`` (no draft) and ``drafted`` (3 deg), side by side."""
    plain = bd.Pos(-30.0, 0.0, 0.0) * bd.Box(20.0, 20.0, 10.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    plain.label = "plain"
    drafted = bd.Pos(30.0, 0.0, 0.0) * bd.extrude(bd.Rectangle(20.0, 20.0), 10.0, taper=3.0)
    drafted.label = "drafted"
    return bd.Compound(label="pair", children=[plain, drafted])


@dataclass
class Case:
    name: str
    build: object
    expect: dict[str, list[Box3]] = field(default_factory=dict)   # rule: the regions it must fail in
    absent: tuple[str, ...] = ()                                   # rules that must fail nowhere
    unit: object = None
    releases: dict[str, str] = field(default_factory=dict)        # an undercut's release, by its region's key


def _box(lo, hi) -> Box3:
    return (tuple(lo), tuple(hi))  # type: ignore[return-value]


CLEAN = ("molding.draft_min", "molding.draft", "molding.undercut", "molding.undercut_unreleasable",
         "molding.wall_min", "molding.wall_max", "molding.thick_section", "molding.wall_transition",
         "molding.inside_corner_radius", "molding.rib_thickness", "molding.rib_height", "molding.boss_wall")
HOLE: Box3 = _box((27.0, -3.0, 7.0), (31.5, 3.0, 13.0))
LIP: Box3 = _box((-6.0, 16.0, 1.5), (6.0, 20.0, 16.5))   # the lip, and the strip of wall it shadows
SIDES: list[Box3] = [_box((29.0, -21, 0), (31.5, 21, 20)), _box((-31.5, -21, 0), (-29.0, 21, 20)),
                     _box((-31, 19.0, 0), (31, 21.5, 20)), _box((-31, -21.5, 0), (31, -19.0, 20))]
INSIDES: list[Box3] = [_box((26.0, -19, 2), (28.5, 19, 21)), _box((-28.5, -19, 2), (-26.0, 19, 21)),
                       _box((-29, 16.0, 2), (29, 18.5, 21)), _box((-29, -18.5, 2), (29, -16.0, 21))]
RIBS: list[Box3] = [_box((-21.5, -26, 1.5), (-18.5, 26, 7.5)), _box((18.5, -26, 1.5), (21.5, 26, 7.5))]
PAD: Box3 = _box((-12.0, -12.0, -0.5), (12.0, 12.0, 8.5))
BOSS: Box3 = _box((-5.5, -5.5, 1.5), (5.5, 5.5, 10.5))
CORNER: Box3 = _box((1.0, 1.0, -0.5), (3.0, 3.0, 20.5))
INNER_EDGES: list[Box3] = [_box((-29, -19, 1), (29, 19, 21))]
HOOKS: list[Box3] = [_box((-26.0, -5.0, -11.0), (-20.0, 5.0, 1.0)), _box((20.0, -5.0, -11.0), (26.0, 5.0, 1.0))]
TRAY_RIBS: list[Box3] = [_box((-11.5, -13, 1.5), (-8.5, 13, 7.5)), _box((8.5, -13, 1.5), (11.5, 13, 7.5))]
SLOTS: list[Box3] = [_box((x - 1.5, 37.0, 13.0), (x + 1.5, 42.0, 23.0)) for x in SLOTS_X]

CASES = [
    Case("clean_tray", tray, absent=CLEAN),
    Case("shallow_draft_tray", lambda: tray(draft=0.75), expect={"molding.draft": SIDES + INSIDES},
         absent=tuple(rule for rule in CLEAN if rule != "molding.draft")),
    Case("sealed_void", lambda: bd.Box(30, 30, 30, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
         - bd.Pos(0, 0, 15) * bd.Sphere(6), expect={"molding.undercut_unreleasable": [_box((-7, -7, 8), (7, 7, 22))]},
         absent=("molding.undercut",)),
    Case("undrafted_tray", lambda: tray(draft=0.0, fillet=0.0),
         expect={"molding.draft_min": SIDES + INSIDES, "molding.inside_corner_radius": INNER_EDGES},
         absent=("molding.undercut", "molding.thick_section", "molding.wall_min", "molding.wall_max",
                 "molding.wall_transition")),
    Case("side_hole", side_hole, expect={"molding.undercut": [HOLE]},
         absent=tuple(rule for rule in CLEAN if rule != "molding.undercut"),
         releases={"hole": "side_action"}),
    Case("side_hole_inch", side_hole, expect={"molding.undercut": [HOLE]},
         absent=tuple(rule for rule in CLEAN if rule != "molding.undercut"), unit="in"),
    Case("snap_lip", snap_lip, expect={"molding.undercut": [LIP]},
         absent=("molding.undercut_unreleasable", "molding.wall_max", "molding.thick_section"),
         releases={"lip": "lifter"}),
    Case("thick_ribs", lambda: ribbed(2.0), expect={"molding.rib_thickness": RIBS},
         absent=("molding.undercut", "molding.rib_height", "molding.wall_max")),
    Case("good_ribs", lambda: ribbed(1.0), absent=("molding.undercut", "molding.rib_thickness", "molding.rib_height",
                                                    "molding.thick_section", "molding.wall_max")),
    Case("tall_ribs", lambda: ribbed(1.0, height=9.0), expect={"molding.rib_height": RIBS[:1] + [
        _box((18.5, -26, 1.5), (21.5, 26, 11.5))]}, absent=("molding.rib_thickness", "molding.undercut")),
    Case("thick_boss", lambda: bossed(5.0, 1.5), expect={"molding.boss_wall": [BOSS]},
         absent=("molding.undercut",)),
    Case("good_boss", lambda: bossed(2.5, 1.6), absent=("molding.boss_wall", "molding.thick_section",
                                                         "molding.wall_max", "molding.undercut")),
    Case("thick_cone_boss", lambda: cone_bossed(5.0, 1.5), expect={"molding.boss_wall": [BOSS]},
         absent=("molding.undercut", "molding.draft_min")),
    Case("good_cone_boss", lambda: cone_bossed(2.5, 1.6), absent=("molding.boss_wall", "molding.thick_section",
                                                                   "molding.wall_max", "molding.undercut",
                                                                   "molding.draft_min")),
    # extrude(taper=) writes the flaring walls and their fillets as B-splines: the fillets still read
    Case("small_fillet_tray", lambda: tray(draft=2.0, fillet=0.5),
         expect={"molding.inside_corner_radius": INNER_EDGES},
         absent=tuple(rule for rule in CLEAN if rule != "molding.inside_corner_radius")),
    Case("floor_hole", floor_hole, absent=CLEAN),
    Case("hooked_lid", hooked_lid, expect={"molding.undercut": HOOKS}, absent=("molding.undercut_unreleasable",)),
    Case("tray_ribs", tray_ribs, expect={"molding.rib_thickness": TRAY_RIBS},
         absent=("molding.undercut", "molding.wall_max")),
    # The pad's section is thick_section's; wall_max judges a face's own wall, not its thickest point.
    Case("thick_pad", thick_pad, expect={"molding.thick_section": [PAD], "molding.wall_transition": [PAD]},
         absent=("molding.undercut", "molding.wall_min")),
    Case("sharp_bracket", bracket, expect={"molding.inside_corner_radius": [CORNER]},
         absent=("molding.undercut", "molding.thick_section", "molding.wall_min", "molding.wall_max")),
    Case("round_bracket", lambda: bracket(1.5, 3.5),
         absent=("molding.inside_corner_radius", "molding.undercut", "molding.thick_section", "molding.wall_min",
                 "molding.wall_max", "molding.wall_transition")),
    Case("filleted_all", filleted_all, absent=CLEAN),
    Case("spline_dome", dome, absent=("molding.draft_min", "molding.draft", "molding.undercut",
                                      "molding.thick_section", "molding.wall_min", "molding.wall_max")),
    Case("assembly", assembly, expect={"molding.draft_min": [_box((-40.5, -10.5, -0.5), (-19.5, 10.5, 10.5))]},
         absent=("molding.undercut",)),
    # nothing planted that traps: a rib's end a hair off a drafted wall failed this part on two samples
    Case("rib_into_wall", rib_into_wall, absent=("molding.undercut", "molding.undercut_unreleasable",
                                                 "molding.rib_thickness", "molding.wall_min", "molding.wall_max")),
    # every rib's end a crevice, every crossing a rib standing on the floor, every slot the one slide's
    Case("housing", housing, expect={"molding.undercut": SLOTS},
         absent=("molding.undercut_unreleasable", "molding.rib_thickness", "molding.wall_min", "molding.wall_max",
                 "molding.draft_zero")),
    Case("tiny_block", lambda: bd.Box(1.0, 1.0, 0.6, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)),
         expect={"molding.draft_min": [EVERYWHERE], "molding.wall_min": [EVERYWHERE]}, absent=("molding.undercut",)),
    # 2 x 1 m: a press's and a mold's size are a shop's, compared with the measurements: no general rule fails it
    Case("huge_panel", lambda: plate(2000.0, 1000.0, 4.0),
         absent=("molding.draft_min", "molding.undercut", "molding.wall_min", "molding.thick_section")),
]


# --- the run -----------------------------------------------------------------------------------------------


def _inside(point, box: Box3) -> bool:
    (x0, y0, z0), (x1, y1, z1) = box
    return x0 <= point[0] <= x1 and y0 <= point[1] <= y1 and z0 <= point[2] <= z1


class _Places:
    """A finding's place as a point: a ref's face centre (the document read as the check reads it) or a part's
    box centre."""

    def __init__(self, path: Path | None) -> None:
        self.parts = {}
        if path is not None:
            document = _dfm_brep.read("step", path)
            self.parts = {part.owner: part for part in document.parts}

    def point(self, location: str | None, xyz) -> tuple[float, float, float] | None:
        if xyz:
            return tuple(float(value) for value in xyz)  # type: ignore[return-value]
        if location and "/face " in f"/{location}":
            owner, _, ordinal = location.rpartition("face ")
            part = self.parts.get(owner.rstrip("/"))
            if part is not None:
                center = part.faces()[int(ordinal) - 1].center()
                return (center.X, center.Y, center.Z)
        if location in self.parts:
            box = self.parts[location].shape.bounding_box()
            return (box.center().X, box.center().Y, box.center().Z)
        if xyz:
            return tuple(float(value) for value in xyz)  # type: ignore[return-value]
        if location and location.count(",") == 2:
            return tuple(float(value) for value in location.split(","))  # type: ignore[return-value]
        return None


@dataclass
class Tally:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    misses: list[str] = field(default_factory=list)
    false: list[str] = field(default_factory=list)


def _score(name: str, result, expect: dict[str, list[Box3]], absent: tuple[str, ...], places: _Places,
           tallies: dict[str, Tally]) -> None:
    outcomes = {outcome["rule"]: outcome for outcome in (result.measurements.get("rules") or {}).get("outcomes", [])}
    for rule in sorted(set(expect) | set(absent)):
        tally = tallies[rule]
        failures = (outcomes.get(rule) or {}).get("failures") or []
        points = [places.point(failure.get("location"), failure.get("xyz")) for failure in failures]
        regions = expect.get(rule, [])
        for region in regions:
            if any(point is not None and _inside(point, region) for point in points):
                tally.tp += 1
            else:
                tally.fn += 1
                tally.misses.append(f"{name}: {rule} not at {region}")
        for failure, point in zip(failures, points):
            if not any(point is not None and _inside(point, region) for region in regions):
                tally.fp += 1
                tally.false.append(f"{name}: {rule} at {failure.get('location')} ({failure.get('value')})")


class MoldingCorpusTest(unittest.TestCase):
    tallies: dict[str, Tally]
    results: dict[str, object]

    @classmethod
    def setUpClass(cls) -> None:
        folder = tempfile.TemporaryDirectory(prefix="cad-molding-corpus-")
        cls.addClassCleanup(folder.cleanup)
        root = Path(folder.name)
        cls.tallies = defaultdict(Tally)
        cls.results = {}
        for case in CASES:
            shape = case.build()
            step = root / f"{case.name}.step"
            if case.unit == "in":
                # build123d writes a shape's numbers as inches under Unit.IN: scaled to inches first, the
                # file reads back at the part's millimetres.
                bd.export_step(shape.scale(1 / 25.4), str(step), unit=bd.Unit.IN)
            else:
                bd.export_step(shape, str(step))
            result = cad.step.dfm(str(step), process="molding", material="abs")
            cls.results[case.name] = result
            _score(case.name, result, case.expect, case.absent, _Places(step), cls.tallies)
        lines = [f"{'rule':34} {'tp':>4} {'fp':>4} {'fn':>4} {'precision':>9} {'recall':>7}"]
        for rule in sorted(cls.tallies):
            tally = cls.tallies[rule]
            precision = tally.tp / (tally.tp + tally.fp) if tally.tp + tally.fp else 1.0
            recall = tally.tp / (tally.tp + tally.fn) if tally.tp + tally.fn else 1.0
            lines.append(f"{rule:34} {tally.tp:4} {tally.fp:4} {tally.fn:4} {precision:9.2f} {recall:7.2f}")
        print("\nmolding corpus, precision and recall per rule:\n" + "\n".join(lines), file=sys.stderr)

    def test_every_planted_defect_is_found_where_it_was_planted(self) -> None:
        misses = [miss for tally in self.tallies.values() for miss in tally.misses]
        self.assertEqual(misses, [])

    def test_no_rule_fails_where_nothing_was_planted(self) -> None:
        false = [found for tally in self.tallies.values() for found in tally.false]
        self.assertEqual(false, [])

    def test_the_verdict_is_the_floors_alone(self) -> None:
        """OK: nothing a general shop sends back (warnings: made, at a cost). FAILED: a floor broken -- a feature
        nothing releases, a wall deeper than 10 mm with no draft at all (the brackets' 20 mm legs, the tray's
        walls), a section over twice the resin's recommended maximum (a 10 mm block or pad in ABS). Every other
        part of the corpus, whatever it is warned of, is OK."""
        failed = {name: sorted({finding.code for finding in result.findings if finding.severity == "error"})
                  for name, result in self.results.items() if not result.ok}
        self.assertEqual(failed, {
            "sealed_void": ["molding.draft_zero", "molding.undercut_unreleasable", "molding.wall_too_thick"],
            "undrafted_tray": ["molding.draft_zero"], "sharp_bracket": ["molding.draft_zero"],
            "round_bracket": ["molding.draft_zero"], "thick_pad": ["molding.wall_too_thick"],
            "assembly": ["molding.wall_too_thick"]})

    def test_every_part_measured_whole(self) -> None:
        for name, result in self.results.items():
            with self.subTest(part=name):
                self.assertFalse(result.measurements.get("partial"), result.measurements.get("partial_sections"))

    def test_undercuts_name_what_releases_them(self) -> None:
        def release(name: str, region: Box3) -> list[str]:
            items = result.measurements["undercuts"]["items"]
            return [item["release"] for item in items if _inside(item["xyz"], region)]

        for name in ("side_hole", "side_hole_inch"):
            result = self.results[name]
            with self.subTest(part=name):
                self.assertEqual(release(name, HOLE), ["side_action"])
                hole = next(item for item in result.measurements["undercuts"]["items"] if _inside(item["xyz"], HOLE))
                self.assertEqual(hole["side_actions"], ["+x"])
                # the bore's trapped length through the 2 mm wall (its inner end opens to the drafted cavity)
                self.assertGreater(hole["stroke_mm"], 1.5)
                self.assertLess(hole["stroke_mm"], 2.3)
        result = self.results["snap_lip"]
        self.assertEqual(release("snap_lip", LIP), ["lifter"])
        # three slots, three features, one slide: a part's side actions are its distinct directions
        housed = self.results["housing"].measurements["undercuts"]
        self.assertEqual({(item["release"], tuple(item["side_actions"])) for item in housed["items"]},
                         {("side_action", ("+y",))})
        self.assertEqual((housed["undercut_count"], housed["side_action_count"], housed["unreleasable_count"]), (3, 1, 0))
        self.assertGreater(housed["crevice_count"], 0)

    def test_the_parting_and_the_clamp(self) -> None:
        clean = self.results["clean_tray"].measurements
        self.assertTrue(clean["parting"]["flat_parting_possible"])
        self.assertAlmostEqual(clean["parting"]["parting_plane_height_mm"], 20.0, delta=0.05, msg="at the rim")
        # 60 x 40 at the rim plus the flare: the projected area is the rim's outline
        flare = 20.0 * math.tan(math.radians(3.0))
        self.assertAlmostEqual(clean["projection"]["projected_area_mm2"], (60 + 2 * flare) * (40 + 2 * flare),
                               delta=clean["projection"]["area_error_mm2"] + 1.0)
        tons = clean["projection"]["projected_area_mm2"] / 645.16 * 3.25 * 1.15
        self.assertAlmostEqual(clean["clamp"]["tons"], tons, delta=0.05)
        # a hole through the floor along the pull is a shut-off: the parting stays one flat plane at the rim
        parting = self.results["floor_hole"].measurements["parting"]
        self.assertTrue(parting["flat_parting_possible"], parting.get("items"))
        self.assertAlmostEqual(parting["parting_plane_height_mm"], 20.0, delta=0.05)

    def test_two_hooks_are_two_undercuts_each_at_its_hook(self) -> None:
        items = self.results["hooked_lid"].measurements["undercuts"]["items"]
        self.assertEqual(len(items), 2)
        for region in HOOKS:
            self.assertEqual(sum(_inside(item["xyz"], region) for item in items), 1)


if __name__ == "__main__":
    unittest.main()
