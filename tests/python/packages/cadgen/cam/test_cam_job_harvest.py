"""The job, tools, feeds and stock rules a second, independent CAM engine taught this one: each a regression test.

Bugs first (a stated stickout, chip thinning on the plunge, rounding past max_rpm, a tap's whole rpm, micro tools'
chip load, a cylinder's margin, stock that does not suit the machine, retract over clearance, a face listed twice,
milling keys on a beam or a lathe tool, a micro tool's shank, a tool id with space round it, a blank with a pocket
where the part stands out, a bar measured on a coarse mesh), then what was added (material aliases and overrides,
per-diameter chip loads, per-operation plunge, clearance and retract, more origins, face mills and counterbores,
the spin-up wait, a required post, a dict job read as a file would be).
"""

from __future__ import annotations

import copy
import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from cadgen._internal.cam.feeds import for_op, for_turn
from cadgen._internal.cam.job import CamJobError, parse_job

BASE = {
    "machine": {"kind": "mill", "post": "grbl", "max_rpm": 24000},
    "material": "aluminum-6061",
    "stock": {"kind": "box", "margin_mm": [2, 2, 1]},
    "tools": [{"id": "T1", "type": "flat", "diameter_mm": 6, "flutes": 3, "flute_length_mm": 18}],
    "setups": [{"id": "top", "operations": [{"op": "face", "tool": "T1"}]}],
}


def job(**changes) -> dict:
    """BASE with ``a__b__0__c=value`` changes."""
    out = copy.deepcopy(BASE)
    for path, value in changes.items():
        target = out
        keys = path.split("__")
        for key in keys[:-1]:
            target = target[int(key)] if key.isdigit() else target[key]
        target[int(keys[-1]) if keys[-1].isdigit() else keys[-1]] = value
    return out


def tool(**raw):
    return parse_job(job(tools=[{"id": "T1", **raw}])).tool("T1")


def refuse(case: unittest.TestCase, expected: str, raw) -> str:
    with case.assertRaises(CamJobError) as caught:
        parse_job(raw)
    case.assertIn(expected, str(caught.exception))
    return str(caught.exception)


def feeds(kind="rough", *, machine=None, material="aluminum-6061", **tool_raw):
    raw = job(tools=[{"id": "T1", **(tool_raw or {"type": "flat", "diameter_mm": 6, "flutes": 3})}],
              material=material)
    if machine:
        raw["machine"].update(machine)
    parsed = parse_job(raw)
    return parsed, lambda **kw: for_op(parsed.material, parsed.tool("T1"), kind, parsed.machine, **kw)


