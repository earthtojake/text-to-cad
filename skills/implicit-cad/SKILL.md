---
name: implicit-cad
description: Create, edit, render, and snapshot browser-native implicit CAD `.implicit.js` and `.implicit.mjs` files using GLSL signed-distance fields, shader primitives, smooth booleans, TPMS fields, and direct CAD Viewer raymarch rendering. Experimental.
---

# Implicit CAD

Use this skill for implicit CAD models that should run directly in CAD Viewer as browser JS modules. The primary artifact is a `.implicit.js` or `.implicit.mjs`.

This skill is experimental. ALWAYS prefer conventional STEP-first CAD workflows unless the user explicitly asks for an implicit model.

## File Format

An implicit CAD file is an ES module exporting an `implicit.js/0.1.0` object. The schema source of truth lives in the bundled package at `scripts/packages/implicitjs/src/lib/implicitCad/schema.js`; `scripts/lib/implicit-cad.mjs` re-exports it as `SCHEMA` for helper-authored modules.

```js
export default {
  schema: "implicit.js/0.1.0",
  name: "rounded capsule block",
  glsl: `
float sdf(vec3 p) {
  float sphere = implicit_sphere(p, vec3(0.0), 22.0);
  float block = implicit_box_centered(p, vec3(34.0, 18.0, 18.0), vec3(0.0));
  return implicit_union_round(sphere, block, 3.0);
}

vec3 color(vec3 p, vec3 normal) {
  return mix(vec3(0.20, 0.55, 0.95), vec3(0.95, 0.45, 0.20), smoothstep(-15.0, 20.0, p.z));
}
`,
};
```

Models may also declare params and animations. Parameter definitions use the implicitjs control schema: `number`, `boolean`, `enum`/`select`, `color`, `string`, and `button`. Number, boolean, color, and button params automatically become GLSL uniforms with the same name; do not add a separate `uniforms` object. `bounds` is optional and is estimated from the SDF when omitted; add explicit bounds only when the auto estimate is too broad, too slow, or misses an unusual field. `bounds` and `render` may be JavaScript functions that receive `{ ...params, params, animation, animationState, elapsedSec, progress, t }`.

Built-in GLSL helpers use the `implicit_*` namespace, for example `implicit_sphere`, `implicit_box_centered`, and `implicit_union_round`.

```js
export default {
  schema: "implicit.js/0.1.0",
  name: "breathing orb",
  params: {
    radius: {
      type: "number",
      label: "Radius",
      min: 12,
      max: 34,
      default: 22,
      unit: "mm",
    },
  },
  animations: {
    breathe: {
      label: "Breathe",
      duration: 3,
      update({ progress, set }) {
        set("radius", 18 + Math.sin(progress * Math.PI) * 10);
      },
    },
  },
  render: { steps: 224, epsilon: 0.004 },
  glsl: `
float sdf(vec3 p) {
  return length(p) - radius;
}

vec3 color(vec3 p, vec3 normal) {
  return mix(vec3(0.10, 0.58, 0.95), vec3(1.0, 0.34, 0.12), smoothstep(-18.0, 18.0, p.z));
}
`,
};
```

Do not copy bundled helper files out of this skill. If helper functions are useful, use `scripts/lib/implicit-cad.mjs` during authoring or emit standalone GLSL into the final `.implicit.js`/`.implicit.mjs` module.

## Authoring Workflow

1. Write a natural-language modeling brief with dimensions, coordinate assumptions, procedural color intent, and visual checks.
2. Create or edit the user-specified `.implicit.js`/`.implicit.mjs` module.
3. Use `scripts/lib/implicit-cad.mjs` helpers for primitives and field composition when useful:
   - primitives: `sphere`, `circle`, `boxCentered`, `plane`, `lineSegment`, `torus`, `axis`, `cylinder`, `cylinderCapped`, `capsule`, `cone`, `coneCapped`, `coneCapsule`
   - booleans/blends: `unionSharp`, `intersectSharp`, `unionRound`, `intersectRound`, `unionChamfer`, `intersectChamfer`, `unionExp`, `intersectExp`, `unionLpNorm`, `intersectLpNorm`, `unionRvachev`, `intersectRvachev`, `difference`
   - modifiers/lattices: `shell`, `rotateAxis`, `repeatCentered`, `remapCylindrical`, `cubicGrid`, `squareHoneycomb`, `squareHoneycombReinforced`, `squareDiagonalHoneycomb`, `octetHoneycomb`, `hexagonalHoneycomb`, `triangularHoneycomb`
   - TPMS fields: `tpmsGyroid`, `tpmsSchwarz`, `tpmsDiamond`, `tpmsLidinoid`, `tpmsNeovius`, `tpmsSplitP`, `tpmsIwp`
   - shader wrappers: `distanceFunction` emits `float sdf(vec3 p)`, `colorFunction` emits `vec3 color(vec3 p, vec3 normal)`
