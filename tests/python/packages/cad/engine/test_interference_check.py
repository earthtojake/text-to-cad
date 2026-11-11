"""The interference check's measuring (``cad.build123d._interference``): every pair of a document's parts
whose boxes meet, measured exactly, as built and posed -- held to what it exists for: a plate planted through
a thin skin is found, one 0.3 mm clear of it and a pin in its bore are not, a named fit is listed apart, and a
pair that could not be measured is said, never passed."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

import numpy as np

from tests.python.support.paths import add_sources

add_sources()

from cad._internal import interference as asked
from cad.build123d import _interference
from cad.engine import build as engine_build
from cad.engine import document

ARM = """
import build123d as bd
from cad.build123d import configuration_sequence, mechanism_state
from cad.engine import xbf


@xbf("XBF/arm.xbf")
def arm():
    def part(label, shape):
        shape.label = label
        return shape

    low = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)
    base = part("base", bd.Box(60, 60, 10, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX))
                - bd.Pos(20, 20, -5) * bd.Cylinder(2, 10) - bd.Pos(-20, 20, -5) * bd.Cylinder(2, 10))
    dowel = part("dowel", bd.Pos(20, 20, -5) * bd.Cylinder(2, 10))            # in its bore: the same cylinder
    press = part("press", bd.Pos(-20, 20, -5) * bd.Cylinder(2.02, 10))        # a press fit: it shares volume
    post = part("post", bd.Cylinder(5, 40, align=low))
    bar = part("bar", bd.Pos(6, 0, 40) * bd.Box(80, 8, 8, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN)))
    stop = part("stop", bd.Pos(40, 0, 20) * bd.Box(10, 10, 20))               # the bar meets it swinging down
    skin = part("skin", bd.Pos(0, -25, 20) * bd.Box(40, 2.6, 40))
    through = part("through", bd.Pos(-10, -25, 20) * bd.Box(8, 20, 8))        # a plate planted through the skin
    beside = part("beside", bd.Pos(10, -25 - 1.3 - 0.3 - 4, 20) * bd.Box(8, 8, 8))  # one 0.3 mm clear of it
    sheet = part("sheet", bd.Pos(0, 25, 20) * bd.Rectangle(10, 10))           # no solid: nothing to share
    hinge = bd.Axis((0, 0, 44), (0, 1, 0))
    bd.RevoluteJoint("elbow", post, axis=hinge, angular_range=(0, 90))
    bd.RigidJoint("elbow", bar, bd.Plane(origin=hinge.position, z_dir=hinge.direction).location)
    post.joints["elbow"].connect_to(bar.joints["elbow"], angle=0)
    kit = bd.Compound(children=[base, dowel, press, post, bar, stop, skin, through, beside, sheet], label="arm")
    mechanism_state(kit, "down", elbow=30)
    return configuration_sequence(kit, "swing", sweep={"elbow": (0, 30)}, duration=2.0)
