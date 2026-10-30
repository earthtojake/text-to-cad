# The study file

One JSON object, passed as `--study study.json` (or inline: `--study '{...}'`). Every key other
than `fixtures` and `loads` is optional. The assembly keys (`parts`, `connections`,
`contact_tolerance_mm`) are in [Assemblies](#assemblies); a study without them on a one-part
document is unchanged. Every check here runs before anything is meshed, so a malformed study fails
at once with a sentence naming the field.

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

Any other key is refused with a sentence naming the keys a study takes, and so is an unknown key
inside `material`, `mesh` or `output`.

## Units

Geometry in mm, force in N, stress, pressure and modulus in MPa, mass density in t/mm³, and
accelerations in g.

| quantity | unit in the study | example key |
| --- | --- | --- |
| length | mm | `size_mm`, `limit_mm` |
| force | N | `vector_N` |
| stress, pressure, modulus | MPa | `pressure_MPa`, `E_MPa` |
| mass density | t/mm³ (steel is 7.85e-9) | `density_t_per_mm3` |
| acceleration, gravity | g (9.81 m/s²) | `vector_g` |

## `material`

Optional. Left out, each part is solved with the material its model set, read from its `.xbf`
([materials.md](materials.md)). Given, it is the study's own numbers for every part, over the
model's:

```json
{"name": "custom", "E_MPa": 70000, "nu": 0.33, "yield_MPa": 240, "density_t_per_mm3": 2.7e-9}
```

An object takes `name`, `E_MPa`, `nu`, `yield_MPa` and `density_t_per_mm3`, nothing else, and
needs the middle three. A name alone is refused.

## `fixtures`

At least one. Each entry lists faces and a type:

| type | what the faces do | Viewer |
| --- | --- | --- |
| `fixed` (the default) | held still: every displacement component clamped | **Held at**, a grey cone into the face |
| `roller` | slide freely in their own plane, but never move along their normal (a frictionless support: a part on a greased floor, or a symmetry plane) | **Slides on**, a grey cone on rollers |

```json
"fixtures": [
  {"faces": ["bracket/face 1"], "type": "fixed"},
  {"faces": ["bracket/face 5", "bracket/face 6"], "type": "roller"}
]
```

A roller on a curved face holds each point along the face's own normal there (per facet), so a
roller on a bore lets the part turn in it and slide along it. Where two roller faces meet at an
edge, the edge's points are held along both normals. Rollers alone must still stop the part moving
and turning every way (three faces that are not parallel, like the corner of a block), or the run
says the part is not held. A part with no fixture at all has no answer, so the run refuses it.

## `loads`

At least one. Four types:

| type | fields | meaning |
| --- | --- | --- |
| `force` | `faces`, `vector_N: [Fx, Fy, Fz]` | the TOTAL force over the listed faces, spread as a uniform traction over their combined area; not zero |
| `pressure` | `faces`, `pressure_MPa` | a normal pressure on the listed faces, positive pushing into the part; not zero |
| `gravity` | `vector_g: [gx, gy, gz]`, no `faces` | the part's own weight: every bit of it is pulled along `vector_g`, in g (`[0, 0, -1]` is Earth's gravity down -Z) |
| `acceleration` | `vector_g: [ax, ay, az]`, no `faces` | the part is accelerated by `vector_g`, in g, so it feels an inertial load the opposite way (`[5, 0, 0]`: speeding up at 5 g in +X pushes the part toward -X) |

