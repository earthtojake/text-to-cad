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


def render_drawing_svg(dxf_path: str | Path, *, hidden_layers: tuple[str, ...] = (), background: str = "white") -> str:
    import ezdxf
    from ezdxf.addons.drawing import Frontend, RenderContext, config, layout
    from ezdxf.addons.drawing.svg import SVGBackend

    document = ezdxf.readfile(str(dxf_path))
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
        min_lineweight=0.15,
    )).draw_layout(document.modelspace(), finalize=True)
    page = layout.Page(0, 0, layout.Units.mm, margins=layout.Margins.all(0))
    return backend.get_string(page)
