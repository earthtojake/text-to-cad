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

REPO_ROOT = Path(__file__).resolve().parents[4]
PLANETARY = REPO_ROOT / "models/assemblies/src/planetary_gear_assembly/planetary_gear_assembly.py"


class OracleSmokeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._store = tempfile.TemporaryDirectory()
        self.env = {"CADGEN_CACHE_DIR": self._store.name}

    def tearDown(self) -> None:
        self._store.cleanup()

    def _fingerprint(self):
        # Resolve against the CHILD's store: builds ran with the per-test
        # CADGEN_CACHE_DIR, and the store paths read env at call time.
        import os
        import unittest.mock

        with unittest.mock.patch.dict(os.environ, self.env):
            return fingerprint(PLANETARY)

    def test_cache_state_independence_cold_vs_warm(self) -> None:
        cold = build_entry(PLANETARY, env=self.env, force=True)
        self.assertEqual(cold.returncode, 0, cold.stderr[-2000:])
        fp_cold = self._fingerprint()
        warm = build_entry(PLANETARY, env=self.env, force=True)
        self.assertEqual(warm.returncode, 0, warm.stderr[-2000:])
        fp_warm = self._fingerprint()
        self.assertEqual(diff_fingerprints(fp_cold, fp_warm), [])

    def test_diff_reports_differences(self) -> None:
        build = build_entry(PLANETARY, env=self.env)
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
