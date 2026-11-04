"""Schematic references: how a person and an agent name what is in a KiCad schematic.

A reference is a token, ``<file>#<selector>[,<selector>...]``, as a board's is
(:mod:`cad.engine.formats.kicad.refs`), and where a schematic and a board hold the same thing it is
named the same, so one reference cross-probes the two: a part by its reference designator, a pin by
the number the footprint's pad carries, a net by the name KiCad gives it on both.

==========================  ===============================================
``#U3``                     a part: every unit of it placed, on any sheet
``#U3.7``                   its pin 7 (the board's pad 7)
``#net:VBUS``               a net, by KiCad's name (``/Power/VBUS`` for a
                            local one; a local one by its bare name too,
                            when one sheet alone has it)
``#sheet:/Power/``          a sheet, by its path (``/`` the root)
``#wire:<uuid>``            a wire, by the uuid KiCad saved it with; so too
                            ``#bus:``, ``#label:``, ``#junction:``,
                            ``#no_connect:``, ``#bus_entry:`` and
                            ``#symbol:`` (one unit's placement)
==========================  ===============================================

A sheet path or a net holding a comma, whitespace, a quote, ``@`` or ``#`` is JSON-quoted
(``#sheet:"/Power Stage/"``). The canonical form ends a sheet's path in ``/`` and begins it with one.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import PurePath

from cad.engine.formats.kicad.ref_path import QUOTED_PREFIX_RE, split_cad_ref
from cad.engine.formats.kicad.refs import _split_selectors, _strip, parse_board_selector

__all__ = ["ITEM_KINDS", "SchematicSelector", "SchematicToken", "format_sheet_selector", "parse_schematic_selector",
           "parse_schematic_token", "schematic_ref_document"]

#: The kinds a schematic names by the uuid KiCad saved them with.
ITEM_KINDS = ("wire", "bus", "label", "junction", "no_connect", "bus_entry", "symbol")
_HEX = r"[0-9A-Fa-f]+(?:-[0-9A-Fa-f]+)*"
_ITEM_RE = re.compile(rf"({'|'.join(ITEM_KINDS)}):({_HEX})")
_SHEET_RE = re.compile(r'sheet:("(?:[^"\\]|\\.)*"|[^\s"@#,]+)', re.DOTALL)
_NEEDS_QUOTES = re.compile(r'[\s"@#,]')


@dataclass(frozen=True)
class SchematicSelector:
    """One parsed selector: what it names (``part``, ``pad``, ``net``, ``sheet`` or an item kind) and
    its canonical text. A pin is the board's ``pad`` kind: the two name one thing."""

    kind: str
    ref: str | None = None
    pad: str | None = None
    net: str | None = None
    sheet: str | None = None
    id: str | None = None
    canonical: str = ""

    def __str__(self) -> str:
        return self.canonical


@dataclass(frozen=True)
class SchematicToken:
    path: str
    selectors: tuple[SchematicSelector, ...]


def schematic_ref_document(path) -> str | None:
    """``"schematic"`` for a ``.kicad_sch``, else ``None``."""
    return "schematic" if PurePath(str(path or "")).suffix.lower() == ".kicad_sch" else None


def _sheet_path(text: str) -> str:
    parts = [part for part in str(text).split("/") if part]
    return "/" + "".join(f"{part}/" for part in parts)


def format_sheet_selector(path: str) -> str:
    """The canonical selector of the sheet at ``path``: ``#sheet:/Power/``."""
    canonical = _sheet_path(path)
    return f"#sheet:{json.dumps(canonical, ensure_ascii=False) if _NEEDS_QUOTES.search(canonical) else canonical}"


def parse_schematic_selector(text: str) -> SchematicSelector | None:
    """The selector ``text`` (``#`` optional) parsed, or ``None`` when it is not one."""
    selector = "" if text is None else str(text)
    if selector.startswith("#"):
        selector = selector[1:]
    if not selector or selector != _strip(selector):
        return None
    match = _SHEET_RE.fullmatch(selector)
    if match:
        raw = match.group(1)
        if raw.startswith('"'):
            try:
                raw = json.loads(raw)
            except ValueError:
                return None
            if not isinstance(raw, str):
                return None
        return SchematicSelector("sheet", sheet=_sheet_path(raw), canonical=format_sheet_selector(raw))
    match = _ITEM_RE.fullmatch(selector)
    if match:
        kind, uid = match.group(1), match.group(2).lower()
        return SchematicSelector(kind, id=uid, canonical=f"#{kind}:{uid}")
    board = parse_board_selector(selector)
    if board is not None and board.kind in ("part", "pad", "net"):
        return SchematicSelector(board.kind, ref=board.ref, pad=board.pad, net=board.net, canonical=board.canonical)
    return None


def parse_schematic_token(text: str) -> SchematicToken | None:
    """A reference token, ``<file>#<selector>[,<selector>...]`` or a bare selector: its file (``""``
    when it names none) and its selectors in the order written; ``None`` when it is not one."""
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
        return SchematicToken(path, ())
    selectors = [parse_schematic_selector(piece) for piece in _split_selectors(selector_text)]
    if any(selector is None for selector in selectors):
        return None
    return SchematicToken(path, tuple(selectors))
