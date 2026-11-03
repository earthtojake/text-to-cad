"""The page a board is drawn on, as KiCad's PCB editor shows it: its border and title block.

KiCad draws every board on a sheet of paper (``(paper "A4")``, or ``"User" w h``) with
its default drawing sheet: a frame 10 mm in from the page's edges, a second one 2 mm
inside it, the grid references (1, 2, 3 ... across, A, B, C ... down, every 50 mm), and
the title block in the bottom right corner holding the board's ``(title_block ...)``:
title, date, revision, company, comments, the file's name and the paper's. The page's
own edge is a grey line around it.

:func:`drawing_sheet` lays that sheet out for a board, as KiCad's drawing sheet engine
does (``common/drawing_sheet/ds_data_item.cpp``): each line, rectangle and text placed
from a corner of the frame, repeated along its increment while it stays on the page, a
repeated label counting up. The description below is KiCad's default layout, written
out as data; a project's own drawing sheet file is not read. Everything is in the
board's frame: millimetres, y down, the page's top-left corner at (0, 0).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Mapping

from cad.engine.formats.kicad import sexpr
from cad.engine.formats.kicad.geometry import XY

__all__ = ["PAGE_SIZES", "SheetLine", "SheetText", "drawing_sheet", "expand", "page_size", "title_variables"]

#: Paper sizes KiCad knows, landscape, millimetres (``common/page_info.cpp``).
PAGE_SIZES: dict[str, tuple[float, float]] = {
    "A5": (210.0, 148.0), "A4": (297.0, 210.0), "A3": (420.0, 297.0), "A2": (594.0, 420.0),
    "A1": (841.0, 594.0), "A0": (1189.0, 841.0),
    "A": (279.4, 215.9), "B": (431.8, 279.4), "C": (558.8, 431.8), "D": (863.6, 558.8), "E": (1117.6, 863.6),
    "USLetter": (279.4, 215.9), "USLegal": (355.6, 215.9), "USLedger": (431.8, 279.4), "GERBER": (812.8, 812.8),
}
_MARGIN = 10.0
_LINE = 0.15  # the default sheet's line width
_TEXT = 1.5  # its text size
_TEXT_LINE = 0.15  # its text's stroke
_GRID_TEXT = 1.3  # the grid references' size

# KiCad's default drawing sheet, as data. A point is (x, y, corner): mm from a corner of the frame
# (rb, the default, rt, lb, lt), x and y running towards the opposite corner.
_RECTS = (
    ((110, 34, "rb"), (2, 2, "rb"), 1, (0, 0)),  # around the title block
    ((0, 0, "lt"), (0, 0, "rb"), 2, (2, 2)),  # the frame, and the one 2 mm inside it
)
_LINES = (
    ((50, 2, "lt"), (50, 0, "lt"), 30, (50, 0)),  # the grid's ticks across the top
    ((50, 2, "lb"), (50, 0, "lb"), 30, (50, 0)),  # across the bottom
    ((0, 50, "lt"), (2, 50, "lt"), 30, (0, 50)),  # down the left
    ((0, 50, "rt"), (2, 50, "rt"), 30, (0, 50)),  # down the right
    ((110, 5.5, "rb"), (2, 5.5, "rb"), 1, (0, 0)),
    ((110, 8.5, "rb"), (2, 8.5, "rb"), 1, (0, 0)),
    ((110, 12.5, "rb"), (2, 12.5, "rb"), 1, (0, 0)),
    ((110, 18.5, "rb"), (2, 18.5, "rb"), 1, (0, 0)),
    ((90, 8.5, "rb"), (90, 5.5, "rb"), 1, (0, 0)),
    ((26, 8.5, "rb"), (26, 2, "rb"), 1, (0, 0)),
)
# (text, position, size, bold, italic, centred, repeat, increment)
_TEXTS = (
    ("1", (25, 1, "lt"), _GRID_TEXT, False, False, False, 100, (50, 0)),
    ("1", (25, 1, "lb"), _GRID_TEXT, False, False, False, 100, (50, 0)),
    ("A", (1, 25, "lt"), _GRID_TEXT, False, False, True, 100, (0, 50)),
    ("A", (1, 25, "rt"), _GRID_TEXT, False, False, True, 100, (0, 50)),
    ("Date: ${ISSUE_DATE}", (87, 6.9, "rb"), _TEXT, False, False, False, 1, (0, 0)),
    ("${KICAD_VERSION}", (109, 4.1, "rb"), _TEXT, False, False, False, 1, (0, 0)),
    ("Rev: ${REVISION}", (24, 6.9, "rb"), _TEXT, True, False, False, 1, (0, 0)),
    ("Size: ${PAPER}", (109, 6.9, "rb"), _TEXT, False, False, False, 1, (0, 0)),
    ("Id: ${#}/${##}", (24, 4.1, "rb"), _TEXT, False, False, False, 1, (0, 0)),
    ("Title: ${TITLE}", (109, 10.7, "rb"), 2.0, True, True, False, 1, (0, 0)),
    ("File: ${FILENAME}", (109, 14.3, "rb"), _TEXT, False, False, False, 1, (0, 0)),
    ("Sheet: ${SHEETPATH}", (109, 17, "rb"), _TEXT, False, False, False, 1, (0, 0)),
    ("${COMPANY}", (109, 20, "rb"), _TEXT, True, False, False, 1, (0, 0)),
    ("${COMMENT1}", (109, 23, "rb"), _TEXT, False, False, False, 1, (0, 0)),
    ("${COMMENT2}", (109, 26, "rb"), _TEXT, False, False, False, 1, (0, 0)),
    ("${COMMENT3}", (109, 29, "rb"), _TEXT, False, False, False, 1, (0, 0)),
    ("${COMMENT4}", (109, 32, "rb"), _TEXT, False, False, False, 1, (0, 0)),
)


class SheetLine:
    """A straight line of the sheet, ``width`` mm wide; ``page`` for the page's own grey edge."""

    def __init__(self, start: XY, end: XY, width: float, page: bool = False):
        self.start, self.end, self.width, self.page = start, end, width, page


