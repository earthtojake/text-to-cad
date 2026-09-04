"""The cross-language render contract: constants that exist in BOTH the Python
producer and the JS consumer must be bumped together.

This repo has lost a cross-language mirror to a deleted check before (the
viewer scanner's package-path constants drifted silently once nothing compared
them) — these greps are the structural version of that comparison: a one-sided
bump fails CI before it can ship a viewer that cannot read what cadgen writes.

The CLIENT half of that boundary is JS — ``packages/cadgen-js`` parses ``.surf``
in the browser — so the SURF_VERSION pin stays here. The viewer BACKEND is
``cadgen.viewer`` now and reads the store through cadgen's own helpers, so there
is no second derivation of a store key left to compare; what remains for it here
is the two package-boundary behaviours that a constant pin cannot see (the
progress record a live build publishes, and the provenance record the classifier
reads), asked of the real reader against a real producer.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]


def _extract(pattern: str, path: Path, flags: int = re.MULTILINE) -> str:
    match = re.search(pattern, path.read_text(), flags)
    assert match, f"{pattern!r} not found in {path}"
    return match.group(1)


class RenderContractSyncTest(unittest.TestCase):
    def test_surf_version_matches_between_python_and_js(self) -> None:
        python_version = _extract(
            r"^SURF_VERSION = (\d+)$",
            ROOT / "packages/cadgen/src/cadgen/_internal/surface_extract.py",
        )
        js_version = _extract(
            r"^export const SURF_VERSION = (\d+);$",
            ROOT / "packages/cadgen-js/src/lib/surf/container.js",
        )
        self.assertEqual(
            python_version,
            js_version,
            "SURF_VERSION diverged between the Python extractor and the JS "
            "surf parser — bump both together (and CACHE_SCHEMA_VERSION with "
            "them; a .surf the client cannot parse renders nothing).",
        )

    def test_sidecar_schema_matches_the_js_kinematics_loader(self) -> None:
        # What is genuinely cross-language is the CLIENT: the kinematics loader
        # runs in the browser and REFUSES any other schema, so a one-sided bump
        # makes every model's kinematics fail to load.
        sidecar_module = ROOT / "packages/cadgen/src/cadgen/_internal/source_sidecar.py"
        self.assertEqual(
            _extract(r"^SOURCE_SIDECAR_SCHEMA_VERSION = (\d+)$", sidecar_module),
            _extract(
                r"^export const SOURCE_SIDECAR_SCHEMA_VERSION = (\d+);",
                ROOT / "packages/cadgen-js/src/common/kinematicsModule.js",
            ),
            "SOURCE_SIDECAR_SCHEMA_VERSION diverged between cadgen and the JS "
            "kinematics loader — the loader REFUSES any other schema, so a "
            "one-sided bump makes every model's kinematics fail to load",
        )

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
