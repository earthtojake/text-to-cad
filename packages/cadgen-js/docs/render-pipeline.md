# Render Pipeline

`cadgen-js` exposes a staged render pipeline for shared viewer, docs, and generated
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
  stepParameterRuntime
} from "cadgen-js/common/source.js";
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
- A caller that passes a `resolved` packet together with any source URL must also pass
  `resolved.inputPath`. Render asset caches are page-lifetime, so a resolved job has to name the
  source its cache entries belong to; a resolved job without `inputPath` is rejected rather than
  cached under an unidentified source. Callers with no `resolved` packet (the interactive viewer and
  the docs hero renderer) render one source per page and need nothing.
- `selectorRuntime` and `displayEdgeRuntime`: preloaded runtimes when a caller
  already owns sidecar loading.
- `kinematics`: pose values for the model's kinematics — a declared preset name,
  or `{dof: value}`. Same spelling as the `--kinematics` flag, the snapshot job
  key and the sidecar section.
- `stepParameterUrl` or `resolved.stepParameterUrl`: model sidecar
  (`.step.json`) URL, whose `kinematics` section is compiled here.

STEP-only options are rejected for non-STEP sources. The old shared `params`
field is rejected, and so is the retired `stepParameters` spelling; use
`kinematics`.

Use `stepParameterRuntime(stepParameterSource)` to turn the loaded parameter
source into the runtime object `buildModel` accepts.

### `common/cadScene.js`

```js
import {
  buildModel,
  fitCameraToModel
} from "cadgen-js/common/cadScene.js";
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
- `stepParameters`: compiled kinematics runtime object, from
  `stepParameterRuntime()`.
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

Source colors: a GLB's material base colors and its `COLOR_0` vertex attribute
both count as source colors (`lib/render/glbMeshData.js`). A vertex-colored
part renders on a white base so the ramp shows unmixed — an FEA result or scan
heatmap keeps its colors even when the file declares no materials at all — and
`overrideSourceColors` in the theme still replaces both kinds with theme fills.
Package components carry no vertex colors; their coloring is the descriptor's
occurrence/component/face colors.

`fitCameraToModel(THREE, camera, bounds, options)` is the shared orthographic
camera framing helper used by interactive rendering.

### `common/renderModel.js`

Use this module for interactive browser canvases, including the docs hero.

```js
import { renderModel } from "cadgen-js/common/renderModel.js";
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
} from "cadgen-js/common/renderMeshScene.js";
```

`renderJobContext(meshData, job)` normalizes snapshot-owned render policy:
theme, display, scene scale, outputs, STEP topology edge visibility, and
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
- `mode: "section"`: PNG data URLs or SVG text in `outputs`.
- `mode: "list"`: part list and bounds.

It does not write files. The CAD skill snapshot CLI writes the returned data to
disk. Source checkouts use `packages/cadgen-js`; generated snapshot browser assets
bundle this entrypoint into cadgen's packaged runtime (`cadgen/_runtime/browser`).

`renderMeshJob(meshData, job)` is a compatibility wrapper that builds a context,
builds a model, renders/captures it, and disposes owned resources.

## Kinematics

Two names, two things, and they are not interchangeable:

* `kinematics` is the POSE INPUT — what `loadSource()` and the snapshot job
  packet take. A declared preset name, or direct DOF values:

  ```json
  { "drive": 180, "ringVisible": false }
  ```

  Animation envelopes (`animate`, `fps`, `durationSeconds`, `duration`, `loop`)
  are retired and throw: a still renders one frame at the given values.

* `stepParameters` is the compiled RUNTIME OBJECT that `buildModel()` takes,
  produced by `stepParameterRuntime(source.stepParameterSource)`.

`common/stepParameters.js` validates the pose values against the loaded
definition and normalizes defaults.
`loadSource()` uses it to populate `source.stepParameterSource`; callers then
pass `stepParameterRuntime()` into `buildModel()`.

## Examples

Interactive viewer/docs usage:

```js
import * as THREE from "three";
import { loadSource, stepParameterRuntime } from "cadgen-js/common/source.js";
import { buildModel } from "cadgen-js/common/cadScene.js";
import { renderModel } from "cadgen-js/common/renderModel.js";

const source = await loadSource({
  kind: "step",
  glbUrl: "/models/.part.step.glb",
  stepParameterUrl: "/models/.part.step.js",
  cadPath: "models/part.step",
  kinematics: { drive: 180 }
});

const model = buildModel(THREE, source, {
  theme,
  displayMode: "solid",
  stepParameters: stepParameterRuntime(source.stepParameterSource)
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
import { loadSource } from "cadgen-js/common/source.js";
import { buildModel } from "cadgen-js/common/cadScene.js";
import {
  captureModel,
  modelOptionsForRenderJob,
  renderJobContext,
  renderModel
} from "cadgen-js/common/renderMeshScene.js";

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