class ToolBugs(unittest.TestCase):
    def test_a_stated_stickout_with_no_flute_length_cuts_the_default_flutes_back(self):
        cutter = tool(type="flat", diameter_mm=10, stickout_mm=25)
        self.assertEqual((25.0, 25.0), (cutter.flute_length_mm, cutter.stickout_mm))
        self.assertEqual(18.0, tool(type="flat", diameter_mm=6, stickout_mm=40).flute_length_mm)   # 3 x D fits
        refuse(self, "stickout_mm (10) is shorter than flute_length_mm",
               job(tools=[{"id": "T1", "type": "flat", "diameter_mm": 6, "flute_length_mm": 18, "stickout_mm": 10}]))

    def test_a_micro_cutter_sits_on_a_3mm_shank_unless_the_job_says(self):
        for kind, extra in (("flat", {}), ("ball", {}), ("bull", {"corner_radius_mm": 0.2}),
                            ("thread_mill", {"pitch_mm": 0.5}), ("engraver", {})):
            with self.subTest(kind=kind):
                self.assertEqual(3.0, tool(type=kind, diameter_mm=1, **extra).holder.shank_diameter_mm)
        self.assertEqual(6.0, tool(type="flat", diameter_mm=6).holder.shank_diameter_mm)
        self.assertEqual(1.0, tool(type="drill", diameter_mm=1).holder.shank_diameter_mm)
        self.assertEqual(2.0, tool(type="flat", diameter_mm=1, shank_diameter_mm=2).holder.shank_diameter_mm)

    def test_a_tool_id_with_space_round_it_is_refused(self):
        refuse(self, "has space around it", job(tools=[{"id": " T1", "type": "flat", "diameter_mm": 6}]))

    def test_each_family_takes_only_the_keys_its_tools_read(self):
        cases = {
            "unknown key 'flutes'": {"id": "T1", "type": "beam", "kerf_mm": 0.2, "flutes": 2},
            "unknown key 'material'": {"id": "T1", "type": "wire", "diameter_mm": 0.25, "material": "carbide"},
            "unknown key 'stickout_mm'": {"id": "T1", "type": "turn", "stickout_mm": 30},
            "unknown key 'holder_diameter_mm'": {"id": "T1", "type": "groove", "width_mm": 3,
                                                 "holder_diameter_mm": 30},
        }
        for expected, raw in cases.items():
            with self.subTest(expected=expected):
                refuse(self, expected, job(tools=[raw]))
        # A lathe tool keeps what it reads: its material (HSS turns slower) and a bar's diameter (its reach).
        lathe = {"machine": {"kind": "lathe", "post": "linuxcnc"}, "material": "brass",
                 "stock": {"kind": "cylinder", "diameter_mm": 20, "length_mm": 50},
                 "tools": [{"id": "T1", "type": "turn", "material": "hss", "diameter_mm": 6}],
                 "setups": [{"operations": [{"op": "turn_face", "tool": "T1"}]}]}
        self.assertEqual("hss", parse_job(lathe).tool("T1").material)

    def test_a_holder_states_its_diameter_and_its_length(self):
        refuse(self, "needs \"holder_length_mm\"",
               job(tools=[{"id": "T1", "type": "flat", "diameter_mm": 6, "holder_diameter_mm": 30}]))
        refuse(self, "needs \"holder_diameter_mm\"",
               job(tools=[{"id": "T1", "type": "flat", "diameter_mm": 6, "holder_length_mm": 40}]))
        held = tool(type="flat", diameter_mm=6, holder_diameter_mm=30, holder_length_mm=50).holder
        self.assertEqual((30.0, 50.0), (held.holder_diameter_mm, held.holder_length_mm))


class FeedsBugs(unittest.TestCase):
    def test_chip_thinning_never_raises_the_plunge(self):
        _, at = feeds("finish")
        full, light = at(), at(stepover_mm=0.3)
        self.assertGreater(light.feed_mm_min, full.feed_mm_min)
        self.assertEqual(full.plunge_mm_min, light.plunge_mm_min)

    def test_rounding_never_lifts_the_spindle_past_max_rpm(self):
        _, at = feeds(machine={"max_rpm": 12006})
        result = at()
        self.assertEqual(12006, result.rpm)
        self.assertTrue(result.clamped)
        _, at = feeds(machine={"max_rpm": 12006.7})
        self.assertEqual(12006, at().rpm)

    def test_a_tap_slowed_for_the_feed_limit_turns_a_whole_rpm(self):
        _, at = feeds("tap", machine={"max_feed_mm_min": 500}, type="tap", diameter_mm=12, pitch_mm=1.75)
        result = at()
        self.assertEqual(285.0, result.rpm)
        self.assertEqual(285 * 1.75, result.feed_mm_min)
        self.assertLessEqual(result.feed_mm_min, 500)
        self.assertEqual(result.feed_mm_min, result.plunge_mm_min)

    def test_chip_load_grows_with_diameter_from_micro_tools_and_holds_past_20mm(self):
        loads = []
        for diameter in (0.3, 0.5, 1, 2, 3, 4.5, 6, 8, 10, 12, 16, 20, 25, 40):
            _, at = feeds("rough", type="flat", diameter_mm=diameter, flutes=2)
            loads.append(at().chipload_mm)
        self.assertEqual(sorted(loads), loads)
        self.assertLess(loads[1], loads[2])                 # 0.5 mm takes less than 1 mm
        self.assertAlmostEqual(0.5 * loads[2], loads[1], places=5)   # in proportion under 1 mm
        self.assertEqual(0.04, loads[6])                    # the table's number at 6 mm
        self.assertEqual(loads[11], loads[12])              # held past 20 mm
        self.assertEqual(loads[11], loads[13])

    def test_a_thread_mill_takes_half_the_chip_load(self):
        _, mill = feeds("thread_mill", type="thread_mill", diameter_mm=6, pitch_mm=1, flutes=3)
        _, flat = feeds("rough", type="flat", diameter_mm=6, flutes=3)
        self.assertAlmostEqual(0.5 * flat().chipload_mm, mill().chipload_mm)