4. Add optional `params` and `animations` for dimensions, toggles, palettes, mode switches, and animated exploration. Use param names directly in GLSL; the runtime declares matching uniforms.
5. Add optional procedural color with `vec3 color(vec3 p, vec3 normal)` when the model benefits from local material variation. Keep color values in 0..1 RGB.
6. Rely on automatic SDF bounds first. Add explicit bounds when an animated, periodic, translated, or very thin model needs tighter or more reliable framing/export sampling.
7. Run the lightweight visual verification flow below after visible geometry, color, params, animation, bounds, render, or export-affecting changes.
8. Run `node scripts/export.mjs --input <model.implicit.js> --format glb` when a mesh artifact is needed for downstream viewers, slicers, or file handoff.

## Visual Verification

Use this skill's snapshot tool as a fast visual check, not as a substitute for deterministic import/export validation. Keep the packet small and purposeful.

For simple static edits, one image is enough:

```bash
node scripts/snapshot.mjs --input models/implicit-cad/<model>.implicit.js --output /tmp/implicit-review/<model>.png
```

For topology, periodicity, thin features, Boolean blends, object identity, color, or suspected framing issues, render a small packet in one CLI call so the browser, module, and runtime model are reused:

```bash
node scripts/snapshot.mjs --job - <<'JSON'
{
  "input": "models/implicit-cad/<model>.implicit.js",
  "mode": "view",
  "render": { "sizeProfile": "simple", "frameMargin": 1.55 },
  "graphics": { "modelColors": true, "detail": 1.2, "shadows": true, "ambientOcclusion": true },
  "outputs": [
    { "path": "/tmp/implicit-review/<model>-iso.png", "camera": "iso" },
    { "path": "/tmp/implicit-review/<model>-front.png", "camera": "front" },
    { "path": "/tmp/implicit-review/<model>-top.png", "camera": "top" },
    { "path": "/tmp/implicit-review/<model>-right.png", "camera": "right" }
  ]
}
JSON
```

Add `implicitParameters` at the job level for one parameter state, or on individual outputs when the point of the review is comparing parameter variants. Use `render.frameMargin` around `1.5` when a model is close to the edge; if a snapshot still appears clipped, first check whether the source `bounds` is cutting the raymarch itself.

For animations, create a short GIF only when motion is part of the request:

```bash
node scripts/snapshot.mjs --job - <<'JSON'
{
  "input": "models/implicit-cad/<model>.implicit.js",
  "mode": "animate",
  "outputs": [{ "path": "/tmp/implicit-review/<model>-animation.gif" }],
  "implicitAnimation": { "activeId": "<animation-id>", "durationSeconds": 3, "fps": 12 }
}
JSON
```

Review the resulting PNG/GIF for centered framing, no top/bottom/side clipping, expected silhouette and topology, visible parameter differences, GLSL-defined colors, no unexpected holes/gaps, and smooth enough edges for the requested graphics settings. If the snapshot reveals a mismatch, fix the implicit source or bounds and rerun only the relevant packet.

## Handoff

After completing implicit CAD work that creates or modifies `.implicit.js`, `.implicit.mjs`, `.glb`, `.stl`, or `.3mf` artifacts, you must ALWAYS hand the explicit file path(s) to `$cad-viewer` when that skill is installed. `$cad-viewer` must start CAD Viewer if it is not already running and return link(s) to the relevant created or updated file(s); include those live viewer link(s) in the final response. If `$cad-viewer` is unavailable or startup fails, report that instead of silently omitting the handoff.

When verification snapshots are generated, also include the saved PNG/GIF snapshot(s) in the final response. If no snapshot applies, or if snapshot generation fails, say why and report the deterministic validation that still ran.

## Snapshot Tool

From this skill directory:

```bash
node scripts/snapshot.mjs --input <model.implicit.js> --output <snapshot.png>
node scripts/snapshot.mjs --input <model.implicit.js> --output <orbit.gif> --mode orbit
node scripts/snapshot.mjs --job <render-job.json>
node scripts/snapshot.mjs --job - --json
node scripts/snapshot.mjs --help
```

Use `node scripts/snapshot.mjs --help` for the complete current command interface. The tool appends a UTC timestamp before the output extension. JSON jobs may be a single job, one job with multiple `outputs`, a raw array of jobs, or `{ "jobs": [...] }`; prefer a multi-output job for review packets because it avoids rebuilding the same artifact for each camera.

## Export Tool

From this skill directory:

```bash
node scripts/export.mjs --input <model.implicit.js> --format glb
node scripts/export.mjs --input <model.implicit.js> --output <mesh.stl> --resolution <resolution>
node scripts/export.mjs --input <model.implicit.js> --format 3mf --params '<parameter-json>' --json
node scripts/export.mjs --help
```

Supported export formats are `glb`, `stl`, and `3mf`. The exporter samples the implicit SDF inside the declared bounds and extracts a triangle mesh. If `--output` is omitted, the mesh is written next to the source file using the same stem, such as `<model>.glb` for `<model>.implicit.js`. Use `node scripts/export.mjs --help` for the complete current command interface.
