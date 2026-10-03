"""KiCad S-expressions: the one syntax every KiCad document is written in.

A ``.kicad_pcb``, ``.kicad_sch``, ``.kicad_sym`` and ``.kicad_mod`` is each a
single S-expression. This module reads one into plain Python values and writes
plain Python values back. It knows nothing about what any of them mean.

The tree
--------
A list is a Python ``list`` whose first element is its head, a :class:`Sym`.
An unquoted atom is a :class:`Sym` (a ``str`` subclass): keywords such as
``yes``, ``smd`` or ``roundrect``. A quoted string is a plain ``str``. A number
is an ``int`` or a ``float``. ``(pad "1" smd rect (at 0 1.5))`` reads as
``[Sym("pad"), "1", Sym("smd"), Sym("rect"), [Sym("at"), 0, 1.5]]``.

Quoted and unquoted stay apart because KiCad tells them apart: it reads
``(layer "F.Cu")`` and ``(layer F.Cu)`` alike, but rejects a keyword written
in quotes (``(attr "smd")``).

Writing
-------
:func:`dumps` is a pure function of the tree, so the same tree always gives
the same bytes. The layout follows KiCad's: a list of atoms stays on one line,
a list holding lists opens a block indented by one tab, and a run of ``xy``
points wraps six to a line. A number prints as the shortest text that reads
back as the same value, never in exponent form and never as ``-0``. KiCad's
own files mix precisions (lengths to the nanometre, a corner ratio to eleven
decimals, an image position to fifteen), and a library footprint copied into a
board must keep every digit it came with. The writers in this package round
what they COMPUTE to KiCad's nanometre before it reaches a tree, so their own
numbers stay short.
"""

from __future__ import annotations

import math
import re
from typing import Iterator

__all__ = [
    "Sym",
    "SexprError",
    "dumps",
    "find",
    "find_all",
    "format_number",
    "head",
    "parse",
    "value",
]


class Sym(str):
    """An unquoted atom: a keyword, never a user string."""

    __slots__ = ()

    def __repr__(self) -> str:
        return f"Sym({str.__repr__(self)})"


class SexprError(ValueError):
    """Bytes that are not one well-formed S-expression."""


_TOKEN = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))', re.DOTALL)
_NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?\Z")
_INTEGER = re.compile(r"[-+]?\d+\Z")
_UNESCAPE = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}


def _unescape(text: str) -> str:
    if "\\" not in text:
        return text
    return re.sub(r"\\(.)", lambda match: _UNESCAPE.get(match.group(1), match.group(1)), text, flags=re.DOTALL)


def _atom(text: str):
    if _NUMBER.match(text):
        if _INTEGER.match(text):
            return int(text)
        return float(text)
    return Sym(text)


def parse(text: str) -> list:
    """The one S-expression ``text`` holds, as a tree (see the module doc)."""
    stack: list[list] = []
    root: list | None = None
    position = 0
    for match in _TOKEN.finditer(text):
        if match.start() != position:
            break
        position = match.end()
        opened, closed, quoted, bare = match.groups()
        if opened:
            node: list = []
            if stack:
                stack[-1].append(node)
            elif root is not None:
                raise SexprError("more than one expression at the top level")
            else:
                root = node
            stack.append(node)
        elif closed:
            if not stack:
                raise SexprError("a ')' closes nothing")
            stack.pop()
        elif not stack:
            raise SexprError("an atom outside any list")
        elif quoted is not None:
            stack[-1].append(_unescape(quoted))
        else:
            stack[-1].append(_atom(bare))
    if text[position:].strip():
        raise SexprError(f"unreadable text at offset {position}: {text[position:position + 40]!r}")
    if stack:
        raise SexprError(f"{len(stack)} list(s) never closed")
    if root is None:
        raise SexprError("no expression")
    if root and not isinstance(root[0], Sym):
        raise SexprError("the top-level list has no keyword head")
    return root


# --- reading helpers -------------------------------------------------------


def head(node) -> str | None:
    """A list's keyword, or ``None`` for an atom or an empty list."""
    if isinstance(node, list) and node and isinstance(node[0], Sym):
        return str(node[0])
    return None


def find_all(node: list, name: str) -> Iterator[list]:
    """Every direct child list of ``node`` whose head is ``name``."""
    for child in node[1:]:
        if isinstance(child, list) and child and child[0] == name:
            yield child


def find(node: list, name: str) -> list | None:
    """The first direct child list of ``node`` whose head is ``name``."""
    return next(find_all(node, name), None)


def value(node: list, name: str, default=None):
    """The first atom of the child ``(name atom ...)``, else ``default``."""
    child = find(node, name)
    if child is None or len(child) < 2:
        return default
    return child[1]


# --- writing ---------------------------------------------------------------


def format_number(number: float | int) -> str:
    """A number as the shortest text that reads back as it: ``0.25``, ``12``."""
    if isinstance(number, bool):
        raise TypeError("a KiCad document has no booleans; write Sym('yes') or Sym('no')")
    if isinstance(number, int):
        return str(number)
    if not math.isfinite(number):
        raise ValueError(f"a KiCad document cannot hold {number!r}")
    if number == 0:
        return "0"
    # repr is the shortest round-tripping text and the same on every platform.
    text = repr(float(number))
    if "e" in text or "E" in text:
        text = f"{number:.17f}".rstrip("0").rstrip(".")
    if text.endswith(".0"):
        text = text[:-2]
    return text


def _quote(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _atom_text(atom) -> str:
    if isinstance(atom, Sym):
        return str(atom)
    if isinstance(atom, str):
        return _quote(atom)
    if isinstance(atom, (int, float)):
        return format_number(atom)
    raise TypeError(f"not a KiCad atom: {atom!r}")


def _inline(node: list) -> str:
    return "(" + " ".join(_inline(item) if isinstance(item, list) else _atom_text(item) for item in node) + ")"


_POINTS_PER_LINE = 6


def _write(node: list, depth: int, out: list[str]) -> None:
    first_list = next((index for index, item in enumerate(node) if isinstance(item, list)), None)
    if first_list is None:
        out.append(_inline(node))
        return
    indent = "\t" * (depth + 1)
    out.append("(" + " ".join(_atom_text(atom) for atom in node[:first_list]))
    rest = node[first_list:]
    if all(head(item) == "xy" for item in rest):
        for start in range(0, len(rest), _POINTS_PER_LINE):
            run = rest[start:start + _POINTS_PER_LINE]
            out.append("\n" + indent + " ".join(_inline(item) for item in run))
    else:
        # Order is kept exactly: an atom that follows a child list (an older
        # file's trailing `hide`) stays after it, on its own line.
        for item in rest:
            out.append("\n" + indent)
            if isinstance(item, list):
                _write(item, depth + 1, out)
            else:
                out.append(_atom_text(item))
    out.append("\n" + "\t" * depth + ")")


def dumps(node: list) -> str:
    """``node`` as document text, newline-terminated."""
    if head(node) is None:
        raise ValueError("a document is a list with a keyword head")
    out: list[str] = []
    _write(node, 0, out)
    out.append("\n")
    return "".join(out)
