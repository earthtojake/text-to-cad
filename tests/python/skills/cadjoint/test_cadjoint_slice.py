#!/usr/bin/env python3

"""Field-slice tests for the cadjoint skill.

The slice reports the field it drew, so its numbers can be checked against
the construction: the space-frame node's wall is 2 mm, so the deepest point
inside any slice through it is 1 mm from the surface; a slice that misses
the part never crosses the surface.
"""

from __future__ import annotations

import io
import json
import struct
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("skills/cadjoint/scripts")

import cadjoint_slice  # noqa: E402

EXAMPLES = Path(cadjoint_slice.__file__).resolve().parents[1] / "references" / "examples"


def _run(*argv: str) -> tuple[int, dict]:
    captured = io.StringIO()
    with redirect_stdout(captured):
        code = cadjoint_slice.main(list(argv))
    return code, json.loads(captured.getvalue())


class SliceTest(unittest.TestCase):
    def test_the_node_wall_reads_as_one_millimetre_deep(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "node.png"
            code, report = _run(str(EXAMPLES / "space_frame_node.py"), str(out),
                                "--axis", "y", "--at", "0", "--pixels", "400")
            self.assertEqual(code, 0, report)
            png = out.read_bytes()
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        width, height = struct.unpack(">II", png[16:24])
        self.assertEqual(max(width, height), 400)
        self.assertTrue(report["crosses_surface"])
        self.assertAlmostEqual(report["field_range"][0], -1.0, delta=0.02)
        self.assertEqual((report["across"], report["up"]), ("x", "z"))

    def test_a_slice_beside_the_part_never_crosses_its_surface(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            code, report = _run(str(EXAMPLES / "clevis_bracket.py"), str(Path(td) / "air.png"),
                                "--axis", "z", "--at", "80", "--pixels", "128")
        self.assertEqual(code, 0, report)
        self.assertFalse(report["crosses_surface"])
        self.assertGreater(report["field_range"][0], 0.0)

    def test_a_flat_field_on_a_contour_value_is_not_filled(self) -> None:
        """A slice along a wall's mid-plane can read one value everywhere."""
        import numpy as np

        flat = np.full((40, 40), -3.0)
        rgb = cadjoint_slice.colour(flat, pixel=0.1, step=1.0)
        self.assertEqual(len(np.unique(rgb.reshape(-1, 3), axis=0)), 1)

    def test_bad_bounds_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            code, report = _run(str(EXAMPLES / "clevis_bracket.py"), str(Path(td) / "x.png"),
                                "--bounds", "10", "0", "0", "10")
        self.assertEqual(code, 1)
        self.assertIn("U0 < U1", report["error"])


if __name__ == "__main__":
    unittest.main()
