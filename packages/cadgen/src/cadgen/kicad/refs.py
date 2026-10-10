"""Board references: how a person and an agent name what is on a KiCad board or schematic.

A reference is a token, ``<file>#<selector>[,<selector>...]``, exactly as a STEP
reference is (:mod:`cadgen.cad_ref_syntax`: the file half optional, JSON-quoted
when its path needs it). The selector language is chosen by the file's suffix:
``.kicad_pcb`` and ``.kicad_sch`` speak this one.

======================  ===================================================
``#U3``                 a part, by its reference designator
``#U3.9``               pad (on a board) or pin (on a schematic) 9 of U3,
                        numbered as KiCad numbers it: ``9``, ``A4``, ``EP``
``#net:VIN``            a net, by the name KiCad shows (``TX/RX``, never
                        ``TX{slash}RX``)
``#net:VIN@x40.1y21.6`` that net's copper (a track, a via, a pour, a pad) at a
                        point: boards only
``#@x40.1y21.6``        a point on the board: boards only
======================  ===================================================

Points are millimetres in the board SCRIPT's frame: y up, origin at the board's
drill/place origin (where cadgen puts the script's own origin), the frame
``board.place``, ``pin.position`` and a build's DRC findings use. They carry no
comma, because a token joins several selectors with commas, as STEP tokens do;
a net name holding a comma, whitespace, a quote, ``@`` or ``#`` is JSON-quoted
(``#net:"a,b"``). The canonical form writes a point to three decimals at most,
without trailing zeros or a negative zero, and quotes a net name only when it
must.

The JavaScript half of this language is ``boardRefs.js`` in the viewer's core
package; both are held to one fixture of cases.
"""

from __future__ import annotations

import difflib
import json
import math
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import PurePath

from cadgen.cad_ref_syntax import QUOTED_PREFIX_RE, ref_prefix_names, split_cad_ref
from cadgen.kicad.naming import natural

__all__ = [
    "BOARD_REF_SUFFIXES",
    "BoardSelector",
    "BoardToken",
    "ReferenceView",
    "SELECTOR_KINDS",
    "board_ref_document",
    "format_board_selector",
    "format_point",
    "parse_board_selector",
    "parse_board_token",
    "selector_or_none",
]

#: The documents whose references are board references.
BOARD_REF_SUFFIXES = (".kicad_pcb", ".kicad_sch")
SELECTOR_KINDS = ("part", "pad", "net", "copper", "point")

# JavaScript's whitespace (`\s`), spelled out: Python's `\s` and `str.strip()` know a few
# characters more (and one fewer), and the two halves of the language must split alike.
_WHITESPACE = (
    "\t\n\v\f\r   " + "".join(chr(code) for code in range(0x2000, 0x200B))
    + "    　﻿"
)
_WS_CLASS = re.escape(_WHITESPACE)

_REF = r"[A-Za-z_][A-Za-z0-9_+\-]*"
_PAD = r"[A-Za-z0-9_+\-]+"
_NUMBER = r"-?[0-9]+(?:\.[0-9]+)?"
_QUOTED = r'"(?:[^"\\]|\\.)*"'
_BARE_NET = rf'[^{_WS_CLASS}"@#,]+'
_POINT = rf"@x({_NUMBER})y({_NUMBER})"

_PART_RE = re.compile(rf"({_REF})")
_PAD_RE = re.compile(rf"({_REF})\.({_PAD})")
_NET_RE = re.compile(rf"net:({_QUOTED}|{_BARE_NET})(?:{_POINT})?", re.DOTALL)
_POINT_RE = re.compile(_POINT)
_NEEDS_QUOTES = re.compile(rf'[{_WS_CLASS}"@#,]')

_DECIMALS = Decimal("0.001")


@dataclass(frozen=True)
class BoardSelector:
    """One parsed selector: what it names, and its canonical text (``#``-led)."""

    kind: str  # "part" | "pad" | "net" | "copper" | "point"
    ref: str | None = None
    pad: str | None = None
    net: str | None = None
    at: tuple[float, float] | None = None
    canonical: str = ""

    def __str__(self) -> str:
        return self.canonical


@dataclass(frozen=True)
class BoardToken:
    """A reference token: the file it names (``""`` for none) and its selectors, in order."""

    path: str
    selectors: tuple[BoardSelector, ...]


def board_ref_document(path) -> str | None:
    """``"board"`` for a ``.kicad_pcb``, ``"schematic"`` for a ``.kicad_sch``, else ``None``:
    whether references into ``path`` are board references."""
    suffix = PurePath(str(path or "")).suffix.lower()
    if suffix == ".kicad_pcb":
        return "board"
    if suffix == ".kicad_sch":
        return "schematic"
    return None


