"""No document, docstring, comment or message spells a command the ``cad`` command had: each says the one it has now.

A command the skills used is replaced, not kept (AGENTS.md): its old spelling runs nothing and answers in one line with
the new one (``cad_server.cli._hint``: ``cad xbf export`` is ``cad export SRC DST``, ``cad urdf validate`` is ``cad
inspect FILE``, ``cad status`` is ``cad server status``). A document that still teaches the old one sends its reader to
that refusal, and an agent copies what it reads. So every tracked text file is read for a mention of ``cad`` and the
words after it, and the command's own table judges each: whatever it answers with a hint is an earlier spelling, and a
spelling added to the table is held out of every document the moment it is added. So is a command removed with nothing
in its place (``REMOVED``: ``cad serve``, ``cad delete``), which is answered as any unknown command is.

``test_documented_commands.py`` puts the skills' fenced command lines through the parsers; this reads the rest of the
text, prose and code alike: a type's operation (``cad step inspect``, ``cad <type> snapshot``) wherever it stands, and
any other earlier spelling where it is code, in a code span or a string, since "the cad server" and "its cad step" are
prose. A shell runs the command through a variable that holds it as often as by its name (``"$COMMAND_PATH" xbf
export``, ``& $cad server stop``, the installed-mode checks' way), or by its path (``"$VENV/bin/cad" server stop``):
each of those is the command line too. The sample models are no test's to read (``test_tests_are_self_contained.py``),
and a generated file is its source's text (``scripts/generated/regenerate.py``).

The documents about the earlier spellings themselves name them on purpose: the migration guides, the hint table and
its tests, the bridge from releases 0.10.0 to 0.11.11 that runs their commands, and the pages that say what an old
spelling answers. Each is allowed the spellings it names (``ALLOWED``), and no other.
"""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

from tests.python.support.paths import REPO_ROOT, add_sources

add_sources()

from cad.registry import ALIASES, DOCUMENT_TYPES, INTEGRATION_OPERATIONS, OPERATIONS  # noqa: E402
from cad_server import cli  # noqa: E402

#: The files read, by suffix: what holds text a person or an agent reads.
SUFFIXES = (".md", ".py", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".ts", ".tsx", ".json", ".jsonc", ".sh", ".ps1",
            ".yml", ".yaml", ".toml", ".txt", ".html", ".css", ".gitignore")
#: Not read: the sample models, every generated file and the lock files.
SKIPPED = re.compile(r"^models/|\.generated\.|(?:^|/)package-lock\.json$")
#: Each file about the earlier spellings, with the ones it names on purpose (each its first words, as ``spelling``
#: has them); ``None`` for every one. A folder by its path with a slash at its end.
ALLOWED: dict[str, frozenset[str] | None] = {
    # The guides that say what changed, the earlier spellings among it.
    "docs/migrations/": None,
    # The table that answers each, and its tests.
    "packages/cad/src/cad_server/cli/__init__.py": None,
    "tests/python/packages/cad_server/test_cli.py": None,
    "tests/python/packages/cad_server/test_cli_commands.py": frozenset({"cad orcaslicer"}),
    "tests/python/packages/cad_server/engine/test_daemon_server.py": frozenset({"cad status"}),
    "tests/python/packages/cad_server/engine/test_engine_port.py": frozenset({"cad server"}),
    "packages/cad/src/cad_server/cli/server.py": frozenset({"cad server"}),
    # The bridge from releases 0.10.0 to 0.11.11, which runs an earlier release's own commands.
    "packages/cad/src/cad_server/cli/setup.py": frozenset({"cad stop"}),
    "tests/python/packages/cad_server/test_setup.py": frozenset({"cad stop"}),
    "docs/contributing/decisions.md": frozenset({"cad status", "cad stop"}),
    # The pages that say what an earlier spelling answers.
    "packages/cad/README.md": frozenset({"cad orcaslicer"}),
    "packages/cad/src/cad_server/README.md": frozenset(
        {"cad xbf export", "cad <type> <operation>", "cad model <operation>", "cad status", "cad stop",
         "cad orcaslicer"}),
    "packages/cad/src/cad_server/engine/docs/cli.md": frozenset(
        {"cad xbf export", "cad model ...", "cad step solve", "cad urdf validate", "cad kicad_pcb drc",
         "cad kicad_pcb export", "cad status", "cad stop", "cad orcaslicer"}),
    "packages/cad/src/cad_server/engine/docs/document-types-and-integrations.md": frozenset(
        {"cad <type> <operation>", "cad model ...", "cad orcaslicer"}),
    # This test's own examples.
    "tests/python/global/test_documents_use_current_commands.py": None,
}

