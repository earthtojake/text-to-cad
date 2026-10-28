# Render Pipeline

`@text-to-cad/core` exposes a staged render for the viewer, the docs hero and the OCCT parity
bench's headless page: a family's scene builder makes the scene, `renderModel` draws it on a
canvas, and `captureModel` (the parity page's) returns its pictures.

```js
const scene = createGlbScene(THREE, document, options);      // or buildMeshScene, createRobotScene, createXbfScene
const viewport = renderModel(THREE, { root: scene.root, bounds: scene.bounds }, viewportOptions);
const result = await captureModel(viewport, captureOptions);
```

Every file family (GLB, STL, 3MF, URDF, SRDF, SDF, and an engine document: an `.xbf`, or a
STEP, which the viewer and a snapshot open as one) is drawn by ITS OWN scene
builder, the one the viewer's renderer for it calls too: the snapshot page loads the
file with that family's loader, builds the scene with that family's builder, dresses it
in the look the viewer's viewport would, and hands it to the same `renderModel` and
`captureModel` (`common/headlessScene.js`). No family is flattened into mesh data for a
render.

The stages keep ownership narrow:

- A family builder owns its scene: `createGlbScene` (`lib/render/glbScene.js`),
  `buildMeshScene` (`lib/render/meshScene.js`), `createRobotScene`
  (`lib/urdf/robotScene.js`), `createXbfScene` (`lib/xbf/xbfScene.js`, a cadgen engine
  document read by `loadXbfDocument` from the engine that serves it: one geometry per
  prototype over its XBM2 buffer's own typed-array views, one placed group per instance, CAD
  edges by class from the edge table, faces, edges and vertices picked by ordinal; the
  document's edges are the view's `edges`, which the scene wears through `setEdgeLook`; its
  regular modes are drawn in the engine's look, `GET /api/look`, and its environment image,
  `GET /api/look/environment`, read beside the document: `lib/xbf/xbfLook.js`). Each returns the
  scene contract of
  `lib/viewer/sceneContract.js`, and each scene gives a sibling (`createSibling()`): a
  second scene of the same file with its own objects, materials and look over the first's
  geometry (`lib/render/sharedGeometry.js`), which the viewer's Preview draws beside
  its editor. A GLB's sibling is a SkeletonUtils clone wearing copies of the file's authored
  materials, kept before any look, with a sibling `document` for its own routine; a robot's
  has its own links and pose, and its own vertex colours. Ownership is
  [resource-ownership §1](resource-ownership.md#1-shared-ownership-and-disposal).
- `renderModel` owns renderer, scene, camera, lighting, background, floor,
  framing, resizing, and render loop concerns. A scene that brings its own lighting (the
  contract's `rig`: an engine document's, its engine's look) is lit by it outside Render in place
  of the theme's lights, its environment the scene's (one PMREM per image and renderer, which every
  surface reflects, an authored finish in Solid and Shaded among them), its tone curve three's
  `CustomToneMapping` (`lib/viewer/sceneRig.js`, which the viewer's viewport puts up the same way);
  every other scene keeps the theme's rig. Such a scene's surface look may name a surface model
  too (`brdf`, `lib/viewer/surfaceBrdf.js`): an engine document's lit surfaces answer light as
  OCCT's PBR program does, which its look is defined by, in place of three's own physical model.
  A scene may light one look otherwise (the contract's `rigFor`, asked through `sceneRigFor`): an
  engine document's X-ray is its look's colour-only model, an ambient term and plain directional
  lights, no environment, three's own surface model and no finish, as OCCT draws it by Phong. A
  rig may blend in linear light too (`blend: "linear"`, an engine document's X-ray): its
  see-through surfaces composite as OCCT's sRGB frame buffer composites them, where three's canvas
  blends each layer after encoding it to sRGB and draws dark see-through parts too dark. Every
  stage draws a scene by `renderWithSceneRig`, which for such a rig draws the surfaces into a
  half-float target in linear light (XR-flagged, so each fragment keeps the rig's tone curve),
  multisampled as the canvas is, encodes that to the canvas with its depth in one pass, and then
  draws what three orders after the surfaces (transparent, a later `renderOrder`: the edges, a
  highlight, ink) over it as three always has, so a line's antialiased pixels stay resolved in
  sRGB, as OCCT's are (`drawnOverSurfaces`); every other scene, mode and rig is three's own draw.
  The target is the drawing buffer's size and lives with the rig: about 60 bytes a pixel at 4×
  MSAA (some 360 MB at 3024 × 1964) while X-ray is on. Neither renderer orders see-through faces
  as the other: three sorts each object back to front and draws a two-sided one back faces first,
  OCCT draws them as they were displayed, which is most of what still differs.
- `captureModel` draws the scene headless and returns its pictures, with no filesystem
  writes. cadgen's stills are OCCT's (`cadgen snapshot`); this headless scene is what the
  renderer parity measurement drives beside OCCT (`scripts/bench/occt_parity.py`).

## Modules

### `common/viewSettings.js` and `common/sceneSettings.js`

`normalizeViewSettings(display)` is the strict public schema shared with the parity page's
snapshot job and mirrored by `cadgen snapshot`'s `--display`. It preserves omitted groups and inherited appearance, defaulting
only `mode` to `solid`. A file's modes, in order, are `solid`, `shaded`, `parts`,
`xray`, `hidden-line`, and `wireframe` (`VIEW_MODE_VALUES`); `grid` is a boolean
switch every mode draws, off unless said. Appearance, camera, clip and exploded are
shared. A mode is a look at its own defaults: it has no settings of its own, and
anything else (a per-mode tree, a style group) fails validation.

```js
{ mode: "parts", grid: true, camera: { projection: "orthographic", focalLength: 50 }, clip: { axis: "z", at: 4 } }
```

Preview's photographic look (Render) is no mode: it is asked for on its own, by the
viewer's Preview and the parity page, over the same display. Its own settings
(`PreviewSettings`: `parts`, `lighting`, `background`, `floor`) are the viewer's,
kept beside the display, never in it (`normalizePreviewSettings`,
`resolvePreviewSettings`, `previewSettingsChanged`). `readViewSettings` and
`readPreviewSettings` read a stored record setting by setting, leaving out what this
build cannot read, without rewriting it.

`resolveViewSettings` returns the established renderer groups. Solid is shaded with
the model's visible CAD edges where the view offers them (`edges`); Shaded is the same
surfaces without; Parts is Solid with the by-part palette. X-ray uses 0.22 surface
opacity and all edges; Hidden line uses depth-only surfaces and visible edges; Wireframe
has no fill and all edges, both lighter on a dark backdrop. With `preview: true` it
resolves Render whatever the mode: perspective, no edges, no grid and the photographic
studio, from `previewSettings`. The modes use the shared camera, orthographic by default.
The grid is the same measuring grid in every mode (`viewGridDefaults`). The view's
capabilities are explicit injected lists (`viewFeaturesForKind`): an engine document (a STEP,
an `.xbf`) every mode (one part: no Parts, no Explode), a drawing Solid alone, any other 3D
file Solid, and Parts where it has several parts (`scenePartCount`); a saved mode
a view does not offer resolves as Solid without rewriting storage. Surface opacity
multiplies authored opacity; colours remain presentation settings, never model material
edits.

Clip keeps coordinates below its plane by default (`invert: false`); Reverse (in Clip's axis dropdown)
keeps coordinates above it. `clip.at` is the plane's coordinate on its axis in millimetres;
omitting it cuts through the middle of the authored bounds. A disabled clip cuts nothing.
`clip.partColors` defaults to true. Caps use each part's normal base material color,
without selection/hover tints or opacity; false uses uniform amber (`0xe9a451`).
Caps stay opaque even for transparent parts, and outer materials are unchanged.
Each intersected part has a winding pair and an opaque fill, so holes remain empty;
the fill (as wide as the model on the plane) writes the stencil back to 0 wherever it
covers, so no part needs a stencil clear of the whole buffer after it. Cap geometry/materials are owned by Clip; stencil
geometry is borrowed from the display meshes. Generic scene looks preserve
`mesh.userData.cadBaseColor` before highlight ink; STEP records use `baseColor`
and normal effect colors. A mesh with several materials uses its first material
as its cap color; texture and vertex-color variation are not sampled.

`resolveViewSceneSettings({display, preview, previewSettings, camera, appearance, quality})` is the public
Viewer/parity-page scene-policy boundary (`preview`: Render over the display, as above). Its `view` is the full grouped state;
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
reapply historical mode-owned edge forcing.

Background opacity follows the ordinary alpha convention: 0 is transparent and
1 is opaque. Fractional alpha is carried by the renderer clear color with
`scene.background = null`, so viewer checkerboards and PNG captures agree. Over that
clear the studio draws its backdrop (`studioBackdrop.js`), first of everything and
writing no depth: the background color as a seamless sweep, lifted toward white
behind the middle of the frame, shaded toward the corners and, by how far the view
ray looks up, above the horizon (`PHOTOGRAPHIC_STUDIO_BACKDROP`; the shade is a larger
share of a dark color than of a light one). It writes the clear's alpha, premultiplied
as three's clear is, so a half-transparent background keeps its gradient; at alpha 0 it
is not drawn, and a caller that renders with `scene.background` taken away and a clear
alpha of 0 (a thumbnail) gets nothing of it. The floor's mirrored draw leaves it out.
The floor is independent of background alpha. Render's stands at the model's
lowest point (`placement: "lowest"`, `RENDER_FLOOR_PLACEMENT`, the Render recipe's
backdrop default too, and the stills' Preview floor): it follows the current model
minimum without moving geometry or lighting. `placement: "origin"` pins it to authored
Z=0 instead. Its double-sided plane uses one transparency pass, keeping geometry below
the origin visible. Depth fitting includes the actual floor elevation;
orthographic views can use a signed near plane when the floor crosses the eye.

Lighting quality is `preview` or `final`, mapping to standard/high scene policy.
The viewer defaults to `lightingQuality: "preview"`; an explicit Preview
`lighting.quality` selects `final`.
Final is the High scene preset: 4096px spotlight shadows, a 512px procedural environment
and 2x snapshot capture, and a still view in the viewer converges over 64 samples of the
studio's frame (Preview: 32). `output.renderScale` is an explicit raster override; every
mesh is the engine's, at its one tolerance.
PNG output retains requested dimensions by resampling the full drawing buffer.

The two studios use one physical Render pipeline. A neutral HDR key card, a rear
fill card, a side bounce card and the studio's fixed soft sources
(`PHOTOGRAPHIC_STUDIO_PANELS`: a large overhead softbox and two tall strip boxes
about 75 degrees either side of the default camera) hang in a studio sweep and
generate a procedural PMREM for authored PBR reflections; one aligned,
model-scaled SpotLight supplies direct illumination and PCF shadows. Softbox
size changes every source's area and bounded shadow softness while keeping each
source's total flux stable. Fill sets both fill cards' radiance as a fraction of
the key card's. Rotation moves the direct light and `scene.environmentRotation`
together around CAD Z. An overhead side key reveals depth; the rear fill keeps
horizontal reflections readable and the bounce, low on the key's far side,
lifts the faces the key cannot reach (an iso view's right-hand side). The
softbox and strips are brightest along their centres and fall off toward their
edges, and the sweep (`PHOTOGRAPHIC_STUDIO_ROOM_RADIANCE`: 0.14 overhead, 0.07
at the horizon and a light floor's 0.3 below, easing between them) is dimmer
than they are, so polished and satin metal show defined gradients and highlight
lines between darker gaps — what reads as metal rather than grey plastic — and
dark glossy parts keep their color. Nothing is a void: a face turned away from
every source keeps a soft fill. Environment radiance and direct illumination
share a calibrated zero-EV lighting budget. Khronos PBR Neutral tone mapping is
fixed; `toneMappingExposure` is `2 ** exposure`. Light and dark differ only in
default backdrop color.

#### The studio's frame

Render's lighting is drawn through the studio's frame (`studioFrame.js`), which
`applyPhotographicStudio` keeps as `state.frame` while its lighting is on, and the viewer
and the snapshot both draw the scene through. Three draws the scene as before, but into an
XR-flagged target of the frame's (`isXRRenderTarget`), which three draws exactly as the
canvas, tone mapping and colour space included, so no material compiles a second program;
its depth is kept. Small full-screen passes then add:

- **Ambient occlusion.** Ground-truth AO (GTAO, after XeGTAO) from that depth alone, at half
  the drawing buffer's resolution: the horizon either side of each pixel along three screen
  directions, four steps each, within a radius of 0.1 of the model's rest radius (never more
  than a fifth of the view's height). Every sample is read at a full-resolution pixel's
  centre; a depth read from one pixel and placed at another turned sloped faces into
  staircases of false horizons. A depth-aware blur smooths it, and the composite upsamples it
  by depth, so it never bleeds across a silhouette, and darkens the scene's colour by it in
  linear light (`power` 2). The floor writes no depth, so it keeps its own contact shadow;
  the background is never darkened. This is what reads as a photograph rather than a
  render: the seam between a cover and its housing, the space between stacked plates, a
  bolt head on its plate, the inside of a bore.
- **Convergence.** A still view is the average of `samples` samples, each blended into a
  half-float accumulation at `1/(n+1)` and presented with a level of dither. Every sample but
  the first moves the camera a fraction of a pixel (Halton 2, 3), so edges and fine
  highlights are anti-aliased; turns the occlusion's directions (interleaved gradient noise
  per sample), so it converges smooth; and moves the key light to a point of its softbox's
  face (`sampleKey`: R2 over the key card's face, `PHOTOGRAPHIC_STUDIO_SOFT_SHADOW.spread`
  of it, scaled by Size), so the key's shadows become a softbox's: crisp where a part meets
  what it shades and soft away from it, on the model and, through the floor shadow's
  composite, on the floor. A shadow pass that only moved the key holds the floor shadow's
  heights (`holdHeights`) and re-composites its key shadow alone.

The frame's caller says whether a frame is `still`: nothing but, perhaps, the camera changed
since the last. A still frame is the next sample unless the camera has moved the model by
more than `STUDIO_FRAME_DRIFT_PIXELS` (0.25) on screen since the picture's first sample, so the
tail of a damped orbit still converges; anything else (a camera that moved, a pose, a
routine's frame, a setting, a resize) starts again from the first sample, which is a whole
picture of its own: the key at rest, the occlusion denoised in space. `render` answers whether
samples are still owed (`refining`); the caller asks for the next frame while they are, and
for none once the picture has converged. A moving view therefore pays for one draw and the
small passes a frame; the samples only while it rests.

Measured at 3024 × 1964 on an M1 Max over 0.6 M and 3 M triangles: a moving frame
3.1 → 4.5 ms and 5.0 → 6.6 ms, a sample 5.2 and 7.8 ms, all 32 samples back to back 155
and 240 ms (in the viewer, a sample a display frame: about half a second). Memory is the scene target (8-bit colour and depth-stencil, multisampled as
the canvas is: four samples, two on a canvas of pixel ratio 2 or more), its resolve, a
half-float accumulation and two half-resolution occlusion targets: about 200 MB at that
size, released with the studio. Software rendering has no frame: three's single draw, as
before, whose key casts no shadow to soften.

`applyPhotographicStudio(THREE, runtime, configuration, options)` owns the
synchronous light, ground and renderer state and updates those objects in place.
`disposePhotographicStudio(runtime)` releases only those objects, the studio's frame
included (`applyPhotographicStudio`'s `frame`: false for none, or its `samples` and
`multisample`). The caller
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

The floor has no edge (`PHOTOGRAPHIC_STUDIO_FLOOR_FADE`): from 1.6 times the model's
reach (the larger of its rest radius and its footprint's half-diagonal) it fades out
to its inscribed circle at 6 times it, where the two-triangle plane ends, so a low or
wide view shows no horizon line and no corner, only the backdrop. The fade is applied
to the floor's alpha after its reflection is laid over it, so the reflection fades with
it; it is squared, so its tail is long even foreshortened at a grazing angle. Camera
fitting keeps `PHOTOGRAPHIC_STUDIO_STAGE_RADIUS_MULTIPLIER` as far-plane padding, far past
that rim. Near-plane fitting includes the visible floor as well as the model.

The physical floor is mostly self-lit backdrop color and receives no shadow
map; its shadow is a contact layer drawn over it (`studioContactShadow.js`):
darkest where the model meets the floor, a broad occlusion fading with height,
and the key's cast shadow crisp near the model and softening into a wide, light
penumbra away from it. The layer is one texture over a square fitted to the
rest placement (`PHOTOGRAPHIC_STUDIO_CONTACT_SHADOW`), as deep as the floor is
opaque, and hidden while the studio's lighting is off; a floor at zero opacity
is not drawn, so it bakes nothing. It is baked in two steps: the heights, a
depth pass of the shadow casters seen up through the floor by a probe light
that is never added to the scene, and the composite, three small full-screen
passes over those heights and the key's own shadow map. Both are due only when
the key's shadows re-render: a sentinel in the studio, a shadow caster of zero
area that every shadow pass and the main pass draw (it rasterizes nothing in
either), notices that pass. The composite runs in that frame, so the key's cast
shadow on the floor follows every frame a model moves in. The heights do too,
unless the caller passes a `heightInterval` (`applyPhotographicStudio`'s
`contactShadow` option): then a scene that keeps changing re-measures them at
most that often, and once more when it stops, in a frame the layer asks for
(`requestFrame`), so what is shown at rest is exact and only the contact
darkening lags while a model moves. The interactive viewer re-renders shadows
only for a change that can alter them, never for a camera move or a highlight,
so it bakes nothing on those frames; the snapshot renderer, which renders
shadows every frame and passes no interval, bakes both steps every frame. A
runtime that renders in software (`softwareRendering`) gets no contact layer:
its key casts no shadow either. A transparent legacy backdrop's floor stays a
`ShadowMaterial` catcher of the key's shadow.

The floor and its shadow layer are dithered: each adds up to one 8-bit level of
noise as it is drawn (the floor's divided by its alpha, so its blend keeps it
whole; the layer's drawn premultiplied, so the blend adds exactly that noise over
whatever floor is under it). A dark floor's shading spans only a few levels of
the canvas, and rounding drew it as wavy contour bands; the noise is too fine to
see and leaves every average colour where it was. A snapshot drawn at a render
scale above 1 averages that scale squared of drawn pixels into each one it keeps,
which quietened the noise to a fraction of a level and let the rounding band
again: it passes its render scale as `applyPhotographicStudio`'s `ditherScale`,
which spreads both noises that much wider (`syncDitherScale`). The viewer keeps
1, and at 1 nothing is defined: its shaders are the ones they always were.

The floor's finish is `backdrop.groundFinish` (`PHOTOGRAPHIC_STUDIO_FLOOR_FINISHES`):
`matte`, the default, or `glossy`, a glossier surface that also reflects the model
(`studioFloorReflection.js`). Before each frame of the scene (its `onBeforeRender`)
the scene is drawn again from the camera mirrored in the floor, at half the
canvas's resolution; three small passes fade and soften it with each reflected
point's height (crisp where the model meets the floor), none of them sampling the
target it draws into, a draw WebGL refuses, and the floor lays it over
itself with a Fresnel weight, in display colour, so a light floor shows it as a
dark one does. The mirrored draw runs when the camera moved or the frame re-renders
shadows (it renders them, and the frame keeps them); a frame for a highlight keeps
the last reflection and catches up within 400 ms; a snapshot draws it every frame.
It runs before the frame, at the frame's own render depth and into a target three
treats as the canvas (`isXRRenderTarget`): drawn nested in the frame, or as an
ordinary target, it made every lit material rebuild its program key twice a frame,
which cost more than the draw. A matte floor allocates none of it; turning the
floor matte, the studio's lighting off or the floor off releases it.

Environment radiance and direct illumination are calibrated together at zero EV
across colored assemblies, gray mechanical models, and authored metal/plastic
finishes.

#### What Render's public contract does NOT have

No global material, no color grading, no arbitrary lights, no floor physics, no
glow controls. Adding one of these is a change to the law in the package
README, not a new option here.

Materials reaching that scene stay authored. An engine document's parts wear the material and
colour the structure gives them (`lib/xbf/xbfLook.js`); a part with none wears the studio's
surface (`PHOTOGRAPHIC_STUDIO_MATERIAL_SETTINGS`).
A GLB, a mesh file and a robot reach the studio as the scene their viewer renderer
builds. A GLB is its native glTF hierarchy, so its textures and PBR channels stay
attached. Regular Solid and Shaded views retain explicit glTF Standard and Physical
finishes, using the fixed neutral Inspect reflection fill; Parts, X-ray and Flat keep
their intentional overrides, and a primitive with no material uses the viewer's fallback.
Render also wears the file's materials as authored. The native GLB loader converts
world-space attenuation distance from glTF metres into CAD millimetres once per shared
material, before any view or sibling is made. Mesh-local thickness is not scaled, sibling
creation does not repeat the conversion, and the file bytes are unchanged. The native XBF
renderer currently uses the part's bounding-box extent for transmission thickness;
this can overestimate attenuation and refraction for a hollow shell. Three's raster
transmission buffer includes opaque geometry, not other transmissive layers, so a
transmissive liquid inside glass cannot be composed correctly through the outer shell.
A 3MF base-material group may author scalar metallicness and roughness through
`pbmetallicdisplayproperties`, indexed alongside its base entries
([Materials extension 1.2.1](https://github.com/3MFConsortium/spec_materials/blob/master/3MF%20Materials%20Extension.md)).
The loader bridges Three's base-entry reference expectation without changing the input archive,
then retains finish and display-colour alpha per material subset in mesh data. Solid/Shaded and
Preview keep those finishes; Inspect supplies the existing fixed neutral reflection fill.
Parts, X-ray and Flat remain reversible overrides, and display opacity multiplies source alpha.
Sibling scenes own their materials and share geometry; mode changes never modify decoded metadata.
This covers scalar base-material display properties, not textured PBR or translucent extension
transport. A material-bearing package the loader cannot decode fails instead of taking the
geometry-only compatibility fallback and silently losing its finish. Ordinary fallback packages
remain supported. An STL, a colour-only 3MF and a robot use the viewer/studio fallback finish over
their source colours (a 3MF's object colours, a robot description's colour, else its link mesh's own).

Snapshots use the same grouped display contract. Photographic lighting supports
only the `view` capture mode. Camera,
selection, clipping, exploded view, guides, part colour, animation,
kinematics, robot joints, per-output cameras and output sizing remain
composable.

Photographic lighting creates its WebGL renderer with
`logarithmicDepthBuffer: false`. Three's logarithmic depth shader path does not
produce usable contact shadows. Render callers fit ordinary-depth near/far
planes to current model bounds with `fitCameraDepthToBounds(camera, bounds)`.
The interactive viewer uses this fitted conventional depth for every preset so
settings can enable shadows without replacing its renderer/canvas. The fit also
uses visible records for closeups, the floor's actual elevation, and the grid's
plane and bounds independently of Floor. Otherwise the subject's near plane
clips foreground guides, or the far plane truncates their finite span. A
perspective camera passes its `pivot` (the point it looks at): its near plane
never comes nearer than 1/256 of the pivot's depth, so a closeup the fit cannot
measure (the camera inside a part's own box, or a part with no bounds to
measure) keeps its depth resolution instead of making close surfaces fight.
Snapshots draw every preset the same way: ordinary depth, fitted to each output
with the same inputs (its placed objects, the studio floor's elevation, the
drawn grid's span and the camera's target as pivot).

### Display modes, CAD edges and geometry sharing

Internal draw modes are `shaded`, `shaded_edges`, `transparent`,
`hidden_edges`, `hidden_lines_removed`, `unshaded` and `wireframe`
(`common/displaySettings.js`). Public presets resolve to those implementation details plus independent surface and
edge settings; never feed a public preset into `normalizeDisplayMode()`. Normal CAD
keeps authored albedo, opacity and finish. Workbench PBR channels are fallbacks;
a small neutral reflection environment makes authored metals readable without
loading the photographic studio (an engine document's: its look's environment,
which its rig brings).
`resolveDisplayMaterialSettings()` applies the shared Original, Single color
and Color by part policy without app state.

**Scene geometry is the engine's part buffers, read in place.** An engine document's parts
are XBM2 buffers (`lib/xbf/xbm.js`): positions, normals, indices, the face and edge tables
and the edge polylines, read as typed-array views (`lib/xbf/xbfDocument.js`) and never
expanded per triangle corner. One geometry per prototype serves every instance
(`lib/render/sharedGeometry.js`).

**CAD edges are not a surface shader.** An engine document draws one line set per edge class
(`lib/xbf/xbfScene.js`: a `LineBasicMaterial` each, in the class's ink) from the buffer's edge
polylines, and a highlighted edge as screen-space segments (`createScreenSpaceLineSegments`,
`common/renderEdges.js`). Every mode draws the same edges, Wireframe included: Wireframe is
the CAD edges with no fill, never the tessellation's triangles, so it builds nothing per
triangle.

`cadInk.js` fixes one dark model-edge palette and nominal widths per class:
feature 1, tangent 0.65, seam 0.8, and degenerate 0 (hidden). Public
`display.edges` exposes enabled, visible/all visibility and color; widths stay
renderer-owned and the default color preserves the restrained class palette. Grid settings keep
`enabled` plus optional `color`, `opacity` and `density`; omission follows the
appearance's graph-paper ink (`GRID_LINE_DEFAULTS` in `stageGrid.js`), while an
explicit color applies to every minor and major line but never the red X and
green Y axes. Viewer and snapshots draw the same grid (`createGridMesh`): its
step, majors and long distance fade are in `packages/ui/docs/render-mode.md`.
The Axes line is the blue Z axis.
Appearance updates preserve model lighting, materials, geometry,
segment textures and occurrence slots; only the canvas and guides adapt.
An edge color edit keeps them too: `model.update` recolors the live edge draws
in place.

A thickness is a FULL width in DEVICE pixels — every line shader normalises its
extrusion by the drawing buffer, never the CSS size, and the fragment stage
filters a box with a symmetric ±0.75 px kernel. Integrated coverage equals the
nominal width even for subpixel lines, and zero width has zero coverage. Both
line paths share the filter; antialiasing does not inflate thin lines or depend
on the framebuffer sample count.

Per-occurrence highlight, dim, hide, isolation, exploded placement and selection are the
scene's own state (`setHighlight`, `setHiddenPartIds`, `setExplode` on the scene contract,
`lib/viewer/sceneContract.js`); a rebuild of the open file keeps every part buffer and
geometry whose key the new version still holds, and builds only the parts the edit changed
(ownership and disposal: [resource-ownership.md](resource-ownership.md)).

### `common/renderModel.js`

Use this module for interactive browser canvases, including the docs hero.

```js
import { renderModel } from "@text-to-cad/core/common/renderModel.js";
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

It frames the model with `fitCameraToModel(THREE, camera, bounds, options)`, the
orthographic fit the module exports: the bounds' corners inside `padding` (0 to 0.15, as
`framePadding` bounds a snapshot's) from `direction`.

### `common/renderMeshScene.js`

Use this module for deterministic headless snapshot rendering.

```js
import {
  renderJobContext,
  renderModel,
  captureModel
} from "@text-to-cad/core/common/renderMeshScene.js";
```

`renderJobContext(meshData, job)` resolves the shared scene contract plus
snapshot-owned output policy: display, camera, quality, scene scale, outputs, the edges
the view offers, and warnings. Studio scene quality is Preview's final when the job asks
for `preview`; `quality` is the scene preset's render scale and shadow and environment
sizes, and the job's `output.renderScale` overrides the first. A family scene passes
`{ bounds, partCount, explodeParts }` for `meshData`; its job's kind resolves the view
features (`viewFeaturesForKind`): an engine document has edges and every mode, any other
family none, Parts only with several parts, and Explode only for a GLB of several.

Snapshot `renderModel(THREE, model, { job, context })` holds a family scene wrapped by
`headlessSceneModel` and returns a headless viewport:

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
Render is drawn through the studio's frame, every sample of it at once
(`renderStill`: `PHOTOGRAPHIC_STUDIO_FRAME.stillSamples`, 32, re-rendering shadows only for a
sample that moved the key), with no MSAA of its own: the snapshot supersamples at its render
scale. A software renderer draws one sample (`snapshotStudioSamples`).
It uses snapshot sizing, studio environment, the shared stage floor/glow/shadow,
model-scaled lights with a fitted shadow frustum, canonical camera projection,
and deterministic renderer settings. Automatic perspective cameras fit the
current visible vertices to `output.padding` when `output.tightFrame` is true;
otherwise they fit the model bounds. An explicit camera position is never
reframed. As in the viewer, a still's studio floor
and its contact shadow stay sized and centred on the rest placement however the
model is posed or exploded (`groundBounds`), and an exploded view radiates from
that rest box.

`captureModel(viewport, { job })` returns data only:

- `mode: "view"`: PNG data URLs in `outputs`.
- `mode: "list"`: part list and bounds. A family scene lists what it drew, one row per mesh,
  in its scene graph's order (a robot's scene attaches a link's meshes before the joints it
  carries, so its rows run down the tree from the root).

It does not write files: its caller does. Consumers use compiled `@text-to-cad/core`
exports; the OCCT parity bench bundles this entrypoint into a snapshot page of its own, built
on demand outside the wheel, and loads it in a headless Chromium to compare with OCCT's stills.
cadgen's own snapshots are drawn by OCCT and never load it.

### `common/headlessScene.js`

The snapshot page's half of "one scene builder per file family". `headlessSceneFamily(job)`
answers, from the job's resolved kind, the family whose loader and builder draw it (GLB;
STL and 3MF; URDF, SRDF and SDF; an engine document, `xbf`, whose `resolved.url` is its API
URL on the engine: `loadXbfDocument` + `createXbfScene`), or null for a STEP document. The
dress carries the view's `edges` too, for a scene that draws CAD edges of its own (an engine
document's), as the xbf renderer hands them to its scene in the viewer. A family is
`{ load(job, { resources }), build(THREE, loaded, job), release(loaded) }`, each a call to
the module the viewer's renderer calls: `loadRenderGlbDocument` + `createGlbScene`,
`loadRenderMeshByUrl` + `buildMeshScene`, `loadRobot` + `createRobotScene`. A robot is
drawn from the payload cadgen resolved for it (`resolved.robot`: the articulation, the
visuals at their rest placements, each mesh by a URL the snapshot's asset server answers)
and posed as it is built, at the articulation's opening (every control at rest, then an
SRDF's `home` group state: where the viewer opens it) with the job's `resolved.controls` on
top, the bench's control values (`cadgen snapshot` poses a robot by `--pose`).

`headlessSceneModel(THREE, scene, headlessSceneDress(context.sceneSettings))` dresses the
scene exactly as the viewer's viewport dresses one it adopts, with the look
`resolveSceneSurfaceLook` resolves (`common/sceneSettings.js`, which the viewport calls
too) and shadows while the lighting is on, and exposes what `renderModel` and
`captureModel` read of any model: `root`, `bounds`, `restBounds` (what sizes the ground),
`keepsAuthoredFinish`, the drawn meshes for the tight frame, `listParts()` and `dispose()`.
The still's tight frame reads a skinned or morphed mesh where the GPU draws it.

## Kinematics

A still of a robot is posed as the viewer opens it — every control at rest, then an SRDF's
`home` group state — with the job's `resolved.controls` on top (`scene.setControlValues`,
`common/articulation.js`), the parity bench's control values. `cadgen snapshot` poses a
document's or a robot's mechanism by `--pose`: a mechanism state's name, or a JSON object of
joint values; a Quick Edit packet carries the same as `jointValues`.

## Examples

Docs usage, the hero: one GLB cadgen exported, read and played the way the viewer reads
and plays a GLB, and drawn by `renderModel` from a model of a root and its bounds:

```js
import * as THREE from "three";
import { buildGlbDocumentFromBuffer } from "@text-to-cad/core/lib/render/glbMeshData.js";
import { createGlbAnimationRuntime, setGlbAnimationTime } from "@text-to-cad/core/lib/render/glbAnimationRuntime.js";
import { renderModel } from "@text-to-cad/core/common/renderModel.js";

const glb = await buildGlbDocumentFromBuffer(await (await fetch("/hero/planetary.glb")).arrayBuffer(), {});
const placed = new THREE.Group();                 // the file in CAD space: millimetres, Z up
placed.matrix.fromArray(glb.cadRootMatrix);
placed.matrixAutoUpdate = false;
placed.add(glb.scene);
const root = new THREE.Group();
root.add(placed);

const clip = glb.clips.find((candidate) => candidate.name === "meshCycle");
const animation = createGlbAnimationRuntime(THREE, glb.scene, clip);
let elapsed = 0;
const viewport = renderModel(THREE, { root, bounds: glb.animatedBounds }, {
  canvas,
  hostElement: canvas.parentElement,
  theme,
  autoStart: true,
  beforeRender: ({ deltaSeconds }) => {
    elapsed = (elapsed + deltaSeconds) % clip.duration;
    setGlbAnimationTime(animation, elapsed);
  }
});
```

A headless snapshot (`headlessRenderEntry.js`) paints a DXF on a 2D canvas
(`common/headlessDrawingRender.js`) and draws a file family through
`common/headlessScene.js` into the same `renderModel`/`captureModel`; a STEP is drawn as
the engine document it opens as.

## Ownership Rules

- Do not write files from shared render APIs. Return data to the owning CLI or
  application layer.
- Dispose viewports and models that you create.
- Prefer a family's scene builder, then `renderModel` and `captureModel`, for new
  shared render code instead of loading assets or constructing render scenes
  inline.
- Draw a GLB, a mesh file, a robot or an engine document with its family's scene builder, in
  the viewer and on the parity page alike. Never give one host its own way to draw a family:
  `scripts/test/check-kit-boundaries.mjs` (`checkSharedSceneBuilders`) refuses it.
