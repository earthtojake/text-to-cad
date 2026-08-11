"""``cadgen.coordination`` must stay importable by the CAD Viewer's long-lived server.

This replaces the real job of tests/python/global/test_viewer_cadgen_mirror.py. That test
pinned two hand-written copies of the coordination protocol against each other by comparing
path STRINGS; the property it was actually protecting is this one -- the viewer's server
process must never drag OCP/build123d/ezdxf into itself. Testing the invariant directly is
strictly stronger than testing a proxy for it, and it is what makes deleting the copy safe.

Runs in a FRESH interpreter: asserting on sys.modules inside the existing one would pass
trivially or fail spuriously depending on what the rest of the suite imported first.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

_CADGEN_SRC = str(Path(__file__).resolve().parents[4] / "packages" / "cadgen" / "src")

_PROBE = """
import json, sys, time
sys.path.insert(0, {src!r})
start = time.perf_counter()
import cadgen.coordination  # noqa: F401
elapsed_ms = (time.perf_counter() - start) * 1000.0
print(json.dumps({{
    "elapsed_ms": elapsed_ms,
    "heavy": sorted(m for m in ("OCP", "build123d", "ezdxf", "numpy") if m in sys.modules),
    "has_api": all(
        hasattr(cadgen.coordination, name)
        for name in ("artifact_build", "generator_busy", "snapshot", "Contended")
    ),
}}))
"""

# Generous: the assertion is "no CAD runtime got pulled in", and a cold interpreter on a
# loaded CI box is slow. A regression that imports OCP costs seconds, not milliseconds.
_IMPORT_BUDGET_MS = 400.0


class CoordinationIsStdlibOnlyTest(unittest.TestCase):
    def _probe(self):
        proc = subprocess.run(
            [sys.executable, "-c", _PROBE.format(src=_CADGEN_SRC)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(0, proc.returncode, f"importing cadgen.coordination failed:\n{proc.stderr}")
        return json.loads(proc.stdout.strip().splitlines()[-1])

    def test_import_pulls_in_no_cad_runtime(self):
        result = self._probe()
        self.assertEqual(
            [],
            result["heavy"],
            "cadgen.coordination must not import a CAD runtime -- the viewer's server "
            "process imports it, and OCP in that process is exactly what the old "
            "hand-mirrored copy existed to avoid",
        )

    def test_import_is_cheap(self):
        result = self._probe()
        self.assertLess(result["elapsed_ms"], _IMPORT_BUDGET_MS)

    def test_public_api_is_present(self):
        self.assertTrue(self._probe()["has_api"])


if __name__ == "__main__":
    unittest.main()
