"""Viewer format-identity checks may only go DOWN.

The viewer renders every format through one shared component stack, but historically
gated every feature per format with identity checks (``renderFormat === RENDER_FORMAT.X``,
``isMeshRenderFormat(...)``, the ``xxxMode`` boolean piles). Each one is a place a new
format must be hand-added and a place an improvement fails to reach the other formats.
That is not hypothetical: the Orbit button was gated off for implicit and for DXF
independently and had to be fixed twice, and implicit grew a parallel export route to an
endpoint the server does not implement.

The fix is the capability registry (``packages/cadjs/src/lib/renderCapabilities.js``):
code asks *what a format can do*, not *what it is*. This test ratchets the old pattern
downward so it cannot grow back — without it the count creeps up again one feature at a
time and the unification silently rots.

If this test fails because you ADDED an identity check: use a capability instead. If you
genuinely removed some, lower the budget in the same commit.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CLIENT_ROOT = REPO_ROOT / "viewer" / "src" / "client"

# Every remaining identity check is a unification candidate. Lower these as phases land;
# never raise them.
MAX_RENDER_FORMAT_CHECKS = 34
MAX_FORMAT_PREDICATE_CALLS = 3

# Files allowed to know about concrete formats, because deciding *which* format an entry
# is, or loading it, is their whole job. Everything else must go through capabilities.
ALLOWLIST = {
    # The registry and the format enum themselves.
    "workbench/constants.js",
    # Per-format loaders: genuinely different work per format.
    "components/workbench/hooks/useCadAssets.js",
}

RENDER_FORMAT_MEMBER = re.compile(
    r"RENDER_FORMAT\.(?:STEP|STL|THREE_MF|GLB|DXF|IMPLICIT|URDF|SRDF|SDF)\b"
)
FORMAT_PREDICATE = re.compile(r"\b(?:isMeshRenderFormat|isRobotRenderFormat)\s*\(")


def _client_sources() -> list[Path]:
    paths: list[Path] = []
    for suffix in ("*.js", "*.jsx"):
        for path in CLIENT_ROOT.rglob(suffix):
            name = path.name
            if name.endswith((".test.js", ".test.jsx")):
                continue
            relative = path.relative_to(CLIENT_ROOT).as_posix()
            if relative in ALLOWLIST:
                continue
            paths.append(path)
    return sorted(paths)


def _count(pattern: re.Pattern[str]) -> tuple[int, dict[str, int]]:
    total = 0
    by_file: dict[str, int] = {}
    for path in _client_sources():
        hits = len(pattern.findall(path.read_text(encoding="utf-8")))
        if hits:
            by_file[path.relative_to(CLIENT_ROOT).as_posix()] = hits
            total += hits
    return total, by_file


class ViewerFormatCapabilityPolicyTest(unittest.TestCase):
    def test_render_format_identity_checks_do_not_grow(self) -> None:
        total, by_file = _count(RENDER_FORMAT_MEMBER)
        worst = sorted(by_file.items(), key=lambda item: -item[1])[:8]
        self.assertLessEqual(
            total,
            MAX_RENDER_FORMAT_CHECKS,
            "viewer client gained RENDER_FORMAT identity checks "
            f"({total} > {MAX_RENDER_FORMAT_CHECKS}). Gate on a capability from "
            "cadjs/lib/renderCapabilities instead of on the format's identity. "
            f"Heaviest files: {worst}",
        )

    def test_format_predicate_calls_do_not_grow(self) -> None:
        total, by_file = _count(FORMAT_PREDICATE)
        self.assertLessEqual(
            total,
            MAX_FORMAT_PREDICATE_CALLS,
            "viewer client gained isMeshRenderFormat/isRobotRenderFormat calls "
            f"({total} > {MAX_FORMAT_PREDICATE_CALLS}). These are format-identity tests; "
            f"use a capability instead. Files: {sorted(by_file.items())}",
        )

    def test_budgets_are_tight(self) -> None:
        """A budget far above the real count stops ratcheting anything."""
        render_total, _ = _count(RENDER_FORMAT_MEMBER)
        predicate_total, _ = _count(FORMAT_PREDICATE)
        self.assertGreaterEqual(
            render_total,
            MAX_RENDER_FORMAT_CHECKS - 10,
            "RENDER_FORMAT budget is stale — lower MAX_RENDER_FORMAT_CHECKS to "
            f"{render_total} to lock in the removals.",
        )
        self.assertGreaterEqual(
            predicate_total,
            MAX_FORMAT_PREDICATE_CALLS - 5,
            "predicate budget is stale — lower MAX_FORMAT_PREDICATE_CALLS to "
            f"{predicate_total} to lock in the removals.",
        )

    def test_shared_shell_components_are_capability_driven(self) -> None:
        """The three components every format flows through must stay identity-free.

        These are the shell: if they start branching on format identity again, every
        feature added to one format stops reaching the others.
        """
        for relative in (
            "components/workbench/FloatingToolBar.js",
            "components/workbench/CadRenderPane.js",
            # The renderer itself: it draws every format, so a format check here is a
            # feature one format gets and the others silently do not.
            "components/CadViewer.js",
            # Status, alerts and the file list: every one of these was a per-format
            # cascade, and each cascade was a place a new format inherited the wrong
            # advice, the wrong icon or no spinner at all.
            "workbench/viewerAlerts.js",
            "workbench/entryIconKind.js",
            "workbench/entryIconStatus.js",
            "components/workbench/CadWorkspaceHome.js",
        ):
            source = (CLIENT_ROOT / relative).read_text(encoding="utf-8")
            self.assertEqual(
                RENDER_FORMAT_MEMBER.findall(source),
                [],
                f"{relative} must gate on capabilities, not RENDER_FORMAT identity",
            )
            self.assertEqual(
                FORMAT_PREDICATE.findall(source),
                [],
                f"{relative} must gate on capabilities, not format predicates",
            )


if __name__ == "__main__":
    unittest.main()
