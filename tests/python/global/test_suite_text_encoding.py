"""Every text read/write in the test suite must name its encoding.

``Path.read_text()`` / ``Path.write_text()`` with no ``encoding=`` use
``locale.getencoding()``. On Linux and macOS that is UTF-8, so a bare call is
invisible; on Windows it is cp1252, and the suite is full of asymmetric pairs
where only one side of a byte round-trip is locale-dependent:

* a fixture written by ``write_text`` and then ``compile()``d, imported, or run
  by a spawned interpreter -- Python source is ALWAYS decoded as UTF-8, so the
  writer must encode as UTF-8 too. This shipped: an em dash in a model
  docstring was written as cp1252 ``0x97`` and the child died with a
  SyntaxError (``test_main_module_survives_eviction``);
* a ``read_text`` of a repo file. Repo sources are UTF-8 and this codebase's
  prose is full of em dashes, so a cp1252 read either raises or silently
  mangles the text a policy check is grepping.

Both are one keyword away, and neither is catchable on the platforms most of
this repo's development happens on -- so it is policy-checked here rather than
left to review.

If this fails: add ``encoding="utf-8"``. There is no case in the test suite
where the developer's locale is the right answer.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
TESTS_ROOT = REPO_ROOT / "tests"

METHODS = ("read_text", "write_text")

# Files still carrying bare calls, excluded so this check can land ahead of the
# branches that own them. This list may only SHRINK: fix the file, drop the
# entry. The staleness test below fails once an entry has nothing left to fix,
# so the list cannot outlive the work.
PENDING = {
    "tests/python/global/test_render_contract_sync.py",
    "tests/python/packages/cadgen/test_kinematics_build.py",
    "tests/python/packages/cadgen/test_step_export_reuse.py",
    "tests/python/packages/cadgen/test_step_write_determinism.py",
    "tests/python/skills/cad/inspect_refs/test_refs_inspect.py",
    "tests/python/skills/cad/snapshot/test_cli.py",
    "tests/python/skills/dxf/test_snapshot_cli.py",
    "tests/python/support/oracle.py",
}


def _bare_calls(path: Path) -> list[tuple[int, str]]:
    """Line and method of every ``.read_text()``/``.write_text()`` with no encoding."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in METHODS:
            continue
        # ``**kwargs`` (arg is None) could carry it; do not guess.
        if any(kw.arg in ("encoding", None) for kw in node.keywords):
            continue
        found.append((node.lineno, func.attr))
    return found


def _sources() -> list[Path]:
    return sorted(
        path
        for path in TESTS_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def _scan() -> dict[str, list[tuple[int, str]]]:
    hits: dict[str, list[tuple[int, str]]] = {}
    for path in _sources():
        bare = _bare_calls(path)
        if bare:
            hits[path.relative_to(REPO_ROOT).as_posix()] = bare
    return hits


class TestSuiteTextEncodingTest(unittest.TestCase):
    def test_the_scan_finds_something_to_check(self) -> None:
        """Guard the premise: a broken walk would pass every other test here."""
        self.assertGreater(len(_sources()), 50, "walked no test sources -- wrong path?")

    def test_no_bare_read_text_or_write_text(self) -> None:
        offenders = {
            relative: bare
            for relative, bare in _scan().items()
            if relative not in PENDING
        }
        detail = "\n".join(
            f"  {relative}: " + ", ".join(f"L{line} {attr}" for line, attr in bare)
            for relative, bare in sorted(offenders.items())
        )
        self.assertEqual(
            {},
            offenders,
            "read_text/write_text without encoding=\"utf-8\" -- these decode as cp1252 "
            "on Windows and mangle every non-ASCII character:\n" + detail,
        )

    def test_pending_entries_are_real_and_still_pending(self) -> None:
        """The exemption list self-prunes: no stale, no fictional entries."""
        hits = _scan()
        missing = sorted(entry for entry in PENDING if not (REPO_ROOT / entry).is_file())
        self.assertEqual([], missing, "PENDING names files that no longer exist")
        clean = sorted(entry for entry in PENDING if entry not in hits)
        self.assertEqual(
            [],
            clean,
            "these PENDING files have no bare read_text/write_text left -- drop them "
            f"from PENDING to lock the fix in: {clean}",
        )


if __name__ == "__main__":
    unittest.main()
