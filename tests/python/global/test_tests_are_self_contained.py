"""Tests are self-contained: nothing under tests/ reads, builds or imports the
models/ corpus, and nothing depends on the developer's default store.

The corpus is a fixture area for humans and skills, not for the test suite: its
outputs are generated (gitignored, absent in CI), its inputs may be LFS pointers,
and a test that reaches into it either fails on a fresh clone or passes only
because a developer built something earlier. Each test writes the small model it
needs (a `bd.Box` is enough for every contract that is not about geometry), or
reads a tiny fixture committed with the tests.

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

# These spellings construct this checkout's models/ path. Plain models/... paths
# remain legal because many tests create a fictional project beneath a temp root.
REPO_MODEL_PATTERNS = (
    re.compile(
        r"""\b(?:REPO_ROOT|_REPO_ROOT|REPO|repoRoot|repo_root\(\))\s*(?:/|,|\.joinpath\()\s*["']models(?:["']|/)"""
    ),
    re.compile(r"""Path\(__file__\)\.resolve\(\)\.parents\[\d+\]\s*/\s*["']models["']"""),
    re.compile(r"""Path\.cwd\(\)\s*(?:/|,|\.joinpath\()\s*["']models(?:["']|/)"""),
    re.compile(r"""\brepo_path\(\s*["']models(?:["']|/)"""),
    re.compile(r"""\$\{?REPO_ROOT\}?/models/"""),
    re.compile(r"""["'`]\.\.(?:/\.\.)*/models/"""),
)

# This file names the corpus on purpose in the patterns above.
EXEMPT = {Path(__file__).resolve()}


def _test_files():
    paths = set()
    for extension in ("py", "js", "mjs", "ts"):
        paths.update(TESTS.rglob(f"*.{extension}"))
    for extension in ("py", "sh"):
        paths.update((REPO_ROOT / "scripts" / "test").rglob(f"*.{extension}"))
    for package in (REPO_ROOT / "packages" / "core", REPO_ROOT / "packages" / "ui",
                    REPO_ROOT / "apps" / "web", REPO_ROOT / "apps" / "desktop"):
        for folder in ("src", "scripts", "tests"):
            for extension in ("js", "mjs", "cjs", "jsx", "ts", "tsx"):
                for pattern in (f"*.test.{extension}", f"*.spec.{extension}"):
                    paths.update((package / folder).rglob(pattern))
    for path in sorted(paths):
        if "__pycache__" in path.parts or path.resolve() in EXEMPT:
            continue
        yield path


class TestsNeverTouchTheCorpus(unittest.TestCase):
    def test_no_test_names_the_repo_models_path(self) -> None:
        offenders = []
        for path in _test_files():
            text = path.read_text(encoding="utf-8")
            for pattern in REPO_MODEL_PATTERNS:
                for match in pattern.finditer(text):
                    line = text.count("\n", 0, match.start()) + 1
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{line}: {match.group(0)}")
        self.assertEqual(
            offenders,
            [],
            "a test reaches into models/; write the fixture it needs instead:\n  " + "\n  ".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