class JobBugs(unittest.TestCase):
    def test_a_bar_of_a_stated_diameter_takes_no_radial_margin(self):
        mill4 = {"kind": "mill4", "post": "linuxcnc"}
        refuse(self, "give diameter_mm or a radial margin_mm",
               job(machine=mill4, stock={"kind": "cylinder", "axis": "x", "diameter_mm": 30, "margin_mm": 2}))
        refuse(self, "give length_mm or an axial margin_mm",
               job(machine=mill4, stock={"kind": "cylinder", "axis": "x", "length_mm": 30, "margin_mm": [0, 2]}))
        parsed = parse_job(job(machine=mill4, stock={"kind": "cylinder", "axis": "x", "diameter_mm": 30,
                                                     "margin_mm": [0, 2]}))
        self.assertEqual((0.0, 2.0), parsed.stock.margin_mm)
        self.assertEqual((3.0, 3.0), parse_job(job(machine=mill4, stock={"kind": "cylinder", "margin_mm": 3})).stock.margin_mm)

    def test_a_cylinders_axial_margin_goes_on_both_ends(self):
        import numpy as np

        from cadgen._internal.cam.stock import build_stock

        parsed = parse_job(job(machine={"kind": "mill4", "post": "linuxcnc"},
                               stock={"kind": "cylinder", "axis": "x", "margin_mm": [1, 2]}))
        corners = np.array([[x, y, z] for x in (0, 40) for y in (-5, 5) for z in (-5, 5)], dtype=float)
        part = SimpleNamespace(bbox=(corners.min(axis=0), corners.max(axis=0)), vertices=corners, shape=None,
                               document=None, faces={})
        stock = build_stock(parsed.stock, part)
        self.assertAlmostEqual(-2.0, stock.bounds_min[0])
        self.assertAlmostEqual(42.0, stock.bounds_max[0])
        self.assertAlmostEqual(math.hypot(5, 5) + 1, stock.cylinder["radius"])

    def test_the_stock_must_suit_the_machine(self):
        refuse(self, "a lathe turns bar stock",
               {**job(machine={"kind": "lathe", "post": "linuxcnc"}, stock={"kind": "box", "margin_mm": 1}),
                "tools": [{"id": "T1", "type": "turn"}],
                "setups": [{"operations": [{"op": "turn_face", "tool": "T1"}]}]})
        message = refuse(self, "a laser cuts from a sheet",
                         {**job(machine={"kind": "laser", "post": "grbl"}, stock={"kind": "box", "margin_mm": 1}),
                          "tools": [{"id": "T1", "type": "beam", "kerf_mm": 0.2}],
                          "setups": [{"operations": [{"op": "cut", "tool": "T1"}]}]})
        self.assertIn("stock.kind", message)
        self.assertEqual("sheet", parse_job(job(stock={"kind": "sheet", "thickness_mm": 6})).stock.kind)

    def test_retract_above_clearance_is_refused(self):
        message = refuse(self, "retract_mm (6 mm) must be at or under",
                         job(setups__0__clearance_mm=5, setups__0__retract_mm=6))
        self.assertIn("clearance_mm (5 mm)", message)
        refuse(self, "retract_mm (2 mm) must be at or under",
               job(setups__0__clearance_mm=1.5))   # the default retract over a lowered clearance

    def test_a_face_listed_twice_is_refused(self):
        refuse(self, "'#o1.f20' is listed twice",
               job(setups__0__operations=[{"op": "pocket", "tool": "T1", "faces": ["#o1.f20", "#o1.f20"]}]))


