"""A skill that runs cadgen must run its version by the `cadgen` command, and name its install command,
pinned to this release.

The CAD plugin's server is one command,
`uvx --no-config --managed-python --python 3.14 --from cadgen==<release> cadgen mcp`
(cadgen._internal.launch): uv keeps one installation per requirement, and that installation
registers itself and writes the `cadgen` command, `~/.local/bin/cadgen`
(cadgen._internal.installations), which every skill runs as `cadgen +<release>` -- uvx cannot start
in an agent's sandbox, the command can. The same installation, so the same warm daemon. A skill
defines that command in its SKILL.md and names the uvx command once, in its setup guide
(`references/setup.md`, which the SKILL.md links), as `cadgen doctor`, which installs cadgen,
registers it and writes the command when they are missing; the guide gives the install command
too, which sets text-to-cad up in every agent app. A skill that runs cadgen any other way -- a `pip install -r
requirements.txt` into the project's interpreter -- makes a second installation with a daemon of
its own, and its docs may describe a cadgen that is not the one running.

Stated as a criterion rather than a list, as before: "uses cadgen" is what the skill's docs
TEACH (`cadgen ...`) or what its own Python imports. Skills that never touch cadgen
(bambu-labs, dfam-check, gcode, sendcutsend, step-parts) carry no launch command, and a
mention on a line that hands off to another skill (`$cad: cadgen stl build ...`) is that
skill's command, not this one's.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILLS = sorted(p for p in (REPO_ROOT / "skills").iterdir() if p.is_dir())

VERSION = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
LAUNCH = "uvx --no-config --managed-python --python 3.14 --from cadgen=={version} {tool}"
DEFINITIONS = ("- `cadgen` below means `cadgen +{version}` (`~/.local/bin/cadgen +{version}` where "
               "`~/.local/bin` is not on your PATH)\n- `python` below means `cadgen +{version} run`\n")
INSTALL = ("If `cadgen` is not on your PATH, or it says {version} is not installed, run\n"
           "`{command}` once,\noutside any sandbox or with its permission: it installs cadgen, registers it, "
           "writes the\n`cadgen` command, makes the CAD kernel environment models run in and starts the engine.\n"
           "With the CAD app's server running, nothing else needs the sandbox's permission: it starts\n"
           "the engine and holds it. Without it, a sandboxed shell cannot start the engine; when a\n"
           "command says no engine is running, run `cadgen server` outside the sandbox once.\n")


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


def _docs_text(skill: Path) -> str:
    return "\n".join(
        _own_lines(skill, path.read_text(encoding="utf-8"))
        for path in skill.rglob("*.md")
        if "__pycache__" not in path.parts
    )


def _teaches_cadgen(skill: Path) -> bool:
    """The skill's docs instruct the agent to run the cadgen CLI (or its code imports it)."""
    return _imports_cadgen(skill) or bool(_CADGEN_INVOCATION.search(_docs_text(skill)))


class SkillLaunchCommand(unittest.TestCase):
    def test_skills_were_found(self) -> None:
        self.assertGreaterEqual(len(SKILLS), 8, "the skills/ glob found almost nothing")

    def test_every_skill_that_uses_cadgen_names_its_version_and_install_command(self) -> None:
        import sys

        sys.path.insert(0, str(REPO_ROOT / "packages" / "cadgen" / "src"))
        from cadgen.updates import INSTALL as INSTALL_COMMAND, INSTALL_WINDOWS

        for skill in SKILLS:
            text = (skill / "SKILL.md").read_text(encoding="utf-8")
            setup = skill / "references" / "setup.md"
            with self.subTest(skill=skill.name):
                if not _teaches_cadgen(skill):
                    self.assertNotIn("--from cadgen==", text, "a skill that never runs cadgen downloads nothing")
                    self.assertFalse(setup.exists(), "a skill that never runs cadgen has no setup guide")
                    continue
                self.assertIn(DEFINITIONS.format(version=VERSION), text)
                self.assertIn("](references/setup.md)", text)
                guide = setup.read_text(encoding="utf-8")
                self.assertIn(INSTALL.format(version=VERSION, command=LAUNCH.format(version=VERSION, tool="cadgen doctor")),
                              guide)
                self.assertIn(f"```bash\n{INSTALL_COMMAND}\n```", guide)
                self.assertIn(f"`{INSTALL_WINDOWS}`", guide)

    def test_no_skill_installs_cadgen_any_other_way(self) -> None:
        # A requirements.txt naming cadgen is a second installation, with a daemon of its own.
        for skill in SKILLS:
            manifest = skill / "requirements.txt"
            with self.subTest(skill=skill.name):
                if manifest.is_file():
                    lines = [line.split("#")[0].strip() for line in manifest.read_text(encoding="utf-8").splitlines()]
                    self.assertFalse([line for line in lines if line.startswith("cadgen")], manifest)

    def test_the_launch_command_and_the_refusal_are_cadgens_own(self) -> None:
        import sys

        sys.path.insert(0, str(REPO_ROOT / "packages" / "cadgen" / "src"))
        from cadgen._internal.launch import launch_command, pinned
        from cadgen._internal.proxy import NOT_INSTALLED

        self.assertEqual(launch_command("python", VERSION), LAUNCH.format(version=VERSION, tool="python"))
        self.assertEqual(pinned(VERSION), f"cadgen +{VERSION}")
        # The line the skills tell the agent to act on is the one the command says.
        self.assertIn(f"{VERSION} is not installed", NOT_INSTALLED.format(version=VERSION))
        self.assertIn(LAUNCH.format(version=VERSION, tool="cadgen doctor"), NOT_INSTALLED.format(version=VERSION))

if __name__ == "__main__":
    unittest.main()
