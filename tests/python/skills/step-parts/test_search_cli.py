from __future__ import annotations

import subprocess
import sys
import unittest

from tests.python.support.paths import repo_path


class StepPartsSearchCliTests(unittest.TestCase):
    """Smoke-test the search/download CLI without touching the network."""

    def test_help_exits_zero_and_documents_network_flags(self) -> None:
        script = repo_path("skills", "step-parts", "scripts", "download_step_part.py")
        proc = subprocess.run(
            [sys.executable, str(script), "--help"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("usage:", proc.stdout)
        for flag in ("--origin", "--download", "--out-dir", "--limit"):
            with self.subTest(flag=flag):
                self.assertIn(flag, proc.stdout)

    def test_invalid_flag_exits_nonzero(self) -> None:
        script = repo_path("skills", "step-parts", "scripts", "download_step_part.py")
        proc = subprocess.run(
            [sys.executable, str(script), "--definitely-not-a-flag"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertNotEqual(0, proc.returncode)
