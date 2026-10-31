"""Rendering a :class:`~cadgen.eng_drawing.Sheet`: the ezdxf document a page of the
PDF is drawn from.

A render settles what the sheet left to itself (its size and scale), projects
each view, plans where each dimension and callout goes, lays the views out again
for the annotation they carry, places details, auxiliary views and hole tables in
free paper, and draws it all with the sheet's furniture. What the sheet leaves
unstated, and what it noticed on the way, goes on the drawing's facts for the
report. Paper that runs out raises ``_OffFrame``, which a sheet choosing its own
size or scale answers with a larger sheet or a smaller scale; two values in one
place raise ``_Crowded``, which a sheet choosing its size answers with a larger
sheet.
"""

from __future__ import annotations

import functools
import itertools
import math
from typing import TYPE_CHECKING

from cadgen._internal.drawing_annotation import (
    _CALLOUT_LINE, _Features, _HoleTable, _callout_lines, _callout_value, _draw_hole_table, _draw_hole_tags,
    _hole_table, _plan_view,
    _resolve_view, _shows, _tol_suffix,
)
from cadgen._internal.drawing_assembly import (
    _draw_balloons, _item_of, _item_point, _refresh_from_item, _refuse_balloons_on,
)
from cadgen._internal.drawing_base import (
    _CALLOUT_CLEAR, _CALLOUT_GAP, _CALLOUT_LANDING, _CALLOUT_STACK, _CENTRE_OVERSHOOT, _DIM_ROW, _FLAG_SIDE,
    _HATCH_SCALE, HATCHES, _LABEL_GAP, _LABEL_HEIGHT, _LAYERS, _MARGIN, _MIN_TEXT_MM, _PLANE_ROOM, _SAME_PLACE,
    SHEET_SIZES, _SIDES, _STANDARD_SCALES, _SYMBOL_ADVANCE, _TITLE_W, _box_dimension_value, _box_text, _cross,
    _dimstyle, _dirs, _dot, _draw_dimension_symbols, _draw_flag, _draw_symbol, _exact, _fmt, _ink_width, _look,
    _looks_down, _mtext_extent, _places, _runs, _scale_label, _shown, _spans, _text_box, _text_width, _where,
)
from cadgen._internal.drawing_gdt import (
    _DATUM_REACH, _FRAME_HEIGHT, _check_datums, _check_standard, _datum_toward, _draw_datum, _draw_frame, _draw_mark,
    _side_of, frame_size, mark_width,
)
from cadgen._internal.drawing_report import _Facts, _member_key, _merge_facts, _tally
from cadgen._internal.drawing_sheet import (
    _AIR, _LARGEST_SCALE, _SIZES_CHOSEN, _SIZES_SMALLEST_FIRST, _Crowded, _OffFrame, _arrange_three_views, _assert_views_fit,
    _SheetTable, _choose_for_breaks, _choose_size_and_scale, _draw_furniture, _draw_sheet_table, _furniture,
    _list_height, _next_smaller,
    _notes_box, _place_box, _place_detail, _require_settled, _settle, _within,
)
from cadgen._internal.drawing_views import (
    _BREAK_GAP, _PLANE_SHOWN_ON, _Projection, _axis_lines, _bbox_bounds, _break_cuts, _break_hides, _break_shift,
    _broken_shape, _broken_size, _centres, _circles, _clip_runs, _cut, _draw_break_lines, _draw_cutting_plane,
    _edge_points, _edge_polyline, _edges_bounds, _end_on, _merge_centre_lines, _model_to_sheet, _on_cut,
    _pictures_alike, _plane_parent, _sheet_axis, _wire_points,
)

if TYPE_CHECKING:
    from cadgen.eng_drawing import Sheet


#: The arrow on a view an auxiliary view is projected from: its head's distance
#: from the face, its tail's, and the letter's beyond the tail.
_AUX_ARROW = (5.0, 20.0, 4.0)


def _place_auxiliaries(sheet: Sheet, work: list, occupied: list, s: float) -> None:
    """Label each auxiliary view, and place each one the sheet places in the free
    paper nearest the view it is projected from."""
    for view, _proj, bounds, _items, plan, _centre in work:
        if view._aux is None:
            continue
        sv = view.scale or s
        # The label states the view's scale when it is not the sheet's. The one the
        # sheet wrote is written again for the scale it ends with; an author's stays.
        if view.label is None or (view._auto_label is not None and view.label == view._auto_label[0]):
            view.label = f"VIEW {view._aux.letter}" + (f" ({_scale_label(sv)})" if abs(sv - s) > 1e-12 else "")
            view._auto_label = (view.label, view.scale)
        if not view._aux.placed_by_sheet:
            continue
        room = plan["room"]
        w = (bounds[1] - bounds[0]) * sv + room["left"] + room["right"]
        h = (bounds[3] - bounds[2]) * sv + room["bottom"] + room["top"]
        spot = _place_box(sheet, w, h, occupied, view._aux.parent.at)
        if spot is None:
            raise _OffFrame(f"VIEW {view._aux.letter}: no free paper on {sheet._size()} for it at {_scale_label(sv)}. "
                            "Give it at=, a smaller scale or a larger sheet.", _next_smaller(s))
        view.at = (spot[0] + room["left"] + (bounds[1] - bounds[0]) * sv / 2,
                   spot[1] - room["top"] - (bounds[3] - bounds[2]) * sv / 2)
        occupied.append((spot[0], spot[0] + w, spot[1] - h, spot[1]))


def _place_hole_tables(sheet: Sheet, tables: dict, occupied: list, s: float) -> None:
    """Put each hole table in the free paper nearest its view, or at the corner its
    author gave, which must be on the paper and clear of everything else."""
    for view in sheet.views:
        if id(view) not in tables:
            continue
        table = tables[id(view)]
        w, h = table.size
        if view._table.corner is None:
            spot = _place_box(sheet, w, h, occupied, view.at)
            if spot is None:
                raise _OffFrame(
                    f"{view.name}.hole_table(): no free paper on {sheet._size()} for a {w:.0f} x {h:.0f} mm table. "
                    "Give it at=, a smaller scale or a larger sheet.", _next_smaller(s))
        else:
            spot = view._table.corner
            box = (spot[0], spot[0] + w, spot[1] - h, spot[1])
            m = _MARGIN
            if box[0] < m or box[1] > sheet.width - m or box[2] < m or box[3] > sheet.height - m:
                raise ValueError(f"{view.name}.hole_table(at={spot}): a {w:.0f} x {h:.0f} mm table there runs off "
                                 f"the {sheet._size()} sheet's frame")
            if any(box[0] < o[1] and box[1] > o[0] and box[2] < o[3] and box[3] > o[2]
                   for o in [*occupied, *_furniture(sheet)]):
                raise ValueError(f"{view.name}.hole_table(at={spot}): the table there is drawn over a view, its "
                                 "annotation, the title block or the revision table; leave at= out to let the "
                                 "sheet place it")
        table.corner = spot
        occupied.append((spot[0] - 4.0, spot[0] + w + 4.0, spot[1] - h - 4.0, spot[1] + 4.0))


#: The symmetry symbol: how far its centre line runs past the part, where its two
#: strokes stand beyond the outline, and half a stroke's length (sheet mm).
_SYMMETRY_REACH = 6.0
_SYMMETRY_STROKES = (2.0, 3.2)
_SYMMETRY_HALF = 1.8
#: Below this width on the sheet (mm) a cut part is too thin to hatch, and is
#: filled solid; and how neighbours of one material family are told apart, as
#: ISO 128-50 has it: the hatch turned a right angle, then spaced wider. A turn
#: of 45 degrees would set a 45-degree pattern square to the sheet, where its
#: lines read as edges.
_THIN = 1.0
_HATCH_TURNS = ((0.0, 1.0), (90.0, 1.0), (0.0, 1.6), (90.0, 1.6))
#: How close two cut regions come on the sheet (mm) to count as touching.
_NEIGHBOURS = 1.0
#: A cut region narrower than this (sheet mm, across its area) is hatched finer,
#: so a small one still shows its lines.
_HATCH_ROOM = 10.0


def _cut_region(faces, flat):
    """The region a part's cut faces cover, each face's rings mapped by ``flat``
    from a model point to the sheet's plane."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    return unary_union([Polygon(rings[0], rings[1:]).buffer(0) for rings in (
        [[flat(point) for point in _wire_points(wire)] for wire in [face.outer_wire(), *face.inner_wires()]]
        for face in faces)])


def _thin(region) -> bool:
    """Whether a cut region (sheet mm) is too thin anywhere to hatch legibly."""
    return region.buffer(-_THIN / 2).is_empty


def _section_looks(cut_items, flat, materials: bool = False) -> list[tuple]:
    """Each part a section cuts, with how it is hatched: (item, its region on the
    sheet, whether it is too thin to hatch, its variant of the hatch, how much
    finer its hatch is set, whether it is drawn uncut). Parts that share a
    pattern and touch -- regions within a millimetre on the sheet -- never look
    alike, whatever their order: each takes the first variant its neighbours do
    not have. In one hatch every part shares the pattern; by ``materials``, the
    parts of one family do."""
    import statistics

    def family(item) -> str:
        return (item.family or "general") if materials else "general"

    looks: list[tuple] = []
    for item, faces, plain in cut_items:
        region = _cut_region(faces, flat)
        near = {variant for other, other_region, _thin_too, variant, _fine, other_plain in looks
                if not other_plain and family(other) == family(item) and other_region.distance(region) < _NEIGHBOURS}
        variant = next((k for k in range(len(_HATCH_TURNS)) if k not in near), len(looks) % len(_HATCH_TURNS))
        # A small region is hatched finer so it still shows lines; the part's
        # typical piece sets it, so all of one part is hatched alike.
        pieces = [g.area for g in getattr(region, "geoms", [region]) if g.area > 0]
        size = math.sqrt(statistics.median(pieces)) if pieces else _HATCH_ROOM
        looks.append((item, region, _thin(region), variant, min(1.0, max(0.35, size / _HATCH_ROOM)), plain))
    return looks


def _section_pattern(item, materials: bool) -> tuple[str, float]:
    """The pattern and angle a section hatches a part with: its material family's
    by ``materials``, else the one general-purpose hatch."""
    return HATCHES[item.family or "general"] if materials else HATCHES["general"]


def _sheet_tables(sheet: Sheet, cuts: dict, work: list, s: float) -> list[_SheetTable]:
    """The tables a sheet's sections and layers ask for: a material key where a
    section hatched by material cuts two or more parts, and the layer table it
    was given."""
    tables = []
    rows: dict[int, tuple] = {}
    near = None
    for view, proj, *_rest in work:
        cut = cuts.get(id(view))
        if not cut or not cut[3] or not view._section_materials:
            continue
        near = near or view.at
        sv = view.scale or s
        for item, _region, thin, variant, _fine, plain in _section_looks(
                cut[3], lambda p: tuple(c * sv for c in proj.point(p)), materials=True):
            if plain:
                continue  # drawn uncut: no hatch to key
            # A row per part, its swatch the look its region has: a section
            # carries no balloons, so the key is what says which region is which.
            rows.setdefault(item.number, (item, "solid" if thin else item.family or "general", variant))
    if len(rows) > 1:
        ordered = [rows[number] for number in sorted(rows)]
        tables.append(_SheetTable("MATERIAL KEY", ("HATCH", "ITEM", "FAMILY", "MATERIAL"),
                                  [(" " * 6, str(item.number),
                                    "THIN, SOLID" if family == "solid" else family.replace("_", " ").upper(),
                                    item.material or item.description) for item, family, _variant in ordered],
                                  [(family, variant) for _item, family, variant in ordered],
                                  near or sheet.views[0].at))
    return tables


def _place_sheet_tables(sheet: Sheet, tables: list[_SheetTable], occupied: list, s: float) -> list:
    """Each sheet table's corner: the free paper nearest what it keys."""
    corners = []
    for table in tables:
        w, h = table.size()
        spot = _place_box(sheet, w, h, occupied, table.near)
        if spot is None:
            raise _OffFrame(f"{table.caption.lower()}: no free paper on {sheet._size()} for a {w:.0f} x {h:.0f} mm "
                            "table. Give it a smaller scale or a larger sheet.", _next_smaller(s))
        box = (spot[0], spot[0] + w, spot[1] - h, spot[1])
        corners.append(spot)
        occupied.append((box[0] - 4.0, box[1] + 4.0, box[2] - 4.0, box[3] + 4.0))
    return corners


