"""``GET /__cad/tube-skins``: what the route refuses before it binds anything.

The answer itself -- a built document's skins, from the store the second time --
runs through a real build in ``test_glb_animation.ARealDocumentPlaysItsClip``.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.viewer.tube_skins import tube_skins_response  # noqa: E402


class TheRouteRefuses(unittest.TestCase):
    def test_a_ref_that_is_not_an_absolute_step_or_a_tessellation_that_is_not_one(self):
        for ref, message in (("", r"needs \?file="), ("/models/plate.dxf", "plate.dxf is not one")):
            with self.assertRaisesRegex(ValueError, message):
                tube_skins_response(ref)
        with self.assertRaisesRegex(ValueError, "chord must be a number"):
            tube_skins_response("/models/arm.step", chord="fine")

    def test_a_missing_or_unbuilt_document_has_no_skins(self):
        with tempfile.TemporaryDirectory(prefix="tube-skins-route-") as folder:
            self.assertEqual(404, tube_skins_response(str(Path(folder) / "missing.step"))[0])
            unbuilt = Path(folder) / "unbuilt.step"
            unbuilt.write_text("ISO-10303-21;\n", encoding="utf-8")
            status, body = tube_skins_response(str(unbuilt))
            self.assertEqual((404, {"error": "unbuilt.step is not built"}), (status, body))


if __name__ == "__main__":
    unittest.main()
