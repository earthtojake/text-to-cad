"""Geometric tolerances on a drawing: feature control frames and datum feature
symbols, in ASME Y14.5 and ISO 1101's shapes.

A frame states how far a feature may stray from its exact form, orientation or
location: its characteristic's symbol, the tolerance (a diameter zone, a
material condition), and the datums it is measured from. Every value comes from
the person; the frame's rules (which characteristics take datums, a diameter
zone, a material condition) are checked when it is made, and a datum it names
must be defined on its sheet when the sheet renders.

Part of :mod:`cadgen.eng_drawing`; nothing here imports the kernel or ezdxf at
module scope.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from cadgen._internal.drawing_base import _SECTION_LETTERS, _exact, _places, _symbol, _text_width

#: Form tolerances relate a feature to itself, so they name no datum.
FORM = ("straightness", "flatness", "circularity", "cylindricity")
#: Orientation tolerances relate a feature to a datum.
ORIENTATION = ("angularity", "perpendicularity", "parallelism")
#: Runout tolerances relate a feature to a datum axis.
RUNOUT = ("circular_runout", "total_runout")
#: The characteristics a frame may state, in Y14.5's order. Concentricity and
#: symmetry are ISO 1101's still; ASME Y14.5-2018 dropped them (``_DROPPED``).
CHARACTERISTICS = (*FORM, "line_profile", "surface_profile", *ORIENTATION, "position", "concentricity",
                   "symmetry", *RUNOUT)
#: Each standard's characteristics it has no symbol for, and what it states in their place.
_DROPPED = {"ASME Y14.5-2018": {"concentricity": "position, or runout", "symmetry": "position, or surface_profile"}}
#: The characteristics whose zone may be a diameter (an axis's).
_DIAMETER_ZONES = ("straightness", *ORIENTATION, "position", "concentricity")
#: The characteristics that apply to a feature of size, and so may take a material
#: condition.
_MATERIAL_CONDITIONS = ("straightness", *ORIENTATION, "position")
MODIFIERS = ("M", "L")
#: A frame's height, in text heights; its symbol and datum cells are square.
_FRAME_HEIGHT = 1.8
#: The air either side of a frame cell's text, in text heights.
_FRAME_PAD = 0.35


@dataclass(frozen=True)
class Frame:
    """A feature control frame: ``Frame("position", 0.1, ("A", "B"), diameter=True,
    modifier="M")`` reads ``⌖ ⌀0.1 Ⓜ A B``. Datums are the letters
    :meth:`~cadgen.eng_drawing.View.datum` defines, primary first."""

    characteristic: str
    tolerance: float
    datums: tuple[str, ...] = ()
    diameter: bool = False
    modifier: str | None = None

    def __post_init__(self) -> None:
        if self.characteristic not in CHARACTERISTICS:
            raise ValueError(f"unknown characteristic {self.characteristic!r}; one of {', '.join(CHARACTERISTICS)}")
        if isinstance(self.tolerance, bool) or not isinstance(self.tolerance, (int, float)) or not self.tolerance > 0:
            raise ValueError(f"a frame's tolerance is a positive number of millimetres, got {self.tolerance!r}")
        _places(self.tolerance)
        if isinstance(self.datums, str):
            raise TypeError(f"datums is a sequence of letters, datums=({self.datums!r},) for one")
        datums = tuple(str(d).upper() for d in self.datums)
        object.__setattr__(self, "datums", datums)
        if len(datums) > 3 or len(set(datums)) != len(datums) or any(d not in _SECTION_LETTERS for d in datums):
            raise ValueError(f"datums are up to three different letters from {_SECTION_LETTERS} (Y14.5 leaves "
                             f"out I, O and Q), got {self.datums!r}")
        if self.characteristic in FORM and datums:
            raise ValueError(f"{self.characteristic} relates a feature to itself and names no datum")
        if self.characteristic in (*ORIENTATION, *RUNOUT) and not datums:
            raise ValueError(f"{self.characteristic} is measured from a datum; give datums=")
        if self.diameter and self.characteristic not in _DIAMETER_ZONES:
            raise ValueError(f"{self.characteristic}'s zone is not a diameter; a diameter zone is for "
                             f"{', '.join(_DIAMETER_ZONES)}")
        if self.modifier is not None:
            if self.modifier not in MODIFIERS:
                raise ValueError(f"modifier is 'M' (maximum material) or 'L' (least), got {self.modifier!r}")
            if self.characteristic not in _MATERIAL_CONDITIONS:
                raise ValueError(f"{self.characteristic} takes no material condition; one applies to "
                                 f"{', '.join(_MATERIAL_CONDITIONS)} of a feature of size")


def _arc(centre, r: float, start: float, end: float, steps: int = 16) -> list[tuple[float, float]]:
    return [(centre[0] + r * math.cos(math.radians(start + (end - start) * i / steps)),
             centre[1] + r * math.sin(math.radians(start + (end - start) * i / steps))) for i in range(steps + 1)]


def _characteristic_symbol(kind: str, x: float, mid: float, h: float) -> list[tuple]:
    """A characteristic's symbol as line work in an ``h`` square starting at ``x``
    and centred on ``mid``: ``("circle", centre, radius)`` and ``("line", points)``
    pieces, as :func:`~cadgen._internal.drawing_base._symbol` draws ⌀."""
    c = (x + h / 2, mid)
    r = 0.36 * h
    if kind == "straightness":
        return [("line", [(x + 0.1 * h, mid), (x + 0.9 * h, mid)])]
    if kind == "flatness":
        return [("line", [(x + 0.1 * h, mid - 0.2 * h), (x + 0.7 * h, mid - 0.2 * h), (x + 0.9 * h, mid + 0.2 * h),
                          (x + 0.3 * h, mid + 0.2 * h), (x + 0.1 * h, mid - 0.2 * h)])]
    if kind == "circularity":
        return [("circle", c, r)]
    if kind == "cylindricity":
        return [("circle", c, 0.28 * h), ("line", [(x + 0.1 * h, mid - 0.4 * h), (x + 0.4 * h, mid + 0.4 * h)]),
                ("line", [(x + 0.6 * h, mid - 0.4 * h), (x + 0.9 * h, mid + 0.4 * h)])]
    if kind == "line_profile":
        return [("line", _arc((c[0], mid - 0.2 * h), r, 0, 180))]
    if kind == "surface_profile":
        arc = _arc((c[0], mid - 0.2 * h), r, 0, 180)
        return [("line", [*arc, arc[0]])]
    if kind == "angularity":
        return [("line", [(x + 0.85 * h, mid - 0.3 * h), (x + 0.15 * h, mid - 0.3 * h),
                          (x + 0.75 * h, mid + 0.35 * h)])]
    if kind == "perpendicularity":
        return [("line", [(x + 0.1 * h, mid - 0.35 * h), (x + 0.9 * h, mid - 0.35 * h)]),
                ("line", [(c[0], mid - 0.35 * h), (c[0], mid + 0.4 * h)])]
    if kind == "parallelism":
        return [("line", [(x + 0.15 * h, mid - 0.35 * h), (x + 0.45 * h, mid + 0.35 * h)]),
                ("line", [(x + 0.55 * h, mid - 0.35 * h), (x + 0.85 * h, mid + 0.35 * h)])]
    if kind == "position":
        return [("circle", c, 0.28 * h), ("line", [(x + 0.08 * h, mid), (x + 0.92 * h, mid)]),
                ("line", [(c[0], mid - 0.42 * h), (c[0], mid + 0.42 * h)])]
    if kind == "concentricity":
        return [("circle", c, 0.38 * h), ("circle", c, 0.2 * h)]
    if kind == "symmetry":
        return [("line", [(x + 0.25 * h, mid + 0.25 * h), (x + 0.75 * h, mid + 0.25 * h)]),
                ("line", [(x + 0.1 * h, mid), (x + 0.9 * h, mid)]),
                ("line", [(x + 0.25 * h, mid - 0.25 * h), (x + 0.75 * h, mid - 0.25 * h)])]
    # Runout: an arrow up and to the right, two for total runout, with a base.
    arrows = [x + 0.3 * h] if kind == "circular_runout" else [x + 0.2 * h, x + 0.55 * h]
    pieces: list[tuple] = []
    for ax in arrows:
        tip = (ax + 0.3 * h, mid + 0.4 * h)
        pieces += [("line", [(ax, mid - 0.4 * h), tip]),
                   ("line", [(tip[0] - 0.2 * h, tip[1] - 0.05 * h), tip, (tip[0] - 0.05 * h, tip[1] - 0.2 * h)])]
    if kind == "total_runout":
        pieces.append(("line", [(x + 0.1 * h, mid - 0.4 * h), (x + 0.75 * h, mid - 0.4 * h)]))
    return pieces


def _draw_pieces(layout, pieces: list[tuple], h: float, layer: str) -> None:
    attribs = {"layer": layer, "lineweight": max(13, min(50, int(round(h * 10))))}
    for piece in pieces:
        if piece[0] == "circle":
            layout.add_circle(piece[1], piece[2], dxfattribs=attribs)
        else:
            layout.add_lwpolyline(piece[1], dxfattribs=attribs)


def _tolerance_text(frame: Frame) -> str:
    return _exact(frame.tolerance)


def _tolerance_width(frame: Frame, th: float) -> float:
    """The tolerance cell's width: its ⌀, the value and its material condition."""
    width = _text_width(_tolerance_text(frame), th) + 2 * _FRAME_PAD * th
    if frame.diameter:
        width += th
    if frame.modifier:
        width += 1.1 * th
    return width