def _check_clear_of_parts_list(sheet: Sheet, placed: list, index: int) -> None:
    """Refuse a view drawn over the parts list, which would print both illegible."""
    if sheet._parts is None:
        return
    x_block, y_title = sheet.width - _MARGIN - _TITLE_W, _MARGIN + sheet._title_height()
    y_list = y_title + _list_height(sheet)
    for view, _proj, _bounds, _cx, _cy, box in placed:
        if box[1] > x_block + 1e-6 and box[2] < y_list - 1e-6 and box[3] > y_title:
            raise ValueError(
                f"sheet {index}: the {view.name} view is drawn over the parts list, which stands on the title "
                f"block from {x_block:.0f} mm across and up to {y_list:.0f} mm. Place the view clear of it, or "
                "draw at a smaller scale."
            )


#: How many landings further out a callout past the rows may stand to clear text.
_CALLOUT_STEPS = 4


def _runs_through(polyline, boxes) -> bool:
    """Whether a polyline runs through any of the boxes ``(x0, x1, y0, y1)``."""
    from shapely.geometry import LineString, box

    path = LineString(polyline)
    return any(path.intersects(box(b[0], b[2], b[1], b[3])) for b in boxes)


def _crosses_any(polyline, others) -> bool:
    """Whether a polyline crosses any of the others (touching an end is not
    crossing)."""
    from shapely.geometry import LineString

    path = LineString(polyline)
    return any(path.crosses(LineString(other)) for other in others)


def _drawn_area(work_item, s: float):
    """The paper a view's part covers: its line work and the regions it closes,
    on the sheet."""
    from shapely.geometry import LineString
    from shapely.ops import polygonize, unary_union

    view, proj, _bounds, _items, _plan, (cx, cy) = work_item
    sv = view.scale or s

    def to_sheet(p):
        return (view.at[0] + (p[0] - cx) * sv, view.at[1] + (p[1] - cy) * sv)

    lines = [LineString([to_sheet(p) for p in points]) for points in
             (_edge_points(edge) for edge in proj.visible) if len(points) > 1]
    ink = unary_union(lines)
    return unary_union([ink, *polygonize(ink)])


def _overall_ends(points, box, horizontal: bool) -> tuple[tuple[float, float], tuple[float, float]]:
    """Where an overall size's extension lines start: on the drawn part, at each
    extreme, the point nearest the side the dimension stands on (the top for a
    width, the left for a height). The view's box corners are not on a part that
    does not fill its box -- an inclined tab's top is nowhere near the box's left
    edge, and an extension line to the corner stops short of the feature it
    measures. A side no drawn point reaches keeps its corner."""
    vx0, vx1, vy0, vy1 = box
    near = 0.05  # sheet mm: a circle sampled in chords still reaches its extreme
    if horizontal:
        def end(x):
            ys = [py for px, py in points if abs(px - x) <= near]
            return (x, max(ys) if ys else vy1)
        return end(vx0), end(vx1)

    def end(y):
        xs = [px for px, py in points if abs(py - y) <= near]
        return (min(xs) if xs else vx0, y)
    return end(vy0), end(vy1)


def _annotation_lines(doc):
    """The line work of a sheet's dimensions (their dimension and extension lines)
    and leaders, as one shapely geometry."""
    from shapely.geometry import LineString
    from shapely.ops import unary_union

    lines = []
    for dimension in doc.modelspace().query("DIMENSION"):
        for entity in doc.blocks.get(dimension.dxf.geometry):
            if entity.dxftype() == "LINE":
                lines.append(LineString([tuple(entity.dxf.start)[:2], tuple(entity.dxf.end)[:2]]))
    for leader in doc.modelspace().query("LEADER"):
        points = [tuple(v)[:2] for v in leader.vertices]
        if len(points) > 1:
            lines.append(LineString(points))
    return unary_union(lines)


#: Where a detail's letter may stand round its circle on the parent, in order:
#: down and to the right first, as drafters set it, then round the circle.
_LETTER_TURNS = (-45, 0, 45, -90, -135, 90, 180, 135)


def _letter_spot(centre, ring: float, letter: str, height: float, area) -> tuple[float, float]:
    """Where a detail's letter stands on its parent: just outside the circle,
    clear of the part where any spot round it is (ISO 128-1: annotation off the
    views), else where it covers the least of the part."""
    from shapely.geometry import box

    half = (_ink_width(letter, height) / 2 + 0.5, height / 2 + 0.5)
    best, least = None, None
    for reach in (ring + max(half) + 1.0, ring + max(half) + 5.0, ring + max(half) + 10.0):
        for turn in _LETTER_TURNS:
            x = centre[0] + reach * math.cos(math.radians(turn))
            y = centre[1] + reach * math.sin(math.radians(turn))
            patch = box(x - half[0], y - half[1], x + half[0], y + half[1])
            if not area.intersects(patch):
                return (x, y)
            covered = area.intersection(patch).area
            if least is None or covered < least:
                best, least = (x, y), covered
    return best


def _draw_aux_arrows(msp, sheet: Sheet, drawn: dict, text, th: float) -> None:
    """On each view an auxiliary view is projected from, an arrow pointing at the
    face the way the auxiliary view looks, and its letter."""
    from ezdxf.enums import TextEntityAlignment

    head_at, tail_at, letter_at = _AUX_ARROW
    for view in sheet.views:
        if view._aux is None or id(view._aux.parent) not in drawn or id(view) not in drawn:
            continue
        _parent_view, parent_to_sheet, _box = drawn[id(view._aux.parent)]
        point, n = view._aux.point, view._direction[0]
        tip = parent_to_sheet(point)
        ahead = parent_to_sheet(tuple(p + c for p, c in zip(point, n)))
        run = math.hypot(ahead[0] - tip[0], ahead[1] - tip[1]) or 1.0
        d = ((ahead[0] - tip[0]) / run, (ahead[1] - tip[1]) / run)
        head = (tip[0] + d[0] * head_at, tip[1] + d[1] * head_at)
        tail = (tip[0] + d[0] * tail_at, tip[1] + d[1] * tail_at)
        msp.add_leader([head, tail], dxfattribs={"layer": "NOTES"},
                       override={"dimasz": th, "dimldrblk": "_CLOSEDFILLED"})
        text(view._aux.letter, tail[0] + d[0] * letter_at, tail[1] + d[1] * letter_at, th + 1.5,
             TextEntityAlignment.MIDDLE_CENTER, "NOTES")


def _render_sheet(sheet: Sheet, *, index: int, count: int, label: str, warnings: list | None = None,
                  facts: _Facts | None = None, continued: dict | None = None):
    """Build the ezdxf document for one sheet. Returns the document.

    A sheet that leaves its size or scale to itself and runs out of paper -- its
    views off the frame, no free paper for a detail, a table or balloons -- is
    drawn again rather than refused, those being the sheet's choices, not the
    author's. A part drawn enlarged is drawn smaller on the same sheet first, down
    to 1:1; then the sheet takes the next size up if it chooses its size, or the
    next standard scale down if it chooses its scale. Two values printed in one
    place on a sheet choosing its size take the next size up too, up to A0, at
    the largest scale it fits: more paper between the features, never a smaller
    scale, which crowds them more.
    Only the drawing that succeeds reports anything.
    """
    if sheet._item is not None:
        _refresh_from_item(sheet)
    floor, ceiling = 0, None
    tried: set = set()
    while True:
        tried_warnings: list = []
        tried_facts = _Facts()
        try:
            doc = _draw_sheet(sheet, index=index, count=count, label=label, warnings=tried_warnings,
                              facts=tried_facts, continued=continued, floor=floor, ceiling=ceiling)
        except _Crowded:
            attempt = (sheet._size(), sheet._scale())
            index_now = _SIZES_SMALLEST_FIRST.index(attempt[0])
            if sheet.size is not None or attempt in tried or index_now == len(_SIZES_SMALLEST_FIRST) - 1:
                raise
            tried.add(attempt)
            # Room between the features: the larger sheet draws them as large as it fits.
            floor, ceiling = index_now + 1, None
            continue
        except _OffFrame as exc:
            attempt = (sheet._size(), sheet._scale())
            if not sheet._chooses() or attempt in tried:
                raise
            tried.add(attempt)
            index_now = _SIZES_SMALLEST_FIRST.index(attempt[0])
            if sheet.scale is None and attempt[1] > 1.0 + 1e-9:
                # Enlarged and out of paper: a smaller scale on this sheet, before a
                # larger sheet that would leave most of itself empty.
                ceiling = max(1.0, _next_smaller(attempt[1]) or 1.0)
                floor = 0  # the smaller drawing may fit a smaller sheet
                continue
            if sheet.size is None and index_now < len(_SIZES_CHOSEN) - 1:
                # A larger sheet is for room, not for a larger scale.
                floor = index_now + 1
                if sheet.scale is None:
                    ceiling = min(ceiling or _LARGEST_SCALE, attempt[1])
                continue
            if sheet.scale is None and exc.fits is not None and exc.fits < attempt[1]:
                ceiling = exc.fits
                continue
            raise
        if warnings is not None:
            warnings.extend(tried_warnings)
        if facts is not None:
            _merge_facts(facts, tried_facts)
        return doc


