"""A skill that runs the server runs it by the plain `cad` command, and says how to get it in one block, the
same in each.

The block names the cad the skills were written for once, as `cad==<VERSION>`, which the release stamps
(scripts/release/sync-version.mjs); no command and no install line carries a version. It has the agent check
`cad --version` on first use; install cad where it is missing; where it is older, `cad update`, which has the
running server install the newest release with no permission asked, and install only where it is still older;
carry on where cad is newer, since cad updates itself ahead of a store's copy of the skills; and start the server
when cad says it is not running. Nothing in it asks the person whether to update: the app's own prompt for
a command is the only asking. A store's copy gets the same block with the store's install line in place of the
install script's (scripts/release/plugin_zip.py, `store_copy`). A skill that runs the server any other way -- a
`pip install -r requirements.txt` into the project's interpreter -- makes a second installation.

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
SETUP = """This skill was written for `cad=={X}`. The first time you use it in a chat, before you write or build
anything, run `cad --version` as a command by itself and read what it prints. Then:

- `cad` is not found: run the install line below.
- A version older than the one above: run `cad update`, then `cad --version` again. If it is still
  older, run `cad server stop`, then the install line below, then `cad server start`.
- The version above or a newer one: go on.

Install line, on macOS and Linux:

```bash
curl -fsSL https://texttocad.dev/install.sh | sh
```

On Windows, in PowerShell:

```powershell
irm https://www.texttocad.dev/install.ps1 | iex
```

When a `cad` command prints that the cad server is not running, run `cad server start`, then run the
command again.

Run models with `cad run`. Run each `cad` command by itself, not joined to others by `;`, `&&` or a pipe.

A project written for an earlier text-to-cad may need changes. The migration guides say what, one per
version: https://github.com/earthtojake/text-to-cad/tree/main/docs/migrations
"""

# What every skill pre-approves in Claude Code: the `cad` commands it runs, the setup block's among them, and
# nothing else. The install line is not: ours is a download run by a shell (a rule for it would allow any script),
# and the store copies' uv line runs where the line is ignored (Codex) or refused (claude.ai's directory, whose
# copy carries no `allowed-tools`: scripts/release/plugin_branch.py).
ALLOWED_TOOLS = "allowed-tools: Bash(cad *)"

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
        # No plugin command, no setup command, no exit codes a pin once added, no repair of apps, no newer-version
        # notice and no asking the person whether to update (cad updates itself, and `cad update` asks nobody), and
        # nothing that claims a permission (agents refused the commands it named).
        gone = re.compile(r"cad(?:\.exe)? (?:plugin|setup)\b|doctor --prune|--add \d|exit code says why"
                          r"|\.local/bin/cad|unknown command '\+|newer version of cad is available"
                          r"|ask whether to update|without asking", re.I)
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
