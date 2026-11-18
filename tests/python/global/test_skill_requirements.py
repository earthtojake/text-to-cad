"""A skill that runs the server runs it by the plain `cad` command, and says how to get it in one block, the
same in each.

The block names the cad the skills were written for once, as `cad==<VERSION>`, which the release stamps
(scripts/release/sync-version.mjs); no command and no install line carries a version. 0.11.12 in its first sentence
is fixed, not stamped: the first release installed globally by uv. It has the agent run `cad --version` before
first use, and install cad by uv's one line, `uv tool install cad`, where it is missing or older than 0.11.12
(0.10.0 to 0.11.11 are a launcher, not a global install, and `--force` replaces its file). cad updates itself, so
the block never has the agent update it: where cad is a major or minor version newer than the skill and something
fails, the agent tells the person to update the plugin, whose skills are then the older half (docs/install.md,
"Updating"). No skill runs our install script: that is how a
person installs the plugins, and a skill installs only cad. A `cad` command that needs the server and finds none
says to run `cad server start`. Nothing in the block asks the person whether to update. Every published copy of
the skills (`latest`, claude.ai's directory's, Codex's) holds the skills byte for byte
(scripts/release/plugin_branch.py), so no skill pre-approves a tool (`allowed-tools`): the directory refuses one
from an organization it has not verified. A skill that runs the server any other way -- a
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
SETUP = """Written for `cad=={X}`. Before first use in a chat, run `cad --version`. If `cad` is missing or older than
0.11.12, run `uv tool install cad`, adding `--force` if uv says `cad` already exists.

If cad is a major or minor version newer than this skill, tell the person to update the text-to-cad plugin:
https://github.com/earthtojake/text-to-cad
A project written for an earlier version may need changes; the migration guides say what:
https://github.com/earthtojake/text-to-cad/tree/main/docs/migrations
"""

# A key in a SKILL.md's front matter that pre-approves tools, in either spelling.
_PRE_APPROVAL = re.compile(r"^(?:allowed-tools|allowedTools)[ \t]*:", re.M)

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

    def test_no_skill_pre_approves_a_tool(self) -> None:
        # Every copy carries the skills as they are here, and claude.ai's directory refuses `allowed-tools` from an
        # organization it has not verified; each `cad` command is the app's to ask about, as any other.
        for skill in SKILLS:
            head = (skill / "SKILL.md").read_text(encoding="utf-8").split("\n---\n", 1)[0]
            with self.subTest(skill=skill.name):
                self.assertIsNone(_PRE_APPROVAL.search(head))

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
        # No plugin command and no setup command (plugins are the person's install script's, never a skill's), no
        # install script (a skill installs cad by uv's line alone), no switching cad's automatic update (on by
        # default), no exit codes a pin once added, no repair of apps, no newer-version notice and no asking the
        # person whether to update (cad updates itself, and `cad update` asks nobody), and nothing that claims a
        # permission (agents refused the commands it named).
        # The commands, not the product's name: "the text-to-cad plugin" is the block's own words.
        gone = re.compile(r"(?<![\w.-])cad(?:\.exe)? (?:plugin|setup|update auto)\b|texttocad\.dev/install"
                          r"|doctor --prune|--add \d|exit code says why"
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
