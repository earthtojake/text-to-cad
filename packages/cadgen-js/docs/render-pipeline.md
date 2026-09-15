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

### `common/sceneSettings.js`

```js
import {
  resolveSceneSettings,
  resolveDisplayMaterialSettings
} from "cadgen-js/common/sceneSettings.js";
```

`resolveSceneSettings({ appearance, render, quality, camera, display })` is the
shared Viewer/snapshot policy resolver. A missing `render` selects responsive
CAD inspection defaults, where the top-level quality, camera, and display fields
apply. A Render envelope is isolated from those CAD fields and has this closed
sparse shape:

```js
{
  studio: "light", // or "dark"; omit to follow global appearance
  quality: "final", // or "preview"
  exposure: 0, // EV, -5..5
  lighting: {
    rotation: 0, // degrees around CAD Z, -180..180
    size: 1, // relative softbox size, 0.25..3
    fill: 0.25 // opposing fill ratio, 0..1
  },
  backdrop: { color: "#e7e7e5", transparent: false, ground: true },
  camera: {
    preset, projection, position, target, up, direction, zoom,
    orthographicHalfHeight, focalLength
  }
}
```

The normalized Render payload preserves omission. The resolved scene expands
the effective values under `resolved.render.configuration`, so a UI can display
the active studio and defaults without pinning them into session state. Render
always uses its private `shaded`, authored-color display policy with edges,
guides, clipping, exploded view, selectors, and selection disabled. The Render
camera comes only from `render.camera`; per-output snapshot cameras are applied
later by the capture adapter. Animation remains active because it is authored
model choreography rather than CAD inspection state.

`orthographicHalfHeight` is the positive pre-zoom vertical half-extent of an
orthographic camera. It may remain in a perspective camera payload so switching
back restores the prior orthographic scale.
`focalLength` is a perspective-camera lens in millimetres from 20 to 200 and
defaults to 50 in Render.

Studio ids are exactly `light` and `dark`. Omitting `studio`
follows the resolver's global appearance while keeping the normalized Render
payload sparse. `resolved.render.configuration.studio` reports the effective id
for UI. Quality is `preview` or `final` and does not select a studio; it maps to
the internal standard or high scene policy respectively. Render defaults to
perspective, `shaded`, authored materials, and final quality. Normal CAD defaults to
orthographic `shaded_edges`, Original part colors, and interactive quality;
it keeps authored albedo and opacity while applying matte workbench PBR
channels, and the snapshot adapter turns normal CAD guides off for deterministic
stills.
Final uses the bounded finest mesh rung, a 0.25px viewport target, 4096px
spotlight shadows, a 512px procedural environment, and 2x snapshot capture.
Those values are derived from the quality id and do not expand the public JSON.

`resolveDisplayMaterialSettings(materials, partColor)` applies the display-owned
Original, Single color, or Color by part palette to normal CAD material settings.

The two studios use one physical Render pipeline. A neutral HDR key card and
opposing fill card generate a procedural PMREM for authored PBR reflections;
one aligned, model-scaled SpotLight supplies direct illumination and PCF contact
shadows. Softbox size changes card area and bounded shadow softness while keeping
total card flux stable. Rotation moves the direct light and
`scene.environmentRotation` together around CAD Z. An overhead side key reveals
depth; a rear fill card and dim enclosure keep reflections on dark and polished
surfaces readable. Environment radiance and direct illumination share a
calibrated zero-EV lighting budget. Khronos PBR Neutral tone mapping is fixed;
`toneMappingExposure` is `2 ** exposure`. Light and dark differ only in default
backdrop color.

`applyPhotographicStudio(THREE, runtime, configuration, options)` owns the
synchronous light, ground and renderer state and updates those objects in place.
`disposePhotographicStudio(runtime)` releases only those objects. The caller
separately owns the asynchronous PMREM returned by
`createEnvironmentResource(renderer, configuration, {size})`, assigns its
texture to `scene.environment`, and releases it through
`disposeEnvironmentResource()`. `environmentResourceIdentity()` includes
softbox size, fill, and PMREM resolution; it excludes rotation so rotating the
rig is a live scene update rather than an environment rebuild.

The ground uses `PHOTOGRAPHIC_STUDIO_STAGE_RADIUS_MULTIPLIER` for its full
square width. Camera fitting uses the same constant as far-plane padding, which
keeps the finite two-triangle ground outside practical product views without
weakening the model-fitted near plane.

Photographic Render creates its WebGL renderer with
`logarithmicDepthBuffer: false`. Three's logarithmic depth shader path does not
produce usable contact shadows. Render callers fit ordinary-depth near/far
planes to current model bounds with `fitCameraDepthToBounds(camera, bounds)`;
normal CAD retains logarithmic depth for broad inspection scales.

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
- `quality.tessellation`: explicit STEP tolerances for normal CAD snapshots.
  Render is isolated from this top-level CAD quality field and derives its
  bounded mesh rung only from `render.quality`.

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

- `theme`: normalized or raw internal studio settings.
- `displayMode`: `shaded`, `shaded_edges`, `transparent`, `hidden_edges`,
  `hidden_lines_removed`, `unshaded`, or `wireframe`.
- `edgeSettings`: display-owned CAD edge style. Themes do not own edges.
- `materialOverrides`: sparse explicit PBR overrides; authored PBR otherwise
  wins over studio material fallbacks.
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
`overrideSourceColors` in material settings replaces both kinds with display
fills.
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

`renderJobContext(meshData, job)` resolves the shared scene contract plus
snapshot-owned output policy: display, camera, quality, scene scale, outputs,
STEP topology edge visibility, and warnings. Snapshot scene quality comes only
from `render.quality`; `job.quality` contains technical tessellation only.

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
It uses snapshot sizing, studio environment, the shared stage floor/glow/shadow,
model-scaled lights with a fitted shadow frustum, canonical camera projection,
and deterministic renderer settings. Automatic perspective cameras fit the
current visible vertices to `output.padding` when `output.tightFrame` is true;
otherwise they fit the model bounds. An explicit camera position is never
reframed. Video capture fits its precomputed sequence-union bounds once so the
camera does not breathe between frames.

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
  sourceSidecarUrl: "/models/part.step.json",
  cadPath: "models/part.step",
  kinematics: { drive: 180 }
});

const model = buildModel(THREE, source, {
  theme,
  displayMode: "shaded_edges",
  edgeSettings,
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
