# The study file

One JSON object, passed as `--study study.json` or inline (`--study '{...}'`). Only `fixtures` and
`loads` are required. An unknown key, at the top or inside an entry, is refused, naming the keys
taken there. Every key names its unit: `_mm`, `_N`, `_MPa` (stress, pressure and modulus),
`_t_per_mm3` (tonnes per mm³: steel is 7.85e-9) and `_g` (9.81 m/s²).

```json
{
  "fixtures": [
    {"faces": ["bracket/face 17"], "type": "fixed"}
  ],
  "loads": [
    {"faces": ["bracket/face 22"], "type": "force", "vector_N": [0, -500, 0]},
    {"faces": ["bracket/face 3", "bracket/face 4"], "type": "pressure", "pressure_MPa": 0.8},
    {"type": "gravity", "vector_g": [0, 0, -1]}
  ],
  "mesh": {"size_mm": 2.5},
  "output": {"deformation_scale": "auto"},
  "margin": 2,
  "checks": [{"kind": "stress"}, {"kind": "displacement", "limit_mm": 0.5, "faces": ["bracket/face 22"], "label": "Tip sag"}]
}
```

## Keys

| key | meaning |
| --- | --- |
| `material` | the study's own numbers for every part; left out, each part's model material ([`material`](#material)) |
| `fixtures` | the faces held, `fixed` or `roller` ([`fixtures`](#fixtures)); at least one |
| `loads` | forces and pressures on faces, gravity and acceleration on the whole part ([`loads`](#loads)); at least one |
| `mesh` | element size and finer balls ([`mesh`](#mesh)) |
| `output` | how the result is drawn ([`output`](#output)) |
| `margin` | the safety factor to keep ([`margin`](#margin)) |
| `checks` | what the result is judged by ([`checks`](#checks)) |
| `parts`, `connections`, `contact_tolerance_mm` | an assembly ([Assemblies](#assemblies)) |

How a face is named is in [Faces](#faces); the files and the result are in
[What comes out](#what-comes-out).

## `material`

Left out, each part is solved with the material its model set ([materials.md](materials.md)).
Given, these numbers are every part's, over the model's:

```json
{"name": "custom", "E_MPa": 70000, "nu": 0.33, "yield_MPa": 240, "density_t_per_mm3": 2.7e-9}
```

`E_MPa`, `nu` and `yield_MPa` are required; `name` and `density_t_per_mm3` are optional. A name
alone is refused.

## `fixtures`

Each entry lists `faces` and a `type`:

| type | what the faces do |
| --- | --- |
| `fixed` (the default) | held still |
| `roller` | slide in their own plane and never move along their normal: a frictionless support, or the cut face of a symmetric half |

A roller on a curved face holds each point along the face's normal there, so a roller on a bore
lets the part turn in it and slide along it; where two roller faces meet, the edge is held along
both normals. Rollers alone must still stop the part moving and turning every way (three faces
that are not parallel, like the corner of a block), or the solve is refused, saying the part is
free to slide or turn.

## `loads`

| type | fields | meaning |
| --- | --- | --- |
| `force` | `faces`, `vector_N: [Fx, Fy, Fz]` | the total force over the listed faces, spread as a uniform traction over their combined area |
| `pressure` | `faces`, `pressure_MPa` | a normal pressure on the listed faces, positive pushing into the part |
| `gravity` | `vector_g: [gx, gy, gz]`, no `faces` | the part's own weight, pulled along `vector_g` (`[0, 0, -1]` is Earth's gravity with +Z up) |
| `acceleration` | `vector_g: [ax, ay, az]`, no `faces` | the part is accelerated by `vector_g`, so it is loaded the opposite way (`[5, 0, 0]`: speeding up at 5 g in +X pushes it toward -X) |

A zero force, pressure or vector is refused. `gravity` and `acceleration` act on the whole volume
of every part and need a density above zero, the material object's or the model's material's.
Their total, mass times acceleration, is part of the result's `applied_force_N`, which the
reactions balance. A drop or a braking load as a steady g-load is in
[body loads](linear-static.md#body-loads-gravity-and-acceleration).

A load on a face a `fixed` fixture holds, or a pressure on a `roller` face (held along its
normal), goes into the support and never reaches the part: it is refused, naming the load and the
fixture. So is a study no load reaches at all (its peak stress zero).

There are no remote loads, bearing loads, bolt preloads or moments: a moment is two opposite
forces on two faces a known distance apart, and a force on a hole's cylindrical face approximates
a pin or bolt load.

## Faces

A face ref is the one the setup lists, the viewer copies and `cad <type> inspect` resolves:
`bracket/face 17` is face 17 of the part `bracket` (`face 17` alone in a one-part document), and a
face the document names goes by its name (`bracket/f:plate.relief.3`). A ref copied from the
viewer comes after its document's path (`/work/bracket.step#bracket/face 17`), which must name the
document being solved.

A name stays with its face while the feature that made it is unchanged, and is refused once it
names nothing. A number is a position in the saved document, which an edit moves.

## Assemblies

A document of several parts is solved as one, bonded where its parts touch; the setup
(`cad step solve assembly.step`) lists the parts and the pairs. This one is a `base`, two posts
and a `beam` across them:

```json
{
  "parts": {
    "beam": {"material": {"name": "custom", "E_MPa": 70000, "nu": 0.33, "yield_MPa": 240}}
  },
  "contact_tolerance_mm": 0.1,
  "fixtures": [{"faces": ["base/face 5"], "type": "fixed"}],
  "loads": [{"faces": ["beam/face 3"], "type": "force", "vector_N": [0, 300, 0]}]
}
```

- `parts`: one part's own material, keyed by the part's ref (`stand/post.2`) or its name; the
  object is [`material`](#material)'s. A part left out takes the study's `material` if there is
  one, else its model's, and one with neither is refused, naming it. A name two parts share is
  refused: use the ref.
- `connections`: overrides of the default, which bonds every pair that touches within the
  tolerance: `[{"between": [A, B], "type": "free"}]`, each part by its ref or name. A `free` pair
  is left unjoined and passes no load, so each side needs its own way to a fixed face. A pair still
  joined through other bonded parts cannot be freed alone, and `bonded` needs the pair to touch
  within the tolerance: both are refused.
- `contact_tolerance_mm` (default 0.1): faces this close touch. A gap within it is closed to bond
  the pair, and so is an overlap no thicker than it (an interference); a `gap_closed` finding says
  which. A thicker overlap is never bonded. The setup lists pairs at the default and prints each
  near miss's gap, which is what to set it from.
- Faces may be on any part (`beam/face 3`). A face another part partly covers holds or loads its
  exposed area; one wholly covered by a bonded joint is refused. Every part must reach a fixed
  face through bonded neighbours, or the study stops with a `not_connected` error.

## `mesh`

`size_mm` is the largest element's size; left out, a fortieth of the bounding diagonal. Halving it
multiplies the element count by about eight.

`refine` meshes balls finer than the rest, where a small detail decides the answer (two curved
parts touching, a sharp notch):
`"mesh": {"size_mm": 3, "refine": [{"center_mm": [0, 0, 0], "radius_mm": 2, "size_mm": 0.3}]}`.
Each ball is meshed at its `size_mm` within `radius_mm` of `center_mm`, graded to the mesh's size
outside it. A large ball at a fine size is refused, as too many local sizes to place.

A safety factor under 3 makes the run mesh finer and solve again by itself:
[Mesh](linear-static.md#mesh).

## `output`

`deformation_scale` multiplies the displacement drawn in `result.glb` and the pictures, so that a
small deflection shows. `"auto"`, the default, draws the largest displacement as 5 % of the part's
size; a number fixes it (`1` is the true deformed shape). The result records the scale used.

## `margin`

The safety factor against yield the part should keep, and the one the stress check holds it to.
Left out, 2; below 1 is refused. A result under it is a `low_margin` warning, and under 1 a
`yields` error.

## `checks`

What the result is judged by; left out, the stress check alone. Each check's result is in the
result's `checks` and the printed lines: `kind`, `label`, `value`, `limit`, `unit`, `ratio` (value
over limit), `close_at`, `status` (`fails`, `close` or `passes`) and `where` (the face and point of
the worst value). The model is linear, so a `ratio` of 0.5 holds at twice the load.

| `kind` | judges | keys |
| --- | --- | --- |
| `stress` | the peak von Mises against yield, in an assembly the weakest part's: fails under a safety factor of 1, close under the study's [`margin`](#margin) | `label` |
| `displacement` | the largest displacement over `faces` (of any parts), else over the whole model, against `limit_mm`: fails past it, close within a tenth of it | `limit_mm` (required, above 0), `faces`, `label` (the person's words: "Tip sag") |

At most one `stress` check, and an empty list is refused. A failing displacement check is a
`displacement_over_limit` error ("'Tip sag' moves 2.91 mm, more than the 0.5 mm allowed").

## What comes out

`--out DIR` names the folder, made when missing; nothing else in it is touched. A study that is
refused or stopped writes nothing and leaves an earlier solve's files as they were. A solve
removes the files of an earlier one that it does not write (its pictures, its deck), so the folder
never mixes two solves. Beyond what SKILL.md's table says of each file:

- `result.glb`: the deformed boundary surface, coloured by von Mises through a ramp texture (blue
  low, red high). Its vertices carry the raw fields as attributes (`_VON_MISES`, `_DISPLACEMENT`
  in glTF metres, `_FACE`, an assembly's `_PART`), and the mesh's `extras` say what each is, with
  the deformation scale, the face refs, the study and its checks.
- `result.vtu`: VTK's unstructured grid, binary, which meshio, PyVista and ParaView read as it is.
- `stress.png`, `displacement.png`: each has a colour bar under it, from 0 to the field's peak.
- `ccx.inp`: the nodes, the C3D10 elements, the materials, the supports and the nodal loads of
  the solve written (the finer one, where there were two).

`result.json` is what `--json` prints: `ok`, `path`, `summary`, `findings` (each with its
`severity`, `code`, `message`, `location` and `hint`), `written` (the files) and `measurements`.
Beside the figures SKILL.md names, `measurements` holds `max_von_mises_gauss_MPa`,
`max_displacement_at_mm`, `applied_force_N` and `reaction_force_N`, `deformation_scale`, `checks`,
`mesh` (`elements`, `nodes`, `dofs`, `size_mm`, `solver` and `straightened`:
[Mesh](linear-static.md#mesh)), `refined` (`from_size_mm`, `from_max_von_mises_MPa`, `size_mm` and
`max_von_mises_MPa`, or `null` when the run solved once), `material`, `fixtures` (each with its
`reaction_N`), `study` (as given), `named_faces` (each face it named) and `timings`.

- `safety_factor` is `yield_MPa` over the nodal peak, cut to three decimals and never rounded up.
- An assembly adds `weakest_part`, `weakest_part_peak_MPa`, `weakest_part_peak_at_mm`, `parts`
  (each part's `ref`, `name`, `material`, `yield_MPa`, `peak_MPa`, `peak_gauss_MPa`, `peak_at_mm`,
  `safety_factor` and `max_displacement_mm`), `connections` (each joint's `between`, `refs`,
  `type`, `area_mm2`, `gap_mm`, `interference_mm` and `faces`) and `overlaps`. Its `yield_MPa` and
  `safety_factor` are the weakest part's, against that part's own peak, and its `max_...` figures
  span every part.
- A study stopped by `not_connected` prints a result with `ok: false`, that finding, no
  `measurements` and `written: []`. A refused study prints
  `{"ok": false, "error": "...", "reason": "failed"}`. Both exit 1 and write nothing.
