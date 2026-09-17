"""A drawing document rendered to SVG, the way it prints.

The viewer draws a dimensioned DXF on screen from ezdxf's own drawing add-on
rather than from a second renderer: linetypes, lineweights, dimension styles
and text come out exactly as the PDF the drawing skill writes, and there is one
look for a sheet instead of two. ezdxf is a cadgen dependency and is cheap; it
is imported inside the function so the server keeps its start time.

The page is the drawing's extent with no margin, so the client can lay the
image over the same bounds the parsed geometry reports.
"""

from __future__ import annotations

from pathlib import Path


#: How the viewer may re-state a drawing's dimensions. Values only, never geometry:
#: ``units`` "drawn" leaves the file's numbers, "mm"/"in" convert them; ``decimals``
#: fixes the places shown (None keeps the file's); ``text_scale`` sizes the dimension
#: text and arrows relative to the file's own.
DIMENSION_UNITS = ("drawn", "mm", "in")
DIMENSION_DECIMALS = (0, 1, 2, 3)

#: Drawing units (DXF $INSUNITS) to millimetres, for the ones a drawing plausibly uses.
_MM_PER_INSUNIT = {1: 25.4, 2: 304.8, 4: 1.0, 5: 10.0, 6: 1000.0}


def restyle_dimensions(document, *, units: str = "drawn", decimals: int | None = None, text_scale: float = 1.0) -> int:
    """Re-render every DIMENSION in modelspace with the requested display, in memory.

    A DIMENSION carries its measured value; its text is generated from the
    dimension style, so precision, unit and text size are display choices the
    viewer can make without touching what the drawing measures. Returns the
    number of dimensions re-rendered (0 when nothing was asked for).
    """
    if units not in DIMENSION_UNITS:
        raise ValueError(f"units must be one of {DIMENSION_UNITS}, got {units!r}")
    if decimals is not None and decimals not in DIMENSION_DECIMALS:
        raise ValueError(f"decimals must be one of {DIMENSION_DECIMALS}, got {decimals!r}")
    text_scale = max(0.25, min(4.0, float(text_scale) or 1.0))
    if units == "drawn" and decimals is None and abs(text_scale - 1.0) < 1e-9:
        return 0
    mm_per_unit = _MM_PER_INSUNIT.get(int(document.header.get("$INSUNITS", 4) or 4), 1.0)
    count = 0
    for dimension in document.modelspace().query("DIMENSION"):
        style = document.dimstyles.get(dimension.dxf.dimstyle) if dimension.dxf.dimstyle in document.dimstyles else None
        override = dimension.override()
        # dimrnd 0.0 (what a saved Standard style carries) makes ezdxf round to a whole
        # number; a rounding unit one place below the shown precision keeps the places.
        attribs = {"dimdsep": ord("."), "dimrnd": 10.0 ** -((decimals if decimals is not None else 3) + 1)}
        if decimals is not None:
            attribs.update({"dimdec": decimals, "dimzin": 0})
        if units == "mm":
            attribs.update({"dimlfac": mm_per_unit, "dimpost": "<>"})
        elif units == "in":
            attribs.update({"dimlfac": mm_per_unit / 25.4, "dimpost": '<>"'})
            if decimals is None:
                attribs.update({"dimdec": 3, "dimzin": 0})
        if abs(text_scale - 1.0) >= 1e-9:
            for key in ("dimtxt", "dimasz"):
                current = override.get(key, style.get_dxf_attrib(key, 2.5) if style is not None else 2.5)
                attribs[key] = float(current) * text_scale
        override.update(attribs)
        override.commit()
        dimension.render()
        count += 1
    return count


XDATA_APPID = "CADGEN"


def _entity_tags(entity) -> dict:
    """The ``view=``/``dim=`` tags a cadgen sheet wrote on an entity, or {}."""
    if not entity.has_xdata(XDATA_APPID):
        return {}
    out = {}
    for tag in entity.get_xdata(XDATA_APPID):
        value = str(tag.value)
        if "=" in value:
            key, _, rest = value.partition("=")
            out[key] = rest
    return out