`gravity` and `acceleration` act on the whole volume (of every part, in an assembly) and need a
density greater than zero: a material object must give `density_t_per_mm3`, and a model's
material its density, or the study is refused with a sentence saying so. Their total (mass times
acceleration) joins the applied force in the summary's `applied_force_N`, so the reactions still
balance it. More in [linear-static.md](linear-static.md#body-loads-gravity-and-acceleration).

A load never reaches the part through a face that is held: a load on a `fixed` face, or a pressure
on a `roller` face (which a roller holds along its normal), is refused before the solve, naming the
load and the fixture, however each names the face. A study that no load reaches anywhere (its peak
stress zero) is refused too, rather than passed.

Remote loads, bearing loads, bolt preloads and moments are not in this version; approximate a
moment with a pair of opposite forces on two faces.

## Faces

Face references are the engine's refs, the ones the Viewer copies and `cadgen inspect` reads:
`bracket/face 17` is face 17 of the part `bracket` (`face 17` alone in a one-part document), and a
face the document names is named by its name (`bracket/f:plate.relief.3`). A reference the user
selected arrives after its document's path (`/work/bracket.step#bracket/face 17`); both forms are
accepted, and the path must name the document being solved. `cadgen fea faces part.step` prints every face
with its area, centre, surface type and a hint. In a one-part study every face must belong to the
same part occurrence (an assembly's may be on any part).

A face number is a position in the saved document: when the model is edited and the STEP re-written, a
face's number can change (a face the document names keeps its name while its feature is unchanged), so list the faces again before re-running a study on a new revision.

## Assemblies

A document of several parts is solved as an assembly, bonded where parts touch. Run
`cadgen fea parts assembly.step` first to see the parts and the pairs.

```json
{
  "parts": {
    "frame/bar.2": {"material": {"name": "custom", "E_MPa": 70000, "nu": 0.33, "yield_MPa": 240}}
  },
  "connections": [{"between": ["post", "base"], "type": "free"}],
  "contact_tolerance_mm": 0.1,
  "fixtures": [{"faces": ["base/face 9"], "type": "fixed"}],
  "loads": [{"faces": ["post/face 6"], "type": "force", "vector_N": [1000, 0, 0]}]
}
```

- `parts`: the study's own numbers for a part, keyed by its ref (`frame/bar.2`) or by its name;
  the same object as `material`. A part left out takes the study's `material` if it has one, else
  its model's; a part with neither is refused, naming it. A name that two parts share is refused:
  use a ref. A part named twice is refused.
- `connections`: optional overrides, `{"between": [A, B], "type": ...}` with `bonded` or `free`.
  Without it every pair that touches within the tolerance is bonded. `bonded` needs the pair to
  touch within the tolerance; `free` leaves them unjoined (their faces stay separate and may not
  pass load). A `free` pair that is still joined through other bonded parts is refused. Parts that press
  and slide, and bolts, are not in this version.
- `contact_tolerance_mm`: default 0.1. Faces this close are touching; a gap within it is closed to
  bond the pair, and so is an overlap no thicker than it (an interference; a `gap_closed` finding
  says which). A thicker overlap is never bonded. It is set here alone: `cadgen fea parts` lists
  against the 0.1 mm default and prints each near miss's gap, which is what to set it from.
- Faces: `post/face 23` is face 23 of the part `post`; faces may be on any part. A face that
  another part only partly covers (a plate's top with a post standing on it) holds or loads its
  exposed area; a face wholly covered by a bonded joint is refused before the solve. At least one
  part must be fixed, and every part must reach it through bonded neighbours (`not_connected`
  error otherwise).

## `mesh`

`size_mm` is the target element size. Omitted, it is a fortieth of the part's bounding diagonal.
Halving it roughly multiplies the run time by eight; a first run at the default, then one
refinement to confirm the peak, is the usual pattern. Elements are quadratic tetrahedra (CalculiX's C3D10).

`refine` meshes balls finer than the rest, where a small detail decides the answer (two curved
parts touching, a sharp notch):
`"mesh": {"size_mm": 3, "refine": [{"center_mm": [0, 0, 0], "radius_mm": 2, "size_mm": 0.3}]}`.
Each ball is meshed at its `size_mm` within `radius_mm` of `center_mm`, graded to `size_mm` outside
it. Keep a ball small: a large one at a fine size is refused, as too many local sizes to place.

When the safety factor comes out under 3, the run meshes again finer and solves again by itself:
half the element size (and half at fillets and holes, where the curvature sets the size), less where
that would pass 150 000 degrees of freedom, and up to 250 000 only when 150 000 leaves no
meaningfully finer mesh: CalculiX's direct solver needs several GB of memory there. A model already
too big for a finer solve keeps its first answer, with a warning that its convergence is unchecked.
A first solve is never refused for its size; past 150 000 degrees of freedom it warns that it will
be slow. The finer solve is the one written; the result's `refined` records both sizes and peaks.

## `output`

`deformation_scale` multiplies the displacement baked into the GLB so that a small deflection is
visible. `"auto"` shows the largest displacement as 5 % of the part's size; a number fixes it (`1`
shows the true deformed shape). The result's summary records the scale used.

## `margin`

The safety factor against yield the part should keep, and the one the stress check holds it to (said
here alone: the check takes none of its own). Omitted, 2. Below 1 is refused (a part that
yields has no margin). A result under it, but above 1, is a `low_margin` warning; below 1 is a
`yields` error. Raise it for polymers, fatigue or a part whose failure hurts someone; lower it only
when the user says the load is known exactly.

## `checks`

What the result is judged by; pick them from what the user asked. Optional; left out, the stress
check alone. cadgen evaluates every check on the written solve and writes each result (`kind`,
`label`, `value`, `limit`, `unit`, `ratio` = value over limit, `close_at`, `status` of `fails`,
`close` or `passes`, and `where`, the face and point of the worst value) into the summary
(`summary.checks`), the GLB (`extras.checks`) and the CLI lines. The Viewer's verdict says how many
fail and how much of the load the weakest takes, then one row per check, worst first; its load
slider scales them all (stress and displacement are linear in the load).

| `kind` | judges | keys |
| --- | --- | --- |
| `stress` | peak von Mises against each part's yield (an assembly's weakest part): fails under a safety factor of 1, close under the study's [`margin`](#margin) | `label` |
| `displacement` | the largest displacement over the whole model, or over `faces` (they may span parts), against `limit_mm`: fails past it, close within a tenth of it (the model's own accuracy) | `limit_mm` (required, > 0), `faces` (face refs, resolved like the fixtures'), `label` (the user's words, "Tip sag") |

"Will it break", "is it strong enough": `stress`. "How much does it sag or deflect", or a
stiffness spec: a `displacement` check with their limit on the faces they mean, labelled in their
words; keep `stress` too unless they only care about stiffness. At most one `stress` check; an
empty list is refused (leave `checks` out for the stress check alone), and so is an unknown `kind`
or key. A failing displacement check is an error finding ("'Tip sag' moves 2.1 mm, more than the
0.5 mm allowed"); the stress check's findings are the yields and margin findings already made.

## What comes out

`cadgen fea solve part.step OUT` writes the GLB `OUT` names (which must end in `.glb`), and nothing
else unless asked:

- `OUT`: the boundary surface, deformed and coloured by von Mises (blue low, red high); the value
  itself rides along as the `_VON_MISES` vertex attribute, and the mesh `extras` carry the field,
  units, range and deformation scale, the `findings` and `checks`; for an assembly also `parts`,
  `connections` and a per-vertex `_PART` index beside `_FACE`.

The numbers are the result's (`--json`): the study as given, the material, the resolved faces, the
summary (max von Mises nodal and at the integration points, safety factor, max displacement and its
location, applied and reaction forces; for an assembly also `parts`, one entry per part with its
material, peak stress, safety factor and displacement, and the weakest part's name and peak; and
`checks`, each check judged), per-fixture reactions, mesh statistics (naming the mesher and the
solver, `"solver": "calculix 2.23 (C3D10)"`, and `straightened`, the elements made straight so
CalculiX could solve them: [Mesh](linear-static.md#mesh)), timings and warnings, the `findings`, and `refined`:
the first and the finer solve's element size and peak when the run solved twice, else `null`. For
an assembly it also records `connections` (each joint: parts, type, area, gap, `interference_mm`
when the parts overlapped by no more than the tolerance and were bonded, interface faces) and
`overlaps`.

With `--vtu`, a `.vtu` beside `OUT`: the volume mesh with displacement and von Mises point data, for
ParaView.

Each file is written under a temporary name and moved into place only once every one is written: a
run that fails writes nothing, and the previous result stays as it was. A solve whose reactions do
not balance the applied load is such a failure: it is refused, never written with a warning.

`ok` (and the exit code) follow the validators' rule: an error blocks. A result with an error
finding (it yields, a check fails) is `ok: false` and the command exits 1, with the GLB written all
the same: the solve is right, and the part is unfit to use. A study stopped before the solve (a
part nothing holds) is `ok: false` with no GLB (`glb: null`). Warnings never block.

For an assembly the summary mixes two scopes. `yield_MPa` and `safety_factor` are the weakest
part's (the part named by `weakest_part`, whose own peak is `weakest_part_peak_MPa` at
`weakest_part_peak_at_mm`). `max_von_mises_MPa`, `max_von_mises_gauss_MPa`, `max_von_mises_at_mm`
and `max_displacement_mm` span the whole assembly: the highest stress can sit in a stronger part,
so `yield_MPa` over `max_von_mises_MPa` is not the safety factor. Quote the weakest part's peak
with its safety factor, and each part's own numbers from `parts`.
