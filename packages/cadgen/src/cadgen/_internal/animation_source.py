"""Inspect animation source embedded in a document-bound STEP sidecar.

Python only reads the source: it preflights literal clip names, and checks the
module's exports when a model declares it; the shared JavaScript runtime
compiles and evaluates the module. No adjacent JS file is searched or loaded.
Dynamic clip definitions are validated by that runtime.
"""

from __future__ import annotations

import functools
import re
from pathlib import Path


def read_animation_source(document: Path | str, *, document_hash: str | None = None) -> str | None:
    """Read the animation from the validated sidecar of the selected STEP."""
    from cadgen._internal.source_sidecar import read_source_sidecar

    sidecar = read_source_sidecar(document, document_hash=document_hash) or {}
    animation = sidecar.get("animation")
    return animation["source"] if animation is not None else None


_CLIPS_DECLARATION = re.compile(r"\bexport\s+const\s+clips\s*=\s*\{")
_IDENTIFIER = re.compile(r"[A-Za-z_$][\w$]*")
_OPENERS = {"{": "}", "[": "]", "(": ")"}


def _skip_string(text: str, index: int) -> int:
    """``index`` just past the string literal opening at ``text[index]``."""
    quote = text[index]
    index += 1
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == quote:
            return index + 1
        if quote == "`" and char == "$" and text.startswith("${", index):
            # A template expression may itself nest braces and quotes: skip it
            # as a balanced group and resume the literal after it.
            index = _skip_group(text, index + 1)
            continue
        index += 1
    raise ValueError("unterminated string")


def _skip_comment(text: str, index: int) -> int | None:
    """``index`` past the comment opening at ``text[index]``, or ``None`` if
    the ``/`` is not a comment (division, or a regex literal we cannot tell
    apart — treated as an ordinary character)."""
    if text.startswith("//", index):
        end = text.find("\n", index)
        return len(text) if end < 0 else end + 1
    if text.startswith("/*", index):
        end = text.find("*/", index + 2)
        if end < 0:
            raise ValueError("unterminated comment")
        return end + 2
    return None


def _skip_group(text: str, index: int) -> int:
    """``index`` just past the bracket group opening at ``text[index]``."""
    closer = _OPENERS[text[index]]
    index += 1
    while index < len(text):
        char = text[index]
        if char == closer:
            return index + 1
        if char in _OPENERS:
            index = _skip_group(text, index)
            continue
        if char in "\"'`":
            index = _skip_string(text, index)
            continue
        if char == "/":
            skipped = _skip_comment(text, index)
            if skipped is not None:
                index = skipped
                continue
        if char in "}])":
            raise ValueError("unbalanced brackets")
        index += 1
    raise ValueError("unterminated group")


def _skip_value(text: str, index: int) -> int:
    """``index`` at the ``,`` or ``}`` that ends the property value starting at
    ``text[index]``."""
    while index < len(text):
        char = text[index]
        if char in ",}":
            return index
        if char in _OPENERS:
            index = _skip_group(text, index)
            continue
        if char in "\"'`":
            index = _skip_string(text, index)
            continue
        if char == "/":
            skipped = _skip_comment(text, index)
            if skipped is not None:
                index = skipped
                continue
        if char in "])":
            raise ValueError("unbalanced brackets")
        index += 1
    raise ValueError("unterminated object")


def _skip_blank(text: str, index: int) -> int:
    while index < len(text):
        if text[index].isspace():
            index += 1
            continue
        if text[index] == "/":
            skipped = _skip_comment(text, index)
            if skipped is not None:
                index = skipped
                continue
        break
    return index


