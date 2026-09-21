"""Engineering drawings: ``@eng_drawing``, :class:`Sheet` and :class:`View`.

An engineering drawing is a DOCUMENT derived from a part: orthographic views
projected from the part's geometry, dimensions that reference points ON that
geometry, centre marks found on it, a sheet frame and a title block. Because
every view and every dimension is computed from the shape at run time, the
drawing follows the part: change the model, rerun the drawing script, and the
views, hidden lines and measured values move with it. Nothing on the sheet is
drawn by hand.

The output is one PDF. A shop receives a PDF, every operating system opens and
marks one up, and nothing here pairs the document with a second file. ezdxf is
the in-memory drawing engine -- real ``DIMENSION`` entities so the value is
measured and the arrowheads and witness lines are the dimension style's, ``TEXT``
for notes and the title block, a LAYER table whose linetypes say which lines are
hidden or centre lines -- and no ``.dxf`` reaches disk. ``@dxf`` remains the
decorator for a DXF: a cut layout is a toolpath, and a drawing is not.

Usage::

    import cadgen
    from cadgen.eng_drawing import eng_drawing, Sheet
    from pathlib import Path

    @eng_drawing(out="../PDF/bracket_drawing.pdf")
    def bracket_drawing():
        part = cadgen.read_step(Path(__file__).parent / "../STEP/bracket.step")
        sheet = Sheet("A3", title="BRACKET", part_number="BRK-001", revision="A")
        top = sheet.view(part, "top", at=(110, 190))
        front = sheet.view(part, "front", at=(110, 90))
        top.overall()                                    # width and height
        top.dim((-35, 25, 0), (35, 25, 0))               # model coordinates
        top.hole((35, 25, 15), 3, depth=8, count=4)
        return sheet                                     # or [sheet1, sheet2]

    if __name__ == "__main__":
        bracket_drawing()

Running the script writes one PDF at ``out`` with a page per sheet. There is no
default location: ``out`` is the path the caller passes. A live build123d shape
works in place of ``read_step``; the part is whatever geometry the function has.

Bytes are a function of the content: the PDF carries no creation date, so an
unchanged drawing rebuilds to an identical file.

This module keeps ``@eng_drawing`` outside the build store on purpose: a drawing
is a document over a part, not a model with a closure to hash. Import
discipline: nothing here pulls in ezdxf or the CAD kernel at module scope.
"""

from __future__ import annotations

import functools
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

__all__ = ["eng_drawing", "Sheet", "View", "SHEET_SIZES"]

#: ISO 216 sheet sizes, landscape, in millimetres.
SHEET_SIZES = {
    "A4": (297.0, 210.0),
    "A3": (420.0, 297.0),
    "A2": (594.0, 420.0),
    "A1": (841.0, 594.0),
    "A0": (1189.0, 841.0),
}

