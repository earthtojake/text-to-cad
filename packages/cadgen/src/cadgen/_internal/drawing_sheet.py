"""The sheet: its frame, title block and parts-list table, where the views go
on it, and the size and scale a sheet that chooses its own settles on.

Part of :mod:`cadgen.eng_drawing`; nothing here imports the kernel or ezdxf at
module scope.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, NamedTuple, Sequence

from cadgen._internal.drawing_base import (
    _DIM_ROW, _FLAG_SIDE, _MARGIN, _MIN_TEXT_MM, _NOTE_HEIGHT, _NOTE_INSET, SHEET_SIZES, _STANDARD_SCALES, _TITLE_H,
    _TITLE_W, _draw_flag, _scale_label, _text_width,
)
from cadgen._internal.drawing_gdt import _draw_frame
from cadgen._internal.drawing_views import _broken_size

if TYPE_CHECKING:
    from cadgen.eng_drawing import Sheet


#: The least clear space between two views, and the air left between one view's
#: annotation and the next view's.
_MIN_GAP = 20.0
_AIR = 8.0
#: What a view's annotation is assumed to need before its dimensions are known:
#: two rows above and to the left, a label below. Only the positions
#: :meth:`Sheet.three_views` hands back at once use it; the render lays the sheet
#: out again from what each view actually carries.
_DEFAULT_ROOM = {"top": 2 * _DIM_ROW + 5.0, "bottom": 12.0, "left": 2 * _DIM_ROW + 5.0, "right": 12.0}
#: The principal views a standard arrangement can hold, in the order it gives them.
_VIEW_NAMES = ("top", "front", "right")


class _Arrangement(NamedTuple):
    """One standard arrangement, shared by its views: the part's box size, a gap
    the author fixed (or None), the isometric's 1:1 extent (or False) and the
    principal views it draws. The render lays the views out again from it, and
    the off-frame guard does at each candidate scale."""

    size: Any
    gap: float | None
    iso: Any
    names: tuple[str, ...]


def _arrange_three_views(sheet: "Sheet", size, gap: float | None, s: float, iso, room: dict | None = None,
                         paper: str | None = None, names: tuple[str, ...] = _VIEW_NAMES
                         ) -> tuple[list[tuple[str, tuple[float, float], float | None, str | None]], tuple[float, float]]:
    """Where the three (or four) views of a standard arrangement go at scale ``s``.

    ``room`` is what each view's annotation takes on every side, in sheet
    millimetres -- its dimension rows, its hole callouts, the label underneath --
    so the space between two views is what their facing sides need, not one
    figure for every sheet. A front view with three rows of dimensions above it
    pushes the top view up instead of printing its outermost row over the top
    view's label. A ``gap`` the author gives is used as is. When the room asked
    for does not fit the paper, the gaps give it back first, down to
    ``_MIN_GAP``, and anything that still collides is reported by the render.

    Separate from :meth:`Sheet.three_views` so the off-frame guard can ask the
    same question of a candidate scale: the views shrink with the scale and
    their annotation does not. ``iso`` is False, or the isometric's projected
    (width, height) at 1:1, measured once by the caller: it is a hidden-line
    projection, and the guard asks this question at every candidate scale.

    ``names`` are the principal views drawn; the others keep their places empty,
    so a front and right view sit where they would beside a top view.

    Returns the views' slots, and how far the arrangement overran the paper,
    ``(width, height)``, before the gaps gave room back: both 0 when it fits.
    """
    L, W, H = size.X * s, size.Y * s, size.Z * s
    need = {name: dict(_DEFAULT_ROOM) for name in ("top", "front", "right")}
    for name, value in (room or {}).items():
        if name in need:
            need[name] = dict(value)
    third = sheet.projection == "THIRD ANGLE"
    if gap is not None:
        gap_v = gap_h = gap
    elif third:
        gap_v = max(_MIN_GAP, need["top"]["bottom"] + need["front"]["top"] + _AIR)
        gap_h = max(_MIN_GAP, need["front"]["right"] + need["right"]["left"] + _AIR)
    else:
        gap_v = max(_MIN_GAP, need["front"]["bottom"] + need["top"]["top"] + _AIR)
        gap_h = max(_MIN_GAP, need["right"]["right"] + need["front"]["left"] + _AIR)
    m = _MARGIN
    x_lo, x_hi, y_lo, y_hi = _free_band(sheet, paper)
    sheet_w, sheet_h = SHEET_SIZES[paper or sheet._size()]
    sizes = {"top": (L, W), "front": (L, H), "right": (W, H)}

    def place(gv: float, gh: float):
        if third:
            centres = {"front": (L / 2, H / 2), "top": (L / 2, H + gv + W / 2), "right": (L + gh + W / 2, H / 2)}
        else:
            # First angle places each view on the side opposite the one it looks
            # from: the plan below the front, the view from the right to its left.
            # The pictures are the third-angle pictures; only the slots swap.
            centres = {"right": (W / 2, W + gv + H / 2), "front": (W + gh + L / 2, W + gv + H / 2),
                       "top": (W + gh + L / 2, W / 2)}
        centres = {n: c for n, c in centres.items() if n in names}
        boxes = [(cx - sizes[n][0] / 2 - need[n]["left"], cx + sizes[n][0] / 2 + need[n]["right"],
                  cy - sizes[n][1] / 2 - need[n]["bottom"], cy + sizes[n][1] / 2 + need[n]["top"])
                 for n, (cx, cy) in centres.items()]
        block = (min(b[0] for b in boxes), max(b[1] for b in boxes),
                 min(b[2] for b in boxes), max(b[3] for b in boxes))
        return centres, block

    centres, block = place(gap_v, gap_h)
    over_w = (block[1] - block[0]) - (x_hi - x_lo)
    over_h = (block[3] - block[2]) - (y_hi - y_lo)
    over = (max(0.0, over_w), max(0.0, over_h))
    if gap is None and max(over) > 0:
        centres, block = place(max(_MIN_GAP, gap_v - over[1]), max(_MIN_GAP, gap_h - over[0]))
    # Centred in the paper the views and their annotation leave free; a block that
    # does not fit starts at the bottom-left, so it is the top and right that run
    # off and the guard names a scale. With a pictorial the block keeps to the
    # left, as a print does, and the right of the sheet is the pictorial's.
    slack_w = max(0.0, (x_hi - x_lo) - (block[1] - block[0]))
    dx = x_lo - block[0] + (min(slack_w / 2, 12.0) if iso else slack_w / 2)
    dy = y_lo - block[2] + max(0.0, ((y_hi - y_lo) - (block[3] - block[2])) / 2)
    at = {n: (cx + dx, cy + dy) for n, (cx, cy) in centres.items()}
    slots: list[tuple[str, tuple[float, float], float | None, str | None]] = [
        (n, at[n], None, None) for n in _VIEW_NAMES if n in names]
    if not iso:
        return slots, over
    # Where the pictorial can go: the corner right of the upper row's annotation
    # (above the right view's, in third angle), the row a front with no view above
    # it leaves empty, or the full height right of every view. It takes whichever
    # draws it larger, at the sheet's scale if it fits, else at the largest
    # STANDARD scale that does: a pictorial still states its scale, and 1:1.17 is
    # not one anybody can use.
    upper = "top" if third else "front"
    label_room = 12.0  # the pictorial's own label hangs under it
    # The revision table, when there is one, owns the top-right corner.
    x_top, y_top = sheet_w - m - 6.0, sheet_h - m - 6.0 - _revisions_height(sheet)
    iso_w, iso_h = iso

    def fit_in(region) -> float:
        x0, y0 = region
        return min((x_top - x0) / iso_w if iso_w else s, (y_top - y0) / iso_h if iso_h else s)

    def regions_at(at: dict) -> list[tuple[float, float]]:
        rightmost = max(at[n][0] + sizes[n][0] / 2 + need[n]["right"] for n in at) + 4.0
        found = [(rightmost, y_lo + label_room)]
        if upper in at:
            upper_w, upper_h = sizes[upper]
            upper_right = at[upper][0] + upper_w / 2 + need[upper]["right"] + 4.0
            corner_bottom = at[upper][1] - upper_h / 2
            if third and "right" in at:
                corner_bottom = max(corner_bottom, at["right"][1] + H / 2 + need["right"]["top"] + 4.0)
            found.insert(0, (upper_right, corner_bottom + label_room))
        elif "front" in at:
            front_w, front_h = sizes["front"]
            found.append((at["front"][0] - front_w / 2 - need["front"]["left"],
                          at["front"][1] + front_h / 2 + need["front"]["top"] + 4.0 + label_room))
        return found

    x_free, y_free = max(regions_at(at), key=fit_in)
    fit = fit_in((x_free, y_free))
    if fit < s and upper not in at and "front" in at:
        # The views kept to the foot of the paper leave the empty row above the
        # front its full height: where that draws the pictorial larger, they go there.
        low = {n: (x, y - (dy - (y_lo - block[2]))) for n, (x, y) in at.items()}
        region = max(regions_at(low), key=fit_in)
        if fit_in(region) > fit:
            at, (x_free, y_free), fit = low, region, fit_in(region)
            slots = [(n, at[n], None, None) for n in _VIEW_NAMES if n in names]
    iso_scale = s if fit >= s else next((c for c in _STANDARD_SCALES if c <= max(fit, s / 5)),
                                        _STANDARD_SCALES[-1])
    w, h = iso_w * iso_scale, iso_h * iso_scale
    iso_at = (x_free + max(0.0, (x_top - x_free - w) / 2) + w / 2,
              y_free + max(0.0, (y_top - y_free - h) / 2) + h / 2)
    own = None if abs(iso_scale / s - 1) < 1e-9 else iso_scale
    # The label states the scale the pictorial was DRAWN at, not its ratio to the
    # sheet: at 2:1 a half-size iso is 1:1, and calling it "1:2" claimed a
    # reduction from full size that never happened.
    slots.append(("iso", iso_at, own, "ISOMETRIC" if own is None else f"ISOMETRIC {_scale_label(iso_scale)}"))
    return slots, over


class _OffFrame(ValueError):
    """Views that run off the frame, with the largest standard scale that fits
    them (``fits``, None when none does)."""

    def __init__(self, message: str, fits: float | None) -> None:
        super().__init__(message)
        self.fits = fits


class _Crowded(ValueError):
    """Two values that would print in one place. On a sheet the author laid out,
    which gives way is the author's call; one choosing its own size takes more
    paper first."""


def _assert_views_fit(sheet: Sheet, placed: Sequence[tuple], *, index: int, groups: Sequence[tuple] = ()) -> None:
    """Refuse a sheet whose views run off the frame, naming the scale that fits.

    A part far larger than the paper still writes valid geometry -- out at
    x = 4284 on a 420 mm sheet -- and the render then crops to a near-empty page.
    Nothing downstream can tell that from a drawing of a small feature, so the
    script stops here, at the one place that knows both extents.
    """
    m = _MARGIN
    frame = (m, sheet.width - m, m, sheet.height - m)
    over = []
    for view, _proj, _bounds, _cx, _cy, box in placed:
        if box[0] < frame[0] or box[1] > frame[1] or box[2] < frame[2] or box[3] > frame[3]:
            over.append((view, box))
    if not over:
        return
    # Lay the sheet out again at each smaller standard scale and name the first that
    # actually fits. Dividing the overflow out instead -- usable width over the union
    # width -- treats the whole arrangement as if it scaled, and the room between
    # views and the annotation around them do not: three of four ordinary part
    # sizes then needed two refusals before a scale rendered, each naming another
    # that did not fit either.
    fits = next((candidate for candidate in _STANDARD_SCALES
                 if candidate < sheet._scale() and _fits_at(sheet, placed, candidate, frame, groups)), None)
    names = ", ".join(sorted({view.name for view, _ in over}))
    remedy = (f"Use Sheet(scale={fits:g}) ({_scale_label(fits)}), a larger sheet size, or place the "
              "views closer." if fits is not None else
              f"No standard scale down to {_scale_label(_STANDARD_SCALES[-1])} fits this part on "
              f"{sheet._size()}; use a larger sheet size, or fewer views.")
    raise _OffFrame(
        f"sheet {index} ({sheet._size()}, scale {_scale_label(sheet._scale())}): the {names} view"
        f"{'s run' if len(over) > 1 else ' runs'} off the frame. {remedy}", fits)


def _fits_at(sheet: Sheet, placed: Sequence[tuple], candidate: float, frame, groups: Sequence[tuple]) -> bool:
    """Would every view sit inside the frame if the sheet were drawn at `candidate`?

    A standard arrangement is laid out again, because the views move when they
    shrink; ``groups`` carries each one's (views by name, shape, size, gap, iso,
    room, names).
    A hand-placed view keeps its ``at=``, which is what would happen, and only
    its box shrinks about that point.
    """
    moved: dict[int, tuple[tuple[float, float], float]] = {}
    for by_name, _shape, size, gap, iso, room, names in groups:
        for name, at, own, _label in _arrange_three_views(sheet, size, gap, candidate, iso, room, names=names)[0]:
            if name in by_name:
                moved[id(by_name[name])] = (at, own or candidate)
    for view, _proj, bounds, _cx, _cy, _box in placed:
        at, scale = moved.get(id(view), (view.at, view.scale or candidate))
        half_w = (bounds[1] - bounds[0]) * scale / 2
        half_h = (bounds[3] - bounds[2]) * scale / 2
        if (at[0] - half_w < frame[0] or at[0] + half_w > frame[1]
                or at[1] - half_h < frame[2] or at[1] + half_h > frame[3]):
            return False
    return True


#: The title block's cells as (x, y, width, height), millimetres from its
#: bottom-left corner: ISO 7200's fields in the arrangement shops read -- what the
#: part is and its number across the top, what it is made of and the scale in the
#: middle, who drew it, in what unit and projection, along the bottom. A field the
#: author did not give stays an empty, captioned cell: a blank MATERIAL says the
#: drawing does not state one, where a missing cell says nothing at all.
_TITLE_CELLS = {
    "TITLE": (0.0, 20.0, 110.0, 20.0),
    "DWG NO.": (110.0, 30.0, 70.0, 10.0),
    "REV": (110.0, 20.0, 30.0, 10.0),
    "SHEET": (140.0, 20.0, 40.0, 10.0),
    "MATERIAL": (0.0, 10.0, 60.0, 10.0),
    "FINISH": (60.0, 10.0, 50.0, 10.0),
    "SCALE": (110.0, 10.0, 30.0, 10.0),
    "SIZE": (140.0, 10.0, 40.0, 10.0),
    "DRAWN": (0.0, 0.0, 40.0, 10.0),
    "DATE": (40.0, 0.0, 30.0, 10.0),
    "UNITS": (70.0, 0.0, 40.0, 10.0),
    "PROJECTION": (110.0, 0.0, 70.0, 10.0),
}
#: The band across the top: who the drawing is by and how far along it is. A
#: profile's own cells take the middle of it (:func:`_band_cells`).
_BAND_CELLS = {
    "COMPANY": (0.0, 40.0, 110.0, 10.0),
    "STAGE": (110.0, 40.0, 70.0, 10.0),
}
#: The grid between those cells, drawn as lines so no edge is written twice.
_TITLE_RULES = (
    ((0.0, 10.0), (180.0, 10.0)), ((0.0, 20.0), (180.0, 20.0)), ((110.0, 30.0), (180.0, 30.0)),
    ((110.0, 0.0), (110.0, 40.0)), ((60.0, 10.0), (60.0, 20.0)), ((40.0, 0.0), (40.0, 10.0)),
    ((70.0, 0.0), (70.0, 10.0)), ((140.0, 10.0), (140.0, 30.0)),
)


def _band_cells(sheet: Sheet) -> dict[str, tuple[float, float, float, float]]:
    """The top band's cells: COMPANY and STAGE, with the profile's own cells
    sharing the space between them; none on a sheet that states no stage,
    profile or company."""
    if not sheet._banded():
        return {}
    extra = sheet.profile.fields if sheet.profile is not None else ()
    if not extra:
        return _BAND_CELLS
    width = 70.0 / len(extra)
    return {"COMPANY": (0.0, 40.0, 70.0, 10.0),
            **{name: (70.0 + i * width, 40.0, width, 10.0) for i, name in enumerate(extra)},
            "STAGE": (140.0, 40.0, 40.0, 10.0)}


#: Cap height of a cell's caption, and the width the title itself may take.
_CAPTION_HEIGHT = 1.8
_TITLE_FIT = _TITLE_CELLS["TITLE"][2] - 6.0
#: ISO 5457 zone letters: I and O are left out, being read as 1 and 0.
_ZONE_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"
#: A parts list: its row height and its columns, which together span the title
#: block's width so the list stands on the block as one column of the sheet.
_LIST_ROW = 7.0
#: Each column's usual share of the list's width; a column takes what its widest
#: entry needs, and the room left over is shared out in these proportions.
_LIST_COLUMNS = (("ITEM", 10.0), ("QTY", 10.0), ("DESCRIPTION", 50.0), ("PART NO.", 30.0), ("MATERIAL", 30.0),
                 ("SPEC", 30.0), ("SUPPLIER", 20.0))
#: In a set with each part's own sheet, the list says which sheet that is.
_SHEET_COLUMN = ("SHEET", 10.0)
#: The columns of numbers, centred in their narrow cells.
_COUNTED = ("ITEM", "QTY", "SHEET")
#: The revision table, top right inside the frame: its row height and columns.
_REVISION_ROW = 6.0
_REVISION_COLUMNS = (("REV", 14.0), ("DATE", 26.0), ("DESCRIPTION", 70.0))


def _list_room(sheet: Sheet) -> float:
    """The height a parts list may take above the title block: the frame, less
    the block, a row for the line saying where a long list continues, and air."""
    box = _revisions_box(sheet)
    revisions = box[3] - box[2] + 4.0 if box is not None else 0.0
    return sheet.height - 2 * _MARGIN - sheet._title_height() - _LIST_ROW - 4.0 - revisions


def _list_height(sheet: Sheet) -> float:
    """How far a sheet's parts list rises above its title block, its caption row
    included; 0 without one."""
    if sheet._parts is None:
        return 0.0
    parts, first, last = sheet._parts
    partial = first > 1 or last < len(parts)
    return (last - first + 2) * _LIST_ROW + (_LIST_ROW if partial else 0.0)


def _list_widths(rows: list[tuple[str, ...]], columns: tuple = _LIST_COLUMNS) -> list[float] | None:
    """The parts list's column widths for its entries: each as wide as its widest
    entry needs, the room left over shared out as the columns usually take it;
    where that is more than the list's width, as the entries need at the smallest
    legible text. None when even that does not fit."""
    def need(c: int, height: float) -> float:
        head = _text_width(columns[c][0], _CAPTION_HEIGHT) + 2.4
        return max([head] + [_text_width(row[c], height) + 3.0 for row in rows if row[c]])

    full = [need(c, 2.5) for c in range(len(columns))]
    if sum(full) <= _TITLE_W:
        spare, usual = _TITLE_W - sum(full), sum(width for _name, width in columns)
        return [f + spare * width / usual for f, (_name, width) in zip(full, columns)]
    least = [need(c, _MIN_TEXT_MM) for c in range(len(columns))]
    if sum(least) > _TITLE_W:
        return None
    room, wants = _TITLE_W - sum(least), [f - m for f, m in zip(full, least)]
    return [m + room * want / sum(wants) for m, want in zip(least, wants)]


def _draw_parts_list(msp, sheet: Sheet, text, continued: dict) -> None:
    """The parts list, standing on the title block: header row at the bottom,
    item numbers rising from it. ``continued`` says on which sheet the rest of a
    split list is, ``{"from": n, "to": m}``, either or both, and on which each
    item is detailed, ``{"sheets": {item: sheet}}``: then a SHEET column says so."""
    from ezdxf.enums import TextEntityAlignment as A

    parts, first, last = sheet._parts
    fields = {"DESCRIPTION": "description", "PART NO.": "part_number", "MATERIAL": "material", "SPEC": "spec",
              "SUPPLIER": "supplier"}
    items = parts.items[first - 1:last]
    detailed = continued.get("sheets", {})
    columns = _LIST_COLUMNS + ((_SHEET_COLUMN,) if detailed else ())
    rows = [tuple(name for name, _w in columns)] + [
        (str(item.number), str(item.quantity), *(getattr(item, fields[name]) for name, _w in _LIST_COLUMNS[2:]),
         *((str(detailed.get(item.number, "")),) if detailed else ()))
        for item in items]
    widths = _list_widths(rows[1:], columns)
    if widths is None:
        # Even at the smallest legible text the entries need more than the list's
        # width: name the longest, as cutting it would state something else.
        entry = max(((item, name, value) for item, row in zip(items, rows[1:])
                     for (name, _w), value in zip(columns, row) if name in fields and value),
                    key=lambda t: _text_width(t[2], _MIN_TEXT_MM))
        item, name, value = entry
        raise ValueError(
            f"item {item.number}'s {name} {value!r} does not fit the parts list, {_TITLE_W:.0f} mm wide like the "
            "title block it stands on, even at the smallest legible text, and a parts list cut short is wrong. "
            f"Shorten it: parts.set({item.number}, {fields[name]}=...)."
        )
    x0, y0 = sheet.width - _MARGIN - _TITLE_W, _MARGIN + sheet._title_height()
    top = y0 + len(rows) * _LIST_ROW
    msp.add_lwpolyline([(x0, y0), (x0 + _TITLE_W, y0), (x0 + _TITLE_W, top), (x0, top)], close=True,
                       dxfattribs={"layer": "TITLE"})
    for r in range(1, len(rows)):
        msp.add_line((x0, y0 + r * _LIST_ROW), (x0 + _TITLE_W, y0 + r * _LIST_ROW), dxfattribs={"layer": "TITLE"})
    x = x0
    for c, width in enumerate(widths):
        if c:
            msp.add_line((x, y0), (x, top), dxfattribs={"layer": "TITLE"})
        for r, row in enumerate(rows):
            if not row[c]:
                continue
            mid = y0 + (r + 0.5) * _LIST_ROW
            if columns[c][0] in _COUNTED:
                text(row[c], x + width / 2, mid, _CAPTION_HEIGHT if r == 0 else 2.5, A.MIDDLE_CENTER, fit=width - 2)
            else:
                text(row[c], x + 1.5, mid, _CAPTION_HEIGHT if r == 0 else 2.5, A.MIDDLE_LEFT, fit=width - 3)
        x += width
    words = [f"CONTINUED FROM SHEET {continued['from']}" if "from" in continued else "",
             f"CONTINUED ON SHEET {continued['to']}" if "to" in continued else ""]
    if any(words):
        text("PARTS LIST, " + ", ".join(w for w in words if w), x0, top + 2.0, 2.5, A.BOTTOM_LEFT, fit=_TITLE_W)


def _draw_furniture(msp, sheet: Sheet, *, index: int, count: int, label: str, text,
                    continued: dict | None = None) -> None:
    """Frame, zone grid, title block, notes and any parts list: what makes a page a
    drawing sheet."""
    from ezdxf.enums import TextEntityAlignment as A

    W, H, m = sheet.width, sheet.height, _MARGIN
    msp.add_lwpolyline([(m, m), (W - m, m), (W - m, H - m), (m, H - m)], close=True, dxfattribs={"layer": "SHEET"})
    # Zones (ISO 5457): numbered columns along the top and bottom, lettered rows
    # down both sides, about 50 mm each and an even count, so a note can say
    # "see C4" and a reader finds it. The marks at the middle of each side run to
    # the paper's edge: they are the centring marks a scan or a reproduction is
    # aligned by.
    cols, rows = max(2, 2 * round(W / 100)), max(2, 2 * round(H / 100))
    for i in range(1, cols):
        x = m + i * (W - 2 * m) / cols
        reach = m if 2 * i == cols else 5.0
        msp.add_line((x, H - m), (x, H - m + reach), dxfattribs={"layer": "SHEET"})
        msp.add_line((x, m), (x, m - reach), dxfattribs={"layer": "SHEET"})
    for j in range(1, rows):
        y = m + j * (H - 2 * m) / rows
        reach = m if 2 * j == rows else 5.0
        msp.add_line((m, y), (m - reach, y), dxfattribs={"layer": "SHEET"})
        msp.add_line((W - m, y), (W - m + reach, y), dxfattribs={"layer": "SHEET"})
    for i in range(cols):
        x = m + (i + 0.5) * (W - 2 * m) / cols
        text(str(i + 1), x, H - m / 2, 3.0, A.MIDDLE_CENTER)
        text(str(i + 1), x, m / 2, 3.0, A.MIDDLE_CENTER)
    for j in range(rows):
        y = H - m - (j + 0.5) * (H - 2 * m) / rows
        text(_ZONE_LETTERS[j], m / 2, y, 3.0, A.MIDDLE_CENTER)
        text(_ZONE_LETTERS[j], W - m / 2, y, 3.0, A.MIDDLE_CENTER)

    x0, y0 = W - m - _TITLE_W, m
    tall = sheet._title_height()
    msp.add_lwpolyline([(x0, y0), (x0 + _TITLE_W, y0), (x0 + _TITLE_W, y0 + tall), (x0, y0 + tall)],
                       close=True, dxfattribs={"layer": "TITLE"})
    band = _band_cells(sheet)
    for (ax, ay), (bx, by) in _TITLE_RULES:
        msp.add_line((x0 + ax, y0 + ay), (x0 + bx, y0 + by), dxfattribs={"layer": "TITLE"})
    if band:
        msp.add_line((x0, y0 + _TITLE_H), (x0 + _TITLE_W, y0 + _TITLE_H), dxfattribs={"layer": "TITLE"})
    for x, y, _w, h in list(band.values())[1:]:
        msp.add_line((x0 + x, y0 + y), (x0 + x, y0 + y + h), dxfattribs={"layer": "TITLE"})
    values = {
        "DWG NO.": (sheet.part_number, 3.5), "REV": (sheet.revision, 2.5), "SHEET": (f"{index} OF {count}", 2.5),
        "MATERIAL": (sheet._material_label(), 2.5), "FINISH": (sheet.finish, 2.5),
        "SCALE": (_scale_label(sheet._scale()), 2.5), "SIZE": (sheet._size(), 2.5),
        "DRAWN": (sheet.author, 2.5), "DATE": (sheet.date, 2.5), "UNITS": (sheet.units.upper(), 2.5),
        "COMPANY": (sheet.company, 2.5), "STAGE": (sheet._stage_label(), 2.5),
        **{name: (sheet.fields.get(name, ""), 2.5) for name in band if name not in _BAND_CELLS},
    }
    for name, (x, y, w, h) in {**_TITLE_CELLS, **band}.items():
        value = values.get(name, ("", 0.0))[0]
        if value and _text_width(str(value), _MIN_TEXT_MM) > w - 3.0:
            # A long title may end inside its cell; a material, a spec or a number
            # cut short states a different one.
            raise ValueError(f"the title block's {name} {value!r} does not fit its {w:.0f} mm cell even at the "
                             f"smallest legible text, and a value cut short is wrong; shorten it")
    for name, (x, y, w, h) in {**_TITLE_CELLS, **band}.items():
        if name == "PROJECTION":
            continue  # the symbol is its own caption
        text(name, x0 + x + 1.2, y0 + y + h - 1.0, _CAPTION_HEIGHT, A.TOP_LEFT, fit=w - 2.4)
        if name in values and values[name][0]:
            value, height = values[name]
            text(str(value), x0 + x + 1.5, y0 + y + 1.6, height, A.BOTTOM_LEFT, fit=w - 3.0)
    tx, ty, _tw, th = _TITLE_CELLS["TITLE"]
    # A subtitle takes the line under the title, which moves up to make room.
    text(sheet.title, x0 + tx + 3.0, y0 + ty + th / 2 + (2.5 if sheet.subtitle else 1.0), 5.0, A.MIDDLE_LEFT,
         fit=_TITLE_FIT)
    if sheet.subtitle:
        text(sheet.subtitle, x0 + tx + 3.0, y0 + ty + 4.2, 2.5, A.BOTTOM_LEFT, fit=_TITLE_FIT)
    # The script that drew the sheet, so a print leads back to its source.
    text(label, x0 + tx + 3.0, y0 + ty + 1.4, _CAPTION_HEIGHT, A.BOTTOM_LEFT, fit=_TITLE_FIT)
    px, py, pw, ph = _TITLE_CELLS["PROJECTION"]
    right = _projection_symbol(msp, x0 + px + 4.0, y0 + py + ph / 2, first_angle=sheet.projection == "FIRST ANGLE")
    text(sheet.projection, right + 4.0, y0 + py + ph / 2, 2.5, A.MIDDLE_LEFT, fit=x0 + px + pw - right - 6.0)

    base, rows = sheet._note_layout()
    if sheet._parts is not None:
        # The notes share the strip beside and above the title block with the
        # parts list, so each row must end before the list begins.
        room = x0 - 4.0 - (m + _NOTE_INSET)
        notes = sheet.drawn_notes()
        for row in rows:
            if sheet._row_width(row, rows) > room:
                raise ValueError(
                    f"note {notes[row[2]]!r} runs under the parts list: beside it the {sheet._size()} sheet leaves "
                    f"{round(room)} mm, and a word of it is longer. Shorten that word."
                )
        _draw_parts_list(msp, sheet, text, continued or {})
    flagged = len(sheet.drawn_notes()) - len(sheet._flags)
    for r, (dx, line, k, first) in enumerate(rows):
        y = y0 + base + 4 + (len(rows) - 1 - r) * 5
        text(line, m + _NOTE_INSET + dx, y, _NOTE_HEIGHT, A.BOTTOM_LEFT, "NOTES")
        if first and k >= flagged:
            # A flag note's number stands in its flag, where the others' are printed.
            at = m + _NOTE_INSET + _text_width(line[:8] + "X", _NOTE_HEIGHT) - _text_width("X", _NOTE_HEIGHT)
            _draw_flag(msp, str(k + 1), at, y + _NOTE_HEIGHT / 2, _FLAG_SIDE * _NOTE_HEIGHT, "NOTES")
        if k == 0 and sheet.general_profile is not None and (r + 1 == len(rows) or rows[r + 1][2] != 0):
            # Note 1's frame follows its words: every surface within this profile.
            _draw_frame(msp, sheet.general_profile,
                        m + _NOTE_INSET + dx + _text_width(line, _NOTE_HEIGHT) + _NOTE_HEIGHT,
                        y + _NOTE_HEIGHT / 2, _NOTE_HEIGHT, "NOTES")
    revisions = _revisions_box(sheet)
    if revisions is not None:
        rx, rx1, _ry0, ry1 = revisions
        rh = _REVISION_ROW
        table = [tuple(name for name, _w in _REVISION_COLUMNS)] + [tuple(str(v) for v in row) for row in sheet.revisions]
        for r, row in enumerate(table):
            y = ry1 - (r + 1) * rh
            msp.add_lwpolyline([(rx, y), (rx1, y), (rx1, y + rh), (rx, y + rh)], close=True,
                               dxfattribs={"layer": "TITLE"})
            x = rx
            for c, ((_name, width), value) in enumerate(zip(_REVISION_COLUMNS, row)):
                if c:
                    msp.add_line((x, y), (x, y + rh), dxfattribs={"layer": "TITLE"})
                text(value, x + 2, y + rh / 2, 2.5, A.MIDDLE_LEFT, fit=width - 4)
                x += width


def _projection_symbol(msp, x: float, y: float, *, first_angle: bool) -> float:
    """The ISO 5456-2 projection symbol with its left edge at ``x``, centred on
    ``y``; returns its right edge.

    It is a truncated cone drawn in the projection it names: its side view, wide
    end left, and its end view seen from the small end, where both circles show.
    Third angle places the view from the right on the right, so the circles sit
    right of the cone; first angle places it on the left. The cone is the same
    picture in both.
    """
    big, small, length, gap = 6.0, 3.0, 7.0, 3.0
    if first_angle:
        circles_x, cone_x = x + big / 2, x + big + gap
    else:
        cone_x, circles_x = x, x + length + gap + big / 2
    msp.add_lwpolyline([(cone_x, y - big / 2), (cone_x + length, y - small / 2), (cone_x + length, y + small / 2),
                        (cone_x, y + big / 2)], close=True, dxfattribs={"layer": "TITLE"})
    msp.add_circle((circles_x, y), big / 2, dxfattribs={"layer": "TITLE"})
    msp.add_circle((circles_x, y), small / 2, dxfattribs={"layer": "TITLE"})
    right = x + length + gap + big
    # Its axis, thin and on the title block's layer: it is part of the symbol, and
    # the CENTER layer holds the views' centre lines and nothing else.
    msp.add_line((x - 1.0, y), (right + 1.0, y), dxfattribs={"layer": "TITLE"})
    return right


#: A table the sheet carries on its paper (a material key, a layer table): its
#: row height, the room its caption takes above it, and the air in a cell.
_TABLE_ROW = 6.0
_TABLE_CAPTION = 5.0
_TABLE_AIR = 4.0


class _SheetTable(NamedTuple):
    """A captioned table on the sheet's paper: its column names, its rows, a swatch
    per row to draw in the first column (a material key's hatch: family and
    variant), and the point it goes nearest."""

    caption: str
    names: tuple[str, ...]
    rows: list[tuple[str, ...]]
    swatches: list[tuple[str, int]]
    near: tuple[float, float]

    def widths(self) -> list[float]:
        """Each column as wide as its widest entry: a table cut short is wrong."""
        return [max(_text_width(value, 2.5) if r else _text_width(value, _CAPTION_HEIGHT)
                    for r, value in enumerate((name, *(row[c] for row in self.rows)))) + _TABLE_AIR
                for c, name in enumerate(self.names)]

    def size(self) -> tuple[float, float]:
        return sum(self.widths()), (len(self.rows) + 1) * _TABLE_ROW + _TABLE_CAPTION


def _draw_sheet_table(msp, table: _SheetTable, corner: tuple[float, float], text) -> list:
    """The table, caption above and header on top. Returns each swatch cell as
    (family, (x0, y0, x1, y1)), for the caller to hatch."""
    from ezdxf.enums import TextEntityAlignment as A

    x0, y1 = corner
    widths = table.widths()
    w, h = sum(widths), (len(table.rows) + 1) * _TABLE_ROW
    top = y1 - _TABLE_CAPTION
    text(table.caption, x0, top + 1.5, 2.5, A.BOTTOM_LEFT, "NOTES")
    msp.add_lwpolyline([(x0, top), (x0 + w, top), (x0 + w, top - h), (x0, top - h)], close=True,
                       dxfattribs={"layer": "TITLE"})
    for r in range(1, len(table.rows) + 1):
        msp.add_line((x0, top - r * _TABLE_ROW), (x0 + w, top - r * _TABLE_ROW), dxfattribs={"layer": "TITLE"})
    swatches, x = [], x0
    for c, (name, width) in enumerate(zip(table.names, widths)):
        if c:
            msp.add_line((x, top), (x, top - h), dxfattribs={"layer": "TITLE"})
        text(name, x + width / 2, top - _TABLE_ROW / 2, _CAPTION_HEIGHT, A.MIDDLE_CENTER)
        for r, row in enumerate(table.rows, start=1):
            mid = top - (r + 0.5) * _TABLE_ROW
            if c == 0 and table.swatches:
                swatches.append((table.swatches[r - 1], (x + 1.0, mid - _TABLE_ROW / 2 + 1.0, x + width - 1.0,
                                                         mid + _TABLE_ROW / 2 - 1.0)))
            elif row[c]:
                text(row[c], x + 2.0, mid, 2.5, A.MIDDLE_LEFT, "NOTES")
        x += width
    return swatches


def _free_spot(sheet: Sheet, w: float, h: float, occupied: list, distance) -> tuple[float, float] | None:
    """The top-left corner of the free ``w`` x ``h`` box that ``distance`` (of a
    top-left corner) ranks nearest: inside the paper above the notes, title block
    and any parts list and below any revision table, 4 mm clear of everything in
    ``occupied``. The search walks a 2 mm grid."""
    x_lo, x_hi, y_lo, y_hi = _free_band(sheet)
    y_hi -= _revisions_height(sheet)
    best = None
    y = y_hi
    while y - h >= y_lo:
        x = x_lo
        while x + w <= x_hi:
            box = (x - 4.0, x + w + 4.0, y - h - 4.0, y + 4.0)
            if not any(box[0] < o[1] and box[1] > o[0] and box[2] < o[3] and box[3] > o[2] for o in occupied):
                rank = distance(x, y)
                if best is None or rank < best[0]:
                    best = (rank, (x, y))
            x += 2.0
        y -= 2.0
    return None if best is None else best[1]


def _place_box(sheet: Sheet, w: float, h: float, occupied: list, near) -> tuple[float, float] | None:
    """The top-left corner of the free ``w`` x ``h`` box whose middle is nearest ``near``."""
    return _free_spot(sheet, w, h, occupied, lambda x, y: math.hypot(x + w / 2 - near[0], y - h / 2 - near[1]))


def _place_detail(sheet: Sheet, size: float, room: dict, occupied: list, near) -> tuple[float, float] | None:
    """Where a detail ``size`` mm across, with its annotation ``room``, has its
    centre: the free spot whose circle is nearest ``near``."""
    half = size / 2
    w, h = size + room["left"] + room["right"], size + room["bottom"] + room["top"]
    corner = _free_spot(sheet, w, h, occupied,
                        lambda x, y: math.hypot(x + room["left"] + half - near[0], y - room["top"] - half - near[1]))
    return None if corner is None else (corner[0] + room["left"] + half, corner[1] - room["top"] - half)


def _notes_box(sheet: Sheet) -> list[tuple[float, float, float, float]]:
    """The notes block as ``[(x0, x1, y0, y1)]``, as the furniture draws it; empty
    without notes."""
    base, rows = sheet._note_layout()
    if not rows:
        return []
    x0, y0 = _MARGIN + _NOTE_INSET, _MARGIN + base + 4.0
    width = max(sheet._row_width(row, rows) for row in rows)
    return [(x0, x0 + width, y0 - 1.0, y0 + (len(rows) - 1) * 5.0 + _NOTE_HEIGHT + 1.0)]


def _notes_base(sheet: Sheet, paper: str | None = None) -> float:
    """How high above the frame's foot the notes stand on ``paper`` (the sheet's
    own by default): on it, beside the title block, unless a word is too long
    to stand there (:meth:`Sheet._note_layout`)."""
    return sheet._note_layout(paper)[0]


def _notes_height(sheet: Sheet, paper: str | None = None) -> float:
    """How far the notes rise above their base, with air; 0 without notes."""
    rows = len(sheet._note_rows(paper))
    return rows * 5.0 + 8.0 if rows else 0.0


def _revisions_box(sheet: Sheet) -> tuple[float, float, float, float] | None:
    """The revision table as ``(x0, x1, y0, y1)``, or None on a sheet without one."""
    if not sheet.revisions:
        return None
    w = sum(width for _name, width in _REVISION_COLUMNS)
    h = (len(sheet.revisions) + 1) * _REVISION_ROW
    return sheet.width - _MARGIN - w, sheet.width - _MARGIN, sheet.height - _MARGIN - h, sheet.height - _MARGIN


def _revisions_height(sheet: Sheet) -> float:
    """How far the revision table reaches down from the frame's top, with air."""
    box = _revisions_box(sheet)
    return box[3] - box[2] + 6.0 if box is not None else 0.0


