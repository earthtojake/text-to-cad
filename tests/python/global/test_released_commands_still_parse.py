"""The 30-day rule: a `cad` command the skills typed keeps working for 30 days after the skills stop typing it.

An agent runs what its skills say, and a store's copy of the skills reaches people later than our release, while
cad updates itself to the newest. So the command line of each release takes every command the skills released in
the last 30 days typed. Checked here against the git history: each release tag (`vX.Y.Z`) from `FIRST_RELEASE` on
dated within 30 days of the newest (the newest included), the skills' text AT that tag, and in it every `cad ...`
command form, put through TODAY's command line: the dispatcher's registry and the command's own parser
(`cad_server.cli`). Nothing is run. The forms are those of the fenced code blocks, extracted exactly as
test_documented_commands.py extracts today's (`_command_forms`), and those typed inline, as a code span that is a
whole `cad ...` command (`inline_forms`): a setup block types its most important commands inline.

A release's date is its tag's (a lightweight tag's is its commit's). The window ends at the newest tag, not at
today, so a quiet month changes nothing. The test needs the tags and their commits: a clone with neither fails here
and says how to fetch them, as does a tag whose skills type no command at all, so the test never passes by finding
nothing.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import re
import subprocess
import unittest
from collections import defaultdict

from tests.python.support.paths import REPO_ROOT, add_sources

add_sources()

from cad_server import cli  # noqa: E402

documented = importlib.import_module("tests.python.global.test_documented_commands")

WINDOW_SECONDS = 30 * 24 * 60 * 60
# The rule began with the releases after 0.11.0. What earlier releases typed (0.10's `cad snapshot`, `cad export` and
# `cad inspect` of a document id, every `cadgen ...` line of 0.7 and 0.8) was removed by 0.11.0 itself, a breaking
# release with its migration guide, before the rule existed: tags older than this one are never read.
FIRST_RELEASE = (0, 11, 0)
RELEASE_TAG = re.compile(r"v(\d+)\.(\d+)\.(\d+)")
# A code span that is a `cad` command, and what in one is a placeholder no form can stand for.
INLINE = re.compile(r"(?<!`)`(cad [^`]+)`(?!`)")
PLACEHOLDER = re.compile(r"[<>|]|(?<!\S)[A-Z][A-Z0-9_]+(?!\S)")  # `<type>`, `drc|export`, a word in capitals: `KIND`
# What an argparse parser says of operands a form leaves out, all a span may leave out.
PARTIAL = "the following arguments are required"
FETCH = ("fetch the release tags and their history: `git fetch --tags --unshallow` (or `git fetch --tags`); in "
         "GitHub Actions, check out with `fetch-depth: 0`")


class Refused(Exception):
    """Today's command line does not take a released form: why, in its own words."""


def _git(*args: str, stdin: bytes | None = None) -> bytes:
    return subprocess.run(["git", "-C", str(REPO_ROOT), *args], input=stdin, check=True, capture_output=True).stdout


def released_tags() -> list[tuple[str, int]]:
    """Each release tag within the window, newest first, with its date (Unix seconds)."""
    listing = _git("for-each-ref", "--format=%(refname:short) %(creatordate:unix)", "refs/tags/v*").decode()
    tags = [(name, int(date)) for name, date in (line.split() for line in listing.splitlines())
            if RELEASE_TAG.fullmatch(name) and _release(name) >= FIRST_RELEASE]
    if not tags:
        return []
    newest = max(date for _name, date in tags)
    return sorted(((name, date) for name, date in tags if date >= newest - WINDOW_SECONDS),
                  key=lambda tag: _release(tag[0]), reverse=True)


def _release(tag: str) -> tuple[int, ...]:
    return tuple(map(int, RELEASE_TAG.fullmatch(tag).groups()))


def skill_text(tags: list[str]) -> dict[str, dict[str, str]]:
    """Each tag's skills' Markdown, path -> text, read from git in one batch."""
    files: dict[str, dict[str, str]] = {}
    for tag in tags:
        listing = _git("ls-tree", "-r", "-z", tag, "--", "skills").decode("utf-8")
        files[tag] = {}
        for record in filter(None, listing.split("\0")):
            meta, path = record.split("\t", 1)
            _mode, kind, blob = meta.split()
            if kind == "blob" and path.endswith(".md"):
                files[tag][path] = blob
    blobs = sorted({blob for paths in files.values() for blob in paths.values()})
    out = _git("cat-file", "--batch", stdin="".join(f"{blob}\n" for blob in blobs).encode()) if blobs else b""
    text, at = {}, 0
    for blob in blobs:
        header_end = out.index(b"\n", at)
        size = int(out[at:header_end].split()[2])
        text[blob] = out[header_end + 1:header_end + 1 + size].decode("utf-8", errors="replace")
        at = header_end + 1 + size + 1
    return {tag: {path: text[blob] for path, blob in paths.items()} for tag, paths in files.items()}


