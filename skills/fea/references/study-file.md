# The study file

One JSON object, passed as `--study study.json` (or inline: `--study '{...}'`).
Every key other than `material`, `fixtures` and `loads` is optional.

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
  "output": {"deformation_scale": "auto"}
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
its area, centre, surface type and a hint. Every face in one study must
belong to the same part occurrence.

Selectors are positions in the saved document. When the model is edited and
the STEP re-written, a face's number can change; list the faces again before
re-running a study on a new revision.

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

## What comes out

`cadgen fea solve part.step` writes two files beside the part, or at the `OUT`
path you give (which must end in `.glb`) plus its `.json` twin:

- `part.fea.glb` — the boundary surface, deformed and coloured by von Mises
  (blue low, red high); the value itself rides along as the `_VON_MISES`
  vertex attribute, and the mesh `extras` carry the field, units, range and
  deformation scale.
- `part.fea.json` — the study as given, the material, the resolved faces,
  the summary (max von Mises nodal and Gauss-point, safety factor, max
  displacement and its location, applied and reaction forces), per-fixture
  reactions, mesh statistics, timings and warnings.
- `part.fea.vtu` with `--vtu` — the volume mesh with displacement and von
  Mises point data, for ParaView.
