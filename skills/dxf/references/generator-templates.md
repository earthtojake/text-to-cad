# DXF generator templates

Read this file when creating a new `<name>.dxf.py` drawing generator. Copy the
template for the workflow that applies and replace the TODO markers. Every
template follows the same contract: `gen_dxf()` takes no arguments and returns
`{"document": <ezdxf document>}` (or the bare document); the CLI owns output
paths; validation runs during generation, so cut layers must hold closed
profiles and open geometry belongs on bend/engrave/reference-named layers.

## 1. Standalone drafting (DXF from scratch)

For pure 2D outputs — gaskets, panels, templates, cut layouts — with no 3D
model behind them. Keep meaningful dimensions as named parameters.

```python
"""Standalone 2D drawing: <description>."""

from __future__ import annotations

import ezdxf

# TODO: named dimension parameters
WIDTH_MM = 40.0
HEIGHT_MM = 20.0


def gen_dxf():
    document = ezdxf.new("R2010")
    document.units = ezdxf.units.MM
    modelspace = document.modelspace()
    document.layers.add("CUT")

    modelspace.add_lwpolyline(
        [(0, 0), (WIDTH_MM, 0), (WIDTH_MM, HEIGHT_MM), (0, HEIGHT_MM)],
        close=True,
        dxfattribs={"layer": "CUT"},
    )
    return {"document": document}


if __name__ == "__main__":
    gen_dxf()
```

## 2. Projection of a generated STEP part

For flat patterns / profiles of a `$cad` model. The `.dxf.py` sits beside the
`<name>.step.py` it projects and path-loads it (dotted-extension files cannot
be imported by module name). Keep the drawing logic — typically a `build_dxf()`
helper built on `cadgen.flatten` — in the `.step.py` or a plain helper module;
the `.dxf.py` is the drawing entry point. The loaded `.step.py` and its imports
are recorded as freshness inputs automatically.

```python
"""Flat-pattern DXF drawing for <name>; geometry reused from <name>.step.py."""

from __future__ import annotations

from pathlib import Path

from cadgen.sources import load_source_module

_step = load_source_module(Path(__file__).with_name("<name>.step.py"))


def gen_dxf():
    return {
        "document": _step.build_dxf(),
    }


if __name__ == "__main__":
    gen_dxf()
```

## 3. Projection of an imported STEP

For a vendor/imported `.step` with no Python source. Only Python sources are
freshness inputs — the drawing does not auto-rebuild when the imported STEP
file changes; rerun with `--force` after replacing it.

The face selection and projection are part-specific judgment calls: pick the
planar face(s) that define the cut profile and the 2D projection for that
plane. `cadgen.flatten` owns the projection/union/emission machinery.

```python
"""DXF projection of <name>.step."""

from __future__ import annotations

from pathlib import Path

import build123d
import ezdxf
from cadgen import flatten

_STEP_PATH = Path(__file__).with_name("<name>.step")


def gen_dxf():
    shape = build123d.import_step(str(_STEP_PATH))
    document = ezdxf.new("R2010")
    document.units = ezdxf.units.MM
    modelspace = document.modelspace()
    document.layers.add("CUT")

    faces = flatten.planar_faces(
        shape,
        normal_axis="z", normal_sign=1.0,      # TODO: the profile face plane
        coordinate_axis="z", coordinate=0.0,   # TODO: the face location
    )
    geometry = flatten.union_projected_faces(
        [(faces, lambda v: (v.X, v.Y))],       # TODO: projection for that plane
    )
    flatten.add_shapely_geometry(modelspace, geometry, layer="CUT")
    return {"document": document}


if __name__ == "__main__":
    gen_dxf()
```

## Common additions

- **Bend/fold lines**: draw them on a layer whose name contains "bend"
  (e.g. `document.layers.add("BEND", linetype="DASHED")`); open geometry is
  allowed there and downstream tools classify it as bends rather than cuts.
- **Kerf / tool-radius compensation**: offset closed profiles with
  `cadgen.flatten.offset_geometry` (shapely geometry) or
  `cadgen.flatten.offset_closed_points` (point lists); do not hand-offset
  coordinates.
- **Circles**: emit holes with `flatten.add_shapely_geometry` (fits circles
  from projected rings automatically) or `flatten.add_circle_polyline` when
  drafting directly.
