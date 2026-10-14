"""Optional machine models and what a plan assumes: the catalog's integrity, a model's numbers under the job's own,
the kind's generic values when nobody states them (each listed in ``assumed`` with its reason), and checks that do
not stand behind a guessed tool length."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from cadgen._internal.cam import machines
from cadgen._internal.cam import posts as post_registry
from cadgen._internal.cam.feeds import for_op
from cadgen._internal.cam.job import CamJobError, parse_job
from cadgen.results import CamPlanResult

from tests.python.support.cam_fixtures import BLOCK, block_step, class_directory, floor_ref, mill_job, quiet

SKILL = Path(__file__).resolve().parents[5] / "skills" / "cam"


def job(machine: dict, **extra) -> dict:
    return {"machine": machine, "material": "aluminum-6061", "stock": {"kind": "box", "margin_mm": [2, 2, 1]},
            "tools": [{"id": "T1", "type": "flat", "diameter_mm": 6, "flutes": 3, "flute_length_mm": 18,
                       "stickout_mm": 25}],
            "setups": [{"id": "top", "operations": [{"op": "face", "tool": "T1"}]}], **extra}


def assumed(parsed) -> dict:
    return {entry["key"]: entry["value"] for entry in parsed.assumed}


class Catalog(unittest.TestCase):
    def test_every_model_posts_for_its_kind_from_its_makers_page(self):
        travel = {"lathe": 2, "laser": 2, "plasma": 2, "waterjet": 2}
        plains = set()
        for model in machines.MODELS.values():
            with self.subTest(model=model.id):
                self.assertRegex(model.id, r"^[a-z0-9]+(-[a-z0-9]+)*$")
                self.assertNotIn(model.plain, plains)
                plains.add(model.plain)
                post_registry.entry_for(model.post, model.kind)
                self.assertTrue(model.source.startswith("https://"), model.source)
                if model.travel_mm is not None:
                    self.assertEqual(travel.get(model.kind, 3), len(model.travel_mm))
                    self.assertTrue(all(axis > 0 for axis in model.travel_mm))
                if model.min_rpm is not None and model.max_rpm is not None:
                    self.assertLess(model.min_rpm, model.max_rpm)
                self.assertIn(model.tool_changer, (None, "none", "manual", "atc"))
                self.assertEqual(model.tool_changer == "atc", model.tool_capacity is not None)
                # A model alone is a machine: it parses with no other machine key.
                self.assertEqual(model.id, parse_job(_job_for(model)).machine.model)

    def test_every_kind_has_a_generic_post_that_serves_it(self):
        from cadgen._internal.cam.job import MACHINE_KINDS

        self.assertEqual(sorted(MACHINE_KINDS), sorted(machines.GENERIC))
        for kind, values in machines.GENERIC.items():
            with self.subTest(kind=kind):
                post_registry.entry_for(values["post"][0], kind)

    def test_job_file_md_lists_every_model_with_its_kind_and_post(self):
        body = (SKILL / "references" / "job-file.md").read_text(encoding="utf-8")
        section = body.split("### Machine models", 1)[1].split("\n## ", 1)[0]
        rows = {}
        for line in section.splitlines():
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            found = re.fullmatch(r"`([a-z0-9-]+)`", cells[0]) if line.startswith("|") else None
            if found:
                rows[found.group(1)] = cells
        self.assertEqual(sorted(machines.MODELS), sorted(rows))
        for model in machines.MODELS.values():
            with self.subTest(model=model.id):
                self.assertEqual([model.plain, f"`{model.kind}`", f"`{model.post}`"], rows[model.id][1:4])


def _job_for(model) -> dict:
    """A job the model's kind of machine takes, naming only the model."""
    if model.kind in ("mill", "mill4", "mill5", "router"):
        return job({"model": model.id})
    if model.kind == "lathe":
        return job({"model": model.id}, stock={"kind": "cylinder", "diameter_mm": 20, "length_mm": 50},
                   tools=[{"id": "T1", "type": "turn"}], setups=[{"operations": [{"op": "turn_face", "tool": "T1"}]}])
    return job({"model": model.id}, stock={"kind": "sheet", "thickness_mm": 3}, tools=[{"id": "T1", "type": "beam", "kerf_mm": 0.2}],
               setups=[{"operations": [{"op": "cut", "tool": "T1"}]}])


