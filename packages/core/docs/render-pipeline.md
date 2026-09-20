# Render Pipeline

`@hardcore/core` exposes a staged render pipeline for shared viewer, docs, and generated
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

### `common/viewSettings.js` and `common/sceneSettings.js`

`normalizeViewSettings(display)` is the strict public schema shared with the
snapshot CLI. It preserves omitted groups and inherited appearance, defaulting
only `mode` to `solid`. The presets, in order, are `solid`, `render`, `xray`,
`hidden-line`, and `wireframe`. Legacy public display fields are rejected.

Every preset has the same independent groups:

```js
{
  mode: "render",
  appearance: "light", // omit to inherit the viewer; CLI defaults to light
  camera: { projection: "perspective", focalLength: 50 },
  surfaces: { style: "shaded", colorMode: "original", opacity: 1 },
  edges: { enabled: false, visibility: "visible", color: "#253443" },
  lighting: { quality: "final", exposure: 0, rotation: 0, size: 1, fill: 0.25 },
  background: { color: "#e7e7e5", opacity: 1 },
  floor: { placement: "origin", color: "#e7e7e5", opacity: 0.6 },
  grid: { enabled: false, color: "#cbd5e1", opacity: 0.16 },
  axes: { enabled: false, color: "#6b7280", opacity: 0.28 }
}
```

Omission inherits the selected preset. A present group merges its partial
fields and enables the group unless `enabled: false` is explicit. Thus
`{mode: "solid", floor: {color: "#ffffff"}}` adds a floor under neutral CAD
lighting. Disabling lighting retains neutral CAD lights and the small authored
material reflection hemisphere from `inspectEnvironment.js`; it does not make
the model black. Disabling background restores the natural workbench canvas.
Disabling floor, grid, axes or edges removes that effect. Disabling surfaces
restores authored, lit surfaces at full view opacity; `surfaces.style: "off"`
explicitly removes visible surfaces. Camera disable restores orthographic/50mm.

`resolveViewSettings(display, {appearance, lightingQuality})` expands all groups. Solid defaults
to shaded original colors, visible edges, neutral lighting, grid and axes.
Render defaults to perspective, no edges, photographic lighting, opaque
background and the translucent floor; the other presets are orthographic.
X-ray uses 0.22 surface opacity with all edges. Hidden line uses depth-only
surfaces with visible edges. Wireframe turns surfaces off and draws all edges.
Every group remains independently editable in every preset. Surface styles are
`shaded`, `flat`, `hidden` (depth only) and `off`; color modes are `original`,
`single` and `by-part`, with `color` and an optional `colors` palette.

`viewSettingsAreCustom()` compares effective settings with the selected preset.
`resetViewSettings()` clears all View overrides, including `clip`/`exploded`,
keeping only the selected mode. Preset selection separately preserves the tools.
Tools never make a preset Custom. Appearance inherits
until explicitly supplied. Surface opacity multiplies authored source opacity;
color modes change presentation without mutating authored materials.

Clip keeps coordinates below its plane by default (`invert: false`); Flip keeps
coordinates above it. Its offset remains measured from the bounds minimum to
maximum regardless of Flip. The neutral boundary is therefore offset 1 normally,
or offset 0 when flipped. Interactive viewers and snapshots share this policy;
orbiting the camera never changes the clipped half.

`resolveViewSceneSettings({display, camera, appearance, quality})` is the public
Viewer/snapshot scene-policy boundary. Its `view` is the full grouped state;
`display` is the historical internal draw policy, including `surfaces` and
edge color/visibility. `camera` combines the top-level pose with the grouped
lens. Public top-level and per-output cameras contain pose/framing only;
projection and focal length belong to `display.camera`. Focal length ranges
from 20 to 200 mm. `orthographicHalfHeight` is the positive pre-zoom vertical
half-extent and may be retained while perspective is active.

The resolver's `render.enabled` means lighting, background or floor needs the
studio scene helper. `render.configuration.lighting.enabled` independently
controls photographic illumination and PMREM allocation. `theme` retains the
neutral workbench recipe whenever photographic lighting is disabled, including
when a custom background or floor is present. Consumers build CAD models with
`surfaceSettings: resolved.view.surfaces` and the resolved edges; they must not
reapply historical mode-owned edge forcing. `resolveSceneSettings()` remains an
internal compatibility resolver for older low-level consumers.

Background opacity follows the ordinary alpha convention: 0 is transparent and
1 is opaque. Fractional alpha is carried by the renderer clear color with
`scene.background = null`, so viewer checkerboards and PNG captures agree.
The floor is independent of background alpha. It defaults to authored Z=0;
`placement: "lowest"` follows the current model minimum without moving geometry
or lighting. Its double-sided plane uses one transparency pass, keeping geometry
below the origin visible. Depth fitting includes the actual floor elevation;
orthographic views can use a signed near plane when the floor crosses the eye.

