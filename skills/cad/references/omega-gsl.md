# Implicit models in GSL (omega)

GSL is the language of [omega-core](https://github.com/Gradient-Control-Laboratories/omega-core), Gradient Control
Laboratories' toolchain for implicit (signed-distance) models: a part is a field, negative inside, and booleans,
blends, lattices, shells and offsets are arithmetic on fields. It is good at what B-rep modelling is bad at:
smooth blends between any two shapes, gyroid and beam lattices, conformal infill, variable thickness, organic
forms. Its output is a mesh (STL), never a STEP: a part that has to be machined, toleranced or exported as exact
geometry is remodelled in build123d once its shape is settled.

Use it when the request asks for GSL or omega, works on an existing `.gsl`, or wants a lattice, an infill or a
blended organic shape for 3D printing. build123d stays the default for everything else.

## The tool

`gsl` comes with the `omega` integration, `cad[omega]` (the `omega-core` wheel: macOS and Linux, no Windows
build). `cad run gsl ...` installs it on first use and runs it as it is:

| Task | Command |
| --- | --- |
| The language reference, before writing GSL | omega-core's [language specification](https://github.com/Gradient-Control-Laboratories/omega-core/blob/v0.1.1/doc/gsl_lang_spec_current.md) and [standard library](https://github.com/Gradient-Control-Laboratories/omega-core/tree/v0.1.1/stdlib/builtin) at the pinned release |
| Check it parses and links | `cad run gsl compile -t ast --no-meta -o - part.gsl > /dev/null` (silent when it is fine; errors name the line) |
| Mesh a model | `cad run gsl compile -t stl -o part.stl part.gsl` |
| The mesh as GLB or 3MF | `cad stl export part.stl part.3mf` |
| Picture the field, no mesh | `cad run gsl render --views iso,top --light -o part.png part.gsl` |
| Ask the field (values, extrema, volume, proofs) | `cad run gsl eval REQUEST.json`, or `omega_core.Session` in a script run with `cad run` |
| Check the mesh | `cad omega check part.gsl` |

`gsl compile`'s defaults are the right ones: dual contouring (`--algo mdc`, flat faces flat and sharp edges sharp),
octree depth 9 (`--subdivision`), in the `@scene` box. Do not pass `--bbox auto`: its box is a fit by sampling,
which misses features thinner than its cells (a 0.4 mm fin 30 mm long is cut off near its root, and `gsl` exits
0). Keep dual
contouring over `--algo marching-cubes`, which rounds sharp edges and can leave small holes in a concave wall,
such as a hollow part's cavity.

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
  features; `cad omega check` refuses a model without one.
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
- The `lattice` package has the lattices: `lattice.solidify(tpms.gyroid([8, 8, 8]), 0, 1.0)` is a 1 mm gyroid
  sheet, `lattice.solidify(beam.octet([8, 8, 8]), 0.8)` octet struts of 0.8 mm radius; a `wall` that is a field
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
- `remap(shape, q)` reads `shape` at the point `q` and drops its bounds; `transform.translate`, `transform.rotateX`
  and the rest move a shape and keep them.
- `@range(lo, hi) name = value;` makes a top-level number a slider: make a part's driving dimensions sliders.
  `gsl eval`'s `describe` lists them, and a query's `defs` (`"t = 8.0;"`) sets one for that query alone.
- Booleans are `min` (union), `max` (intersect) and `max(a, -b)` (subtract), each with blended forms
  (`unionRound`, `intersectChamfer`, ...).

## Idioms for mechanical parts

```gsl
@scene(120, 10)
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

Shell a solid with `shell(d, thickness)`; grow it with `d - r` and shrink it with `d + r`. Patterns are
`remap(shape, map.patternPolarXY(n))` and `map.patternRepeatXY([dx, dy])`. Fasteners, threads, gears and joints
are `fastener.*`, `thread.*`, `gears.*` and `joint.*`; `gsl compile` names a function's arguments when a call is
wrong.

| Need | Call |
| --- | --- |
| A hole, feature by feature, from its mouth at `zTop` | `drill.hole([...], zTop)` of `drill.thru(d)`, `drill.blind(d, depth)`, `drill.bore(d, depth)`, `drill.chamfer(d, leg)`, `drill.countersink(d, included)` (the angle in radians: `90 * 3.141592653589793 / 180`), `drill.tap(major, pitch, depth)`, `drill.slot(d, centers, ang)` |
| A screw's hole, to ISO 273 `fit` (`fastener.fitFine`, `fitMedium`, `fitCoarse`) | `fastener.clearanceHole(m, fit)`, `fastener.countersunkHole(m, fit)` (ISO 10642), `fastener.tappedHole(m, shankLength)` |
| Place it | a hole by `map.axisAt(point, outwardNormal)`; a screw by `fastener.seatedAt(seat, shankDir)` |
| Hollow | `shell(d, thickness)`, or `shell(d, thickness, bias)`: bias -1 inward to +1 outward |

## Blends and fillets

What a blend makes decides whether a build123d remodel can match the concept:

- `unionRound(a, b, r)` is a round fillet of radius `r` only where two exact distance fields meet at 90 degrees, a
  boss standing on a plate. Where the faces meet at another angle it departs from a fillet: by about 1.2, 2.5 and
  5.2 mm at 60, 45 and 30 degrees for `r = 3`.
- Besides its bulge along flush faces (above), it raises bumps where a face hidden inside either body comes within
  `r` of the surface. For an L-corner, union sharply and add the fillet as its own solid, as in the idioms.
- For a fillet that keeps its radius at any angle, use the closing of the two bodies with exact distance fields:
  `unionRoundExact(() { return a - r; }, () { return b - r; }) + r`. A max of planes is exact only on its faces;
  write a rectangle as `m = max([qx, qy], 0);` then `sqrt(max(dot(m, m), 1e-30)) + min(max(qx, qy), 0)`. On a
  curved seam it is slightly fuller than a rolling-ball fillet (about 0.08 mm for `r = 3` on a 12 mm boss), and it
  fills any concave gap narrower than `2r`.
- The closing reads both fields' gradients, so it breaks down where the two bodies share a flush face (the sides
  of a part extruded across, a lip's front face): it grows fins and pulls the face back. For a part that is one
  profile extruded, take the closing of the 2D profiles and extrude the result; the flush faces never meet a
  closing.
- A blend acts on whole fields: one edge cannot be picked to fillet. Arrange the booleans so the edge is the only
  seam the blend reaches.
- A field written with `length(max(d, 0))` has no gradient deep inside the solid, where every part of `d` is below
  zero. A surface put there by a shell or an offset then meshes into loose pieces. Floor the root,
  `sqrt(max(dot(m, m), 1e-30))` with `m = max(d, 0)`: the value is the same and the gradient is finite.

## Check it, every time

`gsl` exits 0 on a mesh it got wrong: empty, open, non-manifold, inside out, cut off at its box, or missing a wall
thinner than a cell. So after every edit:

```sh
cad omega check part.gsl                      # meshes it as gsl compile does, and judges that mesh
cad omega check part.gsl --mesh part.stl      # judges the mesh you wrote instead
```

It compiles the model, measures the mesh (triangles, open and non-manifold edges, signed volume, box) and holds its
volume to the bracket omega's evaluator proves for the field over the `@scene` box. The volume proof takes from a
few seconds to half a minute. `--json` gives every measurement.

| Finding | What to do |
| --- | --- |
| `no_scene` | Add `@scene(size)` as the first line. |
| `cut_off` | The part reaches the box: make `size` larger, or bound a field that never ends (a plane). |
| `volume_mismatch`, `empty_mesh` | A wall is thinner than a cell: thicken it, or mesh finer (`--subdivision 10`) and check that mesh with `--mesh`. |
| `open_edges`, `non_manifold`, `inside_out` | A mesher fault: mesh at another depth, or simplify the blend where it is. |
| `compile_failed` | gsl's own words: fix the GSL. |

Look at the field too, from two or three sides (`cad run gsl render --views iso,front,top`): holes through,
fillets on the edges meant, nothing floating. The picture is the field itself, raymarched, never a mesh of it. A
fin, a gap or a floating band in it is the model's own (a piece reaching where it should not, or a field that
claims more distance than there is, as nested exact blends can), so fix the GSL; a fault in the mesh that the
picture does not show is the mesher's.

Then the STL is a document like any other: show it, `cad stl snapshot`, and for printing always `cad stl dfm
part.stl --process printing --technology T` ([Can it be made?](../SKILL.md#can-it-be-made)). It measures what
`cad omega check` does not: the real wall thickness, overhangs, what rests on the bed, and surfaces that pass
through themselves (omega-core 0.1.1's dual contouring can leave a small body inside the material of a lattice
or a thin shell, which a slicer may fill wrongly).

## From concept to exact geometry

GSL is for the shape: iterate on the field and its pictures (`gsl render` is fast, no mesh), check the mesh, print
it. When the part needs exact faces (a machined part, a STEP for a supplier, toleranced holes), remodel it in
build123d from the dimensions the GSL settled, and keep the GSL as the concept. A lattice or an infill, which has
no exact form, stays a mesh.