#: The commands 0.12 removed with nothing in their place (docs/migrations/migrating-0.11-to-0.12.md): answered as any
#: unknown command is, so no hint names them.
REMOVED = frozenset({"serve", "delete"})
# A type as a mention spells one: its name, an alias's (``model``), or a placeholder for any.
PLACEHOLDERS = ("<type>", "<kind>", "TYPE", "<TYPE>", "{type}")
TYPES = frozenset({*DOCUMENT_TYPES, *ALIASES, *PLACEHOLDERS})
# What follows a type in a mention that is a command line wherever it stands: one of the operations a type had.
OPERATION_WORDS = frozenset({*OPERATIONS, *INTEGRATION_OPERATIONS, "<operation>", "..."})
# Where a mention is code: a code span's backtick or a string's quote right before ``cad``.
CODE = ("`", "'", '"')
# ``cad`` and up to six words after it, across a line break and a comment's leader, each word ending where a code span,
# a string or a clause does.
_GAP = r"(?:[ \t]+|[ \t]*\n[ \t]*(?:(?:#|//|\*)[ \t]*)?)"
_WORD = r"[^\s`'\"(),;:|\]]+"
_WORDS = rf"(?P<words>(?:{_GAP}{_WORD}){{1,6}})"
MENTION = re.compile(rf"(?<![\w./@$-])cad{_WORDS}")
# The command run by a shell: through a variable that holds it (``$cad``, ``$CAD``, ``$COMMAND``, ``"$COMMAND_PATH"``,
# braced or not), or by a path that ends in it (``"$VENV/bin/cad"``, ``"$dir\cad.exe"``).
_HOLDER = r"\$\{?(?:cad|CAD|[A-Z_]*COMMAND[A-Z_]*)\}?"
RUN = re.compile(rf'(?:"{_HOLDER}"|{_HOLDER}(?![\w}}])|"[^"\n]*[/\\]cad(?:\.exe|\.cmd)?"){_WORDS}')


def asked(argv: list[str]) -> list[str]:
    """The command line a mention's words ask for: ``cad help step export`` the help of ``cad step export``."""
    return argv[1:] if argv[0] == "help" and argv[1:] else argv


def spelling(argv: list[str]) -> str:
    """A mention's first words, as ``ALLOWED`` names them: two for a type's operation, else one."""
    argv = asked(argv)
    return "cad " + " ".join(argv[:2] if argv[0] in TYPES and len(argv) > 1 else argv[:1])


def earlier(argv: list[str], in_code: bool) -> bool:
    """Whether the words after ``cad`` spell a command the command had: one its table answers (``cli._hint``) or
    one it removed (``REMOVED``)."""
    argv = asked(argv)
    first = argv[0]
    if first in TYPES:  # a type's operation is a command line wherever it stands; the type alone, where it is code
        hinted = cli._hint(["step" if first in PLACEHOLDERS else first, *argv[1:]]) is not None
        return hinted and (in_code or (len(argv) > 1 and argv[1] in OPERATION_WORDS))
    if argv == ["server"]:
        return False  # the command whose forms are start, stop and status, named
    return in_code and (first in REMOVED or cli._hint(argv) is not None)


def mentions(text: str) -> list[tuple[int, list[str], bool]]:
    """Each mention of ``cad`` and the words after it, in the text's order: its line, the words and whether it is
    code -- a shell's run of the command always is (``RUN``)."""
    found = []
    for pattern in (MENTION, RUN):
        for match in pattern.finditer(text):
            argv = [word if set(word) == {"."} else word.rstrip(".!?")
                    for word in re.split(r"\s+(?:(?:#|//|\*)\s+)?", match.group("words").strip())]
            argv = [word for word in argv if word]
            if argv:
                code = pattern is RUN or text[match.start() - 1: match.start()] in CODE
                found.append((match.start(), text.count("\n", 0, match.start()) + 1, argv, code))
    return [(line, argv, code) for _at, line, argv, code in sorted(found, key=lambda mention: mention[0])]