def _furniture(sheet: Sheet) -> list[tuple[float, float, float, float]]:
    """The sheet's own furniture as ``(x0, x1, y0, y1)``: the title block with any
    parts list standing on it, and the revision table."""
    boxes = [(sheet.width - _MARGIN - _TITLE_W, sheet.width - _MARGIN, _MARGIN,
              _MARGIN + sheet._title_height() + _list_height(sheet))]
    revisions = _revisions_box(sheet)
    if revisions is not None:
        boxes.append(revisions)
    return boxes


def _free_band(sheet: Sheet, paper: str | None = None) -> tuple[float, float, float, float]:
    """The paper views may take, ``(x0, x1, y0, y1)``: inside the frame and 4 mm
    clear of it, above the notes, the title block and any parts list."""
    m = _MARGIN
    width, height = SHEET_SIZES[paper or sheet._size()]
    title = sheet._title_height()
    floor = max(title, _notes_base(sheet, paper) + _notes_height(sheet, paper),
                title + _list_height(sheet) + 6.0 if sheet._parts is not None else 0.0)
    return m + 4.0, width - m - 4.0, m + floor + 4.0, height - m - 4.0


def _next_smaller(scale: float) -> float | None:
    """The next standard scale below ``scale``, or None."""
    return next((c for c in _STANDARD_SCALES if c < scale - 1e-12), None)