class SheetText:
    """A text of the sheet: left-justified (or centred) on ``at``, vertically centred, ``size`` tall."""

    def __init__(self, text: str, at: XY, size: float, width: float, bold: bool, italic: bool, centred: bool):
        self.text, self.at, self.size, self.width = text, at, size, width
        self.bold, self.italic, self.centred = bold, italic, centred


def page_size(tree: list) -> tuple[str, float, float]:
    """The board's paper: its name and its width and height, mm (``(paper "A4" portrait)``, ``"User" w h``)."""
    paper = sexpr.find(tree, "paper")
    name = str(paper[1]) if paper is not None and len(paper) > 1 else "A4"
    if name == "User" and paper is not None and len(paper) >= 4:
        width, height = sexpr.number(paper[2], 297.0), sexpr.number(paper[3], 210.0)
    else:
        width, height = PAGE_SIZES.get(name, PAGE_SIZES["A4"])
        if paper is not None and any(isinstance(atom, str) and str(atom) == "portrait" for atom in paper[2:]):
            width, height = height, width
    return name, width, height


def _corner(point: tuple, step: int, increment: tuple, lt: XY, rb: XY) -> XY:
    x, y, corner = point[0] + increment[0] * step, point[1] + increment[1] * step, point[2]
    if corner == "rb":
        return rb[0] - x, rb[1] - y
    if corner == "rt":
        return rb[0] - x, lt[1] + y
    if corner == "lb":
        return lt[0] + x, rb[1] - y
    return lt[0] + x, lt[1] + y


def _counted(label: str, step: int) -> str:
    """A repeated label counted on: ``1`` -> ``2`` ..., ``A`` -> ``B`` ... ``Z`` -> ``AA``."""
    if not step:
        return label
    if label.isdigit():
        return str(int(label) + step)
    if label.isalpha() and label.isupper():
        number = 0
        for letter in label:
            number = number * 26 + ord(letter) - 64
        number += step
        out = ""
        while number:
            number, rest = divmod(number - 1, 26)
            out = chr(65 + rest) + out
        return out
    return label


