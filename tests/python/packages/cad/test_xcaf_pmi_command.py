"""``cad run xcaf-pmi``: the environment's own command, its exit code the run's (``cad.xcaf_pmi._command``).

The command is a stand-in here: a script beside a stand-in Python. xcaf-pmi itself is on no index yet, so no
job installs it."""

from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cad import registry
from cad._internal.integrations import INTEGRATIONS, for_command
from cad.xcaf_pmi import _command


class CommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="xcaf-pmi-"))
        self.python = self.folder / "python"

    def script(self, body: str) -> Path:
        found = self.folder / "xcaf-pmi"
        found.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
        found.chmod(0o755)
        return found

    def test_the_integration_declares_the_command_and_its_runner(self) -> None:
        self.assertEqual(registry.INTEGRATIONS["xcaf_pmi"].commands, ("xcaf-pmi",))
        self.assertEqual(for_command("xcaf-pmi"), "xcaf_pmi")
        self.assertEqual(INTEGRATIONS["xcaf_pmi"].runner, "cad.xcaf_pmi._command")

    @unittest.skipIf(os.name == "nt", "a shell script stands in for the command")
    def test_the_run_is_the_environment_s_command_with_its_exit_code(self) -> None:
        said = self.folder / "said"
        self.script(f'echo "$@" > "{said}"\nexit 3')
        with mock.patch.object(sys, "executable", str(self.python)):
            self.assertEqual(_command.main(["xcaf-pmi", "to-step", "a.xbf", "-o", "a.step"]), 3)
        self.assertEqual(said.read_text(encoding="utf-8").strip(), "to-step a.xbf -o a.step")

    def test_an_environment_with_no_command_says_so(self) -> None:
        wrote = io.StringIO()
        with mock.patch.object(sys, "executable", str(self.python)), contextlib.redirect_stderr(wrote):
            self.assertEqual(_command.main(["xcaf-pmi", "--help"]), 2)
        self.assertIn("cad[xcaf_pmi]", wrote.getvalue())


if __name__ == "__main__":
    unittest.main()