def frame_size(frame: Frame, th: float) -> tuple[float, float]:
    """A frame's (width, height) at text height ``th``."""
    cell = _FRAME_HEIGHT * th
    return cell + _tolerance_width(frame, th) + cell * len(frame.datums), cell


def _put(layout, value: str, x: float, y: float, h: float, align, layer: str) -> None:
    entity = layout.add_text(value, dxfattribs={"height": h, "layer": layer})
    entity.set_placement((x, y), align=align)


def _draw_frame(layout, frame: Frame, x: float, mid: float, th: float,
                layer: str = "DIM") -> tuple[float, float, float, float]:
    """Draw ``frame`` with its left edge at ``x``, centred on ``mid``. Returns its
    box as (x0, y0, x1, y1), for the caller to keep other annotation off."""
    from ezdxf.enums import TextEntityAlignment as A

    width, cell = frame_size(frame, th)
    y0, y1 = mid - cell / 2, mid + cell / 2
    layout.add_lwpolyline([(x, y0), (x + width, y0), (x + width, y1), (x, y1)], close=True,
                          dxfattribs={"layer": layer})
    _draw_pieces(layout, _characteristic_symbol(frame.characteristic, x + 0.15 * cell, mid, 0.7 * cell), th, layer)
    edge = x + cell
    layout.add_line((edge, y0), (edge, y1), dxfattribs={"layer": layer})
    cursor = edge + _FRAME_PAD * th
    if frame.diameter:
        _draw_pieces(layout, _symbol("diameter", cursor, mid, th), th, layer)
        cursor += th
    _put(layout, _tolerance_text(frame), cursor, mid, th, A.MIDDLE_LEFT, layer)
    cursor += _text_width(_tolerance_text(frame), th)
    if frame.modifier:
        r = 0.45 * th
        centre = (cursor + 0.15 * th + r, mid)
        layout.add_circle(centre, r, dxfattribs={"layer": layer})
        _put(layout, frame.modifier, centre[0], mid, 0.6 * th, A.MIDDLE_CENTER, layer)
    edge += _tolerance_width(frame, th)
    for letter in frame.datums:
        layout.add_line((edge, y0), (edge, y1), dxfattribs={"layer": layer})
        _put(layout, letter, edge + cell / 2, mid, th, A.MIDDLE_CENTER, layer)
        edge += cell
    return x, y0, x + width, y1


