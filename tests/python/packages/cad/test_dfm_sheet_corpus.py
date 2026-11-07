#!/usr/bin/env python3

"""Sheet metal's planted-defect corpus: parts built here with known defects, and clean controls, each
written to a STEP and checked by ``cad.step.dfm(path, process="sheet")`` as a user's would be.

The ground truth is the construction's: each part names the rule ids (and the measurement's finding
codes) that must fire, and where (a point the failure's ``xyz`` must lie near), and every other code is a
false positive. Precision and recall are computed per code over the whole corpus and printed as a table;
the targets are 1.0. Every failure's ref must resolve, by the engine's own resolver, to a face of the
STEP. Edge cases: an assembly of several parts, an inch STEP, a part of about a millimetre and one of
about two metres, rounds everywhere, a freeform shell, a filleted machined block, and the other rule sets
(SendCutSend, Protolabs) on the parts their own rules reach.
"""

from __future__ import annotations

import math
import sys
import tempfile
import time
import unittest
from dataclasses import dataclass, field
from pathlib import Path

import build123d as bd

from cad import step
from tests.python.packages.cad.test_dfm_sheet import bent, tabbed, tray

#: Codes that report, never judge: not scored.
INFO = {"rules_generic", "sheet.k_factor_assumed", "sheet.bend_radii_mixed"}


@dataclass
class Case:
    name: str
    shape: bd.Shape
    expect: list[tuple[str, tuple[float, float, float] | None]] = field(default_factory=list)
    options: dict = field(default_factory=dict)
    unit: object = None
    near: float = 6.0       # how close a failure must lie to the planted point, in the file's own millimetres


def _labelled(shape: bd.Shape, label: str) -> bd.Shape:
    shape.label = label
    return shape


def _bracket(label: str, *, t: float = 2.0, r: float = 2.0, base: float = 40.0, wall: float = 30.0,
             width: float = 50.0) -> bd.Part:
    return bent([("line", base), ("bend", 90, r), ("line", wall)], t, width, label)


def _plate(label: str, size=(100.0, 60.0), t: float = 2.0) -> bd.Part:
    return _labelled(bd.Pos(0, 0, t / 2) * bd.Box(size[0], size[1], t), label)


def _hole(shape: bd.Shape, x: float, y: float, d: float) -> bd.Shape:
    return shape - bd.Pos(x, y, 0) * bd.Cylinder(d / 2, 100)


