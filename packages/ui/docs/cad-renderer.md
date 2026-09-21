# CAD renderer

The CAD viewer is the viewport, floating toolbar, file sheets, reference
interactions, measurement and drawing tools, animation, loading artwork and
alerts, extracted into `@hardcore/ui`. This migration is a behavior-preserving
refactor apart from the approved prompt-action mapping and reference-tooltip
removal described in [ViewerHost](viewer-host.md). Changing a default, control,
layout, saved preference or interaction requires separate work and its own
review.

It is no longer one component stack: there is one renderer per file family over
a shared, format-blind [kit](#kit) and [shell](#shell). The STEP renderer is
under `src/renderers/step`: its scene and everything of it that lives in the
viewport are on the kit ([STEP scene and viewport](#step-scene-and-viewport));
`CadFileView` is still its private surface. Applications use the registrations and the shared
`FileViewer`; they do not import another application's source.

## Kit

`src/renderers/kit` is the format-blind half of the viewer: small modules a
renderer composes, none of which asks what it is showing. There is one renderer
per file family, each a vertical slice over the kit: `src/renderers/dxf`
([DXF renderer](#dxf-renderer)), `src/renderers/glb` ([GLB renderer](#glb-renderer)),
`src/renderers/mesh` (STL and 3MF, [Mesh renderer](#mesh-renderer)),
`src/renderers/robot` (URDF, SRDF and SDF, [Robot renderer](#robot-renderer)) and
`src/renderers/step` (STEP and STP, [STEP renderer](#step-and-source-separation)). The kit imports itself, shared UI
(`primitives`, `lib`, `drawing`) and the format-blind half of `@hardcore/core`
(`lib/viewer/*`, `lib/perspective.js`, `common/viewSettings.js`,
`common/sceneSettings.js`, the Render studio); a renderer imports the kit, never
the reverse.

| folder | what it is |
| --- | --- |
| `viewport/` | `useViewerRuntime` (three.js renderer lifecycle, on-demand render loop and `requestRender`, resize and device-pixel-ratio caps, context loss, keyboard orbit, teardown), `framePresentation`, `viewportBuffer`, `renderDepthPolicy`, `sceneObjects` (`disposeSceneObject`), DOM helpers. The scene in the viewport is its owner's: teardown calls the injected `disposeScene(runtime)` and `disposeStudio(runtime)`. |
| `camera/` | `runtimeCamera` (zoom percent against the authored framing, projection and lens sync, perspective snapshots, eased transitions, fit-to-bounds, recentre), `useViewportCamera` (that behaviour bound to a mounted viewport: the perspective a session stores, the fullscreen camera swap and its restore, the reset, view-cube presets — whose default preset FRAMES as well as turns), `viewportCameraKit` and `viewportCameraFit`, `orbitControls`, `zoomPivotReanchor`, `zoomSpeeds`, `cameraLens`, `ViewPlaneControl` (view cube). |
| `look/` | `stageEffects` (lighting rig scaled to the model, floor, glow and shadow catcher, grid and origin axes), the Render studio boundary (`renderStudioChunk`, `studioEnvironmentCache` and its worker). `chromeBackdrop` and `useChromeBackdropColor` (the frame colour around a scene). The surface LOOK is data the viewport resolves and a scene applies to its own materials: `@hardcore/core/lib/viewer/surfaceLook.js` (`createSurfaceLook(THREE, root).apply(look)`) does it for any authored material tree. |
| `view-settings/` | The settings model and store (`viewSettingsStore`, `useViewSettings`, `viewerDisplaySettings`, `renderState`), applying a change to a viewport (`useAppliedViewSettings`, `viewUpdateCoordinator`, `viewUpdateGate`, `viewUpdatePlan`), and the Display tab (`DisplaySettingsTab`, `DisplayModeOptions`). |
| `tools/` | `FloatingToolBar` (the dumb strip), `toolModes` (the tool-mode state machine), `ToolbarButton`, and the format-blind tools: `draw/` (overlay, view lock, `useDrawingViewLock`), `fullscreen/` (controls and the orbit preference), `playbar/` (`ViewportAnimationBar`, `animationClock`, `usePlaybackFrames`), `pose/` (the handle overlay, canvas, drag mathematics), `select/` (`usePointerPick`: taps and hover through a scene's own `pick`). Screenshot capture is `@hardcore/core/lib/viewer/screenshotCapture.js`. |
| `inspector/` | `FileSheet` and its row primitives, `FileSheetTabbedSurface`, `activeSection`, `InspectorSplit`, `modelTreeSearch`, `referenceRows` (`InfoRow`, `MonoValue`, `CoordValue`), `kinematicsControls` (the named-position dropdown and the Reset button every Kinematics tab ends with). The tree row and filter box are `primitives/tree-row` and `primitives/tree-filter`. |
| `status/` | `LoadingIndicator` and `ViewerLoadingOverlay`, `ViewerAlertDialog` and `ViewerAlertBody`, `BlockingViewerAlert`, `MissingFileAlert`, `StatusToast`, `ViewUpdateStatus`, `useFileActivityReport`, `loadingState` (`viewerLoadingState`), `fileStatus` (`resolveFileStatus`, the chip beside the filename), `loadAlerts` (`failureAlert`, `noGeometryAlert`, `resolveFileStatusAlert`). |
| `shell/` | The host glue every renderer needs that is not about its scene: see [Shell](#shell). |

**What a view opts into.** The Display tab and `resolveViewSettings` take explicit
lists, `features: { sections, modes, surfaceStyles }` (`ViewFeatures` in
`@hardcore/core/common/viewSettings.js`): the sections the tab mounts
(`VIEW_SECTION_IDS`), the presets and the surface styles it lists. A section left
out resolves off whatever was saved, and the saved settings are never rewritten.
Core names two lists, `ALL_VIEW_FEATURES` and `EDGELESS_VIEW_FEATURES` (no Edges,
Clip or Explode; Solid and Render; Shaded and Flat). The STEP renderer passes the
first, in three places that must agree: the view-settings store (`configure({ features })`), the Display tab,
and the headless renderer (`renderMeshScene.js`). The GLB, mesh and robot renderers
pass the second to the shell, which configures the store and the tab from the one list.

**Tools.** The strip draws the list it is handed: `{ id, label, icon, active,
disabled, onSelect, description?, menu?, secondPressOpensMenu?, subToolbar? }`.
`cadInteractionTools` in `step/components/workbench/FloatingToolBar.js` builds
the STEP renderer's list. `createToolModes({ defaultMode, modes })`
answers what a press does (`next`), what a saved tab may record (`persisted`) and
which tool a file opens in (`restore`); the STEP declaration is
`CAD_TOOL_MODES` in `workbench/constants.js`. The playbar follows the clock on
the runtime it is handed (`runtime.clock`, an `AnimationClock`); the Pose overlay
takes a plain handle list, as a prop or (for an owner that poses its model
outside React) as a ref whose list it replaces per pose.

**The scene contract** (`kit/scene.js`, a JSDoc typedef): `{ object3D, bounds,
restBounds?, dispose(), setSurfaceLook?(look), setShadowReception?(receives),
keepsAuthoredFinish?, complete?, pick?(ray), placedObjects?() }`.
The viewport adopts `object3D`, frames `restBounds`, lights and floors `bounds`,
and hands over the surface look the Display tab resolved
(`{ materialSettings, authored, surface: { style, opacity } }`); it only ever
detaches a scene, whose owner disposes it. `buildModel`
(`@hardcore/core/common/cadScene.js`) exposes `object3D`, `bounds`, `restBounds`
and `dispose()`; the GLB and mesh renderers' scenes implement all of it but `pick`,
and the robot renderer's all of it. `pick(ray)` is what `usePointerPick` calls: the
hook owns the pointer (which press is a tap, one hover pick per frame, the
cursor), the scene says what is under the ray, and its renderer says what a hit
means. A tap acts at once: nothing waits to tell it from a double-click.
`placedObjects()` is for the near/far fit alone: a camera inside a mostly empty
aggregate box can still be well outside everything visible in it, so a scene that
placed many things says so and is fitted on them instead of on its whole box.
Shadow reception is the viewport's for every mesh of a scene, unless the scene
implements `setShadowReception`: a scene with unlit or see-through surfaces is told
the setting and applies its own rule (a STEP's watch crystal never takes a shadow).
A mesh names where "Color by part" deals it a palette colour in
`userData.cadFillIndex` (otherwise meshes take the palette in traversal order),
and a material with no source colour says so with `userData.cadSourceColor = false`.

**The rule and its check.** Kit code names no file format, no file-kind switch
and no STEP-assembly concept (topology, selectors, display records, explode,
section clipping), in code or in comments; only `view-settings/` may name the
Clip and Explode sections a view opts into. `npm run check:boundaries` runs
`scripts/test/check-kit-boundaries.mjs`, which scans every kit source for imports
of a renderer or of a file-family core module and for those words, against a
short allowlist that carries a reason per line and fails when an entry goes
stale. The same script holds every split-out renderer to its slice
(`RENDERER_SLICES`): a renderer imports the kit, `renderers/workspace` (the
backend connection a file is prepared against, the host's viewer preferences and
command types, and `useWorkspaceDocument`), shared UI and core, and never another
renderer. The
unbound-identifier test (`src/renderers/unboundIdentifiers.test.js`) scans the
whole renderer tree, so a renamed or added slice is covered the moment it
exists.

### Shell

`kit/shell` is what a file-family renderer needs from its host that is not about
its scene. A renderer loads its document, builds its scene (`kit/scene.js`) and
calls one hook; the shell owns the rest.

| module | what it is |
| --- | --- |
| `useRendererShell.js` | The hook. Per-file state through the host, the Display settings store and tab, tool modes (Draw is the only tool the shell itself owns; `toolModes` is omitted altogether by a renderer with no tools), the Inspector panel (and its control by the renderer), navbar actions, prompt snapshots, the clipboard screenshot, fullscreen, file activity, alerts, shortcuts, and the live command surface. It owns no zoom control: the shell has none. |
| `RendererShell.jsx` | The frame: viewport box, tool strip, bottom action, playbar, fullscreen controls, loading/update/alert overlays, status toast and the Inspector portaled into the host's panel column. One DOM structure (`data-slot="cad-file-view"`, `data-cad-surface`, `data-cad-scene-backdrop`, `data-cad-toolbar`, `data-file-sheet`) for every renderer. |
| `ShellViewport.jsx` | The three.js viewport around ONE kit scene: `useViewerRuntime`, `useViewportCamera`, the look (rig or studio, environment, background, floor, grid, axes), the Draw overlay and view lock, the view cube, frame presentation and the queued view-settings handshake. Its children may be a function of the viewport (`{ runtimeRef, hostRef, mountRef, viewerReadyTick, commitScene }`), which is how a renderer mounts its own overlay or pointer pick. A scene that changes IN PLACE (it arrives in pieces, swaps its detail, is rebuilt under one identity) calls `commitScene()` from its own effect: the viewport re-reads what it placed, fits the stage and the depth range and applies the framing rules THEN, because a child's effects run before the viewport's own adoption effect. The one thing a commit never does ahead of the viewport is FRAME under a camera that is about to change: when the same render also changed the lens, the projection or the viewing mode, the stage is adopted at once and the framing follows once the camera has been given those props (a stored camera applied under the old projection and then converted comes out about a sixth smaller). A scene that says `complete: false` is framed on what has arrived and once more when it is whole. `preserveInteractionPixelRatio` keeps the idle pixel ratio while the camera moves (a scene drawn with hairlines), and `runtimeLifecycle` (`onRelease(runtime, { handoff })` while the WebGL renderer is still alive, `onContextLost()`, `onInitializationError(error)`) is for a renderer that hangs its own objects or in-flight work on the runtime. `syncSceneBounds()` re-fits lighting, shadows and the floor's height to a scene that moved its own bounds, with no React render and no reframe. What is SIZED stays sized from the rest placement, in Inspect and in Render alike: the grid and stage (`sceneRadiusForBounds` on `restBounds`) and the Render studio's floor plane (`applyPhotographicStudio`'s `groundBounds`), so a pose or a playing routine never rescales or slides the ground under the model; `zoomToBounds(bounds)` frames part of the scene. Read-only test seams: `window.__cadCamera()` (the live camera) and `window.__cadStage()` (the ground's radius, the bounds the stage is fitted to, the floor's height, the studio floor's size and centre). |
| `shellState.js` | The per-file record `{ version, camera, display, inspectorTab, tool, renderer }`, read forgivingly and written exactly. The host keys it `[file path, renderer id]`. |
| `liveBinding.ts` | `attachLiveBinding`: the live command surface. Base commands (`readState`, `setCamera`, `resetCamera`, `setDisplaySettings`, `setRenderMode`, `capture`) mean the same for every renderer; a renderer ADDS commands by name and DECLINES the known host commands (`HOST_LIVE_COMMANDS`) that make no sense for it with the sentence the caller reads. Binding fails when a renderer does neither. |
| `promptContext.js` | `createViewPromptContext` (a snapshot and what it depicts) and `promptDeliveryMessage`. |
| `useViewerShortcuts.js` | Which mounted viewer an Escape belongs to; the renderer says what Escape means. |
| `ViewportBottomAction.jsx` | The active tool's one bottom button (Draw: the view with its ink, to the prompt or clipboard); `{ label, shortLabel, render }` for a renderer's own, where a label too wide for the button becomes `shortLabel` and `render` draws a control that is not a plain press. |
| `ViewportContextMenu.jsx` | The viewport's menu on a secondary TAP (a secondary drag pans; primary and secondary together is the pan chord). The gesture, the anchor, the clamping and the dismissal are the shell's; the ITEMS are the renderer's (`contextMenuItems(press)`), asked at the moment of the press, and `onContextMenuOpenChange(open)` says while the menu is up. A renderer that passes no items has no viewport menu at all — every renderer but STEP. |

```jsx
const shell = useRendererShell({
  view,                 // RendererViewProps, unchanged
  services,             // { preferences, onPreferenceChange, live?, captureRequest?, acknowledgeCommand? }
  resource, modelKey, revisionKey,
  features,             // ViewFeatures: the Display sections this family opts into
  toolModes,            // createToolModes({ defaultMode, modes }), or omitted: no tools at all
  scene,                // KitScene | null
  load,                 // { busy, updating?, progress?, alert? }: the renderer's document load
  animation,            // playbar runtime with its own `clock`, or null
  live,                 // { commands?, declined?, state? }
  // optional: promptReferences, escape, displayTabProps, sceneScaleMode,
  //   rendererState   the renderer's slot of the record: an object, or a FUNCTION read when the record is written
  //   toolRestore     { opensIn, never }: the tool THIS file opens in, while the tool modes' default stays the fallback
});
// Renderer-facing, beside `tools`, `displayTab`, `toolMode`, `selectTool`, `requestRender`:
shell.inspector.reveal(tabId);   // turn to a tab, opening the panel where there is room beside the model
shell.inspector.setOpen(open); shell.inspector.setTab(tabId);   // and { open, tab }
shell.syncSceneBounds();         // the scene moved its bounds (a pose): the stage follows, no render
shell.scheduleStateSave();       // state kept outside React changed: write the record soon, and on unmount
const tools = [shell.tools.own({ id, label, icon }), shell.tools.draw].filter(Boolean);   // or [] for no strip at all
return <RendererShell shell={shell} tools={tools} inspector={{ title, tabs: [...own, shell.displayTab] }}
  viewportOverlay={viewport => <PointerPick viewport={viewport} scene={scene} enabled={selecting} onPick={pick} onHover={hover} />} />;
```

A renderer whose model moves outside React (a robot's pose) keeps that state in
its own store: `rendererState` as a function is read at the moment the record is
written, so the last write before unmount is saved; `shell.scheduleStateSave()`
says it changed; `shell.syncSceneBounds()` carries the moved bounds to the stage.
None of them renders a component.

The workspace half of a renderer's surface is one hook too
(`renderers/workspace/useWorkspaceDocument.js`): `useWorkspaceDocument({ view, data })`
returns the live catalog entry of the prepared file, the prompt `resource`, the
`services` object the shell takes and the host's commands;
`workspaceLoadAlert` turns a catalog or loader failure into `load.alert`; and
`useDeclinedSelectReference` consumes a host's request to select a reference in
a file that has none and answers it in the status toast. A renderer is then its
scene hook, its tool list and its tabs (`glb/GlbRenderer.jsx`, `mesh/MeshRenderer.jsx`,
`robot/RobotRenderer.jsx`). The DXF renderer uses the workspace module without the
shell: it has no scene, so it reaches the same catalog entry and commands directly.

The shell's behaviour has one real-browser test,
`kit/shell/RendererShell.browser.test.mjs` (deferred files, warm reopen, isolated
per-pane state, fullscreen's camera, gated Display sections, settings that never
replace the canvas), and Draw has one scenario (`harness/drawScenario.mjs`)
run under the shell (`kit/tools/draw/Draw.browser.test.mjs`).

The STEP renderer's scene and viewport are on the kit
([STEP scene and viewport](#step-scene-and-viewport)); its FRAME, its per-file
record and its host glue are still `CadFileView.js`'s own copy, which shares the
leaf pieces (`liveBinding`, `loadAlerts`, `fileStatus`, `loadingState`,
`BlockingViewerAlert`, `useViewerShortcuts`, `promptDeliveryMessage`,
`chromeBackdrop`). Moving that surface onto `useRendererShell` is what is left
of the split.

Its safety net is `step/StepRenderer.browser.test.mjs`, which opens a real `.step`
in a real browser: a three-part component-SURF package with one revolute mate, one
named pose and one routine, committed under `step/__fixtures__/step/` and served by
`harness/stepScenario.mjs` exactly as the backend serves one.
`kit/tools/draw/Draw.browser.test.mjs` covers the Draw scenario under the shell,
and each renderer's own browser test asserts that the STEP-only Display sections
are absent from it. The shell surfaces only STEP uses so far (the viewport menu and
its open report, the measured bottom action, the camera-settled report, a scene
that arrives in place, the pixel ratio kept for hairlines, the runtime lifecycle)
are driven through `renderers/shell-harness` in `RendererShell.browser.test.mjs`.

## DXF renderer

`createDxfRenderer` (`@hardcore/ui/renderers/dxf`, id `dxf`) shows a `.dxf`. The CAD
renderer does not match one.

It is **not on the shell**, and that is the whole design: a DXF is a finished 2D
document, so the pane is a canvas and the drawing is painted on it. No three.js, no
viewport, no scene, no Inspector, no Display settings, no tools, no toolbar. The
questions the old Material/Bends/Layers tabs answered were about a sheet-metal part
the viewer was inventing from the file; a drawing is not that.

- **The picture comes from the BACKEND.** `client.drawing(file)` is one
  `GET /__cad/drawing` (`apps/web/docs/backend.md`): ezdxf flattens the modelspace on
  the server — text outlined, dimensions exploded, hatches filled, blocks placed — and
  the client receives five primitive shapes in DXF coordinates, y up. **This renderer
  never parses DXF.** The payload is cached server-side by the document's content
  hash, so reopening a file costs a round trip and nothing else.
- **Drawing is core's** (`@hardcore/core/lib/drawing2d`), so the headless snapshot
  bundle paints the same picture from the same payload: `fitTransform` / `zoomTransform`
  / `panTransform` (one uniform scale and a translation; the y flip lives in the
  transform, not in the geometry), `prepareDrawing(payload)` (paths built ONCE, per
  colour for strokes and per primitive for fills) and `drawDrawing(ctx, drawable, …)`.
  That bundle IS `cadgen dxf snapshot`: cadgen resolves a `.dxf` to the same
  `cadgen.drawing_payload` this route answers with and the page fits and paints it
  (`common/headlessDrawingRender.js`), so a CLI render cannot show what this pane
  cannot. The CLI's option surface was cut to match — no camera, no display, no
  render mode, `--appearance light|dark` and a size.
- **Hairlines, always.** Strokes are 1.25 CSS px at every zoom, as AutoCAD draws with
  LWDISPLAY off: paths are in MODEL space and the context carries the view, so one
  `lineWidth = 1.25 / scale` per frame rebuilds no geometry. Model-space lineweights
  are not displayed at all.
- **`color: null` is the default pen** (ACI 7, "whatever contrasts with the
  background"), resolved at DRAW time against the app's `--foreground` on its
  `--background` — the same pair the 3D viewers' chrome uses. One payload therefore
  serves both themes: flipping `.dark` repaints, it does not refetch. The tokens are
  read off the pane, and a mutation on `<html>` schedules a frame. When they cannot be
  read — and in the snapshot bundle, which has no stylesheet at all — the pair comes
  from `@hardcore/core/lib/appTheme.js`, the one place both colours are written down.
- **Fills are even-odd, and each one is filled on its own.** A `filled-paths`
  primitive's inner rings are its holes; merging two overlapping regions of one colour
  into a single path would turn their overlap into a hole as well. Fills go down
  before strokes, which is the one ordering that never hides an edge.
- **Interaction** (`dxf/useDrawingView.js`): fit on open and on resize until the
  person moves the view, drag to pan (any primary press, one finger), wheel or pinch to
  zoom about the pointer, double-click to fit again. The view lives in a REF and the
  canvas repaints through one `requestAnimationFrame` when something changed; a pan
  never re-renders the component tree. The backing store is DPR-aware
  (`kit/viewport/pixelRatio.js`), and the cursor is `grab` / `grabbing`.
- **Navbar**: `Take snapshot`, and nothing else — no Inspector toggle, because the
  renderer declares no panel, and no zoom buttons, because zooming a drawing is the
  pointer's: wheel or pinch about it, drag to pan, double-click to fit. The snapshot is
  the canvas as a PNG, background included, delivered through `host.promptContext`
  like every other renderer's.
- **Empty and failed drawings.** `bounds: null` (nothing in the modelspace) is a quiet
  sentence over the empty pane, not an error. A non-200 becomes the ordinary actionable
  alert carrying the SERVER's sentence (`failureAlert`, `kind: "http"`); a payload from
  a cadgen that disagrees about `schemaVersion` gets its own alert whose recovery is to
  update cadgen and the app together.
- **Host commands**: `resetCamera` fits the drawing again, `capture` hands over the
  PNG, and `readState` reports `camera: null` and an empty `display`. There is no zoom
  command and no zoom percentage: no host ever sent one. `select`,
  `clearSelection`, `setCamera`, `setDisplaySettings` and `setRenderMode` are each
  declined with a sentence that says why a flat drawing has no such thing; a
  `selectReference` host request is consumed and answered in the status toast.
- **State** under `[path, "dxf"]`: `{ kind: "dxf-view", version: 1, transform }`, and
  only once the person has MOVED the view — an untouched drawing stores nothing, so it
  reopens fitted to whatever pane it lands in. A hard cutover: every record the 3D DXF
  viewer wrote (thickness, bends, hidden layers, 2D/3D, a camera) reads as nothing
  stored.
- **Fixture and test**: `dxf/__fixtures__/sample.drawing.json` is exactly what the route
  answered for `sample.dxf` (default-pen line-work, a red circle, a solid hatch with an
  island, TEXT, a bulged LWPOLYLINE); `make_fixture.py` regenerates the pair.
  `DxfRenderer.browser.test.mjs` serves it and asserts on PIXELS — the fit, the theme
  flip, the red circle, the unfilled island, the hairline at 800%, zoom about the
  pointer, pan, re-fit, the resize rule, and that no sidebar, tab or tool strip exists.

## GLB renderer

`createGlbRenderer` (`@hardcore/ui/renderers/glb`, id `glb`) shows a `.glb` as
its NATIVE glTF scene, always: one path whether or not a clip is playing. The
STEP renderer does not match `.glb`.

- **Scene** (`glb/glbScene.js`): the file's hierarchy (nodes, skins, morph
  targets, authored materials) placed in CAD space by the document's root
  matrix. Embedded lights stay hidden, skinned and morphed meshes are never
  frustum-culled, every mesh casts shadows. The scene owns its document and
  releases its geometry, materials and textures. Bounds are the box sampled
  over every clip at load, so a playing clip never re-frames or re-lights.
- **Look**: Inspect wears the viewer's surface (a physical stand-in with the
  viewer's roughness, metalness, clear coat and trace emissive) and keeps what
  identifies a part: its colour, maps and opacity. Photographic Render restores
  the authored materials exactly. Surfaces apply in both: Flat is unlit, Single
  colour and By part override source colours and maps (the palette cycles per
  mesh), opacity scales the authored opacity. A material without a source colour
  (`userData.cadSourceColor === false`: no materials in the file, a writer's
  flag, or the grey a STEP export stamps on uncoloured parts) takes the viewer's
  surface colour in Inspect.
- **Display**: `EDGELESS_VIEW_FEATURES` (Solid and Render; no Edges, Clip or Explode).
- **Tools**: none. A GLB picks nothing, so there is no Select, no filter menu, no
  copy-references action — and no tool strip and no viewport context menu either.
- **Animation** (`glb/useGlbAnimation.js`): a file with playable clips shows the
  kit playbar under the model, always: it is a transport, not a tool to take up
  and leave, and fullscreen shows the same one. The file OPENS AT REST — one
  `AnimationMixer` on the native scene, built by the first play, scrub or clip
  choice and alive only while a routine owns the pose — so the bar appearing
  changes nothing on screen.
- **Inspector**: the single Display tab; the panel starts shut
  (`inspectorPanels(ready, { defaultOpen: false })`).
- **Host commands**: the base live commands; `select` and `clearSelection` are
  declined with a sentence, and a `selectReference` host request is consumed and
  answered in the status toast.
- **State**: the shell record under `[path, "glb"]`. Records written under
  `[path, "cad"]` are not migrated.

## Mesh renderer

`createMeshRenderer` (`@hardcore/ui/renderers/mesh`, id `mesh`) shows an `.stl`
or a `.3mf` as what it is: triangles, and in a 3MF a colour per object. The CAD
renderer does not match either.

- **Scene** (`mesh/meshScene.js`): one `Mesh` per object of the file (an STL is
  one; a 3MF has one per object and material) and nothing else: no part table,
  display records, edges, clip planes, explode matrices or selectors. Geometries
  come from `@hardcore/core/lib/render/meshObjects.js` (`buildMeshObjects`): views
  over the arrays core decoded, never copies, with the display normals of
  `meshNormals.js` (creased at 30° up to `CREASED_NORMAL_MAX_TRIANGLES`, plain
  vertex normals above it) and a 3MF's build transforms baked in.
- **Loading** (`mesh/useMeshScene.js`): core's `loadRenderMeshByUrl`, so an STL is
  parsed in the STL worker where there is one, a 3MF that three's loader rejects
  falls back to the package reader, and the decode is cached per file revision:
  reopening a file fetches and parses nothing. Progress reads "Reading model",
  then "Loading geometry 0/1". A new revision replaces the scene when it is ready.
- **Look**: a mesh authors no finish, so Solid wears the viewer's surface and
  Render the studio's, over the same colours (`setSurfaceLook` never keeps an
  "authored" finish). Original keeps each object's source colour; an object
  without one takes the viewer's surface colour, and once one object of a 3MF is
  coloured the rest keep the colour their material carried. Flat is unlit,
  Single colour and Color by part override source colours (the palette is dealt
  in the order it always was, `paletteIndex`), opacity applies to every object.
- **Display**: `EDGELESS_VIEW_FEATURES` (Solid and Render; no Edges, Clip or Explode).
- **Tools**: none. A triangle mesh has nothing to pick, measure, pose or play, so
  there is no tool strip over the viewport and no viewport context menu; fullscreen
  offers its orbit settings, as it does for every format.
- **Inspector**: the single Display tab, titled `STL` or `3MF`; the panel starts shut.
- **Alerts**: a file that fails to parse raises the load alert ("Couldn’t load
  the model", with the loader's error in Details); one that parses to no
  triangles raises "No geometry to display".
- **Host commands**: the base live commands; `select` and `clearSelection` are
  declined with a sentence, and a `selectReference` host request is consumed and
  answered in the status toast.
- **State**: the shell record under `[path, "mesh"]`. Records written under
  `[path, "cad"]` are not migrated.

## Robot renderer

`createRobotRenderer` (`@hardcore/ui/renderers/robot`, id `robot`) shows a
`.urdf`, `.srdf` or `.sdf` as its kinematic tree. One renderer, three parsers:
an SRDF is its paired URDF with the SRDF's semantics on it (group states, end
effectors, planning groups), an SDF a robot with one more tab. Nothing below the
loader asks which it is. The STEP renderer matches none of them.

- **Scene** (`robot/robotScene.js`, no React, no DOM): a scene GRAPH. One `Group`
  per link, a link's meshes attached to it once, and each joint as three nested
  frames: the static parent-to-joint frame, ONE motion group, then the child link
  (at an SDF joint's static child offset, else identity). A pose writes the
  motion matrices of the joints that changed (the joint and its mimic followers;
  `jointMotionTransform`, values resolved by `resolveUrdfJointValues`, both in
  core's `urdf/kinematics.js`) and nothing else: no geometry, no material, no
  part list, no React state. Core transforms are row-major, so matrices are
  written with `Matrix4.set`. Every link group is where the description solver
  (`solveUrdfLinkWorldTransforms`) puts that link; the unit test holds the graph
  to it for random poses. `bounds` follows the pose (only the moved subtree is
  re-measured); `restBounds` is every joint at its declared default, whatever
  pose the file opens in, and is what the camera frames and the ground is sized
  from. Picking raycasts the link meshes (each geometry's BVH is built in idle
  time once a ray reaches it, core's `raycastBvh.js`) and walks up to the link
  group; a named object of a link's mesh is itself.
- **Parts** (`robot/robotParts.js`): built once per load. One part per visual, or
  per NAMED object of a visual's mesh (`head:v1/object/0`), with its link, local
  transform, source mesh and palette place. Geometries wrap the loader's arrays
  and are shared by visuals that name one mesh.
- **Loading** (`robot/useRobotDocument.js`): core's `loadRenderUrdf`, `loadRenderSrdf`
  or `loadRenderSdf`, then every distinct link mesh (`loadRenderMeshByUrl`, at most
  eight at a time). Progress reads "Loading URDF", "Loading meshes 3/13",
  "Building robot". The robot is published once, whole. A missing link mesh fails
  the load. A warm file is on screen on the first render; a new revision loads
  behind the robot on screen and keeps the pose it was left in. An SRDF with no
  URDF paired (the catalog pairs the ONE `.urdf` in the same folder whose
  `<robot name>` matches) raises an alert that names what was looked for.
- **Look**: a robot authors no finish, so Solid wears the viewer's surface and
  Render the studio's. Colour, in order: the colour the description gives the
  visual; else the colours the mesh brought (per vertex, graded as a material
  colour is); else the named object's own; else the viewer's surface colour.
  A colour the description gives a visual (a URDF `<material>`, an SDF `<diffuse>`)
  WINS over the colours its mesh file carries: this is deliberate, it is what the
  headless renderer does, and it replaces the old viewer's rule, where the mesh's
  vertex colours won.
  Materials are double-sided, so a mirrored `<mesh scale>` cannot turn a link
  inside out. "Color by part" deals the palette in the order parts always took it.
- **Display**: `EDGELESS_VIEW_FEATURES` (Solid and Render; no Edges, Clip or Explode).
- **Tools**, left to right: **Pose** (only with a joint to drag; the tool a robot
  OPENS in: `toolRestore: { opensIn: "pose" }`), **Select** (picks LINKS, under
  its own icon), **Draw**. No Measure, no Animate. Select is the tool a session
  falls back to: ending Draw lands in it, and so does a loaded robot with nothing
  to pose. Fullscreen has no tool and no knobs.
- **Pose** (`robot/poseStore.js`): joint values live in a store outside React
  (degrees; metres for a prismatic joint), with one write path. A write is clamped,
  ignored under `URDF_JOINT_VALUE_EPSILON`, releases the tracked named pose and is
  heard synchronously: the scene poses itself, the handle list is re-read from the
  motion groups' world matrices (`robot/jointHandles.js`), one frame is requested,
  and the stage follows once per frame (`shell.syncSceneBounds`). Only the control
  that shows the value that changed is subscribed to it, so a pose step renders one
  slider row and no other component. On `juno.urdf` (28 links) a knob step cost
  about 270 ms of script when a pose was React state and a re-placed part list; it
  costs about 3 ms with the Inspector shut and about 6 ms with Kinematics open
  (a development React build), which is what a frame costs. The opening pose is
  every joint's default, then the SRDF group state(s) named `home`.
- **Select**: a selection is ONE link or any number of named objects (Shift in
  the viewport; Shift, Ctrl or Cmd on a row). It exists only while Select is the
  tool: choosing a row under another tool returns to Select first, and leaving
  Select clears it. A viewport pick opens the Inspector on Links
  (`shell.inspector.reveal`). Escape clears the selection before it shuts the
  Inspector. Hover and selection are drawn by the scene (`setHighlight`), with
  the highlight ink a STEP part wears; hover is not React state. A robot has no
  viewport menu and so no framing items: its way back to a framed view is the view cube.
- **Inspector**: titled `URDF`, `SRDF` or `SDF`; opens by default, on
  **Kinematics** ("Pose": named poses, only with group states; "Joints": a slider
  per driven joint; Reset; "No movable joints." when there are none). Then
  **Links** ([Robot links](#robot-links)), **SDF** for an `.sdf`, **Display**.
- **Host commands**: the base live commands; `clearSelection` clears the link
  selection; `select` is declined with a sentence (a robot description has no
  reference grammar), and a `selectReference` host request is consumed and
  answered in the status toast. Live state adds `selectedLinks` and `selectedPartIds`.
- **State**: the shell record under `[path, "robot"]`; its own slot is
  `{ jointValues, signature }`, restored only when `signature`
  (`entryUrdfAssetHash`) still matches. The tracked named pose, the selection and
  the tree's disclosure are not stored. Records written under `[path, "cad"]` are
  not migrated.
- **Test seams** (read-only): `window.__cadJointHandles()` (knobs in CSS pixels,
  with values and drawn travel), `window.__robotLinks()` (every link group's frame)
  and `window.__robotPoseStats()` (matrices written per pose, renders of the surface).

## Host integration

```tsx
import { createCadClient } from '@hardcore/core/client';
import { FileViewer } from '@hardcore/ui/file-viewer';
import { createCadPreferences, createStepRenderer } from '@hardcore/ui/renderers/step';
import '@hardcore/ui/styles.css';

const client = createCadClient({
  origin: backendOrigin,
  workspaceId: rootId,
  shouldPoll: () => document.visibilityState !== 'hidden'
});
const preferences = createCadPreferences({
  initial: restoredPreferences,
  onChange: savePreferences
});
const renderers = [createStepRenderer({ client, preferences })];

// Keep client, preferences and registrations stable for this host root.
<FileViewer
  file={path}
  host={host}
  renderers={renderers}
  state={viewerState}
  onStateChange={setViewerState}
/>
```

`source.id` and `workspaceId` identify a stable served root, independently of
the backend's port. The Python catalog/server response supplies `rootId`.
The host owns source access, file selection, URL/history, title, navigation,
the file tree, panel width, browser storage and application color scheme.
It calls `client.dispose()` when the root connection is no longer owned.

`createStepRenderer` accepts an existing client or an async function receiving
`PrepareContext`. The latter lets desktop obtain the local backend only when
opening a CAD file. The host owns backend startup, authorization, and any
runtime recovery actions. Construction does not fetch files or load Three.js.
Preparation resolves metadata with the viewer's abort signal; the component
and viewport are imported lazily after renderer selection.

The STEP renderer declares the Inspector panel, `cad-file-sheet`. The shared
viewer owns its frame and open state; the renderer portals panel contents into
`panelSlot`. The retired `cad-theme` panel is not declared; hosts migrate its
saved selection to the renderer's default Inspector.
The web host owns fullscreen and passes `FileViewer.fullscreen`. The renderer
hides inspection controls and disables picking, drawing, measurement and tool
shortcuts. A transparent fullscreen play bar controls animation. The shared frame hides navigation and sidebars without
changing the saved panel or active tool. Exit restores those controls.

All package exports are compiled ESM with declarations. Consumers need no
source aliases, JSX transforms for dependency `.js`, or cross-app stylesheet
paths. A bundler must support the emitted `new URL(..., import.meta.url)` worker
assets, which remain inside `@hardcore/core`.

## Preferences and per-file state

`CadPreferenceSource` exposes `getSnapshot`, `subscribe` and `update`.
`createCadPreferences` provides an in-memory implementation and an optional
host persistence callback. A host can share one source across its CAD panes.
It contains the global fullscreen orbit preference. Inspector tabs use one
fixed row in each format's canonical order; active selection belongs to the
file, not global preferences. Shared code never reads browser storage on
import or construction.

App light/dark appearance selects Inspect's fixed workbench basis, including
the empty CAD stage. CAD preferences contain no theme choice or custom scene
settings, and legacy saved themes cannot override either Inspect or Render.

Per-file state belongs to `FileViewerState.renderers`, keyed by
`[file.path, renderer.id]` within a host's stable source/root state. CAD stores
the existing versioned file-session slices: display settings, selections,
camera, drawing history, file-sheet sections, kinematic parameters, clip/time
preferences and large-file opt-in. (A robot's joint values are in the robot
renderer's own record, `[path, "robot"]`; a drawing's view is in the DXF renderer's,
`[path, "dxf"]`.) Asset signatures retain
the original invalidation rules. Playback time is saved when stopped or
unmounted, and opening a file does not resume playback automatically.

Hosts preserve these existing preference keys and precedence when migrating:

| Data | Existing storage key / rule |
| --- | --- |
| Directory layout | `cad-viewer:directory-session:v1` (legacy theme fields ignored) |
| Global fullscreen orbit speed | `cad-viewer:orbit:v1` |
| Per-file CAD session | `cad-viewer:file-session:v1:<namespace>:<file>` |

`@hardcore/ui/renderers/step/state` exports the existing tab/file
normalizers and width defaults for migration. `readFileSessionState` requires
an explicit `{ storage }` supplied by the host. `CAD_LEGACY_PREFERENCE_KEYS`
exports the directory key name. Retired
`cad-viewer:file-sheet-tab-layout:v5`, `:v6` and `:v7` records, and a stored
`cad-viewer:pose-transition:v1` preference, are left untouched and ignored:
hosts no longer read, write or subscribe to them.
Legacy per-file lists from a split view select their last available tab; a
stored section ID the current format does not have is simply not open, and the
sheet lands on the format's first tab — there is no table of retired IDs to
keep alive. New interactions save only one active ID. Visited Model trees
remain mounted while hidden so disclosure and scroll survive tab changes.
Origins are transport locations, not persistence namespaces for new state.

## Prompt references, captures and extensions

References, inspection text and PNG captures produce one `PromptContext` through
`host.promptContext`. The old `onReference`, `onPromptContext` and `onCapture`
callbacks are removed. Workspace/path/revision identity and typed targets are
preserved; a capture names the references it depicts. Ordinary explicit copy
controls use `host.clipboard`. The viewport only produces screenshot pixels.
The port and app adapters own delivery and return an acknowledged outcome.

`slots.selectionExtras` is the optional app-contributed selection interface.
Its typed context builder shares the same capture/reference pipeline; it does
not expose the CAD scene. See [ViewerHost](viewer-host.md) for lifetime, focus,
selection invalidation, supported content and clipboard representation limits.

An optional `CadCommandSource` has the same subscription shape and publishes
`selectReference: { selector, key? }` or `captureRequest: { key }`. A fresh key
requests another operation even when its selector or target file is unchanged.
Selecting a reference also activates the Inspector's Tree tab, expands the
matching row's ancestors, and scrolls it into view. Repeating the request
reveals the existing selection again without toggling it off; a face-group
reference keeps the group highlighted and reveals its active face.
Both toolbar capture and host capture commands use the same implementation.
Hosts can provide `acknowledge(kind, key)` to consume an admitted command. Desktop
binds commands to the active project/tab/path/root and removes only the matching
nonce, so an old acknowledgement cannot clear a newer request or replay after a
remount. A capture waits for ready geometry; a selected reference waits until it
can resolve against the current model.

`@hardcore/ui/file-viewer/presentation` exports the lightweight
`ViewerLoadingOverlay`, `MissingFileAlert` and `StatusToast` for host bootstrap and generic
viewer loading/error presentations. Their markup and wording are the original
CAD artwork. They mount inside a relative container and require no CAD client.

The optional `live: CadLiveBinding` registration binds a mounted
`CadLiveController` for app-owned view tools. It reports the actual resource
revision, selection, camera, display and mode, supports explicit controls and
captures a PNG without prompt delivery or clipboard effects. It never substitutes
catalog or persisted state for a live viewport. On unmount it retains only a
serializable inactive snapshot; controls require the tab to be shown. See the
[viewer host contract](viewer-host.md#app-specific-interfaces) for lifecycle and
stale-operation rules and [`live.ts`](../src/renderers/step/live.ts) for signatures.

## Lifetimes

The injected `CadWorkspaceService` owns its catalog and request controllers. The first
subscriber starts the catalog and its two-second poll; further subscribers
share them. The last unsubscribe stops polling. The host supplies `shouldPoll`
and connects window focus and visible `visibilitychange` events to
`refresh({ markRefreshing: false })`, preserving browser refresh behavior
without a DOM dependency in core. Catalog requests retain the ten-second
timeout and the same error text.

Each prepared CAD document owns a render session with a cancellable view of its
client's tessellation cache. The client owns the origin-bound provider and bounded
deferred write queue. Disposing a session aborts its reads and
rejects late worker writes; already admitted writes remain with the client
through file switches. Disposing the client clears that queue and its provider
requests. There is no page-wide mutable cache provider. HTTP storage still uses
the shared Python cache and its original component-key codec.

On mount, immutable mesh and complete robot state are read synchronously from
the existing bounded decoded caches. Reopening a warm file can therefore show
those assets on its first render while file-owned controls restore their own
camera and pose. Completed STEP working sets have a separate LRU of at most
eight packages and 256 MiB, so an assembly that exceeds the core SURF cache's
24-entry limit can reopen without fetching or decoding every component again.
The bound includes unique full backing buffers and estimated structural metadata;
an oversized package is not retained. Memory pressure evicts these disposable
snapshots before reclaiming workers. The existing memory probe reports their
bytes under `assetCaches.completedPackages`, excluding buffers already charged
to the displayed scene, LOD staging or another cache.

Only complete committed CPU display data enters this cache. Component typed
arrays remain immutable and share their existing allocations; cache admission
copies plain bounds, part and descriptor metadata, and every restore gives the
renderer fresh occurrence/material objects and LOD maps. Scene code must not
mutate or transfer the shared component arrays. WebGL scenes, selector runtimes,
workers, pending work, cameras, selections and pose state are never retained.
Refinement drops the old snapshot when its replacement commits; closing the
renderer captures the latest complete working set.

Reuse requires the same resource-provider generation, stable root, file, entry/document and
appearance revision, package URL and runtime descriptor view. Anonymous clients
remain object-isolated. Each component retains its exact surface-input/object
binding and concrete tessellation key and level. Editing previews, changed
revisions and runtime replacement views invalidate the snapshot. Tabs borrowing the same workspace service can reopen while the bounded entry
survives. A replacement service or changed backend identity starts a new resource
generation, preventing URL cache reuse across changed credentials or origins. A native GLB scene and its animation mixer are never cached:
they are mutable state with one owner, the GLB renderer's mounted scene.

Worker infrastructure is reference-counted across live render sessions. The
last session releases workers and pending work. Playback clocks are separate
per mounted renderer. Asset loads, sidecar loads and render-module loads have
their own abort signals; changing or closing a file cannot install a late
result into the next file. A renderer release does not dispose a host's shared
client while another pane still needs it.

## Validation and baseline limitations

CAD helper suites retain format, state, geometry, reference, selection,
settings and loading behavior. Core tests cover independent client origins,
cancelled and late responses, polling ownership, cache/worker lifetime, and
session cancellation and client-owned writes. The browser integration harness exercises actual WebGL
rendering with two roots, panel switching, PNG captures, host title ownership
and state round trips through unmount/remount.

The camera session schema stores vectors and zoom while omitting runtime scope
metadata. The viewport restores the serialized camera in its current file
session, so a 110% view reopens at 110% while a second renderer starts from its
own 100% default. Presets update projection/lens while retaining viewpoint and
zoom on the same renderer, canvas and controls. Ordinary settings edits never
restart the viewport. Initial/reset/fit views use the
projected bounds with 1.1 padding (roughly 91% occupancy in the limiting viewport
dimension), rather than a bounding sphere. Saved/manual views retain their own
zoom and pose. This policy belongs to the interactive UI; snapshot/export
framing remains independent. The orientation control labels its positive X/Y/Z
axes and retains its snap and drag interactions.

See [settings controls](settings-ui.md), [render capabilities](render-types.md)
and [renderer contracts](renderers.md) for changes inside the shared package.

The optional `@hardcore/ui/file-viewer/empty` entry exports `EmptyCadBackdrop` for the web host’s missing-file presentation. It lazily mounts the same empty CAD viewport with the host’s `colorScheme`, and overlays its `children`. It owns no file access, catalog subscription, or persisted state. This preserves the original grid and camera behind `MissingFileAlert` without loading CAD into the master viewer.

## STEP scene and viewport

`createStepRenderer` (`@hardcore/ui/renderers/step`, id `step`) shows a `.step` or
`.stp`. Its scene and everything of it that lives in the viewport are on the kit;
`src/renderers/step/scene` is that half.

- **Scene** (`scene/stepScene.js`): a kit scene around core's `buildModel`
  (`@hardcore/core/common/cadScene.js`, which is also the headless renderer's and
  the docs hero's and does not move). ONE identity for as long as a file is
  mounted: two stable roots (surfaces, and linework for the viewport's edge layer)
  around whatever build is live. A STEP does not arrive once — a large assembly is
  published in pieces, each component's detail is swapped as the camera moves, and
  a display mode that changes how records are BUILT replaces the build — and none
  of that is a new scene to the viewport. `plan()` decides reuse or rebuild (same
  model, same structural build key, same viewer theme: the publish is handed to the
  live build, which reconciles its records, so occurrences on screen keep their
  meshes, materials, visual and deformation state and BVHs); `complete` is false
  while components are still to come; `bounds` is the scene as posed when it was
  last synced and `restBounds` the authored placement; `placedObjects()` is the
  display records. After every sync the renderer calls `viewport.commitScene()`.
- **Ownership.** A build owns its records, materials and the geometries it created.
  Component geometry is shared between builds and scenes through core's owner counts,
  so releasing a build drops this scene's count and frees a buffer only when nothing
  else holds it; a rebuild of the SAME model releases with `releaseGpu: false` and
  keeps its components' GPU buffers and BVHs. Runtime-level teardown
  (`render/lodSceneCleanup.js`) clears only the groups that hold nothing but STEP's
  own objects (the edge layer and the three pick groups) — never the model group or
  the stage, which are the viewport's. The LOD publisher's ownership protocol
  (`onMeshSourceAdoption`) is answered for every source the scene shows, releases
  or fails to show, and for every way the WebGL runtime under it can go away
  (`runtimeLifecycle`).
- **The ground is sized from REST.** The viewport sizes the grid, the stage and the
  Render studio's floor from `restBounds`, as it does for every renderer, so posing
  a mate or playing a routine never rescales or slides the ground — including a
  Render entered while the model is posed, which used to size the studio floor from
  the posed box.
- **Shadows** are per record (core's `syncRecordShadowPolicy`: only an opaque, lit surface
  takes or casts one), so the scene implements `setShadowReception` and the viewport
  never sets its meshes itself.
- **Look.** `setSurfaceLook` is the kit's half; the theme, the app appearance (edge
  ink), authored-material overrides, the whole Surfaces section and shadow
  reception are STEP's (`setLookContext`). Both resolve the same settings, so the
  scene wears a look once: whichever arrives second finds it already on.
  `keepsAuthoredFinish` is `hasAuthoredMaterials(meshData)`.
- **Viewport** (`scene/StepViewport.jsx`): a props adapter around the kit's
  `ShellViewport`. It decides what the viewport may show and pick just now (nothing
  under Pose, Animate or fullscreen; no topology while a previous mesh is held over
  an update), mounts the viewport menu and the bottom action from the shell's own
  pieces, and adds to the kit viewport's handle the two things only a STEP can
  answer: `sampleLodCamera` and `zoomToFitSelection` (the boxes of the selected
  references, from the selector runtime as posed, merged with the boxes of the
  selected parts, from the records on screen).
- **Layers** (`scene/StepSceneLayers.jsx`), mounted through the viewport's overlay
  slot, in the order that is their contract: the scene sync makes the records, part
  state dresses them, the pose pass moves them, the exploded view offsets them, and
  only then are the pick proxies, the linework and the highlights laid over where
  they ended up.

  | module | what it owns |
  | --- | --- |
  | `useStepViewPolicy.js` | Everything DERIVED from the settings and the selection, touching no scene: the normalized display state, which linework is drawn, the edge styling a mode forces, what is pickable once hidden and isolated parts are out. |
  | `useStepSceneSync.js` | The scene sync: reuse or rebuild, the LOD ownership protocol, the topology line, pick groups, the raycast-BVH schedule and the section clip over the new records; STEP's half of the look. |
  | `useStepDisplay.js` | `useStepPartVisualState` (hidden, isolated, hovered, selected parts) and `useStepLinework` (pick proxies, B-rep edges, a highlighted part's brighter edges). |
  | `useStepPose.js` | The sidecar module's setup and the ONE pose/animation pass (below). |
  | `useStepExplode.js` | The exploded view: a radial layout eased over a second, snapped by the slider, re-applied to fresh records. |
  | `useStepHighlights.js` | The reference highlight: boundary lines and fills of selected and hovered faces, edges and vertices. |
  | `useStepMeasureOverlay.js` | The measure canvas: rulers and the snap indicator. |
  | `useStepPicking.js` | The pointer: hover, tap, double-click (isolate) and measure picks, with all of the topology raycasting. The viewport menu is NOT here: it asks this hook what is under a press (`pickAtRef`). |

- **One owner of the frame after a pose.** A pose or animation write is drawn because
  the pose pass asks for a frame, once, as its last act, and nothing else on that
  path does: the topology line it re-syncs is told not to
  (`syncTopologyDisplayEdgeLine(..., { requestRender: false })`), a highlight layer
  asks only when it drew or had drawn something, and part visual state does not
  re-run for a pose at all (the part-id lists keep their identity while their
  contents hold, `useStableIds`). `StepRenderer.browser.test.mjs` fails its
  Kinematics and Animate tests when that one request is removed.
- **The viewport menu** is the part menu, one list
  (`assemblyPartMenuEntries` in `components/workbench/AssemblyContextMenuItems.js`)
  with two presentations: the Features tree renders it into its own context menu,
  and the viewport hands the same entries to the shell's `ViewportContextMenu`.
- **Test seams** (read-only): `window.__cadDisplayRecords()`, `__cadJointHandles()`,
  `__cadRenderMemoryProbe()`, `__cadSceneSync` and `__cadModelPlacement` (a live
  getter: a render setting that moves the ground shows without a scene sync). The
  camera and the stage are the viewport's (`__cadCamera()`, `__cadStage()`).

## STEP and source separation

STEP inspection reads the document's geometry, assembly structure, and topology.
It does not search for a matching Python file or reconstruct authored operations,
parameters, or sketches. Source files remain independently accessible through the
file explorer. Geometry references added to prompts identify the STEP and its
selected entities, without attaching a source filename or source line.

## Selection and inspection tools

STEP's Select tool offers All, Parts, Faces, Tangent faces, and Edges. Explicit
filters never fall back to a different entity type. Face and edge filters load topology
for the selected leaf part; selecting another part in Tree changes that target.
Opening a STEP starts with render geometry; activating Select or Measure requests
exact inspection topology when it is needed.
Shift-click adds/removes entities. Escape clears the
selection after any open menu has been dismissed. Input fields
keep their own Escape behaviour.

Measure works like Select: the first press takes up the tool, and a press while
it is active opens its snap filter — Any geometry, Points, Edges or Faces — in
the selection-filter dropdown; a narrowed snap is named in a small pill under the
tools. It does not toggle off: another tool or Escape ends the session. There is
no panel until something is measured. `MeasurePanel.jsx` then appears below the
tools in the drawing toolbar's surface and width, in rows rather than a grid:
one 24px row per measurement — its ruler's colour, the reading, and a delete
button on hover; deltas and what each end snapped to are in the row's title —
and a Clear all row once there are two. It has no title, close button or footer. The View and Capture menus share the dropdown width, offset and collision boundary.
Leaving Measure or changing models clears
completed rulers and the current draft. Escape first cancels a draft, then exits
the tool. The existing measurement engine supplies planar-face spacing and
angles, straight-edge angles, circular-edge centre spacing, and point distances;
this UI does not add general minimum-distance calculations for curved surfaces.
STEP no longer has separate Reference or Measure tabs. Other renderers retain
their existing inspector tabs.

Clip mode colours cut surfaces amber using stencil winding over the display
meshes. Holes remain open for closed, consistently oriented solids. This is a
non-pickable display fill, not new topology or an edit to the STEP. Only meshes
whose bounds intersect the active plane receive the two extra stencil passes;
disabling clipping releases the fill and materials without disposing the model's
geometry. Open/non-manifold meshes cannot guarantee a solid section fill.

Tangent faces**. Clicking a face selects its connected
chain across edges classified as tangent by the loaded STEP topology; sharp,
unknown, boundary and nonmanifold edges stop the chain. Selection never crosses
occurrences or solid shapes. Shift-click adds a chain, or removes it if the whole
chain is already selected. The resulting faces use the existing highlight and
Add to prompt controls. An assembly part loads its topology through Tree first,
as with the Faces filter. This changes selection only, not CAD geometry.

Selection filters keep All, Parts, Faces and Edges together. **Connected
selection** groups Edge chain and Tangent faces separately; the measurement filter menu keeps
its existing options.

Edge chain uses tessellated edge endpoints within the same solid/occurrence and
a shared face, with a 0.00001 model-unit endpoint tolerance. It follows corners
where only one continuation exists and a unique smooth continuation at branches;
ambiguous branches, missing endpoints, and closed single edges stop traversal.
Shift toggles the resulting group and Add to prompt uses its canonical edge refs.

### STEP inspector layout

The STEP inspector uses a Features tab. Its rows share the file tree's row
primitive and 28px height, with the model tree's horizontal inset. The disclosure
button expands children; the rest of the row selects its canonical references.
Labels keep the row's width; summaries and measurements belong in the selected
reference details. The small eye action changes visibility, while Isolate stays
in the row's context menu.

That menu is THE part menu, the one the viewport offers over the same part: one
descriptor (`assemblyNodeMenu`) and one set of actions (`partMenuActions`),
rendered by `AssemblyPartMenuItems`, so the two cannot drift apart. Add to prompt,
Copy Reference, Select/Deselect, Isolate/Exit isolate, Exit all isolates, Hide
others, Hide/Reveal, then the tree's Expand/Collapse and Expand all/Collapse all,
and last one framing group: **Zoom to fit** and **Zoom to selection** (off without
a selection). Framing cannot contradict the tool in hand, and every item of this
menu returns to Select before it acts. The VIEWPORT's menu exists only while Select is the
active tool — under Measure, Draw, Pose or Animate a secondary tap opens nothing,
though the native menu stays suppressed and a secondary drag still pans. The
TREE's is available under any tool, and every action returns to Select first,
exactly as clicking a row already does (`ensureSelectTool`). A secondary tap on
empty space asks about the model as a whole (Show all, Expand all, Collapse all)
and opens nothing at all when none of those can do anything. The tree starts directly below `Filter model…`, the file
tree's filter box (`primitives/tree-filter`). Conditional Show all and Exit isolate
actions sit on the filter row's right side; there is no feature-count header.
Clicking empty tree space clears selection, including a pending topology pick.

The filter is a second view of the tree, never a filter over its expansion.
Typing replaces the rows with a flat, ranked list (first 200; a search-only status line counts
every match) drawn from an index of what the presented tree already holds: every
assembly and part by name or occurrence reference (`#o1.2`), and the features of
parts recognized earlier. Typing expands nothing, requests no topology and starts
no recognition, so the picking frontier is the same before, during and after a
search; a part's features become searchable once that part has been opened. The
query matches a name as the file filter matches a filename; several words may
also name owners (`bridge screw`), provided one of them is in the name. A hit is
the tree row without its place: name first, its owners muted and truncating
behind it, with the same menu, visibility action, hover and availability.
Selecting a hit selects it in the viewport and immediately expands its owners
through the controlled expansion state — a selection is always a row the tree
holds — while the hit itself stays closed. The one reveal scroll waits until the
search ends (clear, Escape or an empty box); without a new selection the tree
returns to its previous scroll position. Up/Down move the cursor; Enter selects.

Parts retain their assembly hierarchy, except redundant document wrappers are
flattened for presentation. A single structural root (assembly, part, or body)
is also implicitly expanded until its children offer a real choice. Its canonical
owner is expanded in the host and its topology/recognition requested once, so
viewport picking matches the visible features. Feature groups are never implicitly
expanded. Flattening never rewrites occurrence or reference IDs, and hidden-owner
restrictions still apply to the exposed children. Assembly and part expansion use the same controlled state as viewport
picking and topology requests. A collapsed assembly is picked as a unit;
expanding it exposes its children, and expanding a visible part requests that
part's exact topology and inferred features. Collapsing an ancestor removes its
descendants from the requested frontier even if their saved expansion remains.
In All selection mode, visible feature groups own their face hits; exposed
children take precedence over their parents. Explicit Faces and Edges modes
retain exact entity selection inside expanded parts.

Isolation restricts the selectable subtree without propagating an excluded
ancestor's disabled state into the isolated descendants. Hidden geometry stays
unselectable. Selection reveals expand the required ancestors and scroll once
per selection or explicit reveal command. Later expansion, recognition updates
and manual scrolling must not pull the view back to that row.

The Reference pane is read-only, resizable, and independently scrollable. Its
static heading has one X action to clear selection; neither the pane nor its
fields collapse. A compact dropdown browses the selected references directly
without modifying the selection. New selections show their newest reference.
Selection totals remain above the current reference's name, type, wrapping
canonical ID, dimensions, coordinates and source material. Rows share an 8px
gutter, an 80px label column and 11px text, with thin separators between totals,
reference facts and material. There are no copy or dimension-preview buttons;
reference delivery stays in the tree/viewport context actions and measurement
previews in the Measure tool. There is no separate Surfaces tab or source
feature view. Display contains per-file display controls and photographic settings.

The top-right **Interaction tools** toolbar holds Select, Measure (STEP only:
it snaps to B-rep topology, so no other format offers it) and Draw (there is
no Pan tool: the camera pans under every tool by right-drag, Shift-drag or two
fingers), Pose in a file with joints to drag, and Animate, rightmost, in a file
that has animation routines (each is absent otherwise, never disabled). A
robot's Pose leads the toolbar, ahead of Select; a STEP's sits immediately
left of Animate. Press Select to activate selection; press it again
while active to open its selection-filter dropdown. The buttons wrap inside
their pill when the scene is narrow. The Display tab owns display settings and
Kinematics owns Pose. The active tool owns the bottom action: Select the prompt
references, Draw the drawing capture, Animate the playbar. Pose has none.

A selection exists only while Select is the tool. Leaving Select for any other
tool drops the selection, in the viewport and the Model tree alike; choosing a
row in the Model tree (or a host `selectReference`) under another tool returns
to Select first. No other tool ever sees a selection, so none needs a rule for one.

### Pose

Pose drags a model's joints by handles in the viewport. It exists where
something can be driven: a robot (URDF, SRDF, SDF) with a revolute, continuous
or prismatic joint that is not a mimic follower, and a STEP whose sidecar
kinematics declare a revolute, slider or cylindrical mate. It is the tool a
robot OPENS in; that default is a rule of the file's kind, not a saved
preference (the robot renderer's `toolRestore: { opensIn: "pose" }`): a robot
with no recorded tool opens in Pose, one last left in Select comes back in
Select, and a STEP always opens in Select. It is absent in fullscreen. While it is active the model picks nothing, hovers
nothing and casts no model ray (`pickMode` NONE, as in Animate); the camera
orbits, pans and zooms exactly as under every other tool, and the knobs are the
only interactive things. Leaving keeps the pose.

One handle system serves both formats. Two adapters turn a description and its
CURRENT pose into one plain list, in model space: `{ id, label, kind, pivot,
axis, toward, value, min, max, unit, onChange }` (`robot/jointHandles.js`, and
the STEP renderer's `workbench/jointHandles.js`). A robot's joint
frame is READ, not solved: it is the world matrix of the joint's motion group in
the scene graph, which already sits before an SDF joint's static child offset; a
STEP mate's world-at-rest axis is carried by the
accumulated delta of its child, the composition `kinematicsDeltas` uses, so a
handle rides a mate chain of any depth. A fixed joint, a fastened mate and a
mimic follower have no handle. A STEP DOF that a coupling drives KEEPS its
handle and writes through the coupling (`poseControlWrite`), as its slider does:
a coupling has no axis to hang a handle on, and a gear train whose every member
is geared would otherwise have none. The list is rebuilt from the pose on screen,
so sliders, presets, Reset and a handle further up the chain all carry the
knobs along.

`onChange` is the Kinematics tab's own change path (the robot pose store's
`write`, `handleStepModuleParameterChange`), so limits, mimic followers,
couplings, the SRDF group state, persistence and the sliders are decided in one
place and stay in step; the drag itself never clamps. A
continuous joint's drag winds freely and is stored as one turn, (-180, 180],
which is what its slider spans.

A turning joint's handle is a thin arm from the joint's pivot to a small round
knob, with its travel drawn faintly through the knob: the limit arc, or the full
circle for a continuous joint or a range of a turn or more. A sliding joint's
handle is a thumb on a track: the track is the line the joint travels (its limit
range along the axis, with a stop at each end; a short stretch either way when
the description sets no limits), and the knob sits on it where the joint now is.
It has no arm: any arm off the axis has to choose its direction from the camera,
and a handle that re-chooses as the view turns is a handle that jumps.
A turning joint's arm lies in its rotation plane toward the child's geometry,
so the knob sits on the moving part and turns with it; a child centred on its
own axis (a wheel, a roll joint, a turntable) takes a perpendicular fixed in the
child's frame instead, and concentric STEP members fan their arms round the
shared axis, decided at rest. Above twelve handles a model rests as knobs alone and the arm and
travel appear with the pointer. Hovering or holding a knob shows its name and
value (`shoulder  42.0°`, `lift  0.120 m`).

The handles are drawn on a 2D canvas over the viewport (`kit/tools/pose/JointHandleOverlay.jsx`,
`jointHandleCanvas.js`), like the measurement rulers, not as scene objects: the
arm is 44 CSS pixels at every zoom and under either projection, always on top,
and nothing of it reaches captures, render mode, bounds, shadows or picking.
`useJointHandles.js` keeps no React state: the list lands in a ref (the owner's
own ref, for a robot, whose pose never renders a component), a frame loop
repaints only when the camera, the list or the pointer changed, and the label
is written into its element. The overlay's size is measured when its box
changes, never per frame. A press within 12 px of a knob (22 px for touch)
is taken in the capture phase above the WebGL canvas, captures the pointer and
disables OrbitControls until release, cancel or leaving the tool; every other
press, a modified one (Shift/Ctrl/Cmd is the camera's pan) included, is left
untouched. Writes are throttled to one per animation frame.

The drag mathematics is pure (`jointHandleMath.js`: plain vectors, a pointer ray
and a `project` function in, a value out). A turning joint intersects the ray
with the plane through the pivot normal to the axis and accumulates the signed
angle sample to sample; a slider takes the point of its axis closest to the ray.
A drag picks its mapping once, at the grab (the camera cannot move while a knob
is held). When the rotation plane is within about 12° of edge-on the drag
becomes screen distance along the near side of the ring, one arm length to the
radian; when a slider's axis is within about 15° of the view direction it
becomes pixels at the pivot's depth, right or up being positive.
`window.__cadJointHandles()` is a read-only test seam: each knob's and pivot's
position in CSS pixels and its joint's value.

### Animate

Animate is a session, like Draw: never persisted, never restored. While it is
active nothing under the pointer is pickable and the camera orbits as usual.
Its controls are the playbar at the bottom centre (`ViewportAnimationBar`),
transparent, in one row: a routine list button (only with two or more
routines), Play/Pause, the live scrubber, and a settings cog. Settings is a
player's menu: a Speed row showing the current speed and opening the list of
speeds (an authored speed outside the presets is listed too), and a Loop row
whose check sits on the right and which toggles without closing the menu.
There is no Restart; the scrubber's start is the restart.

A routine owns the model's pose only inside the mode. Outside it the clip is
released — stopped, rewound, the pose handed back to Kinematics — so selection,
topology and Kinematics never meet an animated model. Nothing of the playback
survives leaving: returning starts from the start, and a restored session that
was mid-routine is released the same way. A routine that failed to load has no
Animate tool to say so on; it is reported beside the filename with the file's
other unavailable settings.

Because the mode picks nothing and ends at rest pose, pick-only state stands
still while it lasts (`animateMode` in `step/scene/useStepPose.js`): the transformed selector
runtime is not rebuilt per posed frame (which as React state used to rebuild pick
groups, their BVH, the picking listeners and the highlight overlays every
frame), pickable lists are one shared empty list, presses and releases cast no
model ray, and part visual state is not reconciled while a routine plays. The
pass that leaves the mode re-runs once and rebuilds the pick state. Independent
of the mode, a routine's feature resolution is memoized per definition and parts
array (`stepModule.js`), the clip-plane sync is skipped when no section is or
was active, and the view cube is memoized.

No component renders for a playing frame. The viewer's pose pass is one function
with two callers: React runs it when something it reads changes (a scrub, a
pose, a display setting, a new mesh) and publishes it through a ref; while a
routine plays, the animation clock calls that same function once per tick
(`usePlaybackFrames`; the GLB renderer drives its mixer the same way). The
scrubber is the clock's only React subscriber. Because the pass now runs inside
the tick, the clock's adaptive pacing measures a frame's real cost. A frame that
only moved parts skips material and instance-membership reconciliation: the
effects pass reports whether a style, visibility or highlight changed
(`applyStepModuleEffectsToRecords`), and moved instances sync their own matrix.

### Draw

Draw is the shared [drawing editor](drawing.md) (Excalidraw) laid transparently
over the viewport. It is a STEP tool and appears on no other format: a GLB, an
STL, a 3MF, a DXF and a robot description do not offer it. (The tool itself is
the SHELL's — `kit/tools/draw`, `shell.tools.draw` — because STEP moves onto the
shell next; until it does, `renderers/shell-harness` is the only other frame that
mounts it, for tests.) The chunk loads on the first use of the tool, and the
surface stays hidden until the editor has its scene, so its default white page
never flashes over the model. Pressing Draw again, like Measure, ends the session.

The editor's own toolbar, `DrawingToolbar`, is placed by the viewer as a second
row under the interaction tools in the same button metrics, in the order a sketch
is made: Pen, Line, Arrow, Rectangle, Ellipse, Text, Fill area and Eraser, then
Color, then Select and move drawings and Pan view, then Undo, Redo and Clear
drawing. It shows the editor's active
tool. Tools are sticky: a line is followed by another line. Color opens a strip
of neon swatches (plus white and black) in the toolbar's own flow; it sets the
color of what is drawn next and never recolors existing ink. Fill area is not an
SDK tool (`drawing/fill.ts`): a click inside drawn ink adds a translucent
polygon of the current color, from an outline that need not be closed. Draw opens on the pen in neon red.

While Draw is active the view direction is locked: orbit controls, inertia,
keyboard orbit and the view cube are off, and the editor covers the viewport so
no drag reaches them. Pan and zoom belong to the editor (the Pan view tool,
scroll or two-finger pan, space-drag, middle-drag, pinch or modified wheel) and
the camera follows it
so model and ink stay one picture. `kit/tools/draw/drawingViewLock.js` derives every camera
pose from the pose Draw started with and the editor's absolute scroll/zoom,
never from the previous frame, so a long pan cannot drift, and re-derives it
after a viewport resize. A viewport runtime replaced mid-sketch re-locks against
the scroll and zoom the editor is still showing. Pan moves the orbit target along the camera's right/up;
zoom is orthographic zoom or a perspective dolly. In perspective only the focal
plane through the orbit target tracks the ink exactly. The camera keeps its
panned pose when Draw ends.

A sketch is session-only. It lives in the mounted editor, is never written to
tab or file state, and is discarded when Draw is deselected, the file changes or
the renderer unmounts; a restored tab never reopens in Draw. The bottom action
is **Copy Drawing**, or **Add to Prompt** where the host has a composer
destination. It delivers one prompt bundle through the host prompt-context port:
the viewport capture with the editor's committed ink composited over it
viewport-aligned (the ink canvas keeps its own pixel ratio and is scaled into
the frame; selection handles are not included), plus the selected references.

The file navbar holds a direct snapshot action, Inspector (`SlidersHorizontal`) and file
tree (`Folders`). The Inspector opens by default, except over a file whose
Inspector is only Display (an STL, a 3MF and a GLB, each under its own renderer): there the
model gets the room until a person opens it (a robot's Inspector opens, on
Kinematics). Each renderer says so in its own
`panels()` (`inspectorPanels(ready, { defaultOpen })`). Snapshot uses the host prompt-context port: desktop attaches
the viewport image and references to the owning session's draft; web copies
through its clipboard adapter. The DXF renderer, which is not on the shell,
contributes its own one: Take snapshot.
The shared FileViewer renders these registered actions without importing CAD.

**There is no zoom control in the viewer.** No percentage readout, no menu behind
it, no zoom toolbar and no navbar zoom buttons: the camera is the pointer's
(wheel or pinch to zoom, drag to pan, and on a DXF double-click to fit). Two
places bring a lost view back. STEP's viewport context menu ends in a framing
group — **Zoom to fit** and **Zoom to selection**, the latter off without a
selection — offered wherever that one menu is rendered: over a part, over the
backdrop and on every Features tree row (`AssemblyContextMenuItems.js`). And the
view cube's centre, "Reset to default isometric view", FRAMES the model from the
default direction, which is the only way back on a robot, a GLB or a mesh.
Framing the whole model is ONE act — `zoomRuntimeToBounds` over the authored
bounds with `resetZoomBaseline: true`, which the viewport calls `resetZoom` — so
it is offered once, and the live `resetCamera` command is that same call.
Restoring the model itself still belongs to whoever owns it (Kinematics' Reset
for a pose, Display's for settings).
See [settings-ui.md](settings-ui.md). X/Y/Z labels
remain outside the bottom-right axis endpoints. Fullscreen hides all of these
controls. The web header owns Fullscreen (`Maximize2`) beside appearance; while
active, shared `FullscreenToolbar` places a transparent animation play bar at
bottom center and Settings/X at top-right. Both areas fade after two seconds
without pointer, wheel or keyboard activity, except during scrubbing, keyboard
focus, or while settings is open. Movement reveals them again. There are no
fullscreen Kinematics controls, and no bottom bar when the file has no animation.

Fullscreen is the Animate tool with the rest of the viewer put away: a file with
routines shows the same playbar, mounted from the same component over the same
runtime (routine list, Play/Pause, scrubber, settings menu); a file without has
no tool and no bar. An open menu of the bar's holds the fading controls visible.
The corner button is orbit settings only, a content-height floating panel
bounded by the viewport. Orbit uses a 0–5× slider and numeric input; 0 stops rotation,
and at 1× a turn takes 60 seconds. Stopping returns the renderer to idle quality
without rebuilding the scene. Its speed is global via `CadPreferences.orbit`
and host-owned storage (`cad-viewer:orbit:v1`), separate from per-file animation
and display settings.

Each fullscreen entry captures the regular camera and framing, then fits the
authored model at the default angle. Exit restores the saved angle, target,
projection and zoom, accounting for viewport resize. Fullscreen camera events
still drive LOD but cannot overwrite the persisted file camera. Topology picking
listeners are detached, drawing is unmounted, measurement overlays stop their
frame loop, and selection highlights are hidden. Normal camera dragging remains
available regardless of the tool selected before entry.

Each renderer keeps one transport and one renderer-scoped clock;
there is no second animation store. Leaving fullscreen for any tool but Animate
releases the routine, as leaving the Animate tool does. Escape dismisses a
nested menu, then orbit settings, then fullscreen.

### Read-only STEP features

Feature detection is an optional client-side capability of the shared renderer.
Expanding a visible part requests its geometry analysis in a disposable worker;
repeated instances and warm file reopening reuse completed metadata. Expansion
changes preserve a pending component while at least one of its occurrences is
still requested. The cache is versioned and bounded, and lasts only for the
running page or app renderer.

The [feature detection guide](feature-detection.md) owns the algorithm's scope,
cache identity, cancellation, limits, code map and regression policy. Keep this
work in UI, separate from cadgen compilation, Python inspection and reference
syntax. Recognized groups select existing canonical faces and edges. They do
not establish original source history, and failed recognition does not prevent
structural tree display or ordinary part selection.

### Replay experiment scope

Shared Features inspection runs entirely client-side from STEP geometry. The
worker returns inferred operations, not executable playback. The existing
canonical face/edge reference flow supplies highlighting and Add to prompt.

Kernel verification, its cache and endpoint, intermediate-solid playback, and
GIF/video export are isolated on `amy/step-reconstruction-playback`. They are
not shipped in the shared app. Pure numerical recipe helpers remain as
recognition regression checks, without a runtime interpreter or export path.

STEP models place **Features | Kinematics | Display** in one fixed top tab strip.
Kinematics appears only when the sidecar declares it; animation is the Animate
tool, not an Inspector section, so a file with routines and no kinematics has
no Kinematics tab. A mesh (STL, 3MF) and a GLB have only Display, and a robot
has Kinematics, Links and Display, each under its own renderer. An Inspector with a single section draws it as
a single selected tab, so every Inspector reads the same way.
Each section requires its own sidecar block and stays expanded, without a gate.
Every pose write is a jump: a slider drag, a typed number, a Pose knob, a named
pose (a STEP sidecar's pose, an SRDF group state) and Reset all put the model
where it IS from that frame on, for robots and STEP alike. There is no eased
pose transition and no preference for one; motion over time is the Animate
tool's. Each format has one write path (`write` in `robot/poseStore.js`;
`writeParameters` in `useStepMotionControls.js`).
Switching display mode leaves every tab and the active selection intact.
Tab order follows the format's section descriptors and cannot be customized.
The retired split/reorder preference is ignored in both hosts. A stored section
ID the current format does not have is simply not open, and the sheet lands on
the format's first tab — there is no table of retired IDs to keep alive. A
legacy list selects its last available tab. New selections and viewport-driven
reveals store one active section ID.

Robot Kinematics uses the same preset and value controls.

### Robot links

URDF, SRDF and SDF place **Kinematics | Links | Display** in the tab strip
(the [robot renderer](#robot-renderer)'s `KinematicsTab`, `LinksTab`, `SdfTab`).
Kinematics is always the leftmost tab and the one the sheet lands on (an SDF's
metadata tab follows Links; a description with nothing to drive reads "No
movable joints.").
Links is always present: it is the description's kinematic tree, not an
inventory of mesh names. `robot/robotTree.js` builds it as plain data.
Links are the rows, carrying no icon; a child link sits under its parent link
and shows the joint between them as muted text (`shoulder_pan · revolute`); the
named objects inside a link's meshes (`robotComponents` in `robot/robotParts.js`) are leaves under that
link, after its child links. Built-in primitives and unnamed mesh objects
contribute no leaves. Every link appears once: a cycle, a second parent or a
missing parent cannot hang the builder or drop a link, and orphans become
roots. A root that is only a frame — no geometry, no mass, and one child
attached by a fixed joint (`base_footprint`) — gets no row of its own; its
child leads the tree instead, unless the description has no content anywhere,
in which case every link is kept. An SRDF shows its paired URDF's tree.

The tab reuses the Features tree's pieces rather than cloning them: the 28px
row primitive, `Filter links…` (`primitives/tree-filter`), the ranked flat
search of `kit/inspector/modelTreeSearch.js`, and `InspectorSplit` for the Reference pane
(it opens at a third of the tab, never below a readable minimum on a short
screen, and never so tall that the tree loses its own — the same split the
Features tree uses). The search index also reads a row's `searchAliases`, so a
link is found by its joint name and the hit shows that joint in place of its
owners. The root opens, along with a chain of single child links below it;
everything else starts collapsed. When the tree has exactly one root with
children, that root is pinned: no chevron and no indent, so its children start
at the tree's own left edge. Selecting a hit opens its owners at once and
scrolls to it when the search ends.

Selection is the scene graph's. A link is hovered and selected in the viewport
as the meshes of its group, and a viewport pick of a surface that is not a named
object walks up to its link; a named object still selects itself (Shift in the
viewport, Shift/Ctrl/Cmd on a row add). A link with no geometry selects its row
and details only. As for STEP, a robot selection exists only while Select is the
tool: choosing a row under another tool returns to Select, leaving Select clears
it, and Escape clears it before it shuts the Inspector. A click acts at once: a
robot has no double-click to wait for.

The Reference pane reads back what the description says about the link, in
sections: its SRDF planning groups (`srdfGroupNamesByLink`) and end effectors;
**Inertial** (mass, centre of mass in the link frame, and the six inertia terms
laid out as the symmetric tensor); **Geometry** (each visual and collision as
its mesh path or its primitive with dimensions, plus only what the description
bothered to say: a scale that is not 1, an origin that is not zero, the visual's
colour); the **Parent joint** (name, type, parent link, axis, lower/upper limits
as written plus degrees, effort, velocity, mimic, origin); and the **Child
joints**. `parseUrdf` keeps those facts as written (`joint.origin`,
`joint.limit`, `link.inertial` with `origin` and `inertia`, `link.collisions`,
`visual.description`) beside the transforms it renders from, leniently: a
malformed inspection value is left out, never a load failure. An SDF model
reports only what its parser records. A named object shows its link, colour,
triangles and size.

What names something else can be followed. A mesh path is a link that opens
that file through the host's `onOpenFile`: the renderer resolves it against the
opened file with the mesh loader's own `resolveLocalAssetFileRef` (an SRDF's
URDF is always beside it). A `package://` reference, or one that leaves the
served root, has no path here and stays plain text. A parent or child link name
selects that link in the tree and the viewport.
There is no copy action: robot formats have no reference grammar to deliver.


### Inspector tabs and dark surfaces

The inspector uses the shared shadcn Tabs primitives for Model, Kinematics and
Display, with standard small UI typography and native keyboard navigation.
The single top row scrolls horizontally when needed; it has no drag handles,
drop zones, split panes or divider. A single section is a single tab. Visited Model trees remain mounted while hidden,
so disclosure and scroll survive tab changes.

The shared dark UI uses neutral charcoal tokens. Inspect's fixed dark workbench
uses a slightly lighter `#333333` canvas; light app appearance selects its light basis.
The shared loading star and desktop wordmark/icon use blue branding.

## Inspect, Render and live revisions

The Model tree keeps geometry-based Features, contextual dimensions, selection
filters and prompt-reference actions. It does not inspect model source.
Schema-9 annotations embed appearance, animation and kinematics; the content
hash must match the saved artifact before those annotations apply. Active build
previews carry immutable geometry revisions and never initiate a source build.
A complete previous revision stays visible until its replacement is ready.

Display's Mode dropdown selects Solid, Render, X-ray, Hidden line or Wireframe
presets over the same grouped settings. Render defaults to perspective; the
others to orthographic. Changing values shows Custom. Reset restores the base
preset and disables Clip/Explode, preserving camera viewpoint/zoom, selection
and Kinematics.
The groups and gate behavior are specified in [View presets](render-mode.md).
Photographic lighting and stage code stay lazy; the lightweight grouped settings
panel is always available. Authored materials remain read-only in the Model
reference section, with no material override or undo state.

The host-supplied render session owns its tessellation cache and worker leases.
The file session's display slice is the sole view-settings authority; its render
slice holds only the camera snapshot. Surface derivation and preview requests
use the file's injected service and abort when the consumer leaves. The Features
inspector resolves exact surfaces on demand through the same client.

File status reports Opening, Updating, Limited detail and actionable failures.
Full diagnostics stay expandable; Try again uses FileViewer's renderer reload,
which rechecks the artifact and does not restart the desktop window.

### Camera framing and zoom

The zoom ruler and Reset use the original authored model bounds and default
orientation. Explode, clipping, animation, kinematics, visibility, floor and
other scene effects never redefine 100%. Perspective and orthographic derive
their own baseline from that same box and the current viewport dimensions.
Selection fit may move the camera but cannot make that new framing become 100%.
`kit/camera/viewportCameraFit.js` owns the fit calculation; live posed bounds remain useful
for clipping, lighting and picking. Nothing displays that percentage any more — it
survives only as the `window.__cadCamera()` test seam — and the acts that frame the
model are STEP's context menu and the view cube's centre.