def title_variables(tree: list, *, file_name: str, project: Path | None = None) -> dict[str, str]:
    """The text variables a drawing sheet's texts and a board's texts name: the title block, the
    file, the page, and the project's own (``.kicad_pro``'s ``text_variables``)."""
    paper = page_size(tree)[0]
    version = str(sexpr.value(tree, "generator_version") or "")
    block = sexpr.find(tree, "title_block") or []
    names = {"title": "TITLE", "date": "ISSUE_DATE", "rev": "REVISION", "company": "COMPANY"}
    values = {"KICAD_VERSION": f"KiCad E.D.A. {version}".strip(), "#": "1", "##": "1", "SHEETNAME": "", "SHEETPATH": "",
              "FILENAME": file_name, "PAPER": paper, "TITLE": "", "ISSUE_DATE": "", "REVISION": "", "COMPANY": ""}
    values.update({f"COMMENT{n}": "" for n in range(1, 10)})
    for entry in block[1:]:
        head = sexpr.head(entry)
        if head in names and len(entry) > 1:
            values[names[head]] = str(entry[1])
        elif head == "comment" and len(entry) > 2:
            values[f"COMMENT{int(sexpr.number(entry[1], 0))}"] = str(entry[2])
    for name, value in _project_variables(project).items():
        values.setdefault(name, value)
    return values


def _project_variables(project: Path | None) -> dict[str, str]:
    """The project's own text variables (``.kicad_pro``'s ``text_variables``)."""
    if project is None or not project.is_file():
        return {}
    try:
        found = json.loads(project.read_text(encoding="utf-8")).get("text_variables") or {}
    except (OSError, ValueError, AttributeError):
        return {}
    return {str(key): str(value) for key, value in found.items()} if isinstance(found, dict) else {}


def expand(text: str, variables: Mapping[str, str], depth: int = 0) -> str:
    """``${NAME}`` replaced by its value, again inside what it was replaced by; an unknown name stays."""
    if depth > 4 or "${" not in text:
        return text
    return re.sub(r"\$\{([^}]+)\}", lambda match: expand(variables[match.group(1)], variables, depth + 1)
                  if match.group(1) in variables else match.group(0), text)


def drawing_sheet(tree: list, *, file_name: str, project: Path | None = None) -> tuple[list[SheetLine], list[SheetText], tuple[float, float, float, float]]:
    """The board's drawing sheet: its lines (the page's edge among them), its texts, and the page's box."""
    _paper, width, height = page_size(tree)
    lt, rb = (_MARGIN, _MARGIN), (width - _MARGIN, height - _MARGIN)
    variables = title_variables(tree, file_name=file_name, project=project)

    def page_box(*firsts: XY) -> tuple[float, float, float, float]:
        # KiCad's ``IsInsidePage``: the frame, grown to take the run's first place (which may lie in the
        # margin); a repeat is drawn while it stays inside.
        xs, ys = [lt[0], rb[0], *(p[0] for p in firsts)], [lt[1], rb[1], *(p[1] for p in firsts)]
        return min(xs), min(ys), max(xs), max(ys)

    def inside(point: XY, area: tuple[float, float, float, float]) -> bool:
        return area[0] - 1e-9 <= point[0] <= area[2] + 1e-9 and area[1] - 1e-9 <= point[1] <= area[3] + 1e-9

    lines: list[SheetLine] = [SheetLine(a, b, 0.0, page=True) for a, b in (
        ((0.0, 0.0), (width, 0.0)), ((width, 0.0), (width, height)), ((width, height), (0.0, height)), ((0.0, height), (0.0, 0.0)))]
    for shapes, rect in ((_LINES, False), (_RECTS, True)):
        for start, end, repeat, increment in shapes:
            area = page_box(_corner(start, 0, increment, lt, rb), _corner(end, 0, increment, lt, rb))
            for step in range(repeat):
                a, b = _corner(start, step, increment, lt, rb), _corner(end, step, increment, lt, rb)
                if step and not (inside(a, area) and inside(b, area)):
                    continue
                if rect:
                    corners = [a, (b[0], a[1]), b, (a[0], b[1])]
                    lines.extend(SheetLine(corners[k], corners[(k + 1) % 4], _LINE) for k in range(4))
                else:
                    lines.append(SheetLine(a, b, _LINE))
    texts: list[SheetText] = []
    for label, position, size, bold, italic, centred, repeat, increment in _TEXTS:
        area = page_box(_corner(position, 0, increment, lt, rb))
        for step in range(repeat):
            at = _corner(position, step, increment, lt, rb)
            if step and not inside(at, area):
                continue
            text = expand(_counted(label, step), variables)
            if text.strip():
                texts.append(SheetText(text, at, size, size / 5 if bold else _TEXT_LINE, bold, italic, centred))
    return lines, texts, (0.0, 0.0, width, height)