def _files() -> list[str]:
    listed = subprocess.run(["git", "-C", str(REPO_ROOT), "ls-files"], capture_output=True, text=True, check=True)
    return [name for name in listed.stdout.splitlines()
            if name.endswith(SUFFIXES) and not SKIPPED.search(name) and (REPO_ROOT / name).is_file()]


def _allowed(name: str) -> frozenset[str] | None | bool:
    """The spellings a file may name: ``None`` every one, ``False`` none."""
    for path, spellings in ALLOWED.items():
        if name == path or (path.endswith("/") and name.startswith(path)):
            return spellings
    return False


class DocumentsUseCurrentCommands(unittest.TestCase):
    def test_no_file_spells_an_earlier_command(self) -> None:
        found = []
        files = _files()
        self.assertGreater(len(files), 1500, "the sweep read almost no file")
        for name in files:
            allowed = _allowed(name)
            if allowed is None:
                continue
            text = (REPO_ROOT / name).read_text(encoding="utf-8", errors="replace")
            if "cad" not in text:
                continue
            for line, argv, in_code in mentions(text):
                if earlier(argv, in_code) and not (allowed and spelling(argv) in allowed):
                    found.append(f"{name}:{line}: {spelling(argv)}")
        self.assertEqual([], found, "an earlier spelling of a command, which runs nothing now: write the one it has "
                                    "now (the old one, run, names it; docs/migrations/migrating-0.11-to-0.12.md lists "
                                    "them)")

    def test_every_allowed_file_still_names_what_it_is_allowed(self) -> None:
        # An entry the file no longer needs is a hole a stale spelling would pass through.
        for path, spellings in ALLOWED.items():
            if spellings is None:
                continue
            with self.subTest(path=path):
                text = (REPO_ROOT / path).read_text(encoding="utf-8")
                named = {spelling(argv) for _line, argv, in_code in mentions(text) if earlier(argv, in_code)}
                self.assertEqual(set(spellings), named & set(spellings), "ALLOWED names a spelling the file has not")

    def test_a_mention_is_told_from_the_current_spelling_and_from_prose(self) -> None:
        def held(text: str) -> bool:
            return any(earlier(argv, in_code) for _line, argv, in_code in mentions(text))

        for text in ("`cad xbf export a.xbf a.step`", "``cad step\n    inspect DOC REF``",
                     "(cad <type> export, exports.py)", "`cad\n  model snapshot` draws",
                     "# `cad kicad_pcb\n#  snapshot`", "`cad dxf` has no", "`cad status`", "``cad stop``",
                     '"cad status --json"', "`cad server --port N`", "`cad orcaslicer`", "`cad serve DOC`",
                     "`cad delete`", "`cad help step export`", '"$COMMAND_PATH" xbf export a.xbf a.step \\\n  >log',
                     'fail "$COMMAND step dfm --process $process"', "& $cad status", '"${CAD}" stop',
                     '"$VENV/bin/cad" kicad_pcb drc b.kicad_pcb', '& "$tool\\cad.exe" serve a.xbf'):
            with self.subTest(text=text):
                self.assertTrue(held(text))
        for text in ("`cad export a.xbf a.step`", "`cad inspect FILE --interference`", "`cad kicad drc BOARD`",
                     "`cad mujoco check`", "`cad kicad`", "`cad server`", "`cad server start --port 0`",
                     "`cad server --rotate-token --port 3245 --yes`", "`cad viewer arm.xbf`", "`cad help kicad drc`",
                     "`cad <verb> --help`", "`cad --version`", "`cad[build123d]`", "``cad.export``",
                     "uv run cad export a.xbf a.stl", "the cad server is running", "its cad step ended 0",
                     "a text-to-cad model", '"$COMMAND_PATH" export a.xbf a.step', '"$COMMAND_PATH" server start',
                     '"$VENV/bin/cad" server stop', '"$SHIM_COMMAND" --help', '"$GIT" status', "$py model.py",
                     '"$PYTHON_BIN" -c "import cad"', "Use $cad to create the model"):
            with self.subTest(text=text):
                self.assertFalse(held(text))


if __name__ == "__main__":
    unittest.main()