Lighting quality is `preview` or `final`, mapping to standard/high scene policy.
The viewer passes `lightingQuality: "preview"`; the CLI baseline is `final`.
That environment default also feeds Custom comparison and does not pin a saved
override. An explicit `lighting.quality` wins in either context.
Final uses the bounded L3 mesh rung, a 0.25px viewport target, 4096px spotlight
shadows, a 512px procedural environment and 2x snapshot capture. Technical
`quality.tessellation` and `output.renderScale` remain explicit overrides.
PNG output retains requested dimensions by resampling the full drawing buffer.

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
separately owns the PMREM returned by
`createEnvironmentResource(renderer, configuration, {size})` — synchronous GPU
work, returned directly rather than as a promise — assigns its
texture to `scene.environment`, and releases it through
`disposeEnvironmentResource()`. `environmentResourceIdentity()` includes
softbox size, fill, and PMREM resolution; it excludes rotation so rotating the
rig is a live scene update rather than an environment rebuild. A resource also
exposes `readPixels()` for transferring its half-float PMREM from worker WebGL.
The interactive UI prepares and caches these maps off the main thread; snapshot
rendering can keep the synchronous caller-owned path.

The ground uses `PHOTOGRAPHIC_STUDIO_STAGE_RADIUS_MULTIPLIER` for its full
square width. Camera fitting uses the same constant as far-plane padding, which
keeps the finite two-triangle ground outside practical product views. Near-plane
fitting includes the visible floor as well as the model.

Environment radiance and direct illumination are calibrated together at zero EV
across colored assemblies, gray mechanical models, and authored metal/plastic
finishes.

#### What Render's public contract does NOT have

No global material, no color grading, no arbitrary lights, no floor physics, no
glow controls. Adding one of these is a change to the law in the package
README, not a new option here.

Materials reaching that scene stay authored. STEP package material channels are
inputs to the rig: assigned sparse materials use roughness 0.42, metalness 0.03,
clearcoat 0, clearcoat roughness 0.26, and opacity 1; an absent base color
retains the STEP color, and authored opacity multiplies its source alpha.
Static direct mesh normalization retains only the appearance data the shared
mesh-data contract represents — GLB base or vertex color and opacity, 3MF
color, and no authored color for STL. Animated direct GLB keeps its native
glTF hierarchy instead, so its textures and PBR channels stay attached to the
scene.

Snapshots use the same grouped display contract. Photographic lighting supports
only the `view` capture mode. Camera,
selection, clipping, exploded view, guides, part colour, animation, video,
kinematics, robot joints, tessellation quality, per-output cameras and output
sizing remain composable.

Photographic lighting creates its WebGL renderer with
`logarithmicDepthBuffer: false`. Three's logarithmic depth shader path does not
produce usable contact shadows. Render callers fit ordinary-depth near/far
planes to current model bounds with `fitCameraDepthToBounds(camera, bounds)`.
The interactive viewer uses this fitted conventional depth for every preset so
settings can enable shadows without replacing its renderer/canvas. The fit also
uses visible records for closeups, the floor's actual elevation, and the grid's
plane and bounds independently of Floor. Otherwise the subject's near plane
clips foreground guides, or the far plane truncates their finite span. Standalone
CAD snapshots may still use logarithmic depth: they render one fixed configuration.

### `common/source.js`

```js
import {
  loadSource,
  stepParameterRuntime
} from "@hardcore/core/common/source.js";
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
- `quality.tessellation`: explicit STEP tolerances in every preset. When
  omitted, enabled `display.lighting.quality` selects the bounded preview/final
  mesh rung.

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
} from "@hardcore/core/common/cadScene.js";
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
  restBounds,
  radius,
  runtime,
  update(nextSettings),
  dispose()
}
```

`source` can be a `loadSource()` result or raw mesh data. The model owns the
Three.js object graph and its mutable state.

`bounds` follows the live pose — what lighting, the floor, shadows and clipping
need. `restBounds` is the same model at its ZERO pose, before a parameter, mate
or animation frame moved a record, and it is what a camera fit is grounded on so
that posing a model never re-frames it. A source that is itself a posed wrapper
over its own rest geometry (a robot description; see `poseUrdfMeshData`)
publishes `restBounds` on its mesh data and that value stands in.

Common settings:

- `theme`: normalized or raw CAD scene settings. Render passes none and supplies
  `materialSettings` instead.
- `displayMode`: `shaded`, `shaded_edges`, `transparent`, `hidden_edges`,
  `hidden_lines_removed`, `unshaded`, or `wireframe`.
- `edgeSettings`: display-owned CAD edge style. Themes do not own edges.
- `materialOverrides`: sparse explicit PBR overrides; authored PBR otherwise
  wins over studio material fallbacks.
- `scale`/`sceneScale`: CAD or robot scene scale.
- `selection`: internal selection/filtering state. `focus` and `hide`
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

### Display modes, CAD edges and geometry sharing