class Materials(unittest.TestCase):
    def test_aliases_resolve_to_the_tables_row(self):
        self.assertEqual("steel-1018", parse_job(job(material="mild-steel")).material.name)
        self.assertEqual("delrin", parse_job(job(material="acetal")).material.name)
        self.assertEqual("delrin", parse_job(job(material={"name": "acetal", "surface_m_min": 200})).material.name)
        self.assertIn("mild-steel", refuse(self, "material is 'unobtainium'", job(material="unobtainium")))

    def test_a_table_material_with_one_number_overridden_keeps_the_rest(self):
        parsed, at = feeds(material={"name": "aluminum-6061", "surface_m_min": 300})
        self.assertTrue(parsed.material.table)
        _, table = feeds()
        self.assertAlmostEqual(300 / 250, at().rpm / table().rpm, places=2)
        self.assertEqual(table().chipload_mm, at().chipload_mm)
        refuse(self, "surface_m_min (metres a minute) or sfm",
               job(material={"name": "aluminum-6061", "surface_m_min": 300, "sfm": 900}))
        refuse(self, "material needs chipload_mm", job(material={"name": "bronze", "surface_m_min": 90}))

    def test_one_chip_load_is_a_6mm_tools_scaled_with_the_diameter_as_the_tables_is(self):
        material = {"name": "bronze", "surface_m_min": 90, "chipload_mm": 0.04}
        loads = {d: feeds(material=material, type="flat", diameter_mm=d, flutes=2)[1]().chipload_mm for d in (1, 3, 6)}
        self.assertEqual({1: 0.008, 3: 0.02, 6: 0.04}, loads)
        # On a table row it replaces the row's 6 mm number, so it scales the same way.
        _, table = feeds(type="flat", diameter_mm=3, flutes=2)
        _, half = feeds(material={"name": "aluminum-6061", "chipload_mm": 0.02}, type="flat", diameter_mm=3, flutes=2)
        self.assertAlmostEqual(table().chipload_mm / 2, half().chipload_mm, places=5)

    def test_a_chip_load_per_tool_diameter_is_interpolated(self):
        material = {"name": "bronze", "surface_m_min": 90, "chipload_mm": {"3": 0.02, "6": 0.04}}
        loads = {d: feeds(material=material, type="flat", diameter_mm=d, flutes=2)[1]().chipload_mm
                 for d in (1.5, 3, 4.5, 6, 12)}
        self.assertEqual({1.5: 0.01, 3: 0.02, 4.5: 0.03, 6: 0.04, 12: 0.04}, loads)
        for bad, words in (({"3": 0.02, "3.0": 0.03}, "listed twice"), ({"nan": 0.02}, "not a tool diameter"),
                           ({"0": 0.02}, "not a tool diameter"), ({"-1": 0.02}, "not a tool diameter"),
                           ({"abc": 0.02}, "not a tool diameter"), ({}, "one per tool diameter"),
                           ({"3": -0.02}, "chipload_mm.3 must be more than 0")):
            with self.subTest(bad=bad):
                refuse(self, words, job(material={**material, "chipload_mm": bad}))

    def test_a_turning_surface_speed_override_is_read_too(self):
        lathe = {"machine": {"kind": "lathe", "post": "linuxcnc", "max_rpm": 99999}, "material": "brass",
                 "stock": {"kind": "cylinder", "diameter_mm": 20, "length_mm": 50},
                 "tools": [{"id": "T1", "type": "turn"}],
                 "setups": [{"operations": [{"op": "turn_face", "tool": "T1"}]}]}
        table = parse_job(lathe)
        faster = parse_job({**lathe, "material": {"name": "brass", "surface_m_min": 440}})
        rpm = lambda p: for_turn(p.material, p.tool("T1"), "turn_rough", p.machine, diameter_mm=20).rpm  # noqa: E731
        self.assertAlmostEqual(2.0, rpm(faster) / rpm(table), places=2)


