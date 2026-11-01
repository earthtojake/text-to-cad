"""A skill that runs the server runs it by the `cad` command, and says how to get it in one block, the
same in each.

The server is installed by one command (the install command, which runs `cad setup` through uvx:
cad_server._internal.launch), and that installation registers itself and writes the `cad` command,
`~/.local/bin/cad` (cad_server._internal.installations), which every skill runs -- uvx cannot start in
an agent's sandbox, the command can. The command runs the device's current installation whatever
release a skill came with, so a skill names no release. One installation, so one warm engine. A skill
that runs the server any other way -- a `pip install -r requirements.txt` into the project's
interpreter -- makes a second installation with an engine of its own, and its docs may describe a
release that is not the one running.

Stated as a criterion rather than a list: "uses the server" is what the skill's docs TEACH (a `cad`
command in a code block) or what its own Python imports. Skills that never touch it (bambu-labs,
dfam-check, dfm, gcode, sendcutsend, step-parts) carry no setup block; a `cad export` such a skill
mentions in its prose is how a text-to-cad model's file was made, not a command it runs.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILLS = sorted(p for p in (REPO_ROOT / "skills").iterdir() if p.is_dir())

SETUP = """Run the `cad` command (`~/.local/bin/cad` where `~/.local/bin` is not on your PATH, or where a
project's environment puts its own `cad` first; `cad.cmd` on Windows). If `cad` is not found and
the CAD app was only just added, its server may still be starting: run the command again in a few
seconds. Otherwise install text-to-cad, outside a sandbox or with its permission:

```bash
{install}
```

On Windows, in PowerShell: `{install_windows}`. Any other failure
says what to do, and `cad doctor` explains the installation.
"""

_IMPORT = re.compile(r"^\s*(?:from|import)\s+(?:cad|cadgen|cad_server)\b", re.M)
_INVOCATION = re.compile(r"(?:^|[`\s])cad(?:\.cmd)?\s+[a-z]", re.M)
_FENCE = re.compile(r"^ *```[^\n]*\n(.*?)^ *```", re.M | re.S)


def _docs(skill: Path) -> list[Path]:
    return sorted(path for path in skill.rglob("*.md") if "__pycache__" not in path.parts)


def _teaches_the_server(skill: Path) -> bool:
    """The skill's docs run the `cad` command in a code block, or its code imports the library."""
    imports = any(_IMPORT.search(path.read_text(encoding="utf-8"))
                  for path in skill.rglob("*.py") if "__pycache__" not in path.parts)
    fenced = "\n".join(block for path in _docs(skill) for block in _FENCE.findall(path.read_text(encoding="utf-8")))
    return imports or bool(_INVOCATION.search(fenced))


class SkillLaunchCommand(unittest.TestCase):
    def test_skills_were_found(self) -> None:
        self.assertGreaterEqual(len(SKILLS), 8, "the skills/ glob found almost nothing")

    def test_every_skill_that_uses_the_server_says_how_to_get_the_cad_command(self) -> None:
        from tests.python.support.paths import add_sources

        add_sources()
        from cad_server.updates import INSTALL, INSTALL_WINDOWS

        setup = SETUP.format(install=INSTALL, install_windows=INSTALL_WINDOWS)
        users = []
        for skill in SKILLS:
            text = (skill / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(skill=skill.name):
                self.assertFalse((skill / "references" / "setup.md").exists(), "the setup block is the guide")
                for path in _docs(skill):
                    docs = path.read_text(encoding="utf-8")
                    # A skill names no release: the `cad` command runs the current installation.
                    self.assertNotRegex(docs, r"\bcad(?:\.cmd)? \+", path)
                    self.assertNotIn("--from cad-server==", docs, path)
                if _teaches_the_server(skill):
                    users.append(skill.name)
                    self.assertIn(setup, text)
                else:
                    self.assertNotIn(INSTALL, text, "a skill that never runs the server installs nothing")
        self.assertGreater(len(users), 1, "found no skill that runs the server: the criterion no longer matches")

    def test_no_skill_installs_the_library_or_the_server_any_other_way(self) -> None:
        # A requirements.txt naming either is a second installation, with an engine of its own.
        for skill in SKILLS:
            manifest = skill / "requirements.txt"
            with self.subTest(skill=skill.name):
                if manifest.is_file():
                    lines = [line.split("#")[0].strip() for line in manifest.read_text(encoding="utf-8").splitlines()]
                    names = {re.sub(r"[-_.]+", "-", re.match(r"[A-Za-z0-9._-]*", line).group(0)).lower() for line in lines}
                    # text-to-cad is the product's name, unpublished: a requirement on it would install whatever claims it.
                    self.assertFalse(names & {"cad", "cad-server", "cad-mcp", "cadgen", "text-to-cad"}, manifest)


if __name__ == "__main__":
    unittest.main()
