# DXF Examples

Small 2D DXF fixtures for exercising the `dxf` skill tooling, all in one flat
folder: Python `gen_dxf()` generator sources alongside raw imported `.dxf`
files. Everything here is intentionally simple so failures point at the
tooling, not the fixture.

## Generated sources (`.dxf.py` / `.step.py`)

Build them with the DXF skill CLI (`python skills/dxf/scripts/dxf <source>`);
drawing packages land in the gitignored `__cadgen__/` cache and `.dxf` exports
are written on demand only, so no generated DXF output is committed. Together
they cover the skill's standalone-drafting and STEP-projection workflows.

- `gasket_plate.dxf.py` — standalone drafting: rounded-rectangle gasket
  outline (lwpolyline bulge arcs), four bolt holes, center cutout, and an
  engraved alignment crosshair on an `ENGRAVE` layer.
- `l_bracket_flat.dxf.py` — standalone sheet-metal flat pattern: rectangular
  blank, four mounting holes, and a dashed bend line on a `BEND` layer.
- `clamp_plate.step.py` + `clamp_plate.dxf.py` — STEP-projection workflow: the
  `.dxf.py` path-loads the sibling `.step.py` and projects its top-face
  topology to a cut profile with `cadgen.flatten` (outline, two bolt holes,
  center slot).

## Imported files (`.dxf`)

Raw DXF files downloaded from permissively licensed (MIT) test suites,
committed via Git LFS. They cover both R12 (AC1009) and R2013+ (AC1027)
flavors and a spread of entity types, including files that intentionally fail
the skill's drawing checks — useful fixtures for validator and viewer
robustness.

Each entry lists two robustness datapoints: the skill validator verdict
(`scripts/dxf --validate`) and how the CAD Viewer's DXF flat-pattern renderer
handles the file. As of 0.4.0 the viewer renderer handles LINE, ARC, CIRCLE,
and LWPOLYLINE; everything else fails gracefully with a typed error card.

From [gdsestimating/dxf-parser](https://github.com/gdsestimating/dxf-parser)
(`test/data`, MIT):

- `arc1.dxf` — single ARC on a non-cut-named layer (R12). Validation: FAIL
  (`open_cut_profile`), as expected for an open arc. Viewer: renders.
- `ellipse.dxf` — two ELLIPSE entities (R12). Validation: ok. Viewer: error
  card "Unsupported DXF entity ELLIPSE".
- `splines.dxf` — two SPLINE entities (R12). Validation: FAIL
  (`units_not_set`, `open_cut_profile`), as expected for open splines.
  Viewer: error card "Unsupported DXF entity SPLINE".
- `polylines.dxf` — twelve legacy POLYLINE entities (R12). Validation: ok.
  Viewer: error card "Unsupported DXF entity POLYLINE".

From [mozman/ezdxf](https://github.com/mozman/ezdxf) (`examples_dxf`, MIT):

- `minimal_r12.dxf` — the 35-byte minimal R12 skeleton
  (`Minimal_DXF_AC1009.dxf`). Validation: FAIL (`empty_drawing`), as expected
  for an empty modelspace. Viewer: error card "No supported DXF entities
  found".
- `multi_insert_with_attribs.dxf` — block INSERT with attributes (R2013).
  Validation: ok. Viewer: error card "Unsupported DXF entity INSERT".
- `circle_radius_le_0.dxf` — two zero-radius CIRCLE entities (R2013).
  Validation: FAIL (`zero_length_entity` x2), as expected for degenerate
  geometry. Viewer: error card "Invalid DXF circle radius".

Validate any of them post-hoc with:

```bash
python skills/dxf/scripts/dxf --validate models/dxf/<file>.dxf
```