class Models(unittest.TestCase):
    def test_a_model_by_id_or_name_fills_in_what_the_job_leaves_out_and_the_job_wins(self):
        for name in ("tormach-1100mx", "Tormach 1100MX", "tormach 1100 mx"):
            with self.subTest(name=name):
                machine = parse_job(job({"model": name})).machine
                self.assertEqual(("tormach-1100mx", "mill", "linuxcnc"), (machine.model, machine.kind, machine.post))
                self.assertEqual((70.0, 10000.0, 7620.0), (machine.min_rpm, machine.max_rpm, machine.rapid_mm_min))
                self.assertTrue(machine.rigid_tap)
                self.assertEqual((457.0, 279.0, 413.0), machine.travel_mm)
        parsed = parse_job(job({"model": "tormach-1100mx", "max_rpm": 5000, "post": "grbl"}))
        self.assertEqual((5000.0, "grbl", 70.0), (parsed.machine.max_rpm, parsed.machine.post, parsed.machine.min_rpm))
        # What the maker publishes is not assumed; what it leaves out (the 1100MX's tool change time) is, and says so,
        # as is the GRBL post's own spin-up dwell the job swapped in.
        self.assertEqual(["machine.tool_change_s", "machine.spindle_spinup_s"], list(assumed(parsed)))
        self.assertIn("the Tormach 1100MX's maker publishes none", parsed.assumed[0]["why"])
        self.assertEqual("tormach-1100mx", parsed.machine.as_dict()["model"])

    def test_a_model_takes_its_4th_axis_kind_only_where_the_maker_offers_one(self):
        self.assertEqual("mill4", parse_job(job({"model": "tormach-1100mx", "kind": "mill4"})).machine.kind)
        cases = {
            "the Haas VF-2 is a mill; remove kind, or give 'mill'": {"model": "haas-vf-2", "kind": "mill4"},
            "the Haas ST-10 is a lathe": {"model": "haas-st-10", "kind": "mill"},
        }
        for words, machine in cases.items():
            with self.subTest(words=words), self.assertRaises(CamJobError) as caught:
                parse_job(job(machine))
            self.assertIn(words, str(caught.exception))

    def test_an_unknown_or_unsupported_model_is_a_teaching_refusal(self):
        cases = {
            "not in cadgen's catalog (did you mean 'tormach-1100mx'": {"model": "tormach-1100"},
            "reads no G-code file, so cadgen cannot post for it: export the part's outline as a DXF":
                {"model": "Glowforge Pro"},
            "runs a Ruida controller": {"model": "omtech-60w"},
            "runs Makera's own Smoothieware-based firmware": {"model": "Carvera Air"},
            "names a machine model, like \"haas-vf-2\", not": {"model": ""},
            "machine needs a model (like \"tormach-1100mx\") or a kind": {},
        }
        for words, machine in cases.items():
            with self.subTest(words=words), self.assertRaises(CamJobError) as caught:
                parse_job(job(machine))
            self.assertIn(words, str(caught.exception))


