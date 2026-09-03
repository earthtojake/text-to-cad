"""A skill that runs cadgen must say so, with the extras it actually reaches.

`requirements.txt` is not documentation: `scripts/release/pin-cadgen-requirements.sh`
rewrites it to `cadgen==<release>` at publish, and it is what an installed skill's
`pip install -r requirements.txt` resolves. A skill that imports cadgen without declaring
it installs nothing and fails at first use; one that renders without the `snapshot` extra
installs fine and then dies inside the headless browser with a playwright ImportError,
which reads as a rendering bug rather than a missing dependency.

Both stated as criteria rather than lists. A skill shipped for months with no manifest
at all, and dxf gained a snapshot command without gaining the extra -- neither was caught,
because nothing derived the expectation from what the skill actually does.

The skills are instruction-only now (the per-verb shims are gone), so "what the skill
does" is what its documentation TEACHES: a skill whose docs invoke `cadgen ...` (or
whose remaining Python imports cadgen) must declare it, and one that teaches a snapshot
verb needs the `snapshot` extra. Skills that never touch cadgen (bambu-labs, dfam-check,
gcode, sendcutsend, step-parts) correctly have no cadgen line — a mention on a line that
hands off to another skill (`$cad: cadgen stl build ...`) is that skill's command, not a
dependency here.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILLS = sorted(p for p in (REPO_ROOT / "skills").iterdir() if p.is_dir())

# `cadgen`, `cadgen[snapshot]`, or either pinned -- main carries the pinned form.
_CADGEN_LINE = re.compile(r"^cadgen(?:\[(?P<extras>[a-z0-9_,.-]+)\])?\s*(?:==\s*\S+)?\s*$")


def _declared(skill: Path) -> tuple[bool, set[str]]:
    """(declares cadgen, extras it asks for) from the skill's requirements.txt."""
    manifest = skill / "requirements.txt"
    if not manifest.is_file():
        return False, set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        match = _CADGEN_LINE.match(line.strip())
        if match:
            return True, set((match.group("extras") or "").split(",")) - {""}
    return False, set()


_HANDOFF_MARKER = re.compile(r"\$(?P<name>[a-z0-9-]+)")


def _own_lines(skill: Path, text: str) -> str:
    """Drop lines that route the agent to ANOTHER skill (`$cad`, `$dxf`, ...).

    A remediation line like "export an STL with $cad: `cadgen stl build ...`"
    teaches the CAD skill's command, not a dependency of the skill that says it
    — that skill installs nothing and runs nothing; the named skill's own
    requirements cover the command.
    """
    kept = []
    for line in text.splitlines():
        markers = {m.group("name") for m in _HANDOFF_MARKER.finditer(line)}
        if markers and skill.name not in markers:
            continue
        kept.append(line)
    return "\n".join(kept)


def _imports_cadgen(skill: Path) -> bool:
    return any(
        "cadgen" in _own_lines(skill, path.read_text(encoding="utf-8"))
        for path in skill.rglob("*.py")
        if "__pycache__" not in path.parts
    )


_CADGEN_INVOCATION = re.compile(r"(?:^|[`\s])cadgen\s+[a-z]", re.M)
_SNAPSHOT_INVOCATION = re.compile(r"cadgen\s+(?:(?:step|dxf)\s+)?snapshot\b")


def _docs_text(skill: Path) -> str:
    return "\n".join(
        _own_lines(skill, path.read_text(encoding="utf-8"))
        for path in skill.rglob("*.md")
        if "__pycache__" not in path.parts
    )


def _teaches_cadgen(skill: Path) -> bool:
    """The skill's docs instruct the agent to run the cadgen CLI (or its code imports it)."""
    return _imports_cadgen(skill) or bool(_CADGEN_INVOCATION.search(_docs_text(skill)))


def _teaches_snapshot(skill: Path) -> bool:
    return bool(_SNAPSHOT_INVOCATION.search(_docs_text(skill)))


class SkillRequirements(unittest.TestCase):
    def test_skills_were_found(self) -> None:
        self.assertGreaterEqual(len(SKILLS), 8, "the skills/ glob found almost nothing")

    def test_every_skill_that_uses_cadgen_declares_it(self) -> None:
        missing = [s.name for s in SKILLS if _teaches_cadgen(s) and not _declared(s)[0]]
        self.assertEqual(
            missing,
            [],
            "these skills teach or import cadgen but do not name it in requirements.txt, "
            "so `pip install -r requirements.txt` installs nothing they need",
        )

    def test_every_rendering_skill_asks_for_the_snapshot_extra(self) -> None:
        """A skill that teaches a snapshot verb reaches the headless browser renderer.

        Playwright is an extra rather than a base dependency because it is a large install
        plus a browser download, so a skill that renders has to opt in explicitly.
        """
        for skill in SKILLS:
            if not _teaches_snapshot(skill):
                continue
            with self.subTest(skill=skill.name):
                declares, extras = _declared(skill)
                self.assertTrue(declares, f"{skill.name} renders but declares no cadgen")
                self.assertIn(
                    "snapshot",
                    extras,
                    f"{skill.name} teaches a cadgen snapshot verb; it needs "
                    "cadgen[snapshot] or its renders die on a playwright ImportError",
                )

    def test_a_declared_extra_is_one_cadgen_actually_offers(self) -> None:
        """Guards the reverse typo: cadgen[snapshots] installs no extra and never warns."""
        pyproject = (REPO_ROOT / "packages" / "cadgen" / "pyproject.toml").read_text(encoding="utf-8")
        block = pyproject.split("[project.optional-dependencies]", 1)[1].split("\n[", 1)[0]
        available = set(re.findall(r"^([a-z0-9_-]+)\s*=", block, re.M))
        self.assertIn("snapshot", available, "cadgen no longer defines a snapshot extra")
        for skill in SKILLS:
            extras = _declared(skill)[1]
            with self.subTest(skill=skill.name):
                self.assertTrue(
                    extras <= available,
                    f"{skill.name} asks for {sorted(extras - available)}, which cadgen does not define",
                )


if __name__ == "__main__":
    unittest.main()
