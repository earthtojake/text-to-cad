"""Every source of the three distributions parses on the OLDEST Python their wheels say they support.

This shipped. ``cad_server/cli/store.py`` printed a clause with an f-string nesting
the same quote character inside its replacement field -- syntax PEP 701 made
legal in 3.12 and nothing earlier. CI runs 3.12, so every test passed; the
wheel declares ``requires-python >= 3.11``, so ``pip install cadgen`` succeeded
on 3.11 and then ``cadgen store why`` died with a SyntaxError at import.

Nothing behavioural can catch this, because the interpreter running the suite
is the interpreter that accepts the syntax. So it is policy-checked here:
``ast.parse(..., feature_version=...)`` asks the CURRENT interpreter to parse
with an older grammar. That answers "would the floor accept this file?" for
everything but f-strings: their grammar is not versioned, so on 3.12+ it
accepts PEP 701's -- the very syntax that shipped. Below a 3.12 floor the
f-strings are checked on the tokens as well.

The floor is read from the library's own ``requires-python``, which the server's, the shim's
and the alias distributions' declare alike (held here too), so raising the declared minimum
automatically relaxes this check -- the two can never disagree.
"""

from __future__ import annotations

import ast
import io
import re
import sys
import tokenize
import tomllib
import unittest
from pathlib import Path

from tests.python.support.paths import LIBRARY, PROJECTS, REPO_ROOT, SOURCES

# Every pyproject.toml a distribution is built from: the three packages' and the alias's.
PYPROJECTS = (*(project / "pyproject.toml" for project in PROJECTS),
              *sorted((REPO_ROOT / "packages" / "aliases").glob("*/pyproject.toml")))

# ast.parse only honours feature_version back to 3.7, and only forward to the
# running interpreter. A floor outside that window is not a failure of the
# sources, so the test says so rather than pretending to have checked.
_OLDEST_SUPPORTED_FEATURE_VERSION = (3, 7)


def _requires_python(pyproject: Path) -> str:
    return tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["requires-python"]


def _declared_floor() -> tuple[int, int]:
    """The (major, minor) of the library's declared ``requires-python``."""
    requires = _requires_python(LIBRARY / "pyproject.toml")
    match = re.search(r">=\s*(\d+)\.(\d+)", requires)
    if not match:
        raise AssertionError(
            f"the library's requires-python ({requires!r}) has no '>=<major>.<minor>' floor; "
            "this check needs one to know which grammar to parse against",
        )
    return int(match.group(1)), int(match.group(2))


def _quote(token_text: str) -> str:
    """The delimiter of a string or f-string token, without its prefix letters."""
    body = token_text.lstrip("rRbBuUfF")
    return body[:3] if body[:3] in ('"""', "'''") else body[:1]


class _FString:
    """An open f-string: its quote, and the brackets open in its replacement fields.

    A field's own brace is a list ``[in_format_spec]``; any other bracket is its character.
    """

    def __init__(self, quote: str) -> None:
        self.quote = quote
        self.brackets: list[str | list[bool]] = []

    def reuses_quote(self, token_text: str) -> bool:
        inner = _quote(token_text)
        return inner == self.quote if len(self.quote) == 3 else inner.startswith(self.quote)


def _pep701_fstrings(source: str) -> dict[int, str]:
    """Lines whose f-strings need PEP 701 (3.12), each mapped to the first reason found.

    3.11 lexed an f-string as one string literal and parsed its fields afterwards, so a field
    could not reuse the f-string's quote, hold a backslash or a comment, break the line of a
    single-quoted f-string, or nest fields more than two deep. ``ast.parse`` with an older
    ``feature_version`` on 3.12+ accepts all of these (the f-string grammar is not versioned),
    so they are checked on the tokens; only 3.12+ tokenizes f-strings into parts.
    """
    if not hasattr(tokenize, "FSTRING_START"):
        return {}
    line_ends = (tokenize.NL, tokenize.NEWLINE)
    found: dict[int, str] = {}
    fstrings: list[_FString] = []
    previous = None
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        top = fstrings[-1] if fstrings else None
        # In a field's expression: every token of a nested f-string, and every token of the
        # innermost one but its own literal text (format specs included) and its closing quote.
        in_expression = len(fstrings) > 1 or (
            top is not None and tok.type not in (tokenize.FSTRING_MIDDLE, tokenize.FSTRING_END)
        )
        # A backslash line continuation is no token: the next one just starts on a later line.
        continued = (
            previous is not None and tok.start[0] > previous.end[0] and previous.type not in line_ends
        )
        problem = None
        if tok.type in (tokenize.STRING, tokenize.FSTRING_START) and any(
            fstring.reuses_quote(tok.string) for fstring in fstrings
        ):
            problem = "a string in an f-string field reuses the f-string's quote"
        elif tok.type == tokenize.COMMENT and fstrings:
            problem = "a comment in an f-string field"
        elif in_expression and ("\\" in tok.string or continued):
            problem = "a backslash in an f-string field"
        elif (tok.type in line_ends or tok.start[0] != tok.end[0]) and any(
            len(fstring.quote) == 1 and (fstring.brackets or fstring is not top) for fstring in fstrings
        ):
            problem = "a line break in a field of a single-quoted f-string"

        if tok.type == tokenize.FSTRING_START:
            fstrings.append(_FString(_quote(tok.string)))
        elif tok.type == tokenize.FSTRING_END:
            fstrings.pop()
        elif tok.type == tokenize.OP and top is not None:
            brackets = top.brackets
            field = brackets[-1] if brackets and isinstance(brackets[-1], list) else None
            if tok.string == "{" and (not brackets or (field and field[0])):
                brackets.append([False])
                if sum(isinstance(bracket, list) for bracket in brackets) > 2:
                    problem = problem or "f-string fields nested more than two deep"
            elif tok.string in ("(", "[", "{"):
                brackets.append(tok.string)
            elif tok.string in (")", "]", "}"):
                brackets.pop()
            elif tok.string == ":" and field is not None:
                field[0] = True
        if problem:
            found.setdefault(tok.start[0], problem)
        previous = tok
    return found