class Assumed(unittest.TestCase):
    def test_a_machine_named_only_by_kind_lists_every_generic_value_it_takes(self):
        parsed = parse_job(job({"kind": "mill"}))
        self.assertEqual({"machine.post": "fanuc", "machine.max_rpm": 8000.0, "machine.rapid_mm_min": 5000.0,
                          "machine.tool_change_s": 10.0}, assumed(parsed))
        self.assertTrue(all(entry["why"] for entry in parsed.assumed))
        self.assertEqual((8000.0, 5000.0, 10.0), (parsed.machine.max_rpm, parsed.machine.rapid_mm_min,
                                                  parsed.machine.tool_change_s))
        # Stated, a key is not assumed; a GRBL post's spin-up dwell is (it does not wait for the spindle).
        stated = parse_job(job({"kind": "router", "post": "grbl", "max_rpm": 24000, "rapid_mm_min": 5000,
                                "tool_change_s": 30}))
        self.assertEqual({"machine.spindle_spinup_s": 3.0}, assumed(stated))

    def test_an_assumed_rapid_is_no_faster_than_the_machines_top_speed(self):
        parsed = parse_job(job({"model": "longmill-mk2-30x30"}))
        self.assertEqual(4000.0, parsed.machine.rapid_mm_min)
        (rapid,) = [entry for entry in parsed.assumed if entry["key"] == "machine.rapid_mm_min"]
        self.assertEqual(4000.0, rapid["value"])
        self.assertIn("the machine's maximum feed: a rapid runs no faster", rapid["why"])

    def test_a_guess_the_job_marks_is_listed_first_and_must_be_one_it_gives(self):
        parsed = parse_job(job({"kind": "mill", "post": "linuxcnc", "assumed": ["kind"]}))
        self.assertEqual({"key": "machine.kind", "value": "mill",
                          "why": "the job marks it as a guess: the user did not know"}, parsed.assumed[0])
        cases = {"machine.assumed names 'post', which the machine does not give": ["post"],
                 "machine.assumed[] is 'model'": ["model"],
                 "machine.assumed lists the machine keys": "kind"}
        for words, guesses in cases.items():
            with self.subTest(words=words), self.assertRaises(CamJobError) as caught:
                parse_job(job({"kind": "mill", "assumed": guesses}))
            self.assertIn(words, str(caught.exception))

    def test_min_rpm_raises_a_slow_speed_and_says_so(self):
        with self.assertRaises(CamJobError) as caught:
            parse_job(job({"kind": "router", "post": "grbl", "min_rpm": 30000, "max_rpm": 24000}))
        self.assertIn("machine.min_rpm (30000) is more than machine.max_rpm (24000)", str(caught.exception))
        router = {"kind": "router", "post": "grbl", "min_rpm": 18000, "max_rpm": 24000}
        # A 5 mm cutter wants ~15900 rpm in aluminium: raised a little, and said.
        parsed = parse_job(job(router, tools=[{"id": "T1", "type": "flat", "diameter_mm": 5}]))
        cut = for_op(parsed.material, parsed.tool("T1"), "rough", parsed.machine)
        self.assertEqual(18000, cut.rpm)
        self.assertTrue(any("raised to the machine's slowest, 18000 rpm" in line for line in cut.clamped))
        # A 25 mm one wants ~3200: 5.7 times its surface speed burns it in metal, so it is refused with what to do.
        parsed = parse_job(job(router, tools=[{"id": "T1", "type": "flat", "diameter_mm": 25}]))
        with self.assertRaises(CamJobError) as caught:
            for_op(parsed.material, parsed.tool("T1"), "rough", parsed.machine)
        self.assertIn("5.7 times the surface speed", str(caught.exception))
        self.assertIn("Use a smaller tool", str(caught.exception))
        # In wood a router runs a big cutter fast every day: raised, not refused.
        parsed = parse_job(job(router, material="hardwood", tools=[{"id": "T1", "type": "flat", "diameter_mm": 25}]))
        self.assertEqual(18000, for_op(parsed.material, parsed.tool("T1"), "rough", parsed.machine).rpm)

    def test_a_tap_or_a_hole_maker_too_slow_for_the_spindle_is_refused_even_in_wood(self):
        router = {"kind": "router", "post": "grbl", "min_rpm": 18000, "max_rpm": 24000}
        parsed = parse_job(job(router, material="hardwood", tools=[
            {"id": "T1", "type": "flat", "diameter_mm": 6, "flutes": 2},
            {"id": "T2", "type": "tap", "diameter_mm": 6, "pitch_mm": 1},
            {"id": "T3", "type": "drill", "diameter_mm": 20}]))
        with self.assertRaises(CamJobError) as caught:
            for_op(parsed.material, parsed.tool("T2"), "tap", parsed.machine)
        self.assertIn("no tap runs that fast. Mill the thread (thread_mill)", str(caught.exception))
        # A drill's chip is its whole width at the centre, where the surface speed is nil: past 1.3x it burns in wood
        # too, and a smaller drill makes a smaller hole.
        with self.assertRaises(CamJobError) as caught:
            for_op(parsed.material, parsed.tool("T3"), "drill", parsed.machine)
        self.assertIn("Mill the hole with a smaller end mill (circular)", str(caught.exception))
        # A speed the job states is the user's call: raised to the floor, not refused.
        self.assertEqual(18000, for_op(parsed.material, parsed.tool("T3"), "drill", parsed.machine, speed=9000).rpm)

    def test_a_model_whose_spindle_speed_is_a_dial_says_how_to_set_it(self):
        parsed = parse_job(job({"model": "shapeoko-5-pro"}))
        (spindle,) = [entry for entry in parsed.assumed if entry["key"] == "machine.spindle"]
        self.assertIn("dial 1", spindle["why"])
        self.assertIn("min_rpm 8000", spindle["why"])
        stated = parse_job(job({"model": "shapeoko-5-pro", "min_rpm": 8000, "max_rpm": 24000}))
        self.assertNotIn("machine.spindle", assumed(stated))

    def test_used_hole_makers_and_fluted_tools_say_the_material_and_flutes_they_take(self):
        parsed = parse_job(job({"kind": "mill", "post": "grbl", "max_rpm": 24000, "rapid_mm_min": 5000,
                                "tool_change_s": 10},
                               tools=[{"id": "T1", "type": "flat", "diameter_mm": 6, "flute_length_mm": 18,
                                       "stickout_mm": 25},
                                      {"id": "T4", "type": "drill", "diameter_mm": 5}],
                               setups=[{"id": "top", "operations": [
                                   {"op": "face", "tool": "T1"},
                                   {"op": "drill", "tool": "T4", "points": [[0, 0]], "depth_mm": 3}]}]))
        got = assumed(parsed)
        self.assertEqual(2, got["tools.T1.flutes"])
        self.assertEqual("carbide", got["tools.T4.material"])
        self.assertNotIn("tools.T4.flutes", got)                       # a drill's feed is per revolution
        (why,) = [entry["why"] for entry in parsed.assumed if entry["key"] == "tools.T4.material"]
        self.assertIn("\"material\": \"hss\"", why)

    def test_used_milling_tools_list_the_lengths_they_leave_to_the_catalogue(self):
        parsed = parse_job(job({"kind": "mill", "post": "grbl", "max_rpm": 24000, "rapid_mm_min": 5000,
                                "tool_change_s": 10}, tools=[{"id": "T1", "type": "flat", "diameter_mm": 2},
                                                              {"id": "T2", "type": "flat", "diameter_mm": 8}]))
        self.assertEqual({"tools.T1.flute_length_mm": 6.0, "tools.T1.stickout_mm": 11.0,
                          "tools.T1.shank_diameter_mm": 3.0, "tools.T1.flutes": 2, "machine.spindle_spinup_s": 3.0},
                         assumed(parsed))

    def test_the_result_says_each_assumption_on_its_own_line(self):
        result = CamPlanResult(ok=True, document=Path("part.step"), glb=None, posts=(),
                               verdict={"status": "ready", "headline": "Ready to cut", "errors": 0, "warnings": 0},
                               summary={}, assumed=({"key": "machine.post", "value": "fanuc", "why": "no model"},
                                                    {"key": "machine.travel_mm", "value": [300.0, 200.0, 80.5],
                                                     "why": "w"}, {"key": "machine.rigid_tap", "value": False,
                                                                   "why": "not known"}))
        lines = result.human_lines()
        self.assertIn("assumed: machine.post fanuc (no model)", lines)
        self.assertIn("assumed: machine.travel_mm [300, 200, 80.5] (w)", lines)
        self.assertIn("assumed: machine.rigid_tap false (not known)", lines)