class Overrides(unittest.TestCase):
    def test_plunge_mm_min_is_an_operations_override(self):
        from cadgen._internal.cam.run import parse_operations

        parsed = parse_job(job(setups__0__operations=[{"op": "pocket", "tool": "T1", "region": {
            "polygon": [[0, 0], [10, 0], [10, 10]], "bottom_z": -2}, "plunge_mm_min": 123}]))
        spec = parsed.setups[0].operations[0]
        self.assertEqual(123.0, spec.plunge_mm_min)
        parse_operations(parsed)
        result = for_op(parsed.material, parsed.tool("T1"), "rough", parsed.machine, plunge=123)
        self.assertEqual(123.0, result.plunge_mm_min)
        self.assertEqual("mixed", result.source)
        clamped = parse_job(job(machine__max_feed_mm_min=100))
        result = for_op(clamped.material, clamped.tool("T1"), "rough", clamped.machine, plunge=123)
        self.assertEqual(100.0, result.plunge_mm_min)
        drill = parse_job(job(tools=[{"id": "T1", "type": "drill", "diameter_mm": 5}],
                              setups__0__operations=[{"op": "drill", "tool": "T1", "faces": ["#o1.f3"],
                                                      "plunge_mm_min": 50}]))
        with self.assertRaisesRegex(CamJobError, "a drill does not use plunge_mm_min"):
            parse_operations(drill)

    def test_an_operation_may_set_its_own_clearance_and_retract(self):
        parsed = parse_job(job(setups__0__operations__0__clearance_mm=12, setups__0__operations__0__retract_mm=4))
        spec = parsed.setups[0].operations[0]
        self.assertEqual((12.0, 4.0), (spec.clearance_mm, spec.retract_mm))
        plain = parse_job(BASE).setups[0].operations[0]
        self.assertEqual((None, None), (plain.clearance_mm, plain.retract_mm))
        refuse(self, "operations[0].retract_mm (4 mm) must be at or under",
               job(setups__0__operations__0__clearance_mm=3, setups__0__operations__0__retract_mm=4))
        refuse(self, "operations[0].retract_mm (6 mm) must be at or under",   # against the setup's 5 mm
               job(setups__0__operations__0__retract_mm=6))
        refuse(self, "clearance_mm must be more than 0", job(setups__0__operations__0__clearance_mm=0))
        # An operation's own key of the same name is the operation's: a drill's chip-break retract_mm.
        drill = parse_job(job(tools=[{"id": "T1", "type": "drill", "diameter_mm": 5}], setups__0__operations=[
            {"op": "drill", "tool": "T1", "faces": ["#o1.f3"], "cycle": "chipbreak", "retract_mm": 0.3}]))
        spec = drill.setups[0].operations[0]
        self.assertEqual((None, 0.3), (spec.retract_mm, spec.extra["retract_mm"]))


class Origins(unittest.TestCase):
    def test_every_origin_keyword_and_a_bare_point(self):
        import numpy as np

        from cadgen._internal.cam.wcs import build_wcs

        stock = np.array([[-10, -5, -1], [10, 5, 21]], dtype=float)
        part = np.array([[-8, -3, 0], [8, 3, 20]], dtype=float)
        expected = {
            "stock-top-center": [0, 0, 21], "stock-top-corner": [-10, -5, 21], "stock-center": [0, 0, 10],
            "stock-bottom-center": [0, 0, -1], "stock-bottom-corner": [-10, -5, -1],
            "part-top-center": [0, 0, 20], "part-top-corner": [-8, -3, 20], "part-center": [0, 0, 10],
            "part-bottom-center": [0, 0, 0], "part-bottom-corner": [-8, -3, 0],
        }
        for origin, at in expected.items():
            with self.subTest(origin=origin):
                setup = parse_job(job(setups__0__origin=origin)).setups[0]
                wcs = build_wcs(setup, stock_points=stock, part_points=part)
                self.assertEqual([float(v) for v in at], wcs.origin_part_mm)
        point = parse_job(job(setups__0__origin=[1, 2, 3])).setups[0]
        self.assertEqual({"xyz": (1.0, 2.0, 3.0)}, point.origin)

    def test_the_other_engines_spellings_teach_ours(self):
        self.assertIn("did you mean 'part-bottom-corner'?",
                      refuse(self, "setups[0].origin is", job(setups__0__origin="part_bbox_bottom_corner")))
        self.assertIn("did you mean 'stock-top-center'?",
                      refuse(self, "setups[0].origin is", job(setups__0__origin="stock_top_center")))
        refuse(self, "must be a list of 3 numbers", job(setups__0__origin=[1, 2]))

    def test_a_lathe_zero_is_never_a_corner(self):
        lathe = {"machine": {"kind": "lathe", "post": "linuxcnc"}, "material": "brass",
                 "stock": {"kind": "cylinder", "diameter_mm": 20, "length_mm": 50},
                 "tools": [{"id": "T1", "type": "turn"}],
                 "setups": [{"origin": "part-bottom-corner", "operations": [{"op": "turn_face", "tool": "T1"}]}]}
        refuse(self, "a lathe's work zero sits on the spindle axis", lathe)


