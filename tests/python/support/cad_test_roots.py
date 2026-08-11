from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("skills/cad/scripts")

from tests.python.support.tmp_root import CAD_TEST_TMP_ROOT, temporary_directory


IGNORED_TEST_ROOT = CAD_TEST_TMP_ROOT


class IsolatedCadRoots:
    def __init__(self, testcase: unittest.TestCase, *, prefix: str) -> None:
        self._tempdir = temporary_directory(prefix=prefix)
        testcase.addCleanup(self._tempdir.cleanup)

        self.root = Path(self._tempdir.name)
        self.cad_root = self.root / "workspace"
        self.cad_root.mkdir(parents=True, exist_ok=True)

        # cadgen resolves its discovery / identity / display roots from the live process working
        # directory (the module-level REPO_ROOT/CAD_ROOT globals were removed), so isolate the
        # test by switching cwd into the temp workspace and restoring it on cleanup.
        previous_cwd = Path.cwd()
        os.chdir(self.cad_root)
        testcase.addCleanup(lambda: os.chdir(previous_cwd))

    def temporary_cad_directory(self, *, prefix: str) -> tempfile.TemporaryDirectory[str]:
        return tempfile.TemporaryDirectory(prefix=prefix, dir=self.cad_root)
