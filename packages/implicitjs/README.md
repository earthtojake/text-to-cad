# implicitjs

`implicitjs` is a standalone JavaScript runtime for browser-native implicit CAD
models. It defines the `.implicit.js` model schema, builds GLSL raymarch
shaders, renders models with Three.js, evaluates SDFs on the CPU, produces
headless PNG/GIF snapshots, samples meshes, checks mesh quality, and exports
STL, 3MF, and GLB artifacts.

The package is UI-framework agnostic. Applications provide their own editor,
catalog, sidebar, persistence, and product workflow; `implicitjs` provides the
model, rendering, snapshot, and export logic.

## Install

```bash
npm install implicitjs
```

Peer usage expects a modern ESM JavaScript environment. Rendering APIs require
Three.js-compatible WebGL support. The headless snapshot CLI uses Playwright.

## Model Format

An implicit model is an ES module that exports an `implicit.js/0.1.0` object.
The `glsl` string must provide `float sdf(vec3 p)`. It may also provide
`vec3 color(vec3 p, vec3 normal)` for procedural color.

```js
const GLSL = `
float sdf(vec3 p) {
  return implicit_sphere(p, vec3(0.0), radius);
}

vec3 color(vec3 p, vec3 normal) {
  return mix(vec3(0.0, 0.65, 1.0), vec3(1.0, 0.3, 0.8), normal.z * 0.5 + 0.5);
}
`;

export default {
  schema: "implicit.js/0.1.0",
  name: "parametric sphere",
  units: "mm",
  params: {
    radius: { type: "number", label: "Radius", min: 5, max: 50, default: 22, unit: "mm" }
  },
  bounds: ({ params }) => {
    const r = params.radius + 2;
    return [[-r, -r, -r], [r, r, r]];
  },
  render: { steps: 192 },
  glsl: GLSL
};
```

Number, boolean, color, and button params automatically become GLSL uniforms
with matching names. Use param names directly in GLSL; a separate `uniforms`
object is not needed.

`bounds` is optional and can be estimated from the SDF, but explicit bounds are
recommended for unusual fields, thin features, periodic models, animated size
changes, or export-heavy workflows.

Authored GLSL can use built-in helpers in the `implicit_*` namespace, such as
`implicit_sphere`, `implicit_box_centered`, `implicit_cylinder_capped`,
`implicit_line_segment2`, `implicit_union_round`, and
`implicit_intersect_round`.

## Public APIs

Common imports:

```js
import {
  loadImplicitModuleFromSource,
  normalizeImplicitModel,
  renderImplicitToDataUrl,
  snapshotImplicitCadModel,
  exportImplicitModel,
  exportImplicitAnimatedGlb
} from "implicitjs";
```

Useful subpath exports:

- `implicitjs/model`: schema normalization and parameterized runtime models.
- `implicitjs/loader`: loading `.implicit.js` modules or source strings.
- `implicitjs/render`: Three.js shader and camera helpers.
- `implicitjs/snapshot`: browser PNG snapshot helpers.
- `implicitjs/mesh`: SDF mesh sampling.
- `implicitjs/meshQuality`: mesh quality checks.
- `implicitjs/export`: STL/3MF/GLB export APIs.
- `implicitjs/sdfEvaluator`: CPU SDF evaluator for compatible GLSL.

## Rendering

```js
import * as THREE from "three";
import { loadImplicitModuleFromSource, renderImplicitToDataUrl } from "implicitjs";

const model = await loadImplicitModuleFromSource(source);
const pngDataUrl = await renderImplicitToDataUrl(THREE, model, {
  width: 1200,
  height: 900,
  camera: "iso",
  render: { frameMargin: 1.45 },
  graphics: { modelColors: true, detail: 1.2 }
});
```

Camera presets include `iso`, `front`, `back`, `left`, `right`, `top`, and
`bottom`. Cameras can also be JSON objects with `position`, `target`, `up`,
`direction`, `preset`, and `zoom`.

## Snapshots

From a package checkout:

```bash
npm run snapshot -- --input examples/model.implicit.js --output /tmp/model.png
npm run snapshot -- --input examples/model.implicit.js --output /tmp/model.gif --mode orbit
```

The snapshot CLI also accepts JSON jobs. A single job can include multiple
outputs, and `--job` can load one job, an array of jobs, or `{ "jobs": [...] }`.
Prefer one multi-output job when rendering review packets because the browser,
module, and runtime model can be reused.

```bash
npm run snapshot -- --job - <<'JSON'
{
  "input": "examples/model.implicit.js",
  "render": { "frameMargin": 1.55 },
  "outputs": [
    { "path": "/tmp/model-iso.png", "camera": "iso" },
    { "path": "/tmp/model-front.png", "camera": "front" },
    { "path": "/tmp/model-top.png", "camera": "top" }
  ]
}
JSON
```

Each output path receives a UTC timestamp before its extension.

## Exports

```js
import { exportImplicitModel, exportImplicitAnimatedGlb } from "implicitjs/browser";

const glb = await exportImplicitModel(model, {
  format: "glb",
  resolution: 96,
  params: { radius: 24 }
});

const animated = await exportImplicitAnimatedGlb(model, {
  animationId: "breathe",
  params: { radius: 24 },
  frames: 24,
  resolution: 72
});
```

From a package checkout:

```bash
npm run export -- --input examples/model.implicit.js --format glb --output /tmp/model.glb
npm run export -- --input examples/model.implicit.js --format stl --resolution 96
npm run export -- --input examples/model.implicit.js --format 3mf --params '{"radius":24}'
```

Exports sample the model's SDF inside its bounds. Higher resolutions produce
denser meshes and take longer.

## Package Layout

- `src/index.js`: public package entrypoint.
- `src/browser.js`: browser-oriented entrypoint.
- `src/common/`: shared camera, parameter, theme, render-option, and headless
  snapshot helpers.
- `src/lib/implicitCad/`: schema, model normalization, loading, shader
  rendering, CPU evaluation, mesh sampling, mesh quality, and exporters.
- `src/lib/viewer/`: internal render presentation defaults used by shaders.
- `scripts/`: snapshot, export, export-verification, and test CLIs.

Tests live beside the modules they cover as `*.test.js`.

## Development

```bash
npm test
npm run verify:exports -- --input examples/model.implicit.js
```

Keep the package reusable and UI-independent. Runtime behavior that applies to
model normalization, rendering, snapshots, CPU sampling, mesh export, graphics
settings, parameters, and animations belongs here. Product-specific UI state,
catalogs, editors, file sheets, routing, and persistence should live in the
consuming application.
