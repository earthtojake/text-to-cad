"""W0 smoke tests: the oracle itself, and the base cache-state-independence
assertion it exists to enforce (design/production-architecture.md).

Heavier fixtures (moonwatch family) run through the same helpers as gate
measurements, not as unit tests — a cold moonwatch build is minutes.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from tests.python.support.oracle import (
    build_entry,
    diff_fingerprints,
    fingerprint,
)
from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

# The oracle's fixture is a two-level assembly the test writes itself: a pin and a
# stage that places it twice beside a base. Small on purpose -- the contract is
# cache-state independence of the fingerprint, not modelling.
PIN_SOURCE = """\
from cadgen import step
from cadgen import build123d as bd


@step
def pin():
    return bd.Cylinder(radius=2.0, height=12.0)


if __name__ == "__main__":
    pin()
"""

STAGE_SOURCE = """\
from cadgen import step
from cadgen import build123d as bd

from pin import pin


@step
def stage():
    base = bd.Box(40.0, 20.0, 4.0)
    base.label = "base"
    p = pin()
    left = p.moved(bd.Location((-10.0, 0.0, 2.0)))
    left.label = "pin_left"
    right = p.moved(bd.Location((10.0, 0.0, 2.0)))
    right.label = "pin_right"
    return bd.Compound(children=[base, left, right], label="stage")


if __name__ == "__main__":
    stage()
"""


class OracleSmokeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._store = tempfile.TemporaryDirectory()
        self._project = tempfile.TemporaryDirectory(prefix="oracle-fixture-")
        src = Path(self._project.name)
        (src / "pin.py").write_text(PIN_SOURCE, encoding="utf-8")
        (src / "stage.py").write_text(STAGE_SOURCE, encoding="utf-8")
        self.stage = src / "stage.py"
        self.env = {"CADGEN_CACHE_DIR": self._store.name}

    def tearDown(self) -> None:
        self._project.cleanup()
        self._store.cleanup()

    def _fingerprint(self):
        # Resolve against the CHILD's store: builds ran with the per-test
        # CADGEN_CACHE_DIR, and the store paths read env at call time.
        import os
        import unittest.mock

        with unittest.mock.patch.dict(os.environ, self.env):
            return fingerprint(self.stage)

    def test_cache_state_independence_cold_vs_warm(self) -> None:
        cold = build_entry(self.stage, env=self.env, force=True)
        self.assertEqual(cold.returncode, 0, cold.stderr[-2000:])
        fp_cold = self._fingerprint()
        warm = build_entry(self.stage, env=self.env, force=True)
        self.assertEqual(warm.returncode, 0, warm.stderr[-2000:])
        fp_warm = self._fingerprint()
        self.assertEqual(diff_fingerprints(fp_cold, fp_warm), [])

    def test_diff_reports_differences(self) -> None:
        build = build_entry(self.stage, env=self.env)
        self.assertEqual(build.returncode, 0, build.stderr[-2000:])
        fp = self._fingerprint()
        mutated = {
            **fp,
            "cids": fp["cids"][:-1],
            "bbox": {"min": [0, 0, 0], "max": [1, 1, 1]},
        }
        problems = diff_fingerprints(fp, mutated)
        self.assertTrue(any("cids differ" in p for p in problems))
        self.assertTrue(any("bbox" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
