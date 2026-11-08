"""``cad.mjcf.validate``: the bundled read's findings, and MuJoCo's compile where the mujoco integration is
installed (``--compile auto|required|never``), each model a tiny file in a fresh temporary folder."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_sources

add_sources()

import cad.mjcf  # noqa: E402
from cad.mujoco import _compile  # noqa: E402

GOOD = ('<mujoco model="arm"><worldbody><body name="a"><joint name="j" range="-90 90"/>'
        '<geom type="box" size=".1 .1 .1"/></body></worldbody></mujoco>')
# Read by the viewer as a hinged sphere; refused by MuJoCo: a moving body with no mass.
MASSLESS = ('<mujoco model="z"><worldbody><body name="a"><joint name="j" range="-90 90"/>'
            '<geom type="sphere" size="0.1" mass="0"/></body></worldbody></mujoco>')
BROKEN = '<mujoco model="b"><worldbody><body name="a"><geom type="mesh" mesh="nope"/></body></worldbody></mujoco>'


class Validate(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def write(self, text: str, name: str = "robot.xml") -> Path:
        path = self.folder / name
        path.write_text(text, encoding="utf-8")
        return path

    def codes(self, result) -> dict[str, str]:
        return {finding.code: finding.severity for finding in result.findings}

    def test_a_good_model_is_ok_and_summarised(self) -> None:
        result = cad.mjcf.validate(self.write(GOOD), compile="never")
        self.assertTrue(result.ok)
        self.assertTrue(result.summary.startswith("OK "), result.summary)
        self.assertTrue(result.summary.endswith("robot.xml: MJCF 'arm', 1 bodies, 1 controls, 1 visuals, 0 mesh files, "
                                                "0 keyframes"), result.summary)
        self.assertEqual({}, self.codes(result))

    def test_a_broken_model_is_not_ok(self) -> None:
        result = cad.mjcf.validate(self.write(BROKEN), compile="never")
        self.assertFalse(result.ok)
        self.assertEqual("error", self.codes(result)["mesh_asset_unknown"])
        self.assertEqual("", result.summary)

    def test_a_file_that_is_not_an_mjcf(self) -> None:
        self.assertFalse(cad.mjcf.validate(self.folder / "missing.xml").ok)
        self.assertFalse(cad.mjcf.validate(self.write("<mujoco/>", "robot.urdf")).ok)

    def test_an_unknown_compile_mode_is_refused_by_name(self) -> None:
        with self.assertRaises(ValueError) as refused:
            cad.mjcf.validate(self.write(GOOD), compile="sometimes")  # type: ignore[arg-type]
        self.assertIn("compile must be one of auto, required, never", str(refused.exception))

    def test_auto_compiles_where_mujoco_is_installed(self) -> None:
        result = cad.mjcf.validate(self.write(GOOD))
        self.assertTrue(result.ok)
        self.assertEqual("info", self.codes(result)["compiled"])

    def test_what_mujoco_refuses_is_an_error_in_its_words(self) -> None:
        path = self.write(MASSLESS)
        self.assertTrue(cad.mjcf.validate(path, compile="never").ok)
        result = cad.mjcf.validate(path, compile="required")
        self.assertFalse(result.ok)
        refused = [finding for finding in result.findings if finding.code == "compile_failed"]
        self.assertEqual(1, len(refused))
        self.assertIn("MuJoCo refused the model", refused[0].message)
        self.assertIn("mass", refused[0].message)

    def test_without_mujoco_auto_skips_and_required_fails(self) -> None:
        path = self.write(GOOD)
        with mock.patch.object(_compile, "installed", lambda: False):
            skipped = cad.mjcf.validate(path, compile="auto")
            required = cad.mjcf.validate(path, compile="required")
        self.assertTrue(skipped.ok)
        self.assertEqual({"compile_skipped": "info"}, self.codes(skipped))
        self.assertFalse(required.ok)
        self.assertEqual({"compile_unavailable": "error"}, self.codes(required))


if __name__ == "__main__":
    unittest.main()