def declared_clip_ids(module_text: str) -> list[str] | None:
    """The top-level keys of the module's ``export const clips = {...}`` literal,
    in declaration order — or ``None`` when the text declares its clips some
    other way and only the runtime can say what they are."""
    text = str(module_text or "")
    match = _CLIPS_DECLARATION.search(text)
    if match is None:
        return None
    ids: list[str] = []
    index = match.end()
    try:
        while True:
            index = _skip_blank(text, index)
            if index >= len(text):
                raise ValueError("unterminated object")
            char = text[index]
            if char == "}":
                return ids
            if char == ",":
                index += 1
                continue
            if char in "\"'":
                end = _skip_string(text, index)
                key = text[index + 1 : end - 1]
            else:
                identifier = _IDENTIFIER.match(text, index)
                if identifier is None:
                    # A computed key, a spread, or something else outside the
                    # contract's literal form: defer to the runtime.
                    return None
                key = identifier.group(0)
                end = identifier.end()
            index = _skip_blank(text, end)
            if index >= len(text) or text[index] != ":":
                # Method shorthand or a bare identifier is not a clip entry the
                # runtime would keep either (a clip is an object with update()).
                return None
            index = _skip_value(text, index + 1)
            ids.append(key)
    except ValueError:
        return None


# --- The module's exports ------------------------------------------------------
#
# compileAnimationModule (core's renderModule.js) refuses a module that exports
# any name but `clips` -- a helper, a constant -- or a default, and drops every
# clip with it. A model declares its module at build time, so the build refuses
# what the renderer would, in the renderer's words. The exports are read from
# the text without running it; a form this reader cannot follow is left to the
# renderer, which stays the judge.

# The renderer's closed export vocabulary, ANIMATION_MODULE_EXPORTS in
# renderModule.js. renderModule.parity.json beside it pins this tuple and the
# refusals' wording to the renderer's own: both test suites read it.
ANIMATION_MODULE_EXPORTS = ("clips",)


def check_animation_exports(module_text: str, *, name: str) -> None:
    """Raise what ``compileAnimationModule`` throws for this module's exports.

    ``name`` leads the message as it leads the renderer's: ``<model> animation``."""
    exported = module_exports(module_text)
    if exported is None:
        return
    understood = ", ".join(ANIMATION_MODULE_EXPORTS)
    unknown = [key for key in exported if key != "default" and key not in ANIMATION_MODULE_EXPORTS]
    if unknown:
        raise ValueError(
            f"{name}: unknown export{'' if len(unknown) == 1 else 's'} {', '.join(unknown)} — "
            f"the renderer understands: {understood}"
        )
    if "default" in exported:
        raise ValueError(
            f"{name}: a default export is not an animation-module export — use named exports ({understood})"
        )


@functools.lru_cache(maxsize=8)
def module_exports(module_text: str) -> tuple[str, ...] | None:
    """The names an ES module exports, ordered as its namespace lists them (by
    UTF-16 code unit, as ``Object.keys`` does) -- or ``None`` where only a
    JavaScript engine can say: a destructured or re-exported name, a duplicate
    (a SyntaxError), or text this reader cannot follow. Every import of a model
    declares its module again, so a process reads each text once."""
    try:
        names = _top_level_exports(str(module_text or ""))
    except (_Unreadable, RecursionError):
        return None
    if len(set(names)) != len(names):
        return None
    return tuple(sorted(names, key=lambda key: key.encode("utf-16-be", "surrogatepass")))


class _Unreadable(ValueError):
    """Module text the export reader cannot follow."""