def inline_forms(text: str) -> list[tuple[list[str], bool]]:
    """The `cad` forms typed inline, outside the fenced blocks: each code span that is a whole command -- it begins
    `cad `, may wrap a line, and holds no placeholder that cannot be expanded (`<type>`, `drc|export`) -- read by the
    same form parser as a fenced line. A span may name a command without its operands (`cad step solve`), so a form
    from one is held to its command and the options it types, not to the arguments it leaves out (`PARTIAL`)."""
    outside, in_fence = [], False
    for line in text.splitlines():
        if documented.FENCE.match(line):
            in_fence = not in_fence
        elif not in_fence:
            outside.append(line)
    spans = (" ".join(span.split()) for span in INLINE.findall("\n".join(outside)))
    return [form for span in spans if not PLACEHOLDER.search(span)
            for form in documented._command_forms(f"```\n{span}\n```")]


def command_forms(text: str) -> list[tuple[list[str], bool, bool]]:
    """Each form in ``text``: its argv, whether an elision cut it short, and whether it is inline (`inline_forms`)."""
    return ([(argv, elided, False) for argv, elided in documented._command_forms(text)]
            + [(argv, elided, True) for argv, elided in inline_forms(text)])


def dispatch(argv: list[str], elided: bool, inline: bool = False) -> None:
    """Put a released form through today's `cad`, as `cad_server.cli.main` takes it, or raise ``Refused``. (No
    release's skills typed a pin, `cad +X`: a form with one is a command no one answers.)"""
    if not argv or argv[0] in {"-h", "--help", "-V", "--version"}:
        return
    if argv[0] == "help":
        argv, elided = argv[1:], True  # `cad help X` is `cad X --help`: the command must exist
        if not argv:
            return
    split = cli.resolve(argv)
    if split is None and inline and len(argv) == 1 and (argv[0] in cli.TYPE_COMMANDS
                                                      or argv[0] in cli.INTEGRATION_COMMANDS):
        return  # a span that names a document type's commands (`cad model`): the group is there
    if split is None:
        raise Refused("no command answers it")
    if elided:
        return  # not a complete invocation: the command exists, which is all it says
    name, rest = split
    parser = cli.build_parser_for(name)
    if parser is None:
        return  # a command that builds its parser as it runs: existence is what can be checked
    said = io.StringIO()  # both streams: with `--json` a parser says its error on stdout
    try:
        with contextlib.redirect_stderr(said), contextlib.redirect_stdout(said):
            parser.parse_args(rest)
    except SystemExit as exit_:
        if inline and PARTIAL in said.getvalue():
            return  # a span that names the command and leaves its operands out
        if exit_.code not in (0, None):  # `--help` exits 0: taken
            raise Refused(said.getvalue().strip().splitlines()[-1] if said.getvalue().strip() else
                          f"its parser exits {exit_.code}") from None
    except argparse.ArgumentError as error:
        raise Refused(str(error)) from None
    except Exception as error:  # a hand-written parser's own error type
        raise Refused(f"{type(error).__name__}: {error}") from None


class ReleasedCommandsStillParse(unittest.TestCase):
    def test_every_command_the_last_30_days_of_skills_typed_still_parses_today(self) -> None:
        try:
            tags = released_tags()
        except subprocess.CalledProcessError as error:
            self.fail(f"git could not list the tags ({error.stderr.decode().strip()}): {FETCH}")
        self.assertTrue(tags, f"no release tag (vX.Y.Z) in this clone, so nothing can be checked: {FETCH}")
        try:
            texts = skill_text([name for name, _date in tags])
        except subprocess.CalledProcessError as error:
            self.fail(f"git could not read the skills at a release tag ({error.stderr.decode().strip()}): {FETCH}")

        # Each released form once, with the tags and files that typed it, newest first.
        typed: dict[tuple[tuple[str, ...], bool, bool], list[tuple[str, str]]] = defaultdict(list)
        empty = []
        for tag, _date in tags:
            found = 0
            for path, text in sorted(texts[tag].items()):
                for argv, elided, inline in command_forms(text):
                    typed[(tuple(argv), elided, inline)].append((tag, path))
                    found += 1
            if not found:
                empty.append(tag)
        self.assertEqual(empty, [], f"the skills at these tags type no `cad` command, so the extraction no longer "
                                    f"matches their text, or the tags' trees are missing: {FETCH}")

        broken = []
        for (argv, elided, inline), where in typed.items():
            try:
                dispatch(list(argv), elided, inline)
            except Refused as refused:
                tags_typing = sorted({tag for tag, _path in where}, key=_release, reverse=True)
                paths = sorted({path for _tag, path in where})
                broken.append(f"`cad {' '.join(argv)}`{' ...' if elided else ''}{' (inline)' if inline else ''}\n"
                              f"    typed by {', '.join(tags_typing)} in {', '.join(paths)}\n    today: {refused}")
        window = f"{tags[-1][0]} to {tags[0][0]}"
        if broken:
            self.fail(f"{len(broken)} command(s) the skills released from {window} typed no longer work with today's "
                      "command line; each must keep working for 30 days after the skills stop typing it:\n"
                      + "\n".join(sorted(broken)))


if __name__ == "__main__":
    unittest.main()