#: A datum feature symbol: its stem's length and its triangle's side, in text heights.
_DATUM_STEM = 2.2
_DATUM_TRIANGLE = 1.0


def _draw_datum(layout, letter: str, tip: tuple[float, float], toward: tuple[float, float], th: float,
                layer: str = "DIM", extra: float = 0.0) -> tuple[float, float, float, float]:
    """Draw datum feature symbol ``letter``: a filled triangle standing on the
    feature at ``tip``, a stem leading ``toward`` (a unit direction away from the
    part), ``extra`` mm longer than its own length, and the letter in a square.
    Returns the square's box (x0, y0, x1, y1)."""
    from ezdxf import const
    from ezdxf.enums import TextEntityAlignment as A

    ux, uy = toward
    side = _DATUM_TRIANGLE * th
    across = (-uy * side / 2, ux * side / 2)
    apex = (tip[0] + ux * side * 0.87, tip[1] + uy * side * 0.87)
    triangle = [(tip[0] + across[0], tip[1] + across[1]), (tip[0] - across[0], tip[1] - across[1]), apex]
    hatch = layout.add_hatch(dxfattribs={"layer": layer})
    hatch.set_solid_fill()
    hatch.paths.add_polyline_path(triangle, is_closed=True, flags=const.BOUNDARY_PATH_EXTERNAL)
    layout.add_lwpolyline(triangle, close=True, dxfattribs={"layer": layer})
    cell = _FRAME_HEIGHT * th
    end = (apex[0] + ux * (_DATUM_STEM * th + extra), apex[1] + uy * (_DATUM_STEM * th + extra))
    layout.add_line(apex, end, dxfattribs={"layer": layer})
    centre = (end[0] + ux * cell / 2, end[1] + uy * cell / 2)
    box = (centre[0] - cell / 2, centre[1] - cell / 2, centre[0] + cell / 2, centre[1] + cell / 2)
    layout.add_lwpolyline([(box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3])], close=True,
                          dxfattribs={"layer": layer})
    _put(layout, letter, centre[0], centre[1], th, A.MIDDLE_CENTER, layer)
    return box


