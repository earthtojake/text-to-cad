# CAD renderer

The CAD viewer is the viewport, floating toolbar, the tool stack under it,
reference interactions, measurement and drawing tools, animation, loading artwork
and alerts, in `@text-to-cad/ui`. The rules of its chrome — which tools a file has, how
they take and give back the pointer, the tool stack, preview, the keyboard — are the
[design system](settings-ui.md); this document is the mechanism behind them.

There is one renderer per file family over a shared, format-blind [kit](#kit) and
[shell](#shell). The STEP renderer is under `src/renderers/step`, on the kit like
every other family: its scene and viewport
([STEP scene and viewport](#step-scene-and-viewport)) and its surface, `StepSurface.jsx`, which
runs `useRendererShell` exactly as the other renderers do and composes STEP's own
modules around it (see the end of [Shell](#shell)). Applications use the registrations and the shared
`FileViewer`; they do not import another application's source.

## Kit

`src/renderers/kit` is the format-blind half of the viewer: small modules a
renderer composes, none of which asks what it is showing. There is one renderer
per file family, each a vertical slice over the kit: `src/renderers/dxf`
([DXF renderer](#dxf-renderer)), `src/renderers/glb` ([GLB renderer](#glb-renderer)),
`src/renderers/mesh` (STL and 3MF, [Mesh renderer](#mesh-renderer)),
`src/renderers/robot` (URDF, SRDF and SDF, [Robot renderer](#robot-renderer)) and
`src/renderers/step` (STEP and STP, [STEP renderer](#step-and-source-separation)). The kit imports itself, shared UI
(`primitives`, `lib`, `drawing`) and the format-blind half of `@text-to-cad/core`
(`lib/viewer/*`, `lib/perspective.js`, `common/viewSettings.js`,
`common/sceneSettings.js`, the Render studio); a renderer imports the kit, never
the reverse.

| folder | what it is |
| --- | --- |
| `viewport/` | `useViewerRuntime` (three.js renderer lifecycle, on-demand render loop and `requestRender`, resize and device-pixel-ratio caps, context loss, keyboard orbit, teardown), `renderProfile` (`VIEWER_RENDER_PROFILE`: the tools view and preview drawing the same Display settings — `sceneForRenderProfile`, `previewSceneQuality`, `renderProfileKeepsPixelRatio`), `framePresentation`, `viewportBuffer`, `renderDepthPolicy`, `sceneObjects` (`disposeSceneObject`), DOM helpers. The scene in the viewport is its owner's: teardown calls the injected `disposeScene(runtime)` and `disposeStudio(runtime)`. |
| `camera/` | `runtimeCamera` (zoom percent against the authored framing, projection and lens sync, perspective snapshots, eased transitions, fit-to-bounds, recentre), `useViewportCamera` (that behaviour bound to a mounted viewport: the perspective kept by a mounted view, the preview camera swap and its restore, the reset that Zoom to fit and the live `resetCamera` share, view-cube presets, which turn the camera and keep its zoom and target), `viewportCameraKit` and `viewportCameraFit`, `orbitControls`, `zoomPivotReanchor`, `zoomSpeeds`, `cameraLens`, `ViewPlaneControl` (view cube). |
| `look/` | `stageEffects` (lighting rig scaled to the model, floor, glow and shadow catcher, grid and origin axes), the Render studio boundary (`renderStudioChunk`, `studioEnvironmentCache` and its worker). `chromeBackdrop` and `useChromeBackdropColor` (the frame colour around a scene). The surface LOOK is data the viewport resolves and a scene applies to its own materials: `@text-to-cad/core/lib/viewer/surfaceLook.js` (`createSurfaceLook(THREE, root).apply(look)`) does it for any authored material tree. The viewport resolves it with core's `resolveSceneSurfaceLook` (`common/sceneSettings.js`), the resolver the snapshot CLI dresses the same scenes with. |
| `view-settings/` | The settings model and store (`viewSettingsStore`, `useViewSettings`, `viewerDisplaySettings`, `renderState`), applying a change to a viewport (`useAppliedViewSettings`, `viewUpdateCoordinator`, `viewUpdateGate`, `viewUpdatePlan`), and the Display tool's content (`DisplaySettingsSection`, `DisplayModeOptions`; the shell draws it as a stack panel while Display is the tool). |
| `tools/` | `FloatingToolBar` (the dumb strip), `toolModes` (the tool-mode state machine), `ToolModeMenu` (a tool's exclusive modes: one button in its panel's header row and its dropdown), `ToolPopover` (an ordinary dropdown from its button, on a `side` and `align`ed start or end: preview's Playback settings, upward from the playbar), `ToolStack` (the bounded column under the strip, which scrolls only when what cannot give way still does not fit), `ToolPanel` (one panel of it: `fit` says how it gives way when the viewer is short, `resizable` makes it the person's to size — width, height and corner handles, moving only it — and every panel but Drawing folds to its first row; `ToolPanelCollapse` is the chevron for a panel whose first row is its content's; its `footer`, a `ToolPanelFooterButton`, is a full-row action under the body that never scrolls: the Reference's Copy, Drawing's Copy), `toolStackLayout` (every panel's width, the resizable panels' sizes and the folded panels: defaults, bounds and their stored record), `floatingSurface` (the two surfaces, defined together: the strip's and every menu's over the viewport, and the stack panels' more transparent one), and the format-blind tools: `draw/` (overlay, view lock, `useDrawingViewLock`), `PreviewChrome` (the view actions in both modes, and preview's controls and their visibility), `PlaybackMenu` (preview's Playback settings: Animation — Routine, Speed, Loop, Autoplay — then Orbit and its speed), `preview/` (orbit preferences), `playbar/` (`ViewportAnimationBar`, `animationClock`, `usePlaybackFrames`, `playbackPreferences`: the file's Playback settings — orbit and its speed, Autoplay, the routine's chosen Speed and Loop), `pose/` (the handle overlay, canvas, drag mathematics), `select/` (`usePointerPick`: taps and hover through a scene's own `pick`), `quick-edit/` (`QuickEdit`, the note to the agent, and `quickEditPrompt`, the context it builds and the text it copies). Screenshot capture is `@text-to-cad/core/lib/viewer/screenshotCapture.js`. |
| `inspector/` | `FileSheet` and its row and section primitives, `modelTreeSearch` (`useTreeSearch`, the ranked flat search every tree shares), `VirtualRows` (a long tree's rows, windowed), `referenceRows` (`InfoRow`, `MonoValue`, `CoordValue`), `kinematicsControls` (the `Pose` row that heads every Position section, with its Reset). The tree row and filter box are `primitives/tree-row` and `primitives/tree-filter`. |
| `status/` | `LoadingIndicator` and `ViewerLoadingOverlay`, `ViewerAlertCard` (the card over the viewport for every alert), `MissingFileAlert`, `ViewUpdateStatus`, `loadingState` (`viewerLoadingState`), `loadAlerts` (`failureAlert`, `noGeometryAlert`). |
| `shell/` | The host glue every renderer needs that is not about its scene: see [Shell](#shell). |

**What a view opts into.** The Display panel and `resolveViewSettings` take explicit
lists, `features: { sections, modes, surfaceStyles }` (`ViewFeatures` in
`@text-to-cad/core/common/viewSettings.js`): the sections the panel mounts
(`VIEW_SECTION_IDS`), the presets and the surface styles it lists. A section left
out resolves off whatever was saved, and the saved settings are never rewritten.
Core names two lists, `ALL_VIEW_FEATURES` and `EDGELESS_VIEW_FEATURES` (no Edges,
Clip or Explode; Solid and Render; Shaded and Flat). Every renderer hands its list to
the shell, which configures the view-settings store (`configure({ features })`) and the
Display panel from it: STEP passes the first (and the same list to its Explode and Clip
tools), the GLB, mesh and robot renderers the second. The headless renderer
(`renderMeshScene.js`) resolves a job of each family under the same list.

**Tools.** The strip draws the list it is handed: `{ id, label, icon, active,
disabled, onSelect, description? }` — a press is a tool's only action; no tool has a menu
on the strip, and what it can be set to is its panel in the stack. Display is not a tool:
its settings are a popover from a button beside Preview (`kit/shell/DisplayPopover.jsx`). A renderer
builds its own list from `shell.tools.own(...)`, adding `shell.tools.draw` where it offers
Draw; STEP's is in `step/StepSurface.jsx`. There is no Animate tool: routines play in
preview, whose Playback settings and playbar the shell draws for any file with
routines. Preview is not a tool: it is a button among the view actions on top of the cube. Nor is Quick Edit: it is a STEP file's box at the top-right, there while something is picked or drawn. `createToolModes({ defaultMode, modes })`
answers what a press does (`next`), what a saved tab may record (`persisted`) and
which tool a file opens in (`restore`); the STEP declaration is
`CAD_TOOL_MODES` in `workbench/constants.js`. The playbar follows the clock on
the runtime it is handed (`runtime.clock`, an `AnimationClock`); the Position
tool's overlay (`tools/pose/`) takes a plain handle list, as a prop or (for an
owner that poses its model outside React) as a ref whose list it replaces per pose.

**The scene contract** (core's `lib/viewer/sceneContract.js`, a JSDoc typedef that `kit/scene.js`
re-exports, because the snapshot CLI holds the same scenes): `{ object3D, bounds,
restBounds?, dispose(), setSurfaceLook?(look), setShadowReception?(receives),
keepsAuthoredFinish?, complete?, pick?(ray), placedObjects?() }`.
The viewport adopts `object3D`, frames `restBounds`, lights and floors `bounds`,
and hands over the surface look the Display settings resolved
(`{ materialSettings, authored, surface: { style, opacity } }`); it only ever
detaches a scene, whose owner disposes it. `buildModel`
(`@text-to-cad/core/common/cadScene.js`) exposes `object3D`, `bounds`, `restBounds`
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
renderer. It holds the host's file viewer (`src/file-viewer`) to the mirror of
that rule: the file viewer mounts a renderer through the registry and imports
none itself, so no host pays for a family it is not showing. The
unbound-identifier test (`src/renderers/unboundIdentifiers.test.js`) scans the
whole renderer tree, so a renamed or added slice is covered the moment it
exists. The same script's `checkSharedSceneBuilders` holds the rule of the next
section: each family's builder, loader, opening pose and look are imported by the
renderer AND by the snapshot's `common/headlessScene.js` from one core module, are
defined nowhere else, and no module on the snapshot's render path imports a mesh
flattener.

### One scene builder per family: the viewer and the snapshot CLI

`cadgen snapshot` of a GLB, an STL, a 3MF or a robot description draws the scene the
viewer draws, because both call the same builder. A family's scene construction lives in
`@text-to-cad/core` (no React, no DOM beyond three.js); its renderer here keeps the loading
state, the tools and the panels, and the snapshot page (`common/headlessScene.js`, routed
from `common/headlessRenderEntry.js`) keeps only what a still has and a viewport does
not: the camera fit, the studio set up per output, and PNG encoding.

| family | builder (core) | viewer caller | snapshot caller |
| --- | --- | --- | --- |
| GLB | `lib/render/glbScene.js` `createGlbScene`, over `loadRenderGlbDocument` | `glb/useGlbScene.js` | `GLB_FAMILY` |
| STL, 3MF | `lib/render/meshScene.js` `buildMeshScene`, over `loadRenderMeshByUrl` | `mesh/useMeshScene.js` | `MESH_FAMILY` |
| URDF, SRDF, SDF | `lib/urdf/robotScene.js` `createRobotScene` over `robotParts.js`, loaded by `lib/urdf/loadRobot.js` | `robot/RobotRenderer.jsx`, `robot/useRobotDocument.js` | `ROBOT_FAMILY` |
| STEP | `common/cadScene.js` `buildModel` | `step/scene/stepScene.js` | `headlessRenderEntry.js` |

Both hosts dress a scene the same way: the look from `resolveSceneSurfaceLook`, shadows
while the lighting is on, `keepsAuthoredFinish` for Inspect's reflection environment, and
the ground sized from `restBounds`. A robot opens at `robotOpeningPose`
(`lib/urdf/motion.js`: every joint's default, then an SRDF's `home` state) and a
snapshot's `--joint-values` go on top through the same joint matrices. What a snapshot
cannot express, it refuses rather than approximates: a GLB's clips are the viewer's
playbar and have no snapshot flag. The pieces are pinned by `common/headlessScene.test.js`
(core), `kit/view-settings/renderState.test.js` (one look from either route) and
`tests/python/packages/cadgen/test_snapshot_family_scenes.py` (real snapshots, read as
pixels).

### Shell

`kit/shell` is what a file-family renderer needs from its host that is not about
its scene. A renderer loads its document, builds its scene (`kit/scene.js`) and
calls one hook; the shell owns the rest.

| module | what it is |
| --- | --- |
| `useRendererShell.js` | The hook. Per-file state through the host, the Display settings store and the Display panel's content (`shell.display`), tool modes (Draw is the only strip tool the shell itself owns; Display and preview's buttons and Playback settings are the frame's; `toolModes` is omitted altogether by a renderer with no tools of its own), the tool stack's layout (a viewer preference: `services.preferences.toolStack` — the resizable panels' sizes, the folded panels — changed by one patch per gesture, `frame.changeToolStack`), navbar actions, prompt snapshots (the host's `captureRequest`), the clipboard screenshot (a clipboard destination's Take snapshot, and Draw's Copy), what Quick Edit takes from the view (its file, how a copied prompt spells a path, the view as a picture, the viewer's Escape), the one preview state (`shell.previewing` / `setPreviewing`, from `usePreviewState`) and preview's Autoplay (`shell.autoplay`, a viewer preference), alerts, shortcuts, and the live command surface. It owns no zoom control: the shell has none. |
| `RendererShell.jsx` | The frame: viewport box, tool strip (the renderer's tools) at the top-left, the tool stack under the strip (`ToolStack`: the Drawing panel while Draw is up, with Copy at its foot once there is ink, then the renderer's `toolPanels`; the column stops above the view actions, `VIEWPORT_STACK_BOTTOM`), Quick Edit at the top-right, the view actions on top of the view cube in the bottom-left corner (Display settings, whose popover is `DisplayPopover` and opens upward, Reset view and Preview; in preview, Exit preview in Preview's place), preview's controls (`PreviewChrome`: the view actions, and under the model the playbar or the orbit play/pause, either ending in Playback settings), the render profile (`kit/viewport/renderProfile.js`: preview draws the scene one quality tier up, keeps its pixel ratio while orbiting and suspends the tool effects), stopping the routine (`animation.onRelease`) when preview ends, the loading overlay, the update status centred at the top of the viewport, and the alert card. While the model loads, it draws none of its controls; in a compact host (`appearance.compact`), none at all: the model alone. Nothing sits at the bottom centre but preview's playbar, on the `--cad-viewport-bottom-center` line. It takes `references` (what is selected, in the prompt grammar: what Quick Edit attaches and counts) and `copySelection` (what ⌘C / Ctrl+C copies while the renderer's own tool is up and something is selected; null when nothing is). It draws nothing into the host's panel column. One DOM structure (`data-slot="cad-file-view"`, `data-cad-surface`, `data-cad-scene-backdrop`, `data-cad-toolbar`, `data-cad-tool-stack`, `data-tool-panel`) for every renderer. `frameProvider` wraps the WHOLE frame in the renderer's own context — the tool stack as well as the viewport, because both read it — and `onCanvasPointerDown` is a press that landed on the model, for a renderer with something to put down when the person reaches for it. The frame focuses itself on such a press either way. |
| `ShellViewport.jsx` | The three.js viewport around ONE kit scene: `useViewerRuntime`, `useViewportCamera`, the look (rig or studio, environment, background, floor, grid, axes), the Draw overlay and view lock, the view cube (bottom-left, under the view actions; not mounted in preview, `previewMode`, while the model loads, or when the shell says so, `viewCube`), frame presentation and the queued view-settings handshake. Its children may be a function of the viewport (`{ runtimeRef, hostRef, mountRef, viewerReadyTick, commitScene, syncSceneBounds }`), which is how a renderer mounts its own overlay or pointer pick. A scene that changes IN PLACE (it arrives in pieces, swaps its detail, is rebuilt under one identity) calls `commitScene()` from its own effect: the viewport re-reads what it placed, fits the stage and the depth range and applies the framing rules THEN, because a child's effects run before the viewport's own adoption effect. The one thing a commit never does ahead of the viewport is FRAME under a camera that is about to change: when the same render also changed the lens, the projection or the viewing mode, the stage is adopted at once and the framing follows once the camera has been given those props (a stored camera applied under the old projection and then converted comes out about a sixth smaller). A scene that says `complete: false` is framed on what has arrived and once more when it is whole — unless the camera on screen is the person's rather than that first fit, which is true of one they moved during the current mount; reopening always starts with fresh framing. `preserveInteractionPixelRatio` keeps the idle pixel ratio while the camera moves (a scene drawn with hairlines, and preview's orbit: `renderProfileKeepsPixelRatio`), and `runtimeLifecycle` (`onRelease(runtime, { handoff })` while the WebGL renderer is still alive, `onContextLost()`, `onInitializationError(error)`) is for a renderer that hangs its own objects or in-flight work on the runtime. `syncSceneBounds()` re-fits lighting, shadows and the floor's height to a scene that moved its own bounds, with no React render and no reframe. What is SIZED stays sized from the rest placement, in Inspect and in Render alike: the grid and stage (`sceneRadiusForBounds` on `restBounds`) and the Render studio's floor plane (`applyPhotographicStudio`'s `groundBounds`), so a pose or a playing routine never rescales or slides the ground under the model; `zoomToBounds(bounds)` frames part of the scene. Read-only test seams: `window.__cadCamera()` (the live camera, its depth range included) and `window.__cadStage()` (the ground's radius, the bounds the stage is fitted to, the floor's height, the studio floor's size and centre). |
| `fileView.js` | The file's view `{ version, camera, display, playback, renderer }`, read forgivingly and written exactly: the camera (restored in place of the open-time fit; null fits), the Display settings, preview's Playback settings (`tools/playbar/playbackPreferences.js`), and the renderer's own slices, each `{ signature, value }` and restored only under the signature the renderer declares now (`readFileView(raw, signatures)`); the camera, the display and the playback are always kept. The host keys it `[file path, renderer id]` under its root, in the tab store. Not in it: the tool in hand, a selection, measurements, ink, preview, a routine's time — every open starts those afresh. |
| `liveBinding.ts` | `attachLiveBinding`: the live command surface. Base commands (`readState`, `setCamera`, `resetCamera`, `setDisplaySettings`, `setRenderMode`, `capture`) mean the same for every renderer; a renderer ADDS commands by name and DECLINES the known host commands (`HOST_LIVE_COMMANDS`) that make no sense for it with the sentence the caller reads. Binding fails when a renderer does neither. |
| `promptContext.js` | `createViewPromptContext` (a snapshot and what it depicts) and `promptDeliveryError`. A renderer with a reference vocabulary of its own passes `promptContext` instead, and may then return that vocabulary from `promptReferences`. |
| `loadReport.js` | `shellLoadReport`: what the shell asks the status kit about one document load, as one pure function, and all it returns is the loading presentation over the viewport. A renderer whose document is a plain download passes `load` and nothing more. One whose document can be EDITED or PREVIEWED while it is open knows more than the shell can: `load.editPending` (queued work of the person's own, with nothing of it on screen), `load.currentPreview` (that work IS what is drawn, so the wait is over even though the write is not) and `load.finding` (the file is not even located yet). An alert is `load.alert`, which the frame draws as the alert card (`ViewerAlertCard`: every alert; one the model survives, a warning beside it included, can be dismissed). |
| `useViewerShortcuts.js` | Which mounted viewer an Escape or a ⌘C / Ctrl+C belongs to (focus inside it, or the page after a press inside it); the renderer says what Escape means, and a copy is the active tool's (Draw's drawing, else the selection's references, `copySelection`). The order is [the design system's](settings-ui.md#keyboard). |
| `viewportLayout.js` | The corners' geometry: the cube's size and inset (bottom-left), the view actions' height (on top of the cube, the cube's width, a 2px gap), the tool stack's bottom (`VIEWPORT_STACK_BOTTOM`: an inset above the cube and its actions), and the bottom-centre line (`VIEWPORT_BOTTOM_CENTER`, which a host's floating composer moves with `--cad-viewport-bottom-center`). |
| `ViewportContextMenu.jsx` | The viewport's menu on a secondary TAP (a secondary drag pans; primary and secondary together is the pan chord). The gesture, the anchor, the clamping and the dismissal are the shell's; the ITEMS are the renderer's (`contextMenuItems(press)`), asked at the moment of the press, and `onContextMenuOpenChange(open)` says while the menu is up. A renderer that passes no items has no viewport menu at all — every renderer but STEP. |

```jsx
const shell = useRendererShell({
  view,                 // RendererViewProps, unchanged
  services,             // { preferences, onPreferenceChange, live?, captureRequest?, acknowledgeCommand? }
  resource, modelKey, revisionKey,
  features,             // ViewFeatures: the Display sections this family opts into
  toolModes,            // createToolModes({ defaultMode, modes }), or omitted: no tools of its own
  scene,                // KitScene | null
  load,                 // { busy, updating?, progress?, alert? }: the renderer's document load
  animation,            // playbar runtime with its own `clock` (and `onRelease`), or null: plays in preview alone
  live,                 // { commands?, declined?, state? }
  // optional: promptReferences, promptContext, escape, sceneScaleMode, preview, tool,
  //   viewSettings, viewerRef, onCameraSettled, onRuntimeAlert, presentationReport,
  //   preserveInteractionPixelRatio, runtimeLifecycle,
  //   rendererState   { signatures, read }: the renderer's slices of the file's view, read when it is written,
  //                   each restored (by the renderer, `readFileView(view.state, signatures)`) under the same signature
});
// Renderer-facing, beside `tools`, `display`, `toolMode`, `selectTool`, `previewing`, `requestRender`:
shell.syncSceneBounds();         // the scene moved its bounds (a pose): the stage follows, no render
shell.scheduleStateSave();       // a slice changed: write the view soon, and on unmount
shell.playback; shell.setPlayback(patch); // the file's Playback settings: orbit and its speed, Autoplay, the routine's chosen Speed and Loop
// The shell adds Display settings, Preview, and preview's Playback settings and playbar.
const tools = [shell.tools.own({ id, label, icon }), shell.tools.draw].filter(Boolean); // [] for camera-only formats
// toolPanels: the renderer's ToolPanels, shown or `hidden` by the tool they belong to
return <RendererShell shell={shell} tools={tools} toolPanels={<>{selectPanels}{keptPanels}</>}
  viewportOverlay={viewport => <PointerPick viewport={viewport} scene={scene} enabled={selecting} onPick={pick} onHover={hover} />} />;
```

A CAD registration declares no `panels`: the navbar's only toggle is the file explorer's,
and a renderer ignores `openPanel`, `panelSlot` and `onPanelOpen`. Its controls are
`ToolPanel`s in the tool stack, each `hidden` while its tool is not up (a tree keeps its
state), each its content's height, with `fit` saying how it gives way on a short viewer:
`"tree"` first (to 128px or its content), then
`"details"` (to 96px or its content), never `"fixed"`; the column scrolls only if the
rest still does not fit. Every panel is `TOOL_PANEL_WIDTH` wide (164px, a six-tool strip's);
`resizable` — the tree and Position — makes a panel the person's to size on its own, from
handles on its right edge, bottom edge and corner, kept under its `id` (`tree` and `position`
open at half the stack); the Reference is fixed under a `maxHeight` of 288px; every panel
but Drawing folds to its first row, kept by `id` too (`kit/tools/toolStackLayout.js`). Nothing a pick or a tool does
touches the host's column; a pick scrolls its row into view in the tree, which is on
screen whenever Select is.

A renderer whose model moves outside React (a robot's pose) keeps that state in
its own store: `rendererState.read()` is called at the moment the view is
written, so the last write before unmount is saved; `shell.scheduleStateSave()`
says it changed; `shell.syncSceneBounds()` carries the moved bounds to the stage.
None of them renders a component.

The workspace half of a renderer's surface is one hook too
(`renderers/workspace/useWorkspaceDocument.js`): `useWorkspaceDocument({ view, data })`
returns the live catalog entry of the prepared file, the prompt `resource`, the
`services` object the shell takes and the host's commands;
`workspaceLoadAlert` turns a catalog or loader failure into `load.alert`; and
`useDeclinedSelectReference` consumes a host's request to select a reference in
a file that has none without changing the view. A renderer is then its
scene hook, its tool list and its tool panels, if it has any
(`glb/GlbRenderer.jsx`, `mesh/MeshRenderer.jsx`, `robot/RobotRenderer.jsx`). The DXF renderer uses the workspace module without the
shell: it has no scene, so it reaches the same catalog entry and commands directly.

The shell's behaviour has one real-browser test,
`kit/shell/RendererShell.browser.test.mjs` (deferred files, warm reopen, isolated
per-pane state, preview's camera, gated Display sections, settings that never
replace the canvas), and Draw has one scenario (`harness/drawScenario.mjs`)
run under the shell (`kit/tools/draw/Draw.browser.test.mjs`).

The STEP renderer is on the shell end to end: its scene and viewport
([STEP scene and viewport](#step-scene-and-viewport)) and its surface, `StepSurface.jsx`,
whose frame, file view and host glue are the shell's. What STEP keeps of its own is
what only a STEP has — its slices of the file's view (`workbench/stepViewSlices.js`,
read and written by `workbench/useStepView.js`: the tree's expansion, hidden parts and
isolated assemblies, the pose, the large-file setting, each behind the signature that says
whether it still fits the file), its prompt context, and the resource its live state reports while a rebuild is held
behind the previous mesh (`live.resource`). The surface composes modules of its own around
the shell: Measure's session (`workbench/useStepMeasure.js`), the pose and routines
(`workbench/useStepMotion.js`), the context menus as pure descriptors
(`file-view/stepMenus.js`) and what a selection or a node copies (`file-view/stepCopy.js`).
The shell was widened for it rather than forked: it accepts display settings a renderer
made earlier than it could hand them back (`viewSettings`), a viewer handle the renderer
owns (`viewerRef`), externally held tool state (`tool`) and preview state
(`preview`, from `usePreviewState`: STEP's picking and recognition gates run before the shell's hook),
and a load report that knows about finding, editing and previewing.

Its safety net is `step/StepRenderer.browser.test.mjs`, which opens a real `.step`
in a real browser: a two-part component-SURF package with one revolute mate, one
named pose and one routine, committed under `step/__fixtures__/step/` and served by
`harness/stepScenario.mjs` exactly as the backend serves one. The same two shapes
are also served as a package that really ARRIVES IN PIECES
(`stageProgressiveFixture`): twenty-five components held one batch at a time, so
the loader publishes at 8, at 24 and at 25 and the MIDDLE publish is an in-place
change with nothing else moving. That is the only shape of load that can show what
`viewport.commitScene()` is for — two components publish once, and a package whose
second publish is its last is re-adopted by the viewport for reasons of its own.
`kit/tools/draw/Draw.browser.test.mjs` covers the Draw scenario under the shell,
and each renderer's own browser test asserts that the STEP-only Display sections
are absent from it. The shell surfaces only STEP uses so far (the viewport menu and
its open report, the camera-settled report, a scene
that arrives in place, the pixel ratio kept for hairlines, the runtime lifecycle,
and what a renderer says about a load that is more than a download) are driven
through `renderers/shell-harness` in `RendererShell.browser.test.mjs`.

## DXF renderer

`createDxfRenderer` (`@text-to-cad/ui/renderers/dxf`, id `dxf`) shows a `.dxf`. The CAD
renderer does not match one.

It is **not on the shell**, and that is the whole design: a DXF is a finished 2D
document, so the pane is a canvas and the drawing is painted on it. No three.js, no
viewport, no scene, no panel of its own, no Display settings, no tools, no toolbar, no
preview. The
questions the old Material/Bends/Layers tabs answered were about a sheet-metal part
the viewer was inventing from the file; a drawing is not that.

- **The picture comes from the BACKEND.** `client.drawing(file)` is one
  `GET /__cad/drawing` (`apps/web/docs/backend.md`): ezdxf flattens the modelspace on
  the server — text outlined, dimensions exploded, hatches filled, blocks placed — and
  the client receives five primitive shapes in DXF coordinates, y up. **This renderer
  never parses DXF.** The payload is cached server-side by the document's content
  hash, so reopening a file costs a round trip and nothing else.
- **Drawing is core's** (`@text-to-cad/core/lib/drawing2d`), so the headless snapshot
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
  from `@text-to-cad/core/lib/appTheme.js`, the one place both colours are written down.
- **Fills are even-odd, and each one is filled on its own.** A `filled-paths`
  primitive's inner rings are its holes; merging two overlapping regions of one colour
  into a single path would turn their overlap into a hole as well. Fills go down
  before strokes, which is the one ordering that never hides an edge.
- **Interaction** (`dxf/useDrawingView.js`): fit on open and on resize until the
  person moves the view, drag to pan (any primary press, one finger), wheel or pinch to
  zoom about the pointer, double-click to fit again. The view lives in a REF and the
  canvas repaints through one `requestAnimationFrame` when something changed; a pan
  never re-renders the component tree. A resize paints at once, inside the pane's
  ResizeObserver (after layout, before paint): resizing the canvas wipes it, and a frame
  asked for there would leave the pane empty for one frame
  (`dxf/DxfResize.browser.test.mjs`). The backing store is DPR-aware
  (`kit/viewport/pixelRatio.js`), and the cursor is `grab` / `grabbing`.
- **Navbar**: `Take snapshot`, then the file tree's toggle, and nothing else — no
  panel toggle of its own, because the registration declares no panels, and no zoom
  buttons, because zooming a drawing is the pointer's: wheel or
  pinch about it, drag to pan, double-click to fit. The snapshot, a clipboard
  destination's alone, is the canvas as a PNG, background included, delivered through
  `host.promptContext`.
- **Empty and failed drawings.** `bounds: null` (nothing in the modelspace) is a quiet
  sentence over the empty pane, not an error. A non-200 becomes the ordinary actionable
  alert card (`ViewerAlertCard`) carrying the SERVER's sentence (`failureAlert`,
  `kind: "http"`); a payload from
  a cadgen that disagrees about `schemaVersion` gets its own alert whose recovery is to
  update cadgen and the app together.
- **Host commands**: `resetCamera` fits the drawing again, `capture` hands over the
  PNG, and `readState` reports `camera: null` and an empty `display`. There is no zoom
  command and no zoom percentage: no host ever sent one. `select`,
  `clearSelection`, `setCamera`, `setDisplaySettings` and `setRenderMode` are each
  declined with a sentence that says why a flat drawing has no such thing; a
  `selectReference` host request is consumed without changing the view.
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
  pointer, pan, re-fit, the resize rule, and that the file explorer is the navbar's only
  panel, with no tab, tool strip or preview.

## GLB renderer

`createGlbRenderer` (`@text-to-cad/ui/renderers/glb`, id `glb`) shows a `.glb` as
its NATIVE glTF scene, always: one path whether or not a clip is playing. The
STEP renderer does not match `.glb`.

- **Scene** (core's `lib/render/glbScene.js`, which the snapshot CLI draws a GLB with too): the file's hierarchy (nodes, skins, morph
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
- **Tools**: none. The renderer hands the shell no tools of its own (`tools={[]}`), so
  there is no tool strip: a GLB picks nothing, so there is no Select, no filter menu,
  no copy-references action and no viewport context menu.
- **Animation** (`glb/useGlbAnimation.js`): clips play in preview alone, through the
  shell's Playback settings and the playbar under the model (`RendererShell.jsx`).
  The file OPENS AT REST — one `AnimationMixer` on the native scene, built by the
  first play, scrub or clip choice and alive only while a routine owns the pose;
  leaving preview calls the runtime's `onRelease`, which stops it and puts the model
  back at rest, keeping the clip, speed and loop.
- **Panels**: the file tree alone: the registration declares none, so a GLB opens
  with no panel open. Preview is the shell's, as for every 3D file, with the
  Animation settings when the file has clips.
- **Host commands**: the base live commands; `select` and `clearSelection` are
  declined with a sentence, and a `selectReference` host request is consumed and
  acknowledged without changing the view.
- **State**: the shell record under `[path, "glb"]`. Records written under
  `[path, "cad"]` are not migrated.

## Mesh renderer

`createMeshRenderer` (`@text-to-cad/ui/renderers/mesh`, id `mesh`) shows an `.stl`
or a `.3mf` as what it is: triangles, and in a 3MF a colour per object. The CAD
renderer does not match either.

- **Scene** (core's `lib/render/meshScene.js`, `buildMeshScene`, which the snapshot CLI draws an STL or a 3MF with too): one `Mesh` per object of the file (an STL is
  one; a 3MF has one per object and material) and nothing else: no part table,
  display records, edges, clip planes, explode matrices or selectors. Geometries
  come from `@text-to-cad/core/lib/render/meshObjects.js` (`buildMeshObjects`): views
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
- **Tools**: none. A triangle mesh has nothing to pick, measure, pose or
  play, so the renderer hands the shell no tools (`tools={[]}`): there is no tool
  strip and no viewport context menu.
- **Panels**: the file tree alone: the registration declares none, so a mesh opens
  with no panel open. Preview is the shell's, as for every 3D file.
- **Alerts**: a file that fails to parse raises the load alert ("Couldn’t load
  the model", with the loader's error in Details); one that parses to no
  triangles raises "No geometry to display".
- **Host commands**: the base live commands; `select` and `clearSelection` are
  declined with a sentence, and a `selectReference` host request is consumed and
  acknowledged without changing the view.
- **State**: the shell record under `[path, "mesh"]`. Records written under
  `[path, "cad"]` are not migrated.

## Robot renderer

`createRobotRenderer` (`@text-to-cad/ui/renderers/robot`, id `robot`) shows a
`.urdf`, `.srdf` or `.sdf` as its kinematic tree. One renderer, three parsers:
an SRDF is its paired URDF with the SRDF's semantics on it (group states, end
effectors, planning groups), an SDF a robot with one more section. Nothing below the
loader asks which it is. The STEP renderer matches none of them.

- **Scene** (core's `lib/urdf/robotScene.js`, no React, no DOM, which the snapshot CLI draws a robot with too): a scene GRAPH. One `Group`
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
- **Parts** (core's `lib/urdf/robotParts.js`): built once per load. One part per visual, or
  per NAMED object of a visual's mesh (`head:v1/object/0`), with its link, local
  transform, source mesh and palette place. Geometries wrap the loader's arrays
  and are shared by visuals that name one mesh.
- **Loading** (`robot/useRobotDocument.js`, over core's `lib/urdf/loadRobot.js`, the loader
  the snapshot CLI uses): `loadRenderUrdf`, `loadRenderSrdf` or `loadRenderSdf`, then every
  distinct link mesh (`loadRenderMeshByUrl`, at most eight at a time). Progress reads "Loading URDF", "Loading meshes 3/13",
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
  WINS over the colours its mesh file carries: this is deliberate, and a snapshot wears
  it too, because it draws the robot with this same scene.
  Materials are double-sided, so a mirrored `<mesh scale>` cannot turn a link
  inside out. "Color by part" deals the palette in the order parts always took it.
- **Display**: `EDGELESS_VIEW_FEATURES` (Solid and Render; no Edges, Clip or Explode).
- **Tools**, left to right: **Select** (the default), **Position** (only with
  movable joints; shown idle until the robot has loaded; it shows its Position panel),
  and nothing else: Display settings, Reset view and Preview are the view actions on top of the cube.
- **Pose** (`robot/poseStore.js`): joint values live in a store outside React
  (degrees; metres for a prismatic joint), with one write path. A write is clamped,
  ignored under `URDF_JOINT_VALUE_EPSILON`, releases the tracked named pose and is
  heard synchronously: the scene poses itself, the handle list is re-read from the
  motion groups' world matrices (`robot/jointHandles.js`), one frame is requested,
  and the stage follows once per frame (`shell.syncSceneBounds`). Only the control
  that shows the value that changed is subscribed to it, so a pose step renders one
  slider row and no other component. On `juno.urdf` (28 links) a knob step cost
  about 270 ms of script when a pose was React state and a re-placed part list; it
  costs about 3 ms with the Position panel hidden and about 6 ms with the joint sliders on
  screen (a development React build), which is what a frame costs. The opening pose is
  every joint's default, then the SRDF group state(s) named `home` (core's
  `robotOpeningPose`, which a snapshot opens the robot at too).
- **Select**: a selection is any number of links or any number of named objects,
  never both (`robot/useLinkSelection.js`; Shift in the viewport, Shift, Ctrl or Cmd
  on a row add), and the Reference panel names several by what they are ("Links",
  "Mesh objects") and lists them. It exists only while Select is the tool: a pick under
  another tool returns to Select first, and leaving Select clears it. A pick opens
  nothing: its Reference joins the stack under Links. Escape clears the selection. Hover and selection are drawn by the scene (`setHighlight`), with
  the highlight ink a STEP part wears; hover is not React state. A robot has no
  viewport menu and so no framing items; opening the file again fits it afresh.
- **Panels**: the file explorer alone in the navbar. The tool stack holds, under Select,
  **Links** ([Robot links](#robot-links): the filter as its top row, no title), the
  **Reference** with a selection, and **SDF** for an `.sdf` (`SdfSection.jsx`, folded
  until opened); under Position, **Position**.
  `PositionControls.jsx` is the Position panel's body — headed "Position" with Reset
  (`RobotRenderer.jsx`) — the `Pose` label and dropdown (only with SRDF group states:
  `Default`, the states and `Custom` for a hand-moved pose), then a compact slider row per
  driven joint, its thumb named after the joint.
- **Host commands**: the base live commands; `clearSelection` clears the link
  selection; `select` is declined with a sentence (a robot description has no
  reference grammar), and a `selectReference` host request is consumed and
  acknowledged without changing the view. Live state adds `selectedLinks` and `selectedPartIds`.
- **State**: the file's view under `[path, "robot"]`; its one slice is
  `pose: { jointValues }`, written against the description's revision and restored
  only under it. The tracked named pose, the selection and the tree's disclosure
  are not stored.
- **Test seams** (read-only): `window.__cadJointHandles()` (knobs in CSS pixels,
  with values and drawn travel), `window.__robotLinks()` (every link group's frame)
  and `window.__robotPoseStats()` (matrices written per pose, renders of the surface).

## Host integration

```tsx
import { createCadClient } from '@text-to-cad/core/client';
import { FileViewer } from '@text-to-cad/ui/file-viewer';
import { createStepRenderer } from '@text-to-cad/ui/renderers/step';
import { createCadPreferences } from '@text-to-cad/ui/renderers/workspace';
import '@text-to-cad/ui/styles.css';

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

A CAD renderer declares no panel of the host's: the navbar's only toggle is the file
explorer's, and the renderer's controls are panels of its own tool stack. Display is a
popover from the view actions on top of the cube, beside Preview. Preview is the shell's own state in
every 3D renderer, with no host prop: the parent navbar and the host's explorer stay
as they are while it lasts; see [preview](settings-ui.md#camera-animation-and-preview)
and [the host's side](viewer-host.md#preview-and-renderer-navigation-actions).

All package exports are compiled ESM with declarations. Consumers need no
source aliases, JSX transforms for dependency `.js`, or cross-app stylesheet
paths. A bundler must support the emitted `new URL(..., import.meta.url)` worker
assets, which remain inside `@text-to-cad/core`.

## Preferences and the file's view

Everything the viewer keeps is the tab's: one record, `{ version, settings, files }`,
thrown out with the tab and kept across a reload (`@text-to-cad/ui/tab-store`; the host
side is in [viewer-host.md](viewer-host.md#files-state-and-shutdown)). The host hands
the store one adapter — a synchronous read and write of the whole record — and the
package owns the record. Nothing under `renderers/` touches storage, on import,
construction or ever.

**Preferences** are the tab's `settings`, read by every renderer as `CadPreferenceSource`
(`getSnapshot`, `subscribe`, `update`; `createCadPreferences` is the in-memory source a
renderer built without one gets). They hold the tool stack's layout and — for the
host — the file tree's width and expansion and the appearance. Preview's Playback
settings are not preferences: they are each file's own (`playback`, below). Which
panel of the host's is open is the host's (`FileViewerState.panel`):
neither a setting nor part of a file's view. App light/dark appearance selects Inspect's
fixed workbench basis, including the empty CAD stage; the settings contain no theme
choice or custom scene settings.

**A file's view** is `files[[root, path, renderer id]]`, the fifty most recently written
files, each `{ version, camera, display, playback, renderer }` (`kit/shell/fileView.js`):

| Kept | What |
| --- | --- |
| `camera` | The renderer's own: a scene's pose, lens and projection (a perspective snapshot, scoped to the model on read), restored in place of the open-time fit — null, or not a camera, fits; a drawing's plane transform. |
| `display` | The Display settings, Clip and Explode included. |
| `playback` | Preview's Playback settings, every one of them (`kit/tools/playbar/playbackPreferences.js`): `orbit` on or off (on by default) and `orbitSpeed` (1), `autoplay` (off), and `speed` and `loop` once chosen — unset, the routine's authored values apply. Kept between leaving and re-entering preview, and across a reload of the tab; entering preview orbits only if the file's orbit is on. |
| `renderer` | The renderer's slices, each `{ signature, value }`, restored only while the signature the renderer declares for the file on screen still matches. STEP (`workbench/stepViewSlices.js`): `tree` (expanded nodes, hidden parts, isolated assemblies) and `largeFile` against the geometry, `pose` against the sidecar. Robot: `pose` (joint values) against the description's revision. GLB, mesh: none. DXF: nothing beyond its camera. |

| Not kept | Every open starts it afresh |
| --- | --- |
| The tool in hand | The default tool |
| The selection, measurements, Draw's ink | Empty |
| Preview and its camera | Off; the tools view's camera is the one kept, and its Playback settings are the file's (`playback`) |
| The routine, its time and whether it plays | At rest |
| Quick Edit's note | Empty, its box following what is picked or sketched |
| The Select mode filter, hover, menus, popovers | Closed |

The rule is one generic one in `readFileView(raw, signatures)`: a slice whose stored
signature is not the declared one is absent; the camera, the display and the playback come
through whatever the signatures say. A renderer hands the shell `rendererState: { signatures,
read }` and reads its slices back on mount with the same call; it never sees storage.

## Prompt references, captures and extensions

References, inspection text and PNG captures produce one `PromptContext` through
`host.promptContext`. Workspace/path/revision identity and typed targets are
preserved; a capture names the references it depicts. Ordinary explicit copy
controls use `host.clipboard`. The viewport only produces screenshot pixels.
The port and app adapters own delivery and return an acknowledged outcome.

Quick Edit (`kit/tools/quick-edit/QuickEdit.jsx`) is the shared note to the agent:
a box at the top-right, there only while it has something to carry, which
`RendererShell` mounts for a renderer that hands it `references` — STEP alone, the one
format with picks and sketches (a compact host gets none). Its box, header and buttons are the design system's
([Quick Edit](settings-ui.md#quick-edit)); what it can do follows the host
([prompt handoff](viewer-host.md#prompt-handoff)), never an app. The renderer hands
the shell what is selected as `references`, in the prompt grammar (STEP's, under
Select while its references can be read; the file itself always goes), and the
shell hands Quick Edit the file, how a copied prompt spells a path
(`FileSource.referencePath`), the view as a picture, ink included (`captureView`),
the viewer's Escape, and the box's size as the person drags it, kept across files.
`quickEditPrompt.js` builds the context at the press, from
what is live then (`createQuickEditContext`), and the text a copy writes
(`copiedQuickEdit`, over core's `formatPromptMessage`). Draw hands it the sketch:
whether there is ink, and the view with its ink as a picture. Copying without Quick
Edit is the Reference panel's Copy and Draw's Copy Drawing, which write the clipboard
directly. See
[ViewerHost](viewer-host.md) for lifetime, focus, supported content and clipboard
representation limits.

An optional `ViewerCommandSource` (`@text-to-cad/ui/renderers/workspace`) has the same
subscription shape and publishes
`selectReference: { selector, key? }` or `captureRequest: { key }`. A fresh key
requests another operation even when its selector or target file is unchanged.
Selecting a reference also expands the matching Features row's ancestors (under All)
and scrolls it into view; the Features panel is on screen whenever Select is, and
nothing opens or turns the host's panel column. Repeating the request
reveals the existing selection again without toggling it off; a face-group
reference keeps the group highlighted and reveals its active face.
Both toolbar capture and host capture commands use the same implementation.
Hosts can provide `acknowledge(kind, key)` to consume an admitted command. Desktop
binds commands to the active project/tab/path/root and removes only the matching
nonce, so an old acknowledgement cannot clear a newer request or replay after a
remount. A capture waits for ready geometry; a selected reference waits until it
can resolve against the current model.

`@text-to-cad/ui/file-viewer/presentation` exports the lightweight
`ViewerLoadingOverlay` and `MissingFileAlert` for host bootstrap and generic
viewer loading/error presentations. Their markup and wording are the original
CAD artwork. They mount inside a relative container and require no CAD client.

The optional `live: CadLiveBinding` registration binds a mounted
`CadLiveController` for app-owned view tools. It reports the actual resource
revision, selection, camera, display and mode, supports explicit controls and
captures a PNG without prompt delivery or clipboard effects. It never substitutes
catalog or persisted state for a live viewport. On unmount it retains only a
serializable inactive snapshot; controls require the tab to be shown. See the
[viewer host contract](viewer-host.md#app-specific-interfaces) for lifecycle and
stale-operation rules, [`liveBinding.ts`](../src/renderers/kit/shell/liveBinding.ts)
for the signatures every renderer shares and [`live.ts`](../src/renderers/step/live.ts)
for STEP's (its selection, hidden and isolated parts, `select` and `clearSelection`).

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

The camera is the file's: opening, reopening or reloading restores the one the file was
left at and fits only when there is none. Presets update projection/lens while retaining viewpoint and
zoom on the same renderer, canvas and controls. Ordinary settings edits never
restart the viewport. Initial/reset/fit views use the
projected bounds with 1.1 padding (roughly 91% occupancy in the limiting viewport
dimension), rather than a bounding sphere. Manual views retain their own
zoom and pose. This policy belongs to the interactive UI; snapshot/export
framing remains independent. The orientation control labels its positive X/Y/Z
axes and retains its snap and drag interactions.

See [settings controls](settings-ui.md), [render capabilities](render-types.md)
and [renderer contracts](renderers.md) for changes inside the shared package.

The optional `@text-to-cad/ui/file-viewer/empty` entry exports `EmptyCadBackdrop` for the web host’s missing-file presentation. It lazily mounts an empty CAD viewport with the host’s `colorScheme`, and overlays its `children`. It owns no file access, catalog subscription, or persisted state. This preserves the original grid and camera behind `MissingFileAlert` without loading CAD into the master viewer. Its stage (`file-viewer/EmptyCadStage.tsx`) is `ShellViewport` with a null scene, built out of the kit alone: the file viewer MOUNTS a renderer through the registry and imports none itself, because a static edge into a slice pulls that family — and three.js with it — into every host that shows any file at all. `scripts/test/check-kit-boundaries.mjs` enforces that alongside the kit and slice rules.

## STEP scene and viewport

`createStepRenderer` (`@text-to-cad/ui/renderers/step`, id `step`) shows a `.step` or
`.stp`. Its scene and everything of it that lives in the viewport are on the kit;
`src/renderers/step/scene` is that half.

- **Scene** (`scene/stepScene.js`): a kit scene around core's `buildModel`
  (`@text-to-cad/core/common/cadScene.js`, which is also the headless renderer's and
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
  the stage, which are the viewport's. **So nothing STEP draws may be parked in the
  viewport's model group.** An overlay that belongs WITH the surfaces rather than
  with the linework — the reference highlight's face fill — hangs in this scene's
  own `overlayObject3D`, a permanent child of its root: a rebuild took the outline
  (the edge layer IS cleared) and left a fill lit over a model it was no longer
  measured against. That fill is rebuilt whenever the records are
  (`displayRecordsToken`), because its geometry is read off the display meshes on
  screen. The LOD publisher's ownership protocol (`onMeshSourceAdoption`) is
  answered for every source the scene shows, releases or fails to show, and for
  every way the WebGL runtime under it can go away (`runtimeLifecycle`) — which is
  also the ONE place the scene is released. The viewport does not release it a
  second time from an unmount of its own: two owners firing parent-first worked
  only because `dispose()` happens to be idempotent, which is a property to lean on
  in recovery, not a teardown design.
- **The ground is sized from REST.** The viewport sizes the grid, the stage and the
  Render studio's floor from `restBounds`, as it does for every renderer, so posing
  a mate or playing a routine never rescales or slides the ground — including a
  Render entered while the model is posed.
- **Shadows** are per record (core's `syncRecordShadowPolicy`: only an opaque, lit surface
  takes or casts one), so the scene implements `setShadowReception` and the viewport
  never sets its meshes itself.
- **Look.** `setSurfaceLook` is the kit's half; the theme, the app appearance (edge
  ink), authored-material overrides, the whole Surfaces section and shadow
  reception are STEP's (`setLookContext`). Both resolve the same settings, so the
  scene wears a look once: whichever arrives second finds it already on.
  `keepsAuthoredFinish` is `hasAuthoredMaterials(meshData)`.
- **Viewport**: the shell's own `ShellViewport`, mounted by `RendererShell`; STEP
  does not wrap it. The surface decides what it may show and pick just now (nothing
  under Position or in preview; no topology while a previous mesh is held over
  an update) and hands the viewport menu, the selection's references and its copy to the shell, and it
  keeps the two things only a STEP can answer, beside the kit viewport's handle: `sampleLodCamera` and `zoomToFitSelection` (the boxes of the selected
  references, from the selector runtime as posed, merged with the boxes of the
  selected parts, from the records on screen).
- **Layers** (`scene/StepSceneLayers.jsx`), mounted through the viewport's overlay
  slot, in the order that is their contract: the scene sync makes the records, part
  state dresses them, the pose pass moves them, the exploded view offsets them, and
  only then are the pick proxies, the linework and the highlights laid over where
  they ended up.

  **Hover is not React state.** What the pointer is over — the reference or part under
  it in the viewport, the Features row under it — lives in the surface's hover store
  (`workbench/hoverStore.js`: `getSnapshot`, `subscribe`, `update` and React-shaped
  setters). The surface writes it and never reads it; the layers subscribe to it and
  resolve it through the surface's `resolveHover` (the part ids to light, the reference
  to outline, the viewport menu's marked part, nothing in preview). So a hover
  re-renders the layers and nothing else — not the surface, its tool stack or the
  Features tree, which on a large assembly cost about a second a hover —
  and `StepHover.browser.test.mjs` counts the renders to keep it so.

  | module | what it owns |
  | --- | --- |
  | `useStepViewPolicy.js` | Everything DERIVED from the settings and the selection, touching no scene: the normalized display state, which linework is drawn, the edge styling a mode forces, what is pickable once hidden and isolated parts are out. |
  | `useStepSceneSync.js` | The scene sync: reuse or rebuild, the LOD ownership protocol, the topology line, pick groups, the raycast-BVH schedule and the section clip over the new records; STEP's half of the look. |
  | `useStepDisplay.js` | `useStepPartVisualState` (hidden, isolated, hovered, selected parts) and `useStepLinework` (pick proxies, B-rep edges, a highlighted part's brighter edges). |
  | `useStepPose.js` | The sidecar module's setup and the ONE pose/animation pass (below). It refreshes core's placed bounds and calls `syncSceneBounds()` before drawing, so the near plane and shadows track moving parts. |
  | `useStepExplode.js` | The exploded view: a radial layout eased over a second, snapped by the slider, re-applied to fresh records. |
  | `useStepHighlights.js` | The reference highlight: boundary lines and fills of selected and hovered faces, edges and vertices, in two layers — the selection's, rebuilt when the selection is, and the hover's, rebuilt with each hover — that draw what one pass did: a reference both selected and hovered is drawn once, as hovered. A face's fill is read off the display meshes through a per-mesh index of their face runs (`faceRunIndex` in core's `referenceGeometry.js`), not a walk over every triangle on screen. |
  | `useStepMeasureOverlay.js` | The measure canvas: rulers and the snap indicator. |
  | `useStepPicking.js` | The pointer: hover, tap, double-click (the surface copies a face or edge, isolates a part, or leaves isolation on empty space) and measure picks, with all of the topology raycasting. A tap activates at once; which tap of a click sequence activates, and when, is `clickActivation.js`. The viewport menu is NOT here: it asks this hook what is under a press (`pickAtRef`). |

- **One owner of the frame after a pose.** A pose or animation write is drawn because
  the pose pass asks for a frame, once, as its last act, and nothing else on that
  path does: the topology line it re-syncs is told not to
  (`syncTopologyDisplayEdgeLine(..., { requestRender: false })`), a highlight layer
  asks only when it drew or had drawn something, and part visual state does not
  re-run for a pose at all — every part-id list the workspace hands the viewport
  keeps its identity while its contents hold, because each is derived through a
  memo and the empty case is one shared frozen list
  (`components/workbench/hooks/useCadWorkspaceSelectors.js`). It passes through the viewport by identity
  from there, with no comparison of its own to hide churn upstream. `StepRenderer.browser.test.mjs` fails its
  Position and routine tests when that one request is removed.
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

STEP's Select tool filters by All, Parts, Faces or Edges and, under **Connected
selection**, Group edges or Group faces (`workbench/selectionFilter.js`); Measure's
snapping filters are Any geometry, Points, Edges and Faces. Explicit
filters never fall back to a different entity type. In an assembly, face and edge filters
(the connected ones too) load topology per leaf part, on demand: a press on a part whose
faces are not pickable yet requests that part's topology through the same per-node path a
Features row uses (`loadInspectionTopology`, which expands it in the tree), holds the press
(`pendingTopologyPick`, with "Loading selectable geometry…" under the toolbar) and, once
the part's references are composed, picks again at the same point through `pickAtRef` —
one press, never the part. A hover over such a part lights the whole part, the one hint
that a press there reaches it. A chosen part is also loaded when the filter is picked.
Opening a STEP starts with render geometry; activating Select or Measure requests
exact inspection topology when it is needed.
Shift-click adds/removes entities. A double-click on a face or edge (outside the
Parts filter) copies it and leaves it selected; on a component or subassembly it
isolates it, and on empty space it leaves isolation. A click acts at once: nothing
waits to tell it from a double-click. The first click of a double-click therefore
selects, briefly, whatever it hit; the second is not a click of its own (the browser
counts it, `clickActivation.js` holds it for the `dblclick` that owns the gesture),
and the double-click begins by putting the selection back the way its first click
found it — through the same setters every pick goes through, so the Reference panel,
the tree and the viewport follow — before it isolates, leaves isolation or copies.
The one click that still waits is one under a tool a pick would leave (Explode, Clip:
a pick there takes up Select): it is held for the double-click window
(`deferActivation`), so a double-click there isolates and stays in the tool, and a
lone click selects and switches to Select once the window has passed.
Every copied reference — the
Reference panel's Copy, ⌘C, both menus, the double-click — carries the file's prefix through
one `copyTextLines`: the name the host gives the file (`FileSource.referencePath`),
by default its path under the host's root, the real file name with its extension.
Escape clears the
selection after any open menu has been dismissed. Input fields
keep their own Escape behaviour.

Measure starts as an exclusive picking tool, and its **Measure** panel is up at once,
empty: its heading carries the snapping menu (All, Points, Edges, Faces:
`MeasureModeMenu` in `SelectionModes.jsx`, over `ToolModeMenu`, passed as the panel's
`actions`), and its button shows the mode in hand. Completed rulers are the panel's body
(`MeasurePanel.jsx`).
Leaving Measure cancels its draft but retains completed rulers, its panel and the
button highlight (`useModelTools`' `measure.shown`); a mode chosen in the kept panel takes
Measure up again without clearing. A press on Measure while it is up — results or none —
or the panel's X clears it and puts it down. Panels use the shared `ToolPanel`.

Clip mode colours cut surfaces amber using stencil winding over the display
meshes. Holes remain open for closed, consistently oriented solids. This is a
non-pickable display fill, not new topology or an edit to the STEP. Only meshes
whose bounds intersect the active plane receive the two extra stencil passes;
disabling clipping releases the fill and materials without disposing the model's
geometry. Open/non-manifold meshes cannot guarantee a solid section fill.

**Group faces.** Clicking a face selects its connected
chain across edges classified as tangent by the loaded STEP topology; sharp,
unknown, boundary and nonmanifold edges stop the chain. Selection never crosses
occurrences or solid shapes. Shift-click adds a chain, or removes it if the whole
chain is already selected. The resulting faces use the existing highlight and
Copy Reference controls. An assembly part loads its topology on the first press, as
with the Faces filter. This changes selection only, not CAD geometry.

Group edges uses tessellated edge endpoints within the same solid/occurrence and
a shared face, with a 0.00001 model-unit endpoint tolerance. It follows corners
where only one continuation exists and a unique smooth continuation at branches;
ambiguous branches, missing endpoints, and closed single edges stop traversal.
Shift toggles the resulting group, and Copy Reference copies its canonical edge refs.

### STEP panels

A STEP's panels in the tool stack (`components/workbench/StepPanels.js`), in order:

- **Features** (Select): the `Filter…` box as its top row, then the model tree
  (`ModelingTree.jsx`). It gives way first on a short viewer and scrolls inside itself.
- **Reference** (Select, with a selection): headed by the reference being read
  (`StepReferenceSection.js`'s `useStepReference`: its label, else its part as the tree
  names it and its kind — `base · face 3`; with several, a picker with `i/N`) and an X
  that clears the selection; its rows are the browsed reference's alone, compact and in the
  UI font, under a 288px cap the person can drag.
- **Position** (Position): named poses, joint values and Reset, when the file has
  kinematics.

Each is `hidden`, not unmounted, while its tool is not up.

**Select modes.** Select's mode menu (`SelectModeMenu` in `SelectionModes.jsx`, over
`ToolModeMenu`), in the Features filter row beside its chevron (`ModelingTree`'s
`modeMenu`), holds four exclusive modes — All, Parts (assemblies only), Faces, Edges
(`workbench/selectionFilter.js`'s `SELECT_MODES`), each row its mode's glyph at full
size — whose composite the strip's button shows (`SelectModeIcon`: the pointer badged with
the mode's glyph; Measure's `MeasureModeIcon` is the ruler badged with its snapping mode,
`MEASURE_SNAP_MODES`) — then, below a rule, the independent checkboxes Group edges and Group faces
(`CONNECTED_SELECTION`, applying under All and their own mode; only those that apply
under the mode in hand are shown, and a hidden one keeps its choice). `StepSurface`
keeps the mode (`selectionFilter`) and the options (`connectedSelection`), and a mode
change sets the tree's expansion (`changeSelectMode`): leaving All saves the person's
expansion and coming back restores it (with the owners of selected topology kept open);
Parts opens every assembly (`collectStepTreeAssemblyNodeIds`) and shuts every part;
Faces and Edges open every assembly and leave each part to the tree, which asks for a
part's topology (`onLoadTopology`) and recognition as its row comes on screen (the rows
the tree's list reports in view, below). Those requests, and every other
(`loadInspectionTopology`), cost a lookup for a part already requested; new parts expand
together at most every 150 ms. The loader behind them (`useCadAssets`'
`loadReferencesForEntry`) unions requests for the file revision it serves, never aborts its
own work for them, and loads in batches of at most 64 new parts, newest request first, each
composed incrementally (only the new parts are built); a part requested while a batch is in
flight loads beside it rather than after it. While more loads, what is loaded stays
pickable: a composition serves the request while every part it holds is still requested
(`topologyCompositionServes`), and Select is "Preparing selection" only with nothing usable yet.
A new file revision still invalidates everything loaded. Outside All the tree's
disclosure is locked (`data-disclosure-locked`) and the part menus drop Expand/Collapse.
The one-press load for a part not yet loaded stays in the pick path; the Features filter
row shows `Loading…` while it waits.

**A large tree under Faces and Edges.** Above `LARGE_TREE_ROWS` (300, in `ModelingTree.jsx`) rows
of assemblies and parts — the fully expanded tree less the features recognition adds under a
part later, so the tree never changes shape under the person — Faces and Edges keep every
assembly open and locked but start every part closed: its disclosure is its own (the lock is
lifted for part rows alone). A part row shows no face or edge count. A part opens by its disclosure, by a pick inside
it (the reveal opens it and scrolls to the picked row) or by its row menu's Expand; Expand all and
Collapse all open and close every part. A closed part on screen asks for nothing; opening one asks
for its topology and recognition at once (Expand all leaves that to the rows as they come on screen),
and the viewport asks for the part under a pointer that rests on it for `TOPOLOGY_DWELL_MS` (150) or
presses it, read from the viewport's hover store (`workbench/hoverStore.js`), each part once.
Below the threshold, and under All and Parts, nothing of this applies.

Explode and Clip follow Measure on the strip; Explode only with two or more parts
(hidden, never disabled, once the mesh is known). Their panels
(`components/workbench/ModelTools.jsx`), with Measure's results panel, follow the tool's
own panels in the stack, in the order added, with no enable checkbox: a
panel opens neutral and an edit applies its effect. A neutral panel goes when another
tool is chosen, or when the pointer is released after a drag that ended at neutral —
a press inside the panel column holds every panel until it lets go, so a slider
dragged through its neutral value keeps its panel. An applied effect keeps its panel
and its button's highlight across tools. X, or pressing the tool again, resets and
removes the effect. Clip uses an axis selector, one slider/input and Flip; its plane and
slider range share the original bounds, unaffected by pose or Explode. The lifecycle is
[the design system's](settings-ui.md#tools-and-lifecycle).

Position controls are the Position panel, shown by the Position tool, which also
enables joint handles. Robot viewers use the same shell, the shared `Pose` row and the
heading's Reset (`kit/inspector/kinematicsControls.jsx`). Animation belongs to preview.
Display is not a tool: opening its popover leaves the tool in hand, and the
selection, as they are.

**The tree's rows are a window.** A large assembly opens onto thousands of rows, so the
tree (and a search's hits) is one flat list of its visible rows — each open branch's children
after it, a level deeper — drawn by `kit/inspector/VirtualRows.jsx`: only the rows in the
panel body's view and a margin either side are mounted, each at the place the whole list
would give it, in a list as tall as every row, so the scroll range, the rows' positions and
what is drawn are those of the whole tree. The window follows a scroll before the frame that
shows it. The selection's row, the search cursor, a focused row and the row whose context menu
was opened stay mounted wherever they are, so a reveal, Enter, keyboard focus and an open menu
always have their row; a row carries its level
(`aria-level`) in place of the nesting it no longer has. Under Faces and Edges the rows the list
reports on screen (never its margin), once layout has settled a frame later, are the parts
whose topology is asked for, each once (in a large tree, only the open ones). A face or edge
picked on a part not yet recognized asks for that part's recognition itself, so its feature row
arrives and is revealed wherever the part sits in the tree.
Rows are memoized on their own facts (their selection and joins as booleans, stable callbacks,
the one `partControls` object `useStepPanels` keeps), so a re-render of the viewer that changes
nothing in a row renders no row. Recognition (`useModelingRecognition`) runs one component at a
time in one worker kept for the next, and its results reach the tree at most once a frame.

The Features rows share the file tree's row primitive and 28px height, inset 4px from
the panel, with a 20px disclosure column and 12px per level. The disclosure
button expands children; the rest of the row selects its canonical references.
Labels keep the row's width; summaries and measurements belong in the Reference
panel. An assembly row's actions (`ModelPartActions.jsx`), shown on hover and kept
shown while they are on, are Isolate (lit while that node is isolated; not in a part
file) and then Hide (the eye). A double-click on a component or subassembly row
isolates it too; Isolate is also in the row's context menu.

That menu is THE part menu, the one the viewport offers over the same part: one
descriptor (`assemblyNodeMenu`) and one set of actions (`partMenuActions`),
rendered by `AssemblyPartMenuItems`, so the two cannot drift apart. Copy Reference, Select/Deselect, Isolate/Exit isolate, Exit all isolates, Hide
others, Hide/Reveal, then the tree's Expand/Collapse and Expand all/Collapse all,
and last one framing group: **Zoom to fit** and **Zoom to selection** (off without
a selection). Framing cannot contradict the tool in hand, and every item of this
menu returns to Select before it acts. The VIEWPORT's menu exists only while Select is the
active tool — under Measure, Draw or Position a secondary tap opens nothing (in preview there is no viewport menu),
though the native menu stays suppressed and a secondary drag still pans. The
TREE is Select's panel; every action of its menu returns to Select first
(`ensureSelectTool`). A secondary tap on
empty space asks about the model as a whole (Show all, Expand all, Collapse all,
then the framing group). A single-part STEP has no part menu — a press on the part
opens this one too — so there it opens with the part menu's reference group for the
whole part (`<file>#`): Copy Reference (`modelMenuDescriptor`'s `copyText`). The tree starts directly below `Filter…`, the file
tree's filter box (`TreeFilterInput`, `primitives/tree-filter`), with a conditional
Show all on the filter row's right side. While something is isolated, an isolation
bar heads the tree (`Isolated: …` and **Exit**). There is no feature-count header.
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
Viewport hits select individual faces and edges in All, Faces and Edges modes,
independently of inferred feature grouping or tree expansion within the part.
Feature rows select their groups only when clicked in the tree; connected
selection modes explicitly opt into edge chains or tangent face groups.
Double-clicking empty space exits isolation. Collapsing a part or leaving
isolation clears topology selections whose owners leave the expanded tree;
the copy action only appears for a resolved selection.

Isolation restricts the selectable subtree without propagating an excluded
ancestor's disabled state into the isolated descendants. Hidden geometry stays
unselectable. Selection reveals expand the required ancestors and scroll once
per selection or explicit reveal command. Later expansion, recognition updates
and manual scrolling must not pull the view back to that row.

The Reference pane is read-only, fixed in size (every panel's width, capped at 288px),
independently scrollable, and pinned at the panel's foot, under every section. Its
static heading has a Copy action (the reference on show, file-prefixed as Copy Reference copies it) and an X to clear the selection; neither the pane nor its
fields collapse. A compact dropdown browses the selected references directly
without modifying the selection. New selections show their newest reference.
Selection totals remain above the current reference's name, type, wrapping
canonical ID, dimensions, coordinates and source material. Rows share an 8px
gutter, an 80px label column and 11px text, with thin separators between totals,
reference facts and material. The pane's rows have no copy or dimension-preview
buttons: copying is the heading's Copy, the full-row **Copy** at the panel's foot
(**Copy All** with several references, with the ⌘C / Ctrl+C hint; shown only for a
resolved selection) and the tree and viewport menus, and measurement previews are
the Measure tool's. There is no source feature view.

Tool order, tool panels, persistent panels and cleanup policies are defined in
[the shared design system](settings-ui.md#tools-and-lifecycle). Keep renderer
implementations aligned with that contract instead of defining another layout here.

A selection exists only while Select is the tool. Leaving Select for any other
tool drops the selection, in the viewport and the Model tree alike; choosing a
row in the Model tree (or a host `selectReference`) under another tool returns
to Select first. No other tool ever sees a selection, so none needs a rule for one.

### Position

Position edits persist when switching tools or tabs, or closing the panel. Reset
explicitly restores STEP defaults or the robot opening pose (including SRDF `home`).
The Position tool controls joint handles and shows its panel.
A routine playing in preview sets the Position values aside when it takes the pose and gives them
back when it lets go (`workbench/useStepMotionControls.js`). The Position panel's layout
is [the design system's](settings-ui.md#position-and-references).

The Position tool (lucide `Spline`; its tool id is `pose`) drags a model's joints
by handles in the viewport. It exists where
something can be driven: a robot (URDF, SRDF, SDF) with a revolute, continuous
or prismatic joint that is not a mimic follower, and a STEP whose sidecar
kinematics declare a revolute, slider or cylindrical mate. Robots and STEP files
open in Select. Robots also discard a previously recorded Position tool on reopen
to match their initial Links tab; stored joint values restore independently. It is absent in preview. While it is active the model picks nothing, hovers
nothing and casts no model ray (`pickMode` NONE, as in preview); the camera
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

`onChange` is the Position section's own change path (the robot pose store's
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

Every pose write is a jump: a slider drag, a typed number, a Position knob, a named
pose (a STEP sidecar's pose, an SRDF group state) and Reset all put the model
where it IS from that frame on, for robots and STEP alike. There is no eased
pose transition and no preference for one; motion over time is
preview's. Each format has one write path (`write` in `robot/poseStore.js`;
`writeParameters` in `useStepMotionControls.js`).

### Routines in preview

There is no Animate tool: routines play in preview alone, the regular view being
for editing and preview for watching. For a file with routines, preview's
**Playback settings** (`kit/tools/PlaybackMenu.jsx`, the cog at the playbar's right end,
opening upward) holds an **Animation** group — Routine (only with two or more routines),
Speed (the presets, and an authored speed outside them), Loop and Autoplay — above
**Orbit**; the transport is the playbar under the model (`ViewportAnimationBar`):
Play/Pause and the live scrubber. There is no Restart; the scrubber's start is the
restart. Entering preview plays only when the file's Autoplay
(`playback.autoplay` of its view, `kit/tools/playbar/playbackPreferences.js`, off by
default) is on, and orbits only if its orbit is on (on by default), at its orbit speed;
a Speed or a Loop chosen in Playback settings is the file's too, applied to its routine
(`RendererShell.jsx`), while unset the routine's own apply. Every choice in that menu is
kept between leaving and re-entering preview, and across a reload of the tab.
Nothing under the pointer is pickable in preview.

A routine owns the model's pose only inside preview. Leaving it releases the clip —
the shell calls the runtime's `onRelease` (a GLB's), and STEP's surface
`releaseAnimation` — stopped, rewound, the pose handed back to the Position controls,
so selection, topology and the Position controls never meet an animated model. Of the
playback only the transport preferences survive leaving — the routine, Speed and
Loop, kept by a Position edit too (`activatePositionControls` in
`useStepMotionControls.js`) for as long as the file is mounted: the next preview plays that
routine from the start. The routine and its time are not saved: a reopened file starts
at rest, with the Speed and Loop its Playback settings chose, if any. A routine that failed to
load has no Playback settings to say so in; the viewport's card says
`Animation unavailable`, and can be dismissed.

Because preview picks nothing and ends at rest pose, pick-only state stands
still while it lasts (`animateMode`, which is `previewing`, in `step/scene/useStepPose.js`): the transformed selector
runtime is not rebuilt per posed frame (as React state it would rebuild pick
groups, their BVH, the picking listeners and the highlight overlays every
frame), pickable lists are one shared empty list, presses and releases cast no
model ray, and part visual state is not reconciled while a routine plays. The
pass that leaves preview re-runs once and rebuilds the pick state. Independent
of preview, a routine's feature resolution is memoized per definition and parts
array (`stepModule.js`), the clip-plane sync is skipped when no section is or
was active, and the view cube is memoized.

No component renders for a playing frame. The viewer's pose pass is one function
with two callers: React runs it when something it reads changes (a scrub, a
pose, a display setting, a new mesh) and publishes it through a ref; while a
routine plays, the animation clock calls that same function once per tick
(`usePlaybackFrames`; the GLB renderer drives its mixer the same way). Both
callers draw the routine at ONE time: while it plays, that is the clock's, never
the time React holds (where playback started, written back only when it stops),
so a pass React re-runs mid-play — a detail swap, a progressive publish, a display
change — draws the frame the next tick would (`playbackFrameTime`). The
scrubber is the clock's only React subscriber. Because the pass runs inside
the tick, the clock's adaptive pacing measures a frame's real cost. A frame that
only moved parts skips material and instance-membership reconciliation: the
effects pass reports whether a style, visibility or highlight changed
(`applyStepModuleEffectsToRecords`), and moved instances sync their own matrix.

### Draw

Draw is the shared [drawing editor](drawing.md) (Excalidraw) laid transparently
over the viewport. It is a STEP tool and appears on no other format: a GLB, an
STL, a 3MF, a DXF and a robot description do not offer it. (The tool itself is
the SHELL's — `kit/tools/draw`, `shell.tools.draw` — and STEP is the renderer that
puts it on its strip; `renderers/shell-harness` also mounts it, for tests.) The
chunk loads on the first use of the tool, and the
surface stays hidden until the editor has its scene, so its default white page
never flashes over the model. Draw's **Drawing** panel leads the stack while Draw is
up, with the shared drawing controls in one wrapping row: Select and move drawings,
Pan view, Pen, Line, Arrow, Rectangle, Ellipse, Text, Fill area and Eraser, then Color,
Undo, Redo and Clear drawing. Choosing a tool updates Draw's toolbar icon. Pressing Draw
again puts it down, and leaving Draw ends the drawing session. Select and move drawings wears lucide's
`SquareMousePointer`; Undo and Redo are off while there is nothing to undo or redo.
A line is followed by another line. Color changes what
is drawn next without recoloring existing ink. Fill area is not an
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
the renderer unmounts; a restored tab never reopens in Draw. While the sketch has
ink, the Drawing panel ends in a full-row **Copy Drawing**, with the copy shortcut beside it (⌘C or
Ctrl+C does the same): the viewport capture with the editor's committed ink
composited over it viewport-aligned (the ink canvas keeps its own pixel ratio and is
scaled into the frame; selection handles are not included), written to the clipboard
as a PNG (`host.clipboard.writeImage`). The same view with its ink goes with a
Quick Edit note: the first ink opens Quick Edit, whose header says **drawing**, and it
takes the keyboard once the pen lifts; with its note empty it closes when the ink goes.

### File navbar

The file navbar holds the renderer's actions, then the panel toggles; pressing a
toggle opens that panel and closes whatever was open. Left to right: the direct
snapshot action (`Take snapshot`, `Camera`; a clipboard destination's only: a composer
or unavailable destination has none, its note to the agent being Quick Edit) and the file
tree, id `tree` (`Folders`, labelled `Show files` / `Hide files`), when the host's
source lists files. No CAD registration declares `panels`: every
CAD file has the tree alone, its controls being panels of its own tool stack. The
tree is FileViewer's own (`treePanel`), always last. Display is a popover from the
view actions on top of the cube and never a panel of the host's. The renderer's update status is
in the viewport, centred at its top, never in the navbar. So a host shown small in a
conversation (`compact`) has no navbar at all: its card names what it shows.

With nothing chosen (`panel: null`) a CAD file opens with nothing beside it; the tree
is the default only when no file is open at all. On mobile a file opens with no sheet
over it ([the tool stack](settings-ui.md#the-tool-stack)). A file picked in the tree is opened with `panel: "tree"`
(`navigation.openFile(path, { target, panel })`), so the tree stays up while it is
walked; any other open starts the file at its default, and the host applies either
(`viewer-host.md`). `""` is nothing open, and so is an id the file's list does not
have.

Take snapshot captures the view (with Draw's ink, when there is some) and writes it
to the clipboard as a PNG (`host.clipboard.writeImage`), which is the web app's case.
The host's `captureRequest` command is the same capture: to a composer destination
it goes through the prompt-context port (`promptContext.deliver`) with the references
it depicts.
The DXF renderer, which is not on the shell, contributes its own Take snapshot, a
clipboard destination's alone, through the prompt-context port.
The shared FileViewer renders these registered actions without importing CAD.

### Preview and camera

Camera framing, routines and preview follow the shared
[interaction contract](settings-ui.md#camera-animation-and-preview).
`useViewportCamera` owns initial fit, orientation transitions and the preview
camera swap (`previewCameraRef`, `syncPreviewCamera`): entering saves the tools
view's camera and fits a fresh preview camera; leaving restores the tools pose
exactly, converted into the projection and lens the Display settings now hold.
`zoomRuntimeToBounds` is the single framing act used by context-menu
Zoom to Fit and live `resetCamera`. Cube shortcuts preserve zoom and pan.

Preview is one `previewing` state the shell owns (`usePreviewState` in
`useRendererShell.js`); a renderer whose own gates run before the shell's hook holds
it and passes it in as `preview`, as STEP does. The Preview button among the
view actions sets it, and Escape or Exit preview clears it; no host prop reaches it.
While previewing, the frame drops the toolbar, the tool stack and its resize handles,
Quick Edit, view cube (not mounted), alert card and viewport menu (the host's panel
column stays as it was), and every renderer gate reads the same state: picks, hover,
highlights, recognition, Measure, Draw, joint handles, and Select and Position as tools
are off, and Explode and Clip suspended, without discarding their values. The same
view actions (`PreviewChrome`'s `actions`, in the same place on top of where the cube was)
then read Display settings, Reset view and Exit preview; under the model is the playbar for a file with routines or an orbit
play/pause, each ending in Playback settings (`PlaybackMenu`, the playbar's
`trailing`), all on one idle deadline
(`PREVIEW_CHROME_IDLE_MS`). The render profile (`kit/viewport/renderProfile.js`)
draws preview one scene-quality tier up (`previewSceneQuality`), keeps the full
pixel ratio while orbiting (`renderProfileKeepsPixelRatio`) and never changes a
Display setting; `sceneForRenderProfile` is what RendererShell and `StepSurface`
(whose LOD reads the raised quality) draw. Preview never uses the browser Fullscreen API.

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
canonical face/edge reference flow supplies highlighting and copying.

Kernel verification, its cache and endpoint, intermediate-solid playback, and
GIF/video export are isolated on `amy/step-reconstruction-playback`. They are
not shipped in the shared app. Recognition records the numbers a solid was
reconstructed from (`workbench/modelingSolidRecipes.js`); assembling a recognized tree
into a numerical recipe is test-only (`workbench/__tests__/reconstructionRecipe.js`), a
recognition regression check with no runtime interpreter or export path.

### Robot links

A URDF, SRDF or SDF opens in Select, with **Links** in the tool stack (the filter as its
top row, no title), the **Reference** under it with a selection, and an `.sdf`'s **SDF**
panel after them (`LinksSection`, `SdfSection`). **Position** is the Position tool's
panel. Links is always present: it is the description's kinematic tree, not an
inventory of mesh names. `robot/robotTree.js` builds it as plain data.
Links are the rows, carrying no icon; a child link sits under its parent link
and shows the joint between them as muted text (`shoulder_pan · revolute`); the
named objects inside a link's meshes (`robotComponents` in core's `lib/urdf/robotParts.js`) are leaves under that
link, after its child links. Built-in primitives and unnamed mesh objects
contribute no leaves. Every link appears once: a cycle, a second parent or a
missing parent cannot hang the builder or drop a link, and orphans become
roots. A root that is only a frame — no geometry, no mass, and one child
attached by a fixed joint (`base_footprint`) — gets no row of its own; its
child leads the tree instead, unless the description has no content anywhere,
in which case every link is kept. An SRDF shows its paired URDF's tree.

The section reuses the Features tree's pieces rather than cloning them: the 28px
row primitive, `Filter…` (`TreeFilterInput`, `primitives/tree-filter`), the
ranked flat search of `kit/inspector/modelTreeSearch.js` (`useTreeSearch`), and the
Reference panel under it (the stack's next panel, under the same 288px cap, the same
panel the Features tree has). The search index also reads a row's `searchAliases`, so a
link is found by its joint name and the hit shows that joint in place of its
owners. The root opens, along with a chain of single child links below it;
everything else starts collapsed. When the tree has exactly one root with
children, that root is pinned: no chevron and no indent, so its children start
at the tree's own left edge. Selecting a hit opens its owners at once and
scrolls to it when the search ends.

Selection is the scene graph's. A link is hovered and selected in the viewport
as the meshes of its group, and a viewport pick of a surface that is not a named
object walks up to its link; a named object still selects itself. Any number of
links, or of named objects, can be selected, never both (Shift in the viewport,
Shift/Ctrl/Cmd on a row add); the Reference then names them by what they are
(`Links`, `Mesh objects`) and lists them. A link with no geometry selects its row
and details only. As for STEP, a robot selection exists only while Select is the
tool: a pick under another tool returns to Select, leaving Select clears it, and
Escape clears it. A click acts at once, as a STEP's does; a
robot has no double-click at all.

The Reference panel, headed by the link's name, reads back what the description says
about the link, in sections: its SRDF planning groups (`srdfGroupNamesByLink`) and end effectors;
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
There is no copy action and no Quick Edit: robot formats have no reference grammar to deliver.


### Tool panels and dark surfaces

A renderer's controls are `ToolPanel`s in the tool stack under the strip
(`kit/tools/ToolStack.jsx`): every panel one width (164px, a six-tool strip's, whatever
the file's strip has), each exactly its content's height — up to its cap, for the tree,
Position and the Reference — until the column (the area under the strip) runs out; then
a `"tree"` panel scrolls inside itself first, a `"details"` one next, and a `"fixed"` one
never; and if those still do not fit, the column scrolls. The tree and Position are
`resizable`, each on its own: handles on its right edge, bottom edge and corner make it
wider (never narrower than the one width, never past half the viewer) and set its cap,
moving no other panel; every other panel is fixed, with no handle. Every panel folds to
its first row (Drawing excepted). The resizable panels' sizes and the folded panels are
one of the tab's settings (`CadPreferences.toolStack`).
The strip and every menu over the viewport share one translucent, blurred surface, and
the stack's panels a more transparent one with the same blur and border
(`kit/tools/floatingSurface.js`); every scroll region is the `ScrollArea` primitive. A
submenu is portaled, never drawn inside its parent menu, which that surface makes a
containing block.

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

The Display panel's mode control selects Solid, Render, X-ray, Hidden line or
Wireframe presets over the same grouped settings. Render defaults to perspective; the
others to orthographic. Changing values shows Custom. Reset restores the base
preset and disables Clip/Explode, preserving camera viewpoint/zoom, selection
and the pose.
The groups and gate behavior are specified in [View presets](render-mode.md).
Photographic lighting and stage code stay lazy; the lightweight grouped settings
panel is always available. Authored materials remain read-only in the Model
reference section, with no material override or undo state.

The host-supplied render session owns its tessellation cache and worker leases.
The file view's display slice is the sole view-settings authority; the camera is the
mounted viewport's, saved with the view and restored in place of the fit. Surface derivation and preview requests
use the file's injected service and abort when the consumer leaves. The Features
tree resolves exact surfaces on demand through the same client.

Opening shows in the viewport's loading overlay. An update — a newer revision
loading behind the model on screen, or a Display change being prepared, and that
change's failure with a Retry — shows centred at the top of the viewport, level
with the tool strip (`ViewUpdateStatus`; on mobile, a spinner whose label opens on
press). An error is a card over the viewport (`ViewerAlertCard`), always;
one the model survives (`blocking: false`, the previous version still on screen)
has a Dismiss button, and stays dismissed until the alert changes, or clears and is
raised again. A warning is a card too, dismissible while the model is on screen:
there is no other place a problem is listed. Full diagnostics stay expandable under
Details; Try again uses FileViewer's renderer reload,
which rechecks the artifact and does not restart the desktop window.

### Camera framing and zoom

Zoom to fit and the live `resetCamera` frame the original authored model bounds at
the current angle, and that framing is 100%. Explode, clipping, animation, kinematics, visibility, floor and
other scene effects never redefine 100%. Perspective and orthographic derive
their own baseline from that same box and the current viewport dimensions.
Selection fit may move the camera but cannot make that new framing become 100%.
`kit/camera/viewportCameraFit.js` owns the fit calculation; live posed bounds remain useful
for clipping, lighting and picking. Nothing displays that percentage; it is read
through the `window.__cadCamera()` test seam (`zoomPercent`). The acts that frame the
model are STEP's context menu (Zoom to fit, Zoom to selection) and the live
`resetCamera`; the view cube (bottom-left, absent in preview) turns
the camera and keeps its zoom and pan, and opening or reloading a file fits the model
afresh.
