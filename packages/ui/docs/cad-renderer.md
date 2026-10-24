# CAD renderer

The CAD viewer is the viewport, the floating tool strip and the tool in hand's
sub-toolbar under it, the file sidebar, reference interactions, measurement and annotation
tools, animation, loading artwork and alerts, in `@text-to-cad/ui`. The rules of its
chrome — which tools a file has, how they take and give back the pointer, the file sidebar,
Preview, the keyboard — are the
[design system](settings-ui.md); this document is the mechanism behind them.

There is one renderer per file family over a shared, format-blind [kit](#kit) and
[shell](#shell). A STEP opens in the [engine document renderer](#engine-document-renderer)
(`src/renderers/xbf`), as an `.xbf` does: the page reads what the cadgen engine serves of it.
Applications use the registrations and the shared
`FileViewer`; they do not import another application's source.

## Kit

`src/renderers/kit` is the format-blind half of the viewer: small modules a
renderer composes, none of which asks what it is showing. There is one renderer
per file family, each a vertical slice over the kit: `src/renderers/dxf`
([DXF renderer](#dxf-renderer)), `src/renderers/glb` ([GLB renderer](#glb-renderer)),
`src/renderers/mesh` (STL and 3MF, [Mesh renderer](#mesh-renderer)),
`src/renderers/robot` (URDF, SRDF and SDF, [Robot renderer](#robot-renderer)) and
`src/renderers/xbf` (an `.xbf`, a STEP and an STP, [Engine document renderer](#engine-document-renderer)). The kit imports itself, shared UI
(`primitives`, `lib`, `drawing`) and the format-blind half of `@text-to-cad/core`
(`lib/viewer/*`, `lib/perspective.js`, `common/viewSettings.js`,
`common/sceneSettings.js`, the Render studio); a renderer imports the kit, never
the reverse.

| folder | what it is |
| --- | --- |
| `viewport/` | `useViewerRuntime` (three.js renderer lifecycle, on-demand render loop and `requestRender`, resize and device-pixel-ratio caps, context loss, keyboard orbit, `setSuspended`, teardown), `gpuDevice` (the page's one WebGL context, shared by every viewport: see [the GPU device](#the-gpu-device)), `previewViewScene` (Preview's view of the file's Render settings: no clip or explode, one scene-quality tier up, `previewSceneQuality`), `framePresentation`, `viewportBuffer`, `renderDepthPolicy`, `sceneObjects` (`disposeSceneObject`), `thumbnail`, DOM helpers. The scene in the viewport is its owner's: teardown calls the injected `disposeScene(runtime)` and `disposeStudio(runtime)` and disposes its lights' shadow maps; a runtime with a renderer of its own (no device) then loses its WebGL context (`forceContextLoss`), since three's shared textures keep every renderer that drew them reachable and only a lost context gives its GPU memory back, and one on the device lets go of its view and never ends the device's context. A torn-down runtime draws no further frame. The orbit controls let go of the page in a layout cleanup, before React detaches the canvas: they listen on its root node, which is no longer the document once it is detached. |
| `camera/` | `runtimeCamera` (zoom percent against the authored framing, projection and lens sync, perspective snapshots, eased transitions, fit-to-bounds, recentre), `useViewportCamera` (that behaviour bound to a mounted viewport: the perspective kept by a mounted view, the reset that Zoom to fit and the live `resetCamera` share, view-cube presets, which turn the camera and keep its zoom and target), `viewportCameraKit` and `viewportCameraFit`, `orbitControls`, `zoomPivotReanchor` (a wheel step first moves the pivot's depth onto the surface under the cursor, and a perspective pan is scaled by that surface's depth, so Render pans and zooms what the cursor is on at Solid's rate), `zoomSpeeds`, `cameraLens`, `ViewPlaneControl` (view cube). |
| `look/` | `stageEffects` (lighting rig scaled to the model, floor, glow and shadow catcher, grid and origin axes), the Render studio boundary (`renderStudioChunk`, `studioEnvironmentCache` and its worker). `chromeBackdrop` and `useChromeBackdropColor` (the frame colour around a scene). The surface LOOK is data the viewport resolves and a scene applies to its own materials: `@text-to-cad/core/lib/viewer/surfaceLook.js` (`createSurfaceLook(THREE, root).apply(look)`) does it for any authored material tree. The viewport resolves it with core's `resolveSceneSurfaceLook` (`common/sceneSettings.js`), the resolver the snapshot CLI dresses the same scenes with. |
| `view-settings/` | The settings model and store (`viewSettingsStore`, `useViewSettings`, `viewerDisplaySettings`, `renderState`), applying a change to a viewport (`useAppliedViewSettings`, `viewUpdateCoordinator`, `viewUpdateGate`, `viewUpdatePlan`), the content of Display's dropdown (`DisplayModeOptions`: the modes and the Grid switch's icons; `DisplayPopover` draws it), and Preview's settings form (`PreviewRenderSettings`). |
| `tools/` | `FloatingToolBar` (the dumb strip: the tools it is handed, in groups parted by one thin rule, then, only where the host has no navbar, the view's controls, which end the last section the tools have with no rule of their own; after a rule only where the tools are a single group), `SubToolbar` (the tool in hand's one row under the strip, its groups parted by `SubToolbarSeparator`; `SLIDER_SUB_TOOLBAR_CLASS`, the one width of a slider tool's row), `toolModes` (the tool-mode state machine), `ToolModeMenu` (`ToolSettingsMenu`: a tool's settings dropdown, from a chevron right after its button on the strip, or a sliders button in a panel's heading), `ToolPopover` (an ordinary dropdown from its button, on a `side` and `align`ed start or end: the Animation section's Playback settings), `FileSidebar` (the file's sections, whatever the tool: a tile each at the top-left, a tile opening its section in a panel under them, one at a time, sized from its bottom-right grip; on a phone one tile, `phone`, opening one panel with the sections as tabs and its one X; Preview offers its Position and Animation alone, `sections`, its tiles `bare`), `ToolStack` (the bounded column under the strip and sub-toolbar for a renderer's own `toolPanels`, which scrolls only when what cannot give way still does not fit), `ToolPanel` (one panel of the stack, or one section of the sidebar: `fit` says how it gives way when the viewer is short, `resizable` makes a stack panel the person's to size by the grip in its bottom-right corner alone, moving only it, and a panel with a heading can fold to it; its `footer`, a `ToolPanelFooterButton`, is a full-row action under the body that never scrolls), `ResizeGrip` (the one resize grip of a box over the viewport, in a bottom corner: the sidebar's and a resizable panel's at the bottom-right, Quick Edit's at its bottom-left), `toolStackLayout` (every panel's width, each sidebar section's and the resizable panels' sizes, and the folded stack panels: defaults, bounds and their stored record), and the format-blind tools: `annotate/` (`AnnotationOverlay`, the surface the drawing tools' gestures land on; `annotation3d`, its ink projected into the model; `AnnotationSelectionBar`, the bar of the annotations Select picked), `PreviewChrome` (Preview's chrome: the tools view's controls hidden and inert while it is up, and its own corner, `end`, with its settings panel under it, `panel`), `PlaybackMenu` (the Playback settings — Speed, Loop, Autoplay — and `ORBIT_SPEEDS`, Preview's Orbit speeds), `playbar/` (`AnimationSection`, the file sidebar's Animation section: Reset in its heading, the routine where there are several, Play/Pause, the scrubber, Playback settings; `AnimationTimeControl`, the scrubber, and `animationControlsHaveContent`; `animationClock`, `usePlaybackFrames`, `playbackPreferences`: the file's playback settings — Orbit's speed, Autoplay, and the chosen Speed and Loop), `pose/` (the handle overlay, canvas, drag mathematics), `select/` (`SelectFilterMenu`, Select's selection filter on its chevron; `selectFilter`, its pure toggles; `usePointerPick`: taps and hover through a scene's own `pick`, each with where the pointer was; `useSceneSelection` and `sceneReferences`: the parts a scene's pick names, selected, lit and handed to Quick Edit as references), `measure/` (Measure, for any 3D view: `useMeasureSession`, the session; `useMeasureOverlay`, its drawing; `MeasurementCard`; `measurementChips`, its chips and its row under the strip (`MeasurementsBar`); `measureSelection`, Select's press and hover on a measurement; `SceneMeasure`, two points on a scene's surface, and the model's size row), `model-effects/` (Explode and Clip, for any scene that opts in: `ModelTools`, their strip tools and slider rows; `useSceneEffects`, the viewport applying them to the scene; `motionExclusion`, one motion at a time), `sceneTools` (the tools a scene's renderer composes around the shell: the tool in hand, Pencil and Shapes, Measure and the model effects), `quick-edit/` (`QuickEdit`, the note to the agent, and `quickEditPrompt`, the context it builds and the text it copies). Screenshot capture is `@text-to-cad/core/lib/viewer/screenshotCapture.js`. |
| `inspector/` | `FileSheet` and its row and section primitives, `modelTreeSearch` (`useTreeSearch`, the ranked flat search every tree shares), `VirtualRows` (a long tree's rows, windowed), `referenceRows` (`InfoRow`, `MonoValue`, `CoordValue`), `kinematicsControls` (the `Pose` row that heads every Position section: Default, the named poses, Custom). The tree row and filter box are `primitives/tree-row` and `primitives/tree-filter`. |
| `status/` | `LoadingIndicator` and `ViewerLoadingOverlay`, `ViewerAlertCard` (the card over the viewport for every alert, and `useAlertDismissal`: a card put away, and its icon in the navbar that brings it back) and `reportIssue` (`alertIssueUrl`: its Report Issue's new issue), `ViewUpdateStatus`, `loadingState` (`viewerLoadingState`), `loadAlerts` (`failureAlert`, `noGeometryAlert`). |
| `shell/` | The host glue every renderer needs that is not about its scene: see [Shell](#shell). |

**What a view opts into.** Display's settings and `resolveViewSettings` take explicit
lists, `features: { modes, settings }` (`ViewFeatures` in
`@text-to-cad/core/common/viewSettings.js`): the modes it lists and the settings
its menus offer (`VIEW_SETTING_IDS`). A setting left out does not affect the
scene, and saved settings are never rewritten. `viewFeaturesForKind(kind, { parts })`
is the one rule of which list a file gets: `ALL_VIEW_FEATURES` for an engine document (an `.xbf`, a
STEP) of several parts, and without Parts or Explode for one of one part;
`PARTED_MESH_VIEW_FEATURES` (Solid, Clip and Explode) for a GLB of several rigid nodes
that draw; `MESH_VIEW_FEATURES` (Solid and Clip) for any other 3D file; and
`EDGELESS_VIEW_FEATURES` (no Edges, Clip or Explode) for a drawing. Render is no mode. Every
renderer hands its list to the shell, which configures the view-settings store
(`configure({ features })`) and Display's settings from it, and to its Explode and Clip
tools. The headless renderer (`renderMeshScene.js`) resolves a job of each family under the
same rule.

**Tools.** The strip draws the list it is handed: `{ id, label, icon, active,
disabled, onSelect, description?, menu? }` — a press is a tool's only action; a tool with
settings has them as `menu`, a chevron right after its button (Select's filter, the only
one), and what it can be set to while it is up is its sub-toolbar. Display is not a tool:
its settings are a dropdown from its button at the navbar's right end, before Preview
(`kit/shell/DisplayPopover.jsx`), a 3D view's alone. A renderer
builds its own list from `shell.tools.own(...)`, adding `shell.tools.drawing` (Pencil and Shapes) where it offers
them, declared in its `toolModes` as two modes (`pencil`, `shapes`) (a press on the tool in hand does nothing); the engine document's is in `xbf/XbfRenderer.jsx`.
Routines play from the file sidebar's Animation section, which the shell adds for any file with
routines (`kit/tools/playbar/AnimationSection.jsx`), in the tools view and Preview alike. Preview is not a tool: its button, after Display at the navbar's right end, enters it. Nor is Quick Edit: it is a box at the top-right, there while something is picked or annotated. `createToolModes({ defaultMode, modes })`
answers what a press does (`next`), what a saved tab may record (`persisted`) and
which tool a file opens in (`restore`); the engine document's declaration is
`XBF_TOOL_MODES` in `xbf/tools.js`. The scrubber follows the clock on
the runtime it is handed (`runtime.clock`, an `AnimationClock`); Position's knobs
overlay (`tools/pose/`), Select's while its filter ticks Position, takes a plain handle list, as a prop or (for an
owner that poses its model outside React) as a ref whose list it replaces per pose.

**The scene contract** (core's `lib/viewer/sceneContract.js`, a JSDoc typedef that `kit/scene.js`
re-exports, because the snapshot CLI holds the same scenes): `{ object3D, bounds,
restBounds?, dispose(), setSurfaceLook?(look), setShadowReception?(receives),
keepsAuthoredFinish?, complete?, pick?(ray), placedObjects?() }`, and for a family's scene
the tools' half: `units` (the file's unit against the scene's coordinates, core's
`sceneUnits.js`), `setClipPlanes(planes)`, `explodeParts` and `setExplode(amount)` (a GLB),
and, for a scene whose parts are picked by an id of the file's own, `hasPart(id)`,
`describePart(id)` and `setHighlight({ hovered, selected })`.
The viewport adopts `object3D`, frames `restBounds`, lights and floors `bounds`,
and hands over the surface look the Display settings resolved
(`{ materialSettings, authored, surface: { style, opacity } }`); it only ever
detaches a scene, whose owner disposes it. The GLB and mesh renderers' scenes implement
all of it but `pick`, and the robot and engine document renderers' all of it. A family's `pick(ray)` answers the first surface Clip has
not cut away, with the triangle it hit (`triangle`, for Measure). `pick(ray)` is what `usePointerPick` calls: the
hook owns the pointer (which press is a tap, one hover pick per frame, the
cursor), the scene says what is under the ray, and its renderer says what a hit
means. A tap acts at once: nothing waits to tell it from a double-click.
`placedObjects()` is for the near/far fit alone: a camera inside a mostly empty
aggregate box can still be well outside everything visible in it, so a scene that
placed many things says so and is fitted on them instead of on its whole box.
Shadow reception is the viewport's for every mesh of a scene, unless the scene
implements `setShadowReception`: a scene with unlit or see-through surfaces is told
the setting and applies its own rule.
A mesh names where "Color by part" deals it a palette colour in
`userData.cadFillIndex` (otherwise meshes take the palette in traversal order),
and a material with no source colour says so with `userData.cadSourceColor = false`.

**The rule and its check.** Kit code names no file format, no file-kind switch
and no STEP-assembly concept (topology, selectors, display records, explode,
section clipping), in code or in comments; only `view-settings/` may name the
Clip and Explode sections a view opts into, and `tools/model-effects/` the two effects
it applies to whatever scene opts in. `npm run check:boundaries` runs
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
| an engine document (`.xbf`, STEP) | `lib/xbf/xbfScene.js` `createXbfScene`, over `loadXbfDocument` | `xbf/useXbfScene.js` | `XBF_FAMILY` |

Both hosts dress a scene the same way: the look from `resolveSceneSurfaceLook`, shadows
while the lighting is on, `keepsAuthoredFinish` for Inspect's reflection environment, and
the ground sized from `restBounds`. Both cut and explode it the same way: Clip through
core's `lib/viewer/sceneClip.js` (the plane in the box the camera frames, `at` in the
file's unit, the cut capped as a STEP's is), Explode through the scene's `setExplode`
(`lib/viewer/sceneExplode.js`, a STEP's layout over the file's tree). A robot's parts a
Quick Edit's view hid come back in its job's `selection.hide`. A robot opens at `robotOpeningPose`
(`lib/urdf/motion.js`: every joint's default, then an SRDF's `home` state) and a
snapshot's `--joint-values` go on top through the same joint matrices. What a snapshot
cannot express, it refuses rather than approximates: a GLB's clips play in the viewer's
Animation section and have no snapshot flag. The pieces are pinned by `common/headlessScene.test.js`
(core), `kit/view-settings/renderState.test.js` (one look from either route) and
`tests/python/packages/cadgen/test_snapshot_family_scenes.py` (real snapshots, read as
pixels).

### Shell

`kit/shell` is what a file-family renderer needs from its host that is not about
its scene. A renderer loads its document, builds its scene (`kit/scene.js`) and
calls one hook; the shell owns the rest.

| module | what it is |
| --- | --- |
| `useRendererShell.js` | The hook. Per-file state through the host, the Display settings store and the content of Display's dropdown (`shell.display`), tool modes (Pencil and Shapes are the strip tools the shell itself owns, `shell.tools.drawing`; Display, Preview and its controls are the frame's; `toolModes` is omitted altogether by a renderer with no tools of its own), the file sidebar's and tool stack's layout (a viewer preference: `services.preferences.toolStack` — each sidebar section's size, the resizable panels' sizes, the folded stack panels — changed by one patch per gesture, `frame.changeToolStack`), prompt snapshots (the host's `captureRequest`), the clipboard screenshot (the drawing tools' Copy), what Quick Edit takes from the view (its file, how a copied prompt spells a path, the view as a picture, the viewer's Escape), the one Preview state (`shell.previewing` / `setPreviewing`, from `usePreviewState`; every way in and out goes through `setPreviewing`, which mounts Preview's view or takes it away and touches nothing of the editor's), Preview's scene (`frame.previewDesiredScene`: `previewViewScene(store.renderScene())`, Render over the file's settings as Preview draws them) and its viewport (`frame.previewViewRef`), Preview's Orbit (`shell.orbiting`, transient, off at every entry and exit), Render's studio code and environment prepared 600 ms after the model is on screen at Preview's quality, into the GPU device's cache Preview draws from (`previewPrepare`; it changes nothing the editor draws; not on a software renderer, the viewport's `softwareRendering`, where Preview prepares as it is entered), and Autoplay (`shell.autoplay`), alerts, shortcuts, and the live command surface (`setCamera`, `capture` and `resetCamera` act on the view on screen: Preview's while it is open). It owns no zoom control: the shell has none. |
| `RendererShell.jsx` | The frame: viewport box; one centred column at the top centre (`TOOLBAR_POSITION`, `data-cad-tool-groups`) holding the tool strip (the renderer's tools; the view's controls — Display, the active mode's sphere, whose dropdown is `DisplayPopover`, the modes and the Grid switch, then Preview, a play triangle, for a `previewable` view — are the navbar's, portalled into `view.navbarSlot`, and end the strip only where there is no navbar), under it the tool in hand's sub-toolbar (the drawing tools' `AnnotationToolbar` while Pencil or Shapes is up, else the renderer's `subToolbar`: Explode's, Clip's), the update status, and the tool stack (`ToolStack`: the renderer's `toolPanels`; the column stops above the cube's line, `VIEWPORT_STACK_BOTTOM`); the file sidebar at the top-left (`FileSidebar` over the renderer's `sidebar`, `SIDEBAR_POSITION`: its tiles 8px in from the top and left, the open section's panel under them down to 8px off the bottom; on a phone one tile at the left of the strip's line, the strip padded clear of it, `TOOLBAR_POSITION_PHONE_SIDEBAR`, and one tabbed panel down to Quick Edit's peek, `SIDEBAR_POSITION_PHONE`); Quick Edit at the top-right; the view cube in the bottom-right corner; Preview's controls (Preview settings and Exit preview in the navbar slot, or, with no navbar, at the view's top-right, `PreviewChrome`'s `end`; the settings, a toggle whose panel docks at the view's top-right, `panel` (`PreviewSettings.jsx`: Orbit and its speed, then Preview's own settings, `frame.previewSettings`), then Exit preview, an X — and the file sidebar's Position and Animation alone, bare, at the top-left, `PREVIEW_SECTIONS`; nothing under the model); Preview's view (`PreviewView.jsx`, `data-preview-view`), mounted over the editor's viewport box while `shell.previewing` and unmounted as it closes, the editor's viewport `suspended` under it; the cover that answers the press ("Preparing preview…", `data-preview-cover`) until Preview's view has presented its first frame (`onPresented`), the published mesh is complete (`previewView.complete`) and its picture has converged (`pictureProgress`) — lifting at once on a view the shell set moving (Orbit, a routine playing), never on a picture that a component publication started again (`previewCover.js`); at five seconds it stops waiting for more components and lifts on the picture converged, a second later at the latest, with no cover on the way out; the Animation section after the renderer's sidebar sections, for a file with routines, and the file's chosen Speed and Loop applied to its routine; the loading overlay; and the alert card. While the model loads, and once a load has failed in a way the model did not survive (an alert that cannot be put away), it draws none of its controls: only the load, or the card saying why, with the update status at the top centre in the strip's row; in a compact host (`appearance.compact`), none at all: the model alone. Nothing sits at the bottom centre. It takes `studio`, the renderer's own Preview while it is open: `{ scene, overlay(viewport, drawn), animation, runtimeLifecycle, onCameraSettled }` — the scene Preview draws, built by the family's own builder over the editor's geometry, what drives it from inside Preview's viewport (handed the Render scene it draws), Preview's routine (the Animation section's in Preview; Autoplay starts it on entry), and Preview viewport's lifecycle and settle. It takes `references` (what is selected, in the prompt grammar: what Quick Edit attaches and counts), `referenceChips` (how Quick Edit shows them) and `copySelection` (what ⌘C / Ctrl+C copies while the renderer's own tool is up and something is selected; null when nothing is), and, under Select, `onSelectPress`, `onSelectHover` and `selectsAnnotations` (whether Select's filter picks the annotations), and `inkTouches` (what the model is under a point of the view, `(clientX, clientY) => [{ part, ref? }]`: what the drawing tools record a mark as touching). One DOM structure (`data-slot="cad-file-view"`, `data-cad-surface`, `data-cad-scene-backdrop`, `data-cad-toolbar`, `data-view-controls`, `data-cad-sub-toolbar`, `data-cad-file-sidebar`, `data-cad-tool-stack`, `data-tool-panel`) for every renderer. `frameProvider` wraps the WHOLE frame in the renderer's own context — the sidebar and the tool stack as well as the viewport, because they read it — and `onCanvasPointerDown` is a press that landed on the model, for a renderer with something to put down when the person reaches for it. The frame focuses itself on such a press either way. |
| `ShellViewport.jsx` | The three.js viewport around ONE kit scene: `useViewerRuntime`, `useViewportCamera`, the look (rig or studio, environment, background, floor, grid, axes), the drawing tools' surface and the annotations' ink in the model, the view cube (bottom-right, `VIEWPORT_CUBE_BOTTOM`; not mounted in Preview's viewport, while the model loads, or when the shell says so, `viewCube`), frame presentation and the queued view-settings handshake. Its children may be a function of the viewport (`{ runtimeRef, hostRef, mountRef, viewerReadyTick, commitScene, syncSceneBounds }`), which is how a renderer mounts its own overlay or pointer pick. A scene that changes IN PLACE (it arrives in pieces, swaps its detail, is rebuilt under one identity) calls `commitScene()` from its own effect: the viewport re-reads what it placed, fits the stage and the depth range and applies the framing rules THEN, because a child's effects run before the viewport's own adoption effect. The one thing a commit never does ahead of the viewport is FRAME under a camera that is about to change: when the same render also changed the lens, the projection or the viewing mode, the stage is adopted at once and the framing follows once the camera has been given those props (a stored camera applied under the old projection and then converted comes out about a sixth smaller). A scene is framed once, on its `restBounds`. A scene that says `complete: false` (one still arriving) is framed on what has arrived and once more when it is whole, unless the camera on screen is by then the person's: one they dragged, wheeled, turned by keys or the cube, zoomed to a selection or set through `setCamera` during the current mount, or one a reload restored from the file's view. A rebuild of the open file never re-frames; only Zoom to fit does. A file opened again after the tab left it starts with fresh framing, since leaving it dropped its view. `studio` makes it Preview's viewport (opened at rest, framed afresh from the default direction, keeping no camera, no cube and no drawing tools; `orbit` turns the camera at `orbitSpeed`); `suspended` makes it draw nothing while another view covers it, and draws a frame asked of it meanwhile synchronously, before paint, as it is uncovered (`runtime.setSuspended`). `preserveInteractionPixelRatio` keeps the idle pixel ratio while the camera moves (a scene drawn with hairlines, and Preview's orbit), and `runtimeLifecycle` (`onRelease(runtime, { handoff })` while the WebGL renderer is still alive, `onContextLost()`, `onInitializationError(error)`) is for a renderer that hangs its own objects or in-flight work on the runtime. `syncSceneBounds()` re-fits lighting, shadows and the floor's height to a scene that moved its own bounds, with no React render and no reframe; a sync that finds the bounds (and every setting the fit reads) as they were refits nothing and keeps the shadow maps (`look/stageFollow.js`). What is SIZED stays sized from the rest placement, in Inspect and in Render alike: the grid and stage (`sceneRadiusForBounds` on `restBounds`) and the Render studio's floor plane (`applyPhotographicStudio`'s `groundBounds`), so a pose or a playing routine never rescales or slides the ground under the model; `zoomToBounds(bounds)` frames part of the scene. Read-only test seams, the view on screen's (Preview's while it is open, the editor's again as it closes): `window.__cadCamera()` (the live camera, its depth range included) and `window.__cadStage()` (the ground's radius, the bounds the stage is fitted to, the floor's height, the studio floor's size and centre). |
| `PreviewView.jsx` | Preview's view: a `ShellViewport` of its own (`preview`, `orbit`, `orbitSpeed`), with its own view-update coordinator over `frame.previewDesiredScene`, drawing the renderer's `studio.scene` and mounting `studio.overlay(viewport, drawn)` inside it. Its canvas, scene, camera and look are its own; only the GPU device is shared with the editor's, which it never reaches. `onPresented` says when its first frame is on screen. |
| `usePreviewScene.js` | Preview's scene for a family whose core scene has `createSibling()` (GLB, mesh, robot): the editor's scene's sibling, made as Preview opens and disposed as it closes, before the scene it shares geometry with. |
| `fileView.js` | The file's view `{ version, camera, display, playback, renderer }`, read forgivingly and written exactly: the camera (restored in place of the open-time fit; null fits), the Display settings, the playback settings (`tools/playbar/playbackPreferences.js`), and the renderer's own slices, each `{ signature, value }` and restored only under the signature the renderer declares now (`readFileView(raw, signatures)`); the camera, the display and the playback are always kept. The host keys it `[file path, renderer id]` in the tab store, which keeps it for the file on screen alone. Not in it: the tool in hand, a selection, measurements, ink, Preview, a routine's time — every open starts those afresh. |
| `liveBinding.ts` | `attachLiveBinding`: the live command surface. Base commands (`readState`, `setCamera`, `resetCamera`, `setDisplaySettings`, `capture`, `thumbnail`) mean the same for every renderer; a renderer ADDS commands by name and DECLINES the known host commands (`HOST_LIVE_COMMANDS`) that make no sense for it with the sentence the caller reads. Binding fails when a renderer does neither. |
| `promptContext.js` | `createViewPromptContext` (a snapshot and what it depicts) and `promptDeliveryError`. A renderer with a reference vocabulary of its own passes `promptContext` instead, and may then return that vocabulary from `promptReferences`. |
| `loadReport.js` | `shellLoadReport`: what the shell asks the status kit about one document load, as one pure function, and all it returns is the loading presentation over the viewport. A renderer whose document is a plain download passes `load` and nothing more. One whose document can be EDITED or PREVIEWED while it is open knows more than the shell can: `load.editPending` (queued work of the person's own, with nothing of it on screen), `load.currentPreview` (that work IS what is drawn, so the wait is over even though the write is not) and `load.finding` (the file is not even located yet). An alert is `load.alert`, which the frame draws as the alert card (`ViewerAlertCard`: every alert; one the model survives, a warning beside it included, can be dismissed). |
| `useViewerShortcuts.js` | Which mounted viewer an Escape or a ⌘C / Ctrl+C belongs to (focus inside it, or the page after a press inside it); the renderer says what Escape means, and a copy is the active tool's (the drawing tools' view with its annotations, else the selection's references, `copySelection`). The order is [the design system's](settings-ui.md#keyboard). |
| `viewportLayout.js` | The chrome's geometry: its inset from the viewer's edges (`VIEWPORT_INSET_PX`, 8px), the strip's row (`VIEWPORT_TOP_BAR_PX`, 34px), the cube's size and place (bottom-right, 2px from the right, `VIEWPORT_CORNER_INSET_PX`, and `VIEWPORT_CUBE_BOTTOM`, 8px off the bottom so its axes stay inside the view, plus `--cad-viewport-corner-bottom`, which a host whose control floats over that corner sets to lift it clear), the tool column's bottom (`VIEWPORT_STACK_BOTTOM`: an inset above the cube's line). |
| `ViewportContextMenu.jsx` | The viewport's menu on a secondary TAP (a secondary drag pans; primary and secondary together is the pan chord). The gesture, the anchor, the clamping and the dismissal are the shell's; the ITEMS are the renderer's (`contextMenuItems(press)`), asked at the moment of the press, and `onContextMenuOpenChange(open)` says while the menu is up. A renderer that passes no items has no viewport menu at all — every renderer but the engine document's. |

```jsx
const shell = useRendererShell({
  view,                 // RendererViewProps, unchanged
  services,             // { preferences, onPreferenceChange, live?, captureRequest?, acknowledgeCommand? }
  resource, modelKey, revisionKey,
  features,             // ViewFeatures: the Display sections this family opts into
  toolModes,            // createToolModes({ defaultMode, modes }), or omitted: no tools of its own
  previewable,          // true for a 3D view: it offers Preview; omitted (a 2D view): no Preview, and a request keeps the normal view
  scene,                // KitScene | null
  load,                 // { busy, updating?, progress?, alert? }: the renderer's document load
  animation,            // routine runtime with its own `clock` (and `onRelease`), or null
  live,                 // { commands?, declined?, state? }
  // optional: promptReferences, promptContext, escape, sceneScaleMode, preview, tool,
  //   viewSettings, viewerRef, onRuntimeAlert, presentationReport,
  //   preserveInteractionPixelRatio, runtimeLifecycle,
  //   rendererState   { signatures, read }: the renderer's slices of the file's view, read when it is written,
  //                   each restored (by the renderer, `readFileView(view.state, signatures)`) under the same signature
});
// Renderer-facing, beside `tools`, `display`, `toolMode`, `selectTool`, `previewing`, `requestRender`:
shell.requestFrame();            // a frame that keeps the shadow maps: a highlight moves and reshapes no caster
shell.syncSceneBounds();         // the scene moved its bounds (a pose): the stage follows, no render
shell.scheduleStateSave();       // a slice changed: write the view soon, and on unmount
shell.playback; shell.setPlayback(patch); // the file's: Orbit's speed, Autoplay, the chosen Speed and Loop
shell.orbiting; shell.setOrbiting(on);   // Preview's Orbit, transient: off at every entry and exit
// The shell adds Display and Preview (a `previewable` view's, in the navbar), Preview's controls (Preview
// settings, Exit preview), the Animation section for a file with routines, and the sub-toolbar of its own tool (the drawing tools').
const tools = [shell.tools.own({ id, label, icon, menu }), ...shell.tools.drawing].filter(Boolean); // []: no tools, and no strip
// subToolbar: the renderer's tool in hand's row; sidebar: the file's sections, each a ToolPanel, whatever the tool
return <RendererShell shell={shell} tools={tools} subToolbar={toolRow} sidebar={<>{treeSection}{positionSection}</>}
  viewportOverlay={viewport => <PointerPick viewport={viewport} scene={scene} enabled={selecting} onPick={pick} onHover={hover} />} />;
```

A CAD renderer's controls are the shell's chrome: its `tools` on the strip, the tool in
hand's `subToolbar` (`kit/tools/SubToolbar.jsx`) under it, and its `sidebar`, the file's
sections down the left edge (`kit/tools/FileSidebar.jsx`), each a `ToolPanel` drawn as a
section, whatever the tool: an engine document's Model tree and Position, a robot's Links, an
SDF's metadata and Position. Sections are their content's height and the bar scrolls as one,
up to all the room down the left edge or the cap a person set from its bottom-right grip
(`kit/tools/ResizeGrip.jsx`, Quick Edit's), kept under `sidebar` in the tool stack's layout;
a section folds where there are several, kept by `id`. A tree has no X and is on screen under
every tool (out of sight only in Preview, kept mounted with its state); a pick scrolls its row
into view there. A renderer may also hand `toolPanels`, the tool stack under the strip and
sub-toolbar, each panel its content's height, with `fit` saying how it gives way on a short
viewer: `"tree"` first (to 128px or its content), then `"details"` together, each in
proportion to its height (to 96px or its content), never `"fixed"`; the column scrolls only
if the rest still does not fit. Every panel is `TOOL_PANEL_WIDTH` wide (164px, a six-tool
strip's); `resizable` makes a panel the person's to size on its own, from the grip in its
bottom-right corner alone, kept under its `id`. The engine document's and the robot renderer hand none.

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
scene hook, its tool list, its tools' rows and its sidebar sections, if it has any
(`glb/GlbRenderer.jsx`, `mesh/MeshRenderer.jsx`, `robot/RobotRenderer.jsx`). The DXF renderer uses the workspace module without the
shell: it has no scene, so it reaches the same catalog entry and commands directly.

The shell's behaviour has one real-browser test,
`kit/shell/RendererShell.browser.test.mjs` (deferred files, warm reopen, isolated
per-pane state, Preview's camera, gated Display sections, settings that never
replace the canvas), and the drawing tools have one scenario (`harness/annotateScenario.mjs`)
run under the shell (`kit/tools/annotate/Annotate.browser.test.mjs`), in the engine
document's renderer over core's bracket fixture (`harness/xbfScenario.mjs`).

The shell surfaces few renderers use (the viewport menu and its open report, a scene
that arrives in place, the pixel ratio kept for hairlines, the runtime lifecycle,
and what a renderer says about a load that is more than a download) are driven
through `renderers/shell-harness` in `RendererShell.browser.test.mjs`, and each
renderer's own browser test asserts that the Display sections it does not offer are
absent from it.

## DXF renderer

`createDxfRenderer` (`@text-to-cad/ui/renderers/dxf`, id `dxf`) shows a `.dxf`.

It is **not on the shell**, and that is the whole design: a DXF is a finished 2D
document, so the pane is a canvas and the drawing is painted on it. No three.js
viewport, no scene, no Display settings, no Preview. The questions the old
Material/Bends tabs answered were about a sheet-metal part the viewer was inventing
from the file; a drawing is not that. What it has is what a person needs to talk about
a drawing — the kit's chrome, composed around the canvas rather than around
`ShellViewport` (`DxfRenderer.jsx`): the strip at the top centre, the tool's row under
it, the file sidebar, Quick Edit at the top-right.

- **Tools** (`dxf/tools.js`): **Select** (in hand; the view's hand too: a drag pans, a
  tap picks), **Pencil**, **Shapes** and **Measure**, no view controls (Display, Projection and
  Preview are a 3D view's). Select picks, front to back, a measurement, then ink, then
  the drawing's ENTITY under the pointer (`drawing2d/entities.js`'s `entityAt`: within
  6 px, a fingertip's 16; the lines over a hatch before the hatch; nothing on a hidden
  layer); Shift adds. Its selection is the kit's (`useSceneSelection`,
  `useSceneReferences`) over a drawing "scene" (`createDrawingScene`), lit over the
  drawing (`drawEntityHighlights`). Its cursors are the 3D views': the arrow, pressed
  or dragging too, the pointing hand over what a press picks. The drawing tools are the kit's
  layer (`AnnotationOverlay` with a flat view's `surface`, `dxf/drawingAnnotation.js`):
  ink lies on the sheet in drawing coordinates (x, y, 0), on no part, painted with the
  drawing (`drawing2d/marks.js`); its row has no Placement. Measure is the kit's session,
  overlay and chips (`useMeasureSession`, `useMeasureOverlay`, `measurementChips`) over a
  plan-view camera (`drawing2d/planView.js`'s `planProjection`); a pick snaps
  (`snapAt`) to an end, a circle's or arc's centre (`center`, "Centre"), else a point on
  a line, and reads in the unit `$INSUNITS` declares — "units", never millimetres, when
  it declares none. With Measure in hand its row under the strip lists its measurements
  (`MeasurementsBar`), none while nothing is measured.
- **References**: an entity by its DXF handle, `drawing.dxf#h2F` (`drawingReferences.js`);
  everything a block reference draws is its INSERT, a dimension is one entity. Quick
  Edit's chip names it by type and layer ("Circle on CUT", "Block M5_NUT on HARDWARE"),
  its card the handle, type, layer, block, centre and radius.
- **Layers**, a file-sidebar section, only where the drawing has the structure to read
  (`layersSectionShown`): four or more layers drawn on, or any block reference. Each
  layer's pen, name, entity count and eye (hidden: not drawn, picked or snapped to), and
  under it the block references placed on it, a click picking one.
- **Quick Edit** carries the picks and the ink; its views are the window on screen as a
  plan-view camera (`planCamera`: looking straight down, `up` +Y, `orthographicHalfHeight` the
  window's half height), each with its label, which the ink's marks name. `cadgen snapshot --job
  PACKET` draws each view's window with the ink on the sheet, and a packet's `measurements`
  (`PromptFiles.create` takes them) as Measure draws its dimensions; `--annotation PACKET
  --camera authored` the view the ink was last drawn in. The viewer's own Quick Edit puts no
  measurement in its packet: they are the person's.

- **The picture comes from the BACKEND.** `client.drawing(file)` is
  `GET /__cad/drawing` (`apps/web/docs/backend.md`), asked again while the server
  renders a drawing it has not drawn before: ezdxf flattens the modelspace on the
  server — text placed, dimensions exploded, hatches filled, blocks placed — and the
  client receives five primitive shapes and `text` in DXF coordinates, y up. **This
  renderer never parses DXF.** The payload is cached server-side by the document's
  content hash, so reopening a file costs a round trip and nothing else.
- **Drawing is core's** (`@text-to-cad/core/lib/drawing2d`), so the headless snapshot
  bundle paints the same picture from the same payload: `fitTransform` / `zoomTransform`
  / `panTransform` (one uniform scale and a translation; the y flip lives in the
  transform, not in the geometry), `prepareDrawing(payload)` (paths built ONCE, per
  colour for strokes and per primitive for fills; text kept as strings) and
  `drawDrawing(ctx, drawable, …)` (text set with `fillText`, stretched to the width the
  server measured, so the page's face keeps the drawing's layout).
  That bundle IS `cadgen dxf snapshot`: cadgen resolves a `.dxf` to the same
  `cadgen.drawing_payload` this route answers with and the page fits and paints it
  (`common/headlessDrawingRender.js`), so a CLI render cannot show what this pane
  cannot. The CLI's option surface was cut to match — no display, no render mode,
  `--appearance light|dark` and a size; a job may add a plan-view `camera` and an
  `annotation` on the sheet, what a Quick Edit's views carry.
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
  person moves the view, drag to pan (a primary press, one finger, once it has travelled
  more than a tap's 4 px; a press that lets go before is the tool's tap), wheel or pinch to
  zoom about the pointer, double-click to fit again. The view lives in a REF and the
  canvas repaints through one `requestAnimationFrame` when something changed; a pan
  never re-renders the component tree. A resize paints at once, inside the pane's
  ResizeObserver (after layout, before paint): resizing the canvas wipes it, and a frame
  asked for there would leave the pane empty for one frame
  (`dxf/DxfResize.browser.test.mjs`). The backing store is DPR-aware
  (`kit/viewport/pixelRatio.js`). What the tools draw (highlights, ink) is painted in
  the same frame, after the drawing, so a capture holds it.
- **Navbar**: nothing of the drawing's — no zoom buttons, because zooming a drawing is
  the pointer's: wheel or pinch about it, drag to pan, double-click to fit. The host's
  `captureRequest` is the canvas as a PNG, background included, delivered through
  `host.promptContext`.
- **Empty and failed drawings.** `bounds: null` (nothing in the modelspace) is a quiet
  sentence over the empty pane, not an error. A non-200 becomes the ordinary actionable
  alert card (`ViewerAlertCard`) carrying the SERVER's sentence (`failureAlert`,
  `kind: "http"`); a payload from
  a cadgen that disagrees about `schemaVersion` gets its own alert whose recovery is to
  update cadgen and the app together.
- **Host commands**: `resetCamera` fits the drawing again, `capture` hands over the
  PNG, `clearSelection` lets go of the picks, and `readState` reports `camera: null`,
  an empty `display`, the selection as references and `selectedEntities` (handles).
  There is no zoom command and no zoom percentage: no host ever sent one. `select`,
  `setCamera` and `setDisplaySettings` are each declined with a sentence that says why;
  a `selectReference` host request is consumed without changing the view.
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
  pointer, pan, re-fit and the resize rule; `DxfRenderer.test.tsx` asserts that the
  pane has no tab, tool strip or Preview.

## GLB renderer

`createGlbRenderer` (`@text-to-cad/ui/renderers/glb`, id `glb`) shows a `.glb` as
its NATIVE glTF scene, always: one path whether or not a clip is playing.

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
- **Display**: `viewFeaturesForKind("glb", { parts })`: Solid and Clip, and Explode where the
  file has two or more rigid nodes that draw (`explodeParts`); Preview draws Render.
- **Tools** (`glb/tools.js`): **Select** (in hand as the file opens), **Pencil**, **Shapes**,
  **Measure**, **Explode** (several parts only) and **Clip**. Select picks a NODE: the glTF
  node a mesh belongs to, marked on load (`userData.gltfNode`, `glbMeshData.js`), named
  `n<index>` after the file's `nodes[index]`; a selection is any number of nodes, each a chip
  in Quick Edit (its name, told apart by its id where several share it) whose card says
  `nodes[i]`, its triangles and, for a GLB cadgen exported, the STEP occurrence it came from;
  the scene lights it with a STEP part's highlight ink (`sceneHighlight.js`). Measure takes
  points on its surface and reads glTF's metres, approximately (see
  [Measure on a mesh](#measure-on-a-mesh)). Explode moves the rigid nodes that draw along the
  file's tree (`sceneExplode.js`); Clip cuts every surface and caps the cut. There is no filter
  menu, no copy-references key and no viewport context menu.
- **One motion at a time** (`kit/tools/model-effects/motionExclusion.js`): Explode set, the
  routine playing (or owning the pose) and Clip set each put the other two back, decided by
  value. A routine lets go of Explode before it plays, so it starts from where the nodes were
  authored; a routine let go puts them back under Explode's (`syncExplode`).
- **Animation** (`glb/useGlbAnimation.js`): clips play from the file sidebar's Animation
  section, the shell's (`AnimationSection.jsx`) — Reset in its heading, the clip where there
  are several, Play/Pause, the scrubber and Playback settings — in the tools view and the
  Preview alike. The file OPENS AT REST — one `AnimationMixer` on the native scene, built by
  the first play, scrub or clip choice. Preview plays a routine of its own, a second
  `useGlbAnimation` on its own scene's document: at rest each time it opens, playing only
  under Autoplay, gone as it closes; the tools view's clip is never touched.
- **Panels**: none of its own. A GLB with clips has a file sidebar of the Animation section
  alone; one without has none. Preview is the shell's, as for every 3D file; it draws the
  scene's sibling (`createSibling()` in core's `glbScene.js`: a SkeletonUtils clone wearing
  copies of the file's authored materials, kept before any look, over the editor's geometry
  and textures, with a sibling `document` for its routine; `kit/shell/usePreviewScene.js`).
- **Quick Edit**: as a STEP's — the picked nodes as references (`model.glb#n12`), the
  annotation and the views (Clip and Explode in their `display`), Copy, Queue and Send; no
  measurement, as no renderer's Quick Edit carries one.
- **Host commands**: the base live commands, and `clearSelection`; `select` is declined with
  a sentence (a node is picked by a person), a `selectReference` host request is consumed and
  acknowledged without changing the view, and live state reports `selectedNodes`.
- **State**: the shell record under `[path, "glb"]`. Records written under
  `[path, "cad"]` are not migrated.

## Mesh renderer

`createMeshRenderer` (`@text-to-cad/ui/renderers/mesh`, id `mesh`) shows an `.stl`
or a `.3mf` as what it is: triangles, and in a 3MF a colour per object.

- **Scene** (core's `lib/render/meshScene.js`, `buildMeshScene`, which the snapshot CLI draws an STL or a 3MF with too): one `Mesh` per object of the file (an STL is
  one; a 3MF has one per object and material) and nothing else: no part table,
  display records, edges or selectors. A 3MF's object knows its place in the build (`o2.1`:
  the second build item, its first component; `threeMfMeshData.js` reads it from three's
  loader and from the package reader alike) and its unit the one the model declares
  (`<model unit>`, read from the head of the root model part alone). Geometries
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
- **Display**: `MESH_VIEW_FEATURES` (Solid and Clip; Preview drawing Render).
- **Tools** (`mesh/tools.js`): a 3MF has **Select** (its objects, by their place in the
  build: `model.3mf#o2.1`; an unnamed one is "Object o2.1"), **Pencil**, **Shapes**, **Measure** (in the
  unit the file declares, approximately) and **Clip**, Select in hand as it opens. An STL is
  one mesh in no unit: **Pencil**, **Shapes** and **Clip**, nothing in hand as it opens (a press on ink
  still picks it), and its Quick Edit names the whole file. Neither has parts to move apart,
  nor a viewport context menu.
- **Panels**: none, and no file sidebar sections of its own. Preview is the shell's, as for every 3D file;
  it draws the scene's sibling (`createSibling()`: its own meshes, materials and look over the
  editor's geometry; `kit/shell/usePreviewScene.js`).
- **Alerts**: a file that fails to parse raises the load alert ("Couldn’t load
  the model", with the loader's error in Details); one that parses to no
  triangles raises "No geometry to display".
- **Quick Edit**: as a STEP's — a 3MF's picked objects as references, the annotation and the
  views (Clip in their `display`); an STL's carries the file, its ink and its views.
- **Host commands**: the base live commands, and `clearSelection`; `select` is declined with
  a sentence, a `selectReference` host request is consumed and acknowledged without changing
  the view, and live state reports `selectedObjects`.
- **State**: the shell record under `[path, "mesh"]`. Records written under
  `[path, "cad"]` are not migrated.

## Robot renderer

`createRobotRenderer` (`@text-to-cad/ui/renderers/robot`, id `robot`) shows a
`.urdf`, `.srdf` or `.sdf` as its kinematic tree. One renderer, one payload: cadgen
resolves the description (`GET /__cad/robot`, `cadgen.robot_payload`) into the
articulation the page plays, played by core's `common/articulation.js`, the visuals it
draws (each mesh at its rest placement: a link's mesh file, or a box, cylinder, sphere or
capsule cadgen meshed, held by its digest) and the facts a person reads back. An SRDF is its paired URDF with the SRDF's
semantics on it (group states as named poses, end effectors, planning groups), an SDF a
robot with one more section (a model nested in its model is part of it, its links and
joints named by scope: `arm::elbow`). The page parses nothing: a description cadgen refuses (its
validators' findings, a mesh the page cannot draw, a `package://` or remote mesh, an SRDF
with no single URDF beside it) is refused at the door, in cadgen's words. Nothing below
the loader asks which format it was.

- **Scene** (core's `lib/urdf/robotScene.js`, no React, no DOM, which the snapshot CLI draws a robot with too): a scene GRAPH
  played from the payload. One node per joint of the articulation, nested under its
  parent joint's, whose matrix is the joint's own motion in rest space
  (`jointMotionMatrix`); a link's meshes sit under the joint that carries the link, at
  their rest placements, and a link no joint carries under the root. A pose
  (`setControlValues`) normalizes the control vector against the articulation as every
  player does and writes the motion matrices of the joint rows that changed (a joint and
  its mimic followers) and nothing else: no geometry, no material, no
  part list, no React state. Core transforms are row-major, so matrices are
  written with `Matrix4.set`. A joint node's world matrix IS the joint's delta
  (`jointDeltas`), which the unit test holds the graph to for random poses. `bounds`
  follows the pose (only the moved subtree is re-measured); `restBounds` is the robot as
  written (every row at zero), whatever pose the file opens in, and is what the camera
  frames and the ground is sized from. Picking raycasts the link meshes (each geometry's
  BVH is built in idle time once a ray reaches it, core's `raycastBvh.js`) and reads the
  mesh's link; a named object of a link's mesh is itself.
- **Parts** (core's `lib/urdf/robotParts.js`): built once per load. One part per visual of
  the payload, or per NAMED object of a visual's mesh (`head:v1/object/0`), with its link,
  rest placement, source mesh and palette place. A primitive cadgen meshed carries no name
  and is never an object. Geometries wrap the loader's arrays and are shared by visuals
  that name one mesh.
- **Loading** (`robot/useRobotDocument.js`, over core's `lib/urdf/loadRobot.js`, the loader
  the snapshot CLI uses): `loadRenderRobot` (the payload, cached by the description's
  revision), then every distinct mesh URL it names (`loadRenderMeshByUrl`, at most eight
  at a time; a primitive is served by cadgen by its digest, `/__cad/robot?file=&mesh=<hash>`).
  Progress reads "Loading URDF", "Loading meshes 3/13",
  "Building robot". The robot is published once, whole. A mesh that cannot be fetched
  fails the load. A warm file is on screen on the first render; a new revision loads
  behind the robot on screen and keeps the pose it was left in while its controls and
  named poses are unchanged (`poseLogic`), and opens at its opening pose when they
  changed. An SRDF cadgen could not pair (the ONE `.urdf` in the same folder whose
  `<robot name>` matches) raises an alert that says what was looked for, around cadgen's
  sentence; any other refusal is the load alert, with cadgen's sentence as its reason.
- **Look**: a robot authors no finish, so Solid wears the viewer's surface and
  Render the studio's. Colour, in order: the colour the description gives the
  visual; else the colours the mesh brought (per vertex, graded as a material
  colour is); else the named object's own; else the viewer's surface colour.
  A colour the description gives a visual (a URDF `<material>`, an SDF `<diffuse>`)
  WINS over the colours its mesh file carries: this is deliberate, and a snapshot wears
  it too, because it draws the robot with this same scene.
  Materials are double-sided, so a mirrored `<mesh scale>` cannot turn a link
  inside out. "Color by part" deals the palette in the order parts always took it.
- **Display**: `MESH_VIEW_FEATURES` (Solid and Clip; Preview drawing Render). A robot is
  posed, never exploded.
- **Tools** (`robot/tools.js`): **Select**, its menu the chevron after it
  (`kit/tools/select/SelectFilterMenu.jsx`): **All** (when a file opens), **Links** alone or
  **Position** alone (the joints' knobs; the menu is offered where a control can be driven, and
  until the robot has loaded); then **Pencil**, **Shapes**, **Measure** (the description's metres, REP
  103, each mesh as its `<mesh scale>` draws it; approximate) and **Clip**. Clip turned on puts
  the joints back at the opening pose, and a joint moved takes Clip off: the second is heard
  on the pose store itself, outside React, so a pose step still renders no component.
- **Pose** (`robot/poseStore.js`): joint values live in a store outside React
  (degrees; metres for a prismatic joint), with one write path. A write is clamped,
  ignored under `URDF_JOINT_VALUE_EPSILON`, releases the tracked named pose and is
  heard synchronously: the scene poses itself, the handle list is re-read from the
  motion groups' world matrices (`robot/jointHandles.js`), one frame is requested,
  and the stage follows once per frame (`shell.syncSceneBounds`). Only the control
  that shows the value that changed is subscribed to it, so a pose step renders one
  slider row and no other component. On `juno.urdf` (28 links) a knob step cost
  about 270 ms of script when a pose was React state and a re-placed part list; it
  costs about 3 ms with the Position section folded and about 6 ms with the joint sliders on
  screen (a development React build), which is what a frame costs. The opening pose is
  every joint's default, then the SRDF group state(s) named `home` (core's
  `robotOpeningPose`, which a snapshot opens the robot at too). Preview draws a robot of
  its own, the scene's sibling (`createSibling()`: its own links and pose, its own vertex
  colours, over the editor's geometry), posed by a pose store of its own from Preview's
  Position section, at the opening pose each time Preview opens; the tools view's robot
  and pose are never touched.
- **Select**: a selection is any number of links or any number of named mesh objects, never both (`robot/useLinkSelection.js`; Shift in the
  viewport, Shift, Ctrl or Cmd on a row add), each a chip in Quick Edit whose card says what
  the description says of it (`robot/robotReferences.jsx`, `LinkDetails.jsx`). It outlives
  Select, as a STEP's does: a pick in Links returns to Select first, and leaving Select keeps
  it. Picking in the viewport is Select's while its filter ticks Links. Escape clears the
  selection. Hover and selection are drawn by the scene (`setHighlight`), with
  the highlight ink a STEP part wears; hover is not React state. A robot has no
  viewport menu and so no framing items; opening the file again fits it afresh.
- **Sidebar**: the file sidebar's sections, a tile each, whatever the tool: **Links**
  ([Robot links](#robot-links): headed by its filter), **SDF** for an `.sdf`
  (`SdfSection.jsx`), then **Position** where a control can be driven. No tool panels.
  `PositionControls.jsx` is the Position section's body (`RobotRenderer.jsx`) — the `Pose`
  label and dropdown (`Default`, which puts the joints back, the SRDF group states, and
  `Custom` for a hand-moved pose), then a compact slider row per
  driven joint (never a fixed joint or a mimic follower),
  its thumb named after the control.
- **Host commands**: the base live commands; `clearSelection` clears the link
  selection; `select` is declined with a sentence (a robot description has no
  reference grammar), and a `selectReference` host request is consumed and
  acknowledged without changing the view. Live state adds `selectedLinks` and `selectedPartIds`.
- **State**: the file's view under `[path, "robot"]`; its one slice is
  `pose: { jointValues }` (the control values), written against the description's
  revision and restored only under it. The tracked named pose, the selection and the tree's disclosure
  are not stored.
- **Test seams** (read-only): `window.__cadJointHandles()` (knobs in CSS pixels,
  with values and drawn travel), `window.__robotLinks()` (every link group's frame)
  and `window.__robotPoseStats()` (matrices written per pose, renders of the surface).

## Engine document renderer

`createXbfRenderer` (`@text-to-cad/ui/renderers/xbf`, id `xbf`, `src/renderers/xbf`) shows a
cadgen engine document: an `.xbf`, and a `.step` or `.stp`, which the engine reads and serves as
one. The strip is Select with its menu's chevron, Pencil and Shapes, Measure with its own, Explode for two or more
parts, and Clip; the file sidebar an assembly's Model tree, then Position where the document
carries a mechanism; and selection, hover, the menus, isolation, Escape and Quick Edit's chips
follow the rules of [Selection and inspection tools](#selection-and-inspection-tools).
`XbfPanels.test.tsx` holds the panels to those controls.

Underneath, the page reads the document from the engine (`useXbfScene.js`), and
every face and edge is to hand from the start, so nothing waits on topology: under Faces and Edges
every part is pickable at once, and under All a part's faces and edges are once its row is open
(its menu's Expand), the part (or the collapsed assembly holding it) elsewhere. The tree is the
engine's (`xbfTree.js`): the document's wrapper is no row, and sibling parts of one prototype
sharing a name's stem fold, as a STEP's repeated components do. Group faces and Group edges grow a
pick by the engine's groups of the part (`GET …/part/<key>/groups`), and a chip's card reads the
engine's facts of the element, measured on the exact shape. Position's rows are the mechanism's
pairs (`xbfKinematics.js`), a geared pair written through its gear, and its knobs are Select's as
a STEP's are (`xbfJointHandles.js`). A pair the engine could not keep a value for is said in the
section, under the rows.

A document with motions has a **Motion** section after them: the shell's routine transport
(`kit/tools/playbar/AnimationSection.jsx`, named by its runtime's `noun`) over `useXbfMotion.js` —
the motions by name, each with its duration, then Play or Pause, the scrubber and Playback settings
(Speed, Loop, Autoplay), Reset in its heading — and Preview's playbar plays Preview's own. Each frame
is the motion's pair values at the clock's time, interpolated as AP242 says (`xbfMotion.js` in core:
linear; synchronous, each step eased in and out with every pair arriving together; a function
motion's stored samples, linear between them; the clip finite, repeated while Loop is on), the same
values the engine's GLB baker keys (`xbfMotion.test.js` holds them to its bake), posed through
Position's forward kinematics. While a motion owns the pose (from a play, a scrub or a choice of
motion until Reset) Position shows its frame read-only and Select draws no knobs. A motion is one
of the document's motions with Explode and the pose (below): taking it up puts both at rest,
and Explode used puts it at rest, nothing set aside.

What an `.xbf`'s selection copies -- a chip, Copy Reference, Copy Prompt -- is the
engine's canonical ref of each thing, the file's path first, the ref `cadgen inspect` answers and
`select` labels its shapes with (`cadgen.engine.refs`): a part or subassembly by its label where that
names it alone in the document, else by its occurrence path, each segment its label numbered among the
siblings sharing it (`/work/XBF/kit.xbf#kit/hand/finger.2`); an element by its name, else its kind and
number, under it (`…#palm/f:palm.body.3`, `…#kit/hand/finger.2/face 7`); a label a plain segment
would misread JSON-quoted (`…#"M3/M4 screw"`). `xbfTree.js` spells them (`refOf`, `elementRefOf`)
with core's `cadRefs.js`, whose parser and speller are held to the engine's by one fixture, and a
pasted line is parsed back in the same grammar, to the end of the line. A STEP the renderer draws keeps
its own grammar's references.

## Tools on a scene of triangles

A GLB, a 3MF, an STL and a robot have the kit's tools as their matrix allows them
(`kit/tools/sceneTools.jsx` composes them; each renderer adds its own Select):

| | Select | Pencil, Shapes | Measure | Clip | Explode |
| --- | --- | --- | --- | --- | --- |
| URDF, SRDF, SDF | links (and named mesh objects) | yes | metres, approximate | yes | no: a robot is posed |
| GLB | nodes, `n<index>` | yes | metres, approximate | yes | where it has several rigid nodes that draw |
| 3MF | objects, `o<item>[.<component>]` | yes | its declared unit, approximate | yes | no |
| STL | no: one mesh, the whole file | yes | no: the format names no unit | yes | no |

### Measure on a mesh

Measure takes two points on the surface, each exactly where the pointer is
(`@text-to-cad/core/lib/viewer/meshMeasure.js`, "Surface"): a mesh has no vertices, edges or
faces of its own, and a triangle's corner or side is the tessellation's, so a snap to it would
move a point by an amount no one chose. There is no filter on its chevron, and a press on nothing
lets go of the first point. The length is read in the FILE's unit (`scene.units`: a GLB's and a
robot's metres, a 3MF's declared unit) and is approximate — a width across two facets of a
tessellated curve is no diameter — so every reading says so: "≈ 0.0425 m" on the dimension, in
its chip in Measure's row ("Measurement 1: ≈ 0.0425 m (approximate)") and in its card (Accuracy:
Approximate). There is no face-to-face or centre-to-centre reading. Under Select a measurement is picked, lit and deleted as a STEP's is
(`measureSelection.js`). Picks ignore what Clip has cut away.

### Clip and Explode on any scene

`ShellViewport` applies both to a scene whose renderer passes `sceneEffects`
(`kit/tools/model-effects/useSceneEffects.js`), after its look: Explode through the scene's
`setExplode(amount)` (the stage follows the box the parts make), Clip through core's
`sceneClip.js`, which sets the plane on the scene's materials through its `setClipPlanes` (a
look's later stand-ins and a selection's ghost are cut too) and caps the cut with the stencil
fill a STEP's section wears — over meshes drawn where their geometry says, not a skinned or
morphed one. The planes in force are the runtime's `activeClipPlanes`, which the ink is cut by.
Clip's slider maps in the box the camera frames, in the file's unit, which is what `clip.at`
holds. Explode on a GLB moves the rigid nodes that draw,
in the file's tree order, each in its parent's frame from where it was authored (its layout,
a STEP's, is measured the first time Explode is used).

Explode, a routine, Position and Clip are one motion at a time
(`kit/tools/model-effects/motionExclusion.js`): the one SET off its default — by value, never
by a tool taken up — puts the others back. An engine document has Explode, Position and its motions;
a GLB Explode, its routine and Clip; a robot Position and Clip; an STL or a 3MF only Clip.

## Host integration

```tsx
import { createCadClient } from '@text-to-cad/core/client';
import { FileViewer } from '@text-to-cad/ui/file-viewer';
import { createXbfRenderer } from '@text-to-cad/ui/renderers/xbf';
import { createCadPreferences } from '@text-to-cad/ui/renderers/workspace';
import '@text-to-cad/ui/styles.css';

const client = createCadClient({
  origin: backendOrigin,
  shouldPoll: () => document.visibilityState !== 'hidden'
});
const preferences = createCadPreferences({
  initial: restoredPreferences,
  onChange: savePreferences
});
const renderers = [createXbfRenderer({ client, preferences })];

// Keep client, preferences and registrations stable for this host.
<FileViewer
  file={path}   // absolute; null is the host's home
  host={host}
  renderers={renderers}
  state={viewerState}
  onStateChange={setViewerState}
/>
```

`source.id` names the file source a document's key is made of, independently of the
backend's port. The client serves a
file by its absolute path and catalogs only the files on screen; `client.folder(path)`
and `client.search(path, query)` are the explorer's reads, and `isMissingFileError(error)`
says the file asked for is not there. The host owns source access, file selection,
URL/history, title, navigation, browser storage and application color scheme. It calls
`client.dispose()` when the connection is no longer owned.

A registration (`createXbfRenderer`, and every other) accepts an existing client or an
async function receiving `PrepareContext`. The latter lets desktop obtain the local backend only when
opening a CAD file. The host owns backend startup, authorization, and any
runtime recovery actions. Construction does not fetch files or load Three.js.
Preparation resolves metadata with the viewer's abort signal; the component
and viewport are imported lazily after renderer selection.

A CAD renderer's controls are its own, over the viewport: its tool strip, the tool in hand's
sub-toolbar and its file sidebar. Display is a dropdown from its button at the navbar's right
end, before Preview. Preview is the shell's own state in
every 3D renderer, with no host prop, and the navbar stays over it; see [Preview](settings-ui.md#camera-animation-and-preview)
and [the host's side](viewer-host.md#preview-and-renderer-navigation-actions).

All package exports are compiled ESM with declarations. Consumers need no
source aliases, JSX transforms for dependency `.js`, or cross-app stylesheet
paths. A bundler must support the emitted `new URL(..., import.meta.url)` worker
assets, which remain inside `@text-to-cad/core`.

## Preferences and the file's view

Everything the viewer keeps is the tab's: one record, `{ version, settings, files }`,
thrown out with the tab and kept across a reload (`@text-to-cad/ui/tab-store`; the host
side is in [viewer-host.md](viewer-host.md#files-state-and-shutdown)), and of the files
only the one on screen has a view. The host hands
the store one adapter — a synchronous read and write of the whole record — and the
package owns the record. Nothing under `renderers/` touches storage, on import,
construction or ever.

**Preferences** are the tab's `settings`, read by every renderer as `CadPreferenceSource`
(`getSnapshot`, `subscribe`, `update`; `createCadPreferences` is the in-memory source a
renderer built without one gets). They hold the tool stack's layout and — for the
host — the appearance and the home's layout. The playback settings (Orbit's speed, Autoplay, Speed and
Loop) are not preferences: they are each file's own (`playback`, below). App light/dark appearance selects Inspect's
fixed workbench basis, including the empty CAD stage; the settings contain no theme
choice or custom scene settings.

**A file's view** is `files[[path, renderer id]]`, kept for the file on screen alone
(`TAB_FILE_LIMIT` is one, and `CadViewer` drops the view of a file it leaves — for another
file or the home — once the departing renderer's last write has landed:
`files.retain`), `{ version, camera, display, playback, renderer }` (`kit/shell/fileView.js`).
A reload shows the same file, and restores it:

| Kept | What |
| --- | --- |
| `camera` | The renderer's own: a scene's pose, lens and projection (a perspective snapshot, scoped to the model on read), restored in place of the open-time fit — null, or not a camera, fits; a drawing's plane transform. |
| `display` | The Display settings, Clip and Explode included. |
| `playback` | The playback settings, every one of them (`kit/tools/playbar/playbackPreferences.js`): `{ orbitSpeed, autoplay, speed?, loop? }`, `DEFAULT_PLAYBACK` `{ orbitSpeed: 1, autoplay: false }`, and `speed` and `loop` once chosen in the Animation section's Playback settings — unset, the routine's authored values apply. Kept between leaving and re-entering Preview, and across a reload of the tab. Whether Preview orbits is not kept: it opens still. |
| `renderer` | The renderer's slices, each `{ signature, value }`, restored only while the signature the renderer declares for the file on screen still matches. Robot: `pose` (joint values) and `visibility` (hidden component ids) against the description's revision. Engine document, GLB, mesh: none. DXF: nothing beyond its camera. |

| Not kept | Every open starts it afresh |
| --- | --- |
| A file the tab left: its whole view | The defaults, when it is opened again |
| The tool in hand | The default tool |
| The selection, measurements, the annotations | Empty |
| Preview, its camera and its Orbit | Off; the tools view's camera is the one kept, Preview opens still, and its settings are the file's (`playback`) |
| The routine, its time and whether it plays | At rest |
| Quick Edit's note | Empty, its box following what is picked or annotated |
| Select's menu | All |
| Hover, menus, popovers | Closed |

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
`RendererShell` mounts for a renderer that hands it `references` — every 3D file's renderer
(a picture, `compact`, gets none; a drawing has no Quick Edit). Its box, header and buttons are the design system's
([Quick Edit](settings-ui.md#quick-edit)); what it can do follows the host
([prompt handoff](viewer-host.md#prompt-handoff)), never an app. The renderer hands
the shell what is selected as `references`, in the prompt grammar (an `.xbf`'s in the engine's,
`kit.xbf#kit/hand/finger.2`, a STEP's in its own; a robot's links, `robot.urdf#upper_arm`; a GLB's nodes,
`model.glb#n12`, the file's `nodes[12]`; a 3MF's objects, `model.3mf#o2.1`, its build's second
item's first component; none for an STL, whose note names the file; the file itself always
goes), and the
shell hands Quick Edit the file, its prompt (`quickEditPrompt`: the views it
carries — the view on screen, from `ShellViewport.promptCamera` and the renderer's
`viewState`, its pose and hidden and isolated parts — and the files `host.promptFiles`
makes of them, with the annotations as an annotation file), the viewer's Escape, and the box's size
as the person drags it, kept across files. `quickEditPrompt.js` builds the context at
the press, from what is live then (`createQuickEditContext`), and the text a copy writes
(`copiedQuickEdit`, over core's `formatPromptMessage`). The drawing tools hand it whether there is
ink, and the Annotation chip copies its `.annotation.json` file's path. Copying without
Quick Edit is the copy shortcut — the selection's references, or, while Pencil or Shapes is up, the
view with its annotations — which writes the clipboard directly. See
[ViewerHost](viewer-host.md) for lifetime, focus, supported content and clipboard
representation limits.

An optional `ViewerCommandSource` (`@text-to-cad/ui/renderers/workspace`) has the same
subscription shape and publishes
`selectReference: { selector, key? }` or `captureRequest: { key }`. A fresh key
requests another operation even when its selector or target file is unchanged.
Selecting a reference also expands the matching model tree row's ancestors (under All)
and scrolls it into view; the model tree is on screen whenever Select is.
Repeating the request reveals the existing selection again without toggling it off; a face-group
reference keeps the group highlighted and reveals its active face.
Both toolbar capture and host capture commands use the same implementation.
Hosts can provide `acknowledge(kind, key)` to consume an admitted command. Desktop
binds commands to the active project/tab/path and removes only the matching
nonce, so an old acknowledgement cannot clear a newer request or replay after a
remount. A capture waits for ready geometry; a selected reference waits until it
can resolve against the current model.

`@text-to-cad/ui/file-viewer/presentation` exports the lightweight
`ViewerLoadingOverlay` for host bootstrap and generic viewer loading presentations.
Its markup and wording are the original CAD artwork. It mounts inside a relative
container and requires no CAD client.

The optional `live: LiveViewBinding` registration binds a mounted
`LiveViewController` for app-owned view tools. It reports the actual resource
revision, selection, camera, display and mode, supports explicit controls and
captures a PNG without prompt delivery or clipboard effects. It never substitutes
catalog or persisted state for a live viewport. On unmount it retains only a
serializable inactive snapshot; controls require the tab to be shown. See the
[viewer host contract](viewer-host.md#app-specific-interfaces) for lifecycle and
stale-operation rules, and [`liveBinding.ts`](../src/renderers/kit/shell/liveBinding.ts)
for the signatures every renderer shares; each renderer adds or declines its own commands
(the engine document's in [`tools.js`](../src/renderers/xbf/tools.js)).

## Lifetimes

The injected `CadWorkspaceService` owns its catalog — the files on screen, each read as
it is asked for — and request controllers. The first
subscriber starts the catalog and its two-second poll; further subscribers
share them. The last unsubscribe stops polling. A host may gate the poll with
`shouldPoll`; the web viewer's pauses while its page is hidden (the CAD app
polls nothing: its views sync). `CadViewer` connects window focus and visible
`visibilitychange` events to `refresh({ markRefreshing: false })`, so a tab in
the background is current when it is shown, preserving browser refresh behavior
without a DOM dependency in core. Catalog requests retain the ten-second
timeout and the same error text.

Each prepared CAD document owns a render session, with its own abort signal and worker
leases. The client owns the origin-bound resource provider. Disposing a session aborts its
reads; disposing the client aborts its provider requests. There is no page-wide mutable
cache provider. An engine document's meshes are the engine's own: the browser reads them
and never writes one.

On mount, immutable mesh and complete robot state are read synchronously from
the existing bounded decoded caches. Reopening a warm file can therefore show
those assets on its first render while file-owned controls restore their own
camera and pose. An engine document's parts are held by the versions that hold them: a new
version fetches only the parts it has not held. A replacement service or changed backend
identity starts a new resource generation, preventing URL cache reuse across changed
credentials or origins. A native GLB scene and its animation mixer are never cached:
they are mutable state with one owner, the GLB renderer's mounted scene.

Worker infrastructure is reference-counted across live render sessions. The
last session releases workers and pending work. Playback clocks are separate
per mounted renderer. Asset loads and the routines' keyframe loads have
their own abort signals; changing or closing a file cannot install a late
result into the next file. A renderer release does not dispose a host's shared
client while another pane still needs it.

## Validation and baseline limitations

CAD helper suites retain format, state, geometry, reference, selection,
settings and loading behavior. Core tests cover independent client origins,
cancelled and late responses, polling ownership, cache/worker lifetime, and
session cancellation and client-owned writes. The browser integration harness exercises actual WebGL
rendering with two viewers, PNG captures, host title ownership
and state round trips through unmount/remount.

The camera is the file's view's: reloading the page restores the one the file on screen
was left at, and opening a file — for the first time, or again after leaving it — fits, since
leaving a file drops its view. Presets update projection/lens while retaining viewpoint and
zoom on the same renderer, canvas and controls. Ordinary settings edits never
restart the viewport. Initial/reset/fit views use the
projected bounds rather than a bounding sphere, padded 1.1 across and, down, 1.1 on
a square or narrower viewport easing to 1.25 at 16:9 and wider
(`interactiveFitPadding`): about 91% of the limiting dimension in a side pane or on
a phone, and 80% of a wide view's height. Manual views retain their own
zoom and pose. This policy belongs to the interactive UI; snapshot/export
framing remains independent. The orientation control labels its positive X/Y/Z
axes and retains its snap and drag interactions.

See [settings controls](settings-ui.md), [render capabilities](render-types.md)
and [renderer contracts](renderers.md) for changes inside the shared package.

The optional `@text-to-cad/ui/file-viewer/empty` entry exports `EmptyCadBackdrop`, a host's empty-state backdrop. It lazily mounts an empty CAD viewport with the host’s `colorScheme`, and overlays its `children`. It owns no file access, catalog subscription, or persisted state. This puts the original grid and camera behind a host's own page without loading CAD into the file viewer. Its stage (`file-viewer/EmptyCadStage.tsx`) is `ShellViewport` with a null scene, built out of the kit alone: the file viewer MOUNTS a renderer through the registry and imports none itself, because a static edge into a slice pulls that family — and three.js with it — into every host that shows any file at all. `scripts/test/check-kit-boundaries.mjs` enforces that alongside the kit and slice rules.

## STEP and source separation

STEP inspection reads the document's geometry, assembly structure, and topology.
It does not search for a matching Python file or reconstruct authored operations,
parameters, or annotations. Geometry references added to prompts identify the STEP and its
selected entities, without attaching a source filename or source line.

## Selection and inspection tools

An engine document's Select picks what its menu chooses — All, or Parts, Faces, Edges or
Position's knobs alone — and grows a face or edge pick by Group edges or Group faces
(`xbf/xbfSelectionFilter.js`, `kit/tools/select/selectFilter.js`); Measure's menu chooses the
same way among vertices, edges and faces, which a press takes whole. Explicit filters never fall
back to a different entity type. Every face and edge is to hand from the start, so nothing waits
on topology.
Shift-click adds/removes entities. A double-click on a face or edge (outside the
Parts filter) turns the view square to it and selects nothing (the selection is as
its first click found it); on a component or
subassembly it isolates it, and on empty space it leaves isolation.

**Look at** (`kit/camera/lookAt.js`, an engine document's side `xbf/xbfLookAt.js`, the
viewport's `lookAt` / `lookAtAnnotation`). A double-click under Select on a face, an edge
or ink turns the view square to it, its zero point the orbit centre (under Explode and Clip
too, and under Measure the face or edge a press there takes). It is navigation only: it
sets no plane for ink: a mark's level is the plane of the surface it starts on, whatever view
the turn brought ([annotation](annotation.md)):
- A planar face (and flat ink): along its normal, from the side the camera is on; its
  middle, framed.
- A cylinder's side: from the side, along the radius toward the camera; its zero point the
  circumference's point nearest the camera; framed.
- A circular or elliptic edge: down its axis; its centre, framed.
- A straight edge: of the views square to it, the one nearest the camera's now; its middle,
  framed.
- Anything else (a cone, a B-spline face or edge, ink over a curved face with no drawn view):
  the view as it is, its zero point its point nearest the camera, the zoom as it is.
- Ink: a straight line, the plane through it as square to the view as it can be, upright or flat
  where that is within 30° (`planeThroughLine`) — a line drawn on a plate's top, double-clicked
  from the side, is seen edge-on; flat ink, its plane; ink that lies on no plane, the view it was
  drawn in.

Kinds and axes come from the element itself (the scene's `elementGeometry`,
`@text-to-cad/core/lib/xbf/xbfEntities.js`): a face's surface read off its nodes and the normals
the engine meshed it with (a plane's normal, a cylinder's axis, origin and radius), an edge's
polyline read as Measure reads it (straight, or a flat circle about its centre); its points
where its instance stands now, the pose and Explode included. A click acts at once: nothing
waits to tell it from a double-click. The first click of a double-click therefore
selects, briefly, whatever it hit; the second is not a click of its own (the browser
counts it, `xbf/clickActivation.js` holds it for the `dblclick` that owns the gesture),
and the double-click begins by putting the selection back the way its first click
found it — through the same setters every pick goes through, so Quick Edit's chips,
the tree and the viewport follow — before it isolates, leaves isolation or looks at it.
The one click that still waits is one under a tool a pick would leave (Explode, Clip:
a pick there takes up Select): it is held for the double-click window, so a double-click
there isolates and stays in the tool, and a lone click selects and switches to Select once
the window has passed. A coarse pointer has no double-click: every tap picks at once.
Every copied reference — a chip's click, ⌘C, both menus — carries the
file's prefix: the file's absolute path, the real file name with its extension.
Escape clears the
selection after any open menu has been dismissed. Input fields
keep their own Escape behaviour.

Measure is an exclusive picking tool. Its chevron chooses, as Select's does, All or vertices,
edges or faces alone (`kit/tools/measure/MeasureFilterMenu.jsx`, `measureFilter.js`), and badges
Measure's button with the choice. A press takes an entity whole, as a STEP's Measure did
(`xbf/XbfMeasure.jsx`, `xbf/xbfMeasurePick.js`): an edge's end within 10px of the pointer is its
vertex, else the edge, else the face, of any part, open in the tree or not, kept to the choice;
Shift takes the point on the model as it is. What it is comes from the document
(`@text-to-cad/core/lib/xbf/xbfMeasure.js`): a face's surface read off its mesh, an edge's
polyline; an edge's length along a curve and a face's area, beside the pointer, are the engine's
facts of it (`GET …/part/<key>/edge|face/<n>`), asked for when the pointer first rests on it.
A pair reads what the two make (`@text-to-cad/core/lib/viewer/measureEntities.js`), drawn as
every measurement is. Completed rulers are chips in its sub-toolbar while it is the tool
(`kit/tools/measure/measurementChips.jsx`'s `MeasurementsBar`, Quick Edit's chips, their card
`MeasurementCard.jsx`), and no row while there are none. They are the person's alone: nothing of
them reaches Quick Edit or its snapshots (`cadgen snapshot --measurements` draws the rulers it is
given). Leaving Measure cancels its draft but keeps completed rulers, drawn on the model, under
every other tool.

Clip caps the cut with core's section fill (`sceneClip.js`, [Clip and Explode on any
scene](#clip-and-explode-on-any-scene)): a non-pickable display fill, not new topology or an
edit to the document. Open/non-manifold meshes cannot guarantee a solid section fill.

**Group faces and Group edges.** Clicking a face selects its tangent group and
clicking an edge its chain: both are the engine's, read off the part's shape
(`GET …/part/<key>/groups`, asked for when Group faces or Group edges first needs it: faces
joined across tangent edges, edges that continue one another at a shared vertex), and the page
grows the pick to the members of the same group in the same instance. Selection never crosses
instances. Shift-click adds a group, or removes it if the whole group is already
selected. The resulting faces use the existing highlight and Copy Reference
controls. This changes selection only, not CAD geometry.

### Engine document panels

An engine document's file sidebar sections (`xbf/XbfRenderer.jsx`), in
order, whatever the tool:

- **Model tree** (an assembly's): headed by its filter ("Filter model", "Filter…"), then
  **Show all** while parts are hidden, then the section's X; then,
  while something is isolated, the isolation bar; then the model tree (`XbfModelTree.jsx`). Its
  tile is there under every tool (Preview offers it none), the section kept mounted. A part
  file has no model tree: its tree would be its one row.
- **Position** (where the document carries a mechanism): Reset in its heading, the `Pose` row and
  the joint values (`XbfPositionSection.jsx`); reaching for one of
  its controls puts the other motions at rest.

A part file with no mechanism has no sidebar. What is selected is Quick Edit's chips
(`xbf/xbfChips.jsx`'s `useXbfSelectionChips`): a component
or subassembly a chip of its own, faces and edges a chip for each kind on each part,
each chip's card the key measurements.

**Select's menu.** The chevron after Select's button (`SelectModeMenu` in
`XbfSelectionModes.jsx`, over `kit/tools/select/SelectFilterMenu.jsx`) is one choice among an
engine document's modes (`xbfSelectModes`): All (`XBF_SELECT_DEFAULT`: Parts, Faces, Edges,
Position, and the annotations and measurements), then Parts (assemblies only), Faces, Edges and
Position (where the document has a mechanism) alone — All when a file opens, and for another
file — then, below a rule, the independent checkboxes Group edges and Group faces
(`CONNECTED_SELECTION`, each shown while its kind is picked; a hidden one keeps its choice). A
mode is the list of kinds it picks, which is the filter the renderer reads (`selectFilter.js`'s
`pickModeOf` names the mode of a filter). Choosing one takes Select up. Select's button is the
pointer (`SelectIcon`), Measure's the ruler (`MeasureIcon`), each badged with its mode
(`ToolModeIcon`; none for All). The renderer keeps the filter, the geometry mode it gives
(`xbfSelectionFilter.js`'s `selectGeometryMode`: "all", "parts", "faces", "edges", "topology"
or "none") and the options; while Select is up the press goes to a measurement first
(`onSelectPress`, under All), then the annotations (`selectsAnnotations`, under All), then a
part, and Position's knobs are drawn under All and Position. The geometry chosen shapes the tree
(`treeShape`: "all" for Parts with Faces or Edges or no geometry, else "parts", "faces" or
"edges"): Parts opens every assembly and shuts every part, and Faces and Edges open every
assembly, every part pickable at once. Outside the "all" shape the tree's disclosure is locked
(`data-disclosure-locked`) and the part menus drop Expand/Collapse.

Explode and Clip follow Measure on the strip; Explode only with two or more parts
(hidden, never disabled, once the document is known; idle until it is). Their sub-toolbars
(`kit/tools/model-effects/ModelTools.jsx`'s `useModelTools`, handed to the shell as
`subToolbar`) are the tool in hand's alone, with no enable checkbox: Explode's slider, its
amount and Reset explode; Clip's axis (`ClipAxisSelect`, "X ⌄", whose dropdown holds the
axes as one row of radio items, then Part colors and Reverse, drawn as Display's menu), its slider, its amount and Reset clip
(`ModelViewControls.js`). A press on one unset starts it neutral; one with
its effect set takes it up as it is; the one in hand does nothing. An edit applies the effect
and the slider at zero removes it; Reset puts the amount back at zero — Clip's axis and settings
stay — and leaves the tool up, disabled while nothing is set. The effect stays on the model under every other tool, with nothing of it on
screen. Clip's plane and slider range share the original bounds, unaffected by pose or
Explode. The lifecycle is [the design system's](settings-ui.md#tools-and-lifecycle).

Position is no tool: its controls are the file sidebar's Position section, and its joint
handles are Select's while Select's filter ticks Position. Robot viewers use the same shell,
the shared `Pose` row, whose Default puts the pose back (`kit/inspector/kinematicsControls.jsx`),
and the same filter kind. Display is not a tool: opening its popover leaves the tool in hand,
and the selection, as they are.

**The tree's rows are a window.** A large assembly opens onto thousands of rows, so the
tree (and a search's hits) is one flat list of its visible rows — each open branch's children
after it, a level deeper — drawn by `kit/inspector/VirtualRows.jsx`: only the rows in the
panel body's view and a margin either side are mounted, each at the place the whole list
would give it, in a list as tall as every row, so the scroll range, the rows' positions and
what is drawn are those of the whole tree. The window follows a scroll before the frame that
shows it. The selection's row, the search cursor, a focused row and the row whose context menu
was opened stay mounted wherever they are, so a reveal, Enter, keyboard focus and an open menu
always have their row; a row carries its level
(`aria-level`) in place of the nesting it no longer has. A face or edge picked
in the viewport is revealed at its part's row, wherever the part sits in the tree.

The model tree rows share the tree-row primitive (`TreeRowSurface`, `dense`: 24px rows),
inset 4px from the panel, with a 16px disclosure column and the explorer's 10px per level,
hung from faint lines under their owners' chevrons (`TreeRowGuides`), their kind icons light. A part is a
leaf: its faces and edges are the viewport's to pick, never rows. An assembly's disclosure
button expands its children; the rest of the row selects it. Labels keep the row's width;
measurements belong to Quick Edit's chips' cards. An assembly row's actions (`XbfPartActions.jsx`), shown on hover and kept
shown while they are on, are Isolate (lit while that node is isolated; not in a part
file) and then Hide (the eye). A double-click on a component or subassembly row
isolates it too; Isolate is also in the row's context menu.

That menu is THE part menu, the one the viewport offers over the same part: one
descriptor (`xbfMenus.js`'s `xbfPartMenu`) and one set of actions (`partMenuActions`),
rendered by `AssemblyPartMenuItems` (`xbfMenuItems.js`), so the two cannot drift apart. Copy Reference, Select/Deselect, Isolate/Exit isolate, Exit all isolates, Hide
others, Hide/Reveal, then the tree's Expand/Collapse and Expand all/Collapse all,
and last one framing group: **Zoom to fit** and **Zoom to selection** (off without
a selection). Framing cannot contradict the tool in hand, and every item of this
menu returns to Select before it acts. The VIEWPORT's menu exists only while Select is the
active tool — under any other tool a secondary tap opens nothing (in preview there is no viewport menu),
though the native menu stays suppressed and a secondary drag still pans. The
TREE is the file sidebar's, under every tool; every action of its menu returns to Select
first. A secondary tap on
empty space asks about the model as a whole (Show all, Expand all, Collapse all,
then the framing group; `xbfModelMenu`). A single-part document has no part menu — a press on
the part opens this one too — so there it opens with the part menu's reference group for the
whole part: Copy Reference. The tree starts directly below the model tree
section's head, its filter (`TreeFilterInput`, `primitives/tree-filter`, shared with the
explorer), with a conditional Show all after it. While something is isolated, an isolation
bar heads the tree (`Isolated: …` and **Exit**). Clicking empty tree space clears
selection.

The filter is a second view of the tree, never a filter over its expansion.
Typing replaces the rows with a flat, ranked list (first 200; a search-only status line counts
every match) drawn from an index of what the presented tree already holds: every
assembly and part by name. Typing expands nothing, so the picking frontier is the same
before, during and after a search. The query matches a name as a subsequence (`navigation/fuzzy.js`: `m3scr` finds `M3 Screw`); several words may
also name owners (`bridge screw`), provided one of them is in the name. A hit is
the tree row without its place: name first, its owners muted and truncating
behind it, with the same menu, visibility action, hover and availability.
Selecting a hit selects it in the viewport and immediately expands its owners
through the controlled expansion state — a selection is always a row the tree
holds — while the hit itself stays closed. The one reveal scroll waits until the
search ends (clear, Escape or an empty box); without a new selection the tree
returns to its previous scroll position. Up/Down move the cursor; Enter selects.

Parts retain their assembly hierarchy, except redundant document wrappers are
flattened for presentation. A single assembly root is also implicitly expanded
until its children offer a real choice, and expanded in the host, so viewport
picking matches the visible rows; a folded repeat is never implicitly expanded.
Flattening never rewrites occurrence or reference IDs, and hidden-owner
restrictions still apply to the exposed children. Assembly expansion uses the same
controlled state as viewport picking. A collapsed assembly is
picked as a unit; expanding it exposes its children. A part is expanded in the host
alone, never in the tree: by its menu's Expand (Expand all), so that a press under All picks
its faces and edges (`xbfTree.js`'s `xbfPickFrontier`). Viewport hits select individual faces
and edges in All, Faces and Edges modes; connected selection modes explicitly opt into edge
chains or tangent face groups. Double-clicking empty space exits isolation.

Isolation restricts the selectable subtree without propagating an excluded
ancestor's disabled state into the isolated descendants. Hidden geometry stays
unselectable. Selection reveals expand the required ancestors and scroll once
per selection or explicit reveal command. Later expansion and manual scrolling
must not pull the view back to that row.

A chip's card is read-only: under the reference's name and id, its rows are its key
measurements alone (`xbfChips.jsx`'s `xbfMeasurementRows`, the engine's facts of the element):
a face's area and a round face's radii, an edge's length, radii and an arc's sweep, a part's
size, volume and mass, a subassembly's size, volume and mass — no type, centre, normal,
component or source material row. A click on the chip copies its references (as Copy References
writes them, with the file's absolute path); the tree and viewport menus copy too, and
measurement previews are the Measure tool's. There is no source feature view.

Tool order, sub-toolbars, the file sidebar and cleanup policies are defined in
[the shared design system](settings-ui.md#tools-and-lifecycle). Keep renderer
implementations aligned with that contract instead of defining another layout here.

A selection outlives Select: under any other tool the view still lights it and
Quick Edit still carries it as chips, until it is cleared (its chips' X, Quick
Edit's X, Escape, or a new pick). Picking is Select's alone: choosing a row in the
Model tree (or a host `selectReference`) under another tool returns to Select
first. Every tool works alongside a selection, as it does alongside a pose, Explode,
Clip and the annotations (the two motions among them replace each other: one motion at a time).

### Position

Position edits persist when switching tools or tabs, or folding its section. A robot's new
revision keeps the values, and the named pose they were chosen as, when its driven joints and
named poses are the ones in hand (`poseLogic`, `robot/poseStore.js`); when they changed, the
pose starts at the new defaults — the old values are never fitted onto other joints. Its
Pose row's Default restores an engine document's as-built values (`xbf/XbfPositionSection.jsx`)
or the robot opening pose (including SRDF `home`). Preview's pose is its own. The Position
section's layout is [the design system's](settings-ui.md#position-and-references).

Position's knobs (its filter kind's glyph lucide `Spline`) drag a model's joints by handles
in the viewport, under Select while its filter ticks Position. They exist where
something can be driven: a robot (URDF, SRDF, SDF) with a revolute, continuous
or prismatic joint that is not a mimic follower, and an engine document whose mechanism
has a pair that turns or slides. Robots and engine documents
open in Select on All: the tool in hand is never stored, and a reload
brings back a robot's joint values with the rest of the file's view. The knobs are absent in
preview and under every other tool. A press on a knob is the knob's (`useJointHandles`),
anywhere else Select's pick; the camera orbits, pans and zooms exactly as under every other
tool. Choosing a mode without Position, or putting Select down, keeps the pose.

One handle system serves both formats. Two adapters turn a description and its
CURRENT pose into one plain list, in model space: `{ id, label, kind, pivot,
axis, toward, value, min, max, unit, onChange }` (`robot/jointHandles.js`, and
the engine document's `xbf/xbfJointHandles.js`). A robot's joint
frame is READ, not solved: it is the world matrix of the joint's node in the scene
graph, the joint's delta as `jointDeltas` composes it; an engine document's pair is
placed where the mechanism stands now, its pivot on the pair's frame and its axis the
frame's Z. A fixed joint has no handle. A row a coupling drives KEEPS its handle and writes
through the coupling, as its slider does (a robot's mimic follower through the control the
coupling reads, `controlWriteForHandle`; a geared pair through its gear): a coupling has no
axis to hang a handle on, and a gear train whose every member is geared would otherwise
have none. The list is rebuilt from the pose on screen,
so sliders, presets, Reset and a handle further up the chain all carry the
knobs along.

`onChange` is the Position section's own change path (the robot pose store's
`write`, the engine document's `writeXbfPosition`), so limits, mimic followers,
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
child's frame instead, and concentric members fan their arms round the
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
pose (an engine document's configuration, an SRDF group state) and Reset all put the model
where it IS from that frame on, for robots and engine documents alike. There is no eased
pose transition and no preference for one; motion over time is
a routine's. Each format has one write path (`write` in `robot/poseStore.js`;
`writeXbfPosition` in `xbf/XbfPositionSection.jsx`).

### Routines

Routines play from the file sidebar's **Animation** section, the shell's, for a file with
routines (`kit/tools/playbar/AnimationSection.jsx`, after the renderer's own sections), in the
tools view and Preview alike: **Reset animation** in its heading, which stops the routine
and puts the model at rest, disabled while it is; then, with two or more routines, the one in
hand, a dropdown of them (choosing one puts it at its start, at rest); then Play or Pause, the
scrubber (`AnimationTimeControl`) and **Playback settings** (`PlaybackMenu`: Speed — the
presets, and an authored speed outside them — Loop and Autoplay), opening down from its cog.
There is no Restart; the scrubber's start is the restart. A routine opens at rest. In the tools view a
paused routine's frame stays on the model, as a pose does. Each view's routine is its own, on
its own scene: Preview's (`RendererShell`'s `previewView.animation`) is at rest each time the
Preview opens, plays only when the file's Autoplay (`playback.autoplay` of its view,
`kit/tools/playbar/playbackPreferences.js`, off by default) is on, and goes with Preview's
view as it closes; the tools view's is never touched, and stands as it was left. Preview
opens still, whatever Orbit did last (`shell.orbiting`). Speed and Loop are the file's, one set, chosen in the Playback settings
and applied to its routine (`RendererShell.jsx`) once chosen (`playback.speed`,
`playback.loop`; unset, the routine's own); they, Orbit's speed and Autoplay are kept between
leaving and re-entering Preview, and across a reload of the tab. Nothing under the pointer
is pickable in Preview or while a routine plays.

One motion at a time in the tools view: Explode, the Position pose and a playing routine
replace each other (`kit/tools/model-effects/motionExclusion.js`, [Clip and Explode on any
scene](#clip-and-explode-on-any-scene)); while the model is exploded there are no knobs.

Of the playback the transport preferences survive every rewind — the routine, Speed and
Loop — for as long as the file is mounted. The routine and its time are not saved: a
reloaded file starts at rest, with the Speed and Loop chosen, if any, and a file opened
again after the tab left it starts at the defaults.

No component renders for a playing frame. While a routine plays, the animation clock calls
the renderer's frame once per tick (`usePlaybackFrames`; the GLB renderer drives its mixer so),
and the scrubber is the clock's only React subscriber. Because the frame runs inside
the tick, the clock's adaptive pacing measures a frame's real cost, and only a
run of frames that all overran slows it (`createAnimationFramePacer` in core's
`common/animationClock.js`): a frame that misses one vsync publishes on, where
pacing on it held the routine still for two or three frames and then moved it
four or five.

### Pencil and Shapes

Drawing is the viewer's own ink ([annotations](annotation.md)), with no drawing SDK
behind it, and two strip tools: **Pencil** (the Pen, the Highlighter, the Eraser) and **Shapes** (the Rectangle,
Line, Arrow, Ellipse, Text). An engine document (an .xbf or a STEP), a GLB, a mesh, a robot and a DXF offer them. (The tools themselves are the
SHELL's — `kit/tools/annotate`, `shell.tools.drawing` — and a renderer puts them on its strip;
`renderers/shell-harness` also mounts them, for tests.)

Each is one plain tool of the strip, a button (`shell.tools.drawing`, the icon of what it draws with now — the pen's and the
line's at first), with no chevron or menu: a press takes up the one last chosen. Their tool modes are `pencil` and
`shapes`; `useAnnotationSession(family, …)` is told which is in hand and keeps both choices (`pencil`, `shape`). Both share
the session's ink and history, but not the style: it is kept per drawing kind, three slots (`session.styles`) — the Pen,
the Highlighter and Shapes (all five shapes share one) — each with its own colour, stroke width and placement, and
`session.style` is the slot of the tool in hand. While either is up one sub-toolbar, "Annotation
controls", hangs under the strip (`annotation/toolbar.jsx`'s `AnnotationToolbar`, drawn by `RendererShell.jsx`), one row at
every width (a phone's wraps where it has no room, its buttons 36px tiles):

- The **tools of the one that is up**, a button each, the one in hand pressed: choosing one is how Pencil and Shapes change
  what they draw with.
- After a rule, **Color**, **Stroke width** (a straight line at the weight) and **Placement**, dropdowns, then
  **Clear annotations**: two sections, no more. They show and set the tool in hand's own slot; under the **Eraser**, which
  puts nothing down, the three are disabled (greyed out, still on the row so it does not jump) and Clear stays as it was.

The tools: the Pen, smoothed as it is drawn, its width following pressure (a stylus's own, or simulated from speed with a
mouse); the Highlighter, the same line at five times the stroke width, 0.35 opaque, round-ended, with no pressure
taper (`geometry.js`'s `highlighterMark`; an ordinary stroke mark, told by its opacity, `isHighlighterStroke`); Line, Arrow,
Rectangle (rounded corners), Ellipse, and Text, written in place; the Eraser. A
flat view passes `placements={false}`.

The drawing tools have no Select or Move view of their own. Picking ink is the viewer's Select's: under
Select, while its filter ticks Annotations (the shell's `selectsAnnotations`), a press on a mark picks
it (and the marks drawn with it, an arrow's head) before
any part or reference under it, haloed in the selection's blue; Shift adds or takes
away, a press on anything else lets go of it, Escape lets go and Delete deletes it.
Before the press, the pointer resting on a mark lights it as a part is lit, a fainter
halo, and the part under it is not lit (`RendererShell.jsx`'s `hoverSelectable`).
The colour, Stroke width and Placement set what the tool in hand draws
next, never ink already down. Placement is **On surface** (the default) or **On plane**.
Pencil opens on the pen and Shapes on the rectangle, each in neon red, 2px, On surface; the Highlighter opens in
neon yellow (`#ffe600`, on the palette in both schemes), 2px, On surface.

The ink Select has picked has a bar of its own (`kit/tools/annotate/AnnotationSelectionBar.jsx`):
the tool strip's surface, a size smaller, just above the ink (below it where there is
no room above) and following it as the camera and its parts move. Its Color, Stroke
width (strokes picked) dropdowns restyle the pick, one
step each; **Fill** (a closed shape picked) fills its interior in its colour, the fill
joining the shape's group so it is picked, restyled and deleted with it, and again
takes it away; **Delete** deletes everything Select has picked, a measurement too.

An annotation is not an overlay picture. Each mark is projected into the model in
3D as it is put down (`kit/tools/annotate/annotation3d.js`), so it stays where it was drawn
from every angle:

- A mark is in model coordinates and stays put whatever Explode, Position or hiding a part
  does to the model; Clip cuts it, and what the model hides of it is drawn faint through it.
- Ink lies on the surface it is drawn on. Each mark has a **level**: the plane of the surface it
  starts on (a flat face's own plane, a curved face's tangent plane at the start point; its
  normal the surface's, not the view's). Over nothing the level is that of the visible surface
  nearest to the start on the screen (else, with no model in the window, the nearest to the
  window; else the plane through the origin facing the view). **On surface** drops each point
  onto the visible surface under it, and a point with nothing under it takes the level;
  **On plane** puts every point on the level, flat across a curved face. Both carry on at the
  level off the model. Text is a card facing the view at the level's depth under its anchor.
  Views ("view 1", "view 2"…) are only the labels a prompt carries; nothing is drawn per view.

The camera stays the person's between strokes: the wheel zooms, a right or middle
drag orbits (the press goes on to the view), and while Space is held the pointer is
the view's.

Select picks a measurement the same way (`measureSelectHandlers`' press in
`kit/tools/measure/measureSelection.js`, through the shell's `onSelectPress`): a press on its dimension line, a witness line or its
label picks it before ink and parts, haloed in the selection blue, and Delete deletes
it (`useMeasureSession`'s `removeSelected`, the shell's `deleteSelection`). One press
picks one kind: a measurement, an annotation or a part lets go of the others
unless Shift keeps them, while Select's filter ticks Measurement. The pointer resting on a measurement lights it first, a
fainter halo (its hover, through the shell's `onSelectHover`), and the part under it is not lit.

A file view has one set of annotations (`annotation/session.js`). It has no panel: while
there is ink it is Quick Edit's **Annotation** chip, its pen first — a click copies the path
of its `.annotation.json` file, its X clears the annotations as one step to undo. ⌘C or
Ctrl+C, while Pencil or Shapes is up, copies the view as it is on screen, ink included, as a PNG
(`host.clipboard.writeImage`).

With them put down the ink stays in the model, and its chip in Quick Edit. The next
drawing tool adds to it. Annotations are session-only and never written to tab or file state.

**Undo and Redo** are the annotations' (`kit/shell/useViewerHistory.js`, the shell's):
each piece of ink put down, erased, restyled or filled, and a clear, is a step.
They are the keyboard's, with no buttons: ⌘Z and ⇧⌘Z (Ctrl+Z and Ctrl+Y) walk them from anywhere
in the viewer but a text field. A Quick Edit note
carries the annotations as files: the annotation file, the views they were drawn in as a
snapshot job, and a picture of each ([annotations](annotation.md#lifetime-and-capture)).

### File navbar

The file navbar is [FileViewer's](file-viewer.md#the-navbar-and-the-explorer): the logo,
which opens the app menu (Back to files, the person's settings, feedback, the links, the
version), Back and Forward where the host keeps the view's history, the file's name (which
opens the explorer) and its ⋯ menu at the left; at the
right only what a host or a file adds: the update, the renderer's actions and, last, Full
size. The CAD renderers publish one navbar action, and only while a person has put away an
alert card the model survives: the card's own icon, which brings it back (see
[Inspect, Render and live revisions](#inspect-render-and-live-revisions)). What a person
tells the agent is Quick Edit's. The view's own controls (Display, a popover from its tile,
and Preview) end the renderer's tool strip, never the navbar's row. The renderer's update
status is in the viewport, under the strip, never in the navbar. So a view drawn as a
picture (`compact`, as the home draws its thumbnails) needs no navbar at all.

The host's `captureRequest` command captures the view (with its annotations, when there
are some): to a composer destination it goes through the prompt-context port
(`promptContext.deliver`) with the references it depicts. The DXF renderer, which is
not on the shell, answers it with its canvas through the same port.

### Preview and the camera

Camera framing, routines and Preview follow the shared
[interaction contract](settings-ui.md#camera-animation-and-preview).
`useViewportCamera` owns initial fit and orientation transitions. Preview's camera is
its own viewport's: framed afresh from the default direction each time it opens and kept
nowhere, while the editor's camera stays where it was, untouched, under it.
`zoomRuntimeToBounds` is the single framing act used by context-menu
Zoom to Fit and live `resetCamera`. Cube shortcuts preserve zoom and pan.

Preview is one `previewing` state the shell owns (`usePreviewState` in
`useRendererShell.js`); a renderer whose own gates run before the shell's hook holds
it and passes it in as `preview`, as the engine document's does. It is a 3D view's: a renderer that
offers it declares `previewable` (the engine document's, GLB, the meshes and robots do), and one that
does not has no Preview button and stays in its normal view whatever sets the state. The
Preview button, last in the navbar, sets it — after covering the view in the frame of the
press ("Preparing preview…", until Preview's view has presented, its published mesh is complete and the
picture has converged) — and Escape or Exit preview, an X beside Preview settings in the navbar, clears it;
no host prop reaches it.
Preview is a view of its own (`kit/shell/PreviewView.jsx`): RendererShell mounts it over the
editor's viewport box while the state is on and unmounts it as it goes. The editor's viewport
is never told: it is `suspended` (it draws nothing under Preview, and a frame asked of it
meanwhile is drawn before paint as it is uncovered), and what shows when Preview closes is
its own last frame. Each family builds Preview's scene with its own builder over the
editor's geometry (`createSibling()` for GLB, mesh, robot and engine document scenes,
`usePreviewScene.js`), with its own pose and routine.
While it is up, the frame drops the tool strip and its sub-toolbar, the tool stack and their
resize handles, Quick Edit, view cube (not mounted), alert card and viewport menu, the file
sidebar offers its Position and Animation alone (Preview's own pose and routine), and every
renderer gate reads the same state: picks, hover, highlights, Measure, Pencil and Shapes, joint
handles and Select are off, and Explode and Clip suspended, without discarding their values.
The navbar stays; its right end (the renderer's `navbarSlot`; with no navbar, Preview's
corner, `PreviewChrome`'s `end`) holds Preview settings, a toggle whose panel
docks under it (`kit/shell/PreviewSettings.jsx`: Orbit, off at every entry, and its speed, then
Preview's own settings, `PreviewRenderSettings`), and Exit preview; nothing sits under the
model or at the bottom centre. Preview is drawn in Render whatever the file's display mode:
it draws `previewViewScene(store.renderScene())` (`kit/viewport/previewViewScene.js`: no
clip or explode, one scene-quality tier up, `previewSceneQuality`, its full pixel ratio kept
while it orbits, never a Display setting changed), and the editor always draws the file's own
scene: Render is no display mode, so the view settings store never draws it, and Render
settings edited in Preview are the file's. Preview never uses the browser
Fullscreen API.

### The GPU device

Every viewport on the page draws through one WebGL context
(`kit/viewport/gpuDevice.js`): `acquireGpuDevice` makes one `WebGLRenderer` on an
`OffscreenCanvas`, refcounted and kept 5 s after its last view, so the programs compiled for
one file survive the switch to the next. A viewport's renderer is a handle on it
(`device.createView(canvas)`, made by `useViewerRuntime`'s `createViewRenderer`): its
`domElement` is the view's own DOM canvas (a `bitmaprenderer` context), and its size, pixel
ratio and renderer state (tone mapping, exposure, output colour space, clipping, auto-clear,
`sortObjects`, the shadow map's enabled/type/autoUpdate/needsUpdate, clear colour and alpha,
viewport, scissor) are the view's, swapped in when it draws. A frame's draws are handed to the
view's canvas once (`transferToImageBitmap` to `transferFromImageBitmap`, a microtask after the
frame, or as soon as another view draws), so geometry, textures and programs are uploaded once
however many views draw them. Pixels read back right after drawing (a screenshot, core's
`screenshotCapture.js`; a thumbnail, `kit/viewport/thumbnail.js`) come from the handle's
`drawingCanvas`, the device's buffer. A released view that drew last shrinks that buffer to
1×1, and the next view to draw sizes it. A lost device context is dispatched to every view's
canvas. Render's environment cache is the device's (`look/studioEnvironmentCache.js`,
`studioEnvironmentCacheFor`), released with it, so what the editor prepares is what Preview
draws; a runtime never disposes an environment the device owns. Where the browser has no
OffscreenCanvas WebGL or `bitmaprenderer`, there is no device and each viewport makes its own
renderer (core's `createCadWebGlRenderer`). Read-only seam: `window.__cadGpuDevice()`
(`{ views, geometries, textures, programs, buffer }`).

### Robot links

A URDF, SRDF or SDF opens in Select, with **Links** in the file sidebar (headed by its search
box), an `.sdf`'s **SDF** section after it, then
**Position** where a joint can be driven (`LinksSection`, `SdfSection`, `PositionControls`),
whatever the tool. Links is always present: it is the description's kinematic tree, not an
inventory of mesh names. `robot/robotTree.js` builds it as plain data.
Links are the rows, carrying no icon; a child link sits under its parent link
and shows the joint between them as muted text (`shoulder_pan · revolute`); the
visual components (`robotComponents` in core's `lib/urdf/robotParts.js`) are leaves under that
link, after its child links. Every visual contributes a component, including STL
meshes and built-in primitives, named as the payload labels it (`visuals[].label`,
minted by cadgen: the visual's URDF `name` or, without one, its geometry —
`bucket.stl`, `box`). A mesh with named objects still splits into
those objects; an unsliceable mesh stays whole as one selectable component. Every link appears once: a cycle, a second parent or a
missing parent cannot hang the builder or drop a link, and orphans become
roots. A root that is only a frame — no geometry, no mass, and one child
attached by a fixed joint (`base_footprint`) — gets no row of its own; its
child leads the tree instead, unless the description has no content anywhere,
in which case every link is kept. An SRDF shows its paired URDF's tree.

The section reuses the model tree's pieces rather than cloning them: the dense
row primitive, the filter (`TreeFilterInput`, `primitives/tree-filter`), and the ranked
flat search of `kit/inspector/modelTreeSearch.js` (`useTreeSearch`). Its X is the section's: it
closes the panel. The search index also reads a row's `searchAliases`, so a
link is found by its joint name and the hit shows that joint in place of its
owners. The root opens, along with a chain of single child links below it;
everything else starts collapsed. When the tree has exactly one root with
children, that root is pinned: no chevron and no indent, so its children start
at the tree's own left edge. Selecting a hit opens its owners at once and
scrolls to it when the search ends.

Selection is the scene graph's. A link is hovered and selected in the viewport
as the meshes of its group, and a viewport pick selects the visual component
(or named mesh object) under the pointer. Any number of
links, or of components, can be selected, never both (Shift in the viewport,
Shift/Ctrl/Cmd on a row add), each a chip in Quick Edit (`robot/robotReferences.jsx`). A
link with no geometry selects its row and chip only. Viewport picks are Select's while its
filter ticks Links. As for an engine document, a robot selection outlives Select: a pick in Links returns
to Select, leaving Select keeps it, and Escape clears it. A click acts at once, as an engine document's does; a
robot has no double-click at all.

Each link or component row has the Hide/Reveal eye of an assembly row
(`settings-ui.md`; `robot/RobotVisibilityButton.jsx`), also in search results.
A link hides its own visuals, leaving child links visible and all joints active.
A partially hidden link hides its remaining visuals; a fully hidden one reveals
all of them (`robot/visibility.js`). Hidden geometry is excluded from rendering,
picking, the bounds and selection highlights: the scene takes the ids
(`setHiddenPartIds`) and keeps its meshes for a reveal without rebuilding them.
Hidden component ids are the `visibility` slice of the file view, saved against the
payload's revision beside the pose (`robot/useRobotVisibility.js`); a live reload
retains only ids still present.

The `tcad:four_bar` extension is a nonlinear mimic in core's URDF parser and
kinematics solver. Its dependent joint has no Position slider or joint handle;
its chip card names its four-bar driver instead of an affine mimic formula.
The authoring contract specifies the namespace, geometry and range constraints.

A link's chip card (`LinkDetails.jsx`), headed by the link's name, reads back what the
description says about the link, in sections: its SRDF planning groups (`srdfGroupNamesByLink`) and end effectors;
**Inertial** (mass, centre of mass in the link frame, and the six inertia terms
laid out as the symmetric tensor); **Geometry** (each visual and collision as
its mesh path or its primitive with dimensions, plus only what the description
bothered to say: a scale that is not 1, an origin that is not zero, the visual's
colour); the **Parent joint** (name, type, parent link, axis, lower/upper limits
as written plus degrees, effort, velocity, mimic, origin); and the **Child
joints**. cadgen keeps those facts as the description wrote them, in the payload's
`links` and `joints` (`joints[].origin`, `limit`, `mimic`; `links[].inertial` with
`origin` and `inertia`, `visuals` and `collisions`, each mesh file with the host path
cadgen resolved for it), beside the articulation it renders from. An SDF model
reports only what cadgen records of it. A named object shows its link, colour,
triangles and size.

What names something else can be followed. A mesh path is a link that opens
that file, by its absolute path, through the host's `onOpenFile`: the renderer resolves
it against the opened file with the mesh loader's own `resolveLocalAssetFileRef` (an
SRDF's URDF is always beside it). A `package://` reference has no path here and stays
plain text, as is every mesh path in a view that shows its file alone (no `onOpenFile`: a
host's file handler). A parent or child link name selects that link in the tree and the viewport.
A click on a link's chip copies its reference (`/path/robot.urdf#upper_arm`); a link whose
name the reference grammar cannot spell has no reference, and is left out of the prompt.


### Tool panels and dark surfaces

A renderer's sidebar sections are `ToolPanel`s drawn as sections of the file sidebar
(`kit/tools/FileSidebar.jsx`, through `ToolStackContext`'s `sidebar`): the bar's width, each
its content's height, no surface, scroller or grip of its own, always headed, folding where
there are others; the bar scrolls as one and is sized from its own bottom-right grip. A
renderer's own `toolPanels` are `ToolPanel`s in the tool stack under the strip and
sub-toolbar (`kit/tools/ToolStack.jsx`): every panel one width (164px, a six-tool strip's),
each exactly its content's height — up to its cap, for a `resizable` one, which opens at the
column's height — until the column runs out; then a `"tree"` panel scrolls inside itself
first, the `"details"` ones next, each in proportion to its height, and a `"fixed"` one
never; and if those still do not fit, the column scrolls. Each sidebar section's size, the
resizable panels' sizes and the folded stack panels are one of the tab's settings
(`CadPreferences.toolStack`).
The strip, its sub-toolbars, the sidebar's tiles and the stack's panels share one translucent
surface, lightly blurred; every menu and popover over the viewport a more opaque one with more
blur and the same border; the sidebar's panel and Preview's settings, read while they are up,
one between them (`lib/floatingSurface.js`); every scroll region is the
`ScrollArea` primitive. A submenu is portaled, never drawn inside its parent menu, which that
surface makes a containing block.

The shared dark UI and the tools view's canvas take Preview's cool blue-grey (hue 264): the
tokens at chroma 0.008 on the shadcn lightness steps, the canvas Preview's stage mid-tone
`#25272b` (its stage runs `#2c2e31` to `#202226`), so the two views read as one look; light
app appearance selects its light basis.
The shared loading star and desktop wordmark/icon use blue branding.

## Inspect, Render and live revisions

The Model tree keeps the document's assemblies and parts, contextual dimensions, selection
filters and prompt-reference actions. It does not inspect model source, and never
initiates a source build. A complete previous version stays visible until its replacement
is ready.

Display selects Solid, X-ray, Hidden line or Wireframe. Each has its own
settings submenu and remembered overrides; editing an inactive mode does not select it.
Reset removes only that mode's overrides and keeps camera, Clip, Explode and the other
modes. Render is Preview's alone, its settings Preview's settings panel; it resolves
to perspective, and the shared camera defaults to orthographic.
The schema and menu behavior are specified in [Per-mode display settings](render-mode.md).
Photographic lighting and stage code stay lazy. Authored materials are read-only, with
no material override or undo state.

The host-supplied render session owns its worker leases.
The file view's display slice is the sole view-settings authority; the camera is the
mounted viewport's, saved with the view and restored in place of the fit. An engine
document's reads use the file's injected service and abort when the consumer leaves.

Opening shows in the viewport's loading overlay. An update — a newer revision
loading behind the model on screen, or a Display change being prepared, and that
change's failure with a Retry — shows centred at the top of the viewport, level
with the tool strip (`ViewUpdateStatus`; on mobile, a spinner whose label opens on
press). An error is a card over the viewport (`ViewerAlertCard`), always;
one the model survives (`blocking: false`, the previous version still on screen)
has a Dismiss button, and stays dismissed until the alert changes, or clears and is
raised again, or another file opens. The dismissal is the frame's (`useAlertDismissal`), so a
trip to Preview keeps it, and while it stands the card's own icon, in its colour and named
after the alert, is the first of the navbar's right-hand controls after the update button
(the renderer's navigation action): pressing it brings the card back, and the icon goes. A warning is a card
too, dismissible while the model is on screen:
there is no other place a problem is listed. Full diagnostics stay expandable under
Details; Retry uses FileViewer's renderer reload,
which reopens the file and does not restart the desktop window, and Report Issue,
where the host has a tracker, opens a new issue titled "Issue: ", labelled `bug`, filled in
from the card, with the file's name and no path of the machine.

### Camera framing and zoom

Zoom to fit and the live `resetCamera` frame the original authored model bounds at
the current angle, and that framing is 100%. A saved revision keeps the camera and its
zoom exactly; Zoom to fit frames the new revision. Explode, clipping, animation, kinematics, visibility, floor and
other scene effects never redefine 100%. Perspective and orthographic derive
their own baseline from that same box and the current viewport dimensions.
Selection fit may move the camera but cannot make that new framing become 100%.
`kit/camera/viewportCameraFit.js` owns the fit calculation; live posed bounds remain useful
for clipping, lighting and picking. Nothing displays that percentage; it is read
through the `window.__cadCamera()` test seam (`zoomPercent`). The acts that frame the
model are an engine document's context menu (Zoom to fit, Zoom to selection) and the live
`resetCamera`; the view cube (bottom-right, absent in Preview) turns
the camera and keeps its zoom and pan, and opening a file fits the model afresh (a
reload of the page restores the camera the file on screen was left at).