def corpus() -> list[Case]:
    cases: list[Case] = []
    good = _hole(_hole(_bracket("good"), 15, 15, 5), 15, 35, 5)
    cases.append(Case("clean_bracket", _labelled(good, "good")))
    cases.append(Case("clean_channel", bent([("line", 25), ("bend", 90, 2), ("line", 60), ("bend", 90, 2),
                                             ("line", 25)], 2.0, 80, "channel")))
    cases.append(Case("clean_tray", tray(size=80, corner=3.0)))
    cases.append(Case("clean_hem", bent([("line", 40), ("bend", 180, 1.0), ("line", 8)], 1.0, 30, "hem")))
    cases.append(Case("clean_relief", tabbed(relief=(3.0, 6.0), label="relieved")))
    rounded = bd.fillet(bd.Box(80, 50, 2).edges().filter_by(bd.Axis.Z), 5)
    rounded = _hole(rounded, 20, 0, 6) - bd.Pos(-20, 0, 0) * bd.extrude(bd.SlotCenterToCenter(10, 4), 10, both=True)
    cases.append(Case("clean_rounds_everywhere", _labelled(rounded, "rounded")))
    cases.append(Case("clean_tiny_1mm", _bracket("tiny", t=0.5, r=0.5, base=2.0, wall=1.5, width=2.0)))
    inch = _bracket("inch", t=0.0625, r=0.0625, base=2.0, wall=1.0, width=1.5)
    cases.append(Case("clean_inch_step", inch, unit=bd.Unit.IN))

    near_bend = _hole(_bracket("near"), 35, 25, 4)  # 3 mm from the tangent line at x = 40, under 2 t
    cases.append(Case("hole_near_bend", _labelled(near_bend, "near"), [("sheet.hole_to_bend", (35, 25, 1))]))
    cases.append(Case("missing_relief", tabbed(label="bare"),
                      [("sheet.bend_relief_width", (0, 15, 2)), ("sheet.bend_relief_width", (0, -15, 2))]))
    cases.append(Case("narrow_relief", tabbed(relief=(1.0, 6.0), label="narrow"),
                      [("sheet.bend_relief_width", (0, 15, 2)), ("sheet.bend_relief_width", (0, -15, 2))]))
    cases.append(Case("radius_under_thickness", _bracket("sharp", r=0.5), [("sheet.bend_radius", (40.5, 25, 2.5))]))
    cases.append(Case("short_flange", _bracket("stub", wall=1.0), [("sheet.flange_length", (44, 25, 4))]))
    cases.append(Case("tiny_hole", _labelled(_hole(_plate("pin"), 20, 20, 1.0), "pin"),
                      [("sheet.hole_diameter", (20, 20, 1))]))
    cases.append(Case("hole_to_edge", _labelled(_hole(_plate("edge"), -47, 0, 4), "edge"),
                      [("sheet.hole_to_edge", (-47, 0, 1))]))
    pair = _hole(_hole(_plate("pair"), 0, 0, 4), 5, 0, 4)
    cases.append(Case("hole_spacing", _labelled(pair, "pair"), [("sheet.hole_spacing", (2.5, 0, 1))], near=4))
    notch = _plate("notch") - bd.Pos(0, 30 - 4, 1) * bd.Box(1.0, 8, 4)
    cases.append(Case("narrow_notch", _labelled(notch.clean(), "notch"),
                      [("sheet.notch_width", (0, 22, 1)), ("sheet.notch_length", (0, 22, 1))]))
    tab = (_plate("tab") + bd.Pos(50 + 5, 0, 1) * bd.Box(10, 3, 2)).clean()
    cases.append(Case("narrow_tab", _labelled(tab, "tab"), [("sheet.tab_width", (60, 0, 1))]))
    long_tab = (_plate("long") + bd.Pos(50 + 15, 0, 1) * bd.Box(30, 5, 2)).clean()
    cases.append(Case("long_tab", _labelled(long_tab, "long"), [("sheet.tab_length", (80, 0, 1))]))
    boss = _bracket("boss") + bd.Pos(20, 25, 2) * bd.Cylinder(4, 5, align=(bd.Align.CENTER, bd.Align.CENTER,
                                                                           bd.Align.MIN))
    cases.append(Case("boss_not_constant_thickness", _labelled(boss, "boss"),
                      [("sheet.uniform_thickness", (20, 25, 3.5))]))
    pocket = _plate("pocket", t=3.0) - bd.Pos(0, 0, 2.5) * bd.Box(20, 10, 2)
    cases.append(Case("machined_pocket", _labelled(pocket, "pocket"), [("sheet.uniform_thickness", (0, 0, 1.5))],
                      near=12))
    block = bd.fillet(bd.Box(60, 40, 20).edges(), 3)
    cases.append(Case("filleted_machined_block", _labelled(block, "block"),
                      [("sheet.not_sheet", None)]))  # no thickness verdicts on a part that is not sheet
    points = [[(x * 20, y * 20, 5 * ((x - 1.5) ** 2 * 0.3 + (y - 1) ** 2 * 0.2)) for y in range(3)] for x in range(4)]
    shell = bd.Solid.thicken(bd.Face.make_surface_from_array_of_points(points), 2.0)
    cases.append(Case("freeform_shell", _labelled(shell, "shell"), [("sheet.not_sheet", None)]))
    cases.append(Case("tight_short_hem", bent([("line", 40), ("bend", 180, 0.25), ("line", 3)], 1.0, 30, "hem"),
                      [("sheet.hem_diameter", None), ("sheet.hem_return", None)]))  # a hem's radius: hem_diameter
    kit = bd.Compound(children=[_labelled(_hole(_hole(_bracket("fine"), 15, 15, 5), 15, 35, 5), "fine"),
                                bd.Pos(0, 100, 0) * _labelled(_hole(_bracket("near"), 35, 25, 4), "near")])
    kit.label = "kit"
    cases.append(Case("assembly_one_bad_part", kit, [("sheet.hole_to_bend", (35, 125, 1))]))
    inch_hole = _labelled(_hole(_bracket("inchhole", t=0.0625, r=0.0625, base=2.0, wall=1.0, width=1.5),
                                0.5, 0.75, 0.03), "inchhole")
    cases.append(Case("inch_tiny_hole", inch_hole, [("sheet.hole_diameter", (0.5, 0.75, 0.03))],
                      unit=bd.Unit.IN, near=0.2))
    cases.append(Case("huge_2m", _bracket("huge", t=3.0, r=3.0, base=2000, wall=1200, width=1000),
                      [("sheet.flat_length", None)]))
    scs = dict(rules="sendcutsend", material="aluminum")
    cases.append(Case("scs_channel_base", bent([("line", 30), ("bend", 90, 3.175), ("line", 40), ("bend", 90, 3.175),
                                                ("line", 30)], 3.175, 80, "scs"), [("sheet.channel_base", None)],
                      options=scs))
    cases.append(Case("scs_hem", bent([("line", 40), ("bend", 180, 3.175), ("line", 20)], 3.175, 80, "scshem"),
                      [("sheet.bend_angle", None)], options=scs))
    with bd.BuildPart() as sunk:
        bd.Box(80, 50, 3)
        with bd.Locations((0, 0, 1.5)):
            bd.CounterSinkHole(radius=0.8, counter_sink_radius=1.0)
    cases.append(Case("protolabs_small_countersink", _labelled(sunk.part, "sunk"),
                      [("sheet.countersink_diameter", (0, 0, 0)), ("sheet.hole_diameter", (0, 0, 0))],
                      options=dict(rules="protolabs")))
    # 3 mm 5052 is no SendCutSend gauge (0.125 in is 3.175 mm): the gauge rules are reported not evaluated and
    # the gauge-free minimum judges the hole 1.5 mm from the tangent line (4.6 mm from the bend line, under
    # half the narrowest die, 6 mm)
    scs_hole = _labelled(_hole(_bracket("scs3", t=3.0, r=3.0), 40 - 1.5 - 1.75, 25, 3.5), "scs3")
    cases.append(Case("scs_3mm_5052_hole_near_bend", scs_hole,
                      [("sheet.hole_to_bend", (36.75, 25, 1.5)), ("sheet.gauge_unmatched", None)],
                      options=dict(rules="sendcutsend", material="5052", thickness=3.0)))
    # 2 mm mild steel is 0.074 in (14 ga): its calculator row's 1.6 mm radius, 0.320 in formed flange and
    # 0.472 in die judge a flange 4 mm past an R1 bend run into the plate without reliefs
    cases.append(Case("scs_2mm_steel_short_flange", tabbed(t=2.0, r=1.0, height=4.0, label="scs2"),
                      [("sheet.bend_radius_shop", None), ("sheet.gauge_thickness", None),  # 2 mm, 0.074 in
                       ("sheet.flange_length", (2.5, 0, 5)),
                       ("sheet.bend_relief_depth", (0, 15, 2)), ("sheet.bend_relief_depth", (0, -15, 2)),
                       ("sheet.bend_relief_width", (0, 15, 2)), ("sheet.bend_relief_width", (0, -15, 2))],
                      options=dict(rules="sendcutsend", material="mild steel")))
    good_scs = _labelled(_hole(_bracket("scsok", t=3.175, r=3.175, base=40, wall=30), 15, 25, 5), "scsok")
    cases.append(Case("scs_clean_0125_5052", good_scs, options=dict(rules="sendcutsend", material="5052")))
    thin = _labelled(_hole(_plate("thin", t=0.8), -50 + 2.2, 0, 2.0), "thin")  # 1.2 mm from the edge
    cases.append(Case("protolabs_thin_edge", thin, [("sheet.hole_to_edge", (-47.8, 0, 0.4))],
                      options=dict(rules="protolabs")))
    # the modelling mistakes an agent makes most: a bracket of two boxes, a sharp corner and no bend radius; a
    # hole drilled across the bend's tangent line; a slot cut across a bend, the bend line in two
    sharp = (bd.Pos(20, 25, 1) * bd.Box(40, 50, 2) + bd.Pos(1, 25, 15) * bd.Box(2, 50, 30)).clean()
    cases.append(Case("sharp_cornered_bracket", _labelled(sharp, "boxes"),
                      [("sheet.sharp_bend", None)]))  # it says why the flat is short: no flat_incomplete
    across = _hole(_bracket("across"), 39.5, 25, 3)  # the tangent line at x = 40 runs through it
    cases.append(Case("hole_across_tangent_line", _labelled(across, "across"),
                      [("sheet.hole_to_bend", (40, 25, 0)), ("sheet.hole_in_bend", None)], near=3))
    slotted = _bracket("slotted") - bd.Pos(40, 25, 4) * bd.Box(12, 3, 12)
    cases.append(Case("slot_across_bend", _labelled(slotted, "slotted"), [("sheet.hole_to_bend", (42.8, 25, 1.2))],
                      near=3))
    return cases


