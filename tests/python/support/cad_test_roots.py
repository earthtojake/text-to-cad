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

        # The store is content-addressed and shared (~/.cache/cadgen unless
        # CADGEN_CACHE_DIR says otherwise): fixtures that produce identical document bytes
        # share a tree key, so a populated developer store satisfies builds a test expects
        # to RUN, turns "built" into "reused", and breaks "must not exist yet" preconditions.
        # test-python.sh points the whole run at a fresh store; a direct `python -m unittest`
        # does not. Give this test a store of its own either way, and RESTORE the previous
        # value on cleanup (never pop it) so the runner's isolation outlives the test.
        self.cache_dir = self.root / "cadgen-cache"
        self.cache_dir.mkdir()
        previous_cache_dir = os.environ.get("CADGEN_CACHE_DIR")
        os.environ["CADGEN_CACHE_DIR"] = str(self.cache_dir)

        def restore_cache_dir() -> None:
            if previous_cache_dir is None:
                os.environ.pop("CADGEN_CACHE_DIR", None)
            else:
                os.environ["CADGEN_CACHE_DIR"] = previous_cache_dir

        testcase.addCleanup(restore_cache_dir)

    def temporary_cad_directory(self, *, prefix: str) -> tempfile.TemporaryDirectory[str]:
        return tempfile.TemporaryDirectory(prefix=prefix, dir=self.cad_root)
