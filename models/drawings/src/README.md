# drawings models

The repo's 2D `@dxf` fixtures as one cad-project: every script directly
under `src/` is a runnable drawing model and its artifact lands in `DXF/`.
Parts live in the sibling `models/examples/` project and assemblies in
`models/assemblies/`. Nothing here is committed except this `src/` tree — build
what you need.

```bash
python models/drawings/src/gasket_plate.py       # one drawing
ls models/drawings/src/*.py | xargs -n1 -P4 python   # every drawing
```

Unchanged drawings are no-ops. The one helper module lives in `src/lib/`
(`clamp_plate_profile`) — a plain module, never a model.

### Drawings

Small 2D `@dxf` fixtures for exercising the `dxf` skill tooling. Everything
here is intentionally simple so failures point at the tooling, not the fixture.
Written DXF bytes are a pure function of the returned geometry, so a rebuild
that changes them is a real change to report, not noise.

| Script | Artifact | Description |
|--------|----------|-------------|
| `angled_tab.py` | `DXF/angled_tab.dxf` | Plate with a corner gusset tab on a **45° bend line** |
| `cabinet_panel_drawing.py` | `DXF/cabinet_panel_drawing.dxf` | Workshop **drawing**: three views, engraved dimension callouts, title block |
| `clamp_plate.py` | `DXF/clamp_plate.dxf` | Cut profile projected from 3D topology (`lib/clamp_plate_profile.py`) |
| `gasket_plate.py` | `DXF/gasket_plate.dxf` | Rounded gasket, bolt holes, centre cutout, engraved crosshair |
| `l_bracket_flat.py` | `DXF/l_bracket_flat.dxf` | Sheet-metal flat pattern with a single bend line |
| `label_plate.py` | `DXF/label_plate.dxf` | Laser-cut label: engraved text outlines + an open score line |
| `multi_bend_test_panel.py` | `DXF/multi_bend_test_panel.dxf` | **Four bends in three orientations** on one blank |
| `u_channel_bracket.py` | `DXF/u_channel_bracket.dxf` | U-channel flat pattern with **two parallel** bend lines |

Together these cover the skill's standalone-drafting and topology-projection
workflows. `lib/clamp_plate_profile.py` is the clamp plate as a build123d
solid — a plain helper, not a `@step` model: the profile is projected from live
geometry rather than read back from a STEP artifact this project wrote (which
the `$dxf` skill forbids — the freshness gate could never say "current").

Build: `python src/<script>` per row; unchanged models are no-ops.

## Why the cabinet panel drawing exists

`cabinet_panel_drawing.py` is the only model here that is a **drawing document**
rather than a cut layout: three views (front elevation, plan, section A-A), the
eleven measurements a cabinetmaker needs, and a title block. It was a committed
baked file until its information was re-expressed in what `@dxf` actually emits —
geometry on layers that carry intent. The views and dowel holes are `CUT`;
everything annotative is `ENGRAVE`, so the dimension VALUES are `bd.Text`
outlines and the witness, leader, centre and shelf lines are open geometry, which
an engrave-intent layer allows. The DXF constructs the retired ezdxf generator
used — `DIMENSION` entities, ISO 128 `CENTER`/`HIDDEN` linetypes, a non-plotting
layer, `TEXT` entities — have no `@dxf` equivalent and are not reproduced; the
numbers they carried are. That generator is in git history at
`models/drawings/dxf/cabinet_panel_drawing.dxf.py`.

## Why each bend fixture exists

- `l_bracket_flat.py` — the ordinary case: one bend, edge to edge.
- `u_channel_bracket.py` — **two parallel** bends, so the web stays flat and
  both flanges fold the same way. Covers bend ordering and a segment bounded by
  a bend on both sides, which the single-bend L-bracket cannot exercise.
- `angled_tab.py` — arbitrary bend-line ORIENTATION. Every other bend fixture's
  lines are vertical, so a fold that only handles constant-X axes renders this
  one wrong.
- `multi_bend_test_panel.py` — the fold model itself: five faces, four hinges, a
  tree. Two parallel verticals, a horizontal tab fold whose line is a *chord*
  (it spans only the tab, and the same infinite line continues along the
  panel's bottom edge where no bend runs), and a 45° corner fold. This is the
  one that fails when a fold cuts by its infinite line instead of its own
  segment.

## Validating a drawing

Validate any drawing post-hoc with the drawing checks (there is no
`--validate` flag; a clean drawing reports no findings):

```python
from cadgen.drawing_checks import validate_dxf_file

print([finding.render() for finding in validate_dxf_file("DXF/gasket_plate.dxf")])
```