def _strip(text: str) -> str:
    return str(text or "").strip(_WHITESPACE)


def _rounded(value: float) -> Decimal:
    """``value`` to three decimals as JavaScript's ``toFixed(3)`` rounds it: the binary
    number's exact value, ties away from zero."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"a board point's coordinate is a finite number of millimetres, got {value!r}")
    try:
        rounded = Decimal(float(value)).quantize(_DECIMALS, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise ValueError(f"{value!r} mm is no point on a board") from None
    return Decimal(0) if rounded == 0 else rounded


def _coordinate_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def _coordinate(text: str) -> float:
    value = float(text)
    return 0.0 if value == 0 else value


def format_point(x: float, y: float) -> str:
    """A point's selector text, ``@x<x>y<y>``: canonical millimetres."""
    return f"@x{_coordinate_text(_rounded(x))}y{_coordinate_text(_rounded(y))}"


def _net_text(name: str) -> str:
    return json.dumps(name, ensure_ascii=False) if _NEEDS_QUOTES.search(name) else name


def _net_name(text: str) -> str | None:
    if text.startswith('"'):
        try:
            name = json.loads(text)
        except ValueError:
            return None
        return name if isinstance(name, str) and name else None
    return text or None


def parse_board_selector(text: str) -> BoardSelector | None:
    """The selector ``text`` (``#`` optional) parsed, or ``None`` when it is not one.

    ``at`` is the point as written; its canonical text is rounded. Whitespace around a
    selector makes it none, as it does in the viewer's half of the language.
    """
    selector = "" if text is None else str(text)
    if selector.startswith("#"):
        selector = selector[1:]
    if not selector or selector != _strip(selector):
        return None
    match = _PART_RE.fullmatch(selector)
    if match:
        return BoardSelector("part", ref=match.group(1), canonical=f"#{match.group(1)}")
    match = _PAD_RE.fullmatch(selector)
    if match:
        ref, pad = match.groups()
        return BoardSelector("pad", ref=ref, pad=pad, canonical=f"#{ref}.{pad}")
    match = _NET_RE.fullmatch(selector)
    if match:
        name = _net_name(match.group(1))
        if name is None:
            return None
        if match.group(2) is None:
            return BoardSelector("net", net=name, canonical=f"#net:{_net_text(name)}")
        at = (_coordinate(match.group(2)), _coordinate(match.group(3)))
        return BoardSelector("copper", net=name, at=at, canonical=f"#net:{_net_text(name)}{format_point(*at)}")
    match = _POINT_RE.fullmatch(selector)
    if match:
        at = (_coordinate(match.group(1)), _coordinate(match.group(2)))
        return BoardSelector("point", at=at, canonical=f"#{format_point(*at)}")
    return None


def format_board_selector(
    kind: str,
    *,
    ref: str | None = None,
    pad: str | None = None,
    net: str | None = None,
    at=None,
) -> str:
    """The canonical selector (``#``-led) naming ``kind`` with these fields.

    Raises ``ValueError`` for fields the language cannot say: a reference
    designator or pad number outside it, an empty net name, a point that is not
    two finite numbers.
    """
    if kind in ("part", "pad"):
        if not isinstance(ref, str) or not _PART_RE.fullmatch(ref):
            raise ValueError(f"{ref!r} is not a reference designator a board reference can name (a letter, then letters, digits or _)")
        if kind == "part":
            return f"#{ref}"
        if not isinstance(pad, str) or not _PAD_RE.fullmatch(f"{ref}.{pad}"):
            raise ValueError(f"{pad!r} is not a pad number a board reference can name (letters, digits, _, + or -)")
        return f"#{ref}.{pad}"
    if kind in ("net", "copper"):
        if not isinstance(net, str) or not net:
            raise ValueError(f"a net reference needs the net's name, got {net!r}")
        if kind == "net":
            return f"#net:{_net_text(net)}"
        return f"#net:{_net_text(net)}{format_point(*_pair(at))}"
    if kind == "point":
        return f"#{format_point(*_pair(at))}"
    raise ValueError(f"a board reference is one of {', '.join(SELECTOR_KINDS)}, not {kind!r}")


def selector_or_none(kind: str, **fields) -> str | None:
    """:func:`format_board_selector`, or ``None`` for what the language cannot name."""
    try:
        return format_board_selector(kind, **fields)
    except ValueError:
        return None


def _pair(at) -> tuple[float, float]:
    try:
        x, y = at
    except (TypeError, ValueError):
        raise ValueError(f"a board point is (x, y) in millimetres, got {at!r}") from None
    return x, y