def _draw_sheet(sheet: Sheet, *, index: int, count: int, label: str, warnings: list | None = None,
                facts: _Facts | None = None, continued: dict | None = None, floor: int = 0,
                ceiling: float | None = None):
    """Build the ezdxf document for one sheet at its scale. Returns the document.
    ``floor`` and ``ceiling`` bound a size or scale the sheet chooses (see
    :func:`_render_sheet`).

    ``warnings`` collects what makes a right sheet harder to read -- views
    squeezed together, a leader that has to cross a dimension line, say. A
    sheet that would be wrong -- a dimension measuring blank paper, one value
    printed over another -- is refused instead.
    ``facts`` collects what the sheet states about each part (holes called out,
    values dimensioned), so the drawing can say what it leaves unstated.
    """
    import ezdxf
    from ezdxf.enums import TextEntityAlignment

    from cadgen._internal.drawing_features import axes as find_axes, bolt_circles, holes as find_holes, slots as find_slots

    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()
    for name, (color, linetype, weight) in _LAYERS.items():
        aci = 7 if sheet.ink == "mono" and name != "HIDDEN" else color
        doc.layers.add(name, color=aci, linetype=linetype, lineweight=int(round(weight * 100)))
    dimstyle = _dimstyle(doc, sheet.text_height)
    W, H, th = sheet.width, sheet.height, sheet.text_height

    def text(value, x, y, height, align, layer="TITLE", fit: float | None = None):
        # ``fit`` is the width the text may occupy; longer text is set smaller
        # rather than run through a cell divider or off the sheet. Below the
        # smallest legible height the text is cut instead, with an ellipsis, so a
        # long title ends inside its cell rather than running over the next one.
        if fit is not None and value:
            width = _text_width(value, height)
            if width > fit:
                # 0.999 so the shrink lands inside the cell rather than exactly on
                # its edge, where the re-measure rounds over and cuts text that fits.
                height = max(_MIN_TEXT_MM, height * fit / width * 0.999)
                if _text_width(value, height) > fit:
                    # Below the smallest legible height, cut rather than overrun:
                    # a title that runs into the SCALE cell is worse than a short one.
                    while len(value) > 1 and _text_width(value[:-1] + "…", height) > fit:
                        value = value[:-1]
                    value = (value[:-1] + "…") if len(value) > 1 else value[:1]
        if layer in ("DIM", "NOTES") and value and any(kind == "symbol" for kind, _ in _runs(value)):
            symbols(value, x, y, height, align, layer)
            return None
        entity = msp.add_text(value, dxfattribs={"height": height, "layer": layer})
        entity.set_placement((x, y), align=align)
        if layer in ("DIM", "NOTES") and value:
            claim(value, _text_box(value, x, y, height, align))
        return entity

    def symbols(value, x, y, height, align, layer) -> None:
        """Text whose symbols are drawn: each run of plain text a TEXT entity,
        each symbol its line work, laid end to end where one TEXT would sit."""
        box = _text_box(value, x, y, height, align)
        cursor, mid = box[0], (box[1] + box[3]) / 2
        for kind, piece in _runs(value):
            if kind == "text":
                run = msp.add_text(piece, dxfattribs={"height": height, "layer": layer})
                run.set_placement((cursor, mid), align=TextEntityAlignment.MIDDLE_LEFT)
                cursor += _text_width(piece, height)
            else:
                _draw_symbol(msp, piece, cursor, mid, height, layer)
                cursor += _SYMBOL_ADVANCE[piece] * height
        claim(value, box)

    # Annotation already on the paper, as (what it says, its box). The layout
    # gives each view the room its annotation asks for, but a sheet squeezed for
    # paper, or one with views placed by hand, can still land one view's callouts
    # on another's. Nothing here moves them, because which of the two should give
    # way is the author's call; it says so instead of leaving it to the print.
    claimed: list[tuple[str, tuple[float, float, float, float]]] = []
    #: Every dimension line drawn, as its two ends on the sheet, and every callout's
    #: leader, as its points: a new leader may cross neither.
    dimension_lines: list[tuple[tuple[float, float], tuple[float, float]]] = []
    leaders: list[tuple[tuple[float, float], ...]] = []

    def claim_rendered(dimension) -> None:
        """A dimension's VALUE lives as MTEXT inside its rendered block, not as
        TEXT on the sheet, so it is registered from there once it is drawn."""
        try:
            block = doc.blocks.get(dimension.dxf.geometry)
        except Exception:  # noqa: BLE001 - a dimension with no block draws nothing to collide with
            return
        for entity in block:
            if entity.dxftype() != "MTEXT":
                continue
            value = str(entity.text or "")
            height = float(entity.dxf.char_height or th)
            width, tall = _mtext_extent(value, height)
            # A vertical dimension's value is turned with its line: its box is too.
            turn = math.radians(float(entity.dxf.get("rotation", 0.0) or 0.0))
            width, tall = (abs(width * math.cos(turn)) + abs(tall * math.sin(turn)),
                           abs(width * math.sin(turn)) + abs(tall * math.cos(turn)))
            insert = entity.dxf.insert
            claim(value, (insert.x - width / 2, insert.y - tall / 2, insert.x + width / 2, insert.y + tall / 2))

    def claim(value: str, box: tuple[float, float, float, float]) -> None:
        for other, taken in claimed:
            if (box[0] < taken[2] and box[2] > taken[0] and box[1] < taken[3] and box[3] > taken[1]):
                # Two values in one place read as neither: the sheet is wrong, not cramped.
                raise _Crowded(
                    f"annotation overlaps: {value.strip()!r} would print over {other.strip()!r} "
                    f"around ({box[0]:.0f}, {box[1]:.0f}). Give the view more room "
                    "(three_views(gap=...), a larger sheet), or place one of them with offset=."
                )
        claimed.append((value, box))

    # What the part's faces say, read once per part however many views show it.
    found_features: dict[int, _Features] = {}
    found_axes: dict[int, list] = {}

    def part_features(shape) -> _Features:
        if id(shape) not in found_features:
            holes = find_holes(shape)
            found_features[id(shape)] = _Features(holes, find_slots(shape), bolt_circles(shape, holes))
        return found_features[id(shape)]

    def part_axes(shape) -> list:
        if id(shape) not in found_axes:
            found_axes[id(shape)] = find_axes(shape)
        return found_axes[id(shape)]

    # Every view is projected, its callouts read off the part and its annotation
    # planned before anything is placed, so the layout knows what each view carries.
    _require_settled(sheet)
    _check_datums(sheet, f"sheet {index} ({sheet.title})")
    _check_standard(sheet, f"sheet {index} ({sheet.title})")
    key_mark = sheet.profile.characteristic_mark if sheet.profile is not None else "KC"
    framed = sheet.general_profile is not None or any(
        dim.frame is not None for view in sheet.views for dim in view._dims)
    if not framed:
        # A basic dimension is exact by definition; only a frame gives it a tolerance, so one with
        # none on the sheet would print a size nobody can make.
        for view in sheet.views:
            for number, dim in enumerate(view._dims):
                if dim.basic:
                    kind = "dim" if dim.kind == "linear" else dim.kind
                    raise ValueError(f"{view.name} {kind} {number}: a basic dimension, and no GD&T frame on the "
                                     "sheet bounds it, so it has no tolerance; add the frame that controls the "
                                     "feature, or give the dimension tol=")
    breaks = any(view._break is not None for view in sheet.views)
    if sheet._chooses() and breaks:
        # A break leaves a fixed gap of paper, so its views are drawn at the scale
        # the sheet settles on now, not at the one three_views() guessed.
        _choose_for_breaks(sheet, floor, ceiling)
    s = sheet._scale()
    work = []
    tables: dict[int, _HoleTable] = {}
    outlines: dict[int, list] = {}
    breaks_checked: set = set()
    cuts: dict[int, tuple] = {}
    checked: set[int] = set()
    # The assemblies this sheet draws as assemblies: the one its parts list was
    # read from, and any a view balloons. Many solids there are the point.
    assemblies = {id(parts.assembly) for view in sheet.views for parts in view._balloons}
    assemblies |= {id(view._section_parts.assembly) for view in sheet.views if view._section_parts is not None}
    if sheet._parts is not None:
        assemblies.add(id(sheet._parts.parts.assembly))
    if facts is not None:
        # What the sheet's stage asks of it is checked once the drawing is done.
        sheet_record = {
            "sheet": (index, sheet.title), "stage": sheet._stage(), "mark": key_mark,
            "part": any(id(view.shape) not in assemblies for view in sheet.views),
            "material": sheet.material, "spec": sheet.spec, "finish": sheet.finish,
            "general": bool(sheet.general_tolerance or sheet.general_profile),
            "datums": any(view._datums or any(d.datum for d in view._dims) for view in sheet.views),
            "keyed": any(d.key for view in sheet.views for d in view._dims),
        }
        facts.sheets.append(sheet_record)
    for view in sheet.views:
        if view._detail is not None:
            # A detail shows what its parent shows when the sheet renders, so a
            # section() made after detail() still reaches it.
            parent = view._detail.parent
            view._section, view.hidden, view.centre_marks = parent._section, parent.hidden, parent.centre_marks
            view._section_parts = parent._section_parts
            view._section_materials = parent._section_materials
        if view._balloons:
            _refuse_balloons_on(view)
        if id(view.shape) not in checked:
            checked.add(id(view.shape))
            solids = len(view.shape.solids()) if hasattr(view.shape, "solids") else 1
            if solids > 1 and id(view.shape) not in assemblies:
                # One part's drawing of several solids states one part's sizes over
                # pieces that are not joined: its title block and its report say
                # one part, and its views say otherwise.
                raise ValueError(
                    f"the part in the {view.name} view is {solids} separate solids, and a drawing documents one "
                    "part. A cut that runs right through the model splits it; check the model, or draw each "
                    "solid on its own sheet. An assembly is drawn with a parts list and balloons: "
                    "assembly_sheets(parts_list(assembly().shape), ...)."
                )
        cut = _cut(view) if view._section else None
        draw = cut[0] if cut else None
        if view._break is not None:
            # A broken view draws the part shortened, and maps every model point
            # given to it onto the shortened part.
            gap = _BREAK_GAP / (view.scale or s)
            draw = _broken_shape(view.shape, view._break, gap)
            if (id(view.shape), view._break) not in breaks_checked:
                breaks_checked.add((id(view.shape), view._break))
                if _break_hides(view.shape, view._break):
                    # Drawn, it reads as a part of one section all along: a shoulder
                    # or a hole inside the break would go unseen, and unmade.
                    axis, lo, hi = view._break
                    raise ValueError(
                        f"{view.name}.broken(): the break from {'XYZ'[axis]} = {_fmt(lo)} to {_fmt(hi)} hides some "
                        "of the part: it is not the same section all along that stretch. Move the break to where "
                        "the part does not change."
                    )
        shift = _break_shift(view._break, gap) if view._break is not None else None
        proj = _Projection(view.shape, _dirs(view), draw=draw, shift=shift)
        if view._break is not None:
            # Each end of the break is bounded by its break line, not by the edge
            # of the cut.
            break_cuts = _break_cuts(view, proj)
            proj.visible = [e for e in proj.visible if not _on_cut(e, break_cuts)]
            proj.hidden = [e for e in proj.hidden if not _on_cut(e, break_cuts)]
        bounds = _edges_bounds(list(proj.visible) + (list(proj.hidden) if view.hidden else []))
        if not bounds:
            continue
        if cut:
            cuts[id(view)] = cut
        if view._detail is not None:
            # A detail is the circle round its centre, whatever falls inside it.
            c2, r = proj.point(view._detail.centre), view._detail.radius
            bounds, centre = (c2[0] - r, c2[0] + r, c2[1] - r, c2[1] + r), c2
        elif view._aux is not None and view._aux.outline is not None:
            # A partial auxiliary view is its face's outline, whatever lies within it.
            ring = [proj.point(p) for p in view._aux.outline]
            outlines[id(view)] = ring
            bounds = (min(x for x, _ in ring), max(x for x, _ in ring), min(y for _, y in ring),
                      max(y for _, y in ring))
            centre = ((bounds[0] + bounds[1]) / 2, (bounds[2] + bounds[3]) / 2)
        elif cut:
            # Centred on the WHOLE part, so the section lines up with the views
            # beside it even when the half it keeps is not symmetric.
            corners = _bbox_bounds(view.shape, proj)
            centre = ((corners[0] + corners[1]) / 2, (corners[2] + corners[3]) / 2)
        else:
            centre = ((bounds[0] + bounds[1]) / 2, (bounds[2] + bounds[3]) / 2)
        items = _resolve_view(view, proj, bounds, part_features, warnings, cut)
        if view._table is not None:
            tables[id(view)] = _hole_table(view, proj, part_features(view.shape), cut, items)
            items = [dim for dim in items if dim.kind != "hole"]  # a tapped hole's thread is in its row
        work.append((view, proj, bounds, items, _plan_view(view, proj, bounds, items, sheet), centre))

    # A cutting plane runs out past the view it is drawn on, with an arrow and a
    # letter at each end: that view needs room on those two sides, or the letter
    # lands on its label.
    plane_sides: dict[int, set] = {}
    projections = {id(item[0]): item[1] for item in work}
    for view in sheet.views:
        if view._section is None or view._detail is not None:
            continue
        parent = _plane_parent(view, [other for other in sheet.views if id(other) in projections])
        if parent is None:
            continue
        along = _cross(_look(parent), _look(view))
        image = [sum(row[k] * a for row, a in zip(projections[id(parent)].m, along)) for k in (0, 1)]
        plane_sides.setdefault(id(parent), set()).update(
            ("left", "right") if abs(image[0]) >= abs(image[1]) else ("top", "bottom"))
    def plane_room() -> None:
        for view, _proj, _bounds, _items, plan, _centre in work:
            for side in plane_sides.get(id(view), ()):
                plan["room"][side] = max(plan["room"][side], _PLANE_ROOM + (11.5 if side == "bottom" else 0.0))

    plane_room()

    # A sheet that chooses its own size or scale chooses again now that each
    # view's annotation is known: the choice three_views() made assumed two rows
    # of dimensions round every view.
    if sheet._chooses() and not breaks:
        groups_seen = {id(view._arranged): view for view, *_rest in work if view._arranged is not None}
        if len(groups_seen) == 1:
            first = next(iter(groups_seen.values()))
            size, gap, iso, names = first._arranged
            planned = sheet._scale()
            rooms = {view.name: plan["room"] for view, _proj, _bounds, _items, plan, _centre in work
                     if view._arranged is first._arranged}
            _settle(sheet, _choose_size_and_scale(sheet, size, iso, rooms, gap, floor=floor, ceiling=ceiling,
                                                  names=names))
            if abs(sheet._scale() - planned) > 1e-9:
                # Some room is the scale's: a value wider than its span at the scale
                # chosen is set beyond it. Planned again at that scale, for the layout.
                work[:] = [(view, proj, bounds, items, _plan_view(view, proj, bounds, items, sheet), centre)
                           for view, proj, bounds, items, _plan, centre in work]
                plane_room()
        else:
            # Several arrangements, or none: no one layout to choose by, so the
            # earlier choice stands, held within the bounds a retry set.
            _settle(sheet, _within(sheet, floor, ceiling))
        s = sheet._scale()
    _draw_furniture(msp, sheet, index=index, count=count, label=label, text=text, continued=continued)

    # A standard arrangement is laid out again from the room its views' annotation
    # takes; a view placed by hand stays where its author put it.
    arranged: dict[int, tuple] = {}
    for view, _proj, _bounds, _items, plan, _centre in work:
        if view._arranged is not None:
            arranged.setdefault(id(view._arranged), (view._arranged, {}, {}))
            arranged[id(view._arranged)][1][view.name] = view
            arranged[id(view._arranged)][2][view.name] = plan["room"]
    groups = []
    for (size, gap, iso, names), by_name, room in arranged.values():
        shape = next(iter(by_name.values())).shape
        brk = next((view._break for view in by_name.values() if view._break is not None), None)
        if brk is not None:
            size = _broken_size(size, brk, s)
        slots, over = _arrange_three_views(sheet, size, gap, s, iso, room, names=names)
        for name, at, own, slot_label in slots:
            if name in by_name:
                view = by_name[name]
                view.at = at
                if name == "iso" and (view._auto_label is None or (view.label, view.scale) == view._auto_label):
                    view.scale, view.label = own, slot_label
                    view._auto_label = (slot_label, own)
        groups.append((by_name, shape, size, gap, iso, room, names))
        if warnings is not None:
            # A turned or symmetric part shows two sides alike, and drawing both
            # states nothing twice. Sections draw a different picture by design.
            whole = [n for n in names if n in by_name and by_name[n]._section is None]
            extent = shape.bounding_box().size.length
            for a, b in itertools.combinations(whole, 2):
                if _pictures_alike(projections[id(by_name[a])], projections[id(by_name[b])], extent):
                    warnings.append(f"the {a} and {b} views draw the same picture; three_views(views=(...)) "
                                    "leaves one out")
        if gap is None and max(over) > _AIR and warnings is not None:
            # The views were squeezed together past the air between them, so one
            # view's annotation now crowds the next. Say what gives them the room.
            def roomy(scale: float) -> bool:
                return max(_arrange_three_views(sheet, size, None, scale, iso, room, names=names)[1]) <= 0

            roomier = next((name for name in sorted(SHEET_SIZES, key=lambda n: SHEET_SIZES[n][0])
                            if SHEET_SIZES[name][0] > sheet.width), None)
            smaller = next((c for c in _STANDARD_SCALES if c < s and roomy(c)), None)
            remedies = [f'Sheet("{roomier}")' if roomier else None,
                        f"Sheet(scale={smaller:g}) ({_scale_label(smaller)})" if smaller else None]
            ask = max(((name, side, value) for name, sides in room.items() for side, value in sides.items()),
                      key=lambda t: t[2])
            warnings.append(
                f"views crowded: their dimensions and callouts need {max(over):.0f} mm more than {sheet._size()} "
                f"leaves at {_scale_label(s)}, so the space between views was narrowed and one view's "
                f"annotation can crowd the next. The largest ask is the {ask[0]} view's {ask[1]} side "
                f"({ask[2]:.0f} mm of dimensions, callouts and notes). "
                f"{' or '.join(r for r in remedies if r) or 'Fewer views'} gives them room; or move that "
                "annotation to a view with space to spare."
            )

    # Details go in the free paper nearest their parent, once everything else has
    # its place.
    occupied = []
    for view, _proj, bounds, _items, plan, (cx, cy) in work:
        if (view._detail is not None and view._detail.placed_by_sheet) or (
                view._aux is not None and view._aux.placed_by_sheet):
            continue
        sv = view.scale or s
        room = plan["room"]
        occupied.append((view.at[0] + (bounds[0] - cx) * sv - room["left"], view.at[0] + (bounds[1] - cx) * sv + room["right"],
                         view.at[1] + (bounds[2] - cy) * sv - room["bottom"], view.at[1] + (bounds[3] - cy) * sv + room["top"]))
    centres = {id(item[0]): (item[1], item[5]) for item in work}
    for view in sheet.views:
        # Each detail's circle and letter on its parent are paper a detail cannot use.
        if view._detail is None or id(view._detail.parent) not in centres:
            continue
        parent, point, radius, _letter, _auto, _chosen = view._detail
        parent_proj, parent_centre = centres[id(parent)]
        ps = parent.scale or s
        x, y = (parent.at[k] + (parent_proj.point(point)[k] - parent_centre[k]) * ps for k in (0, 1))
        ring = radius * ps + th + 4.0
        occupied.append((x - ring, x + ring, y - ring, y + ring))
    for view, _proj, _bounds, _items, plan, _centre in work:
        if view._detail is None or not view._detail.placed_by_sheet:
            continue
        parent, _point, radius, letter, _auto, chosen = view._detail
        # A scale the sheet chose steps down until the circle finds paper; one the
        # author gave is theirs, and no room for it is a refusal.
        parent_scale = parent.scale or s
        tries = [view.scale] + ([c for c in _STANDARD_SCALES if parent_scale * 2 - 1e-9 <= c < view.scale]
                                if chosen else [])
        spot = None
        for scale in tries:
            size = 2 * radius * scale
            spot = _place_detail(sheet, size, plan["room"], occupied, parent.at)
            if spot is not None:
                if scale != view.scale and view.label == f"DETAIL {letter} ({_scale_label(view.scale)})":
                    view.label = f"DETAIL {letter} ({_scale_label(scale)})"
                view.scale = scale
                break
        if spot is None:
            raise _OffFrame(
                f"DETAIL {letter}: no free paper on {sheet._size()} for a {2 * radius * tries[-1]:.0f} mm circle at "
                f"{_scale_label(tries[-1])} and its annotation. Give it at=, a smaller scale=, or a larger sheet.",
                _next_smaller(s))
        size = 2 * radius * view.scale
        view.at = spot
        room = plan["room"]
        occupied.append((spot[0] - size / 2 - room["left"], spot[0] + size / 2 + room["right"],
                         spot[1] - size / 2 - room["bottom"], spot[1] + size / 2 + room["top"]))
    _place_auxiliaries(sheet, work, occupied, s)
    _place_hole_tables(sheet, tables, occupied, s)
    if facts is not None:
        sheet_record.update(_tally(sheet, work, tables))
    keyed = _sheet_tables(sheet, cuts, work, s)
    keyed_at = _place_sheet_tables(sheet, keyed, occupied, s)

    placed = []
    for view, proj, bounds, _items, _plan, (cx, cy) in work:
        bx0, bx1, by0, by1 = bounds
        sv = view.scale or s
        placed.append((view, proj, bounds, cx, cy,
                       (view.at[0] + (bx0 - cx) * sv, view.at[0] + (bx1 - cx) * sv,
                        view.at[1] + (by0 - cy) * sv, view.at[1] + (by1 - cy) * sv)))
    boxes = [box for (_, _, _, _, _, box) in placed]
    furniture = _furniture(sheet)
    if sheet._parts is not None:
        # Annotation printed over the parts list makes both unreadable; say so.
        title = sheet._title_height()
        claim("the parts list", (sheet.width - _MARGIN - _TITLE_W, _MARGIN + title, sheet.width - _MARGIN,
                                 _MARGIN + title + _list_height(sheet)))
    _assert_views_fit(sheet, placed, index=index, groups=groups)
    _check_clear_of_parts_list(sheet, placed, index)
    m = _MARGIN

    # The sheet's own furniture as (x0, x1, y0, y1), and the notes beside it: no
    # annotation lands on them.
    furnished = [*furniture, *_notes_box(sheet)]

    def blocked(x0, x1, y0, y1, own_box):
        """Whether a landing area [x0,x1]x[y0,y1] runs off the frame, into another view,
        or onto the title block, the parts list, the revision table or the notes."""
        if min(x0, x1) < m + 2 or max(x0, x1) > W - m - 2 or min(y0, y1) < m + 2 or max(y0, y1) > H - m - 2:
            return True
        for box in boxes:
            if box is own_box:
                continue
            if max(x0, x1) >= box[0] - 4 and min(x0, x1) <= box[1] + 4 and y1 >= box[2] - 4 and y0 <= box[3] + 4:
                return True
        return any(max(x0, x1) >= f[0] and min(x0, x1) <= f[1] and y1 >= f[2] and y0 <= f[3] for f in furnished)

    drawn: dict[int, tuple] = {}
    # Items ballooned on this sheet so far, as (parts list, item number): an item
    # is keyed once per sheet, in the first view that shows it.
    keyed_on_sheet: set[tuple[int, int]] = set()
    if sheet._parts is not None and facts is not None:
        parts, first, last = sheet._parts
        facts.of_list(parts)["listed"].update(range(first, last + 1))
    for (view, proj, bounds, items, plan, _centre), (_v, _p, _b, cx, cy, own_box) in zip(work, placed):
        sv = view.scale or s
        cut = cuts.get(id(view))
        section_anchors: dict[int, tuple[float, float]] = {}  # where a section's balloons land, by item
        record = None
        if facts is not None:
            record = facts.parts.setdefault(id(view.shape), {"shape": view.shape, "called": set(), "values": [],
                                                       "axes": set(), "referenced": set(), "views": [],
                                                       "sheet": (index, sheet.title),
                                                       "assembly": id(view.shape) in assemblies,
                                                       "notes": set(), "radii": set(), "spans": [],
                                                       "anchors": [], "datums": [], "symmetric": set(),
                                                       "angles": [], "aligned": []})
            # Where the view says things are: the centre lines it states the part
            # symmetric about, as the model axes they locate across.
            for direction in view._symmetric:
                axis = _sheet_axis(proj, direction == "v")
                if axis is not None:
                    record["symmetric"].add(axis)
            # What the sheet's notes and this view's notes say, for the blends and
            # chamfers a general note states.
            record["notes"].update(sheet.drawn_notes())
            record["notes"].update(d.text for d in view._dims if d.kind == "note" and d.text)
            if view.name != "iso":
                record["views"].append((view.name, _look(view)))

        def to_sheet(p2):
            # Centre the projected geometry on `at`.
            return (view.at[0] + (p2[0] - cx) * sv, view.at[1] + (p2[1] - cy) * sv)

        def model_to_sheet(p3):
            return to_sheet(proj.point(p3))

        # Bound now, not looked up later: the closures above read this loop's
        # variables, which belong to the last view by the time the loop is done.
        drawn[id(view)] = (view, functools.partial(_model_to_sheet, proj, view.at, (cx, cy), sv), own_box)

        # One set for the whole view, not one per pass. HLR returns an edge from
        # every face that bounds it, so an edge on the silhouette comes back
        # visible AND hidden: a per-pass set caught the repeats within each pass
        # and none across them, and since HIDDEN is written second it drew over
        # every visible line on the sheet. A 600 dpi crop of one view in colour
        # was 34,842 grey pixels against 2,635 black -- the outline printing
        # grey-dashed, the whole visible/hidden distinction gone. In mono it is
        # black over black, which is why it went unnoticed.
        seen: set = set()

        def once(key) -> bool:
            if key in seen:
                return False
            seen.add(key)
            return True

        def q(value: float) -> float:
            return round(value, 6)

        # A detail draws only inside its circle, in sheet coordinates.
        region = None
        if view._detail is not None:
            from shapely.geometry import Point

            region = Point(view.at).buffer(view._detail.radius * sv, quad_segs=64)
        elif id(view) in outlines:
            from shapely.geometry import Polygon

            region = Polygon([to_sheet(p) for p in outlines[id(view)]]).buffer(0.5, join_style=2)

        def centre_line(a, b) -> None:
            for run in _clip_runs([a, b], region) if region is not None else [[a, b]]:
                msp.add_line(run[0], run[-1], dxfattribs={"layer": "CENTER"})

        def centre_circle(c, r) -> None:
            if region is None:
                msp.add_circle(c, r, dxfattribs={"layer": "CENTER"})
                return
            ring = [(c[0] + r * math.cos(2 * math.pi * i / 180), c[1] + r * math.sin(2 * math.pi * i / 180))
                    for i in range(181)]
            for run in _clip_runs(ring, region):
                msp.add_lwpolyline(run, dxfattribs={"layer": "CENTER"})

        def put(edges, layer):
            """Write projected edges once each.

            The hidden-line pass returns an edge per face that hides it, so a slot
            behind two faces comes back twice and the same polyline lands on HIDDEN
            twice over. Written that way the dashes double-strike and
            ``validate_drawing_document`` reports every pair, so an edge is keyed by
            its drawn geometry -- rounded to a micron, and for a line or polyline
            read the same in either direction -- and a repeat is dropped.
            """
            from build123d import GeomType

            if region is not None:
                # A detail clips every edge to its circle; what it keeps is drawn as
                # the polyline it was cut to.
                for edge in edges:
                    for run in _clip_runs([to_sheet(p) for p in _edge_points(edge)], region):
                        points = tuple((q(x), q(y)) for x, y in run)
                        if not once(("poly", min(points, points[::-1]))):
                            continue
                        if len(run) == 2:
                            msp.add_line(run[0], run[1], dxfattribs={"layer": layer})
                        else:
                            msp.add_lwpolyline(run, dxfattribs={"layer": layer})
                return
            for edge in edges:
                # A circular edge stays a CIRCLE or ARC: exact on the sheet, so a hole
                # reads as a hole and a fillet as a radius rather than as a polyline.
                if edge.geom_type == GeomType.CIRCLE:
                    c = to_sheet((edge.arc_center.X, edge.arc_center.Y))
                    r = edge.radius * sv
                    if r < 1e-6:
                        continue
                    if edge.is_closed:
                        if once(("circle", q(c[0]), q(c[1]), q(r))):
                            msp.add_circle(c, r, dxfattribs={"layer": layer})
                        continue
                    a, b = edge.position_at(0), edge.position_at(1)
                    mid = edge.position_at(0.5)
                    ang = lambda p: math.degrees(math.atan2(p.Y - edge.arc_center.Y, p.X - edge.arc_center.X)) % 360
                    a0, a1, am = ang(a), ang(b), ang(mid)
                    # ezdxf arcs run counter-clockwise from start to end; pick the
                    # order whose sweep passes through the edge's midpoint.
                    if (am - a0) % 360 > (a1 - a0) % 360:
                        a0, a1 = a1, a0
                    if once(("arc", q(c[0]), q(c[1]), q(r), q(a0), q(a1))):
                        msp.add_arc(c, r, a0, a1, dxfattribs={"layer": layer})
                    continue
                poly = [to_sheet(p) for p in _edge_polyline(edge)]
                points = tuple((q(x), q(y)) for x, y in poly)
                # An edge seen exactly end-on projects to a point, and a point is
                # not a line: drawn, it is a zero-length entity the drawing checks
                # refuse. Single parts rarely show one; assemblies show many.
                if max(math.hypot(x - points[0][0], y - points[0][1]) for x, y in points) < 1e-6:
                    continue
                # The same edge can come back with its ends swapped; one drawn line is
                # one key whichever way it was walked.
                key = ("poly", min(points, points[::-1]))
                if not once(key):
                    continue
                if len(poly) == 2:
                    msp.add_line(poly[0], poly[1], dxfattribs={"layer": layer})
                else:
                    msp.add_lwpolyline(poly, dxfattribs={"layer": layer})

        put(proj.visible, "VISIBLE")
        if view.hidden:
            put(proj.hidden, "HIDDEN")
        if view._break is not None:
            _draw_break_lines(msp, view, proj, to_sheet)
        # Each layer too thin to hatch, and the point its callout's leader ends on.
        thin: list[tuple[tuple[float, float], str]] = []
        if cut:
            from ezdxf import const

            # The cut faces, hatched: what the section is there to show.
            for face in (cut[1] if not cut[3] else []):
                rings = [[to_sheet(proj.point(point)) for point in _wire_points(wire)]
                         for wire in [face.outer_wire(), *face.inner_wires()]]
                if region is not None:
                    from shapely.geometry import Polygon

                    clipped = Polygon(rings[0], rings[1:]).buffer(0).intersection(region)
                    pieces = [[list(g.exterior.coords), *[list(i.coords) for i in g.interiors]]
                              for g in getattr(clipped, "geoms", [clipped])
                              if g.geom_type == "Polygon" and not g.is_empty]
                else:
                    pieces = [rings]
                for piece in pieces:
                    hatch = msp.add_hatch(dxfattribs={"layer": "HATCH"})
                    hatch.set_pattern_fill("ANSI31", scale=_HATCH_SCALE)
                    for k, ring in enumerate(piece):
                        hatch.paths.add_polyline_path(
                            ring, is_closed=True,
                            flags=const.BOUNDARY_PATH_EXTERNAL if k == 0 else const.BOUNDARY_PATH_DEFAULT)
            if cut[3]:
                from shapely.ops import unary_union

                # Part by part: each in its hatch, the next it touches turned,
                # overlaps left to the first, the thin filled solid, a solid round
                # part cut along its axis left uncut.
                taken = None
                for item, own, is_thin, variant, fine, plain in _section_looks(
                        cut[3], lambda p: to_sheet(proj.point(p)), view._section_materials):
                    pattern, angle = _section_pattern(item, view._section_materials)
                    turn, spacing = _HATCH_TURNS[variant]
                    if taken is not None:
                        own = own.difference(taken)
                    if region is not None:
                        own = own.intersection(region)
                    taken = own if taken is None else unary_union([taken, own])
                    if not own.is_empty:
                        inside = own.representative_point()
                        section_anchors[item.number] = (inside.x, inside.y)
                    if plain:
                        continue
                    if is_thin and not own.is_empty and view._section_materials:
                        # Hatched by material, a part too thin to show its hatch is
                        # named where it is; in one hatch its balloon names it.
                        inside = own.representative_point()
                        thin.append(((inside.x, inside.y),
                                     item.material or item.description or f"ITEM {item.number}"))
                    for g in getattr(own, "geoms", [own]):
                        if g.geom_type != "Polygon" or g.is_empty:
                            continue
                        hatch = msp.add_hatch(dxfattribs={"layer": "HATCH"})
                        if is_thin:
                            hatch.set_solid_fill()
                        else:
                            hatch.set_pattern_fill(pattern, scale=_HATCH_SCALE * spacing * fine, angle=angle + turn)
                        for k, ring in enumerate([g.exterior, *g.interiors]):
                            hatch.paths.add_polyline_path(
                                list(ring.coords), is_closed=True,
                                flags=const.BOUNDARY_PATH_EXTERNAL if k == 0 else const.BOUNDARY_PATH_DEFAULT)
        if view.centre_marks:
            # One cross per CENTRE, sized to the largest circle on it. A counterbore
            # is two concentric circles, and two crosses drawn over each other fill
            # the CENTER linetype's gaps in: the centre line printed solid, which is
            # the one thing its dashes are there to say it is not.
            # A section cuts its bores and bosses in half, which leaves no full
            # cylinder to find their axes by; the whole part's axes that reach the
            # kept side of the plane (or lie in it) are the section's.
            turned = part_axes(view.shape)
            if cut:
                look = _look(view)
                turned = [a for a in turned if min(_dot(tuple(e - c for e, c in zip(end, cut[2])), look)
                                                   for end in (a.start, a.end)) <= 1e-6]
            for centre, radius in _centres(_circles(proj.visible) + _end_on(view, proj, turned)):
                c = to_sheet(centre)
                arm = radius * sv + 2.0
                centre_line((c[0] - arm, c[1]), (c[0] + arm, c[1]))
                centre_line((c[0], c[1] - arm), (c[0], c[1] + arm))
            # And a centre line down every turned feature seen from the side: a
            # shaft's axis, a bore drawn hidden through a plate.
            for a, b in _axis_lines(view, proj, turned, to_sheet):
                centre_line(a, b)
            # A slot seen end-on: a centre line down its length and one across each
            # rounded end. A bolt circle: its pitch circle as a chain line.
            look = _look(view)
            features = part_features(view.shape)

            def kept(feature, run: float) -> bool:
                return _shows(view, proj, feature, run, cut)

            for slot in features.slots:
                if not _looks_down(slot.axis, look) or not kept(slot, slot.run):
                    continue
                a, b = to_sheet(proj.point(slot.ends[0])), to_sheet(proj.point(slot.ends[1]))
                run = math.hypot(b[0] - a[0], b[1] - a[1]) or 1.0
                u = ((b[0] - a[0]) / run, (b[1] - a[1]) / run)
                reach = slot.width / 2 * sv + _CENTRE_OVERSHOOT
                centre_line((a[0] - u[0] * reach, a[1] - u[1] * reach), (b[0] + u[0] * reach, b[1] + u[1] * reach))
                for end in (a, b):
                    centre_line((end[0] + u[1] * reach, end[1] - u[0] * reach),
                                (end[0] - u[1] * reach, end[1] + u[0] * reach))
            for circle in features.circles:
                members = [h for h in features.holes if h.mouth in circle.mouths]
                if _looks_down(circle.axis, look) and any(kept(h, h.length) for h in members):
                    centre_circle(to_sheet(proj.point(circle.centre)), circle.diameter / 2 * sv)
        if view._detail is not None:
            # The detail's own boundary: a thin continuous circle, as ISO 128-34 draws it.
            msp.add_circle(view.at, view._detail.radius * sv, dxfattribs={"layer": "NOTES"})
        vx0, vx1, vy0, vy1 = own_box
        if view._symmetric:
            # Through the part's middle, which a break off the middle moves away from
            # the middle of the drawn view.
            centre = model_to_sheet(tuple(view.shape.bounding_box().center()))
        for direction in sorted(view._symmetric):
            # ISO 129-1: the centre line across the part, two short strokes square to
            # it beyond each end.
            middle, (lo, hi) = ((centre[0], (vy0, vy1)) if direction == "v" else (centre[1], (vx0, vx1)))
            ends = [(middle, lo - _SYMMETRY_REACH), (middle, hi + _SYMMETRY_REACH)]
            line = [(e[0], e[1]) if direction == "v" else (e[1], e[0]) for e in ends]
            msp.add_line(line[0], line[1], dxfattribs={"layer": "CENTER"})
            for end, outward in ((lo, -1.0), (hi, 1.0)):
                for step in _SYMMETRY_STROKES:
                    at = end + outward * step
                    stroke = [(middle - _SYMMETRY_HALF, at), (middle + _SYMMETRY_HALF, at)]
                    if direction == "h":
                        stroke = [(q, p) for p, q in stroke]
                    msp.add_line(stroke[0], stroke[1], dxfattribs={"layer": "NOTES"})
        centres = [to_sheet(c) for c, _r in _centres(_circles(proj.visible) + _end_on(view, proj, part_axes(view.shape)))]

        # How far annotation already reaches past each side of the view, so a
        # callout lands outside the dimensions on its side. Callouts on one side
        # share a knee and stack upward instead of pushing each other outward.
        reach = {"left": 0.0, "right": 0.0, "top": 0.0, "bottom": 0.0}
        for side in plane_sides.get(id(view), ()):
            reach[side] = _PLANE_ROOM  # the cutting plane's letters, drawn after the views
        for direction in view._symmetric:
            # The symmetry line runs past both ends, its strokes on it.
            for side in (("top", "bottom") if direction == "v" else ("left", "right")):
                reach[side] = max(reach[side], _SYMMETRY_REACH + 1.0)
        landings: dict[str, list[float]] = {side: [] for side in _SIDES}

        def landing_y(side, y, *, commit: bool = False, lines: int = 1):
            """The first free height for a callout landing on ``side`` at or past
            ``y``, clear for each of its ``lines`` (stacked down from the landing);
            ``commit`` takes them. Stacked callouts climb, except below the view,
            where they go down."""
            step = _CALLOUT_STACK * th * (-1.0 if side == "bottom" else 1.0)
            pitch = _CALLOUT_LINE * th
            while any(abs(y - k * pitch - used) < th * 1.6 for used in landings[side] for k in range(lines)):
                y += step
            if commit:
                landings[side].extend(y - k * pitch for k in range(lines))
            return y

        def state(value: float, axis: int | None) -> None:
            if record is not None:
                record["values"].append(value)
                if axis is not None:
                    record["axes"].add((axis, round(value, 3)))

        def linear(a, b, offset, side, row, override, orientation, tol=None, fit=None, true=None, *,
                   basic=False, reference=False, limits=None, name="overall", frame=None, datum=None, keyed=False,
                   ends=None):
            """``true`` is the length measured on the whole part, when the paper's
            is shorter: a dimension across a broken view's break. ``name`` says
            which dimension it is in a message. An ``aligned`` one runs along the
            line from ``a`` to ``b``, off the side away from the view's middle."""
            aligned = orientation == "aligned"
            horizontal = not aligned and (orientation or _spans(a, b)) == "h"
            if aligned:
                length = math.hypot(b[0] - a[0], b[1] - a[1])
                left = (-(b[1] - a[1]) / length, (b[0] - a[0]) / length)
                if offset is None:
                    middle = ((a[0] + b[0]) / 2 - (vx0 + vx1) / 2, (a[1] + b[1]) / 2 - (vy0 + vy1) / 2)
                    offset = _DIM_ROW if middle[0] * left[0] + middle[1] * left[1] >= 0 else -_DIM_ROW
            elif offset is None:
                # The row the plan gave it, measured from the VIEW's edge, so two
                # dimensions on different features still land on different lines.
                if horizontal:
                    offset = ((vy1 + _DIM_ROW * row) - max(a[1], b[1]) if side == "top"
                              else (vy0 - _DIM_ROW * row) - min(a[1], b[1]))
                else:
                    offset = ((vx1 + _DIM_ROW * row) - max(a[0], b[0]) if side == "right"
                              else (vx0 - _DIM_ROW * row) - min(a[0], b[0]))
            label = (override or "<>") + (f" {fit}" if fit else "")
            if reference:
                label = f"({label})"
            # The value is measured in SHEET millimetres, which are the model's only
            # at 1:1. dimlfac scales what the dimension prints back to true size, per
            # view, so a view drawn at its own scale still reads the part.
            style_override = {"dimlfac": 1.0 / sv}
            # A dimension to a hole's or a boss's centre runs its extension line as a
            # centre line, the way a drafter extends the centre mark to the dimension.
            for point, key in ((a, "dimltex1"), (b, "dimltex2")):
                if any(math.hypot(point[0] - c[0], point[1] - c[1]) < _SAME_PLACE * sv for c in centres):
                    style_override[key] = "CENTER"
            if tol:
                # The deviations are the author's, in true size, and ezdxf prints them
                # as given -- dimlfac scales the measurement, not the tolerance.
                style_override |= {"dimtol": 1, "dimtp": tol[0], "dimtm": tol[1],
                                   "dimtdec": _places(*tol), "dimtfac": 0.7}
            span = length if aligned else abs(b[0] - a[0]) if horizontal else abs(b[1] - a[1])
            measured = span / sv
            if true is not None and abs(true - measured) > 1e-6:
                # The paper's length is the broken view's; the value is the part's.
                measured = true
                label = label.replace("<>", _fmt(true))
            # What prints stacked, one half over the other: unequal deviations after
            # the value, or the two limits in its place.
            stack = None
            if tol and abs(tol[0] - tol[1]) > 1e-9:
                stack = (f"+{_exact(tol[0])}", f"-{_exact(tol[1])}")
            printed = label.replace("<>", _fmt(measured))
            if limits is not None:
                low, high = limits
                if not low - 1e-6 <= measured <= high + 1e-6:
                    raise ValueError(f"{view.name} {name}: limits=({_fmt(low)}, {_fmt(high)}) do not hold the part, "
                                     f"which measures {_fmt(measured)} there. Give the limits the design requires, "
                                     "or change the model.")
                # The two limits, stacked where the value would print, its prefix and
                # suffix kept: ezdxf's own limits (dimlim) print the stack alone, and a
                # bore's ⌀12.000-12.025 read as a width of 12.
                places = _places(low, high)
                stack = (f"{high:.{places}f}", f"{low:.{places}f}")
                printed = label.replace("<>", "")
                label = label.replace("<>", f"{{\\H0.70x;\\S{stack[0]}^ {stack[1]};}}")
            if basic:
                style_override["dimgap"] = -abs(th * 0.25)  # a negative gap is the DXF's mark of a basic value
            # A value wider than the space between its extension lines is set beside
            # them, on the dimension line's side, instead of across them: centred,
            # "3 WALL" printed with both witness lines running through its glyphs.
            # One that fits stays centred and only its arrows go outside.
            width = _ink_width(printed, th)
            if tol and abs(tol[0] - tol[1]) < 1e-9:
                width += _text_width(_tol_suffix(tol), th * 0.7)
            if stack is not None:
                # A stack is as wide as its wider half.
                width += (th * 0.35 if printed.strip() else 0.0) + max(_text_width(v, th * 0.7) for v in stack)
            # A key characteristic's mark follows a value along its line, so the two
            # fit between the extension lines together or are set beside them together.
            beside = width + (th * 0.5 + mark_width(key_mark, th) if keyed and horizontal else 0.0)
            # How far the value's middle stands off its dimension line: ezdxf's gap
            # and half the text for one line. A stack draws 1.7 text heights tall
            # about that middle, its lower half through the line, so it stands half
            # a text height further off: its glyphs clear the line as one line's do.
            stand = 1.0 + th / 2 + (th / 2 if stack is not None else 0.0)
            arrow = th * 0.85
            location = None
            if aligned:
                base = (a[0] + left[0] * offset, a[1] + left[1] * offset)
                d = msp.add_linear_dim(base=base, p1=a, p2=b, angle=math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])),
                                       dimstyle=dimstyle, text=label, override=style_override,
                                       dxfattribs={"layer": "DIM"})
                for x, y in (base, (b[0] + left[0] * offset, b[1] + left[1] * offset)):
                    reach["top"] = max(reach["top"], y - vy1 + th * 1.5)
                    reach["bottom"] = max(reach["bottom"], vy0 - y + th * 1.5)
                    reach["right"] = max(reach["right"], x - vx1 + th * 1.5)
                    reach["left"] = max(reach["left"], vx0 - x + th * 1.5)
            elif horizontal:
                base = (a[0], (max(a[1], b[1]) if offset >= 0 else min(a[1], b[1])) + offset)
                if beside + 1.0 > span:
                    location = (max(a[0], b[0]) + 1.5 * arrow + 1.0 + width / 2, base[1] + stand)
                    reach["right"] = max(reach["right"], location[0] + width / 2 - vx1 + 1.0)
                d = msp.add_linear_dim(base=base, p1=a, p2=b, location=location, angle=0, dimstyle=dimstyle,
                                       text=label, override=style_override, dxfattribs={"layer": "DIM"})
                side = "top" if offset >= 0 else "bottom"
                edge = vy1 if offset >= 0 else vy0
                reach[side] = max(reach[side], abs(base[1] - edge) + th * 1.5)
            else:
                base = ((max(a[0], b[0]) if offset >= 0 else min(a[0], b[0])) + offset, a[1])
                if beside + 1.0 > span:
                    location = (base[0] - stand, max(a[1], b[1]) + 1.5 * arrow + 1.0 + width / 2)
                    reach["top"] = max(reach["top"], location[1] + width / 2 - vy1 + 1.0)
                d = msp.add_linear_dim(base=base, p1=a, p2=b, location=location, angle=90, dimstyle=dimstyle,
                                       text=label, override=style_override, dxfattribs={"layer": "DIM"})
                side = "right" if offset >= 0 else "left"
                edge = vx1 if offset >= 0 else vx0
                reach[side] = max(reach[side], abs(base[0] - edge) + th * 1.5)
            d.render()
            if stack is not None and location is None and not aligned:
                # A centred stack, stood off its line as one set beside it is.
                value = next(e for e in doc.blocks.get(d.dimension.dxf.geometry) if e.dxftype() == "MTEXT")
                x, y = value.dxf.insert.x, value.dxf.insert.y
                value.dxf.insert = (x, base[1] + stand) if horizontal else (base[0] - stand, y)
                reach[side] += th / 2
            if location is not None:
                # ezdxf leaves a value set beside its dimension floating; the
                # dimension line runs on under it, as a drafter draws it.
                run = ((max(a[0], b[0]), base[1]), (location[0] + width / 2, base[1])) if horizontal else \
                    ((base[0], max(a[1], b[1])), (base[0], location[1] + width / 2))
                doc.blocks.get(d.dimension.dxf.geometry).add_line(*run, dxfattribs={"layer": "DIM"})
            claim_rendered(d.dimension)
            _draw_dimension_symbols(doc, d.dimension)
            if basic:
                _box_dimension_value(doc, d.dimension)
            if keyed or frame is not None or datum is not None:
                # A key characteristic's mark follows the value; the frame takes the
                # rows the plan kept beyond it, the datum symbol on the frame's outer
                # edge, or on the value's. Beside an upright value they run outward.
                value = next(e for e in doc.blocks.get(d.dimension.dxf.geometry) if e.dxftype() == "MTEXT")
                vx, vy = value.dxf.insert.x, value.dxf.insert.y
                out = 1.0 if offset >= 0 else -1.0
                toward = (0.0, out) if horizontal else (out, 0.0)
                tip = (vx, vy + out * th) if horizontal else (vx + out * th, vy)
                if keyed:
                    width = mark_width(key_mark, th)
                    if horizontal:
                        length, _tall = _mtext_extent(value.text, value.dxf.char_height)
                        box = _draw_mark(msp, key_mark, vx + length / 2 + th * 0.5, vy, th)
                    else:
                        box = _draw_mark(msp, key_mark, tip[0] if out > 0 else tip[0] - width, vy, th)
                        tip = (box[2] + th * 0.5 if out > 0 else box[0] - th * 0.5, vy)
                    claim(f"{name} key mark", box)
                if frame is not None:
                    width, cell = frame_size(frame, th)
                    if horizontal:
                        box = _draw_frame(msp, frame, vx - width / 2, vy + out * _DIM_ROW, th)
                    else:
                        box = _draw_frame(msp, frame, tip[0] if out > 0 else tip[0] - width, vy, th)
                    claim(f"frame {frame.characteristic}", box)
                    tip = (((box[0] + box[2]) / 2, box[3] if out > 0 else box[1]) if horizontal
                           else (box[2] if out > 0 else box[0], (box[1] + box[3]) / 2))
                if datum is not None:
                    claim(f"datum {datum}", _draw_datum(msp, datum, tip, toward, th))
                    tip = (tip[0] + toward[0] * _DATUM_REACH * th, tip[1] + toward[1] * _DATUM_REACH * th)
                side_name = ("top" if out > 0 else "bottom") if horizontal else ("right" if out > 0 else "left")
                edge = {"top": vy1, "bottom": vy0, "right": vx1, "left": vx0}[side_name]
                reach[side_name] = max(reach[side_name], abs((tip[1] if horizontal else tip[0]) - edge) + th)
            # The dimension line, which no leader or other dimension line may cross.
            if aligned:
                dimension_lines.append(((a[0] + left[0] * offset, a[1] + left[1] * offset),
                                        (b[0] + left[0] * offset, b[1] + left[1] * offset)))
            elif horizontal:
                far = max(a[0], b[0]) if location is None else location[0] + width / 2
                dimension_lines.append(((min(a[0], b[0]), base[1]), (far, base[1])))
            else:
                far = max(a[1], b[1]) if location is None else location[1] + width / 2
                dimension_lines.append(((base[0], min(a[1], b[1])), (base[0], far)))
            axis = _sheet_axis(proj, horizontal)
            if aligned:
                # Along a model axis only when the edge happens to run along one.
                run = [q - p for p, q in zip(*ends)] if ends is not None else [1.0, 1.0, 1.0]
                axis = next((k for k in range(3) if all(abs(run[j]) < 1e-9 for j in range(3) if j != k)), None)
            # A reference dimension states no requirement; an assembly's envelope is
            # stated by one all the same, being information nobody inspects.
            if not reference or (record is not None and record["assembly"]):
                state(measured, axis)
            elif record is not None and axis is not None:
                # A reference size asks nothing; it is information about a size the
                # other dimensions fix, which the report checks they do.
                record["referenced"].add((axis, round(measured, 3)))
            if aligned and record is not None and ends is not None and not reference:
                record["aligned"].append(tuple(ends))
            if record is not None and ends is not None and axis is not None and not reference:
                # What it ties together, along the model axis it measures, what it is
                # called in a message, what kind of statement it is, and its two ends.
                # A diameter across a profile is a feature's size, not a step in a chain.
                kind = "basic" if basic else "diameter" if "%%c" in (override or "").lower() else "size"
                record["spans"].append((axis, ends[0][axis], ends[1][axis], f"{_fmt(measured)} ({view.name} {name})",
                                        kind, tuple(ends)))

        def on_view(point, margin: float = 1.0) -> bool:
            """Does a projected point land on the view's own drawn extent?"""
            return (vx0 - margin <= point[0] <= vx1 + margin
                    and vy0 - margin <= point[1] <= vy1 + margin)

        def check(kind: str, index: int | str, *points) -> None:
            # A dimension between two points in SPACE draws perfectly and measures
            # nothing: move the holes in the model, leave the constants alone, and
            # the sheet prints a clean dimension over blank paper. The commonest
            # cause is model coordinates assumed to be centred when the part was
            # built from a corner.
            off = [p for p in points if not on_view(p)]
            if off:
                where = ", ".join(f"({p[0]:.1f}, {p[1]:.1f})" for p in off)
                raise ValueError(
                    f"{view.name} {kind} {index}: {len(off)} of {len(points)} point(s) fall outside the "
                    f"view's geometry at sheet {where}, so it would measure blank paper; check the model "
                    "coordinates it was given."
                )

        # A broken view's overall sizes are the whole part's, not the paper's.
        whole = _bbox_bounds(view.shape, proj, raw=True) if view._break is not None else None
        # Dimensions first, in the rows the plan gave them, then the overall pair
        # outermost, then the callouts outside all of them, then notes and angles.
        for dim in items:
            if dim.kind == "linear":
                a, b = model_to_sheet(dim.p1), model_to_sheet(dim.p2)
                check("dim", dim.index, a, b)
                across, up = abs(b[0] - a[0]) / sv, abs(b[1] - a[1]) / sv
                if dim.orientation is None and min(across, up) > 0.5 and min(across, up) > 0.5 * max(across, up):
                    # Which span it measures would be a guess: the larger once printed, said only as a warning.
                    raise ValueError(
                        f"{view.name} dim {dim.index}: its points are {_fmt(across)} apart across and {_fmt(up)} "
                        f"up, so it could measure either. Pass orientation=\"h\", \"v\" or \"aligned\", or give "
                        "two points that differ in one direction only."
                    )
                true = None
                if view._break is not None:
                    axis, low, high = view._break
                    inside = [p for p in (dim.p1, dim.p2) if low < p[axis] < high]
                    if inside:
                        raise ValueError(f"{view.name} dim {dim.index}: {_where(inside[0])} is inside the break, "
                                         "which the view leaves out; dimension to a point the view shows.")
                    ra, rb = proj._raw_point(dim.p1), proj._raw_point(dim.p2)
                    if dim.orientation == "aligned":
                        across = [abs(dim.p2[k] - dim.p1[k]) for k in range(3) if k != axis]
                        if (min(dim.p1[axis], dim.p2[axis]) < low < high < max(dim.p1[axis], dim.p2[axis])
                                and max(across) > 1e-9):
                            raise ValueError(
                                f"{view.name} dim {dim.index}: an aligned dimension across the break, inclined to it, "
                                "would be drawn at the shortened view's angle, not the part's. Dimension the edge "
                                "in a view without the break, or along the break axis.")
                        true = math.hypot(rb[0] - ra[0], rb[1] - ra[1])
                    else:
                        horizontal = (dim.orientation or _spans(a, b)) == "h"
                        true = abs(rb[0] - ra[0]) if horizontal else abs(rb[1] - ra[1])
                linear(a, b, dim.offset, dim.side, dim.row, dim.text, dim.orientation, dim.tol, dim.fit, true,
                       basic=dim.basic, reference=dim.reference, limits=dim.limits, name=f"dim {dim.index}",
                       frame=dim.frame, datum=dim.datum, keyed=dim.key, ends=(dim.p1, dim.p2))
        extent = view.shape.bounding_box()
        corners = ((extent.min.X, extent.min.Y, extent.min.Z), (extent.max.X, extent.max.Y, extent.max.Z))
        if view._overall:
            outline = [to_sheet(p) for edge in proj.visible for p in _edge_points(edge)]
        if "width" in view._overall:
            linear(*_overall_ends(outline, own_box, True), None, "top", plan["overall"]["top"], None, "h",
                   true=whole[1] - whole[0] if whole else None, reference=view._overall_reference, ends=corners)
        if "height" in view._overall:
            linear(*_overall_ends(outline, own_box, False), None, "left", plan["overall"]["left"], None, "v",
                   true=whole[3] - whole[2] if whole else None, reference=view._overall_reference, ends=corners)
        # How far the callouts reach past each side, so balloons drawn later
        # stand outside them; callouts on one side share a knee, so this is not
        # applied until they are all placed.
        callout_reach = dict.fromkeys(_SIDES, 0.0)
        for dim in items:
            if dim.kind not in ("diameter", "radius", "hole", "slot"):
                continue
            # A callout: a radial leader from the circle to a horizontal landing
            # outside the view, past whatever dimensions stand on that side, with
            # the text reading along the landing. Stacked callouts on one side land
            # at their own hole's height.
            centre = model_to_sheet(dim.p1)
            check(dim.kind, dim.index, centre)
            r = dim.radius * sv
            value = _callout_value(dim)
            lines = _callout_lines(dim, th)
            wide = max(_ink_width(line, th) for line in lines)
            pitch = _CALLOUT_LINE * th
            # Exit on the hole's own side of the view (the short way out), unless the
            # landing there would run into another view or off the frame; then the
            # other side. A leader across the whole part is the last resort.
            # A hole on the centreline leaves to the left: in third angle the right
            # of the upper view is where the pictorial goes.
            # The ways out, tried in turn until one crosses no dimension line, runs into
            # no other view and lands on no text already printed: the hole's own side,
            # the short way out; that side past the rows above or below, out of the
            # corner, the hole's half first; straight above or below the view; the
            # far side, across the part.
            prefer_right = centre[0] > (vx0 + vx1) / 2 + 1e-6
            own = "right" if prefer_right else "left"
            far = "left" if prefer_right else "right"
            near = "top" if centre[1] >= (vy0 + vy1) / 2 else "bottom"
            exit_angle = math.radians(dim.angle if dim.angle is not None else 45.0)
            # What hangs under the callout's text: its frame, its datum symbol.
            under_width = frame_size(dim.frame, th)[0] if dim.frame is not None else 0.0
            # A key characteristic's mark at the text's outer end.
            beside = mark_width(key_mark, th) + th * 0.5 if dim.key else 0.0
            # How far the callout's line reaches down: its text, or a key mark's box.
            head = _FRAME_HEIGHT * th / 2 if dim.key else th * 0.6
            under_depth = (head - th * 0.6 + (frame_size(dim.frame, th)[1] + 1.0 if dim.frame is not None else 0.0)
                           + (_DATUM_REACH * th if dim.datum is not None else 0.0) + (len(lines) - 1) * pitch)

            def past(vertical: str, step: int) -> float:
                """A landing height past the dimension rows above or below the view, and
                ``step`` landings further out, should text already stand there."""
                outward = 1.0 if vertical == "top" else -1.0
                return (vy1 if vertical == "top" else vy0) + outward * (reach[vertical] + _CALLOUT_CLEAR
                                                                        + step * _CALLOUT_STACK * th)

            def way(kind: str, side: str, step: int = 0, inward: bool = False):
                """(landings key, knee, sign) for one way out. A callout straight above
                or below the view reads toward the hole's own side, or ``inward``."""
                if kind == "vertical":
                    sign = (1.0 if prefer_right else -1.0) * (-1.0 if inward else 1.0)
                    y = landing_y(side, past(side, step), lines=len(lines))
                    return side, (centre[0] + sign * abs(y - centre[1]) / math.tan(math.radians(60.0)), y), sign
                beside, vertical = (side, None) if kind == "side" else (own, side)
                sign = 1.0 if beside == "right" else -1.0
                x = (vx1 + reach[beside] + _CALLOUT_CLEAR) if beside == "right" else (vx0 - reach[beside] - _CALLOUT_CLEAR)
                y = centre[1] + r * math.sin(exit_angle) + 6.0
                if vertical is not None:
                    y = max(y, past(vertical, step)) if vertical == "top" else min(y, past(vertical, step))
                return beside, (x, landing_y(beside, y, lines=len(lines))), sign

            def clear_of(knee, sign: float, below: bool) -> tuple[bool, bool]:
                """Whether a way out runs into nothing, and whether it crosses no line.
                ``below``: straight below the view, where the view's label then hangs
                under it and needs the paper too."""
                run = math.hypot(knee[0] - centre[0], knee[1] - centre[1]) or 1.0
                start = (centre[0] + r * (knee[0] - centre[0]) / run, centre[1] + r * (knee[1] - centre[1]) / run)
                landing = (knee[0] + sign * _CALLOUT_LANDING, knee[1])
                far_end = landing[0] + sign * (_CALLOUT_GAP + max(wide + beside, under_width))
                x0, x1 = min(landing[0], far_end), max(landing[0], far_end)
                y0, y1 = knee[1] - th - under_depth, knee[1] + th
                free = (not blocked(x0, x1, y0, y1, own_box)
                        and not any(x0 < b[2] and x1 > b[0] and y0 < b[3] and y1 > b[1] for _v, b in claimed)
                        and not _runs_through((start, knee, landing),
                                              [*furnished, *(b for b in boxes if b is not own_box)]))
                if below:
                    label = knee[1] - th - _LABEL_GAP - _LABEL_HEIGHT
                    free = free and not blocked(vx0, vx1, label, knee[1] - th, own_box)
                return free, not _crosses_any((start, knee, landing), [*dimension_lines, *leaders])

            def crowded(vertical: str) -> bool:
                """Whether another view stands that way, over this one's width."""
                return any(box is not own_box and box[0] < vx1 and box[1] > vx0
                           and (box[2] >= vy1 if vertical == "top" else box[3] <= vy0) for box in boxes)

            # Out of a corner, into free paper first: the gap shared with the next view
            # is that view's too.
            corners = sorted(("top", "bottom"), key=lambda v: (crowded(v), v != near))
            ways = [("side", own, False), ("corner", corners[0], False), ("corner", corners[1], False),
                    ("vertical", corners[0], False), ("vertical", corners[0], True), ("side", far, False)]
            chosen = None
            for kind, side, inward in ways:
                # Past the rows, a landing may stand a few further out to clear text
                # another view's annotation already put there.
                for step in range(_CALLOUT_STEPS if kind != "side" else 1):
                    landed, knee, sign = way(kind, side, step, inward)
                    free, uncrossed = clear_of(knee, sign, kind == "vertical" and side == "bottom")
                    if free and uncrossed:
                        chosen = (kind, side, landed, knee, sign)
                        break
                if chosen is not None:
                    break
            if chosen is None:
                # Every way crosses a line or lands on something: the short way, said.
                landed, knee, sign = way("side", own)
                chosen = ("side", own, landed, knee, sign)
            kind, way_side, side, knee, sign = chosen
            knee = (knee[0], landing_y(side, knee[1], commit=True, lines=len(lines)))
            if kind == "side" and side == far and warnings is not None:
                warnings.append(
                    f"{view.name} {dim.kind} {dim.index}: there is no room for {_shown(value)!r} on the {own}, "
                    "so its leader crosses the view to the other side. Give the view more room (a larger "
                    "sheet, or three_views(gap=...)), or call out a hole of the same kind nearer the other edge."
                )
            # The leader points at the centre, as a leader to a circle must, and
            # stops on the circle; then it runs level to the text.
            run = math.hypot(knee[0] - centre[0], knee[1] - centre[1]) or 1.0
            start = (centre[0] + r * (knee[0] - centre[0]) / run, centre[1] + r * (knee[1] - centre[1]) / run)
            landing = (knee[0] + sign * _CALLOUT_LANDING, knee[1])
            msp.add_leader([start, knee, landing], dxfattribs={"layer": "DIM"},
                           override={"dimasz": th * 0.85, "dimldrblk": "_CLOSEDFILLED"})
            leaders.append((start, knee, landing))
            align = TextEntityAlignment.MIDDLE_LEFT if sign > 0 else TextEntityAlignment.MIDDLE_RIGHT
            for k, line in enumerate(lines):
                text(line, landing[0] + sign * _CALLOUT_GAP, landing[1] - k * pitch, th, align, "DIM")
            if dim.key:
                outer = landing[0] + sign * (_CALLOUT_GAP + _ink_width(lines[0], th) + th * 0.5)
                claim(f"{view.name} {dim.kind} {dim.index} key mark",
                      _draw_mark(msp, key_mark, outer if sign > 0 else outer - mark_width(key_mark, th),
                                 landing[1], th))
            if dim.basic:
                _box_text(msp, _text_box(value, landing[0] + sign * _CALLOUT_GAP, landing[1], th, align))
            if dim.frame is not None or dim.datum is not None:
                # Under the callout: its frame, then the datum symbol the feature is.
                attach, under = landing[0] + sign * _CALLOUT_GAP, landing[1] - head - 1.0 - (len(lines) - 1) * pitch
                box = (attach, under, attach, under)
                if dim.frame is not None:
                    width, cell = frame_size(dim.frame, th)
                    box = _draw_frame(msp, dim.frame, attach if sign > 0 else attach - width, under - cell / 2, th)
                    claim(f"frame {dim.frame.characteristic}", box)
                if dim.datum is not None:
                    claim(f"datum {dim.datum}", _draw_datum(msp, dim.datum, ((box[0] + box[2]) / 2, box[1]),
                                                            (0.0, -1.0), th))
            if side in ("left", "right"):
                tip = landing[0] + sign * (_CALLOUT_GAP + wide)
                callout_reach[side] = max(callout_reach[side], abs(tip - (vx1 if side == "right" else vx0)) + _CALLOUT_GAP)
            if kind == "vertical":
                # Straight above or below the view: the label and anything placed later
                # stand past it. A corner's text is beside the view, outside its column.
                edge = vy1 if way_side == "top" else vy0
                callout_reach[way_side] = max(callout_reach[way_side], abs(knee[1] - edge) + th)
            if warnings is not None and _crosses_any((start, knee, landing), dimension_lines):
                warnings.append(f"{view.name} {dim.kind} {dim.index}: its leader crosses a dimension line; move "
                                "the dimension, or call out the feature in a view with room around it")
            if record is not None:
                # A hole callout states its hole; a diameter callout states a diameter.
                # A leader's radius is neither, so it is not a stated value.
                if dim.kind in ("hole", "slot") and dim.feature is not None:
                    record["called"].update(_member_key(f) for f in (dim.covers or (dim.feature,)))
                elif dim.kind == "diameter" and not dim.reference:
                    record["values"].append(2 * dim.radius)
                elif dim.kind == "radius" and not dim.reference:
                    record["radii"].add(round(dim.radius, 3))
        for name, value in callout_reach.items():
            reach[name] = max(reach[name], value)
        if id(view) in tables:
            _draw_hole_tags(msp, tables[id(view)], proj, to_sheet, sv, th, text)
            if record is not None:
                table = tables[id(view)]
                record["called"].update(_member_key(row.feature) for row in table.rows)
                # A table gives each hole's X and Y from its origin.
                for axis in (_sheet_axis(proj, True), _sheet_axis(proj, False)):
                    if axis is not None:
                        record["spans"].extend((axis, table.origin[axis], row.feature.mouth[axis], "hole table", "table",
                                                (table.origin, row.feature.mouth))
                                               for row in table.rows)
        if record is not None:
            for dim in items:
                if dim.datum and dim.kind in ("hole", "slot") and dim.feature is not None:
                    # A feature of size made a datum locates from its centre.
                    record["anchors"].extend((axis, dim.feature.mouth[axis]) for axis in range(3))
        for dim in items:
            if dim.kind == "angle":
                v = model_to_sheet(dim.p1)
                a = model_to_sheet(dim.p2)
                b = model_to_sheet(dim.hole["p2"])
                check("angle", dim.index, v, a, b)
                if record is not None and not dim.reference:
                    record["angles"].append((dim.p1, dim.p2, dim.hole["p2"], _look(view)))
                ua = math.atan2(a[1] - v[1], a[0] - v[0])
                ub = math.atan2(b[1] - v[1], b[0] - v[0])
                if (ub - ua) % (2 * math.pi) > math.pi:
                    # The DXF measures anticlockwise from its first leg; the angle
                    # between the legs is the one under half a turn.
                    a, b, ua, ub = b, a, ub, ua
                mid = ua + ((ub - ua + math.pi) % (2 * math.pi) - math.pi) / 2
                base = (v[0] + dim.offset * math.cos(mid), v[1] + dim.offset * math.sin(mid))
                d = msp.add_angular_dim_3p(base=base, center=v, p1=a, p2=b, dimstyle=dimstyle,
                                           text="(<>)" if dim.reference else "<>",
                                           override={"dimgap": -abs(th * 0.25)} if dim.basic else None,
                                           dxfattribs={"layer": "DIM"})
                d.render()
                claim_rendered(d.dimension)
                if dim.basic:
                    _box_dimension_value(doc, d.dimension)
            elif dim.kind == "frame":
                p = model_to_sheet(dim.p1)
                check("frame", dim.index, p)
                q = (p[0] + dim.radius, p[1] + dim.angle)
                right = dim.radius >= 0
                msp.add_leader([p, q, (q[0] + (3 if right else -3), q[1])], dxfattribs={"layer": "DIM"},
                               override={"dimasz": th * 0.85, "dimldrblk": "_CLOSEDFILLED"})
                width, cell = frame_size(dim.frame, th)
                box = _draw_frame(msp, dim.frame, q[0] + 3 if right else q[0] - 3 - width, q[1], th)
                claim(f"frame {dim.frame.characteristic}", box)
                reach["bottom"] = max(reach["bottom"], vy0 - box[1] + 1.0)
            elif dim.kind == "note":
                p = model_to_sheet(dim.p1)
                check("note", dim.index, p)
                q = (p[0] + dim.radius, p[1] + dim.angle)
                msp.add_leader([p, q, (q[0] + (3 if dim.radius >= 0 else -3), q[1])], dxfattribs={"layer": "NOTES"},
                               override={"dimasz": th * 0.85, "dimldrblk": "_CLOSEDFILLED"})
                align = TextEntityAlignment.BOTTOM_LEFT if dim.radius >= 0 else TextEntityAlignment.BOTTOM_RIGHT
                text(dim.text, q[0] + (4 if dim.radius >= 0 else -4), q[1] + 1, th, align, "NOTES")
                # A note hanging below the view pushes the view's label down, as a
                # dimension row there does.
                reach["bottom"] = max(reach["bottom"], vy0 - q[1] + 1.0)

        for letter, point, stem in view._datums:
            # A datum feature symbol stands on its surface, its stem leading out of
            # the view by the nearest side unless the author pointed it.
            if record is not None:
                record["datums"].append(point)
            tip = model_to_sheet(point)
            check("datum", letter, tip)
            toward = _datum_toward(tip, (vx0, vx1, vy0, vy1), stem)
            # A face inside the view's outline reaches its side first.
            inside = 0.0 if stem is not None else {
                (-1.0, 0.0): tip[0] - vx0, (1.0, 0.0): vx1 - tip[0], (0.0, -1.0): tip[1] - vy0,
                (0.0, 1.0): vy1 - tip[1]}[toward]
            box = _draw_datum(msp, letter, tip, toward, th, extra=inside)
            claim(f"datum {letter}", box)
            side = _side_of(toward)
            edge = {"top": vy1, "bottom": vy0, "right": vx1, "left": vx0}[side]
            far = {"top": box[3], "bottom": box[1], "right": box[2], "left": box[0]}[side]
            reach[side] = max(reach[side], abs(far - edge) + 1.0)

        if view._balloons:
            # Their circles and leaders, which a flag drawn next keeps clear of.
            for path, circle in _draw_balloons(msp, sheet, view, keyed_on_sheet, facts, model_to_sheet, own_box,
                                               reach, text, list(claimed),
                                               [b for b in boxes if b is not own_box] + furniture, warnings,
                                               anchors=section_anchors if view._section else None):
                leaders.append(path)
                claimed.append(("balloon", circle))

        part_lines = None

        def leader_spot(p, offset, land_of, box_of, search: bool):
            """Where a leader from ``p`` ends, its landing and the box of what it
            carries: at ``offset``, or, searching, the nearest spot out of the view
            clear of its annotation, the leader crossing no line and, where it can,
            none of the part's own; out by the side nearest ``p`` first, where the
            plan kept room. Returns the spot and whether a clear one was found."""
            nonlocal part_lines
            from shapely.geometry import LineString
            from shapely.ops import unary_union

            def at(off):
                q = (p[0] + off[0], p[1] + off[1])
                return q, land_of(q, off[0] >= 0), box_of(q, off[0] >= 0)

            def clear(q, land, box) -> bool:
                x0, y0, x1, y1 = box
                taken = [(b[0], b[2], b[1], b[3]) for _v, b in claimed]
                return (not blocked(x0, x1, y0, y1, own_box)
                        and not (x1 > vx0 and x0 < vx1 and y1 > vy0 and y0 < vy1)
                        and not any(x0 < t[1] and x1 > t[0] and y0 < t[3] and y1 > t[2] for t in taken)
                        and not _crosses_any((p, q, land), [*dimension_lines, *leaders])
                        and not _runs_through((q, land), taken))

            def crosses_part(q) -> bool:
                # Past its first millimetre: a seam's leader comes from outside.
                nonlocal part_lines
                if part_lines is None:
                    part_lines = unary_union([LineString([to_sheet(pt) for pt in _edge_points(e)])
                                              for e in proj.visible])
                run = math.hypot(q[0] - p[0], q[1] - p[1]) or 1.0
                start = (p[0] + (q[0] - p[0]) / run, p[1] + (q[1] - p[1]) / run)
                return LineString([start, q]).intersects(part_lines)

            if not search:
                return at(offset), True
            toward = _datum_toward(p, (vx0, vx1, vy0, vy1), None)
            ways = sorted(((0.7, 0.7), (-0.7, 0.7), (0.7, -0.7), (-0.7, -0.7)),
                          key=lambda u: -(u[0] * toward[0] + u[1] * toward[1]))
            tries = [at((ux * reach_out, uy * reach_out)) for pair in (ways[:2], ways[2:])
                     for reach_out in range(10, 90, 6) for ux, uy in pair]
            spot = (next((t for t in tries if clear(*t) and not crosses_part(t[0])), None)
                    or next((t for t in tries if clear(*t)), None))
            return (spot, True) if spot is not None else (at(offset), False)

        def reach_past(box) -> None:
            for name, beyond in (("top", box[3] - vy1), ("bottom", vy0 - box[1]), ("right", box[2] - vx1),
                                 ("left", vx0 - box[0])):
                reach[name] = max(reach[name], beyond + 1.0)

        for dim in items:
            if dim.kind != "flag":
                continue
            # A flag note: a leader to the flag, the flag numbered as its note.
            if dim.p1 is None and view._section:
                # On a section the item is flagged inside its own cut, where its
                # balloon lands: a ray from the viewer meets the half taken away.
                item = _item_of(view, dim.item)
                if item.number not in section_anchors:
                    letter = view._section[0]
                    raise ValueError(f"flag(item={dim.item!r}): SECTION {letter}-{letter} cuts none of item "
                                     f"{item.number} ({item.description or 'unnamed'}); flag it in a view that "
                                     "shows it, or with at=")
                p = section_anchors[item.number]
            else:
                p = model_to_sheet(dim.p1 if dim.p1 is not None else _item_point(view, dim.item))
            check("flag", dim.index, p)
            side, tall = _FLAG_SIDE * th, _FLAG_SIDE * th * math.sqrt(3) / 2
            number = len(sheet.drawn_notes()) - len(sheet._flags) + sheet._flags.index(dim.text) + 1
            (q, land, box), found = leader_spot(
                p, (dim.radius, dim.angle), lambda q, right: (q[0] + (side / 4 if right else -side / 4), q[1]),
                lambda q, right: (q[0] if right else q[0] - side, q[1] - tall / 2,
                                  q[0] + side if right else q[0], q[1] + tall / 2),
                search=dim.offset is None)
            if not found and warnings is not None:
                warnings.append(f"{view.name} flag {number}: no clear place near its point; "
                                "flag(..., offset=(x, y)) places it")
            msp.add_leader([p, q, land], dxfattribs={"layer": "DIM"},
                           override={"dimasz": th * 0.85, "dimldrblk": "_CLOSEDFILLED"})
            _draw_flag(msp, str(number), box[0], q[1], side, "DIM")
            claim(f"flag {number}", box)
            leaders.append((p, q, land))
            reach_past(box)

        for p, label in thin:
            # A layer too thin to hatch is filled solid and named where it is.
            width = _ink_width(label, th)
            (q, land, box), found = leader_spot(
                p, (10.0, 10.0), lambda q, right: (q[0] + (3.0 if right else -3.0), q[1]),
                lambda q, right: ((q[0] + 4.0, q[1] - th * 0.6, q[0] + 4.0 + width, q[1] + th * 0.6) if right
                                  else (q[0] - 4.0 - width, q[1] - th * 0.6, q[0] - 4.0, q[1] + th * 0.6)),
                search=True)
            if not found and warnings is not None:
                warnings.append(f"{view.name}: the thin layer {label!r} has no clear place for its callout; give "
                                "the section more room, or draw a detail of it")
            msp.add_leader([p, q, land], dxfattribs={"layer": "NOTES"},
                           override={"dimasz": th * 0.85, "dimldrblk": "_CLOSEDFILLED"})
            right = land[0] > q[0]
            text(label, box[0] if right else box[2], q[1], th,
                 TextEntityAlignment.MIDDLE_LEFT if right else TextEntityAlignment.MIDDLE_RIGHT, "NOTES")
            leaders.append((p, q, land))
            reach_past(box)

        # The view label goes under everything that hangs below the view, so a
        # dimension on the bottom side never sits on it.
        text((view.label or view.name).upper(), view.at[0], vy0 - reach["bottom"] - _LABEL_GAP, _LABEL_HEIGHT,
             TextEntityAlignment.TOP_CENTER, "NOTES")

    for table in tables.values():
        _draw_hole_table(msp, table, text)
    from ezdxf import const

    for table, corner in zip(keyed, keyed_at):
        for (family, variant), (x0, y0, x1, y1) in _draw_sheet_table(msp, table, corner, text):
            # The part's own hatch, a swatch of it: its family's pattern, turned
            # and spaced as its region is.
            hatch = msp.add_hatch(dxfattribs={"layer": "DIM"})
            if family == "solid":
                hatch.set_solid_fill()
            else:
                pattern, angle = HATCHES[family]
                turn, spacing = _HATCH_TURNS[variant]
                hatch.set_pattern_fill(pattern, scale=_HATCH_SCALE * 0.5 * spacing, angle=angle + turn)
            hatch.paths.add_polyline_path([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], is_closed=True,
                                          flags=const.BOUNDARY_PATH_EXTERNAL)
            msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True, dxfattribs={"layer": "DIM"})

    # Each section's cutting plane, on a view that sees it edge-on.
    for view_id, (kept, _faces, point, _items) in cuts.items():
        view = drawn[view_id][0]
        if view._detail is not None:
            continue  # a detail of a section shares its section's plane, drawn once
        letter, look = view._section[0], _look(view)
        parent = _plane_parent(view, [other for other in sheet.views if id(other) in drawn])
        if parent is None:
            # A section whose plane no view shows says nothing of where it cuts.
            raise ValueError(
                f"SECTION {letter}-{letter} has no view on this sheet that sees its cutting plane edge-on, "
                f"so nothing shows where it cuts; add the {_PLANE_SHOWN_ON[view.name][0]} view."
            )
        _draw_cutting_plane(msp, drawn[id(parent)], point, look, letter, text, th)
    # Each detail's circle and letter on the view it enlarges.
    for view in sheet.views:
        if view._detail is None or id(view._detail.parent) not in drawn or id(view) not in drawn:
            continue
        parent, point, radius, letter, _auto, _chosen = view._detail
        _parent_view, parent_to_sheet, _box = drawn[id(parent)]
        c = parent_to_sheet(point)
        ring = radius * (parent.scale or s)
        msp.add_circle(c, ring, dxfattribs={"layer": "NOTES"})
        from shapely.geometry import box as rect
        from shapely.ops import unary_union

        # Clear of the part, and of the annotation already on the sheet: its text,
        # its dimensions' lines and its leaders.
        clear_of = unary_union([_drawn_area(next(w for w in work if w[0] is parent), s),
                                *(rect(*taken) for _value, taken in claimed), _annotation_lines(doc)])
        spot = _letter_spot(c, ring, letter, th + 1.5, clear_of)
        text(letter, spot[0], spot[1], th + 1.5, TextEntityAlignment.MIDDLE_CENTER, "NOTES")
    _draw_aux_arrows(msp, sheet, drawn, text, th)
    _merge_centre_lines(msp)
    return doc
