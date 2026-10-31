"""The dependency-direction and ships-alone laws, held by test rather than prose.

Boundary law (packages/README.md and each package's README): apps import
packages; packages never import apps (here for the Python distributions'; the JavaScript's
direction, and core being framework-free, are scripts/test/check-dependencies.mjs's). Ships-alone
law: each Python distribution (the library, cad; the server, cad-server; the shim,
cad-mcp: each its own PyPI wheel) and every skill (the Skills CLI installs
skills/<name> ALONE; plugin installers copy the published tree, which has no
models/ and whose packages/ is never installed; the server's wheel carries skills/ whole, and
writes it into the plugin folder the agent apps read) each work in isolation outside
this repo, so their markdown must not refer to anything outside the package -- a
distribution's not even to another distribution's files, which its wheel does not carry, and
a skill's links not out of its skill.
The private apps are workspace consumers; their READMEs describe that workspace.
The web app ships as compiled assets inside the server's wheel, not as a source mirror.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from tests.python.support.paths import PROJECTS, REPO_ROOT, SOURCES, repo_path


class PackagesNeverImportApps(unittest.TestCase):
    def test_no_python_reference_into_apps(self) -> None:
        offenders: list[str] = []
        for path in (path for source in SOURCES for path in source.rglob("*.py")):
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
#   - packages/cad, packages/cad-server and packages/cad-mcp each
#     build into a PyPI wheel (each README.md is its long description; the server's
#     @text-to-cad/core and viewer client arrive already bundled under _runtime/).
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
# A distribution ships with no repo around it at all: nothing repo-relative.
_DISTRIBUTION_FAMILIES = (
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
)
_MD_ISOLATION_ROOTS: dict[str, tuple[str, ...]] = {
    **{project.relative_to(REPO_ROOT).as_posix(): _DISTRIBUTION_FAMILIES for project in PROJECTS},
    # Skills own their scripts/<tool> entrypoints; the repo's scripts/
    # families, its venv and its dev manifests are not theirs to name.
    "skills": (
        r"apps/",
        r"packages/",
        r"tests/",
        r"scripts/(?:bundle|dev|test|release|install|github-workflows)/",
        r"\.venv",
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
_MD_SKIPPED_DIRS = {"node_modules", "dist", "dist-verify", ".vite", "tmp", "__pycache__", "_runtime"}
_URL_RE = re.compile(r"https?://\S+")
# A Markdown link's target, its fragment apart.
_MD_LINK = re.compile(r"\]\(([^)\s#]*)(?:#[^)\s]*)?(?:\s+\"[^\"]*\")?\)")


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


def _links_outside(root: Path, files) -> list[str]:
    """Each relative Markdown link in ``files`` that leaves ``root`` or names nothing there."""
    offenders = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for target in _MD_LINK.findall(text):
            if not target or re.match(r"[a-z][a-z0-9+.-]*:", target, re.I):
                continue  # a fragment of this page, or a URL
            resolved = (path.parent / target).resolve()
            if not resolved.is_relative_to(root.resolve()) or not resolved.exists():
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {target}")
    return offenders


class DistributionLinksStayInside(unittest.TestCase):
    """A distribution's relative links name its own files: another distribution's are not in its wheel."""

    def test_every_relative_link_resolves_inside_its_distribution(self) -> None:
        offenders: list[str] = []
        for project in PROJECTS:
            offenders += _links_outside(project, _markdown_files(project))
        self.assertEqual(offenders, [], "a link out of its distribution, or to a file that is not there")

    def test_every_skill_link_resolves_inside_its_skill(self) -> None:
        # The skills ship whole inside the server's wheel (cad_server/_runtime/plugin/skills, byte for byte
        # these files: scripts/release/check-wheel-contents.sh) and each alone through the Skills CLI, so a
        # skill's relative link names a file of its own skill, which both carry, or is a URL.
        offenders: list[str] = []
        for skill in sorted(path.parent for path in repo_path("skills").glob("*/SKILL.md")):
            offenders += _links_outside(skill, _markdown_files(skill))
        self.assertEqual(offenders, [], "a skill's link out of its skill, or to a file that is not there")


if __name__ == "__main__":
    unittest.main()