#: How far a datum feature symbol reaches from its feature, in text heights.
_DATUM_REACH = _DATUM_TRIANGLE * 0.87 + _DATUM_STEM + _FRAME_HEIGHT


def _datum_toward(p: tuple[float, float], bounds, stem) -> tuple[float, float]:
    """The way a datum feature symbol's stem leads out of a view whose extent is
    ``bounds`` (x0, x1, y0, y1): the author's offset, else out by the nearest side."""
    if stem is not None:
        length = math.hypot(*stem)
        return stem[0] / length, stem[1] / length
    x0, x1, y0, y1 = bounds
    gaps = {(-1.0, 0.0): p[0] - x0, (1.0, 0.0): x1 - p[0], (0.0, -1.0): p[1] - y0, (0.0, 1.0): y1 - p[1]}
    return min(gaps, key=lambda k: gaps[k])


def _side_of(toward: tuple[float, float]) -> str:
    ux, uy = toward
    return ("right" if ux > 0 else "left") if abs(ux) >= abs(uy) else ("top" if uy > 0 else "bottom")


def mark_width(mark: str, th: float) -> float:
    """A key characteristic mark's width at text height ``th``."""
    return _text_width(mark, th) + 2 * _FRAME_PAD * th


def _draw_mark(layout, mark: str, x: float, mid: float, th: float,
               layer: str = "DIM") -> tuple[float, float, float, float]:
    """Draw a key characteristic's letters in a box a frame cell high, its left
    edge at ``x`` and centred on ``mid``. Returns its box (x0, y0, x1, y1)."""
    from ezdxf.enums import TextEntityAlignment as A

    width, cell = mark_width(mark, th), _FRAME_HEIGHT * th
    box = (x, mid - cell / 2, x + width, mid + cell / 2)
    layout.add_lwpolyline([(box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3])], close=True,
                          dxfattribs={"layer": layer})
    _put(layout, mark, x + width / 2, mid, th, A.MIDDLE_CENTER, layer)
    return box


def _frames(sheet) -> list[tuple[str, "Frame"]]:
    """Every frame on a sheet, each with where it is: a view's, by its kind and
    number, and the general profile's."""
    frames = [(f"{view.name} {dim.kind} {index}", dim.frame) for view in sheet.views
              for index, dim in enumerate(view._dims) if dim.frame is not None]
    if sheet.general_profile is not None:
        frames.append(("the general profile", sheet.general_profile))
    return frames


def _check_standard(sheet, which: str) -> None:
    """Refuse a frame on a sheet that names no standard to read it by, and one
    whose characteristic the standard the sheet's profile reads it by has no
    symbol for: a Y14.5-2018 drawing with a concentricity frame states a
    requirement its own standard cannot read. ISO GPS and Y14.5 read one frame
    differently (Rule #1), so which one is the person's to state, and the
    profile's note prints it on the sheet."""
    if sheet.profile is None:
        framed = _frames(sheet)
        if framed:
            raise ValueError(f"{which}, {framed[0][0]}: a GD&T frame is read by ISO GPS or ASME Y14.5-2018, "
                             "which read it differently, and the sheet names neither; give it profile=GENERIC "
                             "(ISO GPS) or your own Profile(name, \"ASME Y14.5-2018\")")
        return
    dropped = _DROPPED.get(sheet.profile.standard, {})
    for where, frame in _frames(sheet):
        if frame.characteristic in dropped:
            raise ValueError(f"{which}, {where}: {sheet.profile.standard}, the standard its profile "
                             f"{sheet.profile.name} reads the drawing by, has no {frame.characteristic}; state "
                             f"{dropped[frame.characteristic]} instead")


def _check_datums(sheet, which: str) -> None:
    """Refuse a frame that names a datum no view of its sheet (``which``, as the
    refusal names it) defines: a frame read against a datum nobody marked
    measures from nowhere."""
    defined = {d[0] for view in sheet.views for d in view._datums} | {
        dim.datum for view in sheet.views for dim in view._dims if dim.datum}
    for where, frame in _frames(sheet):
        missing = [d for d in frame.datums if d not in defined]
        if missing:
            raise ValueError(f"{which}, {where}: its frame names datum {missing[0]}, which no view of this sheet "
                             f"defines; view.datum({missing[0]!r}, point) on the feature it means defines it")