"""


class MeasureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from cad.engine.kernel import memo

        cls.folder = Path(tempfile.mkdtemp(prefix="engine-interference-")).resolve()
        cls.addClassCleanup(shutil.rmtree, cls.folder, ignore_errors=True)
        memo.install()
        cls.addClassCleanup(memo.clear)
        script = cls.folder / "arm.py"
        script.write_text(textwrap.dedent(ARM), encoding="utf-8")
        os.utime(script, ns=(time.time_ns(), time.time_ns()))
        report = engine_build.build(script, ["arm"], cwd=cls.folder)[0]
        assert report["ok"], report.get("error")
        loaded = document.Loaded(cls.folder / "XBF/arm.xbf")
        cls.structure, cls.shapes = loaded.structure(), [prototype.shape for prototype in loaded.prototypes]

    def measure(self, **given) -> dict:
        return _interference.measure(self.structure, self.shapes, asked.options(jobs=2, **given))

    @staticmethod
    def pairs(rows: list[dict]) -> dict[tuple[str, str], dict]:
        return {tuple(sorted((row["a"].rpartition("/")[2], row["b"].rpartition("/")[2]))): row for row in rows}

    def test_as_built_a_planted_plate_and_a_press_fit_are_found_and_a_near_miss_and_a_pin_in_its_bore_are_not(self) -> None:
        found = self.measure()
        self.assertEqual((found["name"], found["parts"], found["skipped"], found["stances"]), ("arm", 9, 1, ["as built"]))
        shared = self.pairs(found["interferences"])
        self.assertEqual(sorted(shared), [("base", "press"), ("skin", "through")])
        # A flat plate has vertices on its outline alone and a 2.6 mm skin almost no volume for a sampled point to
        # land in: the kernel's intersection is what finds 8 x 2.6 x 8 of it.
        self.assertAlmostEqual(shared[("skin", "through")]["volume"], 8 * 2.6 * 8, places=6)
        self.assertEqual(shared[("skin", "through")]["at"], ["as built"])
        self.assertGreater(shared[("base", "press")]["volume"], 1.0)
        self.assertEqual((found["fits"], found["unmeasured"]), ([], []))
        # The boxes of the near miss and of the dowel in its bore met, and each was measured to share nothing.
        self.assertGreaterEqual(found["pairs"]["measured"], 4)
        self.assertEqual(found["pairs"]["boxes_meet"], found["pairs"]["measured"])
        # Out of time before the first pair, none is counted measured: each is unmeasured, said so.
        late = _interference.measure(self.structure, self.shapes, {**asked.options(jobs=2), "seconds": 1e-9})
        self.assertEqual((late["pairs"]["measured"], len(late["unmeasured"])), (0, late["pairs"]["boxes_meet"]))
        # Such a report is partial, which the engine does not keep; one fully measured is kept.
        self.assertEqual((late["partial"], found["partial"]), (True, False))

    def test_a_named_fit_is_listed_apart_and_what_names_nothing_is_refused(self) -> None:
        found = self.measure(fits=["press,base"])
        self.assertEqual(sorted(self.pairs(found["interferences"])), [("skin", "through")])
        (fit,) = found["fits"]
        self.assertEqual((fit["fit"], sorted((fit["a"], fit["b"]))), ("press in base", ["arm/base", "arm/press"]))
        self.assertEqual(sorted(self.pairs(self.measure(fits=[("pres?", "bas*")])["fits"])), [("base", "press")])
        for given, words in (({"fits": ["lid*,base"]}, "fit: 'lid\\*' matches no part or assembly of arm"),
                             ({"fits": ["base/face 1,press"]}, "names an element of a part"),
                             ({"poses": ["up"]}, "pose: the document has no mechanism state 'up'"),
                             ({"motions": ["wave"]}, "motion: the document has no motion 'wave'")):
            with self.subTest(given=given), self.assertRaisesRegex(_interference.Refused, words):
                self.measure(**given)

    def test_a_pose_and_a_motion_s_samples_are_stances_and_a_pair_is_measured_once_for_each_way_it_stands(self) -> None:
        built = self.measure(fits=["press,base"])
        posed = self.measure(fits=["press,base"], states=True, motions="all", samples=3)
        self.assertEqual(posed["stances"], ["as built", "pose down", "motion swing at 0 s", "motion swing at 1 s",
                                            "motion swing at 2 s"])
        shared = self.pairs(posed["interferences"])
        self.assertIn(("bar", "stop"), shared)
        down = shared[("bar", "stop")]["at"]
        self.assertTrue({"pose down", "motion swing at 2 s"} <= set(down), down)
        self.assertFalse({"as built", "motion swing at 0 s"} & set(down), "the bar is clear of the stop until it swings")
        self.assertEqual(shared[("skin", "through")]["stances"], 5)
        # Five stances, and what does not move is measured once: only the bar's pairs are measured again.
        self.assertGreater(posed["pairs"]["boxes_meet"], 4 * built["pairs"]["boxes_meet"])
        self.assertLess(posed["pairs"]["measured"], posed["pairs"]["boxes_meet"] / 2)
        by_value = self.measure(fits=["press,base"], poses=[{"elbow": 30}])
        self.assertEqual(self.pairs(by_value["interferences"]).keys(), shared.keys(), "the same pose, said by value")

    def test_a_pair_that_is_not_measured_is_said_and_never_passed(self) -> None:
        orders = [{"n": 0, "a": 0, "b": 1, "placed": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0]},
                  {"n": 1, "a": 0, "b": 1, "placed": [1, 0, 0, 5, 0, 1, 0, 0, 0, 0, 1, 0]}]

        def crew(code: str, pair_seconds: float, deadline: float | None = None) -> dict:
            import subprocess

            made = _interference._Crew(self.folder, 1, pair_seconds, deadline)

            def start():
                process = subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                           text=True, encoding="utf-8")
                return process, self.reader(process)

            made._start = start
            return made.run(orders)

        # One that holds its pair past the pair's time is stopped, and the next pair has a process of its own.
        stuck = crew("import sys, time\nfor line in sys.stdin: time.sleep(600)", 0.3)
        self.assertEqual([stuck[n]["unmeasured"] for n in (0, 1)], ["not measured within 0.3 s"] * 2)
        gone = crew("import sys; sys.stdin.readline()", 30.0)
        self.assertIn("the process measuring it exited", gone[0]["unmeasured"])
        refused = crew("import sys, json\nfor line in sys.stdin:\n"
                       "    print(json.dumps({'n': json.loads(line)['n'], 'error': 'GeometryError: no'}), flush=True)", 30.0)
        self.assertEqual(refused[1]["unmeasured"], "the kernel could not intersect them: GeometryError: no")
        late = crew("import sys", 30.0, time.monotonic() - 1)
        self.assertEqual(late[0]["unmeasured"], "not reached before the check's time was up")
        # And the result says it: a finding for the pair, and a status that is no pass.
        report = {"name": "kit", "parts": 2, "skipped": 0, "stances": ["as built"], "seconds": 0.3,
                  "pairs": {"boxes_meet": 1, "measured": 1}, "interferences": [], "fits": [],
                  "unmeasured": [{"a": "kit/a", "b": "kit/b", "reason": "not measured within 0.3 s", "stances": 1,
                                  "at": ["as built"]}]}
        result = asked.finish(Path("kit"), {"measured": {"report": report}, "measured_in": "engine"}, {})
        self.assertEqual((result.status, result.ok, result.reason), ("not_checked", False, "unmeasured"))
        (finding,) = result.findings
        self.assertEqual((finding.severity, finding.code, finding.location, finding.refs),
                         ("warning", "unmeasured", "kit/a", ["kit/a", "kit/b"]))
        self.assertIn("not measured against kit/b: not measured within 0.3 s (as built)", finding.message)
        self.assertTrue(result.human_lines()[-1].startswith("NOT CHECKED kit: no pair measured shares volume, but 1 "
                                                            "could not be measured"))
        # One that shares volume fails it, whatever else went unmeasured; nothing found and all measured is ok.
        shared = {"a": "kit/a", "b": "kit/c", "volume": 12.5, "stances": 1, "at": ["as built"]}
        failed = asked.finish(Path("kit"), {"measured": {"report": {**report, "interferences": [shared]}}}, {})
        self.assertEqual((failed.status, [finding.code for finding in failed.findings]),
                         ("failed", ["interference", "unmeasured"]))
        self.assertEqual((failed.findings[0].value, failed.findings[0].unit), (12.5, "mm3"))
        clear = asked.finish(Path("kit"), {"measured": {"report": {**report, "unmeasured": [], "fits": [
            {**shared, "fit": "a in c"}]}}}, {})
        self.assertEqual((clear.status, clear.ok, [finding.severity for finding in clear.findings]), ("ok", True, ["info"]))
        self.assertTrue(clear.summary.startswith("OK kit: no two parts share volume"))
        with self.assertRaisesRegex(ValueError, "fit: 'lid\\*' matches no part"):
            asked.finish(Path("kit"), {"refused": "fit: 'lid*' matches no part or assembly of kit"}, {})

    @staticmethod
    def reader(process):
        import queue
        import threading

        lines: queue.SimpleQueue = queue.SimpleQueue()

        def read() -> None:
            for line in process.stdout:
                lines.put(line)
            lines.put(None)

        threading.Thread(target=read, daemon=True).start()
        return lines


class BoxesTest(unittest.TestCase):
    def test_two_boxes_are_tested_as_they_stand_not_as_the_boxes_of_their_boxes(self) -> None:
        def turned(degrees: float) -> np.ndarray:
            c, s = np.cos(np.radians(degrees)), np.sin(np.radians(degrees))
            return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])

        long, small = np.array([100.0, 2.0, 2.0]), np.array([5.0, 5.0, 5.0])
        centres = np.array([[0.0, 0.0, 0.0], [60.0, -60.0, 0.0], [60.0, 60.0, 0.0], [300.0, 0.0, 0.0]])
        axes = np.array([turned(45), np.eye(3), np.eye(3), np.eye(3)])
        halves = np.array([long, small, small, small])
        # A long bar at 45 degrees: its own box's box holds both corners, the bar itself only the one it points at.
        self.assertEqual(_interference._meeting(centres, axes, halves, np.array([True] * 4)), [(0, 2)])
        self.assertEqual(_interference._meeting(centres, axes, halves, np.array([True, True, False, True])), [])


class OptionsTest(unittest.TestCase):
    def test_what_is_asked_is_plain_data_and_what_is_no_option_is_refused_by_name(self) -> None:
        found = asked.options(poses=['{"elbow": 30}', "down"], motions="all", fits=["pin,base", ("a*", "b")], jobs=3)
        self.assertEqual(found, {"poses": [{"elbow": 30}, "down"], "states": False, "motions": "all",
                                 "fits": [["pin", "base"], ["a*", "b"]], "samples": 12, "pair_seconds": 60.0,
                                 "seconds": 1200.0, "min_volume": 0.0, "jobs": 3})
        for given, words in (({"fits": ["pin"]}, "a fit is the two parts meant to share volume, as A,B"),
                             ({"samples": 1}, "samples is a number of 2 or more"),
                             ({"jobs": 0}, "jobs is a number of 1 or more"),
                             ({"poses": ["{elbow}"]}, "is not a JSON object"),
                             ({"motions": [3]}, "motions are configuration sequences' names"),
                             ({"min_volume": -1}, "min_volume is a number of 0 or more")):
            with self.subTest(given=given), self.assertRaisesRegex(ValueError, words):
                asked.options(**given)


if __name__ == "__main__":
    unittest.main()
