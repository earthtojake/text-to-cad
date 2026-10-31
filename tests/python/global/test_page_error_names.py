"""A page's crash is typed by its error's ``name`` (`@text-to-cad/core`'s `client/crash.js`: `crashOf`), and the
bundler renames classes: an error class of the page's own whose ``name`` is not a string it sets would report what
it inherits (``Error``), or -- set from its constructor's name -- a word the bundle made up (``i``). So every class
in the page's packages and apps that extends ``Error``, another of the standard's errors, or one of these classes,
sets ``this.name`` in its constructor to its own name, as written. Read as text, so this needs nothing installed.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
# What the pages are built from: the shared packages and the two apps, their sources alone (a test's error classes
# ship in no page).
SOURCES = ("packages/core/src", "packages/ui/src", "apps/web/src", "apps/mcp/src")
SUFFIXES = {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx"}
TESTS = re.compile(r"\.(?:browser\.)?test\.[cm]?[jt]sx?$")
# The standard's errors a class may extend: anything else counts only as one of the scanned classes does.
STANDARD = {"Error", "AggregateError", "EvalError", "RangeError", "ReferenceError", "SyntaxError", "TypeError",
            "URIError", "DOMException"}
CLASS = re.compile(r"\bclass\s+([A-Za-z_$][\w$]*)\s+extends\s+([A-Za-z_$][\w$.]*)\s*(?:<[^{]*>)?\s*\{")


def sources() -> list[Path]:
    found = []
    for tree in SOURCES:
        for path in sorted((ROOT / tree).rglob("*")):
            if path.suffix in SUFFIXES and path.is_file() and not TESTS.search(path.name) \
                    and "node_modules" not in path.parts:
                found.append(path)
    return found


def body(text: str, start: int) -> str:
    """The braces' contents from the ``{`` at ``start`` to the one that closes it, past strings, template
    literals and comments."""
    depth, at = 0, start
    while at < len(text):
        char = text[at]
        if char in "'\"`":
            at += 1
            while at < len(text) and text[at] != char:
                at += 2 if text[at] == "\\" else 1
        elif text.startswith("//", at):
            at = text.find("\n", at)
            at = len(text) if at < 0 else at
        elif text.startswith("/*", at):
            at = text.find("*/", at + 2)
            at = len(text) if at < 0 else at + 1
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:at]
        at += 1
    raise AssertionError(f"no closing brace after {text[start:start + 60]!r}")


def classes() -> list[tuple[Path, str, str, str]]:
    """Each class with an ``extends``: its file, its name, what it extends (the last name of a dotted one) and its body."""
    found = []
    for path in sources():
        text = path.read_text(encoding="utf-8")
        for match in CLASS.finditer(text):
            found.append((path, match[1], match[2].rsplit(".", 1)[-1], body(text, match.end() - 1)))
    return found


def errors(found: list[tuple[Path, str, str, str]]) -> list[tuple[Path, str, str]]:
    """The error classes among ``found``: each extending one of the standard's, or one of these, all the way down."""
    names, chosen = set(STANDARD), {}
    while True:
        more = {(path, name): text for path, name, base, text in found if base in names and (path, name) not in chosen}
        if not more:
            return [(path, name, text) for (path, name), text in chosen.items()]
        chosen.update(more)
        names |= {name for _, name in more}


def uncommented(text: str) -> str:
    """``text`` without its comments, its strings kept."""
    kept, at = [], 0
    while at < len(text):
        char = text[at]
        if char in "'\"`":
            end = at + 1
            while end < len(text) and text[end] != char:
                end += 2 if text[end] == "\\" else 1
            kept.append(text[at:end + 1])
            at = end + 1
        elif text.startswith("//", at):
            end = text.find("\n", at)
            at = len(text) if end < 0 else end
        elif text.startswith("/*", at):
            end = text.find("*/", at + 2)
            at = len(text) if end < 0 else end + 2
        else:
            kept.append(char)
            at += 1
    return "".join(kept)


def sets_its_name(name: str, text: str) -> bool:
    """Whether a class body's constructor sets ``this.name`` to ``name`` as a literal."""
    text = uncommented(text)
    found = re.search(r"\bconstructor\s*\(", text)
    if found is None:
        return False
    start = text.find("{", text.find(")", found.end()))  # past its parameters: ``(message, readonly code?: number)``
    return re.search(rf"\bthis\.name\s*=\s*(['\"`]){re.escape(name)}\1", body(text, start)) is not None


class EveryPageErrorNamesItself(unittest.TestCase):
    def test_each_error_class_sets_its_name_in_its_constructor(self) -> None:
        found = errors(classes())
        self.assertGreaterEqual(len(found), 7, "the scan reads every error class the pages have")
        unnamed = [f"{path.relative_to(ROOT)}: {name}" for path, name, text in found if not sets_its_name(name, text)]
        self.assertEqual(unnamed, [], "an error class sets `this.name = '<its name>'` in its constructor: a bundle "
                                      "renames the class, so a page's crash would be typed by what it inherits or "
                                      "the bundle's word for it")

    def test_the_scan_finds_a_class_that_does_not_name_itself_and_one_extending_it(self) -> None:
        sample = ("class Named extends Error {\n  constructor(message) { super(`a {brace} ${message}`); this.name = 'Named'; }\n}\n"
                  "class Unnamed extends Named { constructor() { super('x'); /* this.name = 'Unnamed' */ } }\n"
                  "class Other extends Thing { constructor() { super(); this.name = 'Other'; } }\n"
                  "class Wrong extends TypeError { constructor() { super(); this.name = this.constructor.name; } }\n")
        found = []
        for match in CLASS.finditer(sample):
            found.append((Path("sample.js"), match[1], match[2], body(sample, match.end() - 1)))
        named = {name: sets_its_name(name, text) for _, name, text in errors(found)}
        self.assertEqual(named, {"Named": True, "Unnamed": False, "Wrong": False})


if __name__ == "__main__":
    unittest.main()