# One JavaScript token reader, enough to find a module's top-level `export`
# declarations: it steps over strings, templates, comments, regular expressions
# and bracket groups, and tells a regular expression from a division by the
# token before the `/`, as JavaScript's grammar does.
_EOL = r"\r\n\N{LINE SEPARATOR}\N{PARAGRAPH SEPARATOR}"  # JavaScript's line terminators
_STRING = (
    r'"[^"\\\r\n]*+(?:\\(?:\r\n|[\s\S])[^"\\\r\n]*+)*+"'
    r"|'[^'\\\r\n]*+(?:\\(?:\r\n|[\s\S])[^'\\\r\n]*+)*+'"
)
_NUMBER = r"\d[\w$.]*+"
_WORD = r"(?:[^\W\d]|\$)[\w$]*+"
_ATOMS = rf"{_STRING}|{_NUMBER}|{_WORD}"
_PLAIN = r"[^\w$\"'`/()\[\]{}]"
# A `[...]` or `{...}` holding only plain text, strings, numbers and words (a row
# of generated data) is stepped over whole.
_FLAT = rf"(?:{_PLAIN}|{_ATOMS})*+"
_FLAT_GROUP = r"\[" + _FLAT + r"\]|\{" + _FLAT + r"\}"
# What a scan steps over without deciding anything. It stops at any other
# bracket, a slash, a backquote and, at the top level, the words `export` and
# `import`; in an initializer, at `,`, `;` and spaces too.
_TOP_PLAIN = re.compile(
    rf"(?:{_PLAIN}|{_STRING}|{_NUMBER}|(?!(?:export|import)(?![\w$])){_WORD}|{_FLAT_GROUP})++"
)
_GROUP_PLAIN = re.compile(rf"(?:{_PLAIN}|{_ATOMS}|{_FLAT_GROUP})++")
_EXPRESSION_PLAIN = re.compile(r"(?:[^\w$\"'`/()\[\]{},;\s]|" + _ATOMS + r")++")
_SPACE = re.compile(rf"(?:\s++|//[^{_EOL}]*+|/\*[\s\S]*?\*/)*+")
_LINE_REST = re.compile(rf"[^{_EOL}]*+")
_LINE_BREAK = re.compile(rf"[{_EOL}]")
_REGEX_LITERAL = re.compile(rf"/(?:[^/\\\[{_EOL}]|\\[^{_EOL}]|\[(?:[^\]\\{_EOL}]|\\[^{_EOL}])*+\])++/[\w$]*+")
_TEMPLATE_TEXT = re.compile(r"[^`\\$]*+(?:(?:\\[\s\S]|\$(?!\{))[^`\\$]*+)*+")
_TOKEN = re.compile(rf"{_WORD}|{_STRING}|\S")
_BINDING = re.compile(_WORD)
_TAIL_WORD = re.compile(r"[\w$]+$")

_OPERAND = ("operand", "")
# Words a `/` after which begins a regular expression rather than a division.
_BEFORE_EXPRESSION = frozenset({
    "await", "case", "default", "delete", "do", "else", "extends", "in",
    "instanceof", "new", "of", "return", "throw", "typeof", "void", "yield",
})
_CONDITIONS = frozenset({"for", "if", "while", "with"})
# A line break after one of these words never ends a statement.
_EXPECTING = (_BEFORE_EXPRESSION - {"of"}) | {"class", "function"}
# What may follow a line break and still continue the expression before it.
_CONTINUATIONS = frozenset("([`.,;?:=+-*/%&|^<>")


def _top_level_exports(text: str) -> list[str]:
    names: list[str] = []
    i, last = 0, ("punct", ";")
    if text.startswith("#!"):
        i = _LINE_REST.match(text, 2).end()
    while i < len(text):
        plain = _TOP_PLAIN.match(text, i)
        if plain is not None:
            last, i = _after(plain.group(), last), plain.end()
            continue
        char = text[i]
        if char in _OPENERS:
            i, last = _step_group(text, i, last)
        elif char == "/":
            i, last = _slash(text, i, last)
        elif char == "`":
            i, last = _step_template(text, i), _OPERAND
        elif char in "ei":  # `export` or `import`, where the plain stretch stopped
            word = "export" if char == "e" else "import"
            if last == ("punct", "."):
                i, last = i + len(word), _OPERAND  # a property: `module.export`
            elif word == "export":
                i, last = _export_declaration(text, i + len(word), names)
            elif _token(text, i + len(word))[0] in ("(", "."):
                i, last = i + len(word), _OPERAND  # `import(...)`, `import.meta`
            else:
                # Another module's names: the renderer resolves the import, and
                # refuses the module there before it reads an export.
                raise _Unreadable("import")
        else:
            raise _Unreadable("unbalanced brackets or an unterminated string")
    return names


