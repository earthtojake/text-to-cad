# Meshing, the tape, and review

Read this when a mesh is wanted (printing, a viewer-only preview), when
choosing its resolution, or when explaining what the written files contain.
The everyday output is the STEP; the mesh is one build away from the tape.

## How a part becomes a mesh

The field is sampled on a grid of cells of size `resolution` over the part's
bounds (padded by two cells), and contoured with surface nets: one vertex per
cell the surface crosses, placed where the tangent planes at the cell's edge
crossings meet (dual contouring's placement), so box edges and hole rims come
out sharp; one quad per crossed grid edge. The mesh is closed and outward
facing by construction. Normals come from the field's gradient, so curved
surfaces shade smoothly at any grid size; an edge whose two faces disagree by
more than `crease_deg` (35° by default) is creased.

The cost is the grid: halving the resolution multiplies samples by eight. A
30 mm part at 0.5 mm is about 100k samples and a fraction of a second; at
0.1 mm it is 30M samples and many seconds. The engine refuses a grid over
40M samples and says which resolution would fit.

**Choosing a resolution**

| Need | Cell size |
| --- | --- |
| a quick look | the default (diagonal / 120) |
| holes and walls read true | ≤ a third of the smallest hole radius or wall |
| a print-ready STL | 0.2–0.3 mm for FDM, finer only for resin |

Set it in the decorator when the part declares a mesh; override for one run
with `python part.py --resolution R`, or build a mesh from the tape.

## The tape

Running a part writes `<stem>.implicit.json` beside its first output: the
field as data (every leaf, transform and boolean with its numbers), the
bounds, the resolution and the leaf table. It is the part's source of truth:
the STEP and any mesh are derived from it and can be rebuilt without the
script.

```bash
cadgen implicit build src/housing.implicit.json                              # the STEP, blends as fillets
cadgen implicit build src/housing.implicit.json STL/housing.stl --resolution 0.25
cadgen implicit build src/housing.implicit.json GLB/housing.glb --crease-deg 20 --json
```

A part that uses `im.custom(...)`, or a B-rep leaf with no file, writes no
tape; its script is the only way to rebuild it, and the build result says so.

## What the files hold

- **STEP**: the B-rep, one solid (or several, when the tree describes them).
  Faces are the leaves' surfaces, blends are fillets. `cadgen implicit faces`
  maps any face back to its leaf and source line.
- **GLB**: Y-up glTF, one node per leaf, named by the leaf's label, each with
  its own colour and extras naming the leaf id, kind, label and source line.
  The viewer's Leaves panel lists them; picking one names the code that made it.
- **STL**: binary, flat-shaded, one solid. No names or colours survive an STL.
- **Tape**: see above. Keep it beside the STEP; `faces` and `build` read it there.

`cadgen stl build` / `glb build` are the STEP-document doors and work on the
STEP an implicit part wrote, as on any STEP; `cadgen implicit build` from the
tape is the exact way.

## STEP

The STEP is the default output. Translated exactly: every primitive (a box's
`radius` and a cylinder's `radius_edge` become fillets), sharp `|`/`&`/`-`,
translate, rotate, scale, mirror, repeat, offset and shell (OpenCascade's
offset, which can refuse a shape it dislikes). A boolean's `round`/`chamfer`
becomes a fillet or chamfer on the edges that boolean made; when OpenCascade
refuses it the radius is halved up to three times, then each tool's edges are
tried alone, and a join it still refuses is left sharp with a warning naming
it. `--blends drop` leaves every blend sharp; `--blends refuse` fails instead.
`elongate` and `custom` have no B-rep. A tree the kernel cannot build falls
back to a `.glb` of the same name, and the build result says why. Read the
warnings and repeat them in the report: a STEP with a dropped blend differs
from the field at that join.

Building the B-rep costs what a `$cad` build costs (a couple of seconds,
mostly the kernel import). While iterating, `python part.py` with a `.glb` in
`out` and no `.step` is a fraction of a second; add the STEP when the shape
is settled.

In a `$cad` model, `im.to_brep(field)` returns the build123d shape, so an
implicit part can be composed into a STEP assembly or filleted with B-rep
tools from there.

## Reviewing

```bash
cadgen step snapshot src/housing.step tmp/housing.png
cadgen step snapshot src/housing.step tmp/housing-under.png --camera bottom
cadgen glb snapshot GLB/housing.glb tmp/housing-mesh.png
```

Look for: a feature that vanished (resolution too coarse), a faceted curve
(too coarse for the radius), a stray shell or floating piece (a boolean that
did not join — check `round` reach, or that a translated feature overlaps its
base), and the leaf colours landing where the request said. Then hand the GLB
to `$cad-viewer`.
