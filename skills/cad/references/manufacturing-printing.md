# 3D printing

The evidence, the rules, the review and how to check a redesign are SKILL.md's
[Can it be made?](../SKILL.md#can-it-be-made), the same for every process; this is what is particular
to additive processes.

Slicing and sending a print to a printer is the print3d skill's ($print3d).

## Process limits

Design-rule limits per additive process, for comparison against the facts
`cad <type> dfm --process printing` measures. Values are conservative defaults
from published process design guides and consistent with ISO/ASTM 52910
(general DfAM guidance) and ISO/ASTM 52911-1 (laser powder bed fusion of
metals). Machine-, material-, and parameter-specific datasheets override
these defaults when the person provides them — cite whichever source is used.

| Limit | FDM/FFF | SLS (PA12) | SLA/DLP | PBF-LB metal (SLM/DMLS) | MJF |
| --- | --- | --- | --- | --- | --- |
| Min supported wall (mm) | 1.2 | 0.7 | 0.5 | 0.4 | 0.5 |
| Min unsupported wall (mm) | 1.6 | 0.7 | 1.0 | 0.5 | 0.5 |
| Self-supporting angle (deg from horizontal) | 45 | n/a (powder supports) | 30 | 45 | n/a (powder supports) |
| Min hole diameter (mm) | 2.0 | 1.5 | 0.5 | 1.5 | 1.0 |
| Min positive feature (mm) | 0.8 | 0.8 | 0.2 | 0.4 | 0.5 |
| Max unsupported bridge (mm) | 10 | n/a | 5 | 2 | n/a |

Sources: Hubs FDM/SLS/SLA/metal design guides, Formlabs design guides,
HP MJF design guidelines, EOS design rules; ISO/ASTM 52910 §6 for the
category structure (feature limits §6.5, support structures §6.7).

## Interpretation notes

- **Wall thickness facts** come from ray-cast sampling, so `min_mm` is a
  sampled minimum, not an exhaustive one. Treat `p05_mm` below the limit as
  a strong violation signal even when `min_mm` alone might be an outlier.
- **Overhang facts** exclude faces resting on the build plate. For powder
  processes (SLS, MJF) the surrounding powder supports all geometry:
  support-area findings do not apply, but trapped-powder escape holes
  become the relevant check instead.
- **Support volume** is a prism upper-bound estimate for cost and
  post-processing effort, not a slicer-accurate figure. Ratios above
  ~30% of part volume usually justify reorientation or redesign for
  support-requiring processes.
- **Watertightness** (`measurements.mesh.watertight: false`) blocks slicing
  for every process and should be reported before any other finding.
- **Orientation candidates** are the six axis-aligned rotations only.
  A candidate reaching materially lower support area than the current
  orientation is a finding worth reporting with its build-height tradeoff.

## What the check measures today

`cad <type> dfm --process printing` returns measured values for **min
supported wall**, **min unsupported wall** (both from the thickness field) and
**self-supporting angle** (from the overhang map). Those rows can be compared
directly against the limits above.

**Min hole diameter**, **min positive feature** and **max unsupported bridge**
have no measured counterpart yet. Treat them the way the trapped-powder gap is
treated: report them as not checked, rather than inferring them from a render,
the bounding box, or the triangle count. A limit with no measurement behind it
is not a finding.

Wall thickness is measured per connected body. An assembly reports a
`per_body` breakdown alongside the pooled figures, because a ray crossing a
mating clearance would otherwise record the fit gap as a wall.

## Measure it

`cad <type> dfm --process printing` measures overhangs, wall thickness and support volume, and
with `--candidates` ranks the six axis-aligned build orientations beside them, in one run:

```bash
cad stl dfm part.stl --process printing --angle-limit 45
cad model dfm "$ID" --process printing --angle-limit 30 --json
cad step dfm part.step --process printing --angle-limit 45 --candidates
```

```text
OK part.stl: printing: 5497.6 mm3, 1 body(ies); overhangs under 45 deg 0 mm2; walls min 6.012, p05 10, median 10 mm; support ~0 mm3
```

The source is an `.stl`, `.3mf`, `.glb`, `.step` or `.xbf`, or a model's id, and `<type>` is its document
type: `stl`, `threemf` (`cad threemf dfm part.3mf`), `glb`, `step`, `xbf` or `model`. A STEP or an xbf is
tessellated by the engine, so there is nothing to export first. Set `--angle-limit` to the target
process's self-supporting angle ([above](#process-limits)) before measuring, and measure again when the process
changes: the overhang and support figures are binned against it. `--samples` (default 2000) is the
number of rays cast for the wall-thickness field; `--units mm|cm|m|in|ft` states an STL's units
(millimetres by default), the other types declaring their own. A mesh already held in a program is
measured with `cad.trimesh.printing(mesh)` in a check script.

`--json` prints one line, `ok`, `findings`, `summary` and `measurements`:

- `measurements.mesh`: `bbox_mm`, `volume_mm3`, `surface_area_mm2`, `triangle_count`, `watertight`,
  `body_count`, and `internal_void_count` for a cavity sealed inside a body (one body, its void
  measured with it: the skin over it is one of its walls).
- `measurements.scale`: `bbox_diagonal_mm`, `units_suspect`, `note`.
- `measurements.overhangs`: `down_facing_area_below_limit_mm2` and `_pct`, `face_count_below_limit`,
  `down_facing_angle_histogram_mm2`, and `largest_faces_below_limit`, each at its location. Faces
  resting on the plate are excluded.
- `measurements.wall_thickness`: `min_mm`, `p05_mm`, `p25_mm`, `median_mm`, `max_mm`,
  `samples_valid`, and `thinnest_samples`, each at its location; an assembly adds `body_count` and
  `per_body`.
- `measurements.support_volume`: `estimated_support_volume_mm3`, `part_volume_mm3` and
  `support_to_part_ratio_pct`, a prism from each down-facing face to the plate: a coarse upper bound.
- With `--candidates`, beside the families above: `measurements.orientations.candidates`, one row per orientation
  (`current_plus_z`, `flip_180_x`, `rot_plus_90_x`, `rot_minus_90_x`, `rot_plus_90_y`,
  `rot_minus_90_y`) with its `support_area_mm2`, `support_area_pct` and `build_height_mm`.

The check is facts only: it never compares a figure with a printer's or a material's limit, so its
`OK` is not a printable verdict. Its findings say what the figures show (warnings `overhangs`,
`not_watertight`, `units_suspect`; info `several_bodies`, `sealed_voids`, `walls_not_measured`). It exits 1 when
something was not measured: a `measurement_failed` error names the family (`wall_thickness`,
`support_volume`) and the rest are still reported; `mesh_unreadable`, `not_finite` and
`invalid_target` carry no measurements at all. Treat an unmeasured family as unverified, never as a
measurement of zero: the `measurement_failed` finding's message says why it failed, and `cad doctor
--check` says which environment the check measures in (its `trimesh` line: this installation's own, or
`cad[trimesh]`'s, made on first need, and where).

## Compare and report

1. Collect print intent: target process, material, layer height, and any machine or material
   datasheet the person can provide. If the process is unknown, measure once with the default 45°
   limit, then present findings per candidate process rather than guessing a single verdict.
2. Select the limit column for the target process from the [process limits](#process-limits). A machine or material datasheet the
   person provides overrides the defaults; cite whichever source is used for every comparison.
3. Check the exact file that will be sliced, or the model's document: never only a generator script,
   a source model the file was not exported from, or a console summary.
4. Rank orientations (`--candidates`) when the process needs supports and the measured support area
   is not zero. Report any candidate that materially reduces support area, with its build-height
   tradeoff.
5. Order findings by severity: watertightness first (it blocks slicing for every process), then wall
   thickness, then overhangs and supports, then orientation and cost signals.

Compare only trustworthy pairs of evidence:

- Cite the limit (the process-limits row, or the person's datasheet field) and the measured fact (its
  JSON field, such as `measurements.wall_thickness.p05_mm`) for every finding.
- Treat `p05_mm` below the wall limit as a violation even when `min_mm` alone could be a sampling
  outlier; report both values.
- On an assembly, attribute a wall violation to the body in `per_body` it belongs to; a thin figure
  pooled across bodies is not a finding against the part as a whole.
- Do not apply support-angle findings to powder processes (SLS, MJF). Their check is trapped-powder
  escape: a sealed cavity is said (`sealed_voids`), and an escape hole for one is not measured, so
  report that unverified.
- Do not silently rescale geometry. When `scale.units_suspect` is true the file is probably in metres
  or inches, every down-facing face reads as resting on the plate, and overhang and support figures
  of 0.0 mean nothing: report a units finding and ask the person to confirm units before comparing
  anything against a material limit.
- Support-volume ratios are coarse upper bounds: report them as cost signals, not failures, unless
  the person has set an explicit budget.

For every fail, give a concrete, plain-language redesign instruction with target numbers (for example
"thicken the wall at [12.4, 3.0, 8.1] from 0.6 mm to ≥1.2 mm" or "chamfer the overhang at
[23.3, 10.0, 52.0] to ≥45°"). When the model's source can be edited, offer to apply them and check the
regenerated part again, repeating until no fail remains.
