# Render Pipeline

`cadjs` exposes a staged render pipeline for shared viewer, docs, and generated
snapshot browser-runtime work:

```js
const source = await loadSource(input, sourceOptions);
const model = buildModel(THREE, source, modelOptions);
const viewport = renderModel(THREE, model, viewportOptions);
const result = await captureModel(viewport, captureOptions);
```

The stages keep ownership narrow:

- `loadSource` owns source and sidecar loading plus file-kind validation.
- `buildModel` owns the CAD object graph, records, selection, clipping,
  materials, topology/display edges, and STEP parameter effects.
- `renderModel` owns renderer, scene, camera, lighting, background, floor,
  framing, resizing, and render loop concerns.
- `captureModel` owns deterministic snapshot outputs without filesystem writes.

The CAD skill's Python snapshot CLI remains responsible for job parsing, path
resolution, Playwright routing, and writing returned outputs to disk.

## Modules

### `common/source.js`

```js
import {
  loadSource,
  stepParameterFrameRuntime
} from "cadjs/common/source.js";
```

`loadSource(input, options)` returns a normalized render source:

```js
{
  kind,
  meshData,
  selectorRuntime,
  displayEdgeRuntime,
  stepParameterSource,
  resolved,
  url,
  glbUrl,
  cadPath
}
```

Accepted input fields:

- `kind`: `step`, `stp`, `glb`, `stl`, `3mf`, or inferred from a URL.
- `meshData`: already-loaded mesh data. If present, no mesh URL fetch is needed.
- `url`: source URL for non-STEP GLB loading.
- `glbUrl` or `resolved.glbUrl`: STEP/STP hidden GLB sidecar URL.
- `cadPath` or `resolved.inputPath`: CAD path used by STEP selectors.
- `selectorRuntime` and `displayEdgeRuntime`: preloaded runtimes when a caller
  already owns sidecar loading.
- `stepParameters`: raw STEP render values or animation envelope.
- `stepParameterUrl` or `resolved.stepParameterUrl`: `.step.js`/`.stp.js`
  parameter sidecar URL.

STEP-only options are rejected for non-STEP sources. The old shared `params`
field is rejected; use `stepParameters`.

Use `stepParameterFrameRuntime(stepParameterSource, frameIndex)` to turn the
loaded STEP parameter source into the runtime object accepted by `buildModel`
for a still or animation frame.

### `common/cadScene.js`

```js
import {
  buildModel,
  fitCameraToModel
} from "cadjs/common/cadScene.js";
```

`buildModel(THREE, source, settings)` returns a model API:

```js
{
  source,
  meshData,
  root,
  modelGroup,
  edgesGroup,
  displayRecords,
  records,
  bounds,
  radius,
  runtime,
  update(nextSettings),
  dispose()
}
```

`source` can be a `loadSource()` result or raw mesh data. The model owns the
Three.js object graph and its mutable state.

Common settings:

- `theme`: normalized or raw theme settings.
- `displayMode`: `solid`, `rendered`, `transparent`, `hidden_edges`,
  `hidden_lines_removed`, `unshaded`, or `wireframe`.
- `scale`/`sceneScale`: CAD or robot scene scale.
- `selection`: internal selection/filtering state. `focus`, `refs`, and `hide`
  filter rendered parts before records are built. Viewer-only fields such as
  `selectedPartIds`, `hiddenPartIds`, and `showEdges` affect visual state.
- `clip`: normalized clip-plane settings.
- `stepParameters`: STEP parameter runtime object, usually from
  `stepParameterFrameRuntime()`.
- `parameterSetup`: set `false` to skip sidecar setup lifecycle calls.
- `renderPartsIndividually`: build per-part records instead of a whole mesh.
- `edgeRendering`: declarative edge rendering configuration.

Declarative screen-space edge rendering:

```js
buildModel(THREE, source, {
  edgeRendering: {
    mode: "screen-space",
    Line2,
    LineGeometry,
    LineSegments2,
    LineSegmentsGeometry,
    LineMaterial,
    wireframeEdgeColor: "#111827"
  }
});
```

The model keeps screen-space line material bookkeeping internal through
`runtime.screenSpaceLineMaterials` and `runtime.syncScreenSpaceLineMaterials()`.
Callers should not provide callbacks that create edge objects.

`model.update(nextSettings)` merges mutable settings, rebuilds geometry only
when needed, reapplies material/selection/clip/STEP parameter state, and returns
the same model API. `model.dispose()` releases model-owned scene objects and
STEP parameter cleanup hooks.

`fitCameraToModel(THREE, camera, bounds, options)` is the shared orthographic
camera framing helper used by interactive rendering.

### `common/renderModel.js`

Use this module for interactive browser canvases, including the docs hero.

```js
import { renderModel } from "cadjs/common/renderModel.js";
```

`renderModel(THREE, model, options)` returns an interactive viewport API:

```js
{
  THREE,
  model,
  renderer,
  scene,
  camera,
  ready,
  resize(),
  render(),
  start(),
  stop(),
  capturePng(),
  dispose()
}
```

Common options:

- `canvas`: existing canvas for the renderer.
- `hostElement`/`container`: element used for responsive sizing.
- `renderer`: caller-owned renderer. If omitted, one is created.
- `scene` and `camera`: caller-owned scene/camera. If omitted, defaults are
  created.
