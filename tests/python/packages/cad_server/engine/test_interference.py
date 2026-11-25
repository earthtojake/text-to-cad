"""``cad <type> interference``: the interference check asked of a real engine -- measured in a checks process,
answered again from the result the engine keeps, its verdict the command's status (0 clear, 1 parts share
volume), an option the document does not answer refused by name, and the same from Python by the model's handle."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.python.support import engine_daemon
from tests.python.support.paths import add_sources

SRC = add_sources()

KIT = """
import build123d as bd
from cad import model
from cad.build123d import mechanism_state


@model
def kit():
    def part(label, shape):
        shape.label = label
        return shape

    base = part("base", bd.Box(60, 60, 10, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX)))
    press = part("press", bd.Pos(20, 20, -5) * bd.Cylinder(2, 12))            # through the base: a named fit
    post = part("post", bd.Cylinder(5, 40, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)))
    bar = part("bar", bd.Pos(6, 0, 40) * bd.Box(80, 8, 8, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN)))
    stop = part("stop", bd.Pos(40, 0, 20) * bd.Box(10, 10, 20))               # the bar meets it swinging down
    hinge = bd.Axis((0, 0, 44), (0, 1, 0))
    bd.RevoluteJoint("elbow", post, axis=hinge, angular_range=(0, 90))
    bd.RigidJoint("elbow", bar, bd.Plane(origin=hinge.position, z_dir=hinge.direction).location)
    post.joints["elbow"].connect_to(bar.joints["elbow"], angle=0)
    return mechanism_state(bd.Compound(children=[base, press, post, bar, stop], label="kit"), "down", elbow=30)


if __name__ == "__main__":
    kit()
"""


class CommandTest(unittest.TestCase):
    """Through a real daemon, in an engine, a state and a cache folder of the test's own."""

    def setUp(self) -> None:
        self.folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="engine-interference-")))
        self.addCleanup(shutil.rmtree, self.folder, True)
        engine = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        self.addCleanup(shutil.rmtree, engine, True)
        self.env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC), "CAD_ENGINE_DIR": str(engine),
                                          "CAD_STATE_DIR": str(self.folder / "state"),
                                          "CAD_CACHE_DIR": str(self.folder / "cache"),
                                          "CAD_ENGINE_MESH": "inline"}, self.addCleanup)
        self.addCleanup(self.run_, "-m", "cad_server.engine", "stop")

    def run_(self, *args: str):
        return engine_daemon.run([sys.executable, *args], cwd=self.folder, env=self.env)

    def check(self, *args: str):
        return self.run_("-m", "cad_server.cli", "model", "interference", self.ident, *args)

    def test_the_command_s_status_is_its_verdict_and_the_same_check_is_answered_from_what_was_kept(self) -> None:
        (self.folder / "kit.py").write_text(textwrap.dedent(KIT), encoding="utf-8")
        built = self.run_("kit.py")
        self.assertEqual(built.returncode, 0, built.stderr)
        self.ident = next(line.split()[1] for line in built.stdout.splitlines() if line.strip().startswith("id:"))

        # As built the press fit shares volume with the base, and nothing says it is meant to: status 1.
        found = self.check()
        self.assertEqual(found.returncode, 1, found.stderr)
        lines = found.stdout.splitlines()
        self.assertRegex(lines[0], r"^error: overlapping_parts at kit/base: shares [\d.]+ mm\^3 with kit/press \(as built\)")
        self.assertRegex(lines[-1], r"^FAILED kit: 1 pair of parts share volume \(5 parts at 1 pose, the boxes of \d+ "
                                    r"pairs? met: \d+ measured, in [\d.]+ s\)$")

        # Named a fit, it is listed apart and the kit is clear: status 0. Asked again, nothing is measured.
        clear = self.check("--fit", "press", "base", "--json")
        self.assertEqual(clear.returncode, 0, clear.stderr)
        result = json.loads(clear.stdout)
        self.assertEqual((result["status"], result["ok"], result["reason"]), ("ok", True, None))
        self.assertEqual([(row["severity"], row["code"], row["refs"]) for row in result["findings"]],
                         [("info", "fit", ["kit/base", "kit/press"])])
        measured = result["measurements"]
        self.assertEqual((measured["overlaps"], measured["unmeasured"], measured["measured_in"]), ([], [], "engine"))
        self.assertEqual([(row["between"], row["fit"], row["poses"]) for row in measured["fits"]],
                         [(["kit/base", "kit/press"], ["press", "base"], ["as built"])])
        self.assertEqual(measured["resolved"], {"poses": [], "fits": [["press", "base"]], "min_volume": 0.001})
        self.assertNotIn("reused", measured)
        again = json.loads(self.check("--fit", "press", "base", "--json").stdout)
        self.assertTrue(again["measurements"]["reused"])
        self.assertEqual(again["measurements"]["fits"], measured["fits"])

        # At its mechanism state the bar is in the stop: found there, and said where.
        posed = self.check("--fit", "press", "base", "--pose", "down", "--pose", '{"elbow": 30}', "--json")
        self.assertEqual(posed.returncode, 1, posed.stderr)
        result = json.loads(posed.stdout)
        self.assertEqual((result["status"], result["measurements"]["poses"]),
                         ("failed", ["as built", "down", '{"elbow":30}']))
        self.assertIn((["kit/bar", "kit/stop"], ["down", '{"elbow":30}']),
                      [(row["between"], row["poses"]) for row in result["measurements"]["overlaps"]])
        self.assertIn(["kit/bar", "kit/stop"],
                      [row["refs"] for row in result["findings"] if row["code"] == "overlapping_parts"])

        # What the document does not answer is refused by name, before anything is measured: status 2.
        for flags, words in ((("--pose", "up"), "pose: the document has no mechanism state 'up'"),
                             (("--pose", "swing@1"), "pose: the document has no configuration sequence 'swing'"),
                             (("--fit", "lid*", "base"), "fit: 'lid*' matches no part or assembly of kit"),
                             (("--fit", "press"), "argument --fit: expected 2 arguments")):
            refused = self.check(*flags)
            self.assertEqual(refused.returncode, 2, refused.stdout)
            self.assertIn(words, refused.stderr)

        # A script asks the same of the handle its model call returns.
        (self.folder / "ask.py").write_text(
            "import json\nfrom cad import model\nfrom kit import kit\n"
            "found = model.interference(kit(), fits=[('press', 'base')], poses=['down'])\n"
            "print(json.dumps([found.status, [finding.refs for finding in found.findings if finding.code == "
            "'overlapping_parts']]))\n", encoding="utf-8")
        asked = self.run_("ask.py")
        self.assertEqual(asked.returncode, 0, asked.stderr)
        status, pairs = json.loads(asked.stdout.splitlines()[-1])
        self.assertEqual(status, "failed")
        self.assertIn(["kit/bar", "kit/stop"], pairs)


def setUpModule() -> None:
    engine_daemon.isolate(unittest.addModuleCleanup)


if __name__ == "__main__":
    unittest.main()
