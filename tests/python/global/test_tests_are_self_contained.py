"""Tests are self-contained: nothing under tests/ reads, builds or imports the
models/ corpus, and nothing depends on the developer's own engine daemon.

The corpus is a fixture area for humans and skills, not for the test suite: its
outputs are generated (gitignored, absent in CI), and a test that reaches into it
either fails on a fresh clone or passes only because a developer built something
earlier. Each test writes the small model it
needs (a `bd.Box` is enough for every contract that is not about geometry), or
reads a tiny fixture committed with the tests.

The runner gives every test file an engine daemon of its own; a test that spawns a
build should still set CAD_ENGINE_DIR itself so a direct `python -m unittest`
never builds on the developer's daemon (that is a convention, not something this
guard can tell apart from a subprocess that merely runs Python). A test module that names
an engine folder names its own state and cache folders too, or calls
``engine_daemon.isolate``: an engine with only its folder its own still records and caches
its documents in the developer's (they then show in every `cad status`).
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
                    REPO_ROOT / "apps" / "web", REPO_ROOT / "apps" / "mcp", REPO_ROOT / "apps" / "api", REPO_ROOT):
        for folder in ("src", "scripts", "tests"):
            for extension in ("js", "mjs", "cjs", "jsx", "ts", "tsx"):
                for pattern in (f"*.test.{extension}", f"*.spec.{extension}"):
                    paths.update(path for path in (package / folder).rglob(pattern) if "node_modules" not in path.parts)
    # The docs site's CI checks (`npm --prefix apps/docs run check` runs them).
    paths.update((REPO_ROOT / "apps" / "docs" / "scripts").rglob("*.mjs"))
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


class EnginesKeepTheirDocumentsToThemselves(unittest.TestCase):
    def test_a_module_that_names_an_engine_folder_names_its_state_and_cache(self) -> None:
        unkept = []
        for path in sorted((TESTS / "python").rglob("test_*.py")):
            text = path.read_text(encoding="utf-8")
            if "CAD_ENGINE_DIR" not in text or "engine_daemon.isolate(" in text:
                continue
            missing = [name for name in ("CAD_STATE_DIR", "CAD_CACHE_DIR") if name not in text]
            if missing:
                unkept.append(f"{path.relative_to(REPO_ROOT).as_posix()}: no {' or '.join(missing)}")
        self.assertEqual(unkept, [], "a test module that starts an engine keeps its documents to itself: set "
                                     "CAD_STATE_DIR and CAD_CACHE_DIR beside CAD_ENGINE_DIR, or call "
                                     "engine_daemon.isolate(unittest.addModuleCleanup) in setUpModule")


if __name__ == "__main__":
    unittest.main()
