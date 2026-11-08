"""The CadQuery memo on the real CadQuery (``cad.cadquery._memo``): hits, misses and replay equality.

In the environment of ``cad[cadquery]`` (``tests/python/support/cadquery_env.py``), with no daemon: a part
built twice in one process replays -- every kernel call a hit, none a miss -- and returns the very geometry
the first run made (the same ``TShape``; equal volume, bounds and face count); an edited parameter re-runs
what reads it and keeps the rest; a cold process makes the same geometry as a replay. Runs in the
``cadquery`` job; anywhere the environment cannot be made it says why it skips.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.python.support import cadquery_env
from tests.python.support.paths import add_sources

SRC = add_sources()

PROGRAM = """
import json
import sys

import cadquery as cq
from cad.cadquery import _memo


def bracket(width=40, bore=8):
    body = cq.Workplane("XY").box(width, 20, 6).faces(">Z").workplane().hole(bore).edges("|Z").fillet(2)
    peg = cq.Workplane("XY").cylinder(10, 2).translate((10, 0, 8))
    return body.union(peg)


def facts(shape):
    box = shape.BoundingBox()
    return [round(shape.Volume(), 6), [round(v, 6) for v in (box.xmin, box.ymin, box.zmin, box.xmax, box.ymax, box.zmax)],
            len(shape.Faces())]


patched = _memo.install()
runs = {}
with _memo.run() as cold:
    first = bracket().val()
with _memo.run() as warm:
    second = bracket().val()
with _memo.run() as edited:
    third = bracket(width=50).val()
with _memo.run() as again:
    fourth = bracket(width=50).val()
print("RESULT " + json.dumps({
    "patched": patched,
    "cold": cold.tally, "warm": warm.tally, "edited": edited.tally, "again": again.tally,
    "unkeyable": cold.unkeyable,
    "first": facts(first), "second": facts(second), "third": facts(third),
    "same_tshape": second.wrapped.TShape() == first.wrapped.TShape(),
    "stats": _memo.stats()}))
"""

COLD = """
import json
import cadquery as cq

body = cq.Workplane("XY").box(40, 20, 6).faces(">Z").workplane().hole(8).edges("|Z").fillet(2)
peg = cq.Workplane("XY").cylinder(10, 2).translate((10, 0, 8))
shape = body.union(peg).val()
box = shape.BoundingBox()
print("RESULT " + json.dumps([round(shape.Volume(), 6), [round(v, 6) for v in (box.xmin, box.ymin, box.zmin, box.xmax, box.ymax, box.zmax)], len(shape.Faces())]))
"""


class Memo(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.folder = Path(tempfile.mkdtemp(prefix="cadquery-memo-"))
        cls.addClassCleanup(shutil.rmtree, cls.folder, True)
        (cls.folder / "program.py").write_text(textwrap.dedent(PROGRAM), encoding="utf-8")
        (cls.folder / "cold.py").write_text(textwrap.dedent(COLD), encoding="utf-8")

    def run_(self, name: str) -> dict:
        done = cadquery_env.run(self, str(self.folder / name), env={**os.environ, "PYTHONPATH": str(SRC)})
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout.rsplit("RESULT ", 1)[1])

    def test_a_part_built_twice_replays_and_an_edit_reruns_what_reads_it(self) -> None:
        found = self.run_("program.py")
        self.assertGreater(found["patched"], 50, "CadQuery's makers, booleans, fillets, copies and placements")
        self.assertEqual(found["unkeyable"], [], "every call of the chain is keyed")
        self.assertEqual((found["cold"]["hits"], found["cold"]["errors"]), (0, 0))
        self.assertGreater(found["cold"]["misses"], 10)
        self.assertEqual(found["warm"]["misses"], 0, found["warm"])
        self.assertEqual(found["warm"]["hits"], found["cold"]["misses"], "every call of the cold run hits")
        self.assertTrue(found["same_tshape"], "a replay hands back the first run's kernel objects")
        self.assertEqual(found["first"], found["second"], "equal volume, bounds and face count")
        # The edit: the box and everything that reads it ran; the peg's chain did not.
        self.assertGreater(found["edited"]["misses"], 0)
        self.assertGreater(found["edited"]["hits"], 0)
        self.assertLess(found["edited"]["hits"], found["cold"]["misses"])
        self.assertEqual(found["third"][1][0], -25.0, "the wider plate")
        self.assertEqual((found["again"]["misses"], found["again"]["hits"]), (0, found["cold"]["misses"]))

    def test_a_replay_equals_a_cold_process_s_geometry(self) -> None:
        memoized = self.run_("program.py")
        cold = self.run_("cold.py")
        self.assertEqual(memoized["second"], cold, "a replay returns what a process with no memo makes")


if __name__ == "__main__":
    unittest.main()
