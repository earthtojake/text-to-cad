"""``cad cam features|plan`` are the library's verbs, run where the CAD kernel is (``kernel_verb``)."""

from __future__ import annotations

import contextlib
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

from cad_server._internal import base  # noqa: E402
from cad_server.cli import cam_features, cam_plan  # noqa: E402


class CamCommandsTest(unittest.TestCase):
    def test_each_command_takes_its_verbs_options(self):
        import cad.cam

        self.assertIn("--occurrence", cam_features.build_parser().format_help())
        self.assertIn("--job", cam_plan.build_parser().format_help())
        self.assertTrue(cad.cam.plan.__doc__)

    def test_the_command_prints_what_came_back_from_the_base(self):
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(base, "ensure", return_value=base.Environment(sys.executable, sys.prefix, False)), \
                mock.patch.dict(os.environ, {"PYTHONPATH": SOURCE_PATH}), contextlib.redirect_stdout(out):
            code = cam_features.main([str(Path(tmp) / "missing.step"), "--json"])
        self.assertEqual(code, 1)
        payload = json.loads(out.getvalue().strip().splitlines()[-1])
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["document"].endswith("missing.step"))
        self.assertIn("missing.step", payload["findings"][0]["summary"])


if __name__ == "__main__":
    unittest.main()