Internal draw modes are `shaded`, `shaded_edges`, `transparent`,
`hidden_edges`, `hidden_lines_removed`, `unshaded`, and `wireframe`. Public
presets resolve to those implementation details plus independent surface and
edge settings; never feed a public preset into `normalizeDisplayMode()`. Normal CAD
keeps authored albedo, opacity and finish. Workbench PBR channels are fallbacks;
a small neutral reflection environment makes authored metals readable without
loading the photographic studio.
`resolveDisplayMaterialSettings()` applies the shared Original, Single color
and Color by part policy without app state.

**Scene geometry is the tessellator's INDEXED output.** A surf component's
`meshData` shares the tessellation's vertex, normal and index buffers by
reference (a decoded `.tess` cache entry is copied out of its one entry
buffer) and is never expanded per triangle corner.

**CAD edges are not a surface shader.** `surfMeshData.js` emits indexed line
segments (`cadEdgePositions` + `cadEdgeIndices` + `cadEdgeClassRanges`, from
the same tessellation's boundary polylines, ~1.5 bytes per surface triangle)
and `cadScene.js` draws them as ONE instanced screen-space line draw per
component (`cadEdgeInstances.js`): the instances are every (segment,
occurrence) pair, decoded in the vertex shader from a per-component segment
texture (32 B per drawn segment, cached on the component) and a per-set
instance texture (128 B per occurrence: matrix, colour, opacity, visibility,
highlight).

`cadInk.js` fixes one dark model-edge palette and nominal widths per class:
feature 1, tangent 0.65, seam 0.8, and degenerate 0 (hidden). Public
`display.edges` exposes enabled, visible/all visibility and color; widths stay
renderer-owned and the default color preserves the restrained class palette. Grid settings keep
`enabled` plus optional `color` and `opacity`; omission follows the appearance
palette, while an explicit color applies to both cell and origin lines. Viewer
and snapshots share the same grid spacing:
five cells across the default model framing, with 112 divisions spanning the
floor so orbiting and panning do not expose an abrupt grid edge.
Grid and Axes share the appearance's default guide color.
Appearance updates preserve model lighting, materials, geometry,
segment textures and occurrence slots; only the canvas and guides adapt.

A thickness is a FULL width in DEVICE pixels — every line shader normalises its
extrusion by the drawing buffer, never the CSS size, and the fragment stage
filters a box with a symmetric ±0.75 px kernel. Integrated coverage equals the
nominal width even for subpixel lines, and zero width has zero coverage. Both
line paths share the filter; antialiasing does not inflate thin lines or depend
on the framebuffer sample count.

Per-occurrence highlight, dim, hide, focus, exploded placement and selection
are slots in that texture, written by the same record passes
(`applyDisplayRecordTransform`, `applyPartVisualState`,
`syncRecordEdgeMaterials`) that drive a plain line object; highlighted
occurrences draw in a second pass at the highlight render order. A deformed
tube leaves its slot for private screen-space lines, one per drawn class, that
bend with the surface and preserve the same class weights and colours.
Basic-only hosts use separate per-class materials too, so appearance changes
retain private edge geometry and cannot recolour another scene's component.
GPU cost per component: two textures, one 4-vertex quad, two materials, one
draw call (+1 while any occurrence is highlighted).

**One upload per component.** Geometry built from a shared component is cached
on the component object (`part.sourceMesh`), never on the composed package
`meshData`: a package is re-composed on every progressive publish and LOD swap,
and every occurrence, publish and swap reuses the one upload. A publish of the
same model reaches the live scene through `api.update({ source })`, which
reconciles records by occurrence id — records already on screen keep their
mesh, materials, visual and deformation state and BVH; only new occurrences are
built and only departed ones disposed (ownership and disposal:
[resource-ownership.md](resource-ownership.md)). Effects that change vertex
positions or normals acquire writable attributes before deforming them;
material refreshes leave component data unchanged. This keeps large assemblies
from duplicating these buffers for display. Assemblies keep geometry in their
component buffers; they allocate no combined copy of all positions, normals and
indices. Rendering and section views visit the placed components directly, and
the Viewer accepts that component geometry.

### `common/renderModel.js`

Use this module for interactive browser canvases, including the docs hero.

```js
import { renderModel } from "@hardcore/core/common/renderModel.js";
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
} from "@hardcore/core/common/renderMeshScene.js";
```

`renderJobContext(meshData, job)` resolves the shared scene contract plus
snapshot-owned output policy: display, camera, quality, scene scale, outputs,
STEP topology edge visibility, and warnings. Studio scene quality comes from enabled
`display.lighting.quality`; `job.quality` contains technical tessellation only.

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
disk. Consumers use compiled `@hardcore/core` exports; generated snapshot browser assets
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
import { loadSource, stepParameterRuntime } from "@hardcore/core/common/source.js";
import { buildModel } from "@hardcore/core/common/cadScene.js";
import { renderModel } from "@hardcore/core/common/renderModel.js";

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
import { loadSource } from "@hardcore/core/common/source.js";
import { buildModel } from "@hardcore/core/common/cadScene.js";
import {
  captureModel,
  modelOptionsForRenderJob,
  renderJobContext,
  renderModel
} from "@hardcore/core/common/renderMeshScene.js";

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
