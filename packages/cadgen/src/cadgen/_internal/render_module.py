"""The render module beside a document: ``<name>.step.js``.

A STEP document may carry, beside it and its sidecar, ONE JavaScript module the
renderer loads by name — ``part.step`` -> ``part.step.js``. It is authored (and
committed), never generated, and no build reads it: choreography is a render-
only concern, so an edit is a reload in the viewer, never a rebuild. Today the
module's one export is ``clips`` (see the cad skill's kinematics reference);
future render-only exports live in the same file.

The Python side only needs two things from it: WHERE it is (this module's path
helpers, shared by the snapshot door and the viewer's catalog) and, for a
snapshot's ``--animation CLIP``, WHICH clip ids it declares — read WITHOUT
running it, so a typo'd clip name fails as a clean CLI error naming the clips
the model has, the way a typo'd pose name fails against the declared poses. The
reader collects the top-level keys of ``export const clips = { id: {...} }``,
skipping over nested braces, strings, template literals and comments.

That reader is a PRE-FLIGHT, not a parser: a module that builds its clips some
other way (``export const clips = build()``) yields ``None``, and the runtime's
own check — which has the compiled clips in hand — is the authority that
refuses the name with the declared set. The two never disagree on a literal,
because the runtime's ids are exactly these keys.
"""

from __future__ import annotations

import re
from pathlib import Path

# APPENDED to the document's whole name, so the trio sorts and reads together:
# `part.step`, `part.step.js`, `part.step.json`. Match the pair of suffixes,
# never `.js` alone — a loose script beside a model is not a render module.
RENDER_MODULE_SUFFIX = ".js"
RENDER_MODULE_NAMES = (".step.js", ".stp.js")


def render_module_path(document: Path | str) -> Path:
    """``part.step`` -> ``part.step.js``, beside the document."""
    document = Path(document)
    return document.with_name(document.name + RENDER_MODULE_SUFFIX)


def is_render_module_name(name: str) -> bool:
    return str(name or "").lower().endswith(RENDER_MODULE_NAMES)


def read_render_module_text(document: Path | str) -> str | None:
    """The module's text, or ``None`` when the document has no render module."""
    path = render_module_path(document)
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


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