def _split_selectors(text: str) -> list[str]:
    """``text`` cut at its commas outside quotes (a backslash in quotes escapes what follows)."""
    pieces: list[str] = []
    current: list[str] = []
    quoted = escaped = False
    for character in text:
        if quoted:
            current.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = False
        elif character == '"':
            quoted = True
            current.append(character)
        elif character == ",":
            pieces.append("".join(current))
            current = []
        else:
            current.append(character)
    pieces.append("".join(current))
    return pieces


def parse_board_token(text: str) -> BoardToken | None:
    """A reference token, ``<file>#<selector>[,<selector>...]``: its file (``""`` when it names
    none) and its selectors in the order written; ``None`` when it is not one.

    The file half is split off as a STEP token's is (:func:`cadgen.cad_ref_syntax.split_cad_ref`).
    Its selectors hold whitespace only inside a quoted net name (a hierarchical sheet's
    ``#net:"/Power Stage/VLOC"``), as its file half does inside quotes, and every one of them must
    parse.
    """
    stripped = _strip(text)
    if "#" not in stripped:
        return None
    if stripped.startswith('"'):
        quoted = QUOTED_PREFIX_RE.match(stripped)
        try:
            if quoted is None or not isinstance(json.loads(quoted.group(1)), str):
                return None
        except ValueError:
            return None
    path, selector_text = split_cad_ref(stripped)
    if not selector_text:
        return None
    selectors = [parse_board_selector(piece) for piece in _split_selectors(selector_text)]
    if any(selector is None for selector in selectors):
        return None
    return BoardToken(path, tuple(selectors))


class ReferenceView:
    """What a board's view and a schematic's share: parts and nets by name, and references answered.

    A subclass sets ``path``, ``_parts`` (by reference designator) and ``_nets`` (by name), says
    what its document is in the class attributes below, and answers a pad selector
    (:meth:`_pad`) and a point (:meth:`_place`).
    """

    _DOCUMENT = ""  # "board" or "schematic"
    _FORMS = ""  # the references it answers, for a reference that is none of them
    _NAMEABLE = ""  # what a selector names in it

    def part(self, ref: str):
        """The part ``ref`` (``"U3"``)."""
        found = self._parts.get(str(ref))
        if found is None:
            close = sorted(difflib.get_close_matches(str(ref), list(self._parts), n=3), key=natural)
            if close:
                hint = f"; did you mean {', '.join(close)}?"
            else:
                refs = sorted(self._parts, key=natural)
                hint = f"; its parts are {', '.join(refs[:40])}" + (f" and {len(refs) - 40} more" if len(refs) > 40 else "")
            raise ValueError(f"{self.path.name} has no part {ref}{hint}")
        return found

    def net(self, name: str):
        """The net ``name``, as KiCad shows it (``"TX/RX"``; a sheet's local net ``"/Power/EN"``)."""
        found = self._nets.get(str(name))
        if found is None:
            close = sorted(difflib.get_close_matches(str(name), list(self._nets), n=3), key=natural)
            hint = f"; did you mean {', '.join(close)}?" if close else ""
            raise ValueError(f"{self.path.name} has no net {name!r}{hint}")
        return found

    def resolve(self, ref: str):
        """What the reference ``ref`` names (the class says what each selector answers). A file
        before the ``#`` must name this document."""
        answers = self.resolve_all(ref)
        if len(answers) != 1:
            raise ValueError(
                f"{ref!r} names {len(answers)} things; resolve_all() answers each, in the order written"
            )
        return answers[0]

    def resolve_all(self, ref: str) -> list:
        """Every selector of a reference token (``board.kicad_pcb#U3,C14.2``), each resolved."""
        token = parse_board_token(ref)
        if token is None:
            selector = parse_board_selector(ref)
            if selector is None:
                raise ValueError(f"not a {self._DOCUMENT} reference: {ref!r}; {self._FORMS}")
            path, selectors = "", (selector,)
        else:
            path, selectors = token.path, token.selectors
        if path and not ref_prefix_names(path, str(self.path)):
            raise ValueError(f"reference names {path!r}, but this {self._DOCUMENT} is {str(self.path)!r}")
        if not selectors:
            raise ValueError(f"{ref!r} names the whole {self._DOCUMENT}; name {self._NAMEABLE} in it")
        return [self._answer(selector) for selector in selectors]

    def _answer(self, selector: BoardSelector):
        if selector.kind == "part":
            return self.part(selector.ref)
        if selector.kind == "pad":
            return self._pad(self.part(selector.ref), selector.pad)
        if selector.kind == "net":
            return self.net(selector.net)
        return self._place(selector)

    def _pad(self, part, number: str):
        raise NotImplementedError

    def _place(self, selector: BoardSelector):
        raise NotImplementedError
