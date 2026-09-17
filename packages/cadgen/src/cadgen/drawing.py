"""Engineering drawings: ``@drawing``, :class:`Sheet` and :class:`View`.

A drawing is a DOCUMENT derived from a part: orthographic views projected from
the part's geometry, dimensions that reference points ON that geometry, centre
marks found on it, a sheet frame and a title block. Because every view and every
dimension is computed from the shape at run time, the drawing follows the part:
change the model, rerun the drawing script, and the views, hidden lines and
measured values move with it. Nothing on the sheet is drawn by hand.

Where ``@dxf`` writes geometry only (a cut layout is a toolpath), ``@drawing``
writes the format's own document constructs: real ``DIMENSION`` entities (the
value is measured, the arrowheads and witness lines are the dimension style's),
``TEXT`` for notes and the title block, and a LAYER table whose linetypes say
which lines are hidden or centre lines. Any CAD package, and the CAD Viewer,
reads those as a drawing.

Usage::

    from cadgen.drawing import drawing, Sheet, source_step

    @drawing(out="../DXF/bracket_drawing.dxf")
    def bracket_drawing():
        part = source_step("../STEP/bracket.step")      # the model's own artifact
        sheet = Sheet("A3", title="BRACKET", part_number="BRK-001", revision="A")
        top = sheet.view(part, "top", at=(110, 190))
        front = sheet.view(part, "front", at=(110, 90))
        top.overall()                                    # width and height
        top.dim((-35, 25, 0), (35, 25, 0), offset=26)    # model coordinates
        top.diameter((35, 25, 15), 1.5, text="%%c3 x 8 DEEP, 4 PLACES")
        return sheet                                     # or [sheet1, sheet2]

    if __name__ == "__main__":
        bracket_drawing()

Running the script writes one ``.dxf`` per sheet (the first at ``out``, the rest
suffixed ``-sheet2``, ``-sheet3``) and, when matplotlib is installed, one PDF
with a page per sheet beside them under ``PDF/``. The DXF is the artifact the
CAD Viewer catalogs; the PDF is the document to send.

Bytes are a function of the content: ezdxf's volatile provenance is pinned the
same way ``@dxf`` pins it, so an unchanged drawing rebuilds to identical files.

This module keeps ``@drawing`` outside the build store on purpose: a drawing
is a document over an artifact, not a model with a closure to hash. Import
discipline: nothing here pulls in ezdxf or the CAD kernel at module scope.
"""

from __future__ import annotations

import functools
import io
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