def _choose_for_breaks(sheet: Sheet, floor: int, ceiling: float | None) -> None:
    """Settle a chosen size or scale before a sheet's broken views are projected,
    with the room three_views() assumes and the extents the breaks leave."""
    arranged = next((view for view in sheet.views if view._arranged is not None), None)
    if arranged is None:
        _settle(sheet, _within(sheet, floor, ceiling))
        return
    size, gap, iso, names = arranged._arranged
    brk = next(view._break for view in sheet.views if view._break is not None)
    _settle(sheet, _choose_size_and_scale(sheet, _broken_size(size, brk, sheet._scale()), iso, _default_rooms(), gap,
                                          floor=floor, ceiling=ceiling, names=names))


def _within(sheet: Sheet, floor: int, ceiling: float | None) -> tuple[str, float]:
    """The sheet's current size and scale, held within a retry's bounds: no smaller
    than the ``floor``-th size, no larger than ``ceiling``."""
    paper, scale = sheet._size(), sheet._scale()
    if sheet.size is None and _SIZES_SMALLEST_FIRST.index(paper) < floor:
        paper = _SIZES_SMALLEST_FIRST[floor]
    if sheet.scale is None and ceiling is not None and scale > ceiling + 1e-12:
        scale = next(c for c in _STANDARD_SCALES if c <= ceiling + 1e-12)
    return paper, scale