def parse_view_moves(spec: str) -> dict[str, tuple[float, float]]:
    """``"FRONT:10,-5;RIGHT:0,20"`` -> {"FRONT": (10, -5), "RIGHT": (0, 20)}; bad parts are skipped."""
    moves: dict[str, tuple[float, float]] = {}
    for part in str(spec or "").split(";"):
        name, _, delta = part.strip().partition(":")
        try:
            dx, dy = (float(v) for v in delta.split(","))
        except ValueError:
            continue
        if name.strip():
            moves[name.strip().lower()] = (dx, dy)
    return moves


def parse_tolerance_spec(spec: str) -> dict:
    """``"±0.1"`` / ``"0.1"`` -> symmetric; ``"+0.05/-0.02"`` -> deviations; anything
    else (``"H7"``) -> a fit class appended to the value. Returns dimstyle overrides
    plus an optional ``"fit"`` key."""
    text = str(spec or "").strip().replace("\u00b1", "±")
    if not text:
        return {}
    if "/" in text:
        plus, _, minus = text.partition("/")
        try:
            return {"dimtol": 1, "dimtp": abs(float(plus)), "dimtm": abs(float(minus)), "dimtdec": 2, "dimtfac": 0.7}
        except ValueError:
            return {"fit": text}
    try:
        value = abs(float(text.lstrip("±")))
    except ValueError:
        return {"fit": text}
    return {"dimtol": 1, "dimtp": value, "dimtm": value, "dimtdec": 2, "dimtfac": 0.7}


def parse_draft_dimensions(spec: str) -> list[tuple]:
    """``"x1,y1,x2,y2,off[,h|v];..."`` -> [(x1, y1, x2, y2, off, orientation), ...]; bad parts skipped."""
    drafts = []
    for part in str(spec or "").split(";"):
        fields = [f.strip() for f in part.split(",")]
        try:
            numbers = [float(v) for v in fields[:5]]
        except ValueError:
            continue
        if len(numbers) != 5:
            continue
        orientation = fields[5].lower() if len(fields) > 5 and fields[5] else None
        drafts.append((*numbers, orientation if orientation in ("h", "v") else None))
    return drafts


def parse_tolerances(spec: str) -> list[tuple[str, str]]:
    """``"view:index=SPEC;..."`` -> [("view:index", "SPEC"), ...]."""
    out = []
    for part in str(spec or "").split(";"):
        key, _, value = part.partition("=")
        if key.strip() and value.strip():
            out.append((key.strip(), value.strip()))
    return out