#: Standard view names -> (view direction: where the viewer STANDS relative to the
#: part, up vector). Third-angle projection places each view on the side it looks
#: from; the sheet does not enforce placement, the author picks ``at=``.
VIEW_DIRECTIONS = {
    "top": ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
    # Looking up from below, the sheet's up is the model's -Y: the bottom view is the
    # top view mirrored about the horizontal, which is what third angle draws. With
    # up=+Y it comes out rotated 180 degrees (+X to the left), so it would not line up
    # with the front view above it.
    "bottom": ((0.0, 0.0, -1.0), (0.0, -1.0, 0.0)),
    "front": ((0.0, -1.0, 0.0), (0.0, 0.0, 1.0)),
    "back": ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    "right": ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    "left": ((-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    "iso": ((1.0, -1.0, 1.0), (0.0, 0.0, 1.0)),
}

#: Layers a sheet writes, with ACI colour and linetype. ``ink="mono"`` collapses
#: the colours to the default ink; the linetypes are the drawing's meaning and stay.
#: Every linetype here must be one ``ezdxf.new(setup=True)` defines, or ezdxf draws
#: the layer continuous and its audit reports the substitution: there is no HIDDEN
#: in that table, DASHED is the ISO 128 dashed line it does define.
_LAYERS = {
    "SHEET": (7, "CONTINUOUS", 0.35),
    "TITLE": (7, "CONTINUOUS", 0.25),
    "VISIBLE": (7, "CONTINUOUS", 0.5),
    "HIDDEN": (8, "DASHED", 0.25),
    "CENTER": (4, "CENTER", 0.18),
    "DIM": (1, "CONTINUOUS", 0.18),
    "NOTES": (3, "CONTINUOUS", 0.25),
}

#: Projection conventions the title block may name. The two differ only in WHERE a
#: view is placed: third angle puts the view from above above the front view and the
#: view from the right to its right; first angle puts each on the opposite side. The
#: pictures are the same, so only :meth:`Sheet.three_views` reads this.
PROJECTIONS = ("THIRD ANGLE", "FIRST ANGLE")

_MARGIN = 10.0
_TITLE_W, _TITLE_H = 180.0, 40.0
#: One row of dimensions: the line's distance from the last, with room for its text.
_DIM_ROW = 12.0
#: The smallest text a print stays legible at. Below it, text is cut, not shrunk.
_MIN_TEXT_MM = 1.6
#: Drawing scales a shop expects to read, largest first. An over-size part is
#: refused with the first of these that fits rather than an arbitrary ratio.
_STANDARD_SCALES = (1.0, 1 / 2, 1 / 2.5, 1 / 5, 1 / 10, 1 / 20, 1 / 50, 1 / 100, 1 / 200, 1 / 500, 1 / 1000)


@dataclass
class _Dim:
    kind: str
    p1: tuple[float, float, float]
    p2: tuple[float, float, float] | None
    #: Sheet millimetres from the dimensioned points, or None for the next free row.
    offset: float | None
    text: str | None
    orientation: str | None
    radius: float = 0.0
    angle: float = 45.0
    tol: Any = None
    fit: str | None = None
    hole: dict | None = None


@dataclass
class View:
    """One orthographic view of a shape on a sheet.

    Points handed to :meth:`dim`, :meth:`diameter` and :meth:`note` are MODEL
    coordinates; the view projects them exactly as it projected the geometry, so
    a dimension between two model points measures what the sheet shows.
    """

    sheet: "Sheet"
    shape: Any
    name: str
    at: tuple[float, float]
    label: str | None = None
    hidden: bool = True
    centre_marks: bool = True
    #: This view's own drawing scale; None means the sheet's. A pictorial view is
    #: often drawn smaller so it fits the free corner.
    scale: float | None = None
    _dims: list[_Dim] = field(default_factory=list)
    _overall: bool = False

    def dim(self, p1, p2, *, offset: float | None = None, text: str | None = None, orientation: str | None = None,
            tol: float | tuple[float, float] | None = None, fit: str | None = None) -> "View":
        """A linear dimension between two model points. ``orientation`` is ``"h"``,
        ``"v"`` or None (whichever the projected pair spans more); ``offset`` is
        the dimension line's distance from the farther point, in sheet mm, and its
        sign picks the side. Left unset, the dimension takes the next free row on
        its side, so defaults never stack on each other or on :meth:`overall`.
        ``tol=0.1`` states ±0.1; ``tol=(0.05, 0.02)`` states +0.05/-0.02
        deviations; ``fit="H7"`` appends an ISO fit class."""
        if orientation not in (None, "h", "v"):
            raise ValueError(f"orientation must be 'h', 'v' or None, got {orientation!r}")
        self._dims.append(_Dim("linear", _p3(p1), _p3(p2), _offset(offset), text, orientation,
                               tol=_tol(tol), fit=fit))
        return self

    def hole(self, center, diameter: float, *, depth: float | None = None, thru: bool = False,
             cbore: tuple[float, float] | None = None, csk: tuple[float, float] | None = None,
             thread: str | None = None, count: int | None = None, angle: float = 45.0,
             tol: float | tuple[float, float] | None = None, fit: str | None = None,
             label: str | None = None) -> "View":
        """A hole callout in the standard symbols: ``4× ⌀6.6 ↧12``, ``THRU``, a
        counterbore ``⌴ ⌀11 ↧6.5``, a countersink ``⌵ ⌀12 × 90°``, or a thread
        such as ``M6x1 - 6H`` in place of the diameter. ``tol``/``fit`` qualify the
        diameter the way :meth:`dim` does; ``label`` is appended (``"WHEEL"``).
        ``angle`` is where the leader leaves the circle, degrees from horizontal."""
        spec = {"diameter": _positive("diameter", diameter), "depth": _positive("depth", depth, allow_none=True),
                "thru": bool(thru), "cbore": _pair("cbore", cbore), "csk": _pair("csk", csk),
                "thread": None if thread is None else str(thread),
                "count": None if count is None else _positive("count", count, integer=True),
                "label": None if label is None else str(label)}
        if thru and depth is not None:
            raise ValueError("a hole is either THRU or has a depth, not both")
        self._dims.append(_Dim("hole", _p3(center), None, 0.0, None, None, radius=spec["diameter"] / 2,
                               angle=float(angle), tol=_tol(tol), fit=fit, hole=spec))
        return self

    def diameter(self, center, radius: float, *, angle: float = 45.0, text: str | None = None) -> "View":
        """A diameter dimension on a circular feature at a model centre point."""
        self._dims.append(_Dim("diameter", _p3(center), None, 0.0, text, None,
                               radius=_positive("radius", radius), angle=float(angle)))
        return self

    def radius(self, center, radius: float, *, angle: float = 45.0, text: str | None = None) -> "View":
        self._dims.append(_Dim("radius", _p3(center), None, 0.0, text, None,
                               radius=_positive("radius", radius), angle=float(angle)))
        return self

    def angle(self, vertex, p1, p2, *, offset: float = 14.0) -> "View":
        """The angle at ``vertex`` between the legs toward ``p1`` and ``p2`` (model
        points); ``offset`` is the arc's distance from the vertex, in sheet mm."""
        self._dims.append(_Dim("angle", _p3(vertex), _p3(p1), offset, None, None, radius=0.0, angle=0.0, hole={"p2": _p3(p2)}))
        return self

    def note(self, text: str, at, *, offset: tuple[float, float] = (10.0, 10.0)) -> "View":
        """A note with a leader from a model point; ``offset`` places the text, in
        sheet mm, relative to the projected point."""
        self._dims.append(_Dim("note", _p3(at), None, 0.0, text, None, radius=offset[0], angle=offset[1]))
        return self

    def overall(self) -> "View":
        """Overall width (above) and height (left) of the view's projected extent."""
        self._overall = True
        return self


def _fmt(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text or "0"


def _tol(value):
    """Normalise a tolerance argument to (plus, minus) or None."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise TypeError(f"tol must be a number or a (plus, minus) pair, got {value!r}")
    if isinstance(value, (int, float)):
        return (abs(float(value)), abs(float(value)))
    try:
        plus, minus = value
        return (abs(float(plus)), abs(float(minus)))
    except (TypeError, ValueError) as exc:
        raise TypeError(f"tol must be a number or a (plus, minus) pair, got {value!r}") from exc


def _offset(value) -> float | None:
    """A dimension offset in sheet millimetres, or None for the next free row."""
    if value is None:
        return None
    try:
        offset = float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"offset must be a number of sheet millimetres, got {value!r}") from exc
    if not math.isfinite(offset):
        raise ValueError(f"offset must be finite, got {value!r}")
    return offset


def _positive(name: str, value, *, allow_none: bool = False, integer: bool = False):
    """A dimension the shop can make: a real, finite, positive number."""
    if value is None:
        if allow_none:
            return None
        raise ValueError(f"{name} is required")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{name} must be a number, got {value!r}") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be a positive number, got {value!r}")
    return int(round(number)) if integer else number


def _pair(name: str, value) -> tuple[float, float] | None:
    """A (diameter, depth) or (diameter, angle) pair, both positive."""
    if value is None:
        return None
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise TypeError(f"{name} must be a pair of numbers, got {value!r}")
    values = tuple(value)
    if len(values) != 2:
        raise ValueError(f"{name} must be a pair of numbers, got {value!r}")
    return (_positive(f"{name}[0]", values[0]), _positive(f"{name}[1]", values[1]))


def _tol_suffix(tol) -> str:
    if not tol:
        return ""
    plus, minus = tol
    if abs(plus - minus) < 1e-9:
        return f" ±{_fmt(plus)}"
    return f" +{_fmt(plus)}/-{_fmt(minus)}"


def hole_callout_text(spec: dict, *, tol=None, fit: str | None = None) -> str:
    """The text of a hole callout, in the ISO/ASME symbols a shop reads."""
    parts = []
    lead = f"{spec['count']}× " if spec.get("count") else ""
    size = spec["thread"] if spec.get("thread") else f"%%c{_fmt(spec['diameter'])}"
    size += _tol_suffix(tol) + (f" {fit}" if fit else "")
    if spec.get("thru"):
        size += " THRU"
    elif spec.get("depth") is not None:
        size += f" \u21a7{_fmt(spec['depth'])}"
    parts.append(lead + size)
    if spec.get("cbore"):
        d, depth = spec["cbore"]
        parts.append(f"\u2334 %%c{_fmt(d)} \u21a7{_fmt(depth)}")
    if spec.get("csk"):
        d, ang = spec["csk"]
        parts.append(f"\u2335 %%c{_fmt(d)} × {_fmt(ang)}°")
    if spec.get("label"):
        parts.append(str(spec["label"]))
    return "   ".join(parts)


def _p3(p) -> tuple[float, float, float]:
    values = tuple(float(v) for v in p)
    if len(values) == 2:
        values = (values[0], values[1], 0.0)
    if len(values) != 3:
        raise ValueError(f"expected a 2D or 3D point, got {p!r}")
    return values  # type: ignore[return-value]


@dataclass
class Sheet:
    """One sheet of a drawing: a frame, a title block and the views placed on it.

    ``at`` positions on views are the sheet's own millimetres with the origin at
    the sheet's bottom-left corner; ``scale`` is drawing scale (1 = 1:1, 0.5 = 1:2).
    """

    size: str = "A3"
    scale: float = 1.0
    title: str = "UNTITLED"
    part_number: str = ""
    material: str = ""
    revision: str = "A"
    author: str = ""
    units: str = "mm"
    projection: str = "THIRD ANGLE"
    notes: Sequence[str] = ()
    ink: str = "mono"
    text_height: float = 3.5
    #: A general tolerance standard, e.g. "ISO 2768-m": written as the first note.
    general_tolerance: str = ""
    #: Revision history rows (rev, date, description), drawn as a table top-right.
    revisions: Sequence[tuple[str, str, str]] = ()
    views: list[View] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.size not in SHEET_SIZES:
            raise ValueError(f"unknown sheet size {self.size!r}; one of {sorted(SHEET_SIZES)}")
        if not (self.scale > 0):
            raise ValueError("scale must be positive")
        # The title block prints this label and `three_views` lays the views out to
        # match it. Accepting any string would print "FIRST ANGLE" over a third-angle
        # arrangement, which is the one mislabel a shop cannot recover from.
        if self.projection not in PROJECTIONS:
            raise ValueError(
                f"unknown projection {self.projection!r}; one of {sorted(PROJECTIONS)}. "
                "The label and the view arrangement are the same decision."
            )

    @property
    def width(self) -> float:
        return SHEET_SIZES[self.size][0]

    @property
    def height(self) -> float:
        return SHEET_SIZES[self.size][1]

    def three_views(self, shape, *, gap: float | None = None, hidden: bool = True, centre_marks: bool = True,
                    iso: bool = False) -> tuple[View, View, View] | tuple[View, View, View, View]:
        """Top, front and right views in third-angle arrangement, placed from the
        part's own extents: front centred low on the sheet, top above it, right
        beside it. ``gap`` is the clear space between views; by default it is
        sized for two rows of dimensions (offsets 12 and 24 plus their text) so
        annotation never runs into the neighbouring view. ``iso=True`` adds an
        isometric view in the free top-right slot and returns it fourth."""
        size = shape.bounding_box().size
        s = self.scale
        L, W, H = size.X * s, size.Y * s, size.Z * s
        m = _MARGIN
        if gap is None:
            gap = 24.0 + 2 * self.text_height + 16.0  # second dimension row + its text + air
        # Annotation also reaches outside the block: left of the front view (heights),
        # below it (the label), above the top view (widths); keep that clear too.
        reach = 12.0 + 2 * self.text_height + 8.0
        usable_w = self.width - 2 * m - 2 * reach
        # Notes stack upward from the title block; the block starts above them and
        # above the label that hangs under the front view.
        note_rows = len(self.notes) + (1 if self.general_tolerance else 0)
        notes_h = (note_rows * 5.0 + 8.0) if note_rows else 0.0
        usable_h = self.height - 2 * m - _TITLE_H - notes_h - reach - 12.0
        block_w = L + gap + W
        block_h = H + gap + W
        left = m + reach + max(0.0, (usable_w - block_w) / 2)
        bottom = m + _TITLE_H + notes_h + 12.0 + max(0.0, (usable_h - block_h) / 2)
        if self.projection == "FIRST ANGLE":
            # First angle places each view on the side opposite the one it looks from:
            # the plan below the front, the view from the right to its left. The
            # pictures are the third-angle pictures; only the slots swap.
            front_at = (left + W + gap + L / 2, bottom + W + gap + H / 2)
            top_at = (front_at[0], bottom + W / 2)
            right_at = (left + W / 2, front_at[1])
        else:
            front_at = (left + L / 2, bottom + H / 2)
            top_at = (front_at[0], bottom + H + gap + W / 2)
            right_at = (left + L + gap + W / 2, front_at[1])
        views = (
            self.view(shape, "top", at=top_at, hidden=hidden, centre_marks=centre_marks),
            self.view(shape, "front", at=front_at, hidden=hidden, centre_marks=centre_marks),
            self.view(shape, "right", at=right_at, hidden=hidden, centre_marks=centre_marks),
        )
        if iso:
            # The free slot is above the right view. The isometric is taller and wider
            # than that view, so it is placed from its own projected extent: bottom edge
            # level with the top view's, centred over the right view, kept inside the frame.
            # The free corner is right of the top view and above the right view, less the
            # room the top view's own callouts need. A pictorial that does not fit is drawn
            # at a smaller scale and says so in its label.
            iso_w, iso_h = _view_extent(shape, "iso", 1.0)
            # The upper row is the top view in third angle and the front view in first;
            # either way the free corner starts at that row's bottom edge and right of
            # the widest view in it.
            upper = views[0] if self.projection == "THIRD ANGLE" else views[1]
            upper_h = W if self.projection == "THIRD ANGLE" else H
            upper_bottom = upper.at[1] - upper_h / 2
            # A hole callout beside that view needs its knee (a dimension row plus 10)
            # and its text (about 13 characters); keep that much clear of the iso.
            avail_w = self.width - m - 6 - (upper.at[0] + L / 2 + 30.0 + 8.0 + 13 * self.text_height * 0.7 + 8.0)
            # The revision table, when there is one, owns the top-right corner.
            table_h = (len(self.revisions) + 1) * 6.0 + 6.0 if self.revisions else 0.0
            avail_h = self.height - m - 6 - table_h - upper_bottom
            iso_scale = s * min(1.0, max(0.2, avail_w / iso_w if iso_w else 1.0), max(0.2, avail_h / iso_h if iso_h else 1.0))
            iso_w, iso_h = iso_w * iso_scale, iso_h * iso_scale
            iso_x = self.width - m - 6 - iso_w / 2
            iso_y = min(upper_bottom + iso_h / 2, self.height - m - 6 - table_h - iso_h / 2)
            ratio = iso_scale / s
            label = "ISOMETRIC" if abs(ratio - 1) < 1e-6 else f"ISOMETRIC (1:{1 / ratio:.3g})"
            return views + (self.view(shape, "iso", at=(iso_x, iso_y), hidden=False, centre_marks=False, label=label,
                                      scale=None if abs(ratio - 1) < 1e-6 else iso_scale),)
        return views

    def view(self, shape, name: str, *, at, label: str | None = None, hidden: bool = True, centre_marks: bool = True,
             scale: float | None = None) -> View:
        if name not in VIEW_DIRECTIONS:
            raise ValueError(f"unknown view {name!r}; one of {sorted(VIEW_DIRECTIONS)}")
        if scale is not None and not (scale > 0):
            raise ValueError("a view's scale must be positive")
        view = View(self, shape, name, (float(at[0]), float(at[1])), label, hidden, centre_marks, scale)
        self.views.append(view)
        return view


# --- projection ---------------------------------------------------------------------

class _Projection:
    """The affine map a build123d viewport applies, recovered from the viewport
    itself, so dimension points land exactly where the geometry did."""

    def __init__(self, shape, name: str) -> None:
        from build123d import Axis, Edge, Vector

        direction, up = VIEW_DIRECTIONS[name]
        bbox = shape.bounding_box()
        centre = bbox.center()
        radius = max(bbox.size.length, 1.0)
        d = Vector(*direction).normalized()
        origin = centre + d * (radius * 10.0)
        self.origin, self.up, self.look_at = origin, up, centre
        self.visible, self.hidden = shape.project_to_viewport(
            viewport_origin=origin, viewport_up=up, look_at=centre
        )
        # Recover the map from three unit lines along the model axes.
        probes = []
        for axis in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
            line = Edge.make_line(Vector(0, 0, 0), Vector(*axis))
            vis, hid = line.project_to_viewport(viewport_origin=origin, viewport_up=up, look_at=centre)
            edges = list(vis) + list(hid)
            if not edges:
                probes.append(((0.0, 0.0), (0.0, 0.0)))
                continue
            e = edges[0]
            a, b = e.position_at(0), e.position_at(1)
            probes.append(((a.X, a.Y), (b.X, b.Y)))
        # Each probe's start is the projected origin; its end minus start is the axis image.
        # Anchor on the first probe that projected to a line: the X probe is parallel
        # to the right and left views and comes back empty, and anchoring on its
        # zero placeholder put the projected centre in the wrong place, so the
        # fix-up below chose the wrong end of the Z probe and mirrored those views'
        # annotations vertically.
        o = next((p[0] for p in probes if p[0] != p[1]), (0.0, 0.0))
        self.c = o
        self.m = [(p[1][0] - p[0][0], p[1][1] - p[0][1]) for p in probes]
        # A probe whose line is parallel to the view direction projects to a point;
        # its axis image is zero, which is correct. A projected edge can come back
        # with its ends swapped, so the map is settled by probes anchored at the
        # model centre, whose projected start is unambiguous.
        self._m_fixup(shape, centre)

    def _m_fixup(self, shape, centre) -> None:
        from build123d import Edge, Vector

        # Probe with a line from the centre to the centre + axis, whose START is
        # unambiguous: its projected start must equal the projected centre.
        for index, axis in enumerate(((1, 0, 0), (0, 1, 0), (0, 0, 1))):
            line = Edge.make_line(centre, centre + Vector(*axis) * 7.0)
            vis, hid = line.project_to_viewport(viewport_origin=self.origin, viewport_up=self.up, look_at=self.look_at)
            edges = list(vis) + list(hid)
            if not edges:
                continue
            e = edges[0]
            a, b = e.position_at(0), e.position_at(1)
            # Whichever end is closer to the projected centre is the start.
            pc = self._raw_point(tuple(centre))
            da = math.hypot(a.X - pc[0], a.Y - pc[1])
            db = math.hypot(b.X - pc[0], b.Y - pc[1])
            start, end = (a, b) if da <= db else (b, a)
            self.m[index] = ((end.X - start.X) / 7.0, (end.Y - start.Y) / 7.0)
            self.c = (pc[0] - (self.m[0][0] * centre.X + self.m[1][0] * centre.Y + self.m[2][0] * centre.Z),
                      pc[1] - (self.m[0][1] * centre.X + self.m[1][1] * centre.Y + self.m[2][1] * centre.Z))

    def _raw_point(self, p) -> tuple[float, float]:
        x = self.c[0] + self.m[0][0] * p[0] + self.m[1][0] * p[1] + self.m[2][0] * p[2]
        y = self.c[1] + self.m[0][1] * p[0] + self.m[1][1] * p[1] + self.m[2][1] * p[2]
        return (x, y)

    def point(self, p) -> tuple[float, float]:
        return self._raw_point(p)


def _edges_bounds(edges) -> tuple[float, float, float, float] | None:
    """Exact (x0, x1, y0, y1) of projected edges, from the kernel's own bounding boxes,
    so a circle's extent is its diameter and not the chord of a few samples."""
    x0 = y0 = math.inf
    x1 = y1 = -math.inf
    for edge in edges:
        bb = edge.bounding_box()
        x0, x1 = min(x0, bb.min.X), max(x1, bb.max.X)
        y0, y1 = min(y0, bb.min.Y), max(y1, bb.max.Y)
    if not math.isfinite(x0):
        return None
    return (x0, x1, y0, y1)


def _view_extent(shape, name: str, scale: float) -> tuple[float, float]:
    """The projected (width, height) of a view in sheet millimetres, for placement."""
    proj = _Projection(shape, name)
    bounds = _edges_bounds(list(proj.visible) + list(proj.hidden))
    if not bounds:
        return (0.0, 0.0)
    return ((bounds[1] - bounds[0]) * scale, (bounds[3] - bounds[2]) * scale)


def _edge_polyline(edge, samples: int = 24) -> list[tuple[float, float]]:
    from build123d import GeomType

    n = 2 if edge.geom_type == GeomType.LINE else samples
    return [(float(v.X), float(v.Y)) for v in (edge.position_at(i / (n - 1)) for i in range(n))]


def _circles(edges) -> list[tuple[tuple[float, float], float]]:
    """Full circles among projected edges: (centre, radius) in viewport coordinates."""
    from build123d import GeomType

    found: list[tuple[tuple[float, float], float]] = []
    for edge in edges:
        if edge.geom_type != GeomType.CIRCLE or not edge.is_closed:
            continue
        c = edge.arc_center
        key = ((round(c.X, 3), round(c.Y, 3)), round(edge.radius, 3))
        if key not in found:
            found.append(key)
    return found


# --- writing ------------------------------------------------------------------------

def _dimstyle(doc, text_height: float):
    style = doc.dimstyles.get("Standard")
    style.dxf.dimtxt = text_height
    style.dxf.dimasz = text_height * 0.85
    style.dxf.dimexo = 1.5
    style.dxf.dimexe = 2.0
    style.dxf.dimgap = 1.0
    style.dxf.dimtad = 1
    style.dxf.dimdec = 2
    style.dxf.dimzin = 8
    style.dxf.dimdsep = ord(".")
    style.dxf.dimtdec = 2
    style.dxf.dimblk = "_CLOSEDFILLED"
    return "Standard"


def _assert_views_fit(sheet: Sheet, placed: Sequence[tuple], *, index: int) -> None:
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
    # Measure the whole arrangement, not each view: the views have to fit the frame
    # together. Shrinking the scale shrinks the geometry but not the gaps between
    # views, so the ratio below understates what is achievable -- deliberately, since
    # a suggestion that still does not fit is worse than a conservative one.
    usable_w, usable_h = frame[1] - frame[0], frame[3] - frame[2]
    union = (min(b[0] for *_, b in placed), max(b[1] for *_, b in placed),
             min(b[2] for *_, b in placed), max(b[3] for *_, b in placed))
    need = min(usable_w / max(union[1] - union[0], 1e-9), usable_h / max(union[3] - union[2], 1e-9))
    ceiling = min(sheet.scale * need, sheet.scale * 0.999)
    fits = next((candidate for candidate in _STANDARD_SCALES if candidate <= ceiling), _STANDARD_SCALES[-1])
    names = ", ".join(sorted({view.name for view, _ in over}))
    raise ValueError(
        f"sheet {index} ({sheet.size}, scale {_scale_label(sheet.scale)}): the {names} view"
        f"{'s run' if len(over) > 1 else ' runs'} off the frame. "
        f"Use Sheet(scale={fits:g}) ({_scale_label(fits)}), a larger sheet size, or place the views closer."
    )


def _spans(a, b) -> str:
    """Whether a projected point pair reads as a horizontal or a vertical dimension."""
    return "h" if abs(b[0] - a[0]) >= abs(b[1] - a[1]) else "v"


def _scale_label(scale: float) -> str:
    if abs(scale - 1) < 1e-9:
        return "1:1"
    return f"1:{1 / scale:g}" if scale < 1 else f"{scale:g}:1"


def _text_box(value: str, x: float, y: float, height: float, align) -> tuple[float, float, float, float]:
    """The rectangle a TEXT entity occupies, from its anchor and alignment.

    Character width is taken at 0.72 of the cap height, the same ratio the title
    block fits text with, so one number governs both.
    """
    width = len(value) * height * 0.72
    name = getattr(align, "name", str(align)).upper()
    if "CENTER" in name and "LEFT" not in name and "RIGHT" not in name:
        x0 = x - width / 2
    elif "RIGHT" in name:
        x0 = x - width
    else:
        x0 = x
    if "TOP" in name:
        y0 = y - height
    elif "MIDDLE" in name:
        y0 = y - height / 2
    else:
        y0 = y
    return (x0, y0, x0 + width, y0 + height)


def _render_sheet(sheet: Sheet, *, index: int, count: int, label: str, warnings: list | None = None):
    """Build the ezdxf document for one sheet. Returns the document.

    ``warnings`` collects anything the sheet renders but a reader should look
    at -- a dimension whose points miss the geometry, say. The render never
    stops for one: it is the PDF that answers whether the sheet is right.
    """
    import ezdxf
    from ezdxf.enums import TextEntityAlignment

    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()
    for name, (color, linetype, weight) in _LAYERS.items():
        aci = 7 if sheet.ink == "mono" and name != "HIDDEN" else color
        doc.layers.add(name, color=aci, linetype=linetype, lineweight=int(round(weight * 100)))
    dimstyle = _dimstyle(doc, sheet.text_height)
    W, H = sheet.width, sheet.height

    def text(value, x, y, height, align, layer="TITLE", fit: float | None = None):
        # ``fit`` is the width the text may occupy; longer text is set smaller
        # rather than run through a cell divider or off the sheet. Below the
        # smallest legible height the text is cut instead, with an ellipsis, so a
        # long title ends inside its cell rather than running over the next one.
        if fit is not None and value:
            height = max(_MIN_TEXT_MM, min(height, fit / (len(value) * 0.72)))
            room = int(fit / (height * 0.72))
            if len(value) > room:
                value = (value[: max(room - 1, 1)] + "…") if room > 1 else value[:1]
        entity = msp.add_text(value, dxfattribs={"height": height, "layer": layer})
        entity.set_placement((x, y), align=align)
        if layer in ("DIM", "NOTES") and value:
            claim(value, _text_box(value, x, y, height, align))
        return entity

    # Annotation already on the paper, as (what it says, its box). A sheet lays
    # each view out knowing only where the views are, so two views' callouts can
    # still land on each other -- the overall width of one view against the label
    # of the view above it, say. Nothing here moves them, because which of the two
    # should give way is the author's call; it says so instead of leaving it to be
    # noticed on the print.
    claimed: list[tuple[str, tuple[float, float, float, float]]] = []

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
            value = stripped = str(entity.text or "")
            for token in ("\\A0;", "{", "}"):
                stripped = stripped.replace(token, "")
            height = float(entity.dxf.char_height or sheet.text_height)
            insert = entity.dxf.insert
            width = len(stripped.splitlines()[0] if stripped else "") * height * 0.72
            claim(value, (insert.x - width / 2, insert.y - height / 2,
                          insert.x + width / 2, insert.y + height / 2))

    def claim(value: str, box: tuple[float, float, float, float]) -> None:
        for other, taken in claimed:
            if (box[0] < taken[2] and box[2] > taken[0] and box[1] < taken[3] and box[3] > taken[1]):
                if warnings is not None:
                    warnings.append(
                        f"annotation overlaps: {value.strip()!r} is printed over {other.strip()!r} "
                        f"around ({box[0]:.0f}, {box[1]:.0f}). Give the view more room "
                        "(three_views(gap=...)), or place one of them with offset=."
                    )
                break
        claimed.append((value, box))

    # Frame and title block.
    m = _MARGIN
    msp.add_lwpolyline([(m, m), (W - m, m), (W - m, H - m), (m, H - m)], close=True, dxfattribs={"layer": "SHEET"})
    tw, th = min(_TITLE_W, W - 2 * m), _TITLE_H
    x0, y0 = W - m - tw, m
    msp.add_lwpolyline([(x0, y0), (x0 + tw, y0), (x0 + tw, y0 + th), (x0, y0 + th)], close=True, dxfattribs={"layer": "TITLE"})
    msp.add_line((x0, y0 + th / 2), (x0 + tw, y0 + th / 2), dxfattribs={"layer": "TITLE"})
    msp.add_line((x0 + tw * 0.6, y0), (x0 + tw * 0.6, y0 + th), dxfattribs={"layer": "TITLE"})
    left_w, right_w = tw * 0.6 - 6, tw * 0.4 - 6
    text(sheet.title, x0 + 3, y0 + th * 0.75, 5.0, TextEntityAlignment.MIDDLE_LEFT, fit=left_w)
    sub = " · ".join(v for v in (sheet.part_number, sheet.material, sheet.author) if v)
    if sub:
        text(sub, x0 + 3, y0 + th * 0.25, 2.5, TextEntityAlignment.MIDDLE_LEFT, fit=left_w)
    text(f"SCALE {_scale_label(sheet.scale)}   {sheet.units.upper()}   {sheet.projection}",
         x0 + tw - 3, y0 + th * 0.75, 2.5, TextEntityAlignment.MIDDLE_RIGHT, fit=right_w)
    text(f"SHEET {index} OF {count}   REV {sheet.revision}   {label}", x0 + tw - 3, y0 + th * 0.25, 2.5, TextEntityAlignment.MIDDLE_RIGHT, fit=right_w)
    notes = ([f"TOLERANCES PER {sheet.general_tolerance} UNLESS OTHERWISE SPECIFIED."] if sheet.general_tolerance else []) + list(sheet.notes)
    if notes:
        for row, note in enumerate(notes):
            prefix = "NOTES:  " if row == 0 else "        "
            text(f"{prefix}{row + 1}. {note}", m + 3, y0 + th + 4 + (len(notes) - 1 - row) * 5, 2.5, TextEntityAlignment.BOTTOM_LEFT, "NOTES")
    if sheet.revisions:
        # Revision table, top-right inside the frame: REV | DATE | DESCRIPTION.
        cols = (14.0, 26.0, 70.0)
        rw = sum(cols)
        rh = 6.0
        rx, ry = W - m - rw, H - m - rh
        rows = [("REV", "DATE", "DESCRIPTION")] + [tuple(str(v) for v in row) for row in sheet.revisions]
        for r, row in enumerate(rows):
            y = ry - r * rh
            msp.add_lwpolyline([(rx, y), (rx + rw, y), (rx + rw, y + rh), (rx, y + rh)], close=True, dxfattribs={"layer": "TITLE"})
            x = rx
            for c, (width, value) in enumerate(zip(cols, row)):
                if c:
                    msp.add_line((x, y), (x, y + rh), dxfattribs={"layer": "TITLE"})
                text(value, x + 2, y + rh / 2, 2.5, TextEntityAlignment.MIDDLE_LEFT, fit=width - 4)
                x += width

    # Views. Every view's box is known before any annotation is drawn, so a callout
    # can avoid landing on a neighbour.
    s = sheet.scale
    placed = []
    for view in sheet.views:
        proj = _Projection(view.shape, view.name)
        bounds = _edges_bounds(list(proj.visible) + (list(proj.hidden) if view.hidden else []))
        if not bounds:
            continue
        bx0, bx1, by0, by1 = bounds
        cx = (bx0 + bx1) / 2
        cy = (by0 + by1) / 2
        sv = view.scale or s
        half_w = (bx1 - bx0) * sv / 2
        half_h = (by1 - by0) * sv / 2
        placed.append((view, proj, bounds, cx, cy, (view.at[0] - half_w, view.at[0] + half_w, view.at[1] - half_h, view.at[1] + half_h)))
    boxes = [box for (_, _, _, _, _, box) in placed]
    _assert_views_fit(sheet, placed, index=index)

    def blocked(x0, x1, y0, y1, own_box):
        """Whether a landing area [x0,x1]x[y0,y1] runs off the frame or into another view."""
        if min(x0, x1) < m + 2 or max(x0, x1) > W - m - 2:
            return True
        for box in boxes:
            if box is own_box:
                continue
            if max(x0, x1) >= box[0] - 4 and min(x0, x1) <= box[1] + 4 and y1 >= box[2] - 4 and y0 <= box[3] + 4:
                return True
        return False

    for view, proj, bounds, cx, cy, own_box in placed:
        sv = view.scale or s
        # Centre the projected geometry on `at`.

        def to_sheet(p2):
            return (view.at[0] + (p2[0] - cx) * sv, view.at[1] + (p2[1] - cy) * sv)

        def model_to_sheet(p3):
            return to_sheet(proj.point(p3))

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

            seen: set = set()

            def once(key) -> bool:
                if key in seen:
                    return False
                seen.add(key)
                return True

            def q(value: float) -> float:
                return round(value, 6)

            for edge in edges:
                # A circular edge stays a CIRCLE or ARC: exact on the sheet, so a hole
                # reads as a hole and a fillet as a radius rather than as a polyline.
                if edge.geom_type == GeomType.CIRCLE:
                    c = to_sheet((edge.arc_center.X, edge.arc_center.Y))
                    r = edge.radius * sv
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
        if view.centre_marks:
            for centre, radius in _circles(proj.visible):
                c = to_sheet(centre)
                arm = radius * sv + 2.0
                msp.add_line((c[0] - arm, c[1]), (c[0] + arm, c[1]), dxfattribs={"layer": "CENTER"})
                msp.add_line((c[0], c[1] - arm), (c[0], c[1] + arm), dxfattribs={"layer": "CENTER"})
        vx0, vx1, vy0, vy1 = own_box

        # How far annotation already reaches past each side of the view, so a later
        # callout lands outside the dimensions that came before it. Callouts on one
        # side share a knee and stack upward instead of pushing each other outward.
        reach = {"left": 0.0, "right": 0.0, "top": 0.0, "bottom": 0.0}
        landings = {"left": [], "right": []}

        def free_landing_y(side, y):
            step = sheet.text_height * 2.2
            while any(abs(y - used) < sheet.text_height * 1.6 for used in landings[side]):
                y += step
            landings[side].append(y)
            return y

        # Rows already taken on each side, so a dimension left to place itself
        # lands past the ones before it instead of on top of them. `overall()`
        # claims the first row above and the first row to the left.
        rows: dict[str, int] = {"left": 0, "right": 0, "top": 0, "bottom": 0}

        def claim_row(side: str) -> float:
            rows[side] += 1
            return _DIM_ROW * rows[side]

        def linear(a, b, offset, override, orientation, tol=None, fit=None):
            horizontal = (orientation or _spans(a, b)) == "h"
            if offset is None:
                # Unplaced dimensions go above a horizontal pair and right of a
                # vertical one, which are the sides `overall()` does not use twice.
                # The row is measured from the VIEW's edge, not from the dimensioned
                # points, so two dimensions on different features still land on
                # different lines -- which is the whole point of not placing them.
                if horizontal:
                    offset = (vy1 + claim_row("top")) - max(a[1], b[1])
                else:
                    offset = (vx1 + claim_row("right")) - max(a[0], b[0])
            else:
                side = ("top" if offset >= 0 else "bottom") if horizontal else ("right" if offset >= 0 else "left")
                rows[side] = max(rows[side], int(abs(offset) // _DIM_ROW))
            label = (override or "<>") + (f" {fit}" if fit else "")
            # The value is measured in SHEET millimetres, which are the model's only
            # at 1:1. dimlfac scales what the dimension prints back to true size, per
            # view, so a view drawn at its own scale still reads the part.
            style_override = {"dimlfac": 1.0 / sv}
            if tol:
                # The deviations are the author's, in true size, and ezdxf prints them
                # as given -- dimlfac scales the measurement, not the tolerance.
                style_override |= {"dimtol": 1, "dimtp": tol[0], "dimtm": tol[1],
                                   "dimtdec": 2, "dimtfac": 0.7}
            if horizontal:
                base = (a[0], (max(a[1], b[1]) if offset >= 0 else min(a[1], b[1])) + offset)
                d = msp.add_linear_dim(base=base, p1=a, p2=b, angle=0, dimstyle=dimstyle, text=label,
                                       override=style_override, dxfattribs={"layer": "DIM"})
                side = "top" if offset >= 0 else "bottom"
                edge = vy1 if offset >= 0 else vy0
                reach[side] = max(reach[side], abs(base[1] - edge) + sheet.text_height * 1.5)
            else:
                base = ((max(a[0], b[0]) if offset >= 0 else min(a[0], b[0])) + offset, a[1])
                d = msp.add_linear_dim(base=base, p1=a, p2=b, angle=90, dimstyle=dimstyle, text=label,
                                       override=style_override, dxfattribs={"layer": "DIM"})
                side = "right" if offset >= 0 else "left"
                edge = vx1 if offset >= 0 else vx0
                reach[side] = max(reach[side], abs(base[0] - edge) + sheet.text_height * 1.5)
            d.render()
            claim_rendered(d.dimension)

        # The overall pair is the OUTERMOST row on its side: a drawing reads from the
        # view outward, smallest feature first. Its rows are reserved here so the
        # feature dimensions and the hole callouts keep clear of them, and drawn
        # after them so the rows in between stay free.
        unplaced_above = sum(
            1 for d in view._dims
            if d.kind == "linear" and d.offset is None
            and (d.orientation or _spans(model_to_sheet(d.p1), model_to_sheet(d.p2))) == "h"
        )
        overall_top = _DIM_ROW * (unplaced_above + 1)
        overall_left = _DIM_ROW
        if view._overall:
            reach["top"] = max(reach["top"], overall_top + sheet.text_height * 1.5)
            reach["left"] = max(reach["left"], overall_left + sheet.text_height * 1.5)
        def on_view(point, margin: float = 1.0) -> bool:
            """Does a projected point land on the view's own drawn extent?"""
            return (vx0 - margin <= point[0] <= vx1 + margin
                    and vy0 - margin <= point[1] <= vy1 + margin)

        def check(kind: str, index: int, *points) -> None:
            # A dimension between two points in SPACE draws perfectly and measures
            # nothing: move the holes in the model, leave the constants alone, and
            # the sheet prints a clean dimension over blank paper. The commonest
            # cause is model coordinates assumed to be centred when the part was
            # built from a corner.
            off = [p for p in points if not on_view(p)]
            if off and warnings is not None:
                where = ", ".join(f"({p[0]:.1f}, {p[1]:.1f})" for p in off)
                warnings.append(
                    f"{view.name} {kind} {index}: {len(off)} of {len(points)} point(s) fall outside the "
                    f"view's geometry at sheet {where}. The dimension is drawn, but it measures blank "
                    "paper -- check the model coordinates it was given."
                )

        for index, dim in enumerate(view._dims):
            if dim.kind == "linear":
                a, b = model_to_sheet(dim.p1), model_to_sheet(dim.p2)
                check("dim", index, a, b)
                linear(a, b, dim.offset, dim.text, dim.orientation, dim.tol, dim.fit)
            elif dim.kind in ("diameter", "radius", "hole"):
                # A hole callout: a leader from the circle's edge to a horizontal landing
                # outside the view, past whatever dimensions already stand on that side,
                # with the text reading along the landing. Nothing is drawn across the
                # part, and stacked callouts on one side land at their own hole's height.
                centre = model_to_sheet(dim.p1)
                check(dim.kind, index, centre)
                r = dim.radius * sv
                if dim.kind == "hole":
                    value = hole_callout_text(dim.hole, tol=dim.tol, fit=dim.fit)
                else:
                    prefix = "%%c" if dim.kind == "diameter" else "R"
                    value = dim.text if dim.text else f"{prefix}{_fmt(2 * dim.radius if dim.kind == 'diameter' else dim.radius)}"
                text_w = 8.0 + len(value) * sheet.text_height * 0.7
                # Exit on the hole's own side of the view (the short way out), unless the
                # landing there would run into another view or off the frame; then the
                # other side. A leader across the whole part is the last resort.
                prefer_right = centre[0] >= (vx0 + vx1) / 2
                choice = None
                for go_right in (prefer_right, not prefer_right):
                    clear_try = reach["right" if go_right else "left"] + 10.0
                    knee_try = (vx1 + clear_try) if go_right else (vx0 - clear_try)
                    land_x0, land_x1 = (knee_try, knee_try + text_w) if go_right else (knee_try - text_w, knee_try)
                    if not blocked(land_x0, land_x1, centre[1] - sheet.text_height, centre[1] + r + 6.0 + sheet.text_height, own_box):
                        choice = go_right
                        break
                go_right = prefer_right if choice is None else choice
                side = "right" if go_right else "left"
                clear = reach[side] + 10.0
                knee_x = (vx1 + clear) if go_right else (vx0 - clear)
                exit_angle = math.radians(dim.angle if dim.angle is not None else 45.0)
                land_y = free_landing_y(side, centre[1] + r * math.sin(exit_angle) + 6.0)
                # Leave the circle at 45 degrees toward the exit so the arrow reads as a
                # pointer, then run level to the landing.
                sign = 1.0 if go_right else -1.0
                start = (centre[0] + sign * r * abs(math.cos(exit_angle)), centre[1] + r * math.sin(exit_angle))
                knee = (knee_x, land_y)
                landing = (knee[0] + sign * 6.0, knee[1])
                msp.add_leader([start, knee, landing], dxfattribs={"layer": "DIM"},
                               override={"dimasz": sheet.text_height * 0.85, "dimldrblk": "_CLOSEDFILLED"})
                align = TextEntityAlignment.MIDDLE_LEFT if go_right else TextEntityAlignment.MIDDLE_RIGHT
                text(value, landing[0] + sign * 2.0, landing[1], sheet.text_height, align, "DIM")
            elif dim.kind == "angle":
                v = model_to_sheet(dim.p1)
                a = model_to_sheet(dim.p2)
                b = model_to_sheet(dim.hole["p2"])
                check("angle", index, v, a, b)
                ua = math.atan2(a[1] - v[1], a[0] - v[0])
                ub = math.atan2(b[1] - v[1], b[0] - v[0])
                mid = ua + ((ub - ua + math.pi) % (2 * math.pi) - math.pi) / 2
                base = (v[0] + dim.offset * math.cos(mid), v[1] + dim.offset * math.sin(mid))
                d = msp.add_angular_dim_3p(base=base, center=v, p1=a, p2=b, dimstyle=dimstyle, dxfattribs={"layer": "DIM"})
                d.render()
                claim_rendered(d.dimension)
            elif dim.kind == "note":
                p = model_to_sheet(dim.p1)
                check("note", index, p)
                q = (p[0] + dim.radius, p[1] + dim.angle)
                msp.add_leader([p, q, (q[0] + (3 if dim.radius >= 0 else -3), q[1])], dxfattribs={"layer": "NOTES"})
                align = TextEntityAlignment.BOTTOM_LEFT if dim.radius >= 0 else TextEntityAlignment.BOTTOM_RIGHT
                text(dim.text, q[0] + (4 if dim.radius >= 0 else -4), q[1] + 1, sheet.text_height, align, "NOTES")

        if view._overall:
            linear((vx0, vy1), (vx1, vy1), overall_top, None, "h")
            linear((vx0, vy0), (vx0, vy1), -overall_left, None, "v")

        # The view label goes under everything that hangs below the view, so a
        # dimension on the bottom side never sits on it.
        text((view.label or view.name).upper(), view.at[0], vy0 - reach["bottom"] - 6, 3.5,
             TextEntityAlignment.TOP_CENTER, "NOTES")
    return doc


def _write_pdf(docs, sheets: Sequence[Sheet], path: Path) -> None:
    """Render the sheets to one PDF, a page each.

    The PDF is the drawing, so a missing renderer is a failure, not a downgrade:
    an exit 0 with no document is the one outcome a build cannot recover from.
    The page carries no creation date, so the bytes are a function of the
    content, and the render goes to a temporary file that is renamed on success,
    so a failed run never leaves a half-written document behind.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_pdf import PdfPages
        from ezdxf.addons.drawing import Frontend, RenderContext, config
        from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
    except ImportError as exc:
        raise RuntimeError(
            "@eng_drawing writes a PDF and its renderer is missing: "
            f"{exc}. Install cadgen's dependencies (pip install matplotlib pillow)."
        ) from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f".{path.name}.partial")
    try:
        # CreationDate=None drops the one field matplotlib stamps from the clock.
        with PdfPages(partial, metadata={"CreationDate": None}) as pdf:
            for doc, sheet in zip(docs, sheets):
                fig = plt.figure(figsize=(sheet.width / 25.4, sheet.height / 25.4))
                ax = fig.add_axes([0, 0, 1, 1])
                ax.set_xlim(0, sheet.width)
                ax.set_ylim(0, sheet.height)
                ctx = RenderContext(doc)
                ctx.set_current_layout(doc.modelspace())
                backend = MatplotlibBackend(ax, adjust_figure=False)
                Frontend(ctx, backend, config=config.Configuration(
                    background_policy=config.BackgroundPolicy.WHITE,
                    color_policy=config.ColorPolicy.BLACK if sheet.ink == "mono" else config.ColorPolicy.COLOR,
                )).draw_layout(doc.modelspace(), finalize=False)
                ax.set_xlim(0, sheet.width)
                ax.set_ylim(0, sheet.height)
                ax.set_aspect("equal")
                ax.axis("off")
                pdf.savefig(fig)
                plt.close(fig)
        partial.replace(path)
    finally:
        partial.unlink(missing_ok=True)


def eng_drawing(func: Callable[..., Any] | None = None, *, out: str | Path | None = None):
    """Declare an engineering drawing. The function returns a :class:`Sheet` or a
    list of them; calling it (the script's ``__main__`` does) writes one PDF with a
    page per sheet at ``out`` and returns the path written.

    ``out`` is required and relative paths resolve against the script, because
    cadgen has no opinion on where a document belongs -- the caller does.
    """

    def apply(fn: Callable[..., Any]) -> Callable[..., Any]:
        import inspect

        if out is None:
            raise ValueError(
                f"@eng_drawing {fn.__name__} needs out=<path>.pdf: the drawing is that PDF, "
                "and cadgen does not choose where it lands."
            )
        target_spec = Path(out)
        if target_spec.suffix.lower() != ".pdf":
            raise ValueError(f"@eng_drawing out= must name a .pdf, got {out!r}")
        script = Path(inspect.getsourcefile(fn) or inspect.getfile(fn)).resolve()

        @functools.wraps(fn)
        def run(*args: Any, **kwargs: Any) -> list[Path]:
            result = fn(*args, **kwargs)
            sheets = list(result) if isinstance(result, (list, tuple)) else [result]
            if not sheets or not all(isinstance(s, Sheet) for s in sheets):
                raise TypeError(f"@eng_drawing {fn.__name__} must return a Sheet or a list of Sheets")
            from cadgen.drawing_checks import raise_on_error_findings, validate_drawing_document

            target = target_spec if target_spec.is_absolute() else (script.parent / target_spec).resolve()
            docs = []
            notices: list[str] = []
            for index, sheet in enumerate(sheets, start=1):
                doc = _render_sheet(sheet, index=index, count=len(sheets), label=fn.__name__,
                                    warnings=notices)
                # The same checks every @dxf build runs, against the document the
                # page is rendered from: duplicate geometry, unset units, an empty
                # sheet. A drawing skipping them is how the duplicates went unseen.
                findings = validate_drawing_document(doc)
                raise_on_error_findings(findings, label=f"{fn.__name__} sheet {index}")
                for finding in findings:
                    if finding.severity == "warning":
                        print(f"{fn.__name__} sheet {index} {finding.render()}")
                docs.append(doc)
            for notice in notices:
                print(f"{fn.__name__}: {notice}")
            _write_pdf(docs, sheets, target)
            print(f"wrote {target} ({len(sheets)} page{'s' if len(sheets) != 1 else ''})")
            return [target]

        run.__cadgen_eng_drawing__ = True  # type: ignore[attr-defined]
        return run

    return apply(func) if func is not None else apply
