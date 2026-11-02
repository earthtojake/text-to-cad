"""A library verb that needs the CAD kernel runs where the kernel is: in this process when the installation
carries it, else in the base's Python, its arguments and its result one JSON line each way."""

from __future__ import annotations

import contextlib
import dataclasses
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import SOURCE_PATH, add_repo_path

add_repo_path("packages/cad/src")

from cad.results import CamFeaturesResult, CamPlanResult  # noqa: E402
from cad_server._internal import base, kernel_verb  # noqa: E402
from cad_server.cli import cam_features  # noqa: E402

PROG = "cad cam features"


class InKernelTest(unittest.TestCase):
    def test_the_command_takes_the_verbs_own_options(self):
        import cad.cam

        verb = kernel_verb.in_kernel(("cad.cam", "plan"), prog="cad cam plan")
        self.assertIs(verb.__wrapped__, cad.cam.plan)
        self.assertEqual(verb.__doc__, cad.cam.plan.__doc__)

    def test_an_installation_that_carries_the_kernel_runs_the_verb_here(self):
        found = CamFeaturesResult(ok=True, document=Path("part.step"))
        with mock.patch("cad.cam.features", return_value=found) as features, \
                mock.patch.object(base, "ensure", return_value=base.Environment(sys.executable, sys.prefix, True)), \
                mock.patch.object(kernel_verb.subprocess, "run") as run:
            self.assertIs(kernel_verb.in_kernel(("cad.cam", "features"), prog=PROG)(Path("part.step")), found)
        features.assert_called_once_with(Path("part.step"))
        run.assert_not_called()

    def test_else_the_bases_python_runs_it_and_its_result_comes_back_as_its_type(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(base, "ensure", return_value=base.Environment(sys.executable, sys.prefix, False)), \
                mock.patch.dict(os.environ, {"PYTHONPATH": SOURCE_PATH}):
            missing = Path(tmp) / "missing.step"
            result = kernel_verb.in_kernel(("cad.cam", "features"), prog=PROG)(missing, occurrence=None)
        self.assertIsInstance(result, CamFeaturesResult)
        self.assertFalse(result.ok)
        self.assertEqual(result.document, missing)
        self.assertIsInstance(result.findings, tuple)
        self.assertIn("missing.step", result.findings[0]["summary"])

    def test_a_result_keeps_its_paths_and_tuples(self):
        planned = CamPlanResult(ok=True, document=Path("/w/part.step"), glb=Path("/w/part.cam.glb"),
                                posts=({"setup": "top", "file": "/w/part.top.nc", "post": "grbl", "tool": None},),
                                verdict={"status": "ready"}, assumed=({"key": "k", "value": [1, 2], "why": "w"},))
        answer = json.loads(json.dumps({"result": "CamPlanResult", "fields": dataclasses.asdict(planned)}, default=str))
        self.assertEqual(kernel_verb.result(answer), planned)

    def test_a_runner_that_fails_is_an_error_naming_the_verb(self):
        failed = mock.Mock(returncode=1, stdout="")
        with mock.patch.object(base, "ensure", return_value=base.Environment("/nowhere/python", "/nowhere", False)), \
                mock.patch.object(kernel_verb.subprocess, "run", return_value=failed):
            with self.assertRaisesRegex(RuntimeError, r"did not run cad\.cam\.features \(exit code 1\)"):
                kernel_verb.in_kernel(("cad.cam", "features"), prog=PROG)(Path("part.step"))

    def test_the_command_prints_what_came_back(self):
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(base, "ensure", return_value=base.Environment(sys.executable, sys.prefix, False)), \
                mock.patch.dict(os.environ, {"PYTHONPATH": SOURCE_PATH}), contextlib.redirect_stdout(out):
            code = cam_features.main([str(Path(tmp) / "missing.step"), "--json"])
        self.assertEqual(code, 1)
        payload = json.loads(out.getvalue().strip().splitlines()[-1])
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["document"].endswith("missing.step"))


if __name__ == "__main__":
    unittest.main()
