"""A skill that runs the server must run its version by the `cad` command, and name its install command,
pinned to this release.

The server is one command, `uvx --no-config --managed-python --python 3.14 --from cad-server==<release> cad`
(cad_server._internal.launch): uv keeps one installation per requirement, and that installation
registers itself and writes the `cad` command, `~/.local/bin/cad`
(cad_server._internal.installations), which every skill runs as `cad +<release>` -- uvx cannot start
in an agent's sandbox, the command can. One installation, so one warm engine. A skill
defines that command in its SKILL.md and names the uvx command once, in its setup guide
(`references/setup.md`, which the SKILL.md links), as `cad doctor`, which installs the server,
registers it and writes the command when they are missing; the guide gives the install command
too, which sets text-to-cad up in every agent app. A skill that runs the server any other way -- a `pip install -r
requirements.txt` into the project's interpreter -- makes a second installation with an engine of
its own, and its docs may describe a release that is not the one running.

Stated as a criterion rather than a list, as before: "uses the server" is what the skill's docs
TEACH (`cad ...`) or what its own Python imports. Skills that never touch it
(bambu-labs, dfam-check, gcode, sendcutsend, step-parts) carry no launch command, and a
mention on a line that hands off to another skill (`$cad: cad export ...`) is that
skill's command, not this one's.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILLS = sorted(p for p in (REPO_ROOT / "skills").iterdir() if p.is_dir())

VERSION = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
LAUNCH = "uvx --no-config --managed-python --python 3.14 --from cad-server=={version} {tool}"
DEFINITIONS = ("- `cad` below means `cad +{version}` (`~/.local/bin/cad +{version}` where "
               "`~/.local/bin` is not on your PATH)\n- `python` below means `cad +{version} run`\n")
INSTALL = ("If `cad` is not on your PATH, or it says {version} is not installed, run\n"
           "`{command}` once,\noutside any sandbox or with its permission: it installs the server, registers it, "
           "writes the\n`cad` command, makes the CAD kernel environment models run in and starts the server.\n"
           "With the CAD app running, nothing else needs the sandbox's permission: it starts the\n"
           "server and holds it. Without it, a sandboxed shell cannot start the server; when a\n"
           "command says no engine server is running, run `cad server` outside the sandbox once.\n")


_HANDOFF_MARKER = re.compile(r"\$(?P<name>[a-z0-9-]+)")


def _own_lines(skill: Path, text: str) -> str:
    """Drop lines that route the agent to ANOTHER skill (`$cad`, `$dxf`, ...).

    A remediation line like "export an STL with $cad: `cad export ...`"
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


_IMPORT = re.compile(r"^\s*(?:from|import)\s+(?:cad|cadgen|cad_server)\b", re.M)


def _imports_the_library(skill: Path) -> bool:
    return any(
        _IMPORT.search(_own_lines(skill, path.read_text(encoding="utf-8")))
        for path in skill.rglob("*.py")
        if "__pycache__" not in path.parts
    )


_INVOCATION = re.compile(r"(?:^|[`\s])cad(?:\.cmd)?\s+(?:\+|[a-z])", re.M)


def _docs_text(skill: Path) -> str:
    return "\n".join(
        _own_lines(skill, path.read_text(encoding="utf-8"))
        for path in skill.rglob("*.md")
        if "__pycache__" not in path.parts
    )


def _teaches_the_server(skill: Path) -> bool:
    """The skill's docs instruct the agent to run the `cad` command (or its code imports the library)."""
    return _imports_the_library(skill) or bool(_INVOCATION.search(_docs_text(skill)))


class SkillLaunchCommand(unittest.TestCase):
    def test_skills_were_found(self) -> None:
        self.assertGreaterEqual(len(SKILLS), 8, "the skills/ glob found almost nothing")

    def test_every_skill_that_uses_the_server_names_its_version_and_install_command(self) -> None:
        import sys

        from tests.python.support.paths import add_sources

        add_sources()
        from cad_server.updates import INSTALL as INSTALL_COMMAND, INSTALL_WINDOWS

        for skill in SKILLS:
            text = (skill / "SKILL.md").read_text(encoding="utf-8")
            setup = skill / "references" / "setup.md"
            with self.subTest(skill=skill.name):
                if not _teaches_the_server(skill):
                    self.assertNotIn("--from cad-server==", text, "a skill that never runs the server downloads nothing")
                    self.assertFalse(setup.exists(), "a skill that never runs the server has no setup guide")
                    continue
                self.assertIn(DEFINITIONS.format(version=VERSION), text)
                self.assertIn("](references/setup.md)", text)
                guide = setup.read_text(encoding="utf-8")
                self.assertIn(INSTALL.format(version=VERSION, command=LAUNCH.format(version=VERSION, tool="cad doctor")),
                              guide)
                self.assertIn(f"```bash\n{INSTALL_COMMAND}\n```", guide)
                self.assertIn(f"`{INSTALL_WINDOWS}`", guide)

    def test_no_skill_installs_the_library_or_the_server_any_other_way(self) -> None:
        # A requirements.txt naming either is a second installation, with an engine of its own.
        for skill in SKILLS:
            manifest = skill / "requirements.txt"
            with self.subTest(skill=skill.name):
                if manifest.is_file():
                    lines = [line.split("#")[0].strip() for line in manifest.read_text(encoding="utf-8").splitlines()]
                    names = {re.sub(r"[-_.]+", "-", re.match(r"[A-Za-z0-9._-]*", line).group(0)).lower() for line in lines}
                    self.assertFalse(names & {"cad", "cad-server", "cad-mcp", "cadgen", "text-to-cad"}, manifest)

    def test_the_launch_command_and_the_refusal_are_the_servers_own(self) -> None:
        import os
        import subprocess
        import sys
        import tempfile

        from tests.python.support.paths import add_sources

        add_sources()
        from cad_server._internal import installations
        from cad_server._internal.launch import launch_command, pinned

        self.assertEqual(launch_command("python", VERSION), LAUNCH.format(version=VERSION, tool="python"))
        self.assertEqual(pinned(VERSION), f"cad +{VERSION}")
        if os.name == "nt":
            return  # the cmd says it with no version; the sh below is the skills' wording
        # The line the skills tell the agent to act on is the one the command says, with none installed.
        with tempfile.TemporaryDirectory() as scratch:
            where = os.path.join(scratch, "bin")
            installations.write_proxy(where, windows=False)
            said = subprocess.run([installations.proxy_path(where, windows=False), f"+{VERSION}", "status"],
                                  capture_output=True, text=True,
                                  env={"PATH": os.environ.get("PATH", ""), "HOME": scratch,
                                       "CAD_STATE_DIR": os.path.join(scratch, "state")}).stderr
        self.assertIn(f"{VERSION} is not installed", said)
        self.assertIn(LAUNCH.format(version=VERSION, tool="cad doctor"), said)

if __name__ == "__main__":
    unittest.main()