class NewTools(unittest.TestCase):
    def test_a_face_mill(self):
        mill = tool(type="face_mill", diameter_mm=50)
        self.assertEqual((4, "50 mm face mill", "mill"), (mill.flutes, mill.plain, mill.family))
        self.assertLess(mill.flute_length_mm, 50)
        self.assertEqual(0.0, mill.height_at(20.0))

    def test_a_counterbore_and_its_pilot(self):
        bore = tool(type="counterbore", diameter_mm=10, pilot_diameter_mm=5.5)
        self.assertEqual((2.75, 5.0), (bore.radius_at(1.0), bore.radius_at(6.0)))
        self.assertEqual((0.0, 5.5, math.inf), (bore.height_at(2.0), bore.height_at(4.0), bore.height_at(6.0)))
        self.assertEqual("10 mm counterbore", bore.plain)
        plain = tool(type="counterbore", diameter_mm=10)
        self.assertEqual(0.0, plain.height_at(4.0))
        refuse(self, "pilot_diameter_mm must be less than diameter_mm",
               job(tools=[{"id": "T1", "type": "counterbore", "diameter_mm": 10, "pilot_diameter_mm": 10}]))
        refuse(self, "does not reach past its 5.5 mm pilot",
               job(tools=[{"id": "T1", "type": "counterbore", "diameter_mm": 10, "pilot_diameter_mm": 5.5,
                           "stickout_mm": 4}]))


class MachineAndLoading(unittest.TestCase):
    def test_a_post_left_out_is_the_kinds_usual_one_and_said(self):
        for kind, post in (("mill", "fanuc"), ("router", "grbl")):
            with self.subTest(kind=kind):
                parsed = parse_job(job(machine={"kind": kind}))
                self.assertEqual(post, parsed.machine.post)
                (entry,) = [entry for entry in parsed.assumed if entry["key"] == "machine.post"]
                self.assertEqual(post, entry["value"])

    def test_spindle_spinup_s(self):
        self.assertIsNone(parse_job(BASE).machine.spindle_spinup_s)
        parsed = parse_job(job(machine={"kind": "mill", "post": "linuxcnc", "spindle_spinup_s": 2.5}))
        self.assertEqual(2.5, parsed.machine.spindle_spinup_s)
        self.assertEqual(2.5, parsed.machine.as_dict()["spindle_spinup_s"])
        self.assertEqual(0.0, parse_job(job(machine__spindle_spinup_s=0)).machine.spindle_spinup_s)
        refuse(self, "spindle_spinup_s must be at least 0", job(machine__spindle_spinup_s=-1))

    def test_travel_has_the_machines_axes(self):
        refuse(self, "a mill's travel_mm is [x, y, z]", job(machine__travel_mm=[300, 200]))
        lathe = {"machine": {"kind": "lathe", "post": "linuxcnc", "travel_mm": [200, 300, 100]}, "material": "brass",
                 "stock": {"kind": "cylinder", "diameter_mm": 20, "length_mm": 50},
                 "tools": [{"id": "T1", "type": "turn"}],
                 "setups": [{"operations": [{"op": "turn_face", "tool": "T1"}]}]}
        refuse(self, "a lathe's travel_mm is [x, z]", lathe)

    def test_a_dict_job_reads_as_its_file_would_and_shares_nothing(self):
        region = {"polygon": [[0, 0], [10, 0], [10, 10]]}
        raw = job(setups__0__operations=[{"op": "pocket", "tool": "T1", "region": region}],
                  stock={"kind": "box", "margin_mm": (2, 2, 1)})
        parsed = parse_job(raw)
        region["polygon"].append([0, 10])
        self.assertEqual(3, len(parsed.setups[0].operations[0].region["polygon"]))
        self.assertEqual((2.0, 2.0, 2.0, 2.0, 0.0, 1.0), parsed.stock.margin_mm)
        refuse(self, "not plain JSON", job(machine__max_rpm=math.nan))
        refuse(self, "not plain JSON", job(name=object()))
        refuse(self, "NaN is not a number a job can hold", '{"machine": {"kind": "mill", "max_rpm": NaN}}')


