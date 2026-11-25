"""A saved KiCad schematic in one look: its sheets, its parts and its nets, and what a reference names.

:func:`inspect_schematic` (``cad.kicad_sch.inspect``) reads the hierarchy with the standard library
alone, as :func:`~cad.engine.formats.kicad.schematic.read_schematic` does: no KiCad runs. Its answer
is plain data, so a command can print it as JSON; every position is millimetres on its sheet's page
(y down), the frame ``read_schematic`` answers in.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any

from cad.engine.formats.kicad.naming import natural
from cad.engine.formats.kicad.schematic import Net, Pin, Sheet, Symbol, read_schematic

__all__ = ["inspect_schematic", "plain"]


def plain(value: Any) -> Any:
    """What a reference resolves to, as plain data: a dataclass as its fields, a path as text."""
    if isinstance(value, (tuple, list)):
        return [plain(item) for item in value]
    if isinstance(value, Net):
        return {"kind": "net", "name": value.name, "pins": [f"{pin.ref}.{pin.number}" for pin in value.pins],
                "sheets": list(value.sheets), "labels": [{"kind": label.kind, "text": label.text, "sheet": label.sheet,
                                                          "at": list(label.at)} for label in value.labels]}
    if isinstance(value, Sheet):
        return {"kind": "sheet", "path": value.path, "name": value.name, "file": value.file.name, "page": value.page,
                "parent": value.parent, "pins": [{"name": pin.name, "net": pin.net} for pin in value.pins]}
    if isinstance(value, Symbol):
        return {"kind": "symbol", "ref": value.ref, "value": value.value, "footprint": value.footprint,
                "lib_id": value.lib_id, "mpn": value.mpn, "unit": value.unit, "sheet": value.sheet, "at": list(value.at),
                "angle": value.angle, "mirror": value.mirror, "fields": dict(value.fields),
                "pins": [{"number": pin.number, "name": pin.name, "type": pin.type, "net": pin.net} for pin in value.pins]}
    if isinstance(value, Pin):
        return {"kind": "pin", "ref": value.ref, "number": value.number, "name": value.name, "type": value.type,
                "sheet": value.sheet, "at": list(value.at), "net": value.net}
    if is_dataclass(value):
        found = {"kind": type(value).__name__.lower()}
        for item in fields(value):
            found[item.name] = plain(getattr(value, item.name))
        return found
    if isinstance(value, Path):
        return str(value)
    return value


def inspect_schematic(path: Path | str, ref: str | None = None) -> dict:
    """The KiCad schematic hierarchy ``path`` belongs to, summarised::

        {"file": "load.kicad_sch", "root": "divider.kicad_sch",
         "format": {"version": 20250114, "generator": "eeschema 9.0"},
         "sheets": [{"path": "/", "name": "/", "file": "divider.kicad_sch", "page": "1", "symbols": 6}, ...],
         "parts": [{"ref": "R1", "value": "10k", "footprint": "...", "lib_id": "Device:R", "mpn": None,
                    "sheet": "/", "units": 1, "pins": 2, "dnp": False}, ...],       # natural order
         "nets": [{"name": "/MID", "pins": ["C1.1", "R1.2", "R2.1"], "sheets": ["/", "/Load/"]}, ...],
         "counts": {"sheets": 2, "parts": 5, "pins": 9, "nets": 5, "wires": 9, "buses": 0, "labels": 4, ...},
         "warnings": [...],
         "resolved": {...}}                                   # with ``ref``: what it names

    Raises ``FileNotFoundError`` for a missing file and ``ValueError`` for one that is not a KiCad
    schematic, or for a reference that names nothing in it.
    """
    view = read_schematic(path)
    parts: dict[str, dict] = {}
    for symbol in view.symbols:
        if symbol.power or symbol.ref.startswith("#"):
            continue
        part = parts.setdefault(symbol.ref, {"ref": symbol.ref, "value": symbol.value, "footprint": symbol.footprint,
                                             "lib_id": symbol.lib_id, "mpn": symbol.mpn, "sheet": symbol.sheet, "units": 0,
                                             "pins": 0, "dnp": symbol.dnp})
        part["units"] += 1
        part["pins"] += len(symbol.pins)
    on_sheet: dict[str, int] = {}
    for symbol in view.symbols:
        on_sheet[symbol.sheet] = on_sheet.get(symbol.sheet, 0) + 1
    answer = {
        "file": Path(path).name, "root": view.root.name,
        "format": {"version": view.index.version, "generator": view.index.generator},
        "sheets": [{"path": sheet.path, "name": sheet.name, "file": sheet.file.name, "page": sheet.page,
                    "symbols": on_sheet.get(sheet.path, 0)} for sheet in view.sheets],
        "parts": sorted(parts.values(), key=lambda part: natural(part["ref"])),
        "nets": [{"name": net.name, "pins": [f"{pin.ref}.{pin.number}" for pin in net.pins], "sheets": list(net.sheets)}
                 for net in view.nets],
        "counts": {"sheets": len(view.sheets), "parts": len(parts),
                   "pins": sum(len(symbol.pins) for symbol in view.symbols if not symbol.power),
                   "nets": len(view.nets), "wires": sum(1 for wire in view.wires if wire.kind == "wire"),
                   "buses": sum(1 for wire in view.wires if wire.kind == "bus"),
                   "labels": sum(1 for label in view.labels if label.kind not in ("power", "local_power")),
                   "junctions": len(view.junctions), "no_connects": len(view.no_connects)},
        "warnings": list(view.warnings),
    }
    if ref:
        answer["resolved"] = plain(view.resolve(ref))
    return answer
