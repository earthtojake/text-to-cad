"""Every `cad` command a skill runs pins the skill's release: `cad +<VERSION> <verb> ...`.

The skill text of a release runs that release's software and no other, in every copy of the plugin
(the server's plugin folder, `latest`, claude.ai's directory, the Codex ZIP), so the pin is in the
source and the release stamps it (scripts/release/sync-version.mjs; check-version.sh asserts it).
An agent copies commands from code: every fenced block and inline code span under `skills/` is read,
tables included, and a `cad` followed by a word with no pin before it is an unpinned command --
placeholders such as `cad <type> inspect` too, which an agent fills in and runs.

Prose that names the command rather than running it holds no word after `cad` inside its span (the
`cad` command, `~/.local/bin/cad`, `cad.exe`), and the library is `cad.` or `cad[`, so neither
matches. What does match and is not a command is ALLOWED, each with its reason.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
VERSION = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()

_FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})[^\n]*\n(.*?)^[ \t]*\1[ \t]*$", re.M | re.S)
_SPAN = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)", re.S)
# `cad` standing alone ($cad is a skill's name, cad.step the library, my-cad another word), then a word.
_UNPINNED = re.compile(r"(?<![\w.$/+-])cad(?:\.exe)?[ \t]+(?!\+)[a-z<\[]")
_PIN = re.compile(r"(?<![\w.-])cad(?:\.exe)? \+(\S+?)(?=[\s`]|$)", re.M)

ALLOWED = {
    # The library imported in a Python block: `from cad import kicad_pcb`.
    r"\b(?:from|import)[ \t]+cad\b": "the Python library, not the command",
    # render's scene script: a Python comment saying where text-to-cad's model put each part.
    r"where cad placed it": "prose in a code comment about the model, not a command",
}


def code(text: str) -> list[str]:
    """Every fenced block's body and every inline code span outside them."""
    found, rest, start = [], [], 0
    for match in _FENCE.finditer(text):
        found.append(match.group(2))
        rest.append(text[start:match.start()])
        start = match.end()
    rest.append(text[start:])
    for chunk in rest:
        found.extend(span.group(2) for span in _SPAN.finditer(chunk) if "\n\n" not in span.group(2))
    return found


def unpinned(text: str) -> list[str]:
    """The lines of `text`'s code that run `cad` with no release pinned."""
    hits = []
    for body in code(text):
        allowed = [range(*m.span()) for pattern in ALLOWED for m in re.finditer(pattern, body)]
        for match in _UNPINNED.finditer(body):
            if any(match.start() in span for span in allowed):
                continue
            line_start = body.rfind("\n", 0, match.start()) + 1
            line_end = body.find("\n", match.end())
            hits.append(body[line_start:line_end if line_end >= 0 else None].strip())
    return hits


def pins(text: str) -> list[str]:
    return [match.group(1) for body in code(text) for match in _PIN.finditer(body)]


def _documents() -> list[Path]:
    return sorted(path for path in (REPO_ROOT / "skills").rglob("*.md") if "__pycache__" not in path.parts)


class SkillCommandsPinTheirRelease(unittest.TestCase):
    def test_no_skill_runs_an_unpinned_cad_command(self) -> None:
        documents = _documents()
        self.assertGreater(len(documents), 10, "the skills/ glob found almost nothing")
        for path in documents:
            with self.subTest(path=str(path.relative_to(REPO_ROOT))):
                self.assertEqual(unpinned(path.read_text(encoding="utf-8")), [],
                                 f"pin these to the skill's release: `cad +{VERSION} <verb>`")

    def test_every_pin_names_this_release(self) -> None:
        found = {}
        for path in _documents():
            for pin in pins(path.read_text(encoding="utf-8")):
                found.setdefault(pin, str(path.relative_to(REPO_ROOT)))
        self.assertIn(VERSION, found, "no skill pins its commands")
        self.assertEqual({pin: where for pin, where in found.items() if pin != VERSION}, {},
                         "run node scripts/release/sync-version.mjs to stamp VERSION")

    def test_the_check_finds_a_planted_unpinned_command(self) -> None:
        planted = (
            "Build it:\n\n```bash\ncad run src/part.py\n```\n\n"
            "| Task | Command |\n|---|---|\n| Look | `cad model snapshot \"$ID\" out.png` |\n\n"
            "Then `cad <type> inspect`, and `cad doctor\n--check` on a failure, on Windows `cad.exe stop`.\n"
        )
        self.assertEqual(unpinned(planted), ["cad run src/part.py", 'cad model snapshot "$ID" out.png',
                                             "cad <type> inspect", "cad doctor", "cad.exe stop"])
        pinned = planted.replace("cad run", f"cad +{VERSION} run").replace("cad model", f"cad +{VERSION} model") \
            .replace("cad <type>", f"cad +{VERSION} <type>").replace("cad doctor", f"cad +{VERSION} doctor") \
            .replace("cad.exe stop", f"cad.exe +{VERSION} stop")
        self.assertEqual(unpinned(pinned), [])
        self.assertEqual(set(pins(pinned)), {VERSION})

    def test_prose_and_the_library_are_not_commands(self) -> None:
        prose = (
            "Run the `cad` command (`~/.local/bin/cad`; `cad.exe` on Windows), the $cad skill, `cad.step`,\n"
            "`cad[build123d]==1.0`, `cad-mcp`, `cad_server`.\n\n"
            "```python\nfrom cad import model\nimport cad\nmodel = load(p)  # every part where cad placed it\n```\n"
            "Outside code, run cad doctor is prose: it is not copied as a command.\n"
        )
        self.assertEqual(unpinned(prose), [])


if __name__ == "__main__":
    unittest.main()
