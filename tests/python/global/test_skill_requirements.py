"""A skill that runs the server runs it by the `cad` command, pinned to its release, and says how to get
it in one block, the same in each.

The `cad` command, `~/.local/bin/cad`, is written by `cad setup`, which the skill's own line runs through
uvx (`--from cad-server==<VERSION> cad setup`); every skill runs the command -- uvx cannot start in an
agent's sandbox, the command can. Every command a skill runs names the skill's release first, `cad +<VERSION>
<verb>`, so the skill text of a release runs that release's software and no other; the release stamps the
pin (scripts/release/sync-version.mjs) and test_skill_commands_pin_their_release.py holds every command to
it. The setup block says what the pin does and how to install that release when the command says it is not
installed; our own text (main, `latest`) adds the update paragraph between two markers, which a store's copy
leaves out (scripts/release/channel_stamp.py), and every copy ends the block with the migration guides' link.
A skill that runs the server any other way -- a `pip install -r requirements.txt` into the project's
interpreter -- makes a second installation, and its docs may describe a release that is not the one running.

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
SETUP = """Every command in this skill starts `cad +{X}`: it runs cad {X}, the version this skill was written for,
and never another. Run it as written (`~/.local/bin/cad` where `cad` is not on your PATH; `cad.exe`
on Windows).

If `cad` is missing, or says {X} is not installed, install it, outside the sandbox, then run the
command again:

```bash
uvx --no-config --managed-python --python 3.14 --from cad-server=={X} cad setup
```

It installs cad {X} and the `cad` command and changes nothing else. If `uvx` is missing, install uv
first.

<!-- manual-copy-update: start -->
Keep this install up to date: nothing updates it but you.

1. At the start of a session, run `cad +{X} --version`.
2. If it, or any `cad` command later, says a new version of cad is available, install the new version of
   the plugin from https://github.com/earthtojake/text-to-cad.

Then tell the person it was updated and that a new chat will use the new version, and carry on with
this chat: its commands keep working.
<!-- manual-copy-update: end -->

A project written for an earlier text-to-cad may need changes. The migration guides say what, one per
version: https://github.com/earthtojake/text-to-cad/tree/main/docs/migrations
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
        setup = SETUP.format(X=VERSION)
        users = []
        for skill in SKILLS:
            text = (skill / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(skill=skill.name):
                self.assertFalse((skill / "references" / "setup.md").exists(), "the setup block is the guide")
                for path in _docs(skill):
                    docs = path.read_text(encoding="utf-8")
                    # The setup block's line is the one place a skill runs the server through uvx: every command
                    # runs `cad`, pinned.
                    self.assertEqual(docs.count("--from cad-server=="), int(path == skill / "SKILL.md"), path)
                if _teaches_the_server(skill):
                    users.append(skill.name)
                    self.assertEqual(text.count(setup), 1)
                else:
                    self.assertNotIn("cad setup", text, "a skill that never runs the server installs nothing")
        self.assertGreater(len(users), 1, "found no skill that runs the server: the criterion no longer matches")

    def test_no_skill_names_what_the_software_no_longer_has(self) -> None:
        # No updater, no plugin command, no exit codes a pin once added, no repair of apps: what a skill says to run
        # is a command of its own release.
        gone = re.compile(r"cad(?:\.exe)? (?:\+\S+ )?(?:update|plugin)\b|doctor --prune|--add \d|exit code says why")
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