def preview_edits(document, *, moves: dict | None = None, draft_dimension=None,
                  highlight: str = "", tolerance=None) -> None:
    """Apply the viewer's PREVIEW edits to an in-memory document. Nothing is saved:
    these show what a script change would look like before the agent makes it.

    ``moves``: {view name (lower): (dx, dy)} translates a tagged view's entities.
    ``draft_dimension``: (x1, y1, x2, y2, offset, orientation) in sheet mm adds a
    red linear dimension. ``highlight``: "view:index" paints that dimension red.
    ``tolerance``: ("view:index", spec) restates that dimension with a tolerance.
    """
    msp = document.modelspace()
    moves = {k.lower(): v for k, v in (moves or {}).items()}
    hl_view, _, hl_index = str(highlight or "").partition(":")
    if isinstance(tolerance, tuple):
        tolerance = [tolerance]
    tolerances = {}
    for key, spec in (tolerance or []):
        view_name, _, index = str(key).partition(":")
        tolerances[(view_name.lower(), index)] = spec
    for entity in list(msp):
        tags = _entity_tags(entity)
        view = str(tags.get("view", "")).lower()
        if not view:
            continue
        if view in moves:
            dx, dy = moves[view]
            entity.translate(dx, dy, 0)
        index = tags.get("dim")
        if index is None:
            continue
        tol_spec = tolerances.get((view, index))
        if tol_spec and entity.dxftype() == "DIMENSION":
            attribs = parse_tolerance_spec(tol_spec)
            fit = attribs.pop("fit", None)
            override = entity.override()
            if attribs:
                override.update({**attribs, "dimdsep": ord(".")})
                override.commit()
            if fit:
                base = str(entity.dxf.text or "<>").split(" ")[0] or "<>"
                entity.dxf.text = f"{base} {fit}"
            entity.render()
        if hl_view and hl_view.lower() == view and hl_index == index:
            entity.dxf.color = 1
            if entity.dxftype() == "DIMENSION":
                block = document.blocks.get(entity.dxf.geometry)
                for part in block:
                    part.dxf.color = 1
    if isinstance(draft_dimension, tuple):
        draft_dimension = [draft_dimension]
    for draft in (draft_dimension or []):
        x1, y1, x2, y2, offset, orientation = draft
        horizontal = (orientation or ("h" if abs(x2 - x1) >= abs(y2 - y1) else "v")) == "h"
        if horizontal:
            base = (x1, (max(y1, y2) if offset >= 0 else min(y1, y2)) + offset)
            dim = msp.add_linear_dim(base=base, p1=(x1, y1), p2=(x2, y2), angle=0, dimstyle="Standard",
                                     override={"dimdsep": ord(".")}, dxfattribs={"layer": "DIM", "color": 1})
        else:
            base = ((max(x1, x2) if offset >= 0 else min(x1, x2)) + offset, y1)
            dim = msp.add_linear_dim(base=base, p1=(x1, y1), p2=(x2, y2), angle=90, dimstyle="Standard",
                                     override={"dimdsep": ord(".")}, dxfattribs={"layer": "DIM", "color": 1})
        dim.render()
        for part in document.blocks.get(dim.dimension.dxf.geometry):
            part.dxf.color = 1


def render_drawing_svg(
    dxf_path: str | Path,
    *,
    hidden_layers: tuple[str, ...] = (),
    background: str = "white",
    lineweight_scale: float = 1.0,
    dimension_units: str = "drawn",
    dimension_decimals: int | None = None,
    dimension_text_scale: float = 1.0,
    moves: dict | None = None,
    draft_dimension: tuple | None = None,
    highlight: str = "",
    tolerance: tuple[str, str] | None = None,
) -> str:
    """``lineweight_scale`` multiplies every stroke (the viewer's Fine/Normal/Bold);
    the DXF's own lineweights stay the reference at 1.0. The ``dimension_*`` options
    re-state the dimensions' display (see ``restyle_dimensions``)."""
    import ezdxf
    from ezdxf.addons.drawing import Frontend, RenderContext, config, layout
    from ezdxf.addons.drawing.svg import SVGBackend

    document = ezdxf.readfile(str(dxf_path))
    restyle_dimensions(document, units=dimension_units, decimals=dimension_decimals, text_scale=dimension_text_scale)
    if moves or draft_dimension or highlight or tolerance:
        preview_edits(document, moves=moves, draft_dimension=draft_dimension, highlight=highlight, tolerance=tolerance)
    hidden = {name.strip().upper() for name in hidden_layers if name.strip()}
    if hidden:
        for layer in document.layers:
            if layer.dxf.name.upper() in hidden:
                layer.off()
    context = RenderContext(document)
    backend = SVGBackend()
    policy = config.BackgroundPolicy.WHITE if background == "white" else config.BackgroundPolicy.OFF
    Frontend(context, backend, config=config.Configuration(
        background_policy=policy,
        lineweight_policy=config.LineweightPolicy.ABSOLUTE,
        lineweight_scaling=max(0.25, min(4.0, float(lineweight_scale) or 1.0)),
        min_lineweight=0.15,
    )).draw_layout(document.modelspace(), finalize=True)
    page = layout.Page(0, 0, layout.Units.mm, margins=layout.Margins.all(0))
    return backend.get_string(page)