def _after(stretch: str, last: tuple[str, str]) -> tuple[str, str]:
    """The token a stepped-over stretch ends with, as a following `/` reads it:
    a word, an operand (the `/` divides) or a punctuator (it begins a regular
    expression). A stretch of spaces leaves the token before it."""
    tail = stretch.rstrip()
    if not tail:
        return last
    char = tail[-1]
    if char in "\"']" or tail.endswith(("++", "--")):
        return _OPERAND
    if char in "$_" or char.isalnum():
        word = _TAIL_WORD.search(tail).group()
        before = tail[: len(tail) - len(word)].rstrip()
        if word[0].isdigit() or (before.endswith(".") and not before.endswith("...")):
            return _OPERAND  # a number, or a property: `x.return / 2` divides
        return ("word", word)
    return ("punct", char)


def _regex_may_follow(last: tuple[str, str]) -> bool:
    return last[0] == "punct" or (last[0] == "word" and last[1] in _BEFORE_EXPRESSION)


def _slash(text: str, i: int, last: tuple[str, str]) -> tuple[int, tuple[str, str]]:
    """Step over the comment, regular expression or division at ``text[i]``."""
    if text.startswith("//", i):
        return _LINE_REST.match(text, i).end(), last
    if text.startswith("/*", i):
        end = text.find("*/", i + 2)
        if end < 0:
            raise _Unreadable("unterminated comment")
        return end + 2, last
    if _regex_may_follow(last):
        literal = _REGEX_LITERAL.match(text, i)
        if literal is None:
            raise _Unreadable("unterminated regular expression")
        return literal.end(), _OPERAND
    return i + 1, ("punct", "/")


def _step_template(text: str, i: int) -> int:
    """The index past the template literal opening at ``text[i]``; each ``${}`` is code."""
    i += 1
    while True:
        i = _TEMPLATE_TEXT.match(text, i).end()
        if text.startswith("`", i):
            return i + 1
        if not text.startswith("${", i):
            raise _Unreadable("unterminated template")
        i = _step_group(text, i + 1, ("punct", "{"))[0]


def _opened(char: str, last: tuple[str, str]) -> tuple[str, bool]:
    """A bracket's closer, and whether it is a condition's `(`: after its `)` a
    `/` begins a regular expression, as after a `}`; after a call's `)` or a `]`
    it divides."""
    return _OPENERS[char], char == "(" and last[0] == "word" and last[1] in _CONDITIONS


def _step_group(text: str, i: int, last: tuple[str, str]) -> tuple[int, tuple[str, str]]:
    """(The index past the bracket group opening at ``text[i]``, its closer as a
    following `/` reads it.)"""
    stack = [_opened(text[i], last)]
    last, plain, i = ("punct", text[i]), None, i + 1
    while i < len(text):
        match = _GROUP_PLAIN.match(text, i)
        if match is not None:
            plain, i = match, match.end()
            continue
        char = text[i]
        if plain is not None and char in "(/":  # only these ask what came before
            last = _after(plain.group(), last)
        plain = None
        if char in _OPENERS:
            stack.append(_opened(char, last))
            last, i = ("punct", char), i + 1
        elif char in ")]}":
            if stack[-1][0] != char:
                raise _Unreadable("unbalanced brackets")
            condition = stack.pop()[1]
            last, i = (("punct", char) if char == "}" or condition else _OPERAND), i + 1
            if not stack:
                return i, last
        elif char == "/":
            i, last = _slash(text, i, last)
        elif char == "`":
            i, last = _step_template(text, i), _OPERAND
        else:
            raise _Unreadable("unterminated string")
    raise _Unreadable("unterminated group")


def _token(text: str, i: int) -> tuple[str, int]:
    """(The next token of a declaration, the index past it), or ``("", i)`` at the end."""
    i = _SPACE.match(text, i).end()
    token = _TOKEN.match(text, i)
    return (token.group(), token.end()) if token is not None else ("", i)


