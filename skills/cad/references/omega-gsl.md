# Implicit models in GSL (omega)

GSL is the language of [omega-core](https://github.com/Gradient-Control-Laboratories/omega-core), Gradient Control
Laboratories' toolchain for implicit (signed-distance) models: a part is a field, negative inside, and booleans,
blends, lattices, shells and offsets are arithmetic on fields. It is good at what B-rep modelling is bad at:
smooth blends between any two shapes, gyroid and beam lattices, conformal infill, variable thickness, organic
forms. Its output is a mesh (STL), never a STEP: a part that has to be machined, toleranced or exported as exact
geometry is remodelled in build123d once its shape is settled.

Use it where the request asks for it: a concept, a rough or quick look at a part whose shape is still being
settled, GSL or omega by name, work on an existing `.gsl`, or a lattice, an infill or a blended organic shape. A
concept is quick to change, each change a few edited numbers, which is what it is for.

Use build123d for every other part. A request for a new part that names none of these is an exact part: build
it in build123d, and make no concept of it first.

## The stage: a concept, quickly

A GSL model is a concept: something to look at and change in seconds, before the part is exact. Work to that:

- **Sizes, positions, wall thicknesses and holes are as asked.** Probe them.
- **Blend and fillet radii are nominal.** Use the library's round blends (`unionRound`, `intersectRound`,
  `differenceRound`) as they are, and say where one departs from the radius asked ([Blends and
  fillets](#blends-and-fillets) says where that is). Do not write a blend of your own to hold a radius: that is
  the build123d remodel's work, and it costs minutes for a fraction of a millimetre nobody sees at this stage.
- **Check with the picture, `bounds` and a handful of `eval` points**, the ones that say each face and hole is
  where it was asked for. `certify` is for a through hole or a join that is in doubt.
- **No `volume` and no mesh while iterating.** `volume` takes over a minute on a blended part and a mesh longer;
  neither says anything the picture and `bounds` do not.
- **Stop when the part is right for this stage**, and say what is approximate.

When the person asks for an exact radius, a proof or a file, give it: the rest of this page says how.

## The tool

`gsl` comes with the `omega` integration, `cad[omega]` (the `omega-core` wheel: macOS and Linux, no Windows
build). `cad run gsl ...` installs it on first use and runs it as it is:

| Task | Command |
| --- | --- |
| The language reference, before writing GSL | omega-core's [language specification](https://github.com/Gradient-Control-Laboratories/omega-core/blob/v0.1.3/doc/gsl_lang_spec_current.md) and [standard library](https://github.com/Gradient-Control-Laboratories/omega-core/tree/v0.1.3/stdlib) (`builtin`, and `mechanical`, `map`, `lattice` and the rest beside it) at the pinned release |
| Check it parses and links | `cad run gsl compile -t ast --no-meta -o - part.gsl > /dev/null` (silent when it is fine; errors name the line) |
| Picture the field, no mesh | `cad run gsl render --views iso,top --light -o part.png part.gsl` |
| Ask the field (values, extrema, volume, proofs) | `cad run gsl eval REQUEST.json`, or `omega_core.Session` in a script run with `cad run` |
| Mesh it, checked, when a file is wanted | `cad gsl mesh part.gsl part.glb` (a value for one of its names: `--define r=6.5`) |
| The mesh as STL or 3MF | `cad glb export part.glb part.stl` |
| An STL as gsl writes it, and that mesh judged | `cad run gsl compile -t stl -o part.stl part.gsl`, then `cad gsl validate part.gsl --mesh part.stl` |
| Exact parts around a concept part: clearance, interference, contacts | `cad gsl fit enclosure.gsl "$ID"` (`--contact x,y,z` where a part should touch it), [below](#a-concept-among-exact-parts) |
| A bake checked against its concept, and the concept kept as baked | `cad gsl bake part.gsl "$ID"`; after the concept changes, `--stale` ([below](#from-concept-to-exact-geometry)) |

`gsl compile`'s defaults are the right ones: dual contouring (`--algo mdc`, flat faces flat and sharp edges sharp),
octree depth 9 (`--subdivision`), in the `@scene` box. Do not pass `--bbox auto`: its box is a fit by sampling,
which misses features thinner than its cells (a 0.4 mm fin 30 mm long is cut off near its root, and `gsl` exits
0). Keep dual contouring over `--algo marching-cubes`, which rounds sharp edges and can leave small holes in a
concave wall, such as a hollow part's cavity.

## Write a model

```gsl
@scene(120)

// A bracket: an upright standing on a plate, blended, with a 2 mm skin and a gyroid infill.
plate = boxCentered([0, 0, 3], [80, 40, 6]);
upright = boxCentered([-35, 0, 28], [6, 32, 44]);
solid = unionRound(plate, upright, 6);
skin = max(solid, -(solid + 2));

g = sin(p.x * 0.5) * cos(p.y * 0.5) + sin(p.y * 0.5) * cos(p.z * 0.5) + sin(p.z * 0.5) * cos(p.x * 0.5);
infill = max(abs(g) - 0.4, solid + 1);

return min(skin, infill);
```

- **Always `@scene(size)` first.** It names the box the model is meshed in: an edge of `size` mm centred on the
  origin, which must hold the whole part with room to spare. Without it `gsl` guesses the box and cuts off thin
  features; `cad gsl mesh` and `cad gsl validate` refuse a model without one.
- Lengths are millimetres; `p` is the point. `boxCentered`, `sphere`, `cylinderCapped`, `torus` and the rest,
  `unionRound` / `differenceSharp` / `intersectChamfer` and their families, are the `builtin` package's. A blend
  argument is an operator, not a radius: `boxCentered(center, size, intersectRound(4))` rounds a box's edges.
  `atan(y, x)` is the two-argument arc tangent (`atan2` is reserved).
- A round blend (`unionRound` and its family) of two faces in one plane bulges past them by r(1 - 1/sqrt 2),
  1.76 mm for r = 6: stand one shape on or inside the other, never flush with it, where the blend is meant
  for the corner between them.
- A lattice that meets a skin at an edge is non-manifold there: let it run into the skin (`solid + 1` inside
  a 2 mm skin), never stop at its surface, and join the two with a small round blend (`unionRound(skin,
  lattice, 1)`): a sharp `min` leaves surfaces passing through each other where they cross.
- The `lattice` package has the lattices: `lattice.solidify(normalizeField(tpms.gyroid([8, 8, 8])), 0, 1.0)` is
  a gyroid sheet of 0.95 mm (a gyroid's field changes 1.5 to 1.8 times as fast as distance, so without
  `normalizeField` the same call gives 0.56 to 0.68 mm), `lattice.solidify(beam.octet([8, 8, 8]), 0.8)` octet
  struts of 0.8 mm radius; a `wall` that is a field
  grades it. A strut lattice cut sharply by a shell or a box can go non-manifold where the cut just grazes
  a strut; blended into its shell (`unionRound(shell, struts, 1)`) it is manifold, though omega-core 0.1.1 can still leave
  places where its surface passes through itself: `cad stl dfm` finds them. A lattice cut by a body's outline leaves loose fragments (`cad stl dfm`: `several_solids`).
- Two shapes that only touch, face to face, mesh as two bodies: overlap them.
- A mesh holds no tolerance. A 6 mm bore comes out 5.989 to 6.011 mm (H7 is 6.000 to 6.012) and `thread.male`
  an M6 at 6.015 mm over the crests: bores, threads and fits are modelled in build123d.
- `abs(f) - t` is a wall 2t thick only where `f` is a true distance. A field that is not one (a lobed or twisted
  radius, a gyroid, a sum of fields) changes faster than distance, and its wall comes out thinner than written:
  measure it (`cad stl dfm`, below) before printing.
- A wall must be thicker than a few mesh cells: a cell is `size / 2^9`, 0.23 mm in `@scene(120)`. A thinner wall
  is lost and `gsl` still exits 0.

## The language, in what bites

- `p` (the point, mm) and `time` are implicit, never parameters. Each name is assigned once.
- `return a, b;` unions the returns. Library packages are used by their last path segment, with no import:
  `drill.hole`, `map.axisAt`, `transform.translate`, `metal.aluminum`.
- Reserved and builtin names are not identifiers: `part`, `map`, `box`, `sphere`, `select`, `chan`, among others.
  The compiler suggests a rename.
- A shape's `.color` is sRGB `[r, g, b]` in 0..1, or `color.fromHex("#8fa3b8")`; a bare hex string is refused.
- `shape.dp` is a field's gradient.
- `remap(shape, q)` reads `shape` at the point `q` and drops its bounds; `transform.translate`, `transform.rotateX`
  and the rest move a shape and keep them.
- `@range(lo, hi) name = value;` makes a top-level number a slider: make a part's driving dimensions sliders.
  `gsl eval`'s `describe` lists them, and a query's `defs` (`"t = 8.0;"`) sets one for that query alone.
- Booleans are `min` (union), `max` (intersect) and `max(a, -b)` (subtract), each with blended forms
  (`unionRound`, `intersectChamfer`, ...).

## Idioms for mechanical parts

```gsl
@scene(140, 10)
@range(3, 12) t = 6.0;

// Extrude: a 2D XY profile made solid between z = 0 and z = t.
baseProfile = rectangleXYCentered([0, 0], [80, 50], intersectRound(6));   // corners R6
base = max(baseProfile, abs(p.z - t / 2) - t / 2);

// A box with every edge rounded.
upright = boxCentered([-37, 0, 30], [6, 50, 60], intersectRound(1.5));

// An inside-corner fillet r = 4 as its own solid: the corner square less the fillet's circle, along Y.
r = 4.0;
cx = -34 + r;
cz = t + r;
fillet = max(p.x - cx, p.z - cz, -37 - p.x, t / 2 - p.z, r - length([p.x - cx, p.z - cz]), abs(p.y) - 25);
body = min(base, upright, fillet);

// Revolve: a 2D profile in (radius, height) turned about +Z, then placed.
bossProfile = (q) { return max(q.x - 9, -q.x + 4, -q.y, q.y - 12); };   // a tube r 4..9, h 12
boss = transform.translate(remap(bossProfile([length(p.xy), p.z]), p), [20, 0, t]);

// Holes are void solids cut down from z = 0, put on a face by its point and outward normal.
cb = drill.hole([drill.thru(5.5), drill.bore(9.5, 3.0)], 0);              // counterbored M5
h1 = remap(cb, map.axisAt([0, 15, t], [0, 0, 1]));
side = remap(drill.hole([drill.thru(6.6)], 0), map.axisAt([-34, 0, 40], [1, 0, 0]));

bracket = max(unionRound(body, boss, 2), -h1, -side);
mat, col = metal.aluminum();
bracket.material = mat;
bracket.color = col;
return bracket;
```

Hollow a solid and keep its outside with `max(d, -(d + t))`; grow it with `d - r` and shrink it with `d + r`.
Patterns are `remap(shape, map.patternPolarXY(n))` and `map.patternRepeatXY([dx, dy])`. Fasteners, threads, gears
and joints
are `fastener.*`, `thread.*`, `gears.*` and `joint.*`; `gsl compile` names a function's arguments when a call is
wrong.

- `map.patternRepeatXY([dx, dy])` repeats about the origin: one copy sits at (0, 0), the rest `dx` and `dy` apart.
  Four posts at (±a, ±b) are one post at (a, b) mirrored: `remap(post, [abs(p.x), abs(p.y), p.z])`.
- A `drill` hole is open above its mouth, by design, so a hole whose mouth is on a face inside the part (a post's
  top inside a closed shell) cuts on through every wall above it. Stop it in the air between the mouth and the
  next wall, never at the mouth itself: `max(hole, p.z - zStop)`.

| Need | Call |
| --- | --- |
| A hole, feature by feature, from its mouth at `zTop` | `drill.hole([...], zTop)` of `drill.thru(d)`, `drill.blind(d, depth)`, `drill.bore(d, depth)`, `drill.chamfer(d, leg)`, `drill.countersink(d, included)` (the angle in radians: `90 * 3.141592653589793 / 180`), `drill.tap(major, pitch, depth)`, `drill.slot(d, centers, ang)` |
| A screw's hole, to ISO 273 `fit` (`fastener.fitFine`, `fitMedium`, `fitCoarse`) | `fastener.clearanceHole(m, fit)`, `fastener.countersunkHole(m, fit)` (ISO 10642), `fastener.tappedHole(m, shankLength)` |
| Place it | a hole by `map.axisAt(point, outwardNormal)`; a screw by `fastener.seatedAt(seat, shankDir)` |
| Hollow | `max(d, -(d + t))` keeps the outside and hollows a wall `t` thick inward. `shell(d, thickness)` centres the wall on the surface, half of it outside; `shell(d, thickness, bias)` puts it inside at bias -1 and outside at +1 |

## Blends and fillets

For a concept, `unionRound` and its family are the blend to use; the rest of this section is what they make,
so a departure can be named, and what an exact one costs.

- `unionRound(a, b, r)` is a round fillet of radius `r` only where two exact distance fields meet at 90 degrees, a
  boss standing on a plate. Where the faces meet at another angle it departs from a fillet: by about 1.2, 2.5 and
  5.2 mm at 60, 45 and 30 degrees for `r = 3`.
- Besides its bulge along flush faces (above), it raises bumps where a face hidden inside either body comes within
  `r` of the surface. So it suits an upright standing on a plate inside the plate's outline, as in Write a
  model, where no face of one is flush with a face of the other. For an L-corner, whose wall and base share
  their back, bottom and end faces, union sharply and add the fillet as its own solid, as in the idioms.
- Two more places a round blend adds material where none was meant, both of which `bounds` shows as a box
  larger than the part. A post standing on a floor with its base in the floor's outer face bulges through
  that face (0.05 to 0.6 mm for `r = 2`): blend the post into the cavity (`differenceRound(cavity, posts, r)`)
  or cut the result back to the outside shape (`intersectSharp(blended, outer)`). A cylinder that starts on
  another's axis swells the far side of it: start it part way out, still buried.
- A blend does not bridge a gap as wide as its radius or wider: a post 2 mm from a wall is not joined to it by
  `unionRound(shell, post, 2)`. Where the request asks for the two to be joined, join them: add a web, widen
  the blend, or move the post, and say which. Leaving the gap open is not the request.
- When a fillet must keep its radius at any angle, the closing of the two bodies does on straight seams:
  `unionRoundExact(() { return a - r; }, () { return b - r; }) + r`, with exact distance fields. A max of planes
  is exact only on its faces; write a rectangle with `m = [max(qx, 0), max(qy, 0)];` and `w = max(m.x, m.y);`
  as `max(qx, qy) + sqrt(dot(m, m) + 1e-30) - sqrt(w * w + 1e-30)`, whose gradient is the normal on the faces
  themselves, which the closing reads. It has costs, so it is not for a concept:
  - on a curved seam it runs full: about 0.08 mm for `r = 3` on a 12 mm boss standing square, and up to
    1.7 mm for `r = 12` where a 24 mm pipe leaves a 30 mm one at 30 degrees;
  - it fills any concave gap narrower than `2r`, and can leave a pocket or slivers in one near that width;
  - `bounds` answers unproven and `certify` indeterminate on a model that uses it.
- The closing reads both fields' gradients, so it breaks down where the two bodies share a flush face (the sides
  of a part extruded across, a lip's front face): it grows fins and pulls the face back. For a part that is one
  profile extruded, take the closing of the 2D profiles and extrude the result; the flush faces never meet a
  closing.
- A blend acts on whole fields: one edge cannot be picked to fillet. Arrange the booleans so the edge is the only
  seam the blend reaches.
- A field written with `length(max(d, 0))` has no gradient deep inside the solid, where every part of `d` is below
  zero. A surface put there by a shell or an offset then meshes into loose pieces. Floor the root,
  `sqrt(max(dot(m, m), 1e-30))` with `m = max(d, 0)`: the value is the same and the gradient is finite.

## Ask the field after every edit; mesh when a file is wanted

The model is its field, and the field answers at once, with no mesh. After every edit:

```sh
cad run gsl compile -t ast --no-meta -o - part.gsl > /dev/null       # it parses and links
cad run gsl render --views iso,front,top --light -o part.png part.gsl
cad run gsl eval REQUEST.json                                         # a face's place, a hole proved open
```

A request is one JSON object that names its `op` and the model; `cad run gsl eval --help` lists every op and
its fields. `--stdio` in place of the file answers one request a line, which is how to ask many. The four the
loop leans on, for a plate named `plate`:

```json
{"op": "eval", "source": "part.gsl", "exprs": ["plate"], "points": [[0, 0, 0], [25, 0, 0], [39.5, 0, 0]]}
{"op": "surface", "source": "part.gsl", "points": [[50, 0, 0]]}
{"op": "certify", "source": "part.gsl", "expr": "plate", "region": [24, -1, -7, 26, 1, 7], "threshold": 0.5}
{"op": "volume", "source": "part.gsl", "region": [-45, -30, -8, 45, 30, 8]}
```

- **`eval` is the check for a dimension.** It gives the field at each point: negative inside, positive outside,
  zero on the surface (a face reads `1e-15`). A point 0.5 mm inside a face reads -0.5 and one on a 10 mm hole's
  axis +5, so a few points say whether each face and hole is where it was asked for. `exprs` are names the
  model declares, and default to its returns.
- **`surface` finds a face.** It moves each point onto the surface and gives the normal there: `[50, 0, 0]` lands
  on `[40, 0, 0]` for a plate 80 mm long.
- **`certify` proves, where the others sample.** Its verdict is `proven` when `expr` stays at or above
  `threshold` over the whole `region`, a box `[x0, y0, z0, x1, y1, z1]`. `plate >= 0.5` over a box inside a hole
  proves the hole open; `-plate >= 0.5` over a box inside the material proves it solid, so two bodies meant to be
  one are joined. `"overSliders": true` proves it for every value of every slider at once. Keep the box about
  0.5 mm clear of the surface: nearer, and on most lattices anywhere, the verdict is `indeterminate`, which is no
  answer; measure with `eval` and `surface` there.
- **`volume` catches a gross error only, and slowly.** It needs its `region`. Its bracket is 2 to 4 percent wide
  on a plain part, and on a blended part or a lattice it is wider: it stops after 10 seconds with the bracket it
  has, `"converged": false` and `"reason": "time"` (`timeLimit` sets the seconds). Leave it out of the loop.
- **`bounds` gives the part's box when it answers `"proven": true`.** It takes about a second and needs no
  region. The box holds the whole part, thin walls included, and stands off it by at most `cellSize`: about
  0.02 mm on a plain part, so a box larger than the part by more is material where none was meant (a blend
  bulging through a face). Where an angle is folded with `atan`, as `map.patternPolarXY` does, it answers
  `"proven": false` with the reason `loose`; placed by a `map` over a list of positions, the same repeats give a
  proven, tight box. With `"proven": false` (`reason` says why: `loose`, a lattice under `normalizeField`, or an
  exact closing) the box is fitted on a coarse grid and can miss
  a wall thinner than a cell: read no size from it, and probe the faces with `eval`.

`"defs"` gives a name another value for that question alone (`"defs": "r = 6.5;"`), so a size is tried without
editing the file.

A mesh is a translation of the field for something that needs triangles: a slicer, a renderer, another program.
Make one when a file is wanted, not on every edit:

```sh
cad gsl mesh part.gsl part.glb                 # meshed, judged, and only then written
cad gsl mesh part.gsl part.glb --define r=6.5  # the same model with r = 6.5
```

`gsl` exits 0 on a mesh it got wrong: empty, open, non-manifold, inside out, cut off at its box, or missing a wall
thinner than a cell. So the mesh is judged before it is written: its triangles are measured (open and non-manifold
edges, signed volume, box) and its volume held to the bracket omega's evaluator proves for the field, with the
same values, over the `@scene` box. A mesh that fails is not written. One that passes is kept, so the same model
and values are meshed once; the proof takes from a few seconds to half a minute the first time. `--depth 10`
meshes finer (gsl's own is 9); `--json` gives every measurement. `cad gsl validate part.gsl` judges without
writing, and `--mesh part.stl` judges a mesh made another way.

| Finding | What to do |
| --- | --- |
| `no_scene` | Add `@scene(size)` as the first line. |
| `cut_off` | The part reaches the box: make `size` larger, or bound a field that never ends (a plane). |
| `volume_mismatch`, `empty_mesh` | A wall is thinner than a cell: thicken it, or mesh finer (`cad gsl mesh --depth 10`). |
| `open_edges`, `non_manifold`, `inside_out` | A mesher fault: mesh at another depth, or simplify the blend where it is. |
| `compile_failed` | gsl's own words: fix the GSL, or a value given outside its slider's range. |

Look at the field too, from two or three sides (`cad run gsl render --views iso,front,top`): holes through,
fillets on the edges meant, nothing floating. `--views` also takes a direction to look from (`1,-1,0.8`), for
a feature `iso` hides, such as the inside of a corner. The picture is the field itself, raymarched, never a
mesh of it. A fin, a gap or a floating band in it is the model's own (a piece reaching where it should not, or
a field that claims more distance than there is, as nested exact blends can), so fix the GSL; a fault in the
mesh that the picture does not show is the mesher's.

Then the GLB is a document like any other: show it, `cad glb snapshot`, and for printing always `cad glb dfm
part.glb --process printing --technology T` ([Can it be made?](../SKILL.md#can-it-be-made)). It measures what
`cad gsl mesh` does not: the real wall thickness, overhangs, what rests on the bed, and surfaces that pass
through themselves (omega-core 0.1.1's dual contouring can leave a small body inside the material of a lattice
or a thin shell, which a slicer may fill wrongly).

## Answer from the field, never from a picture

Before you state a wall thickness, a clearance, whether two parts touch, a volume or weight, or that something holds
for every value of a slider, ask the field. The source's numbers and a picture miss what blends, rotations and
slider ranges do, and the field answers exactly, often with a proof. Put the questions in a script and run it with
`cad run`:

```python
# ask.py, run with: cad run ask.py
from omega_core import Session

with Session() as gsl:
    part = gsl.document("part.gsl")
    box = (-60, -60, -60, 60, 60, 60)                       # x0, y0, z0, x1, y1, z1 in mm: the @scene box (here 120)

    # Do two of the returns overlap? Proven: never (max(a, b) >= 0 everywhere). Disproven: counter_box is where.
    c = part.certify("max(plate, bolt)", region=box, threshold=0)
    print(c.verdict, c.counter_box)

    # Is the wall at least 2 mm for every value of the sliders? over_sliders proves it over their whole ranges;
    # counter_params is the range where it fails. A plain number is a slider's value for one query: defs="t = 8.0;".
    c = part.certify("wall", region=box, threshold=2, over_sliders=True)
    print(c.verdict, c.counter_params)

    # The deepest point of a field, and where: min is a true value, the bound below it holds for a distance field.
    e = part.extremum("max(plate, bolt)", region=box, tolerance=1e-3)
    print(e.min, e.min_at, e.min_conditional_bound)

    # Values and gradients at points.
    f = part.eval(["plate", "plate.dp"], points=[(0, 0, 5)])
    print(f["plate"].values, f["plate.dp"].values)
```

- Ask over the `@scene` box, or one you know holds the whole part, never a box from the part's nominal dimensions
  or from `bounds()`, which samples and falls short. Blends bulge past the faces they join (a `unionRound` of two
  flush faces stands out by a good part of its radius), and a query whose box cuts that off answers for less than
  the part, silently.
- `certify` answers proven or disproven: report that word, and the box or the slider range of a disproof.
- `volume(region=box, relative_tolerance=0.01)` brackets the volume, but on a part with many faces it can stop at
  its budget with a bracket wider than you asked for: read `upper_mm3 - lower_mm3`. For a weight to 1%, mesh it
  (`cad run gsl compile -t stl`) and take the mesh's signed volume, and say which you did.
- Ask in the part's own names (`describe()` lists them, and its sliders): an expression is any GSL in the document's
  scope, such as `max(plate, bolt)` or `slot - 1`.

## From concept to exact geometry

GSL is for the shape: iterate on the field and its pictures (`gsl render` is fast, no mesh), mesh it once it is
settled, print it. When the part needs exact faces (a machined part, a STEP for a supplier, toleranced holes),
bake it: build it in build123d from the concept, check it against the concept's field, and keep the `.gsl` as
the concept. A lattice or an infill, which has no exact form, stays a mesh.

1. **Take the shape from the `.gsl`.** Its named values (sliders at their values) are the dimensions. Keep its
   positions, orientations and the choices it made: a web, a buried start, where a pattern begins.
2. **Make each round blend a true fillet** at the radius the file names. Where one cannot be built as written
   (a fillet "between lobe and disc" whose neighbours overlap), build the nearest true fillet and say so.
3. **Check the part against the concept's field, both ways:** `cad gsl bake part.gsl "$ID"`, the concept
   written in the part's frame (the same `--define` values the part was built from). One way, points spread by
   area over the part's surface are scored by the concept's field: below zero the concept carries material the
   part does not, above it the part carries more. The other, points on the concept's surface are measured to the
   part. Each part's largest departure is said, and where.
   - Exact features agree within 0.01 mm: flat faces, bores, holes, slots, and fillets where faces meet at
     90 degrees. A larger gap belongs where the concept's blend was nominal; report where, how large and why
     (for a blend at a known angle the expected gap can be worked out from the geometry, and should match).
   - Inside a nominal blend the concept's value is not a true distance: read the gap there from the other
     direction, the concept's surface measured to the part.
   - `--max-deviation MM` fails the bake past that departure, either way.
4. **Expect the concept to carry more material at its round blends** (below zero, one way): a round blend fills
   past a true fillet. Where the true fillet cannot follow the blend as written, the part can carry more instead
   (above zero): on a knob, an R6 fillet between two lobes bridges them and buries the disc the concept's blend
   dipped to, 1.3 mm proud of the concept there. The bake's sign says which; name each such place.
5. **The concept as baked is kept**, beside it as `part.baked.gsl`: not a model to edit. When the concept changes
   later, `cad gsl bake part.gsl "$ID" --stale` fails where the part no longer follows it and says, region by
   region, how far it moved and whether it grew or shrank. Bake that change into the part, then run `cad gsl bake`
   again to keep the new concept. A file the concept imports is not kept.

The check is what tells a faithful bake from a guess: it names every place the two differ.

## A concept among exact parts

A concept part is fitted to exact ones (a board, a motor, a bought part's STEP) through its field, with no mesh:
`cad gsl fit enclosure.gsl "$ID"`, where `$ID` is the exact parts' document (an assembly of them, an `.xbf` or a
`.step` will do). Write the concept in that document's frame, so its numbers are the assembly's.

- Each exact part's clearance is the least field over its surface, with where it is; a part that runs into the
  concept's material is an error, by its depth.
- **Clearance never shows a missing contact.** A board that should rest on four posts is "clear" when the posts
  are somewhere else. Name each contact the design means: `--contact 31.5,21.5,0`, a point on the exact part
  where it should touch the concept. A contact the part does not make is an error, with its gap.
- It judges the exact parts, not the concept's own features where no part comes near (a hole cut through a lid
  above nothing): look at the concept's picture as well.

### Concepts in the assembly's own script

An assembly's script can say which of its parts are concepts, so one document holds the exact parts and the
concepts together and the CAD Viewer shows them as one model:

```python
from cad import gsl, model

@model
def device():
    board = xbf.read("vendor/board.xbf")
    knob = bd.Pos(8, 0, 25.5) * knob_part()
    gsl.baked(knob, "knob/knob.gsl")                 # an exact part made from a concept
    enclosure = gsl.concept("enclosure.gsl", wall=2.5)  # a part that is still a concept
    return bd.Compound(children=[board, knob, enclosure], label="device")
```

- `gsl.concept(path, label=..., **values)` is a part with no shape of its own. Place it as any part
  (`.moved(bd.Location(...))`); write the concept in that part's own frame. A value is one of the concept's
  **ranged** names (`@range`), this placement's: a name without a range is refused where the concept is drawn.
- `gsl.baked(part, path, **values)` says an exact part was made from a concept. The Viewer shows it as its exact
  body, the concept, or both (the part's menu), which is where a bake's departure from its concept is seen;
  Display's **Show as** sets every baked part to Exact or Concept at once.
- The Viewer draws each concept as its field among the exact parts, at the values its part gives. It has no
  sliders: a ranged name is changed in the `.gsl`, or by the value the script gives.
- In the Viewer a part that is a concept has its own glyph in the Model tree. Clip cuts the concepts with the
  exact parts and caps them. A concept that reads `time` is played by the playbar: with the document's motion
  where it has one, else by a clip of its own, Time, ten seconds long and looping. A baked part's row has a
  button for how it is shown, and a concept's menu has **Convert to B-rep**, which starts a Quick Edit note
  asking the agent to bake it.
- With the pairs in the document, the checks take the assembly alone: `cad gsl fit "$ID"` holds every exact part
  to each part that is a concept, where the assembly places it and with its values; `cad gsl bake "$ID"` holds
  each baked part to its own concept, alone, and `cad gsl bake "$ID" --stale` says which bakes the concepts have
  moved away from. A place is then said in that concept's own frame. `--contact` and `--define` belong to the
  two-argument forms, which stay as they are.
- A part that is a concept has no exact shape: a STEP of the assembly is refused by the part's name, a snapshot
  is refused (OCCT draws no field: look at it in the Viewer), and a GLB, STL or 3MF holds the exact parts and
  says which part it leaves out. Bake the concept when the assembly must be exact.