def _events(result) -> list[tuple[str, str | None, list | None]]:
    """Every failure the check reports: each failing rule's every failure (with its xyz), and each finding
    of the measurement's own (by its location)."""
    found = []
    record = result.measurements.get("rules") or {}
    ruled = set()
    for outcome in record.get("outcomes") or []:
        if outcome.get("status") == "failed":
            ruled.add(outcome["rule"])
            found.extend((outcome["rule"], failure["location"], failure.get("xyz")) for failure in outcome["failures"])
    for finding in result.findings:
        if finding.code in ruled or finding.code in INFO or finding.severity == "info":
            continue
        found.append((finding.code, finding.location, None))
    return found


class CorpusTest(unittest.TestCase):
    def test_precision_and_recall_per_code(self) -> None:
        from cad.engine import refs
        from cad.engine.document import Loaded

        started = time.perf_counter()
        tally: dict[str, list[int]] = {}   # code: [true positives, false positives, false negatives]
        problems: list[str] = []
        with tempfile.TemporaryDirectory() as folder:
            for case in corpus():
                path = Path(folder) / f"{case.name}.step"
                if case.unit is not None:
                    bd.export_step(case.shape, str(path), unit=case.unit)
                else:
                    bd.export_step(case.shape, str(path))
                result = step.dfm(path, process="sheet", **case.options)
                scale = 25.4 if case.unit == bd.Unit.IN else 1.0
                structure = Loaded(path).structure()
                events = _events(result)
                matched = [False] * len(case.expect)
                for code, location, xyz in events:
                    if location and "face " in location:
                        if len(refs.resolve_structure(structure, location, path)) != 1:
                            problems.append(f"{case.name}: {code} at {location} does not resolve")
                    hit = False
                    for i, (want, point) in enumerate(case.expect):
                        if want != code:
                            continue
                        if point is not None and (xyz is None or math.dist(xyz, [v * scale for v in point]) >
                                                  case.near * scale):
                            continue
                        matched[i] = True
                        hit = True
                    counts = tally.setdefault(code, [0, 0, 0])
                    if not hit:
                        counts[1] += 1
                        problems.append(f"{case.name}: unexpected {code} at {location} {xyz}")
                for (want, point), ok in zip(case.expect, matched):
                    counts = tally.setdefault(want, [0, 0, 0])
                    if ok:
                        counts[0] += 1
                    else:
                        counts[2] += 1
                        problems.append(f"{case.name}: missed {want} at {point}")
        elapsed = time.perf_counter() - started
        lines = [f"{'code':32} {'TP':>4} {'FP':>4} {'FN':>4} {'precision':>10} {'recall':>7}"]
        for code, (tp, fp, fn) in sorted(tally.items()):
            precision = tp / (tp + fp) if tp + fp else 1.0
            recall = tp / (tp + fn) if tp + fn else 1.0
            lines.append(f"{code:32} {tp:4d} {fp:4d} {fn:4d} {precision:10.2f} {recall:7.2f}")
        from cad._internal.dfm.sheet import NOT_JUDGED, RULE_SETS

        for name, rule_set in RULE_SETS.items():
            ids = sorted({rule.id for rule in rule_set.rules})
            lines.append(f"\n{name}: {len(ids)} rules: {', '.join(i.removeprefix('sheet.') for i in ids)}")
            lines.append(f"{name} does not judge: {', '.join(sorted(NOT_JUDGED.get(name, {}))) or '-'}")
        print("\nsheet corpus, " + f"{len(corpus())} parts in {elapsed:.1f} s\n" + "\n".join(lines), file=sys.stderr)
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
