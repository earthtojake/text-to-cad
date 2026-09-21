"""Write the DXF renderer's browser-test fixture: one tiny drawing, and the
payload ``GET /__cad/drawing`` answers for it.

The drawing is deliberately one of each thing the renderer has to get right:

* default-pen line-work (ACI 7, which the client paints with the theme
  foreground, so a theme flip is visible in a screenshot),
* a RED circle, so a pen that is not the default survives the round trip,
* a solid hatch with an island, so the even-odd fill leaves a real hole,
* TEXT, which ezdxf outlines into filled paths on the server,
* an LWPOLYLINE with a bulge, so a curve reaches the client as a path.

Regenerate with (from the repository root):

    .venv/bin/python packages/ui/src/renderers/dxf/__fixtures__/make_fixture.py

Both outputs are committed: the browser test serves the JSON, and the `.dxf`
is what makes the JSON reproducible.
"""

from __future__ import annotations

import json
from pathlib import Path

import ezdxf

from cadgen.drawing_payload import build_drawing_payload

HERE = Path(__file__).resolve().parent
DXF_PATH = HERE / "sample.dxf"
PAYLOAD_PATH = HERE / "sample.drawing.json"


def build_document() -> ezdxf.document.Drawing:
    document = ezdxf.new("R2010")
    document.header["$INSUNITS"] = 4  # millimetres
    modelspace = document.modelspace()

    # Default pen: layer "0" is ACI 7, so these come back with `color: null`.
    for start, end in (
        ((0, 0), (100, 0)),
        ((100, 0), (100, 60)),
        ((100, 60), (0, 60)),
        ((0, 60), (0, 0)),
    ):
        modelspace.add_line(start, end)

    # A pen of its own: ACI 1 is red.
    modelspace.add_circle((22, 40), radius=12, dxfattribs={"color": 1})

    # A solid hatch with an island: the inner ring must read as a hole.
    hatch = modelspace.add_hatch(color=5)
    hatch.paths.add_polyline_path(
        [(58, 28), (92, 28), (92, 52), (58, 52)], is_closed=True, flags=1
    )
    hatch.paths.add_polyline_path(
        [(68, 34), (82, 34), (82, 46), (68, 46)], is_closed=True, flags=0
    )

    # Text: outlined on the server into filled paths.
    modelspace.add_text("PART A", height=6, dxfattribs={"color": 3}).set_placement((8, 8))

    # A bulged LWPOLYLINE: one true arc, so a `path` primitive with curves arrives.
    modelspace.add_lwpolyline(
        [(30, 8, 0, 0, 0.6), (50, 8, 0, 0, 0), (50, 18, 0, 0, 0)],
        dxfattribs={"color": 4},
    )
    return document


def main() -> None:
    build_document().saveas(DXF_PATH)
    payload = build_drawing_payload(DXF_PATH)
    PAYLOAD_PATH.write_text(json.dumps(payload, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    print(f"{DXF_PATH.name}: {DXF_PATH.stat().st_size} bytes")
    print(f"{PAYLOAD_PATH.name}: {len(payload['primitives'])} primitives, bounds {payload['bounds']}")


if __name__ == "__main__":
    main()
