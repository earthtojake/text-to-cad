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


def render_drawing_svg(
    dxf_path: str | Path,
    *,
    hidden_layers: tuple[str, ...] = (),
    background: str = "white",
    lineweight_scale: float = 1.0,
    dimension_units: str = "drawn",
    dimension_decimals: int | None = None,
    dimension_text_scale: float = 1.0,
) -> str:
    """``lineweight_scale`` multiplies every stroke (the viewer's Fine/Normal/Bold);
    the DXF's own lineweights stay the reference at 1.0. The ``dimension_*`` options
    re-state the dimensions' display (see ``restyle_dimensions``)."""
    import ezdxf
    from ezdxf.addons.drawing import Frontend, RenderContext, config, layout
    from ezdxf.addons.drawing.svg import SVGBackend

    document = ezdxf.readfile(str(dxf_path))
    restyle_dimensions(document, units=dimension_units, decimals=dimension_decimals, text_scale=dimension_text_scale)
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
