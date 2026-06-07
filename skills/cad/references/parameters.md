# CAD parameters

Read this file when designing or reviewing CAD source parameters, STEP sidecar parameters, CAD Viewer controls, or animation controls.

## Contents

- Principle
- Parameter Brief
- Naming
- Defaults And Bounds
- Derive, Do Not Drift
- Features And Refs
- Animations
- Controls
- Validation
- Common Failure Patterns

## Principle

Parameters are part of the model contract. A good parameter makes design intent explicit, maps to named geometry or motion, stays inside a valid range, and gives both users and LLMs enough context to predict what changing it will do.

Prefer parameter logic that preserves the mechanism or part constraints over logic that only looks plausible from one camera angle.

## Parameter Brief

Before coding, write a compact internal parameter brief:

- What geometry or motion each parameter controls.
- Units, defaults, min/max, step size, and whether the value is dimensionless.
- Which named features, datums, pivots, axes, faces, or local selector refs each parameter affects.
- Which values are independent inputs and which are derived from constraints.
- What validation proves the parameter is correct.

For assemblies and mechanisms, identify fixed pivots, moving pivots, link lengths, gear ratios, axes, joint limits, and branch choices before creating controls.

## Naming

Use semantic names that describe intent:

- Prefer `wallThickness`, `bearingClearance`, `hingeAngleDeg`, `lidOpen`, `gearRatio`, `linkTravel`.
- Avoid names like `offset2`, `magicScale`, `fixAngle`, `sliderA`, unless the source model itself uses a meaningful matching term.
- Encode units in names only when the value could otherwise be ambiguous, such as `angleDeg`, `durationSec`, or `clearanceMm`.
- Keep source constants, manifest feature ids, UI labels, and comments aligned enough that an LLM can trace a control to geometry.

For STEP sidecars, strongly prefer an explicit target link in the module manifest:

```js
export default {
  manifest: {
    schemaVersion: 1,
    step: {
      path: "models/path/to/model.step"
    }
  }
};
```

`manifest.step.path` must be a workspace-relative path, never an absolute path, URL, or path with `..` segments. This link is provenance for humans and tools, not a freshness contract; do not add hashes or staleness checks to STEP parameter modules. Keep the sidecar named `.<step-stem>.step.js` when it lives next to its STEP file so existing viewers can fall back to the same-filename convention if `manifest.step.path` is absent.

## Defaults And Bounds

Defaults should produce a useful, valid model or pose. Bounds should protect the model from impossible, self-intersecting, or misleading states.

- Use physically valid ranges where possible: joint limits, positive dimensions, manufacturable wall thickness, realistic clearances.
- Clamp in code even when the UI already declares `min` and `max`.
- Make `step` match the useful precision of the underlying model, not just the UI.
- Use booleans for true binary state, selects for discrete modes, colors for style-only values, and numbers only for ordered quantities.
- Keep debug parameters available when useful, but label them as inspection controls if they do not represent real design degrees of freedom.

## Derive, Do Not Drift

Compute dependent values from the real constraints:

- Use pivots, axes, centers, bounds, and measured link lengths instead of eyeballed translations.
- Compose assembly transforms around the correct local datum or joint, not around visual centers unless that is the actual design datum.
- For linkages, solve the kinematics from fixed pivots and link lengths. Do not interpolate through impossible intermediate points.
- For gears, preserve pitch-circle relationships, tooth counts, and angular ratios instead of tuning rotations by sight.
- For repeated features, derive positions from count, pitch, radius, and pattern axes.

If a parameter changes a source-level CAD generator, regenerate STEP and validate the exported geometry. If a STEP sidecar changes only viewer-time presentation, say so in labels/descriptions when ambiguity matters.

## Features And Refs

Named features are the bridge between parameters and geometry.

- Label source parts and assembly children explicitly.
- Expose sidecar `manifest.features` with stable local refs such as `#o1.2`; keep file identity in `manifest.step.path`.
- Prefer feature ids like `lid`, `hingePin`, `inputGear`, `lowerRocker`, not occurrence ids as public names.
- In code, group constants and transforms by feature role so the logic reads like the mechanism.
- Resolve and inspect refs when a parameter targets a specific face, edge, part, pivot, or assembly child.

## Animations

Animation parameters should drive the smallest real degrees of freedom and derive everything else.

- Use one normalized travel parameter for a mechanism when possible, then derive all dependent transforms from it.
- Make loops exact: the final pose must equal the initial pose, or the animation should ping-pong through a periodic function.
- Do not blend between incompatible kinematic branches. Switch branches only at a physically valid tangent, over-center, or singular pose.
- Keep hinge centers, mating faces, gear contacts, belt paths, and slider axes coincident throughout the animation.
- Separate style controls from mechanism controls: colors, visibility, highlights, clip/explode, speed, play/pause, and scrub should not alter the mechanical truth.
- Preserve source STEP/GLB material colors by default. Only override colors, add color controls, or assign viewer-time color styles when the user explicitly asks for recoloring, presentation styling, or diagnostic color coding.
- Use comments for non-obvious kinematic choices, especially branch selection, sign conventions, datum origin, and derived ratios.

For STEP sidecars, use JavaScript for live CAD Viewer interaction and Three.js hooks. Use Python/build123d as the source of truth for regenerating geometry. Python may generate `.step.js` modules, but CAD Viewer controls should not imply regeneration unless that workflow exists.

## Controls

Expose controls that make the model understandable, not every constant.

- Numeric dimensions: slider plus number input when the range is bounded and interactive; number input when the range is broad or precision-heavy.
- Angles and normalized travel: sliders with clear min/max and units.
- Visibility, enablement, and optional details: switches.
- Discrete modes: select or segmented control.
- Colors: color controls only when explicitly requested for viewer styling; otherwise keep imported material colors.
- Animation: play/pause, scrub, loop, reset, and speed controls.

Use concise labels and descriptions. A good description says what changes and what stays constrained.

## Validation

Validate parameter behavior at representative values:

- Defaults.
- Min and max.
- Mid travel.
- Boundary or branch-change poses.
- Values involved in user-reported failures.

Use deterministic checks first:

- `scripts/inspect refs --facts --planes --positioning` for scale, labels, frames, and major datums.
- `scripts/inspect frame`, `measure`, or `align` for pivots, axes, mating faces, and distances.
- Source-level assertions for derived dimensions or joint limits when practical.

Use CAD Viewer links and CAD `scripts/snapshot` review for visual semantics:

- Use CAD `scripts/snapshot` to review several parameter poses, not manual viewer or Playwright inspection.
- Compare sidecar enabled vs disabled when viewer-time presentation is involved.
- Check for disconnected hinges, drifting pivots, collisions, impossible branch blends, and looping jumps.
- Use PNGs for static parameter reviews and GIFs for motion/animation reviews.
- Convert visual concerns into measurements or explicit geometric facts before calling them fixed.

## Common Failure Patterns

- Eyeballed keyframes that violate real link lengths or mating constraints.
- A UI parameter that controls a visual transform but is named like a geometry parameter.
- Interpolating between two valid poses through invalid intermediate geometry.
- Transforming a part around its bounding-box center instead of its hinge, mate, or local frame.
- Letting a debug scale or offset create collisions outside the real design envelope.
- Using absolute paths, URLs, parent-directory escapes, or stale renamed STEP paths in sidecar `manifest.step.path`.
- Hiding a geometry issue with color, transparency, camera angle, or exploded spacing.