def _binding(token: str) -> str:
    if _BINDING.fullmatch(token) is None:
        raise _Unreadable(f"binding {token!r}")  # a destructuring pattern: the engine's to read
    return token


def _export_declaration(text: str, i: int, names: list[str]) -> tuple[int, tuple[str, str]]:
    """Add the names the declaration after an `export` keyword exports: (the index
    past what was read, its last token as a following `/` reads it)."""
    keyword, i = _token(text, i)
    if keyword == "default":
        names.append("default")
        return i, ("word", "default")
    if keyword == "async":
        keyword, i = _token(text, i)
        if keyword != "function":
            raise _Unreadable("export async")
    if keyword in ("function", "class"):
        name, i = _token(text, i)
        if keyword == "function" and name == "*":
            name, i = _token(text, i)
        names.append(_binding(name))
        return i, _OPERAND
    if keyword in ("const", "let", "var"):
        return _declarators(text, i, names)
    if keyword == "{":
        return _specifiers(text, i, names)
    raise _Unreadable(f"export {keyword}")  # `export * from`: another module's names


def _specifiers(text: str, i: int, names: list[str]) -> tuple[int, tuple[str, str]]:
    """`export { a, b as c }`. With `from`, the names are another module's."""
    while True:
        local, i = _token(text, i)
        if local == "}":
            break
        exported, (following, i) = local, _token(text, i)
        if following == "as":
            exported, i = _token(text, i)
            following, i = _token(text, i)
        quoted = len(exported) > 1 and exported[0] in "\"'" and exported[-1] == exported[0]
        names.append(exported[1:-1] if quoted and "\\" not in exported else _binding(exported))
        if following == "}":
            break
        if following != ",":
            raise _Unreadable("export specifiers")
    if _token(text, i)[0] == "from":
        raise _Unreadable("export from")
    return i, ("punct", "}")


def _declarators(text: str, i: int, names: list[str]) -> tuple[int, tuple[str, str]]:
    """`export const a = 1, b = 2`: each declared name; initializers are stepped over."""
    while True:
        name, i = _token(text, i)
        names.append(_binding(name))
        following, after = _token(text, i)
        if following == "=":
            i, following = _initializer_end(text, after)
            after = i + 1
        if following == ",":
            i = after
        elif following == ";":
            return after, ("punct", ";")
        else:
            return i, ("punct", ";")  # ended by a line break, or by the end of the text


def _initializer_end(text: str, i: int) -> tuple[int, str]:
    """Where the initializer starting at ``text[i]`` ends: (the index of its `,`
    or `;`, that character), or (the index of the next statement, ``""``) where
    a line break ends it (automatic semicolon insertion) or the text does."""
    last = ("punct", "=")
    while True:
        start, i = i, _SPACE.match(text, i).end()
        if i >= len(text) or (_LINE_BREAK.search(text, start, i) and _semicolon_inserted(last, text, i)):
            return i, ""
        char = text[i]
        if char in ",;":
            return i, char
        if char in _OPENERS:
            i, last = _step_group(text, i, last)
        elif char == "/":
            i, last = _slash(text, i, last)
        elif char == "`":
            i, last = _step_template(text, i), _OPERAND
        else:
            plain = _EXPRESSION_PLAIN.match(text, i)
            if plain is None:
                raise _Unreadable("unbalanced brackets or an unterminated string")
            last, i = _after(plain.group(), last), plain.end()


def _semicolon_inserted(last: tuple[str, str], text: str, i: int) -> bool:
    """Whether a line break before ``text[i]`` ends the statement: only after a
    token an expression can end with, and only before one that cannot continue
    it -- `++` and `--` never do."""
    kind, value = last
    if (kind == "punct" and value not in (")", "}")) or (kind == "word" and value in _EXPECTING):
        return False
    if text.startswith(("++", "--"), i):
        return True
    if text[i] in _CONTINUATIONS or text.startswith("!=", i):
        return False
    word = _BINDING.match(text, i)
    return word is None or word.group() not in ("in", "instanceof")
