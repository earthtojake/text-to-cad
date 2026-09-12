"""The snapshot job's ``render`` block is a closed schema with real limits.

Two failure modes this pins, both of which used to be silent or opaque:

* an unread render key (`render.tesselation`, one l) rendered at default
  tessellation, exit 0, no hint — a full-price image of the wrong thing;
* an absurd tolerance was accepted here and killed the browser later, so the
  caller saw `Connection closed while reading from the driver` and no cause.

The page validates the same field (packages/cadgen-js/src/common/source.js,
which also serves the viewer); this side refuses the job before a browser is
launched, so the floors have to agree — the parity test below reads the JS.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path, repo_path

add_repo_path("packages/cadgen/src")

from cadgen.snapshot_core import (  # noqa: E402
    MIN_RENDER_TESSELLATION,
    SUPPORTED_RENDER_KEYS,
    SnapshotError,
    normalize_common_job,
    validate_render_tessellation,
)


def normalize(render: dict[str, object]) -> dict[str, object]:
    return normalize_common_job(
        {"input": "part.step", "render": render, "outputs": []},
        mode="list",
        resolved_cwd=Path("."),
        timestamp="20260907-000000",
    )


class RenderKeySchemaTest(unittest.TestCase):
    def test_every_supported_render_key_is_accepted(self):
        values = {
            "tessellation": {"chordTolerance": 0.001},
            "scale": "cad",
            "sceneScale": "cad",
            "sceneScaleMode": "urdf",
            "sizeProfile": "diagnostic",
            "padding": 0.12,
            "paddingPercent": 0.12,
            "viewLabels": True,
            "tightFrame": True,
            "transparent": True,
            "renderScale": 1,
        }
        # Every key the renderer reads has a legal spelling here; a key missing
        # from this table is a key nobody documented a value for.
        self.assertEqual(set(values), set(SUPPORTED_RENDER_KEYS))
        for key, value in values.items():
            normalize({key: value})

    def test_a_misspelled_render_key_is_refused_by_name(self):
        with self.assertRaises(SnapshotError) as caught:
            normalize({"tesselation": {"chordTolerance": 0.001}})
        message = str(caught.exception)
        self.assertIn("unknown key(s): tesselation", message)
        self.assertIn("tessellation", message)


class RenderTessellationLimitsTest(unittest.TestCase):
    def test_unknown_field_and_non_numbers_are_refused(self):
        for value in ({"quality": "high"}, {"chordTolerance": "0.001"}, {"chordTolerance": True}):
            with self.assertRaises(SnapshotError):
                validate_render_tessellation(value)
        with self.assertRaises(SnapshotError):
            validate_render_tessellation([0.001])

    def test_tolerances_below_the_floor_are_refused_here_not_in_the_browser(self):
        with self.assertRaises(SnapshotError) as caught:
            normalize({"tessellation": {"chordTolerance": 1e-12}})
        self.assertIn("at least 1e-05", str(caught.exception))
        with self.assertRaises(SnapshotError):
            normalize({"tessellation": {"angleTolerance": 1e-6}})
        # The floors themselves, and everything coarser, are legal requests.
        validate_render_tessellation(dict(MIN_RENDER_TESSELLATION))
        validate_render_tessellation({"chordTolerance": 0.0005, "angleTolerance": 0.10})
        validate_render_tessellation(None)

    def test_the_floors_match_the_page_that_tessellates(self):
        source = repo_path("packages/cadgen-js/src/common/source.js").read_text(encoding="utf-8")
        block = re.search(r"RENDER_TESSELLATION_FLOORS = Object\.freeze\(\{(.*?)\}\)", source, re.S)
        self.assertIsNotNone(block, "source.js no longer declares RENDER_TESSELLATION_FLOORS")
        declared = {
            key: float(value)
            for key, value in re.findall(r"(\w+):\s*([0-9.e-]+)", block.group(1))
        }
        self.assertEqual(declared, MIN_RENDER_TESSELLATION)


if __name__ == "__main__":
    unittest.main()
