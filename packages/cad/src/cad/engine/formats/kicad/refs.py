"""Board references: how a person and an agent name what is on a KiCad board.

A reference is a token, ``<file>#<selector>[,<selector>...]``, exactly as a STEP
reference is (:mod:`cad.engine.formats.kicad.ref_path`: the file half optional, JSON-quoted
when its path needs it). The selector language is chosen by the file's suffix:
``.kicad_pcb`` speaks this one.

==========================  ===============================================
``#U3``                     a part, by its reference designator
``#U3.9``                   pad 9 of U3, numbered as KiCad numbers it: ``9``,
                            ``A4``, ``EP``
``#net:VIN``                a net, by the name KiCad shows (``TX/RX``, never
                            ``TX{slash}RX``)
``#net:VIN@x40.1y21.6``     that net's copper (a track, a via, a pour, a pad)
                            at a point
``#track:<uuid>``           a track or an arc, by the uuid KiCad saved it with
``#via:<uuid>``             a via
``#zone:<uuid>``            a zone (a pour, on each of its layers)
``#text:<uuid>``            a board's text, or a footprint's (a field shown,
                            an ``fp_text``)
``#dimension:<uuid>``       a dimension
``#shape:<uuid>``           a graphic: a ``gr_*`` or ``fp_*`` line, rectangle,
                            circle, arc, polygon or curve
``#@x40.1y21.6``            a point on the board
``#F.Cu@x40.1y21.6``        a point on one layer
``#@x10y5..x20y15``         an area: the box between two corners
``#F.Cu@x10y5..x20y15``     an area on one layer
==========================  ===============================================

Points are millimetres in KiCad's frame, y down, as the board file holds them and
as native board edits use them: a copied point needs no coordinate conversion. They carry no comma, because a token joins several
selectors with commas, as STEP tokens do;
a net name holding a comma, whitespace, a quote, ``@`` or ``#`` is JSON-quoted
(``#net:"a,b"``). The canonical form writes a point to three decimals at most,
without trailing zeros or a negative zero, an area from its low corner to its
high one, and quotes a net name only when it must.

An item is named by the uuid KiCad saved it with (``(uuid "...")``, an older board's
``(tstamp ...)``), which a save keeps and an edit through KiCad's API keeps, so a reference
still names its item after the board is changed around it; the canonical form is lower
case. Copies of one footprint can share their items' uuids: such an item is named under
its footprint's uuid, ``#text:<footprint uuid>/<uuid>``. A layer is KiCad's own name for
it (``F.Cu``, ``In2.Cu``, ``B.SilkS``, ``Edge.Cuts``, ``User.3``), as the file writes it.

The JavaScript half of this language is ``boardRefs.js`` in the viewer's core
package; both are held to one fixture of cases. :class:`cad.engine.formats.kicad.board_index.BoardView`
answers a reference against a board.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import PurePath

from cad.engine.formats.kicad.ref_path import QUOTED_PREFIX_RE, split_cad_ref

__all__ = [
    "BoardSelector",
    "BoardToken",
    "ITEM_KINDS",
    "SELECTOR_KINDS",
    "board_ref_document",
    "format_board_selector",
    "format_point",
    "parse_board_selector",
    "parse_board_token",
    "selector_or_none",
]

SELECTOR_KINDS = ("part", "pad", "net", "copper", "point", "area", "track", "via", "zone", "text", "dimension", "shape")
#: The kinds a board names by the uuid KiCad saved them with (``#track:<uuid>``).
ITEM_KINDS = ("track", "via", "zone", "text", "dimension", "shape")

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
# KiCad's own layer names, as a board file writes them (a user's names for them are only shown).
_LAYER = r"(?:[FB]\.(?:Cu|Adhes|Paste|SilkS|Mask|CrtYd|Fab)|In[0-9]{1,2}\.Cu|(?:Dwgs|Cmts|Eco1|Eco2)\.User|Edge\.Cuts|Margin|User\.[0-9]{1,2})"
_HEX = r"[0-9A-Fa-f]+(?:-[0-9A-Fa-f]+)*"

_PART_RE = re.compile(rf"({_REF})")
_PAD_RE = re.compile(rf"({_REF})\.({_PAD})")
_NET_RE = re.compile(rf"net:({_QUOTED}|{_BARE_NET})(?:{_POINT})?", re.DOTALL)
_POINT_RE = re.compile(_POINT)
_SPOT_RE = re.compile(rf"({_LAYER})?{_POINT}(?:\.\.x({_NUMBER})y({_NUMBER}))?")
_ITEM_RE = re.compile(rf"({'|'.join(ITEM_KINDS)}):({_HEX}(?:/{_HEX})?)")
_LAYER_RE = re.compile(_LAYER)
_ID_RE = re.compile(rf"{_HEX}(?:/{_HEX})?")
_NEEDS_QUOTES = re.compile(rf'[{_WS_CLASS}"@#,]')

_DECIMALS = Decimal("0.001")


@dataclass(frozen=True)
class BoardSelector:
    """One parsed selector: what it names, and its canonical text (``#``-led)."""

    kind: str  # one of SELECTOR_KINDS
    ref: str | None = None
    pad: str | None = None
    net: str | None = None
    at: tuple[float, float] | None = None  # a point; an area's low corner
    canonical: str = ""
    to: tuple[float, float] | None = None  # an area's high corner
    layer: str | None = None  # the layer a point or an area is on
    id: str | None = None  # an item's uuid (``<footprint uuid>/<uuid>`` for a shared one), lower case

    def __str__(self) -> str:
        return self.canonical


@dataclass(frozen=True)
class BoardToken:
    """A reference token: the file it names (``""`` for none) and its selectors, in order."""

    path: str
    selectors: tuple[BoardSelector, ...]


def board_ref_document(path) -> str | None:
    """``"board"`` for a ``.kicad_pcb``, else ``None``: whether references into ``path`` are
    board references."""
    return "board" if PurePath(str(path or "")).suffix.lower() == ".kicad_pcb" else None


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


def _corners(at, to) -> tuple[tuple[float, float], tuple[float, float]]:
    """An area's two corners as its low one and its high one."""
    (x0, y0), (x1, y1) = _pair(at), _pair(to)
    return (min(x0, x1), min(y0, y1)), (max(x0, x1), max(y0, y1))


def _spot_text(at, to=None, layer: str | None = None) -> str:
    """A point's or an area's selector body: ``[<layer>]@x..y..[..x..y..]``."""
    if layer is not None and (not isinstance(layer, str) or not _LAYER_RE.fullmatch(layer)):
        raise ValueError(f"{layer!r} is not a KiCad layer a board reference can name (F.Cu, In2.Cu, B.SilkS, Edge.Cuts, User.3...)")
    where = layer or ""
    if to is None:
        return f"{where}{format_point(*_pair(at))}"
    low, high = _corners(at, to)
    # Rounded first, so the corners are the canonical text's, then ordered: a box is the same box either way round.
    (x0, y0), (x1, y1) = ((float(_rounded(value)) for value in corner) for corner in (low, high))
    return f"{where}{format_point(min(x0, x1), min(y0, y1))}..{format_point(max(x0, x1), max(y0, y1))[1:]}"


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
    match = _ITEM_RE.fullmatch(selector)
    if match:
        kind, uid = match.group(1), match.group(2).lower()
        return BoardSelector(kind, id=uid, canonical=f"#{kind}:{uid}")
    match = _SPOT_RE.fullmatch(selector)
    if match:
        layer = match.group(1)
        at = (_coordinate(match.group(2)), _coordinate(match.group(3)))
        if match.group(4) is None:
            return BoardSelector("point", at=at, layer=layer, canonical=f"#{_spot_text(at, layer=layer)}")
        low, high = _corners(at, (_coordinate(match.group(4)), _coordinate(match.group(5))))
        return BoardSelector("area", at=low, to=high, layer=layer, canonical=f"#{_spot_text(low, high, layer)}")
    return None


def format_board_selector(
    kind: str,
    *,
    ref: str | None = None,
    pad: str | None = None,
    net: str | None = None,
    at=None,
    to=None,
    layer: str | None = None,
    id: str | None = None,
) -> str:
    """The canonical selector (``#``-led) naming ``kind`` with these fields: a part's ``ref``, a
    pad's ``ref`` and ``pad``, a net's ``net`` (and copper's ``at``), an item's ``id`` (its uuid),
    a point's ``at``, an area's ``at`` and ``to`` (two opposite corners), a point's or an area's
    ``layer`` (optional).

    Raises ``ValueError`` for fields the language cannot say: a reference
    designator or pad number outside it, an empty net name, a point that is not
    two finite numbers, an id that is no uuid, a layer KiCad does not name so.
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
        return f"#{_spot_text(at, layer=layer)}"
    if kind == "area":
        if to is None:
            raise ValueError("an area is the box between two corners: give at and to")
        return f"#{_spot_text(at, to, layer)}"
    if kind in ITEM_KINDS:
        if not isinstance(id, str) or not _ID_RE.fullmatch(id):
            raise ValueError(f"a {kind} is named by the uuid KiCad saved it with, got {id!r}")
        return f"#{kind}:{id.lower()}"
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

    The file half is split off as a STEP token's is (:func:`cad.engine.formats.kicad.ref_path.split_cad_ref`).
    Its selectors hold whitespace only inside a quoted net name (``#net:"/Power Stage/VLOC"``), as
    its file half does inside quotes, and every one of them must parse.
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
