---
name: dfam-check
description: Measure mesh files against Design for Additive Manufacturing (DfAM) rules and report printability findings per process (FDM, SLS, SLA/DLP, metal PBF, MJF). Use when the user asks whether a part is printable, wants overhang/wall-thickness/support analysis of an `.stl`, `.obj`, `.ply`, or `.3mf` mesh, wants a build-orientation recommendation, or wants DfAM redesign guidance before slicing with `$gcode` or regenerating geometry with `$cad`.
---

# DfAM Check

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

Use this skill to produce conservative, evidence-backed DfAM reports for mesh
files before slicing or printing. It measures geometry facts locally and
compares them against per-process design limits; it never slices, uploads, or
starts print jobs.

## Geometry Inspection

Use `scripts/dfam_tool.py` in the active project Python environment for all
geometry facts (install `requirements.txt` first — every run needs it). The tool is fact-only:
it reports measurements and never emits pass/fail or readiness statuses.
Comparisons and verdicts belong to this workflow. Do not estimate wall
thickness, overhang angles, or support volume by eye or from renders when the
tool can measure them.

```bash
python scripts/dfam_tool.py measure part.stl --angle-limit 45
python scripts/dfam_tool.py orientations part.stl --angle-limit 45
```

Set `--angle-limit` to the target process's self-supporting angle from
`references/process-limits.md` before measuring, and re-run when the target
process changes: the aggregate support-area facts are binned against it.

STEP/STP input is boundary-representation CAD, not a mesh. When the `$cad`
skill is installed, export an STL sidecar with it first, then measure the STL
here. Report that remediation instead of attempting raw STEP parsing.

## Workflow

1. Collect print intent: target process, material, layer height, and any
   machine or material datasheet the user can provide. If the process is
   unknown, measure once with the default 45° limit, then present findings
   per candidate process rather than guessing a single verdict.
2. Read `references/process-limits.md` and select the limit column for the
   target process. A user-provided machine/material datasheet overrides the
   defaults; cite whichever source is used for every comparison.
3. Run `measure` on the exact upload file. Do not inspect only a generator
   script, source CAD model, or console summary of the file.
4. Run `orientations` when the process requires supports and the measured
   support area is nonzero. Report any candidate that materially reduces
   support area, with its build-height tradeoff.
5. Compare each measured fact to the cited limit and report findings with
   restrained status labels:
   - `✅ pass`: the measured fact satisfies the cited limit.
   - `❌ fail`: a measured fact directly violates the cited limit.
   - `❓ need more info`: missing process context, unmeasured geometry,
     sampling too sparse to trust, or tool limitations.
6. Order findings by severity: watertightness first (blocks slicing for
   every process), then wall thickness, then overhangs/supports, then
   orientation and cost signals.

## Comparison

Compare only trustworthy pairs of evidence.

- Cite the limit source (process-limits table row, or the user's datasheet
  field) and the measured fact (JSON field path) for every finding.
- Treat `p05_mm` below the wall-thickness limit as a violation even when
  `min_mm` alone could be a sampling outlier; report both values.
- On an assembly, `wall_thickness` reports `body_count` and a `per_body`
  breakdown. Attribute a violation to the body it belongs to; a thin figure
  pooled across bodies is not a finding against the part as a whole.
- Do not apply support-angle findings to powder processes (SLS, MJF); the
  relevant powder-process check is trapped-volume powder escape, which this
  tool does not yet measure — report that as `❓ need more info` when
  enclosed cavities are likely.
- Do not silently rescale geometry. `scale.units_suspect` is measured from
  the bounding-box diagonal: when it is `true`, the source is probably in
  meters or inches, every down-facing face reads as resting on the plate, and
  overhang and support figures of 0.0 mean nothing. Report a unit/scale
  finding and ask the user to confirm units before comparing anything against
  a material limit.
- Support-volume ratios are coarse upper bounds; report them as cost
  signals, not hard failures, unless the user has set an explicit budget.

## Redesign Handoff

For every `❌ fail`, include a concrete, plain-language redesign instruction
with target numbers (for example "thicken the wall at [12.4, 3.0, 8.1] from
0.6 mm to ≥1.2 mm" or "chamfer the overhang at [23.3, 10.0, 52.0] to ≥45°").
When the `$cad` skill is installed, offer to apply the redesign instructions
with it and re-measure the regenerated geometry here, repeating until no
`❌ fail` findings remain. When `$cad-viewer` is installed, hand the measured
file path(s) to it so the user can inspect the findings visually.
