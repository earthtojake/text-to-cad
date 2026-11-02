"""Write the DXF renderer's browser-test fixture: one tiny drawing, and the
payload ``GET /api/v1/documents/dxf/<id>/drawing`` answers for it.

The drawing is deliberately one of each thing the renderer has to get right:

* default-pen line-work (ACI 7, which the client paints with the theme
  foreground, so a theme flip is visible in a screenshot),
* a RED circle, so a pen that is not the default survives the round trip,
* a solid hatch with an island, so the even-odd fill leaves a real hole,
* TEXT, which arrives as a `text` primitive the client sets with `fillText`,
* an LWPOLYLINE with a bulge, so a curve reaches the client as a path.

`layered.dxf` is the drawing with structure a Layers section is for: five
layers, a block placed twice on one of them with its centre line on another,
and a dimension -- what the renderer's Layers, Select and reference tests read
(`layered.drawing.json`).

Regenerate with (from the repository root):

    .venv/bin/python packages/ui/src/renderers/dxf/__fixtures__/make_fixture.py

Both outputs are committed: the browser test serves the JSON, and the `.dxf`
is what makes the JSON reproducible.
"""

from __future__ import annotations

import json
from pathlib import Path

import ezdxf

from cad_server.drawing_payload import build_drawing_payload

HERE = Path(__file__).resolve().parent
DXF_PATH = HERE / "sample.dxf"
PAYLOAD_PATH = HERE / "sample.drawing.json"
LAYERED_DXF_PATH = HERE / "layered.dxf"
LAYERED_PAYLOAD_PATH = HERE / "layered.drawing.json"


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

    # Text: a `text` primitive, set by the client where ezdxf placed it.
    modelspace.add_text("PART A", height=6, dxfattribs={"color": 3}).set_placement((8, 8))

    # A bulged LWPOLYLINE: one true arc, so a `path` primitive with curves arrives.
    modelspace.add_lwpolyline(
        [(30, 8, 0, 0, 0.6), (50, 8, 0, 0, 0), (50, 18, 0, 0, 0)],
        dxfattribs={"color": 4},
    )
    return document


def build_layered_document() -> ezdxf.document.Drawing:
    document = ezdxf.new("R2010", setup=True)
    document.header["$INSUNITS"] = 4  # millimetres
    for name, color in (("CUT", 7), ("BEND", 3), ("ENGRAVE", 5), ("HARDWARE", 1), ("CENTRE", 8)):
        document.layers.add(name, color=color)
    modelspace = document.modelspace()
    # A plate with two holes and a bend line.
    modelspace.add_lwpolyline([(0, 0), (120, 0), (120, 60), (0, 60)], close=True, dxfattribs={"layer": "CUT"})
    modelspace.add_circle((20, 30), 6, dxfattribs={"layer": "CUT"})
    modelspace.add_circle((60, 30), 4, dxfattribs={"layer": "CUT"})
    modelspace.add_line((80, 0), (80, 60), dxfattribs={"layer": "BEND"})
    modelspace.add_text("PANEL 7", height=5, dxfattribs={"layer": "ENGRAVE"}).set_placement((30, 48))
    # A fastener block, placed twice: its outline takes the INSERT's layer (it is on "0"), its
    # centre line keeps its own.
    bolt = document.blocks.new("M5_NUT")
    bolt.add_circle((0, 0), 4.6)
    bolt.add_line((-6, 0), (6, 0), dxfattribs={"layer": "CENTRE"})
    modelspace.add_blockref("M5_NUT", (100, 15), dxfattribs={"layer": "HARDWARE"})
    modelspace.add_blockref("M5_NUT", (100, 45), dxfattribs={"layer": "HARDWARE"})
    modelspace.add_linear_dim(base=(0, -8), p1=(0, 0), p2=(120, 0), dxfattribs={"layer": "ENGRAVE"}).render()
    return document


def write(document, dxf_path: Path, payload_path: Path) -> None:
    document.saveas(dxf_path)
    payload = build_drawing_payload(dxf_path)
    payload_path.write_text(json.dumps(payload, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    print(f"{dxf_path.name}: {dxf_path.stat().st_size} bytes")
    print(f"{payload_path.name}: {len(payload['primitives'])} primitives, bounds {payload['bounds']}")


def main() -> None:
    write(build_document(), DXF_PATH, PAYLOAD_PATH)
    write(build_layered_document(), LAYERED_DXF_PATH, LAYERED_PAYLOAD_PATH)


if __name__ == "__main__":
    main()