__all__ = ["drawing", "Sheet", "View", "source_step", "SHEET_SIZES"]

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
    "bottom": ((0.0, 0.0, -1.0), (0.0, 1.0, 0.0)),
    "front": ((0.0, -1.0, 0.0), (0.0, 0.0, 1.0)),
    "back": ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    "right": ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    "left": ((-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    "iso": ((1.0, -1.0, 1.0), (0.0, 0.0, 1.0)),
}

#: Layers a sheet writes, with ACI colour and linetype. ``ink="mono"`` collapses
#: the colours to the default ink; the linetypes are the drawing's meaning and stay.
_LAYERS = {
    "SHEET": (7, "CONTINUOUS", 0.35),
    "TITLE": (7, "CONTINUOUS", 0.25),
    "VISIBLE": (7, "CONTINUOUS", 0.5),
    "HIDDEN": (8, "HIDDEN", 0.25),
    "CENTER": (4, "CENTER", 0.18),
    "DIM": (1, "CONTINUOUS", 0.18),
    "NOTES": (3, "CONTINUOUS", 0.25),
}

_MARGIN = 10.0
_TITLE_W, _TITLE_H = 180.0, 40.0


def source_step(path: str | Path):
    """The part a drawing documents, read from a STEP file the model wrote (or any
    STEP). Relative paths resolve against the calling script, like ``out=``."""
    from build123d import import_step

    resolved = _resolve_relative(Path(path), depth=2)
    if not resolved.is_file():
        raise FileNotFoundError(
            f"source_step: {resolved} does not exist. Run the model that writes it first "
            "(python <model>.py); a drawing documents the artifact, it does not build it."
        )
    return import_step(str(resolved))


def _resolve_relative(path: Path, *, depth: int) -> Path:
    if path.is_absolute():
        return path
    import inspect

    frame = inspect.stack()[depth]
    return (Path(frame.filename).resolve().parent / path).resolve()


@dataclass
class _Dim:
    kind: str
    p1: tuple[float, float, float]
    p2: tuple[float, float, float] | None
    offset: float
    text: str | None
    orientation: str | None
    radius: float = 0.0
    angle: float = 45.0


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
    _dims: list[_Dim] = field(default_factory=list)
    _overall: bool = False

    def dim(self, p1, p2, *, offset: float = 12.0, text: str | None = None, orientation: str | None = None) -> "View":
        """A linear dimension between two model points. ``orientation`` is ``"h"``,
        ``"v"`` or None (whichever the projected pair spans more); ``offset`` is
        the dimension line's distance from the farther point, in sheet mm, and its
        sign picks the side."""
        self._dims.append(_Dim("linear", _p3(p1), _p3(p2), offset, text, orientation))
        return self

    def diameter(self, center, radius: float, *, angle: float = 45.0, text: str | None = None) -> "View":
        """A diameter dimension on a circular feature at a model centre point."""
        self._dims.append(_Dim("diameter", _p3(center), None, 0.0, text, None, radius=radius, angle=angle))
        return self

    def radius(self, center, radius: float, *, angle: float = 45.0, text: str | None = None) -> "View":
        self._dims.append(_Dim("radius", _p3(center), None, 0.0, text, None, radius=radius, angle=angle))
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
    ink: str = "color"
    text_height: float = 3.5
    views: list[View] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.size not in SHEET_SIZES:
            raise ValueError(f"unknown sheet size {self.size!r}; one of {sorted(SHEET_SIZES)}")
        if not (self.scale > 0):
            raise ValueError("scale must be positive")

    @property
    def width(self) -> float:
        return SHEET_SIZES[self.size][0]

    @property
    def height(self) -> float:
        return SHEET_SIZES[self.size][1]

    def view(self, shape, name: str, *, at, label: str | None = None, hidden: bool = True, centre_marks: bool = True) -> View:
        if name not in VIEW_DIRECTIONS:
            raise ValueError(f"unknown view {name!r}; one of {sorted(VIEW_DIRECTIONS)}")
        view = View(self, shape, name, (float(at[0]), float(at[1])), label, hidden, centre_marks)
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
        o = probes[0][0]
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
    style.dxf.dimblk = "_CLOSEDFILLED"
    return "Standard"


def _render_sheet(sheet: Sheet, *, index: int, count: int, label: str):
    """Build the ezdxf document for one sheet. Returns the document."""
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

    def text(value, x, y, height, align, layer="TITLE"):
        msp.add_text(value, dxfattribs={"height": height, "layer": layer}).set_placement((x, y), align=align)

    # Frame and title block.
    m = _MARGIN
    msp.add_lwpolyline([(m, m), (W - m, m), (W - m, H - m), (m, H - m)], close=True, dxfattribs={"layer": "SHEET"})
    tw, th = min(_TITLE_W, W - 2 * m), _TITLE_H
    x0, y0 = W - m - tw, m
    msp.add_lwpolyline([(x0, y0), (x0 + tw, y0), (x0 + tw, y0 + th), (x0, y0 + th)], close=True, dxfattribs={"layer": "TITLE"})
    msp.add_line((x0, y0 + th / 2), (x0 + tw, y0 + th / 2), dxfattribs={"layer": "TITLE"})
    msp.add_line((x0 + tw * 0.6, y0), (x0 + tw * 0.6, y0 + th), dxfattribs={"layer": "TITLE"})
    text(sheet.title, x0 + 3, y0 + th * 0.75, 5.0, TextEntityAlignment.MIDDLE_LEFT)
    sub = " · ".join(v for v in (sheet.part_number, sheet.material, sheet.author) if v)
    if sub:
        text(sub, x0 + 3, y0 + th * 0.25, 2.5, TextEntityAlignment.MIDDLE_LEFT)
    scale_text = "1:1" if abs(sheet.scale - 1) < 1e-9 else (f"1:{1 / sheet.scale:g}" if sheet.scale < 1 else f"{sheet.scale:g}:1")
    text(f"SCALE {scale_text}   {sheet.units.upper()}   {sheet.projection}", x0 + tw - 3, y0 + th * 0.75, 2.5, TextEntityAlignment.MIDDLE_RIGHT)
    text(f"SHEET {index} OF {count}   REV {sheet.revision}   {label}", x0 + tw - 3, y0 + th * 0.25, 2.5, TextEntityAlignment.MIDDLE_RIGHT)
    if sheet.notes:
        for row, note in enumerate(sheet.notes):
            prefix = "NOTES:  " if row == 0 else "        "
            text(f"{prefix}{row + 1}. {note}", m + 3, y0 + th + 4 + (len(sheet.notes) - 1 - row) * 5, 2.5, TextEntityAlignment.BOTTOM_LEFT, "NOTES")

    # Views.
    s = sheet.scale
    for view in sheet.views:
        proj = _Projection(view.shape, view.name)
        # Centre the projected geometry on `at`.
        pts = [p for e in list(proj.visible) + (list(proj.hidden) if view.hidden else []) for p in _edge_polyline(e, 8)]
        if not pts:
            continue
        cx = (min(p[0] for p in pts) + max(p[0] for p in pts)) / 2
        cy = (min(p[1] for p in pts) + max(p[1] for p in pts)) / 2

        def to_sheet(p2):
            return (view.at[0] + (p2[0] - cx) * s, view.at[1] + (p2[1] - cy) * s)

        def model_to_sheet(p3):
            return to_sheet(proj.point(p3))

        def put(edges, layer):
            for edge in edges:
                poly = [to_sheet(p) for p in _edge_polyline(edge)]
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
                arm = radius * s + 2.0
                msp.add_line((c[0] - arm, c[1]), (c[0] + arm, c[1]), dxfattribs={"layer": "CENTER"})
                msp.add_line((c[0], c[1] - arm), (c[0], c[1] + arm), dxfattribs={"layer": "CENTER"})
        xs = [to_sheet(p)[0] for p in pts]
        ys = [to_sheet(p)[1] for p in pts]
        vx0, vx1, vy0, vy1 = min(xs), max(xs), min(ys), max(ys)
        text((view.label or view.name).upper(), view.at[0], vy0 - 6, 3.5, TextEntityAlignment.TOP_CENTER, "NOTES")

        def linear(a, b, offset, override, orientation):
            dx, dy = abs(b[0] - a[0]), abs(b[1] - a[1])
            horizontal = (orientation or ("h" if dx >= dy else "v")) == "h"
            if horizontal:
                base = (a[0], (max(a[1], b[1]) if offset >= 0 else min(a[1], b[1])) + offset)
                d = msp.add_linear_dim(base=base, p1=a, p2=b, angle=0, dimstyle=dimstyle, text=override or "<>", dxfattribs={"layer": "DIM"})
            else:
                base = ((max(a[0], b[0]) if offset >= 0 else min(a[0], b[0])) + offset, a[1])
                d = msp.add_linear_dim(base=base, p1=a, p2=b, angle=90, dimstyle=dimstyle, text=override or "<>", dxfattribs={"layer": "DIM"})
            d.render()

        if view._overall:
            linear((vx0, vy1), (vx1, vy1), 12.0, None, "h")
            linear((vx0, vy0), (vx0, vy1), -12.0, None, "v")
        for dim in view._dims:
            if dim.kind == "linear":
                linear(model_to_sheet(dim.p1), model_to_sheet(dim.p2), dim.offset, dim.text, dim.orientation)
            elif dim.kind in ("diameter", "radius"):
                centre = model_to_sheet(dim.p1)
                adder = msp.add_diameter_dim if dim.kind == "diameter" else msp.add_radius_dim
                d = adder(center=centre, radius=dim.radius * s, angle=dim.angle, dimstyle=dimstyle, text=dim.text or "<>", dxfattribs={"layer": "DIM"})
                d.render()
            elif dim.kind == "note":
                p = model_to_sheet(dim.p1)
                q = (p[0] + dim.radius, p[1] + dim.angle)
                msp.add_leader([p, q, (q[0] + (3 if dim.radius >= 0 else -3), q[1])], dxfattribs={"layer": "NOTES"})
                align = TextEntityAlignment.BOTTOM_LEFT if dim.radius >= 0 else TextEntityAlignment.BOTTOM_RIGHT
                text(dim.text, q[0] + (4 if dim.radius >= 0 else -4), q[1] + 1, sheet.text_height, align, "NOTES")
    return doc


def _emit(doc, *, label: str) -> bytes:
    from cadgen._internal.dxf_emit import _assert_volatile_fields_pinned, _canonicalize_class_registry

    _canonicalize_class_registry(doc)
    buffer = io.StringIO()
    doc.write(buffer)
    payload = buffer.getvalue()
    _assert_volatile_fields_pinned(payload, label=label)
    return payload.encode("utf-8")


def _write_pdf(docs, sheets: Sequence[Sheet], path: Path) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_pdf import PdfPages
        from ezdxf.addons.drawing import Frontend, RenderContext, config
        from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
    except Exception:  # noqa: BLE001 - the PDF is the optional half; the DXF is the artifact
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(path) as pdf:
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
    return True


def drawing(func: Callable[..., Any] | None = None, *, out: str | None = None, pdf: str | bool = True):
    """Declare a drawing. The function returns a :class:`Sheet` or a list of them;
    calling it (the script's ``__main__`` does) writes the files and returns the
    paths written."""

    def apply(fn: Callable[..., Any]) -> Callable[..., Any]:
        import inspect

        script = Path(inspect.getsourcefile(fn) or inspect.getfile(fn)).resolve()

        @functools.wraps(fn)
        def run(*args: Any, **kwargs: Any) -> list[Path]:
            result = fn(*args, **kwargs)
            sheets = list(result) if isinstance(result, (list, tuple)) else [result]
            if not sheets or not all(isinstance(s, Sheet) for s in sheets):
                raise TypeError(f"@drawing {fn.__name__} must return a Sheet or a list of Sheets")
            target = (script.parent / (out or f"../DXF/{fn.__name__}.dxf")).resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            from cadgen._internal.dxf_emit import _pinned_ezdxf_metadata, write_dxf

            written: list[Path] = []
            docs = []
            with _pinned_ezdxf_metadata():
                for index, sheet in enumerate(sheets, start=1):
                    label = fn.__name__
                    doc = _render_sheet(sheet, index=index, count=len(sheets), label=label)
                    docs.append(doc)
                    path = target if index == 1 else target.with_name(f"{target.stem}-sheet{index}{target.suffix}")
                    write_dxf(_emit(doc, label=f"{label} sheet {index}"), path)
                    written.append(path)
                    print(f"wrote {path}")
            if pdf:
                pdf_path = (script.parent / pdf).resolve() if isinstance(pdf, str) else target.parent.parent / "PDF" / f"{target.stem}.pdf"
                if _write_pdf(docs, sheets, pdf_path):
                    written.append(pdf_path)
                    print(f"wrote {pdf_path} ({len(sheets)} page{'s' if len(sheets) != 1 else ''})")
                else:
                    print("skipped PDF: matplotlib is not installed (pip install matplotlib)")
            return written

        run.__cadgen_drawing__ = True  # type: ignore[attr-defined]
        return run

    return apply(func) if func is not None else apply
