"""A skill that runs the server runs it by the `cad` command, pinned to its release, and says how to get
it in one block, the same in each.

The server is installed by one command (the install command, which runs `cad setup` through uvx:
cad_server._internal.launch), and that installation writes the `cad` command, `~/.local/bin/cad`
(cad_server._internal.installations), which every skill runs -- uvx cannot start in an agent's
sandbox, the command can. Every command a skill runs names the skill's release first, `cad +<VERSION>
<verb>`, so the skill text of a release runs that release's software and no other; the release
stamps the pin (scripts/release/sync-version.mjs) and test_skill_commands_pin_their_release.py holds
every command to it. The setup block says what the pin does, how to install that release when the
command cannot, and what the exit codes a pin adds (3, 4, 5) mean. A skill that runs the server any other way -- a `pip install -r requirements.txt` into
the project's interpreter -- makes a second installation, and its docs may describe a release that is
not the one running.

Stated as a criterion rather than a list: "uses the server" is what the skill's docs TEACH (a `cad`
command in a code block) or what its own Python imports. A skill that never touches it carries no
setup block (every skill runs it today).
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILLS = sorted(p for p in (REPO_ROOT / "skills").iterdir() if p.is_dir())
VERSION = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()

SETUP = """Every command in this skill starts `cad +{X}`: it runs text-to-cad {X}, the release this skill was
written for, and never another. Run it as written (`~/.local/bin/cad` where `cad` is not on your
PATH; `cad.exe` on Windows). The first command after a new release installs it, once.

If `cad` is missing, or says it does not know `+{X}` (an older text-to-cad), install this release,
outside the sandbox or with its permission, then run the command again:

```bash
{install} -s -- --add {X}
```

On Windows, in PowerShell: `& ([scriptblock]::Create((irm {install_windows_script}))) --add {X}`.
It installs {X} and the `cad` command and changes nothing else.

When a command fails, its exit code says why:

- 3: it could not install or switch to {X} from this shell. Do what it says, outside
  the sandbox or with its permission, then run the command again.
- 4: this copy of the skill is older than the text-to-cad its channel is on now. Read the skill again;
  if it still names the same release, this app's copy of the text-to-cad plugin is out of date: run
  cad update (with no pin), or, where the copy came from an app's plugin store, update it there; then start
  a new chat.
- 5: the `cad` this shell found is not the `cad` command but another copy of text-to-cad. Run
  `~/.local/bin/cad` (`%USERPROFILE%\\.local\\bin\\cad.exe` on Windows) instead.

`cad +{X} doctor --check` explains any other failure, changing nothing; `cad +{X} doctor` repairs what
it reports. Tell the person any next step it prints.
"""

_IMPORT = re.compile(r"^\s*(?:from|import)\s+(?:cad|cadgen|cad_server)\b", re.M)
_INVOCATION = re.compile(r"(?:^|[`\s])cad(?:\.exe)?\s+(?:\+\S+\s+)?[a-z]", re.M)
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
        self.assertGreaterEqual(len(SKILLS), 6, "the skills/ glob found almost nothing")

    def test_every_skill_that_uses_the_server_says_how_to_get_the_cad_command(self) -> None:
        from tests.python.support.paths import add_sources

        add_sources()
        from cad_server.updates import INSTALL, INSTALL_WINDOWS

        # The Windows one-liner pipes the script to iex, which takes no arguments: the block runs it as a
        # script block instead, with `--add`.
        script = INSTALL_WINDOWS.removeprefix("irm ").removesuffix(" | iex")
        self.assertEqual(f"irm {script} | iex", INSTALL_WINDOWS)
        setup = SETUP.format(X=VERSION, install=INSTALL, install_windows_script=script)
        users = []
        for skill in SKILLS:
            text = (skill / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(skill=skill.name):
                self.assertFalse((skill / "references" / "setup.md").exists(), "the setup block is the guide")
                for path in _docs(skill):
                    docs = path.read_text(encoding="utf-8")
                    # A skill pins its release in its commands, never by running the server through uvx.
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
