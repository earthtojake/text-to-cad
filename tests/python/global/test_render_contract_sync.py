"""The render contract: what the Python producer writes and pins must stay what its
readers expect.

This repo has lost a cross-language mirror to a deleted check before (the
viewer scanner's package-path constants drifted silently once nothing compared
them). The viewer BACKEND is ``cadgen.viewer`` now and reads the store through
cadgen's own helpers, and the page takes every part key from cadgen, so there is no
second derivation of a store key or a format version left to compare.
"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class RenderContractSyncTest(unittest.TestCase):
    def test_component_blob_format_is_pinned_not_current(self) -> None:
        # Component blobs are content-addressed: their serialized bytes ARE the
        # cid. A floating BinTools_FormatVersion_CURRENT would let an OCP
        # upgrade silently re-serialize every blob and re-key every cid; the
        # write site must name an explicit version so a format bump is a
        # deliberate act, not a dependency-update side effect.
        source = (ROOT / "packages/cadgen/src/cadgen/_internal/component_package.py").read_text()
        writes = source.count("BinTools.Write_s(")
        self.assertGreaterEqual(writes, 1, "the component blob write site moved; update this test")
        self.assertNotIn(
            "BinTools_FormatVersion.BinTools_FormatVersion_CURRENT",
            source,
            "component blobs must be written with a PINNED BinTools format "
            "version (see _shape_brep_bytes), never _CURRENT",
        )


class TheViewerSuiteActuallyRuns(unittest.TestCase):
    """The wiring, not the check.

    The viewer backend suite is the executable specification of the backend, and
    for one release cycle it ran in ZERO configurations of this repo: the JS
    runner stopped covering the server, the Python runner discovered only what it
    was pointed at, and the workflow never named it. It lives under the cadgen
    package suite now, so the ordinary runner reaches it -- this pins that the
    directory the runner walks still contains it.
    """

    def test_the_viewer_suite_is_under_the_cadgen_package_tests(self) -> None:
        suite = ROOT / "tests/python/packages/cadgen/viewer"
        tests = sorted(p.name for p in suite.glob("test_*.py"))
        self.assertIn("test_launcher.py", tests)
        self.assertIn("test_module_boundaries.py", tests)
        runner = (ROOT / "scripts/test/test-python.sh").read_text(encoding="utf-8")
        self.assertIn(
            '"tests/python/packages/cadgen"',
            runner,
            "test-python.sh must run the cadgen package suite, which is where the viewer suite lives",
        )


if __name__ == "__main__":
    unittest.main()
