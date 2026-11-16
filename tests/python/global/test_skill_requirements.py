"""A skill that runs the server runs it by the plain `cad` command, and says how to get it in one block, the
same in each.

The block names the cad the skills were written for once, as `cad==<VERSION>`, which the release stamps
(scripts/release/sync-version.mjs); no command carries a version. It has the agent check `cad --version`
on first use, install or update cad when it is missing or older, start the server when cad says it is not
running, and, in our own copies, update on the person's yes when cad says a newer version is out. A store's
copy gets the same block with the store's lines in place of the install script's (scripts/release/plugin_zip.py,
`store_copy`). A skill that runs the server any other way -- a `pip install -r requirements.txt` into the
project's interpreter -- makes a second installation.

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

# The owner's text, word for word (X is the release, stamped).
SETUP = """This skill was written for `cad=={X}`. The first time you use it in a chat, run `cad --version` in
the shell. Then:

- `cad` is not found: run the install line below, then carry on.
- It prints a version older than the one above: run the update line below, then carry on.
- It prints a version newer than the one above: carry on. This skill is older than cad.

Install line, on macOS and Linux:

```bash
curl -fsSL https://texttocad.dev/install.sh | sh
```

On Windows, in PowerShell:

```powershell
irm https://www.texttocad.dev/install.ps1 | iex
```

Update line, on macOS and Linux:

```bash
cad server stop && curl -fsSL https://texttocad.dev/install.sh | sh && cad server start
```

On Windows, in PowerShell:

```powershell
cad server stop; irm https://www.texttocad.dev/install.ps1 | iex; cad server start
```

When a `cad` command prints that:

- the cad server is not running: run `cad server start`, then run the command again.
- the command and the server are different versions: do what that line says.
- a newer version of cad is available: tell the person and ask whether to update. If they say yes, run
  the update line above.

Run models with `cad run`.

A project written for an earlier text-to-cad may need changes. The migration guides say what, one per
version: https://github.com/earthtojake/text-to-cad/tree/main/docs/migrations
"""

# What every skill pre-approves in Claude Code: its own `cad` commands and the store copies' one install line.
ALLOWED_TOOLS = ("allowed-tools: Bash(cad *) Bash(uv tool install --managed-python --python 3.14 cad==*) "
                 "Bash(uv --version)")

_IMPORT = re.compile(r"^\s*(?:from|import)\s+(?:cad|cadgen|cad_server)\b", re.M)
_INVOCATION = re.compile(r"(?:^|[`\s])cad(?:\.exe)?\s+[a-z]", re.M)
_FENCE = re.compile(r"^ *```[^\n]*\n(.*?)^ *```", re.M | re.S)
# A version of cad written into skill text: only `cad==X`, the form the release stamps.
_VERSIONED = re.compile(r"(?<![\w.-])cad(?:\.exe)?(?: \+|==|@)(\d[^\s`'\")]*)")


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
        setup = SETUP.format(X=VERSION)
        users = []
        for skill in SKILLS:
            text = (skill / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(skill=skill.name):
                self.assertFalse((skill / "references" / "setup.md").exists(), "the setup block is the guide")
                if _teaches_the_server(skill):
                    users.append(skill.name)
                    self.assertEqual(text.count(setup), 1)
                else:
                    self.assertNotIn("install.sh", text, "a skill that never runs the server installs nothing")
        self.assertGreater(len(users), 1, "found no skill that runs the server: the criterion no longer matches")

    def test_every_skill_pre_approves_its_cad_commands(self) -> None:
        for skill in SKILLS:
            head = (skill / "SKILL.md").read_text(encoding="utf-8").split("\n---\n", 1)[0]
            with self.subTest(skill=skill.name):
                self.assertEqual(head.splitlines().count(ALLOWED_TOOLS), 1)

    def test_no_command_names_a_version(self) -> None:
        # Commands are plain `cad <verb>`; the one version is the setup block's `cad==X`, the release's.
        for skill in SKILLS:
            for path in _docs(skill):
                with self.subTest(path=str(path.relative_to(REPO_ROOT))):
                    text = path.read_text(encoding="utf-8")
                    self.assertNotIn("cad +", text)
                    self.assertEqual({found[0] for found in _VERSIONED.finditer(text)} - {f"cad=={VERSION}"}, set(),
                                     "run node scripts/release/sync-version.mjs to stamp VERSION")

    def test_no_skill_names_what_the_software_no_longer_has(self) -> None:
        # No updater, no plugin command, no setup command, no exit codes a pin once added, no repair of apps.
        gone = re.compile(r"cad(?:\.exe)? (?:update|plugin|setup)\b|doctor --prune|--add \d|exit code says why"
                          r"|\.local/bin/cad|unknown command '\+")
        for skill in SKILLS:
            for path in _docs(skill):
                with self.subTest(path=str(path.relative_to(REPO_ROOT))):
                    self.assertIsNone(gone.search(path.read_text(encoding="utf-8")))

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