class StockSolids(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = tempfile.TemporaryDirectory(prefix="cam-harvest-")
        cls.addClassCleanup(folder.cleanup)
        cls.folder = Path(folder.name)

    def test_a_blank_with_a_pocket_where_the_part_stands_out_is_refused(self):
        from build123d import Align, Box, Pos, export_step

        from cadgen._internal.cam.part import read_part
        from cadgen._internal.cam.stock import build_stock

        base = (Align.CENTER, Align.CENTER, Align.MIN)
        export_step(Box(60, 40, 6, align=base), str(self.folder / "plate.step"))
        export_step(Pos(0, 0, -1) * (Box(70, 50, 8, align=base) - Box(10, 10, 8, align=base)),
                    str(self.folder / "ring.step"))
        part = read_part(self.folder / "plate.step")
        # The part as its own blank: nothing stands outside it (each STEP read is a build, so the suite reads two).
        good = parse_job(job(stock={"kind": "from_step", "path": "plate.step"}))
        self.assertEqual("from_step", build_stock(good.stock, part).kind)
        bad = parse_job(job(stock={"kind": "from_step", "path": "ring.step"}))
        with self.assertRaisesRegex(CamJobError, "600 mm3 of the part stands outside it"):
            build_stock(bad.stock, part)

    def test_a_missing_absolute_blank_is_refused_at_parse(self):
        refuse(self, "stock.path: no STEP at", job(stock={"kind": "from_step", "path": str(self.folder / "no.step")}))
        self.assertEqual("nope.step", parse_job(job(stock={"kind": "from_step", "path": "nope.step"})).stock.path)

    def test_a_bar_is_measured_on_the_true_part_not_a_coarse_mesh(self):
        import numpy as np
        from build123d import Cylinder

        from cadgen._internal.cam.stock import build_stock

        # A Ø20 x 20 cylinder along Z, its bar along X: the farthest point from the bar's axis is on a rim at
        # y = ±10, sqrt(200) out; a coarse mesh with no node there reads 13.6.
        angles = np.radians(np.arange(22.5, 360, 45))
        rims = [[10 * math.cos(a), 10 * math.sin(a), z] for a in angles for z in (-10.0, 10.0)]
        vertices = np.asarray(rims, dtype=float)
        part = SimpleNamespace(bbox=(np.array([-10.0, -10, -10]), np.array([10.0, 10, 10])), vertices=vertices,
                               shape=Cylinder(10, 20), document=None, faces={})
        mill4 = {"kind": "mill4", "post": "linuxcnc"}
        with self.assertRaisesRegex(CamJobError, "does not hold the part"):
            build_stock(parse_job(job(machine=mill4, stock={"kind": "cylinder", "axis": "x",
                                                             "diameter_mm": 28})).stock, part)
        bar = build_stock(parse_job(job(machine=mill4, stock={"kind": "cylinder", "axis": "x"})).stock, part)
        self.assertGreaterEqual(bar.cylinder["radius"], math.sqrt(200) - 1e-4)


if __name__ == "__main__":
    unittest.main()
