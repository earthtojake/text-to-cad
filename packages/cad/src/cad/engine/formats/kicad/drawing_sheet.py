"""KiCad's default drawing sheet (its page frame and title block) as plot items, for one page.

KiCad prints every schematic page on a drawing sheet: a ``.kicad_wks`` description, by default the one
built into KiCad (pl_editor's default, ``drawing_sheet_default_description.cpp``). :func:`drawing_sheet_items`
lays that default out on a page of a given size: the frame (two rectangles, at the 10 mm margin and 2 mm
inside it, with the column numbers along the top and bottom and the row letters down both sides every
50 mm, as many as the page holds), every item of it flagged ``frame``, and the title block in the
bottom-right corner (its box, rows and dividers, and its texts with their ``${...}`` variables
substituted from ``values``). Positions are KiCad's: each from a corner of the margin rectangle (the
bottom-right unless the item names another), x and y measured inward from that corner; a repeated item
steps inward and stops at the first that leaves the margin rectangle. Text is the stroke font's with its
markup drawn; a text that substitutes to nothing draws nothing.

Pure: the page's size and the variables in, plot items (the plot payload's ``path`` and ``text``) out.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from cad.engine.formats.kicad.stroke_font import text_strokes

__all__ = ["MARGIN", "drawing_sheet_items"]

MARGIN = 10.0  # every side's margin, mm
_TEXT_SIZE = 1.5
_LINE_WIDTH = 0.15
_TEXT_LINE_WIDTH = 0.15

# (start, end, corner of both, repeat, (incrx, incry)), the default's lines and its frame's rectangles.
_FRAME_RECTS = (((0, 0, "lt"), (0, 0, "rb"), 2, (2, 2)),)
_FRAME_LINES = (
    ((50, 2), (50, 0), "lt", 30, (50, 0)), ((50, 2), (50, 0), "lb", 30, (50, 0)),
    ((0, 50), (2, 50), "lt", 30, (0, 50)), ((0, 50), (2, 50), "rt", 30, (0, 50)),
)
# (first label, position, corner, justify, repeat, (incrx, incry)): the column numbers and row letters.
_FRAME_TEXTS = (
    ("1", (25, 1), "lt", "left", 100, (50, 0)), ("1", (25, 1), "lb", "left", 100, (50, 0)),
    ("A", (1, 25), "lt", "center", 100, (0, 50)), ("A", (1, 25), "rt", "center", 100, (0, 50)),
)
_FRAME_TEXT_SIZE = 1.3
_TITLE_RECT = ((110, 34), (2, 2))
_TITLE_LINES = (((110, 5.5), (2, 5.5)), ((110, 8.5), (2, 8.5)), ((110, 12.5), (2, 12.5)), ((110, 18.5), (2, 18.5)),
                ((90, 8.5), (90, 5.5)), ((26, 8.5), (26, 2)))
# (text, position from the bottom-right corner, size, bold, italic), each left-justified and centred on its row.
_TITLE_TEXTS = (
    ("Date: ${ISSUE_DATE}", (87, 6.9), _TEXT_SIZE, False, False),
    ("${KICAD_VERSION}", (109, 4.1), _TEXT_SIZE, False, False),
    ("Rev: ${REVISION}", (24, 6.9), _TEXT_SIZE, True, False),
    ("Size: ${PAPER}", (109, 6.9), _TEXT_SIZE, False, False),
    ("Id: ${#}/${##}", (24, 4.1), _TEXT_SIZE, False, False),
    ("Title: ${TITLE}", (109, 10.7), 2.0, True, True),
    ("File: ${FILENAME}", (109, 14.3), _TEXT_SIZE, False, False),
    ("Sheet: ${SHEETPATH}", (109, 17), _TEXT_SIZE, False, False),
    ("${COMPANY}", (109, 20), _TEXT_SIZE, True, False),
    ("${COMMENT1}", (109, 23), _TEXT_SIZE, False, False),
    ("${COMMENT2}", (109, 26), _TEXT_SIZE, False, False),
    ("${COMMENT3}", (109, 29), _TEXT_SIZE, False, False),
    ("${COMMENT4}", (109, 32), _TEXT_SIZE, False, False),
)
_VARIABLE = re.compile(r"\$\{([^}]*)\}")


def _r(value: float) -> float:
    return round(float(value), 4) + 0.0


def substitute(text: str, values: Mapping[str, str]) -> str:
    """``text`` with each ``${NAME}`` that ``values`` knows replaced; an unknown one stays as written."""
    return _VARIABLE.sub(lambda found: str(values[found.group(1)]) if found.group(1) in values else found.group(0), text)


def drawing_sheet_items(width: float, height: float, values: Mapping[str, str]) -> list[dict[str, Any]]:
    """KiCad's default drawing sheet on a ``width`` by ``height`` page (mm, y down), its variables from
    ``values`` (``TITLE``, ``ISSUE_DATE``, ``REVISION``, ``COMPANY``, ``COMMENT1``.., ``PAPER``,
    ``FILENAME``, ``SHEETPATH``, ``KICAD_VERSION``, ``#``, ``##``): the module doc."""
    left, top, right, bottom = MARGIN, MARGIN, width - MARGIN, height - MARGIN

    def place(point, corner: str) -> tuple[float, float]:
        x, y = point
        return left + x if corner[0] == "l" else right - x, top + y if corner[1] == "t" else bottom - y

    def inside(point) -> bool:
        return left - 1e-9 <= point[0] <= right + 1e-9 and top - 1e-9 <= point[1] <= bottom + 1e-9

    def path(points, **flags) -> dict[str, Any]:
        closed = len(points) > 2 and points[0] == points[-1]
        return {"t": "path", "pts": [[_r(x), _r(y)] for x, y in points], "w": _LINE_WIDTH,
                **({"closed": True} if closed else {}), **flags}

    def text(content: str, at, size: float, justify: str, *, bold: bool = False, italic: bool = False,
             **flags) -> dict[str, Any] | None:
        if not content.strip():
            return None
        strokes = text_strokes(content, size=(size, size), at=at, justify=[justify] if justify != "center" else [],
                               italic=italic, markup=True)
        if not strokes:
            return None
        return {"t": "text", "text": content, "w": _r(size / 5 if bold else _TEXT_LINE_WIDTH),
                "strokes": [[[round(x, 3) + 0.0, round(y, 3) + 0.0] for x, y in stroke] for stroke in strokes], **flags}

    items: list[dict[str, Any]] = []
    for (sx, sy, start_corner), (ex, ey, end_corner), repeat, (dx, dy) in _FRAME_RECTS:
        for step in range(repeat):
            a = place((sx + dx * step, sy + dy * step), start_corner)
            b = place((ex + dx * step, ey + dy * step), end_corner)
            if step and not (inside(a) and a[0] < b[0] and a[1] < b[1]):
                break
            items.append(path([a, (b[0], a[1]), b, (a[0], b[1]), a], frame=True))
    for start, end, corner, repeat, (dx, dy) in _FRAME_LINES:
        for step in range(repeat):
            a = place((start[0] + dx * step, start[1] + dy * step), corner)
            if not inside(a):
                break
            items.append(path([a, place((end[0] + dx * step, end[1] + dy * step), corner)], frame=True))
    for first, at, corner, justify, repeat, (dx, dy) in _FRAME_TEXTS:
        for step in range(repeat):
            point = place((at[0] + dx * step, at[1] + dy * step), corner)
            if not inside(point):
                break
            # KiCad's IncrementLabel: a digit counts on as a number, a letter as the letters after it.
            label = str(int(first) + step) if first.isdigit() else chr(ord(first) + step)
            item = text(label, point, _FRAME_TEXT_SIZE, justify, frame=True)
            if item:
                items.append(item)
    (sx, sy), (ex, ey) = _TITLE_RECT
    a, b = place((sx, sy), "rb"), place((ex, ey), "rb")
    items.append(path([a, (b[0], a[1]), b, (a[0], b[1]), a]))
    for start, end in _TITLE_LINES:
        items.append(path([place(start, "rb"), place(end, "rb")]))
    for content, at, size, bold, italic in _TITLE_TEXTS:
        item = text(substitute(content, values), place(at, "rb"), size, "left", bold=bold, italic=italic)
        if item:
            items.append(item)
    return items
