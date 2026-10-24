# drawings

The eight scripts of `models/drawings/src`, on cadgen 0.8: a drawing is a `@model`
whose body returns 2D build123d geometry, and `exports.py` writes the DXF of each, by
build123d's own DXF exporter from the model's planar document: this corpus's example of
DXF deliverables (flat patterns among them) kept current by an `exports.py`.

| Script | DXF (`exports.py`) | What it is |
| --- | --- | --- |
| `angled_tab.py` | `DXF/angled_tab.dxf` | Plate with a corner gusset tab on a **45° bend line** (`BEND`) |
| `cabinet_panel_drawing.py` | `DXF/cabinet_panel_drawing.dxf` | Workshop **drawing**: three views on `CUT`, engraved dimension callouts and title block on `ENGRAVE` |
| `clamp_plate.py` | `DXF/clamp_plate.dxf` | The cut profile of a solid (`lib/clamp_plate_profile.py`): its top face laid onto z=0 |
| `gasket_plate.py` | `DXF/gasket_plate.dxf` | Rounded gasket, bolt holes and a centre cutout on `CUT`, an open crosshair on `ENGRAVE` |
| `l_bracket_flat.py` | `DXF/l_bracket_flat.dxf` | Sheet-metal flat pattern with a single bend line |
| `label_plate.py` | `DXF/label_plate.dxf` | Laser-cut label: engraved text outlines + an open score line on `ENGRAVE` |
| `multi_bend_test_panel.py` | `DXF/multi_bend_test_panel.dxf` | **Four bends in three orientations** on one blank |
| `u_channel_bracket.py` | `DXF/u_channel_bracket.dxf` | U-channel flat pattern with **two parallel** bend lines |

Build from this folder, any one, then write every DXF (`../DXF/`, gitignored):

```
python gasket_plate.py
python cabinet_panel_drawing.py
python exports.py
cadgen snapshot ../DXF/cabinet_panel_drawing.dxf cabinet.png
```

Each bend fixture is there for a case:

- `l_bracket_flat.py`: the ordinary case, one bend, edge to edge.
- `u_channel_bracket.py`: two parallel bends, so the web stays flat and both flanges
  fold the same way: bend ordering, and a segment bounded by a bend on both sides.
- `angled_tab.py`: an arbitrary bend-line orientation. Every other fixture's lines are
  vertical, so a fold that handles only constant-X axes renders this one wrong.
- `multi_bend_test_panel.py`: the fold model itself, five faces and four hinges in a
  tree. Two parallel verticals, a horizontal tab fold whose line is a chord (it spans
  only the tab; the same infinite line continues along the panel's bottom edge, where
  no bend runs), and a 45° corner fold: the one that fails when a fold cuts by its
  infinite line instead of its own segment.

The cabinet panel is the one drawing document rather than a cut layout: its dimension
values are `bd.Text` outlines and its witness, leader, centre and shelf lines open
geometry, which an engrave layer allows.

The port:

- `@dxf(out=...)` -> `@model`, the DXF written by `exports.py`; cadgen's build123d proxy
  -> `import build123d as bd`. Each script's `__main__` calls its model.
- Layers: the `{"CUT": ..., "BEND": ...}` dict becomes a compound of labelled children,
  a part per layer (`plate.label, bend.label = "CUT", "BEND"`); a layer of several
  shapes is one part of them all (`bd.Compound([line, line])`: the bends of
  `u_channel_bracket` and `multi_bend_test_panel`, the text and score of
  `label_plate`, the cabinet panel's annotation). A model returning one shape is the
  layer `CUT`.
- `cadgen.flatten.flat_pattern(plate(), ..., coordinate=THICKNESS_MM, kerf=0)` becomes
  the solid's top face moved onto z=0: one planar face at that height, no kerf, which is
  all the flat pattern did here. The helper stays a plain module, not a model.

The drawing checks run on every DXF before it is written (units, closed cut
profiles, no duplicate or zero-length entity, open geometry only on a bend, engrave
or reference layer); all eight pass them. Run them on any DXF with
`cadgen.engine.export.dxf.validate_dxf_file`.