- `theme`/`themeSettings`: background and lighting settings.
- `alpha`, `antialias`, `powerPreference`, `preserveDrawingBuffer`,
  `logarithmicDepthBuffer`, `shadows`: renderer controls.
- `direction`, `up`, `padding`, `scale`/`sceneScale`: framing controls.
- `pixelRatio`, `maxPixelRatio`: output density controls.
- `autoResize`: set `false` to disable `ResizeObserver`.
- `autoStart`: set `true` to start an animation loop.
- `autoRender`: set `false` to prevent the initial render.
- `beforeRender({ deltaSeconds, viewport })`: per-frame hook for animation.
- `disposeModel`: set `false` when the caller will dispose the model.

`dispose()` stops animation, disconnects resize observation, removes the model
root from the scene, and disposes the created renderer/model unless ownership
was explicitly retained by options.

### `common/renderMeshScene.js`

Use this module for deterministic headless snapshot rendering.

```js
import {
  renderJobContext,
  modelOptionsForRenderJob,
  renderModel,
  captureModel,
  renderMeshJob
} from "cadjs/common/renderMeshScene.js";
```

`renderJobContext(meshData, job)` normalizes snapshot-owned render policy:
appearance, display, scene scale, outputs, STEP topology edge visibility, and
warnings.

`modelOptionsForRenderJob(context, job)` converts that policy into
`buildModel()` settings.

Snapshot `renderModel(THREE, model, { job, context })` returns a headless
viewport:

```js
{
  THREE,
  model,
  scene,
  renderer,
  orthographicCamera,
  perspectiveCamera,
  context,
  sceneBuildStarted,
  ready,
  dispose()
}
```

This `renderModel` is intentionally separate from `common/renderModel.js`.
It uses snapshot sizing, theme environment, floor, orthographic/perspective
camera presets, and deterministic renderer settings.

`captureModel(viewport, { job })` returns data only:

- `mode: "view"`: PNG data URLs in `outputs`.
- `mode: "orbit"`: the caller composes frames into GIF output.
- `mode: "section"`: PNG data URLs or SVG text in `outputs`.
- `mode: "list"`: part list and bounds.

It does not write files. The CAD skill snapshot CLI writes the returned data to
disk. Source checkouts use `packages/cadjs`; generated snapshot browser assets
bundle this entrypoint into `skills/cad/scripts/snapshot/runtime`.

`renderMeshJob(meshData, job)` is a compatibility wrapper that builds a context,
builds a model, renders/captures it, and disposes owned resources.

## STEP Parameters

Shared render APIs use the name `stepParameters`.

Raw render values can be direct parameter values:

```json
{
  "drive": 180,
  "ringVisible": false
}
```

Or an animation envelope:

```json
{
  "values": {
    "ringVisible": true
  },
  "animate": {
    "drive": { "from": 0, "to": 1260 }
  },
  "durationSeconds": 6,
  "fps": 18,
  "loop": true
}
```

`common/stepParameters.js` validates these values against the loaded STEP
parameter sidecar schema, normalizes defaults, and computes per-frame values.
`loadSource()` uses it to populate `source.stepParameterSource`; callers can
then use `stepParameterFrameRuntime()` when passing parameters into
`buildModel()`.

## Examples

Interactive viewer/docs usage:

```js
import * as THREE from "three";
import { loadSource, stepParameterFrameRuntime } from "cadjs/common/source.js";
import { buildModel } from "cadjs/common/cadScene.js";
import { renderModel } from "cadjs/common/renderModel.js";

const source = await loadSource({
  kind: "step",
  glbUrl: "/models/.part.step.glb",
  stepParameterUrl: "/models/.part.step.js",
  cadPath: "models/part.step",
  stepParameters: { drive: 180 }
});

const model = buildModel(THREE, source, {
  theme,
  displayMode: "solid",
  stepParameters: stepParameterFrameRuntime(source.stepParameterSource, 0)
});

const viewport = renderModel(THREE, model, {
  canvas,
  hostElement: canvas.parentElement,
  theme,
  autoStart: true
});
```

Headless snapshot usage:

```js
import * as THREE from "three";
import { loadSource } from "cadjs/common/source.js";
import { buildModel } from "cadjs/common/cadScene.js";
import {
  captureModel,
  modelOptionsForRenderJob,
  renderJobContext,
  renderModel
} from "cadjs/common/renderMeshScene.js";

const source = await loadSource(job);
const context = renderJobContext(source.meshData, job);
const model = buildModel(THREE, source, modelOptionsForRenderJob(context, job));
const viewport = renderModel(THREE, model, { job, context });

try {
  const result = await captureModel(viewport, { job });
  // Write result.outputs in the CAD skill snapshot CLI or another caller-owned layer.
} finally {
  viewport.dispose();
}
```

## Ownership Rules

- Do not write files from shared render APIs. Return data to the owning CLI or
  application layer.
- Do not expose object-construction callbacks for edges. Use declarative
  `edgeRendering`.
- Keep STEP-only options explicitly STEP-named and reject them for non-STEP
  sources.
- Dispose viewports and models that you create.
- Prefer `loadSource -> buildModel -> renderModel -> captureModel` for new
  shared render code instead of loading assets or constructing render scenes
  inline.