#: The largest enlargement a sheet chooses: past it a part is a detail view.
_LARGEST_SCALE = 10.0


#: The sheets a sheet choosing its own size tries, smallest first, for a part it
#: can draw at full size or larger; a part bigger than that goes on A3, reduced.
#: A1 and A0 are tried only at a scale the author fixed.
_SIZES_SMALLEST_FIRST = ("A4", "A3", "A2", "A1", "A0")
_SIZES_CHOSEN = ("A4", "A3", "A2")
_SIZE_REDUCED = "A3"


def _choose_size_and_scale(sheet: Sheet, extent, iso, room: dict, gap: float | None = None, *, floor: int = 0,
                           ceiling: float | None = None, names: tuple[str, ...] = _VIEW_NAMES) -> tuple[str, float]:
    """The size and scale for a sheet that leaves either to itself, with a part
    of ``extent`` drawn in three views (and an isometric, ``iso`` being its 1:1
    extent or False), each view with ``room`` for its annotation.

    A chosen scale is the largest standard one, up to 10:1 and no larger than
    ``ceiling``, that fits. A chosen size is the smallest of A4 to A2, from the
    ``floor``-th size up, that draws the part at 1:1 or larger, else A3 (or the
    floor's size, if larger) reduced, or the next size up where no standard scale
    fits A3 (scale before sheet); given a fixed scale, it is the smallest
    sheet from the floor up that fits it. A fixed size or scale is kept. A part
    too big for a fixed scale takes the largest sheet, and the render refuses it,
    naming the scale that fits."""
    scales = ([c for c in _STANDARD_SCALES if c <= (ceiling or _LARGEST_SCALE) + 1e-9] if sheet.scale is None
              else [sheet.scale])

    def largest(paper: str) -> float | None:
        """The largest candidate scale that fits ``paper``, or None."""
        try:
            sheet._check_notes(paper)
        except ValueError:
            return None  # its notes do not fit this sheet's width
        for scale in scales:
            if max(_arrange_three_views(sheet, extent, gap, scale, iso, room, paper, names)[1]) <= 0:
                return scale
        return None

    if sheet.size is not None:
        paper, fit = sheet.size, largest(sheet.size)
    elif sheet.scale is not None:
        # A fixed scale: the smallest sheet it fits.
        paper, fit = _SIZES_SMALLEST_FIRST[-1], None
        for name in _SIZES_SMALLEST_FIRST[floor:]:
            fit = largest(name)
            if fit is not None:
                paper = name
                break
    else:
        # Both chosen: the smallest sheet that draws the part full size or larger,
        # else A3 (or the floor's size, if larger) reduced.
        paper, fit = None, None
        for name in _SIZES_CHOSEN[floor:]:
            fit = largest(name)
            if fit is not None and fit >= 1.0 - 1e-9:
                paper = name
                break
        if paper is None:
            # Reduced on A3 (or the floor's size); where no standard scale fits it,
            # the next sheet up that one does, scale before sheet.
            for paper in _SIZES_SMALLEST_FIRST[max(floor, _SIZES_SMALLEST_FIRST.index(_SIZE_REDUCED)):]:
                fit = largest(paper)
                if fit is not None:
                    break
    if fit is None and sheet.scale is not None:
        fit = sheet.scale  # the render refuses it, naming the scale that fits
    if fit is None:
        raise ValueError(
            f"the views do not fit {paper} at any standard scale: the room their dimensions, callouts and labels "
            "take alone is more than the sheet has. Give Sheet a larger size=, or fewer views."
        )
    return paper, fit


def _settle(sheet: Sheet, choice: tuple[str, float]) -> None:
    """Record a choice for whichever of size and scale the sheet leaves to itself."""
    paper, scale = choice
    if sheet.size is None:
        sheet._chosen_size = paper
    if sheet.scale is None:
        sheet._chosen_scale = scale
    sheet._check_notes(sheet._size())


def _default_rooms() -> dict:
    """The room each of three views is assumed to need before its annotation is known."""
    return {name: dict(_DEFAULT_ROOM) for name in ("top", "front", "right")}


def _require_settled(sheet: Sheet) -> None:
    """Refuse to place anything by hand on a sheet whose size or scale is not yet chosen."""
    sheet._size()
    sheet._scale()
