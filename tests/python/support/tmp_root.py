from __future__ import annotations

import tempfile
from pathlib import Path

from tests.python.support.paths import REPO_ROOT

TMP_ROOT = REPO_ROOT / "tmp"
CAD_TEST_TMP_ROOT = TMP_ROOT / "cad-skill-tests"


def temporary_directory(*, prefix: str) -> tempfile.TemporaryDirectory[str]:
    CAD_TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(prefix=prefix, dir=CAD_TEST_TMP_ROOT)


def named_tmp_root(name: str) -> Path:
    tmp_root = TMP_ROOT / name
    tmp_root.mkdir(parents=True, exist_ok=True)
    return tmp_root
