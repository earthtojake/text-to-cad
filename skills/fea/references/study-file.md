# The study file

One JSON object, passed as `--study study.json` (or inline: `--study '{...}'`).
Every key other than `material`, `fixtures` and `loads` is optional.
The assembly keys (`parts`, `connections`, `contact_tolerance_mm`) are in
[Assemblies](#assemblies); a study without them on a one-part document is
unchanged.

```json
{
  "material": "aluminum-6061-t6",
  "fixtures": [
    {"faces": ["#o1.f17"], "type": "fixed"}
  ],
  "loads": [
    {"faces": ["#o1.f22"], "type": "force", "vector_N": [0, -500, 0]},
    {"faces": ["#o1.f3", "#o1.f4"], "type": "pressure", "pressure_MPa": 0.8}
  ],
  "mesh": {"size_mm": 2.5},
  "output": {"deformation_scale": "auto"},
  "margin": 2
}
```

## `material`

A name from [materials.md](materials.md), or an object:

```json
{"name": "custom", "E_MPa": 70000, "nu": 0.33, "yield_MPa": 240, "density_t_per_mm3": 2.7e-9}
```

An object may also name a table entry and override some of its fields:
`{"name": "steel", "yield_MPa": 355}`.

## `fixtures`

At least one. Each entry lists faces and a type; only `fixed` exists (every
displacement component clamped on those faces). A part with no fixture has no
answer, so the run refuses it.

## `loads`

At least one. Two types:

| type | fields | meaning |
| --- | --- | --- |
| `force` | `vector_N: [Fx, Fy, Fz]` | the TOTAL force over the listed faces, spread as a uniform traction over their combined area |
| `pressure` | `pressure_MPa` | a normal pressure on the listed faces, positive pushing into the part |

Gravity, remote loads, bearing loads, moments and bolt preloads are not in
this version; approximate a moment with a pair of opposite forces on two
faces.

## Faces

Face references are the Viewer's selectors: `#o1.f17` is face 17 of
occurrence 1. A reference the user selected arrives with its document prefix
(`part.step#o1.f17`); both forms are accepted, and the prefix must match the
document being solved. `cadgen fea faces part.step` prints every face with
its area, centre, surface type and a hint. In a one-part study every face must
belong to the same part occurrence (an assembly's may be on any part).

Selectors are positions in the saved document. When the model is edited and
the STEP re-written, a face's number can change; list the faces again before
re-running a study on a new revision.

## Assemblies

A document of several parts is solved as an assembly, bonded where parts touch.
Run `cadgen fea parts assembly.step` first to see the parts and the pairs.

```json
{
  "material": "aluminum-6061-t6",
  "parts": {
    "post": {"material": "steel"},
    "#o1.3": {"material": {"name": "custom", "E_MPa": 70000, "nu": 0.33, "yield_MPa": 240}}
  },
  "connections": [{"between": ["post", "base"], "type": "free"}],
  "contact_tolerance_mm": 0.1,
  "fixtures": [{"faces": ["#o1.1.f9"], "type": "fixed"}],
  "loads": [{"faces": ["#o1.2.f6"], "type": "force", "vector_N": [1000, 0, 0]}]
}
```

- `parts`: a material per part, keyed by occurrence ref (`#o1.2`) or by name;
  same forms as `material`. A part left out gets the default `material` and a
  `default_material` finding. A name that two parts share is refused: use a
  ref. A part named twice is refused.
- `connections`: optional overrides, `{"between": [A, B], "type": ...}` with
  `bonded` or `free`. Without it every pair that touches within the tolerance
  is bonded. `bonded` needs the pair to touch within the tolerance; `free`
  leaves them unjoined (their faces stay separate and may not pass load). A
  `free` pair that is still joined through other bonded parts is refused.
  `bolt` and `contact` are refused with "not yet".
- `contact_tolerance_mm`: default 0.1. Faces this close are touching; a gap
  within it is closed to bond the pair (a `gap_closed` finding says so).
- Faces: `#o1.4.f23` is face 23 of occurrence `#o1.4`; faces may be on any
  part. A face that another part only partly covers (a plate's top with a post
  standing on it) holds or loads its exposed area; a face wholly covered by a
  bonded joint is refused before the solve. At least one
  part must be fixed, and every part must reach it through bonded neighbours
  (`not_connected` error otherwise).
- `--occurrence REF` on the command line solves that one part alone; `parts`
  and `connections` are then ignored, with a warning.

## `mesh`

`size_mm` is the target element size. Omitted, it is a fortieth of the part's
bounding diagonal. Halving it roughly multiplies the run time by eight; a
first run at the default, then one refinement to confirm the peak, is the
usual pattern. `--mesh-size` on the command line overrides the file for one
run. Elements are always quadratic tetrahedra (`order` 2).

## `output`

`deformation_scale` multiplies the displacement baked into the GLB so that a
small deflection is visible. `"auto"` shows the largest displacement as 5 % of
the part's size; a number fixes it (`1` shows the true deformed shape). The
sidecar records the scale used.

## `margin`

The safety factor against yield the part should keep. Omitted, 2. Below 1 is
refused (a part that yields has no margin). A result under it, but above 1,
is a `low_margin` warning; below 1 is a `yields` error. Raise it for polymers,
fatigue or a part whose failure hurts someone.

## What comes out

`cadgen fea solve part.step` writes two files beside the part, or at the `OUT`
path you give (which must end in `.glb`) plus its `.json` twin:

- `part.fea.glb` — the boundary surface, deformed and coloured by von Mises
  (blue low, red high); the value itself rides along as the `_VON_MISES`
  vertex attribute, and the mesh `extras` carry the field, units, range and
  deformation scale.
- `part.fea.json` — the study as given, the material, the resolved faces,
  the summary (max von Mises nodal and Gauss-point, safety factor, max
  displacement and its location, applied and reaction forces; for an assembly
  also `parts`, one entry per part with its material, peak stress, safety
  factor and displacement, and the weakest part's name and peak), per-fixture
  reactions, mesh statistics, timings and warnings, the `findings` (also in
  the GLB's mesh `extras`) and `refined`: the first and the finer solve's
  element size and peak when the run solved twice, else `null`.
- for an assembly the sidecar also records `connections` (each joint: parts,
  type, area, gap, interface faces), and the GLB carries `parts`,
  `connections` and a per-vertex `_PART` index beside `_FACE`.
- `part.fea.vtu` with `--vtu` — the volume mesh with displacement and von
  Mises point data, for ParaView.
