"""``cad <type> check --process molding|printing``: a 3D type's manufacturing check, as a command.

The measurements are the library's (``tests/python/packages/cad/test_trimesh_*.py``); this holds the
command: its options, its one result shape, its refusals before anything is read, a STEP measured
through the engine's tessellation, and the run in the environment of the trimesh integration when the
command's own environment lacks it.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import trimesh

from cad_server._internal import integration_env
from cad_server.cli.document_types import pull_value, type_main


def _run(document_type: str, *argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = type_main(document_type, ["check", *argv])
    return code, out.getvalue(), err.getvalue()


class ManufacturingCheckCommand(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory(prefix="cad-check-cli-")
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.box = self.folder / "box.stl"
        trimesh.creation.box(extents=(20, 20, 15)).export(self.box)

    def test_molding_answers_one_json_line_with_its_measurements(self) -> None:
        code, out, _ = _run("stl", str(self.box), "--process", "molding", "--pull", "-z", "--json")
        payload = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(sorted(payload), ["findings", "measurements", "ok", "path", "summary"])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["measurements"]["draft"]["pull_axis"], [0.0, 0.0, -1.0], "--pull -z reached argparse")
        finding = next(f for f in payload["findings"] if f["code"] == "zero_draft_walls")
        self.assertEqual((finding["severity"], len(finding["location"].split(", "))), ("warning", 3))
        self.assertEqual(pull_value(["p.stl", "--pull", "-z"]), ["p.stl", "--pull=-z"])

    def test_printing_says_its_findings_then_its_summary(self) -> None:
        code, out, _ = _run("stl", str(self.box), "--process", "printing", "--angle-limit", "30")
        self.assertEqual(code, 0)
        self.assertRegex(out.splitlines()[-1], r"^OK .*box\.stl: printing: 6000 mm3, 1 body\(ies\); overhangs under 30 deg")

    def test_a_mistake_is_refused_before_anything_is_read(self) -> None:
        for argv, words in (((str(self.box),), "give --process molding or printing"),
                            ((str(self.box), "--process", "casting"), "not 'casting'"),
                            ((str(self.box), "--process", "molding", "--samples", "9"), "--samples is not molding's"),
                            ((str(self.box), "--process", "printing", "--pull", "z"), "--pull is not printing's"),
                            ((str(self.box), "--process", "molding", "--candidates", "--pull", "x"), "ranks every pull")):
            with self.subTest(argv=argv):
                code, out, _ = _run("stl", *argv, "--json")
                self.assertEqual((code, json.loads(out)["ok"]), (1, False))
                self.assertIn(words, json.loads(out)["error"])
        code, out, _ = _run("threemf", str(self.folder / "box.3mf"), "--process", "printing", "--units", "cm", "--json")
        self.assertIn("a 3MF declares its unit", json.loads(out)["error"])
        code, _, err = _run("stl", str(self.folder / "box.glb"), "--process", "molding")
        self.assertEqual(code, 2)
        self.assertIn("box.glb is a glb, not a stl: use cad glb check", err)

    def test_a_usage_error_is_argparses_two_and_a_failed_measurement_one(self) -> None:
        """Exit 1 is a check that failed (a family not measured); a misspelled flag never reads as one."""
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            _run("stl", str(self.box), "--process", "molding", "--not-a-flag")
        self.assertEqual(raised.exception.code, 2)
        code, out, _ = _run("stl", str(self.folder / "missing.stl"), "--process", "molding", "--json")
        self.assertEqual((code, json.loads(out)["findings"][0]["code"]), (1, "invalid_target"))

    def test_a_step_is_measured_as_the_engine_tessellates_it(self) -> None:
        from build123d import Box, export_step

        step = self.folder / "box.step"
        export_step(Box(20, 20, 15), str(step))
        code, out, _ = _run("step", str(step), "--process", "printing", "--json")
        payload = json.loads(out)
        self.assertEqual(code, 0, out)
        self.assertAlmostEqual(payload["measurements"]["mesh"]["volume_mm3"], 6000.0, delta=1.0)
        self.assertEqual(payload["path"], str(step.resolve()))

    def test_without_trimesh_here_it_runs_in_the_integrations_environment(self) -> None:
        """The command's environment lacks the integration: the check runs in the one that holds it (this
        interpreter stands in for it), answering exactly as it does here."""
        argv = (str(self.box), "--process", "molding", "--candidates", "--json")
        _code, here, _ = _run("stl", *argv)
        with mock.patch.object(integration_env, "carries", return_value=False), \
                mock.patch.object(integration_env, "environment", return_value=sys.executable) as made:
            code, there, _ = _run("stl", *argv)
            refused, said, _ = _run("stl", str(self.box), "--process", "molding", "--samples", "3", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(there), json.loads(here))
        self.assertEqual((refused, made.call_count), (1, 1), "a refusal makes no environment")
        self.assertIn("--samples is not molding's", json.loads(said)["error"])


if __name__ == "__main__":
    unittest.main()
