"""Tests are self-contained: nothing under tests/ reads, builds or imports the
models/ corpus, and nothing depends on the developer's default store.

The corpus is a fixture area for humans and skills, not for the test suite: its
outputs are generated (gitignored, absent in CI), its inputs may be LFS pointers,
and a test that reaches into it either fails on a fresh clone or passes only
because a developer built something earlier. Each test writes the small model it
needs (a `bd.Box` is enough for every contract that is not about geometry), or
reads a tiny fixture committed under tests/.

The runner gives every test file its own fresh store; a test that spawns a build
should still set CADGEN_CACHE_DIR itself so a direct `python -m unittest` never
reads the developer's ~/.cache/cadgen (that is a convention, not something this
guard can tell apart from a subprocess that merely runs Python).
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from tests.python.support.paths import REPO_ROOT

TESTS = REPO_ROOT / "tests"
MODELS = REPO_ROOT / "models"

# Every top-level project under models/ -- the corpus a test must never name as a
# path. A fictional `models/part.step` inside a temp root is fine; `models/juno/…`
# is not.
CORPUS_DIRS = sorted(p.name for p in MODELS.iterdir() if p.is_dir())
CORPUS_PATH = re.compile(r"models/(?:" + "|".join(map(re.escape, CORPUS_DIRS)) + r")/")
# Joining the repo root with "models" is reaching into the corpus by another spelling.
REPO_MODELS = re.compile(r"""(?:REPO_ROOT|REPO|ROOT|repo_root\(\)|repo_path\()\s*(?:/|,)\s*["']models(?:["']|/)""")

# This file names the corpus on purpose (in the regexes above), as does the
# package-boundary guard, whose regex forbids package markdown from naming it.
EXEMPT = {
    Path(__file__).resolve(),
    (TESTS / "python" / "global" / "test_package_boundaries.py").resolve(),
}


def _test_files():
    for path in sorted(TESTS.rglob("*.py")):
        if "__pycache__" in path.parts or path.resolve() in EXEMPT:
            continue
        yield path


class TestsNeverTouchTheCorpus(unittest.TestCase):
    def test_no_test_names_a_corpus_path(self) -> None:
        offenders = []
        for path in _test_files():
            text = path.read_text(encoding="utf-8")
            for match in CORPUS_PATH.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{line}: {match.group(0)}")
            for match in REPO_MODELS.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{line}: {match.group(0)}")
        self.assertEqual(
            offenders,
            [],
            "a test reaches into models/; write the fixture it needs instead:\n  " + "\n  ".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
