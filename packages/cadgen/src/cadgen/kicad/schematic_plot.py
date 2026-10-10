"""A schematic's plot payload: its index on the plot's sheets, and KiCad's ERC on them.

:mod:`cadgen.kicad.plot` draws the sheets; this reads what the payload carries beside them, in
the frame of each sheet's picture (:mod:`cadgen.kicad.schematic_index`'s sheet frame).
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Sequence

from cadgen.kicad.phrasing import summarize
from cadgen.kicad.refs import selector_or_none
from cadgen.kicad.schematic_index import export_netlist, read_index

__all__ = ["erc_payload", "payload_index"]


def payload_index(root: Path, install, plotted: Sequence[str]) -> dict:
    """The index a schematic's plot payload carries as ``schematic``, for the staged root sheet
    ``root`` the plot drew (``plotted``: the names of its pictures): KiCad's netlist exported
    beside it (one ``kicad-cli`` run), on the plot's sheets in KiCad's page order, then any
    picture the hierarchy does not name. The plot orders its pictures as these sheets."""
    root = Path(root)
    index = read_index(root, netlist=export_netlist(root, install), project=root.with_suffix(".kicad_pro"))
    pictures = set(plotted)
    names = [sheet.name for sheet in index.sheets if sheet.name in pictures]
    names += [name for name in plotted if name not in set(names)]
    return index.aligned(names).as_json()


_SYMBOL = re.compile(r"^Symbol (\S+)")


def _erc_ref(index: dict, sheet: int | None, at: list[float] | None, text: str) -> str | None:
    """A board reference to what an ERC item names: the pin at its point, else the label's net, else its symbol."""
    if sheet is not None and at is not None:
        for pin in index.get("pins", []):
            if pin.get("sheet") == sheet and math.dist(pin.get("at") or (math.inf, math.inf), at) < 0.01:
                return selector_or_none("pad", ref=pin["part"], pad=pin["number"])
        for label in index.get("labels", []):
            if label.get("sheet") == sheet and label.get("net") and math.dist(label.get("at") or (math.inf, math.inf), at) < 0.01:
                return selector_or_none("net", net=label["net"])
    match = _SYMBOL.match(text)
    return selector_or_none("part", ref=match[1]) if match else None


def erc_payload(report: Path, index: dict) -> list[dict]:
    """KiCad's ERC of the schematic, for its plot payload: each finding in a plain sentence, each
    item with the reference it names on the sheet ``index`` (:func:`payload_index`'s) draws it on."""
    data = json.loads(Path(report).read_text(encoding="utf-8"))
    sheets = {sheet["path"]: number for number, sheet in enumerate(index.get("sheets", []))}
    found: list[dict] = []
    for sheet in data.get("sheets", []) or []:
        number = sheets.get(str(sheet.get("path", "")))
        for violation in sheet.get("violations", []) or []:
            items = []
            for item in violation.get("items", []) or []:
                text = str(item.get("description", ""))
                position = item.get("pos")
                # KiCad's ERC JSON says "mm" but writes page millimetres divided by 100 (verified on KiCad 10).
                at = [round(float(position.get("x", 0.0)) * 100, 4), round(float(position.get("y", 0.0)) * 100, 4)] \
                    if isinstance(position, dict) and number is not None else None
                items.append({"text": text, "ref": _erc_ref(index, number, at, text), "at": at, "sheet": number})
            kind, description = str(violation.get("type", "")), str(violation.get("description", ""))
            entry = {
                "check": "erc", "severity": str(violation.get("severity", "error")), "type": kind, "description": description,
                "summary": summarize("erc", kind, description, [item["text"] for item in items]), "items": items,
            }
            if entry not in found:
                found.append(entry)
    return found
