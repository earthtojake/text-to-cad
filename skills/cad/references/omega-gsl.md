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
| Mesh a model | `cad run gsl compile -t stl -o part.stl part.gsl` |
| Picture the field, no mesh | `cad run gsl render --views iso,top --light -o part.png part.gsl` |
| Ask the field (values, extrema, volume, proofs) | `cad run gsl eval REQUEST.json`, or `omega_core.Session` in a script run with `cad run` |
| Check the mesh | `cad omega check part.gsl` |

`gsl compile`'s defaults are the right ones: dual contouring (`--algo mdc`, flat faces flat and sharp edges sharp),
octree depth 9 (`--subdivision`), in the `@scene` box. Do not pass `--algo marching-cubes` or `--bbox auto`:
omega-core 0.1.1 writes marching cubes inside out, and its automatic box cuts off thin features.

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
