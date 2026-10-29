"""The dependency-direction and ships-alone laws, held by test rather than prose.

Boundary law (packages/README.md and each package's README): apps import
packages; packages never import apps (here for cadgen's Python; the JavaScript's
direction, and core being framework-free, are scripts/test/check-dependencies.mjs's). Ships-alone law: cadgen (the built PyPI
distribution) and every skill (the Skills CLI installs
skills/<name> ALONE; plugin installers copy the published tree, which has no
models/ and whose packages/ is never installed) each work in isolation outside
this repo, so their markdown must not refer to anything outside the package.
The private apps are workspace consumers; their READMEs describe that workspace.
The web app ships as compiled assets inside cadgen, not as a source mirror.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from tests.python.support.paths import repo_path

CADGEN_SRC = repo_path("packages/cadgen/src")


class PackagesNeverImportApps(unittest.TestCase):
    def test_no_python_reference_into_apps(self) -> None:
        offenders: list[str] = []
        for path in CADGEN_SRC.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for lineno, line in enumerate(text.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if re.search(r"""["'](?:\.\./)*apps/""", stripped):
                    offenders.append(f"{path}:{lineno}: {stripped[:80]}")
        self.assertEqual(
            offenders,
            [],
            "packages never reach into apps/ (dependency-direction law): the "
            "distribution must build and run with the apps deleted.",
        )


# The ships-alone law. Two surfaces leave this repo whole:
#   - packages/cadgen builds into the PyPI wheel (README.md is its long
#     description; @text-to-cad/core and the viewer client arrive already bundled
#     under _runtime/).
#   - skills/ installs standalone: the Skills CLI copies skills/<name> by
#     itself, and Claude Code and Codex copy the PUBLISHED tree, which has no
#     models/ and never installs its packages/ — so a skill that points at this
#     repo's example projects (models/examples, models/thang010146), at apps/,
#     packages/ or tests/, or says "in this repo" makes a promise the installed
#     skill cannot keep.
# A repo-relative path in any of them ships broken. Each root forbids the
# path families that only mean something inside this repo; a package may
# name its own files, its bundled/vendored dependencies, and the concepts of
# its dependencies — never the repo's layout. `models/` itself stays legal in
# skills: it is the conventional example of a USER workspace's model
# directory ("the project's `models/` directory"), never this repo's.
_MD_BOUNDARY = r"(?<![\w./@-])"
_MD_ISOLATION_ROOTS: dict[str, tuple[str, ...]] = {
    # cadgen ships with no repo around it at all: nothing repo-relative.
    "packages/cadgen": (
        r"apps/",
        r"packages/",
        r"skills/",
        r"models/",
        r"tests/",
        r"scripts/",
        r"requirements-dev",
        r"AGENTS\.md",
        r"CONTRIBUTING\.md",
        r"\.github/",
    ),
    # Skills own their scripts/<tool> entrypoints; the repo's scripts/
    # families and dev manifests are not theirs to name. A project's `.venv`
    # is a user environment, like its models/ directory, not a repository dependency.
    "skills": (
        r"apps/",
        r"packages/",
        r"tests/",
        r"scripts/(?:bundle|dev|test|release|install|github-workflows)/",
        r"requirements-dev",
        r"AGENTS\.md",
        r"CONTRIBUTING\.md",
        r"\.github/",
    ),
}
# Phrases forbidden anywhere in a line, boundary or not: this repo's example
# projects (a `.../models/thang010146/STEP` path hides `models/` behind a
# slash, so the bounded families above would miss it) and the words that
# only make sense from inside the checkout.
_MD_UNBOUNDED_PHRASES: dict[str, tuple[str, ...]] = {
    "skills": (
        r"models/(?:examples|thang010146)",
        r"thang010146",
        r"[Tt]his repo(?:sitory)?\b",
        r"[Rr]epository fixtures",
    ),
}
_MD_SKIPPED_DIRS = {"node_modules", "dist", "dist-verify", ".vite", "tmp", "__pycache__"}
_URL_RE = re.compile(r"https?://\S+")


def _markdown_files(root: Path):
    for path in sorted(root.rglob("*.md")):
        if _MD_SKIPPED_DIRS.intersection(path.parts):
            continue
        yield path


class PackagedMarkdownShipsAlone(unittest.TestCase):
    """Shipped markdown must read true outside this repo."""

    def test_no_repo_relative_references(self) -> None:
        offenders: list[str] = []
        for root_rel, families in _MD_ISOLATION_ROOTS.items():
            root = repo_path(root_rel)
            pattern = re.compile(_MD_BOUNDARY + "(?:" + "|".join(families) + ")")
            phrases = _MD_UNBOUNDED_PHRASES.get(root_rel, ())
            phrase_pattern = re.compile("|".join(phrases)) if phrases else None
            for path in _markdown_files(root):
                text = path.read_text(encoding="utf-8", errors="replace")
                for lineno, line in enumerate(text.splitlines(), 1):
                    # URLs are exempt from the path families (a GitHub link
                    # may legally spell docs/ or main/) but not from the
                    # phrases: `?file=thang010146/...` is still this repo's
                    # example project.
                    scannable = _URL_RE.sub("", line)
                    match = pattern.search(scannable) or (
                        phrase_pattern and phrase_pattern.search(line)
                    )
                    if match:
                        rel = path.relative_to(repo_path("."))
                        offenders.append(f"{rel}:{lineno}: {line.strip()[:100]}")
        self.assertEqual(
            offenders,
            [],
            "Ships-alone law: cadgen installs from PyPI and skills "
            "install alone (the Skills CLI copies skills/<name> by itself; "
            "the published tree has no models/), so their markdown must be "
            "true and actionable with "
            "this repo gone. Name the bundled thing ('the @text-to-cad/core runtime "
            "bundled at build time'), not the repo path to its source; give "
            "a skill a self-contained exemplar in its references/, not a "
            "pointer at this repo's example projects; move repo-development "
            "guidance to CONTRIBUTING.md; delete what serves neither "
            "audience.\n"
            + "\n".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
