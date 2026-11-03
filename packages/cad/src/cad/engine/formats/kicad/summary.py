"""A saved KiCad board in one look: what file it is, its layers, its parts and its nets.

:func:`inspect_board` (``cad.kicad_pcb.inspect``) reads the ``.kicad_pcb`` with the standard library alone,
as :func:`~cad.engine.formats.kicad.board_index.read_board` does: no KiCad runs, none need be
installed. Its answer is plain data (dicts, lists, numbers, strings) so a command can print it as JSON.
Every length is in millimetres in KiCad's frame (y down), the frame ``read_board`` answers in.
"""

from __future__ import annotations

from pathlib import Path

from cad.engine.formats.kicad import sexpr
from cad.engine.formats.kicad.board_index import BoardView, canonical_copper, read_index

__all__ = ["inspect_board"]


def _layers(tree: list) -> list[dict]:
    """The board's layer table, ``(0 "F.Cu" signal)`` or ``(5 "F.SilkS" user "F.Silkscreen")``, in order."""
    found = []
    for entry in (sexpr.find(tree, "layers") or [None])[1:]:
        if isinstance(entry, list) and len(entry) >= 3 and isinstance(entry[1], str):
            layer = {"id": entry[0] if isinstance(entry[0], int) else None, "name": entry[1], "type": str(entry[2])}
            if len(entry) >= 4 and isinstance(entry[3], str):
                layer["alias"] = entry[3]  # the name KiCad shows, when it is not the file's
            found.append(layer)
    return found


def _size(outline) -> list[float] | None:
    points = [point for line in outline for point in line]
    if not points:
        return None
    xs, ys = [point[0] for point in points], [point[1] for point in points]
    return [round(max(xs) - min(xs), 4), round(max(ys) - min(ys), 4)]


def inspect_board(path: Path | str) -> dict:
    """The KiCad board at ``path`` summarised::

        {"file": "uart.kicad_pcb",
         "format": {"version": 20260901, "generator": "pcbnew", "generator_version": "10.99"},
         "thickness": 1.6,                      # the board's, mm; None when the file does not say
         "size": [40.0, 30.0],                  # the Edge.Cuts outline's bounding box, mm; None without one
         "layers": {"copper": ["F.Cu", "B.Cu"],
                    "all": [{"id": 0, "name": "F.Cu", "type": "signal"}, ...]},
         "parts": [{"ref": "R1", "value": "10k", "footprint": "Resistor_SMD:R_0603_1608Metric",
                    "side": "top", "at": [35.0, 15.0], "rotation": 0.0, "pads": 2, "dnp": False,
                    "in_bom": True}, ...],     # by reference, natural order
         "nets": [{"name": "GND", "class": "Default", "pads": 2, "tracks": 1, "vias": 1, "zones": 1}, ...],
         "counts": {"parts": 3, "pads": 6, "nets": 3, "tracks": 2, "vias": 1, "zones": 1, "holes": 0}}

    Raises ``FileNotFoundError`` for a missing file and ``ValueError`` for one that is not a KiCad
    board (a name that does not end in ``.kicad_pcb``, text that is not UTF-8 or not a board).
    """
    board = Path(path).expanduser()
    if board.suffix.lower() != ".kicad_pcb":
        raise ValueError(f"{board.name} is not a KiCad board (.kicad_pcb)")
    if not board.is_file():
        raise FileNotFoundError(f"{board} does not exist")
    try:
        text = board.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise ValueError(f"{board.name} is not a readable KiCad board: it is not UTF-8 text") from None
    try:
        tree = canonical_copper(sexpr.parse(text))
        index = read_index(tree, project=board.with_suffix(".kicad_pro"), graphics=False)  # what it says is parts and nets
    except (sexpr.SexprError, ValueError) as error:
        raise ValueError(f"{board.name} is {error}") from None
    view = BoardView(board.resolve(), index)
    layers = _layers(tree)
    general = sexpr.find(tree, "general")
    thickness = sexpr.value(general, "thickness") if general else None
    version = sexpr.value(tree, "version")
    generator = sexpr.value(tree, "generator")
    generator_version = sexpr.value(tree, "generator_version")
    return {
        "file": board.name,
        "format": {
            "version": version if isinstance(version, int) else None,
            "generator": str(generator) if generator is not None else None,
            "generator_version": str(generator_version) if generator_version is not None else None,
        },
        "thickness": float(thickness) if isinstance(thickness, (int, float)) else None,
        "size": _size(index.outline),
        "layers": {
            "copper": [layer["name"] for layer in layers if layer["name"].endswith(".Cu")],
            "all": layers,
        },
        "parts": [
            {
                "ref": part.ref, "value": part.value, "footprint": part.footprint, "side": part.side,
                "at": [round(part.at[0], 4), round(part.at[1], 4)], "rotation": round(part.rotation, 4),
                "pads": len(part.pads), "dnp": part.dnp, "in_bom": part.in_bom,
            }
            for part in view.parts
        ],
        "nets": [
            {"name": net.name, "class": net.netclass, "pads": len(net.pads), "tracks": len(net.tracks),
             "vias": len(net.vias), "zones": len(net.zones)}
            for net in view.nets
        ],
        "counts": {
            "parts": len(view.parts), "pads": len(view.pads), "nets": len(view.nets), "tracks": len(view.tracks),
            "vias": len(view.vias), "zones": len(view.zones), "holes": len(view.holes),
        },
    }