def _sources() -> list[Path]:
    return sorted(
        path for source in SOURCES for path in source.rglob("*.py")
        if "__pycache__" not in path.parts
    )


class EveryPackageParsesOnItsDeclaredFloor(unittest.TestCase):
    def test_every_distribution_declares_the_one_floor(self) -> None:
        library = _requires_python(LIBRARY / "pyproject.toml")
        self.assertTrue(PYPROJECTS)
        self.assertEqual({str(path.relative_to(REPO_ROOT)): _requires_python(path) for path in PYPROJECTS},
                         {str(path.relative_to(REPO_ROOT)): library for path in PYPROJECTS},
                         "one release is one product: every distribution of it runs on the library's Python floor")

    def test_every_module_parses_with_the_declared_minimum_grammar(self) -> None:
        floor = _declared_floor()
        if floor < _OLDEST_SUPPORTED_FEATURE_VERSION or floor > sys.version_info[:2]:
            self.skipTest(
                f"cannot parse against {floor[0]}.{floor[1]} from "
                f"{sys.version_info.major}.{sys.version_info.minor}",
            )

        sources = _sources()
        self.assertTrue(sources, f"no sources found under {SOURCES}")

        offenders = []
        for path in sources:
            source = path.read_text(encoding="utf-8")
            try:
                ast.parse(source, filename=str(path), feature_version=floor)
            except SyntaxError as error:
                offenders.append(
                    f"{path.relative_to(REPO_ROOT)}:{error.lineno}: {error.msg}",
                )
                continue
            if floor < (3, 12):
                offenders.extend(
                    f"{path.relative_to(REPO_ROOT)}:{line}: {problem} (PEP 701, 3.12+)"
                    for line, problem in sorted(_pep701_fstrings(source).items())
                )

        self.assertEqual(
            [],
            offenders,
            f"the packages declare requires-python >= {floor[0]}.{floor[1]}, so every module "
            f"must parse under that grammar; these do not:\n  " + "\n  ".join(offenders),
        )

    def test_pep701_fstrings_are_caught(self) -> None:
        # Each is a SyntaxError on 3.11 that ast.parse(feature_version=(3, 11)) on 3.12+
        # accepts. The first is the line that shipped in cad_server/cli/store.py.
        if not hasattr(tokenize, "FSTRING_START"):
            self.skipTest("this interpreter (< 3.12) rejects the syntax in ast.parse already")
        for illegal in (
            "x = f\"{c.get('why') or f'{c.get('files', 0)} files unchanged'}\"\n",
            "x = f\"{'\\n'.join(a)}\"\n",
            'x = f"""{a # why\n}"""\n',
            'x = f"{a +\n b}"\n',
            'x = f"{a:{b:{c}}}"\n',
            'x = f"{d["k"] + d["j"]}"\n',
        ):
            with self.subTest(illegal):
                self.assertEqual([1], list(_pep701_fstrings(illegal)))
        # Their legal neighbours on 3.11: the other quote, a backslash or '#' outside the
        # expression, a line break inside a triple-quoted f-string, and the field syntax.
        for legal in (
            'x = f"{a}" + f\'{b["k"]}\' + f"""{d["k"]}"""\n',
            'x = f"\\n{a:\\n}" + f"#{a:#x}" + f"{\'#\'}"\n',
            'x = f"""{a +\n b}"""\n',
            'x = f"{{a}} {a!r} {a=} {a:>{b}} {a[1:2]}"\n',
        ):
            with self.subTest(legal):
                self.assertEqual({}, _pep701_fstrings(legal))


if __name__ == "__main__":
    unittest.main()
