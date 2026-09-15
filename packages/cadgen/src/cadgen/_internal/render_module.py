"""Inspect animation source embedded in a document-bound STEP sidecar.

Python only reads the source and preflights literal clip names; the shared
JavaScript runtime compiles and evaluates the module. No adjacent JS file is
searched or loaded. Dynamic clip definitions are validated by that runtime.
"""

from __future__ import annotations

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