class AssumedInAPlan(unittest.TestCase):
    """The block's lower pocket cut through its upper step: walls 9 mm over the floor the tool works on."""

    @classmethod
    def setUpClass(cls):
        from cadgen import cam

        cls.directory = class_directory(cls)
        cls.step = block_step(cls.directory)
        cls.lower = floor_ref(cam.features(cls.step), BLOCK["lower"]["floor_z"])

    def plan(self, name, tool, machine=None):
        from cadgen import cam

        with quiet():
            return cam.plan(self.step, job=mill_job([{"op": "pocket", "tool": "T1", "faces": [self.lower]}],
                                                    tools=[{"id": "T1", "type": "flat", "diameter_mm": 2, **tool}],
                                                    machine=machine), out_dir=self.directory / name)

    def test_a_cut_past_an_assumed_length_is_not_judged_and_a_stated_one_is(self):
        guessed = self.plan("guessed", {})
        (reach,) = [f for f in guessed.findings if f["check"] == "reach"]
        self.assertEqual(("warning", "not_judged"), (reach["severity"], reach["type"]))
        # 9 mm deep: past the 2 mm flat's catalogue flutes (6), short of its stickout (6 + 5).
        self.assertIn("past T1's assumed flutes of 6 mm (the job gives no flute_length_mm)", reach["summary"])
        self.assertTrue(all(f["type"] == "not_judged" for f in guessed.findings
                            if f["check"] in ("reach", "holder_collision")))
        stated = self.plan("stated", {"flute_length_mm": 6, "stickout_mm": 8, "shank_diameter_mm": 2})
        (reach,) = [f for f in stated.findings if f["check"] == "reach"]
        self.assertEqual(("error", "reach_holder"), (reach["severity"], reach["type"]))
        # A stated flute length still judges the cut when only the stickout is a guess.
        flutes = self.plan("flutes", {"flute_length_mm": 3, "shank_diameter_mm": 2})
        (reach,) = [f for f in flutes.findings if f["check"] == "reach"]
        self.assertEqual(("error", "reach_flutes"), (reach["severity"], reach["type"]))

    def test_the_glb_and_the_header_carry_what_was_assumed(self):
        from tests.python.support.cam_fixtures import read_glb

        result = self.plan("generic", {"flute_length_mm": 12, "stickout_mm": 20, "shank_diameter_mm": 2},
                           machine={"kind": "mill"})
        self.assertEqual("fanuc", next(e["value"] for e in result.assumed if e["key"] == "machine.post"))
        document, _ = read_glb(result.glb)
        cam = document["scenes"][document.get("scene", 0)]["extras"]["cam"]
        self.assertEqual([dict(entry) for entry in result.assumed], cam["assumed"])
        text = Path(result.posts[0]["file"]).read_text(encoding="utf-8")
        self.assertIn("ASSUMED, NOT STATED: POST FANUC, MAX_RPM 8000.", text.upper())

    def test_a_dial_spindle_tells_the_operator_how_to_set_its_speed_in_the_header(self):
        result = self.plan("dial", {"flute_length_mm": 12, "stickout_mm": 20, "shank_diameter_mm": 2, "flutes": 2},
                           machine={"model": "shapeoko-5-pro"})
        text = " ".join(Path(post["file"]).read_text(encoding="utf-8") for post in result.posts).upper()
        text = text.replace(")\n(", " ")                                  # header comments wrap
        self.assertIn("SPINDLE CARBIDE COMPACT ROUTER: ITS SPEED IS SET BY HAND ON ITS DIAL", text)
        self.assertIn("DIAL 1 IS ABOUT 11,000 RPM", text)


if __name__ == "__main__":
    unittest.main()
