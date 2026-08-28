# Blender/CAD styling handoff

Status: bounded feasibility workflow. Blender output is concept/reference-only.
The verified CAD checkpoint remains the engineering authority.

## Coordinate and file contract

- Coordinates are millimetres in the CAD frame: `+X` rearward, `+Y` driver
  side, `+Z` up. The origin is vehicle centreline at the forward edge of the
  bed-rail mounting plane.
- In Blender use Metric units, `Unit Scale = 0.001`, and
  `Length = Millimeters`. Enter CAD millimetres directly as Blender coordinate
  values; do not rotate, mirror, centre, or auto-scale on import.
- Exchange editable styling profiles as UTF-8 JSON using
  `interchange/reference_only/cad_to_blender_stations.json` as the schema:
  explicit units/axes/origin, immutable source checkpoint, named stations, and
  ordered world-space `[x,y,z]` points. Keep section names and `x_mm` values.
- A CAD tessellation may accompany the JSON as a named OBJ visual scaffold.
  OBJ has no unit metadata, so it is invalid without an adjacent JSON sidecar
  carrying this contract. Import/export it at scale `1.0`, clamp disabled,
  Forward Axis `Y`, Up Axis `Z`, with no transform application; this preserves
  numeric XYZ while the project contract gives those axes their vehicle
  meaning. It is not editable fitment geometry.
- Return the styled result primarily as the same sparse JSON section/profile
  format: a small, deliberate set of closed sections and any named longitudinal
  character lines. CAD rebuilds controlled splines/surfaces from those curves.
- Only when curves cannot describe the proposal, return one clean, manifold,
  watertight OBJ plus its JSON sidecar as a tracing/reference fallback. Never
  convert a dense Blender mesh directly to STEP or treat it as fitment truth.

Blender objects and collections use uppercase semantic names:
`REFERENCE_ONLY__DO_NOT_ENGINEER`, `STATION_00_FRONT` through
`STATION_04_REAR`, `DATUM_ORIGIN`, `X_REAR_CHECK`, `Y_DRIVER_CHECK`,
`Y_PASSENGER_CHECK`, and `Z_UP_CHECK`. New styling curves should start with
`STYLE_`; engineered/interface-like names such as `MOUNT`, `SEAL`, `FLANGE`,
`HATCH`, and `KEEP_OUT` are reserved for CAD.

## Round-trip acceptance

Run `blender --background --python
interchange/reference_only/make_axis_scale_proof.py`. The script creates
`axis_scale_roundtrip_proof.blend` and `axis_scale_roundtrip_result.json`.
Accept a transfer only when all of the following hold:

1. The Blender scene reports Metric, unit scale `0.001`, millimetres, and the
   exact axis/origin strings above.
2. Station-profile object transforms are identity. The five datum-marker
   locations read exactly `(0,0,0)`, `(1462,0,0)`, `(0,865,0)`,
   `(0,-865,0)`, and `(0,0,760)` mm, within `0.01 mm`.
3. Station X coordinates remain `0`, `321.64`, `760.24`, `1140.36`, and
   `1462 mm`; every returned profile is closed and stays in its named X plane.
4. Point-by-point JSON → Blender → JSON error is at most `0.01 mm`, with no
   axis swap, sign flip, centring, or object-level scale.
5. CAD source checks still pass. The authoritative STEP tracked at
   `outputs/step/R1T_TOPPER_ASSEMBLY.step` must retain its pre-spike Git blob
   unless a separately reviewed CAD change explicitly replaces it.

## Authority boundary

Blender may edit only the aesthetic exterior silhouette and visual character
lines. CAD remains authoritative for units, axes, vehicle/bed/cab datum,
mounting plane, measured or scan-derived surfaces, keep-outs, thickness,
flanges, seals, hatches and kinematics, hardpoints, tooling, clearances,
manufacturing geometry, and every validation claim. The five supplied profiles
are estimated styling scaffolds, not measured vehicle sections. A future CAD
worker must review and rebuild accepted styling curves; importing them does not
promote their provenance or establish production readiness.

The proof uses only project-authored numeric station data. It contains no
third-party mesh, image, or redistributable reference asset.
