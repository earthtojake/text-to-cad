# CAD renderer

The viewer is the viewport, the floating tool strip and the tool in hand's
sub-toolbar under it, the view's panel, reference interactions, measurement and annotation
tools, animation, the loading indicator and alerts, in `@cad/ui`. The rules of its
chrome — which tools a file has, how they take and give back the pointer, the view's panel,
Preview, the keyboard — are [the viewer's layout and patterns](viewer-ux.md) and the
[design system](design-system.md); this document is the mechanism behind them.

There is one renderer per file family over a shared, format-blind [kit](#kit) and
[shell](#shell). A STEP opens in the [engine document renderer](#engine-document-renderer)
(`src/renderers/xbf`), as an `.xbf` does: the page reads what the engine serves of it.
Applications use the registrations and the shared
`FileViewer`; they do not import another application's source.

## Kit

`src/renderers/kit` is the format-blind half of the viewer: small modules a
renderer composes, none of which asks what it is showing. There is one renderer
per file family, each a vertical slice over the kit: `src/renderers/board` (a KiCad board),
`src/renderers/dxf` ([DXF renderer](#dxf-renderer)), `src/renderers/glb` ([GLB renderer](#glb-renderer)),
`src/renderers/mesh` (STL and 3MF, [Mesh renderer](#mesh-renderer)),
`src/renderers/robot` (URDF and SRDF, [Robot renderer](#robot-renderer)) and
`src/renderers/xbf` (an `.xbf`, a STEP and an STP, [Engine document renderer](#engine-document-renderer)). The kit imports itself, shared UI
(`primitives`, `lib`, `drawing`) and the format-blind half of `@cad/core`
(`lib/viewer/*`, `lib/perspective.js`, `common/viewSettings.js`,
`common/sceneSettings.js`, the Render studio); a renderer imports the kit, never
the reverse.

| folder | what it is |
| --- | --- |
| `viewport/` | `useViewerRuntime` (three.js renderer lifecycle, on-demand render loop and `requestRender` -- a frame asked for is drawn in the browser's next animation frame, however late a GPU behind on its frames makes that, so the page stays the browser's to pace; only a HIDDEN document, which gets no animation frames, draws from a timer, as it hides and 120 ms after each later request -- resize and device-pixel-ratio caps, context loss, keyboard orbit, `setSuspended`, teardown), `gpuDevice` (the page's one WebGL context, shared by every viewport: see [the GPU device](#the-gpu-device)), `previewViewScene` (Preview's view of the file's Render settings: no clip or explode, one scene-quality tier up, `previewSceneQuality`), `framePresentation`, `viewportBuffer`, `renderDepthPolicy`, `sceneObjects` (`disposeSceneObject`), `thumbnail`, DOM helpers. The scene in the viewport is its owner's: teardown calls the injected `disposeScene(runtime)` and `disposeStudio(runtime)` and disposes its lights' shadow maps; a runtime with a renderer of its own (no device) then loses its WebGL context (`forceContextLoss`), since three's shared textures keep every renderer that drew them reachable and only a lost context gives its GPU memory back, and one on the device lets go of its view and never ends the device's context. A torn-down runtime draws no further frame. The orbit controls let go of the page in a layout cleanup, before React detaches the canvas: they listen on its root node, which is no longer the document once it is detached. |
| `camera/` | `runtimeCamera` (zoom percent against the authored framing, projection and lens sync, perspective snapshots, eased transitions — each a turn of the camera about its target, its whole orientation on the shortest turn and its distance eased, so the eye goes round and never through the target, and a half turn goes the screen's right — fit-to-bounds, recentre), `useViewportCamera` (that behaviour bound to a mounted viewport: the perspective kept by a mounted view, the reset that Zoom to fit and the live `resetCamera` share, view-cube presets, which turn the camera and keep its zoom and target), `viewportCameraKit` and `viewportCameraFit`, `turntable` (the orbit: three's OrbitControls with its rotation replaced by a turntable that goes over the top — sideways about the world's vertical, up and down about the camera's own level right, unclamped, the camera's up its own and never rolled, a drag's sideways sense held from its start; the arrow keys and the cube's drag turn through it too), `orbitControls`, `zoomPivotReanchor` (a wheel step first moves the pivot's depth onto the surface under the cursor, and a perspective pan is scaled by that surface's depth, so Render pans and zooms what the cursor is on at Solid's rate), `zoomSpeeds`, `cameraLens`, `ViewPlaneControl` (view cube). |
| `look/` | `stageEffects` (lighting rig scaled to the model, floor, glow and shadow catcher, grid and origin axes), the Render studio boundary (`renderStudioChunk`, `studioEnvironmentCache` and its worker). `canvasColor` (the canvas a scene is drawn on, the `--canvas` token, and the colour of the box it fills), `useViewportTheme` (the viewport's theme: the person's Background, Light or Dark). The surface LOOK is data the viewport resolves and a scene applies to its own materials: `@cad/core/lib/viewer/surfaceLook.js` (`createSurfaceLook(THREE, root).apply(look)`) does it for any authored material tree. The viewport resolves it with core's `resolveSceneSurfaceLook` (`common/sceneSettings.js`), the resolver the snapshot CLI dresses the same scenes with. |
| `view-settings/` | The settings model and store (`viewSettingsStore`, `useViewSettings`, `viewerDisplaySettings`, `renderState`), applying a change to a viewport (`useAppliedViewSettings`, `viewUpdateCoordinator`, `viewUpdateGate`, `viewUpdatePlan`), the content of Display's card (`DisplayModeOptions`: the modes and the Grid switch's icons, its Style's options), the settings cards (`SettingsCard`: the Display card's and Preview's one card, its placement, slide, rows and sections), and Preview's Render sections (`PreviewRenderSettings`). |
| `tools/` | `FloatingToolBar` (the dumb strip at Figma's toolbar's proportions, a 40px bar of 28px tiles 5px in, a phone's tiles 36px: the tools it is handed, one row with no rule, and only tools; a phone's those that do not fit in its More), `SubToolbar` (the tool in hand's row under the strip, Draw's two, its groups parted by `SubToolbarSeparator`; `SLIDER_SUB_TOOLBAR_CLASS`, the one width of a slider row; Explode's and Clip's rows are the same component, `model-effects/ModelTools.jsx`), `toolModes` (the tool-mode state machine), `ToolModeMenu` (`ToolSettingsMenu`: a tool's settings dropdown, from a chevron right after its button on the strip, or a sliders button in a panel's heading), `ToolPopover` (an ordinary dropdown from its button, on a `side` and `align`ed start or end: Preview's playbar's Playback settings), `ToolStack` (the bounded column under the strip and sub-toolbar for a renderer's own `toolPanels`, which scrolls only when what cannot give way still does not fit), `ToolPanel` (one panel of the stack, or one tab of the view's panel, `kit/shell/FlatPanel.jsx`: `fit` says how it gives way when the viewer is short, `resizable` makes a stack panel the person's to size by the grip in its bottom-right corner alone, moving only it, and a panel with a heading can fold to it), `ResizeGrip` (the one resize grip of a box over the viewport: a resizable panel's, at its bottom-right), `toolStackLayout` (every panel's width, the resizable panels' sizes and the folded stack panels — defaults, bounds and the tab's stored record, whose old shared fields for the view's panel it still reads so that `file-viewer/filePanel.js` adopts them once; the view's panel itself is the file's, `filePanel.js`), and the format-blind tools: `annotate/` (`AnnotationOverlay`, the surface the drawing tools' gestures land on; `annotation3d`, its ink projected into the model; `AnnotationSelectionBar`, the bar of the annotations Select picked), `PreviewChrome` (Preview's chrome: the tools view's controls hidden and inert while it is up, and its own corner, `end`, with its settings panel under it, `panel`), `PlaybackMenu` (the Playback settings — Speed, Loop — and `ORBIT_SPEEDS`, Preview's Orbit speeds), `playbar/` (`AnimationSection` (the tools view's routines, the panel's Animation tab for a file with routines, one set of controls at rest, playing and paused: the Clip dropdown row, always, then Play/Pause and the scrubber, whose start is the rest pose, with no time readout, then Speed and Loop rows, and Reset at the tab's bottom right; `AnimationControls` and `JointsMotionContext`, the rows a mechanism's Joints tab draws first), `PreviewPlaybar`, Preview's playbar under the model: the routine where there are several, Play/Pause, the scrubber, Playback settings; `AnimationTimeControl`, the scrubber, and `animationControlsHaveContent`; `animationClock`, `usePlaybackFrames`, `playbackPreferences`: the file's playback settings — Orbit's speed, the chosen Speed and Loop), `pose/` (the handle overlay, canvas, drag mathematics), `select/` (`SelectFilterMenu`, every picking tool's Filter on its chevron, its one row `SelectionSettings.jsx`'s `FilterRow`; `selectFilter`, its pure ticks, the strip's badge and the telemetry name of each box; `usePointerPick`: taps and hover through a scene's own `pick`, each with where the pointer was; `useBoxSelectGesture`, the one box of every viewer (a window left to right, a crossing right to left, each its own look), which draws its box over a scene and holds the camera for the press, mounted by `RendererShell` for a renderer's `boxSelect` and by `useFlatBoxSelect` for a flat view's Select; `boxTake`, what a box takes of each kind, Shift adding; `useSceneSelection` and `sceneReferences`: the parts a scene's pick names, selected, lit and handed to Quick Edit as references), `measure/` (Measure, for any 3D view: `useMeasureSession`, the session; `useMeasureOverlay`, its drawing; `MeasurementCard`; `measurementChips`, its chips and its row under the strip (`MeasurementsBar`); `measureSelection`, Select's press, hover and box on a measurement; `SceneMeasure`, two points on a scene's surface, and the model's size row), `model-effects/` (Explode and Clip, for any scene that opts in: `ModelTools`, their strip tools and slider rows, each the slider control `inline`; `useSceneEffects`, the viewport applying them to the scene; `motionExclusion`, one motion at a time), `sceneTools` (the tools a scene's renderer composes around the shell: the tool in hand, Draw, Measure and the model effects), `quick-edit/` (`QuickEdit`, the note to the agent, and `quickEditPrompt`, the context it builds and the text it copies). Screenshot capture is `@cad/core/lib/viewer/screenshotCapture.js`. |
| `inspector/` | `FileSheet` and its row and section primitives, `SliderField` (the slider control: every number a slider sets, in a panel or `inline` in a toolbar row), `modelTreeSearch` (`useTreeSearch`, the ranked flat search every tree shares), `VirtualRows` (a long tree's rows, windowed), `referenceRows` (`InfoRow`, `MonoValue`, `CoordValue`), `kinematicsControls` (the `Pose` row over a Joints tab's joints, a settings row labelled Position whose dropdown is as wide as its value: Default, the named poses, Custom; and its Reset, the tab's actions row, last, `KinematicsResetRow`), `PanelActions` (a tab's actions row, last and sticky: Params' Reset and Save, Joints' Reset), `CircuitTree` (a board's or a schematic's Parts and Nets), `ItemDetail` (what a pick is, in a Quick Edit chip's card, the one place a pick is read in detail: the pick in focus alone, its name and a few key facts, no list of what it holds) over `inspect.js` (the view's one description of a pick, `DetailItem`, and the `Inspect` it hands its frame: the cards' and the hover tip's), `layerRows` (`LayerSwatch`, a layer's colour in a row's glyph slot; `LayerColorMark`, a branch layer's after its name), `SceneTreeSection` (a GLB's nodes, a 3MF's objects, an STL's bodies: the Model tab, there from the view's first frame, the panel's placeholder rows in it while the file loads). Every panel view reuses the STEP/xbf Model tree's base components, never its own: `primitives/tree-row`'s one row (`TreeRowSurface` with its `depth`, `TreeRowGlyph`, `TreeRowToggle`, `TreeRowName`, `TreeRowDetail` — every count's style — `TreeRowActions`, `TreeRowHeading`), which alone sets a row's horizontal geometry — its gutter (the chevron's column), its glyph and its name, a column further a level — from the panel's `--tree-row-pad` and `--tree-row-actions-pad`; `primitives/tree-filter` (the filter box, `TreeFilterHighlight` and `TreeFilterMatch`, a search's lit match, `TreeSearchStatus`, its count); `VirtualRows`; no text size of a view's own. |
| `status/` | `LoadingIndicator` (the view's step, said over `loading/LoadingStep.jsx`'s line and bar) and `ViewerLoadingOverlay`, `ViewerAlertCard` (the card over the viewport for every alert, and `useAlertDismissal`: a card put away, and its icon in the navbar that brings it back) and `reportIssue` (`alertIssueUrl`: its Report Issue's new issue), `ViewUpdateStatus`, `loadingState` (`viewerLoadingState`), `loadAlerts` (`failureAlert`, `noGeometryAlert`). |
| `shell/` | The host glue every renderer needs that is not about its scene: see [Shell](#shell). |

**What a view opts into.** Display's settings and `resolveViewSettings` take explicit
lists, `features: { modes, settings }` (`ViewFeatures` in
`@cad/core/common/viewSettings.js`): the modes it lists and the settings
its menus offer (`VIEW_SETTING_IDS`). A setting left out does not affect the
scene, and saved settings are never rewritten. `viewFeaturesForKind(kind, { parts })`
is the one rule of which list a file gets: `ALL_VIEW_FEATURES` for an engine document (an `.xbf`, a
STEP) of several parts (`XBF_VIEW_FEATURES`), and without Parts or Explode for one of one part
(`XBF_PART_VIEW_FEATURES`); for any other 3D file Solid, with Parts where it draws several
parts (`scenePartCount`), and Clip, and Explode too for a GLB of several rigid nodes that draw; and `EDGELESS_VIEW_FEATURES` (no Edges, Clip or Explode)
for a drawing. Render is no mode. Every
renderer hands its list to the shell, which configures the view-settings store
(`configure({ features })`) and Display's settings from it, and to its Explode and Clip
tools. The OCCT parity bench's headless page (core's `common/renderMeshScene.js`) resolves a job
of each family under the same rule; `cad <type> snapshot` itself draws every family by OCCT in the
engine.

**Tools.** The strip draws the list it is handed: `{ id, label, icon, active,
disabled, onSelect, description?, menu? }` — a press is a tool's only action; a tool with
settings has them as `menu`, a chevron right after its button (Select's filter, the only
one), and what it can be set to while it is up is its sub-toolbar. Display is not a tool:
its settings are Display's card (`kit/shell/DisplaySettings.jsx`), the navbar's one button left of Preview. A renderer
builds its own list from `shell.tools.own(...)`, adding `shell.tools.drawing` (Draw) where it offers
them, declared in its `toolModes` as two modes (`pencil`, `shapes`) (a press on the tool in hand does nothing); the engine document's is in `xbf/XbfRenderer.jsx`.
Routines play, in the tools view, from the Animation tab the shell adds to the panel, last, for a file with
routines, or, for a mechanism whose Joints tab takes its motion (`jointsHoldMotion`), from the top of that tab
(`kit/tools/playbar/AnimationSection.jsx`), never from the strip; in Preview from Preview's playbar
(`PreviewPlaybar.jsx`). Preview is not a tool: its button, the navbar's after Display, enters it. Nor is Quick Edit: it is a bar at the view's bottom, on the strip's centre line, always there, one row, its attachments a row above it while something is picked or annotated. `createToolModes({ defaultMode, modes })`
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
means. A tap acts at once, but for one that would take something out of the selection (`takesAway`: the thing
selected pressed again, or a selected thing with Shift or a finger), which waits the double-click window
(`DOUBLE_CLICK_WAIT_MS`, a finger's `DOUBLE_TAP_MS`) and which a double-click drops.
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
renderer AND by the parity page's `common/headlessScene.js` from one core module, are
defined nowhere else, and no module on that page's render path imports a mesh
flattener.

### One scene builder per family: the viewer and the parity page

`cad <type> snapshot` draws every family by OCCT in the engine (`engine/snapshot.py`,
`render/occt.py`; a DXF through `render/drawing.py`), never through these builders. What calls
them beside the viewer is the OCCT parity bench's headless page, which draws each family beside
OCCT's still to measure how alike they are (`scripts/bench/occt_parity.py`): a family's scene
construction lives in `@cad/core` (no React, no DOM beyond three.js); its renderer here
keeps the loading state, the tools and the panels, and the parity page (`common/headlessScene.js`,
routed from `common/headlessRenderEntry.js`) keeps only what a still has and a viewport does
not: the camera fit, the studio set up per output, and PNG encoding.

| family | builder (core) | viewer caller | parity page caller |
| --- | --- | --- | --- |
| GLB | `lib/render/glbScene.js` `createGlbScene`, over `loadRenderGlbDocument` | `glb/useGlbScene.js` | `GLB_FAMILY` |
| STL, 3MF | `lib/render/meshScene.js` `buildMeshScene`, over `loadRenderMeshByUrl` | `mesh/useMeshScene.js` | `MESH_FAMILY` |
| URDF, SRDF | `lib/urdf/robotScene.js` `createRobotScene` over `robotParts.js`, loaded by `lib/urdf/loadRobot.js` | `robot/RobotRenderer.jsx`, `robot/useRobotDocument.js` | `ROBOT_FAMILY` |
| an engine document (`.xbf`, STEP) | `lib/xbf/xbfScene.js` `createXbfScene`, over `loadXbfDocument` | `xbf/useXbfScene.js` | `XBF_FAMILY` |

Both callers dress a scene the same way: the look from `resolveSceneSurfaceLook`, shadows
while the lighting is on, `keepsAuthoredFinish` for Inspect's reflection environment, and
the ground sized from `restBounds`. Both cut and explode it the same way: Clip through
core's `lib/viewer/sceneClip.js` (the plane in the box the camera frames, `at` in the
file's unit, the cut capped as a STEP's is), Explode through the scene's `setExplode`
(`lib/viewer/sceneExplode.js`, a STEP's layout over the file's tree). A robot's parts a
Quick Edit's view hid come back in its job's `selection.hide`. A robot opens at
`openingControlValues` (core's `common/articulation.js`: every joint's default, then an SRDF's
`home` state) and the job's `resolved.controls` go on top through the same joint matrices
(`cad <type> snapshot` poses a robot by `--pose`). A GLB's clips play in the viewer's Animation
section and have no snapshot flag. The pieces are pinned by `common/headlessScene.test.js`
(core) and `kit/view-settings/renderState.test.js` (one look from either route); the engine's
stills of each family are `tests/python/packages/cad_server/engine/test_snapshot.py`'s.

### Shell

`kit/shell` is what a file-family renderer needs from its host that is not about
its scene. A renderer loads its document, builds its scene (`kit/scene.js`) and
calls one hook; the shell owns the rest.

| module | what it is |
| --- | --- |
| `useRendererShell.js` | The hook. Per-file state through the host, the Display settings store and what Display's card shows (the frame's `displayMode`, `projection`, `grid` and `background`), tool modes (Draw, over its `pencil` and `shapes` modes, is the strip tool the shell itself owns, `shell.tools.drawing`; Display, Preview and its controls are the frame's; `toolModes` is omitted altogether by a renderer with no tools of its own), the tool stack's layout (a viewer preference: `services.preferences.toolStack` — the resizable panels' sizes, the folded stack panels — changed by one patch per gesture, `frame.changeToolStack`; the view's panel is the file's, `filePanel.js`), prompt snapshots (the host's `captureRequest`), the clipboard screenshot (the drawing tools' Copy), what Quick Edit takes from the view (its file, how a copied prompt spells a path, the view as a picture, the viewer's Escape), the one Preview state (`shell.previewing` / `setPreviewing`, from `usePreviewState`; every way in and out goes through `setPreviewing`, which mounts Preview's view or takes it away and touches nothing of the editor's), Preview's scene (`frame.previewDesiredScene`: `previewViewScene(store.renderScene())`, Render over the file's settings as Preview draws them) and its viewport (`frame.previewViewRef`), Preview's Orbit (`shell.orbiting`, transient, off at every entry and exit), Render's studio code and environment prepared 600 ms after the model is on screen at Preview's quality, into the GPU device's cache Preview draws from (`previewPrepare`; it changes nothing the editor draws; not on a software renderer, the viewport's `softwareRendering`, where Preview prepares as it is entered), alerts, shortcuts, and the live command surface (`setCamera`, `capture` and `resetCamera` act on the view on screen: Preview's while it is open). It owns no zoom control: the shell has none. |
| `ViewFrame.jsx` | The ONE frame every renderer mounts, 2D or 3D, the canvas (`children`) the only difference: the root (`data-slot="cad-file-view"`, `data-cad-surface`, the renderer's `surface` attributes; a press on a canvas focuses it), the view's one panel docked at the left (`FlatPanel`, `useFlatPanelState`, `sidebars.js`: its tabs or a 3D view's sections, each a tab; always pushing, collapsed on its own where it would leave the model under 640px (872px with the 232px panel); a phone's a sheet under the navbar, over the strip and the view, sliding, with no dimming; hidden, still mounted, in Preview; its toggle the navbar's, `usePanelToggles`), the stage (`data-cad-canvas`, the canvas's colour where a 3D view has one), the strip's column at the top centre of the WHOLE view (`data-cad-tool-groups`: the strip, the tool's row, the update status, the tool stack; in the top layer over the panel, `data-view-top-layer`, centred on the window, so no panel moves it), ONE measure of that column onto the root (`--cad-tools-bottom`, `--cad-top-right-left`, `--cad-corner-below`: the corner's bottom, which the notice stands under, again as the notice or the corner comes or goes; Quick Edit's bar centred on the window (on the model's area where it would stand over a pinned panel), 400px at most, its top's distance off the bottom `--cad-quick-edit-reserve`, `--cad-quick-edit-left` and `--cad-quick-edit-width`), the corner slot (the top-right), the column under it (`ViewportTopRight`: the host's notice), Quick Edit's bar at the bottom, a bottom-centre slot (Preview's playbar), the renderer's `underlay` and `overlays`, the status at the top centre when there is no strip, the view's menu over a canvas it is handed, loading and the alert card, and what is picked (`inspect`, `inspector/inspect.js`: the view's ONE description of each pick — a Quick Edit chip list's row, its kind and key facts, the one place a pick is read in detail, the panel holding only its lists; the hover tip over the canvas under Select, `HoverTip.jsx`'s `useFrameHoverTip`; the view's name for its marks, `InspectContext`); `preview` (`PreviewChrome`'s props) wraps exactly the strip's column, the top-right and the corner. `FlatViewFrame.jsx` (a flat view's strip, status, corner and Quick Edit) and `RendererShell.jsx` mount it, and nothing else draws its parts: `scripts/test/check-kit-boundaries.mjs` fails a renderer source other than it that renders `ViewportTopRight`, `ViewerAlertCard`, `ViewerLoadingOverlay`, `HoverTip` or `data-cad-tool-groups`, or calls `usePanelToggles` or `useFlatPanelState`, and `RendererShell.browser.test.mjs` holds the frame's contract over a 3D view and a flat one (the strip at the view's centre as the panel opens and shuts, the picture filling what the panel leaves, a phone's panel a sheet and its Display the desktop's card). |
| `RendererShell.jsx` | A 3D view's frame, mounted on `ViewFrame.jsx` (above), which places every part named here but the viewport, Preview's view and cover, Preview's playbar: viewport box; one centred column at the top centre (`TOOLBAR_POSITION`, `data-cad-tool-groups`) holding the tool strip (the renderer's tools); in the file's navbar Display (`DisplaySettings.jsx`: a toggle whose card — Projection | Style, Background, Show grid, and Reset — docks under the navbar at the view's right edge, `ViewFrame.jsx`'s `card`) then Preview portalled into its right end (`NavbarViewControls.jsx`, the same on a phone); the cube alone at the top-right; under it the tool in hand's sub-toolbar (the drawing tool's `AnnotationToolbar` while Draw is up, else the renderer's `subToolbar`: Measure's chips), the update status, and the tool stack (`ToolStack`: the renderer's `toolPanels`; the column stops clear of Quick Edit's bar, `VIEWPORT_STACK_BOTTOM` or the bar's measured top where that is higher); the panel (`FlatPanel` over the renderer's `sidebar`, its structure, then its `fileSections` — Params, Joints — and the Animation (none where the Joints tab takes the motion, `jointsHoldMotion`), each a tab, one state with the flat views', `useFlatPanelState`), always pushing the model aside (`sidebars.js`), the picture drawn in what it leaves; collapsed, nothing over the model; the strip and Quick Edit's bar centred on the window over it; a phone's a sheet from the left behind the navbar's toggle; the view cube in the top-right corner (the viewport's), its row under it; Preview's bar in the navbar's place (`PreviewChrome`, `data-preview-bar`: the file's name, then Preview's Display, a toggle whose card docks under the bar at the view's right edge, sliding in, `panel` (`PreviewSettings.jsx`, a settings card: Orbit and its speed, then Preview's own Render sections, `frame.previewSettings`), then Exit preview, an X; it fades with the playbar while the pointer rests, `usePreviewIdle` — no panel (hidden, a tree keeping its state), and for a file with routines Preview's own playbar under the model, `PreviewPlaybar.jsx`, fading with the bar); Preview's view (`PreviewView.jsx`, `data-preview-view`), mounted over the editor's viewport box while `shell.previewing` and unmounted as it closes, the editor's viewport `suspended` under it; the cover that answers the press ("Preparing preview…", `data-preview-cover`) until Preview's view has presented its first frame (`onPresented`), the published mesh is complete (`previewView.complete`) and its picture has converged (`pictureProgress`) — lifting at once on a view the shell set moving (Orbit, a routine playing), never on a picture that a component publication started again (`previewCover.js`); at five seconds it stops waiting for more components and lifts on the picture converged, a second later at the latest, with no cover on the way out; for a file with routines the panel's Animation tab (`AnimationSection.jsx`, after the renderer's tabs; a mechanism's motion the top of its Joints tab instead; no playbar in the tools view), Preview's playbar in Preview, and the file's chosen Speed and Loop applied to its routine; the loading overlay; and the alert card. While the model loads, and once a load has failed in a way the model did not survive (an alert that cannot be put away), it draws none of its controls: only the load, or the card saying why, with the update status at the top centre in the strip's row; in a compact host (`appearance.compact`), none at all: the model alone. Nothing sits at the bottom centre at rest. It takes `studio`, the renderer's own Preview while it is open: `{ scene, overlay(viewport, drawn), animation, runtimeLifecycle, onCameraSettled }` — the scene Preview draws, built by the family's own builder over the editor's geometry, what drives it from inside Preview's viewport (handed the Render scene it draws), Preview's routine (the playbar's in Preview, at rest on entry), and Preview viewport's lifecycle and settle. It takes `references` (what is selected, in the prompt grammar: what Quick Edit attaches and counts), `referenceChips` (how Quick Edit shows them) and `copySelection` (what ⌘C / Ctrl+C copies while the renderer's own tool is up and something is selected; null when nothing is), and, under Select, `onSelectPress`, `onSelectHover` and `selectsAnnotations` (whether Select's filter picks the annotations), and `inkTouches` (what the model is under a point of the view, `(clientX, clientY) => [{ part, ref? }]`: what the drawing tools record a mark as touching). One DOM structure (`data-slot="cad-file-view"`, `data-cad-surface`, `data-cad-canvas`, `data-cad-toolbar`, `data-cad-sub-toolbar`, `data-flat-panel`, `data-cad-tool-stack`, `data-tool-panel`) for every renderer. `frameProvider` wraps the WHOLE frame in the renderer's own context — the panel and the tool stack as well as the viewport, because they read it — and `onCanvasPointerDown` is a press that landed on the model, for a renderer with something to put down when the person reaches for it. The frame focuses itself on such a press either way. |
| `ShellViewport.jsx` | The three.js viewport around ONE kit scene: `useViewerRuntime`, `useViewportCamera`, the look (rig or studio, environment, background, floor, grid, axes), the drawing tools' surface and the annotations' ink in the model, the view cube (top-right, `VIEWPORT_CUBE_TOP`; not mounted in Preview's viewport, while the model loads, or when the shell says so, `viewCube`), frame presentation and the queued view-settings handshake. Its children may be a function of the viewport (`{ runtimeRef, hostRef, mountRef, viewerReadyTick, commitScene, syncSceneBounds }`), which is how a renderer mounts its own overlay or pointer pick. A scene that changes IN PLACE (it arrives in pieces, swaps its detail, is rebuilt under one identity) calls `commitScene()` from its own effect: the viewport re-reads what it placed, fits the stage and the depth range and applies the framing rules THEN, because a child's effects run before the viewport's own adoption effect. The one thing a commit never does ahead of the viewport is FRAME under a camera that is about to change: when the same render also changed the lens, the projection or the viewing mode, the stage is adopted at once and the framing follows once the camera has been given those props (a stored camera applied under the old projection and then converted comes out about a sixth smaller). A scene is framed once, on its `restBounds`. A scene that says `complete: false` (one still arriving) is framed on what has arrived and once more when it is whole, unless the camera on screen is by then the person's: one they dragged, wheeled, turned by keys or the cube, zoomed to a selection or set through `setCamera` during the current mount, or one a reload restored from the file's view. A rebuild of the open file is not a reframe: it keeps a camera the person took exactly, and fits again, animated as Zoom to fit does, only a camera still untouched since the page opened or the last fit, and only when the rebuild changed the rest box (`camera/cameraTouch.js`; a reload's restored view counts as touched). A file shown again in the page that left it opens on the camera it was left at, restored as a reload restores the file on screen's (the page keeps the view of each file it left, `tab-store`'s `files.retain`); a file the page has not shown starts with fresh framing. `studio` makes it Preview's viewport (opened at rest, framed afresh from the default direction, keeping no camera, no cube and no drawing tools; `orbit` turns the camera at `orbitSpeed`); `suspended` makes it draw nothing while another view covers it, and draws a frame asked of it meanwhile synchronously, before paint, as it is uncovered (`runtime.setSuspended`). `preserveInteractionPixelRatio` keeps the idle pixel ratio while the camera moves (a scene drawn with hairlines, and Preview's orbit), and `runtimeLifecycle` (`onRelease(runtime, { handoff })` while the WebGL renderer is still alive, `onContextLost()`, `onInitializationError(error)`) is for a renderer that hangs its own objects or in-flight work on the runtime. `syncSceneBounds()` re-fits lighting, shadows and the floor's height to a scene that moved its own bounds, with no React render and no reframe; a sync that finds the bounds (and every setting the fit reads) as they were refits nothing and keeps the shadow maps (`look/stageFollow.js`). What is SIZED stays sized from the rest placement, in Inspect and in Render alike: the grid and stage (`sceneRadiusForBounds` on `restBounds`) and the Render studio's floor plane (`applyPhotographicStudio`'s `groundBounds`), so a pose or a playing routine never rescales or slides the ground under the model; `zoomToBounds(bounds)` frames part of the scene. Read-only test seams, the view on screen's (Preview's while it is open, the editor's again as it closes): `window.__cadCamera()` (the live camera, its depth range included, and `settling`: true while a gesture, a camera transition, a held orbit key, Preview's orbit or the controls' damping still moves it, so a test waits on the camera at rest and not on its coordinates holding still) and `window.__cadStage()` (the ground's radius, the bounds the stage is fitted to, the floor's height, the studio floor's size and centre). |
| `PreviewView.jsx` | Preview's view: a `ShellViewport` of its own (`preview`, `orbit`, `orbitSpeed`), with its own view-update coordinator over `frame.previewDesiredScene`, drawing the renderer's `studio.scene` and mounting `studio.overlay(viewport, drawn)` inside it. Its canvas, scene, camera and look are its own; only the GPU device is shared with the editor's, which it never reaches. `onPresented` says when its first frame is on screen. |
| `usePreviewScene.js` | Preview's scene for a family whose core scene has `createSibling()` (GLB, mesh, robot, engine document): the editor's scene's sibling, made as Preview opens and disposed as it closes, before the scene it shares geometry with. |
| `usePreviewFrame.jsx` | Preview's frame, the same for every view that has Preview, over the one `previewing` state its caller holds: entering under the cover and leaving, the cover's lift (`previewCover.js`: presented, `view.complete`, the picture converged, or the cap), a new file leaving Preview, the host's navbar stepping aside (`onPreviewChange`), Preview's bar and settings panel (`PreviewChrome`'s props; the chrome's idle store, `usePreviewIdle`), Preview's view as the frame's underlay (`View`: `PreviewView.jsx`, or a view's own around it) and the Preview button (the navbar's, and the strip's entry). `RendererShell.jsx` calls it for a 3D view and `useFlatPreview.jsx` for a flat one; it returns `ViewFrame`'s props (`previewing`, `preview`, `underlay`, `overlays`). |
| `useFlatPreview.jsx` | Preview for a view outside the shell (a flat view whose picture can be shown in 3D, lit: a board): what `useRendererShell.js` holds of Preview, under the same rules — the `previewing` state (`usePreviewState.js`), Orbit (off at every entry and exit), Preview's settings in a view settings store of their own and the scene Preview draws from them (`previewViewScene.js`), Orbit's speed, what the file's view keeps of them (`preview`, `playback`), Preview's viewport's handle — handed to `usePreviewFrame.jsx`. The view brings Preview's own view component (lazy, where its 3D code loads) and what it draws. Nothing is prepared ahead: there is no viewport until Preview is entered. `FlatViewFrame.jsx` takes its result as `preview`; `useFlatView.js`'s `useFlatHandover` takes `previewing` and `leavePreview` for the keys. |
| `fileView.js` | The file's view `{ version, camera, display, preview, playback, renderer }`, read forgivingly and written exactly: the camera (restored in place of the open-time fit; null fits), the Display settings, Preview's Render settings (`preview`), the playback settings (`tools/playbar/playbackPreferences.js`), and the renderer's own slices, each `{ signature, value }` and restored only under the signature the renderer declares now (`readFileView(raw, signatures)`); the camera, the display, the preview and the playback are always kept. The host keys it `[file path, renderer id]` in the tab store, which keeps it for the file on screen alone. Not in it: the tool in hand, a selection, measurements, ink, Preview, a routine's time — every open starts those afresh. |
| `liveBinding.ts` | `attachLiveBinding`: the live command surface. Base commands (`readState`, `setCamera`, `resetCamera`, `setDisplaySettings`, `capture`, `thumbnail`) mean the same for every renderer; a renderer ADDS commands by name and DECLINES the known host commands (`HOST_LIVE_COMMANDS`) that make no sense for it with the sentence the caller reads. Binding fails when a renderer does neither. |
| `promptContext.js` | `createViewPromptContext` (a snapshot and what it depicts) and `promptDeliveryError`. A renderer with a reference vocabulary of its own passes `promptContext` instead, and may then return that vocabulary from `promptReferences`. |
| `loadReport.js` | `shellLoadReport`: what the shell asks the status kit about one document load, as one pure function, and all it returns is the loading presentation over the viewport. A renderer whose document is a plain download passes `load` and nothing more. One whose document can be EDITED or PREVIEWED while it is open knows more than the shell can: `load.editPending` (queued work of the person's own, with nothing of it on screen), `load.currentPreview` (that work IS what is drawn, so the wait is over even though the write is not) and `load.finding` (the file is not even located yet). An alert is `load.alert`, which the frame draws as the alert card (`ViewerAlertCard`: every alert; one the model survives, a warning beside it included, can be dismissed). |
| `useViewerShortcuts.js` | Which mounted viewer an Escape or a ⌘C / Ctrl+C belongs to (focus inside it, or the page after a press inside it); the renderer says what Escape means, and a copy is the active tool's (the drawing tools' view with its annotations, else the selection's references, `copySelection`). The order is [the viewer's](viewer-ux.md#keyboard). |
| `viewportLayout.js` | The chrome's geometry: its inset from the viewer's edges (`VIEWPORT_INSET_PX`, 8px), the strip's row (`VIEWPORT_TOP_BAR_PX`, 48px, which the status takes where there is no strip; the bar itself `STRIP_BAR_PX`, 40px), the cube's size and place (`VIEWPORT_CUBE_SIZE`, 6rem; top-right, 2px from the right, `VIEWPORT_CORNER_INSET_PX`, and `VIEWPORT_CUBE_TOP`, 8px off the top as the strip is, plus `--cad-viewport-corner-top`, which a host whose control floats over that corner sets to lower it clear), the tool column's bottom (`VIEWPORT_STACK_BOTTOM`: clear of Quick Edit's row), and where a flat view's zoom stands (`viewCornerLayout(side)`'s `pill`: its outer edge the corner's inset from the edge, `chromeInset.js`'s `CORNER_INSET_PX`, its middle on the strip's, `STRIP_BAR_PX`, at the top-right, or mirrored at the top-left where the host sets `--cad-viewport-corner-left`; the frame reads the side, `ViewCorner.jsx`'s `viewCornerSide`, and says it to the corner, `ViewCornerSideProvider`). |
| `ViewCorner.jsx` | The view's corner at the top-right (the bottom row is Quick Edit's), the camera's own control alone: a 3D view's cube (the viewport's) or a flat view's "100%" zoom dropdown (`ZoomControl.jsx`); the side the host anchors the corner at (`viewCornerSide`, `ViewCornerSideProvider`, `useViewCornerSide`: the zoom's menu opens away from it). Its places are `viewportLayout.js`'s ([the tool strip and the corner](viewer-ux.md#the-tool-strip-and-the-corner)). |
| `TextGlyph.jsx` | A word as an icon, two or three characters (a board's 2D/3D: **2D**, **3D**), where the word is clearer than a picture: an `svg` on Lucide's 24-unit grid, so a strip tile and a More row size it as they size a Lucide icon, the word semibold, its figures tabular, tightly spaced, centred by its capitals, in `currentColor` and `aria-hidden`. `textGlyphIcon(text)` makes one the `Icon` a menu option or a More row takes. |
| `useStageViewport.js` | A `ShellViewport` outside the shell: the applied view settings as its props (`useStageView`, Preview's view's too) and the projection's control (`projectionControl`, the shell's too); `useStageViewport`, a flat view's picture shown in 3D: its own settings, no grid or floor, its stage's background the flat canvas's colour. |
| `DoubleClickFit.jsx` | A double-click on nothing under Select fits: every 3D view's. Under Select only, by the rule a flat view's canvas keeps too (`viewport/dom.js`'s `doubleClickFits`: the frame's root says Select is in hand, `ViewFrame.jsx`'s `selecting`). |
| `ViewportContextMenu.jsx` | The viewport's menu on a secondary TAP (a secondary drag pans; primary and secondary together is the pan chord). The gesture, the anchor, the clamping and the dismissal are the shell's; the ITEMS are the renderer's (`contextMenuItems(press)`), asked at the moment of the press, and `onContextMenuOpenChange(open)` says while the menu is up. Every view passes its items, built from one set of groups (`viewMenu.js`, below); a flat view hands its own canvas (`canvasRef`) and pane in place of a 3D runtime. |
| `viewMenu.js` | The entries of every view's menu, in one order: the reference (Copy Reference), the pick (Select or Deselect, Isolate, Exit all isolates), what is shown (Hide others, Show all, Hide or Reveal), the view's own (a tree's Expand and Collapse, a schematic's sheets, a drawing's layers, a board's Flip), and last the framing (Zoom to fit; Zoom to selection, off with nothing picked). Over something, the menu opens with its reference; over empty space it is the view as a whole and the framing. `menuGroups` joins the groups with a rule between them. A 3D scene's is `kit/tools/select/sceneMenu.js`'s (`scene.selectionBounds` for Zoom to selection). |

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
// Renderer-facing, beside `tools`, `toolMode`, `selectTool`, `previewing`, `requestRender`:
shell.requestFrame();            // a frame that keeps the shadow maps: a highlight moves and reshapes no caster
shell.syncSceneBounds();         // the scene moved its bounds (a pose): the stage follows, no render
shell.scheduleStateSave();       // a slice changed: write the view soon, and on unmount
shell.playback; shell.setPlayback(patch); // the file's: Orbit's speed, the chosen Speed and Loop
shell.orbiting; shell.setOrbiting(on);   // Preview's Orbit, transient: off at every entry and exit
// The shell adds Display (its card: Projection, Style, Background, Show grid) and Preview (a `previewable` view's: the
// navbar's, or ending the strip), Preview's frame (`usePreviewFrame.jsx`: its cover, its bar — the file's name, Preview
// settings, Exit preview — and its view), for a file with routines the Animation tab (a mechanism's motion: the top of
// its Joints tab) and Preview's playbar, and the sub-toolbar of its own tool (the drawing tools').
const tools = [shell.tools.own({ id, label, icon, menu }), ...shell.tools.drawing].filter(Boolean); // []: no tools, and no strip
// subToolbar: the renderer's tool in hand's row; sidebar: the file's sections, each a ToolPanel, a tab each of the view's panel
return <RendererShell shell={shell} tools={tools} subToolbar={toolRow} sidebar={<>{treeSection}{positionSection}</>}
  viewportOverlay={viewport => <PointerPick viewport={viewport} scene={scene} enabled={selecting} onPick={pick} onHover={hover} />} />;
```

A CAD renderer's controls are the shell's chrome: its `tools` on the strip, the tool in
hand's `subToolbar` (`kit/tools/SubToolbar.jsx`) under it, and its `sidebar`, the file's
sections in the view's panel docked at the left (`kit/shell/FlatPanel.jsx`, a board's and a
drawing's too), each a `ToolPanel` drawn as a tab by its name, whatever the tool: an engine
document's Model, Params and Joints, a robot's Links and Joints. A section draws
no heading in its tab and pads nothing: the panel's body stands its rows on the panel's lines
([the panel inset](design-system.md#spacing-and-the-panel-inset)); the panel's one search searches the trees. The
panel's width, whether the person opened or closed it and the tab shown are the file's, kept in its view for the
session (`file-viewer/filePanel.js`; the tool stack's old shared `panels.flat`, `collapsed.flat` and `tabs` are read
once, as a file's start, then dropped). A tree is there under every tool (out of sight only in Preview, kept mounted with
its state); a pick scrolls its row into view there. A renderer may also hand `toolPanels`, the tool stack under the strip and
sub-toolbar, each panel its content's height, with `fit` saying how it gives way on a short
viewer: `"tree"` first (to 128px or its content), then `"details"` together, each in
proportion to its height (to 96px or its content), never `"fixed"`; the column scrolls only
if the rest still does not fit. Every panel is `TOOL_PANEL_WIDTH` wide (164px); `resizable` makes a panel the person's to size on its own, from the grip in its
bottom-right corner alone, kept under its `id`. The engine document's and the robot renderer hand none.

A board is a flat view with two canvases in one frame (`ViewFrame.jsx`, through `FlatViewFrame.jsx`): the flat canvas
(`board/useBoardView.js`) and, under 2D/3D, the board in 3D (`board/Board3dView.jsx`, a lazy
chunk, so a board in 2D loads no three.js): a `ShellViewport` (its settings through
`useStageViewport.js`) around core's bare board (`@cad/core/lib/board3d/`: `boardStage.js`, a slab cut
to the outline, and round it, at each face's height, a see-through surround with what the file draws
past the outline; `boardFaces.js`, its two faces the 2D drawer's own `drawPlot` of each side (a board made in its
stack-up's colours, in Board mode: `drawPlot`'s `finish`, the side as it is made) over the
face's box (`faceBox`: the outline's box and what lies past it, symmetric about the sheet's centre line,
at most half the sheet farther) and an overlay of `drawBoardOverlay` and the ink, drawn through one scratch canvas per kind into textures
overwritten in place, at most 8 megapixels a face (a quarter of it on software WebGL) and 2 an
overlay, freed when 3D is left; `boardFrame.js`, the sheet to the world and back). The frame, the
strip, the panel, the selection (`useSceneSelection` over the board's one scene), the tools'
sessions and Quick Edit never unmount: the board view hands the active canvas's half — where a pane
point lands on the board and how far a pick reaches, Measure's camera, the drawing tools' surface
(`board/board3dAnnotation.js`), the framing, the zoom (`ZoomControl.jsx`'s `viewportZoom` in 3D)
and the capture — to the same handlers. The view's controls (Display's card's Side, Mode, Style and Background, `BoardDisplay.jsx`'s
`boardViewGroups`) are the same in both, the card adding Projection in 3D, and the corner is the flat
view's: its zoom, whose zoom in 3D is `viewportZoom` over the 3D
viewport, made again once that viewport is up so the pill hears its camera; the 3D viewport draws no cube
(`viewCube={false}`). A tap and the
pointer resting go
through the 3D views' `usePointerPick`, handed the pointer alone: the board view picks once a frame
(the bodies, each baked geometry with its accelerator, `viewer/raycastBvh.js`, then the face); a drag
turns the view. Its faces' bytes are put on screen as
drawn (no sRGB decode and encode), so they match the flat canvas's colours. The switch shows nothing but
the board: entering, the 3D viewport mounts see-through and deaf to the pointer over the flat canvas, its
stage `presentable` (the frame presentation, `viewport/framePresentation.js`, keeps a new canvas covered
until its scene says so) only once the face its camera sees is drawn, and the board view swaps the two
canvases in one commit when that frame is up, head on (in perspective, its eye where the face is drawn
at the flat scale for the viewport's lens, `boardFrame.js`'s `perspectiveHeadOn`); then the camera
eases to a camera on the side the 2D view showed (`boardFrame.js`'s `cameraOnSide`, the opening's
`side`): the camera the file was left at in 3D, turned over to that side when it looks at the other, or
Home's direction so turned, handed to the viewport's `goHome`, so the ease never crosses the board's plane.
Leaving, the flat canvas paints its own window again (`usePlotView`'s `settle`) under the 3D viewport,
which then goes: the window it held all the while 3D was up, as the 2D view was left (a file reopened in
3D: the window it was left at in 2D, or the fit), whatever the 3D camera did, as KiCad's 3D viewer, a
window of its own, never moves the PCB editor's view. Each mode keeps its own last view: entering eases
to the 3D camera, leaving gives back the 2D window. Only the side carries over, both ways: Flip's icon is
one state, the camera's side in 3D. The camera's window (`boardFrame.js`'s `planFromCamera`) is what a
prompt's view of the board in 3D is, and nothing leaving frames.

The board's parts stand on it (`@cad/core/lib/board3d/boardParts.js`, placed by `partPlacement.js`): the
board's models table (`board/useBoardModels.js`, `GET …/kicad_pcb/<id>/models`, asked on every revision
and when the window takes the focus back, in 2D too, for a part's card's fact and the Parts' No 3D
model block) names each model a STEP by its document id; the 3D view opens each by that id
(`client.engineDocument`), four at a time, reads it (`loadXbfDocument`, no look, no version wait: the
engine may let it go), bakes it into ONE geometry with a material per colour, and shares it with every
placement of it, at the placement's own opacity (KiCad's per-model `opacity`: see-through below 1); a placement is diffed by reference on every revision (a moved part a matrix, a model
held never asked for again), and a model no placement uses is released, and loaded again if a
placement wants it back (a part deleted and put back, a model hidden and shown). A named model that is missing
is a see-through block on the part's outline, a millimetre tall. A press tries the bodies before the
face (the board's `pickAt` and the stage's `pickBody`), as the filter's Footprints takes them; the
highlight and an isolation light and fade them (`bodyInk`); the Layers tab's 3D models hides them. Zoom to fit and the opening's ease (`goHome`) frame the slab with
the bodies and blocks shown on it at that moment (the stage's `shownBounds`), while its `bounds` stay
the slab's (what 100% means): a body arriving moves no camera, and the next fit takes it in. The
canvas element says what it holds: `data-board-bodies`, `-blocks`, `-models`, `-mesh-mb`,
`-models-waiting`, `-models-failed`.

A board has Preview (`kit/shell/useFlatPreview.jsx`, through `FlatViewFrame.jsx`'s `preview`), where it has the layers to
be shown in 3D: the frame's Preview is every view's (`usePreviewFrame.jsx`), and what it draws is the board's own
(`board/BoardPreviewView.jsx`, a lazy chunk mounted only while Preview is up): `PreviewView.jsx` around a scene built
as Preview opens, from the plot, the parts and the models table — core's stage in its `lit` form (`boardStage.js`'s
`lit`: the two faces `MeshStandardMaterial`s whose `map` is the 2D drawer's picture, sRGB, both wanted from the start;
the slab casting; no overlay and no surround) and its parts (`boardParts.js`'s `shadows` and `blocks: false`: the
bodies casting, no block for a missing model), with a model loader of its own. Its scene's `bounds` are the slab with
the bodies on it as they stand (`shownBounds`), `complete: false` while models are still wanted, each arrival adopted
in place (`viewport.commitScene()`, once a frame) and said to the frame (`view.onComplete`, the cover's
`view.complete`); it takes shadows on every surface (`setShadowReception`) and wears no surface look, so Preview's
settings leave Part colours out. It draws `BOARD_DISPLAY_DEFAULTS` in the viewport's theme, whatever the Layers tab
shows; the 3D models eye alone carries over. The working view stays mounted under it and is never told: the flat
canvas is `suspended` (`useFlatCanvasView`'s: its size, view and fit held while the page's chrome goes and comes back
round it, so it is uncovered exactly as it was left), the board in 3D's viewport `suspended` as a 3D file's editor
is, both out of sight (Preview's Background may be see-through), and the flat views' keys are Preview's
(`useFlatHandover`'s `previewing`). A live `capture` and `resetCamera` act on the view on screen, Preview's while it
is up. Preview's settings and Orbit's speed are written with the file's view (`preview`, `playback`).

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
scene hook, its tool list, its tools' rows and its panel's sections, if it has any
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

`createDxfRenderer` (`@cad/ui/renderers/dxf`, id `dxf`) shows a `.dxf`.

It is **not on the shell**, and that is the whole design: a DXF is a finished 2D
document, so the pane is a canvas and the drawing is painted on it. No three.js
viewport, no scene, no Preview, and no Display settings of its own: its Display card is the viewport's Background
alone. The questions the old
Material/Bends tabs answered were about a sheet-metal part the viewer was inventing
from the file; a drawing is not that. What it has is what a person needs to talk about
a drawing — every view's one frame (`kit/shell/ViewFrame.jsx`) and the flat views' hooks around its canvas, a board's and a schematic's
(`kit/shell/FlatViewFrame.jsx`, `useFlatTools`, `flatViewTools` and `useFlatHandover`): the strip
at the top centre, the tool's row under it, the view's panel docked at the left (`kit/shell/FlatPanel.jsx`,
where the drawing has a Layers tab, kind `drawing`), Quick Edit's bar at the bottom, the zoom in the corner.

- **Tools** (`dxf/tools.js`): **Select** (in hand: a tap picks, a plain drag draws the box,
  every viewer's, below), **Draw** and **Measure**, and no view controls on the strip: the navbar's Display
  opens its card, the Background alone (no rule, no Reset); Projection and Preview are a 3D view's. Select picks, front to back, a measurement, then ink, then
  the drawing's ENTITY under the pointer (`drawing2d/entities.js`'s `entityAt`: within
  6 px, a fingertip's 16; the lines over a hatch before the hatch; nothing on a hidden
  layer); Shift adds, as a finger's tap on something does. Its box (`useFlatBoxSelect`) takes the entities it touches
  (`entitiesInBox`, over each entity's drawn line-work, points,
  regions and words, on the layers shown), with the ink and the measurements (`boxTake.js`'s
  `takeFlatBox`). Its selection is the kit's (`useSceneSelection`,
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
- **Layers**, the panel's one tab, on every drawing once it is read (`layersSectionShown`): a drawing of
  one layer has its one row. Each layer's pen, name, entity count and eye (hidden: not drawn, picked or snapped
  to), and under it the block references placed on it, a level down, a click picking one — the Model
  tree's rows, one glyph slot each: the pen in a layer's slot, or its chevron where blocks hang under it
  (the pen then after its name); the panel's search
  ("Search the drawing") keeps the layers whose names match, and the blocks whose names do, each
  layer's chevron folding its hits while the search is up (folds of the search's own, `searchFolded`,
  dropped as it is cleared: [the rule](viewer-ux.md#trees)). The
  panel docking or going leaves a view the person framed where it was (`useDrawingView.js`).
- **Quick Edit** carries the picks and the ink; its views are the window on screen as a
  plan-view camera (`planCamera`: looking straight down, `up` +Y, `orthographicHalfHeight` the
  window's half height), each with its label, which the ink's marks name. `cad <type> snapshot --job
  PACKET` draws each view's window with the ink on the sheet, and `--annotation PACKET
  --camera authored` the view the ink was last drawn in. Quick Edit puts no measurement in its
  packet: they are the person's.

- **The picture comes from the BACKEND.** `client.drawing(file)` is the DXF document's
  `drawing` (`GET /api/v1/documents/dxf/<id>/drawing`, `apps/web/docs/backend.md`), asked again while the server
  renders a drawing it has not drawn before: ezdxf flattens the modelspace on the
  server, in a kernel process — text placed, dimensions exploded, hatches filled, blocks placed — and the
  client receives five primitive shapes and `text` in DXF coordinates, y up. **This
  renderer never parses DXF.** The payload is cached server-side by the document's
  content hash, so reopening a file costs a round trip and nothing else.
- **Drawing is core's** (`@cad/core/lib/drawing2d`), which the OCCT parity bench's page
  paints a drawing with too: `fitTransform` / `zoomTransform`
  / `panTransform` (one uniform scale and a translation; the y flip lives in the
  transform, not in the geometry), `prepareDrawing(payload)` (paths built ONCE, per
  colour for strokes and per primitive for fills; text kept as strings) and
  `drawDrawing(ctx, drawable, …)` (text set with `fillText`, stretched to the width the
  server measured, so the page's face keeps the drawing's layout).
  `cad <type> snapshot` draws a drawing by OCCT in the engine (`engine/render/drawing.py`) as
  this pane draws it: from above, fitted, hairlines in their pens, on the light theme's paper
  whatever the pane's theme (every snapshot is light), with the plan-view `camera` and the
  `annotation` on the sheet a Quick Edit's view carries.
- **Hairlines, always.** Strokes are 1.25 CSS px at every zoom, as AutoCAD draws with
  LWDISPLAY off: paths are in MODEL space and the context carries the view, so one
  `lineWidth = 1.25 / scale` per frame rebuilds no geometry. Model-space lineweights
  are not displayed at all.
- **`color: null` is the default pen** (ACI 7, "whatever contrasts with the
  background"), resolved at DRAW time against `--foreground` on the
  canvas, `--canvas` — what every view's content is drawn on — in the viewport's scheme, the person's
  Background (the frame scopes the canvas box to it), never the app's theme. One payload therefore
  serves both: switching the Background repaints, it does not refetch. The tokens are
  read off the pane, and a change of the scheme, or a mutation on `<html>`, schedules a frame. When they cannot be
  read the pair comes from `@cad/core/lib/appTheme.js`, the one place the app's colours
  are written down; the snapshot bundle, which has no stylesheet at all, paints its stills
  on that file's `background`, not the canvas.
- **Fills are even-odd, and each one is filled on its own.** A `filled-paths`
  primitive's inner rings are its holes; merging two overlapping regions of one colour
  into a single path would turn their overlap into a hole as well. Fills go down
  before strokes, which is the one ordering that never hides an edge.
- **Interaction** (`dxf/useDrawingView.js`, every flat view's `kit/viewport/useFlatCanvasView.js`
  under the drawing's paint): fit on open and on resize until the person moves the view, with a board's
  and a schematic's margin (`fitBoardBounds`: 6% of the pane's shorter side, at least 16px), drag to
  pan (a primary press, one finger, once it has travelled more than a tap's 4 px, unless Select's box
  has the press: `controls.enabled`, which `useFlatBoxSelect` turns off for it as Box select turns
  OrbitControls off; a press that lets go before is the tool's tap), the 3D views' pans too (the right or middle button's drag, a drag
  with Ctrl, Cmd or Shift), a mouse's wheel or a pinch to zoom about the pointer and a trackpad's
  two-finger scroll to pan, double-click to fit again (dropping first a tap that waits for it: one that would take
  something out of the selection, `takesAway`, waits the double-click window), and a right-click for the view's menu (an
  entity's reference, Select, Hide its layer; Show all layers; the framing). The view lives in a REF and the
  canvas repaints through one `requestAnimationFrame` when something changed; a pan
  never re-renders the component tree. A resize paints at once, inside the pane's
  ResizeObserver (after layout, before paint): resizing the canvas wipes it, and a frame
  asked for there would leave the pane empty for one frame
  (`dxf/DxfResize.browser.test.mjs`). The backing store is DPR-aware
  (`kit/viewport/pixelRatio.js`). What the tools draw (highlights, ink) is painted in
  the same frame, after the drawing, so a capture holds it.
- **Navbar**: the drawing's Display, its card the Background alone; no zoom buttons: zooming a drawing is
  the pointer's (wheel or pinch about it, drag to pan, double-click to fit), and the corner's "100%" zoom holds
  the zoom's commands. The host's
  `captureRequest` is the canvas as a PNG, background included, delivered through
  `host.promptContext`.
- **Empty and failed drawings.** `bounds: null` (nothing in the modelspace) is a quiet
  sentence over the empty pane, not an error. A non-200 becomes the ordinary actionable
  alert card (`ViewerAlertCard`) carrying the SERVER's sentence (`failureAlert`,
  `kind: "http"`); a payload from
  a server that disagrees about `schemaVersion` gets its own alert whose recovery is to
  reload the page, or restart the app that shows it.
- **Host commands**: `resetCamera` fits the drawing again, `capture` hands over the
  PNG, `clearSelection` lets go of the picks, and `readState` reports `camera: null`,
  an empty `display`, the selection as references and `selectedEntities` (handles).
  There is no zoom command and no zoom percentage: no host ever sent one. `select`,
  `setCamera` and `setDisplaySettings` are each declined with a sentence that says why;
  a `selectReference` host request is consumed without changing the view.
- **State** under `[path, "dxf"]`: the drawing's `camera`, every flat view's record
  (`kit/viewport/flatView.js`): `{ scale, offsetX, offsetY, width, height }`, the transform and the pane
  it was framed in, and only once the person has MOVED the view — an untouched drawing stores nothing, so it
  reopens fitted to whatever pane it lands in. A stored view is placed on the pane the drawing opens in by
  what it shows (`carryTransform`), so on a pane of the size it was framed in (a reload with the panel
  open, though the canvas is the whole view until the panel docks) it is that view exactly; a record
  without its pane is taken as it is. A hard cutover: every record the 3D DXF
  viewer wrote (thickness, bends, hidden layers, 2D/3D, a camera) reads as nothing
  stored.
- **Fixture and test**: `dxf/__fixtures__/sample.drawing.json` is exactly what the route
  answered for `sample.dxf` (default-pen line-work, a red circle, a solid hatch with an
  island, TEXT, a bulged LWPOLYLINE); `make_fixture.py` regenerates the pair.
  `DxfRenderer.browser.test.mjs` serves it and asserts on PIXELS — the fit, the theme
  flip, the red circle, the unfilled island, the hairline at 800%, zoom about the
  pointer, pan, re-fit and the resize rule; `DxfRenderer.test.tsx` asserts its strip
  (Select, in hand, Draw and Measure), the corner's zoom, no Preview, a Display card of the Background alone, and
  its Layers tab from the first frame.

## GLB renderer

`createGlbRenderer` (`@cad/ui/renderers/glb`, id `glb`) shows a `.glb` as
its NATIVE glTF scene, always: one path whether or not a clip is playing.

- **Scene** (core's `lib/render/glbScene.js`): the file's hierarchy (nodes, skins, morph
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
- **Display**: `viewFeaturesForKind("glb", { parts, explodeParts })`: Solid and Clip, Parts where
  the file has several meshes, and Explode where it has two or more rigid nodes that draw
  (`explodeParts`); Preview draws Render.
- **Tools** (`glb/tools.js`): **Select** (in hand as the file opens), **Draw**,
  **Measure**, **Explode** (several parts only) and **Clip**. Select picks a NODE: the glTF
  node a mesh belongs to, marked on load (`userData.gltfNode`, `glbMeshData.js`), named
  `n<index>` after the file's `nodes[index]`; a selection is any number of nodes, each a chip
  in Quick Edit (its name, told apart by its id where several share it) whose card says
  `nodes[i]`, its triangles and, for a GLB the engine exported, the STEP occurrence it came from;
  the scene lights it with a STEP part's highlight ink (`sceneHighlight.js`). Measure takes
  points on its surface and reads glTF's metres, approximately (see
  [Measure on a mesh](#measure-on-a-mesh)). Explode moves the rigid nodes that draw along the
  file's tree (`sceneExplode.js`); Clip cuts every surface and caps the cut. There is no filter
  menu and no copy-references key; its viewport menu (`kit/tools/select/sceneMenu.js`) is a node's
  reference, Select and the framing, and a double-click on empty space fits.
- **One motion at a time** (`kit/tools/model-effects/motionExclusion.js`): Explode set, the
  routine playing (or owning the pose) and Clip set each put the other two back, decided by
  value. A routine lets go of Explode before it plays, so it starts from where the nodes were
  authored; a routine let go puts them back under Explode's (`syncExplode`).
- **Animation** (`glb/useGlbAnimation.js`): clips play from the shell's Animation tab (the panel's last) in the tools view
  (`AnimationSection.jsx`: the Clip dropdown row, always, one clip too, the transport, Speed and Loop, Reset at its bottom right; its scrubber's
  start the rest pose) and from Preview's playbar in
  Preview (`PreviewPlaybar.jsx`). The file OPENS AT REST — one `AnimationMixer` on the native scene, built by
  the first play, scrub or clip choice. Preview plays a routine of its own, a second
  `useGlbAnimation` on its own scene's document: at rest each time it opens, played only by
  the person, gone as it closes; the tools view's clip is never touched.
- **Panels**: the view's panel from the first frame, its Model tab the file's node tree (`kit/inspector/SceneTreeSection.jsx`,
  the panel's placeholder rows in it while the file loads; a GLB with no node, one row named for the file, which picks nothing), then, for a file
  with clips, the shell's Animation tab. Preview is the shell's, as for every 3D file; it draws the
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

`createMeshRenderer` (`@cad/ui/renderers/mesh`, id `mesh`) shows an `.stl`
or a `.3mf` as what it is: triangles, and in a 3MF a colour per object.

- **Scene** (core's `lib/render/meshScene.js`, `buildMeshScene`): one `Mesh` per object of the file (a 3MF has one per
  object and material; an STL one per body, `b<n>`, else one, `b1`) and nothing else: no part table,
  display records, edges or selectors. An STL's bodies are core's `lib/render/stlBodies.js` (`withStlBodies`): the
  connected pieces of its triangles, corners welded at `STL_WELD_TOLERANCE` (a millionth) of the bounding diagonal,
  joined by union-find, numbered largest first by triangles, an ASCII STL's named solids kept apart; past
  `STL_BODY_LIMIT` (2,000) the file is one body. One unnamed body is named for the file (`buildMeshScene`'s `name`).
  A 3MF's object knows its place in the build (`o2.1`:
  the second build item, its first component; `threeMfMeshData.js` reads it from three's
  loader and from the package reader alike) and its unit the one the model declares
  (`<model unit>`, read from the head of the root model part alone). Geometries
  come from `@cad/core/lib/render/meshObjects.js` (`buildMeshObjects`): views
  over the arrays core decoded, never copies, with the display normals of
  `meshNormals.js` (creased at 30° up to `CREASED_NORMAL_MAX_TRIANGLES`, plain
  vertex normals above it) and a 3MF's build transforms baked in.
- **Loading** (`mesh/useMeshScene.js`): core's `loadRenderMeshByUrl`, so an STL is
  parsed in the STL worker where there is one, a 3MF that three's loader rejects
  falls back to the package reader, and the decode is cached per file revision:
  reopening a file fetches and parses nothing. Progress reads "Reading model",
  then "Loading geometry 0/1". A new revision replaces the scene when it is ready. An STL shows first as
  one body, the whole file; its bodies are split after (core's `loadStlBodies`, `stlMeshWorkerClient.js`: in the STL
  worker over a copy of the triangles, else on the page, once per decode, the decode never written — on a million
  triangles the split takes about twice the parse) and, where there are several, replace the scene, what was picked
  in the first one let go.
- **Look**: a mesh authors no finish, so Solid wears the viewer's surface and
  Render the studio's, over the same colours (`setSurfaceLook` never keeps an
  "authored" finish). Original keeps each object's source colour; an object
  without one takes the viewer's surface colour, and once one object of a 3MF is
  coloured the rest keep the colour their material carried. Flat is unlit,
  Single colour and Color by part override source colours (the palette is dealt
  in the order it always was, `paletteIndex`), opacity applies to every object.
- **Display**: `viewFeaturesForKind` (Solid and Clip, and Parts for a 3MF of several objects or an STL of several bodies;
  Preview drawing Render).
- **Tools** (`mesh/tools.js`): a 3MF has **Select** (its objects, by their place in the
  build: `model.3mf#o2.1`; an unnamed one is "Object o2.1"), **Draw**, **Measure** (in the
  unit the file declares, approximately) and **Clip**, Select in hand as it opens. An STL is
  in no unit: **Select** (its bodies, by their number: `model.stl#b2`), **Draw** and **Clip**, Select in hand as it
  opens. Neither has parts to move apart, and their viewport menu is an object's or a body's reference and Select,
  then the framing; a double-click on empty space fits.
- **Panels**: the view's panel from the first frame, its Model tab the file's objects or bodies
  (`kit/inspector/SceneTreeSection.jsx`, a row each, the panel's placeholder rows while the file loads; one row for a 3MF of one object or an
  STL of one body). Preview is the shell's, as for every 3D file;
  it draws the scene's sibling (`createSibling()`: its own meshes, materials and look over the
  editor's geometry; `kit/shell/usePreviewScene.js`).
- **Alerts**: a file that fails to parse raises the load alert ("Couldn’t load
  the model", with the loader's error in Details); one that parses to no
  triangles raises "No geometry to display", unless it is a 3MF that carries G-code: a slicer's print file
  (a `.gcode.3mf`), which says so and that it opens in the slicer, a warning with no Retry or Report Issue.
- **Quick Edit**: as a STEP's — the picked objects or bodies as references, the annotation and the
  views (Clip in their `display`).
- **Host commands**: the base live commands, and `clearSelection`; `select` is declined with
  a sentence, a `selectReference` host request is consumed and acknowledged without changing
  the view, and live state reports `selectedObjects`.
- **State**: the shell record under `[path, "mesh"]`. Records written under
  `[path, "cad"]` are not migrated.

## Robot renderer

`createRobotRenderer` (`@cad/ui/renderers/robot`, id `robot`) shows a
`.urdf` or `.srdf` as its kinematic tree. One renderer, one payload: the engine
resolves the description (its document's `structure`, `cad_server.robot_payload`) into the
articulation the page plays, played by core's `common/articulation.js`, the visuals it
draws (each mesh at its rest placement: a link's mesh file, or a box, cylinder or sphere
the engine meshed, held by its digest) and the facts a person reads back. An SRDF is its paired URDF with the SRDF's
semantics on it (group states as named poses, end effectors, planning groups). The page parses nothing: a
description the engine refuses (its validators' findings, a mesh the page cannot draw, a `package://` or remote mesh, an SRDF
with no single URDF beside it) is refused at the door, in the engine's words. Nothing below
the loader asks which format it was.

- **Scene** (core's `lib/urdf/robotScene.js`, no React, no DOM): a scene GRAPH
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
  rest placement, source mesh and palette place. A primitive the engine meshed carries no name
  and is never an object. Geometries wrap the loader's arrays and are shared by visuals
  that name one mesh.
- **Loading** (`robot/useRobotDocument.js`, over core's `lib/urdf/loadRobot.js`):
  `loadRenderRobot` (the payload, cached by the description's
  revision), then every distinct mesh URL it names (`loadRenderMeshByUrl`, at most six
  at a time; a primitive is served by the engine by its digest, its document's `parts/<hash>`).
  Progress reads "Loading URDF", "Loading meshes 3/13",
  "Building robot". The robot is published once, whole. A mesh that cannot be fetched
  fails the load. A warm file is on screen on the first render; a new revision loads
  behind the robot on screen and keeps the pose it was left in while its controls and
  named poses are unchanged (`poseLogic`), and opens at its opening pose when they
  changed. An SRDF the engine could not pair (the ONE `.urdf` in the same folder whose
  `<robot name>` matches) raises an alert that says what was looked for, around the engine's
  sentence; any other refusal is the load alert, with the engine's sentence as its reason.
- **Look**: a robot authors no finish, so Solid wears the viewer's surface and
  Render the studio's. Colour, in order: the colour the description gives the
  visual; else the colours the mesh brought (per vertex, graded as a material
  colour is); else the named object's own; else the viewer's surface colour.
  A colour the description gives a visual (a URDF `<material>`)
  WINS over the colours its mesh file carries: this is deliberate, and a snapshot wears
  it too, because it draws the robot with this same scene.
  Materials are double-sided, so a mirrored `<mesh scale>` cannot turn a link
  inside out. "Color by part" deals the palette in the order parts always took it.
- **Display**: `viewFeaturesForKind` (Solid and Clip, and Parts where it has several link
  meshes; Preview drawing Render). A robot is posed, never exploded.
- **Tools** (`robot/tools.js`): **Select**, its menu the chevron after it
  (`kit/tools/select/SelectFilterMenu.jsx`), its one row Filter: All, **Links**, then **Position** (the
  joints' knobs, shown while it is ticked, beside the links a click picks; the menu is offered where a
  control can be driven, and until the robot has loaded), both ticked when a file opens; Select's button
  badged with Position's knobs while they are all it picks, a funnel while nothing is; then **Draw**, **Measure** (the description's metres, REP
  103, each mesh as its `<mesh scale>` draws it; approximate) and **Clip**. Clip turned on puts
  the joints back at the opening pose, and a joint moved takes Clip off: the second is heard
  on the pose store itself, outside React, so a pose step still renders no component.
- **Pose** (`robot/poseStore.js`): joint values live in a store outside React
  (degrees; metres for a prismatic joint), with one write path. A write is clamped,
  ignored under `JOINT_VALUE_EPSILON`, releases the tracked named pose and is
  heard synchronously: the scene poses itself, the handle list is re-read from the
  motion groups' world matrices (`robot/jointHandles.js`), one frame is requested,
  and the stage follows once per frame (`shell.syncSceneBounds`). Only the control
  that shows the value that changed is subscribed to it, so a pose step renders one
  slider row and no other component. On `juno.urdf` (28 links) a knob step cost
  about 270 ms of script when a pose was React state and a re-placed part list; it
  costs about 3 ms with the Position section folded and about 6 ms with the joint sliders on
  screen (a development React build), which is what a frame costs. The opening pose is
  every joint's default, then the SRDF group state(s) named `home` (core's
  `openingControlValues`, `common/articulation.js`; the engine opens a robot there for a still too). Preview draws a robot of
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
  the highlight ink a STEP part wears; hover is not React state. Its viewport menu, under
  Select, is a link's or an object's reference, Select, Hide and the framing; opening the file again fits it afresh.
- **Panel**: the view's panel's tabs, whatever the tool: **Links**
  ([Robot links](#robot-links): searched by the panel's search box), then **Joints** where a control can be
  driven. No tool panels.
  `PositionControls.jsx` is the Joints tab's body (`RobotRenderer.jsx`) — the `Pose`
  row, labelled Position, and its dropdown (`Default`, which puts the joints back, the SRDF group states, and
  `Custom` for a hand-moved pose), then the slider control (`kit/inspector/SliderField.jsx`) per
  driven joint (never a fixed joint or a mimic follower),
  its thumb named after the control, and last Reset, the tab's actions row.
- **Host commands**: the base live commands; `clearSelection` clears the link
  selection; `select` is declined with a sentence (a robot description has no
  reference grammar), and a `selectReference` host request is consumed and
  acknowledged without changing the view. Live state adds `selectedLinks` and `selectedPartIds`.
- **State**: the file's view under `[path, "robot"]`; its slices are
  `pose` (the control values) and `visibility` (the hidden component ids), written against the
  description's revision and restored only under it. The tracked named pose, the selection and the tree's disclosure
  are not stored.
- **Test seams** (read-only): `window.__cadJointHandles()` (knobs in CSS pixels,
  with values and drawn travel), `window.__robotLinks()` (every link group's frame)
  and `window.__robotPoseStats()` (matrices written per pose, renders of the surface).

## Engine document renderer

`createXbfRenderer` (`@cad/ui/renderers/xbf`, id `xbf`, `src/renderers/xbf`) shows a
engine document: an `.xbf`, and a `.step` or `.stp`, which the engine reads and serves as
one. The strip is Select with its menu's chevron, Draw, Measure with its own, Explode for two or more
parts, and Clip; the panel its Model tab (a part file's one row, an assembly's tree), then Params where the
document records any, then Joints where it carries a mechanism, each a tab; and selection, hover, the menus, isolation, Escape and Quick Edit's chips
follow the rules of [Selection and inspection tools](#selection-and-inspection-tools).
`XbfPanels.test.tsx` holds the panels to those controls.

Underneath, the page reads the document from the engine (`useXbfScene.js`), and
every face and edge is to hand from the start, so nothing waits on topology: under Faces and Edges
every part is pickable at once, and with Parts and Faces or Edges ticked a part's faces and edges are once its row is open
(its menu's Expand), the part (or the collapsed assembly holding it) elsewhere. The tree is the
engine's (`xbfTree.js`): the document's wrapper is no row, and sibling parts of one prototype
sharing a name's stem fold, as a STEP's repeated components do. The view's menu's Select tangent faces
and Select tangent edges add the engine's groups of the part to the selection (`GET …/part/<key>/groups`), and a chip's card reads the
engine's facts of the element, measured on the exact shape. The Joints tab's rows are the mechanism's
pairs (core's `lib/xbf/xbfKinematics.js`), a geared pair written through its gear, and its knobs are Select's as
a STEP's are (`xbfJointHandles.js`). A pair the engine could not keep a value for is said in the
tab, under the rows.

A document with motions plays them from the shell's routine transport, named by its runtime's
`noun`, over `useXbfMotion.js`: the top of its Joints tab (`kit/tools/playbar/AnimationSection.jsx`'s
`AnimationControls`: a Sequence dropdown row of the motions by name, Play or Pause and the scrubber (its start the
rest pose; no time readout), then Speed and Loop rows, the tab's one Reset at its bottom right; with no Joints tab,
a Motion tab of its own) — and Preview's playbar plays Preview's own. Each frame
is the motion's pair values at the clock's time, interpolated as AP242 says (`xbfMotion.js` in core:
linear; synchronous, each step eased in and out with every pair arriving together; a function
motion's stored samples, linear between them; the clip finite, repeated while Loop is on), the same
values the engine's GLB baker keys (`xbfMotion.test.js` holds them to its bake), posed through
the mechanism's forward kinematics. While a motion owns the pose (from a play, a scrub or a choice of
motion until it is scrubbed back to its start, paused) the Joints tab shows its frame (an edit lets the motion go)
and Select draws no knobs. A motion is one
of the document's motions with Explode and the pose (below): taking it up puts both at rest,
and Explode used puts it at rest, nothing set aside.

What an engine document's selection copies -- an `.xbf`'s, a STEP's alike; a chip, Copy Reference,
Copy Prompt -- is the engine's canonical ref of each thing, the file's path first, the ref `cad <type> inspect` answers and
`select` labels its shapes with (`cad.engine.refs`): a part or subassembly by its label where that
names it alone in the document, else by its occurrence path, each segment its label numbered among the
siblings sharing it (`/work/XBF/kit.xbf#kit/hand/finger.2`); an element by its name, else its kind and
number, under it (`…#palm/f:palm.body.3`, `…#kit/hand/finger.2/face 7`); a label a plain segment
would misread JSON-quoted (`…#"M3/M4 screw"`). `xbfTree.js` spells them (`refOf`, `elementRefOf`)
with core's `cadRefs.js`, whose parser and speller are held to the engine's by one fixture, and a
pasted line is parsed back in the same grammar, to the end of the line. A STEP's are spelled the same way:
its part's label whole, spaces and all (`…/bracket.step#L bracket 80 x 60 x 6 mm/face 3`).

## Tools on a scene of triangles

A GLB, a 3MF, an STL and a robot have the kit's tools as their matrix allows them
(`kit/tools/sceneTools.jsx` composes them; each renderer adds its own Select):

| | Select | Draw | Measure | Clip | Explode |
| --- | --- | --- | --- | --- | --- |
| URDF, SRDF | links (and named mesh objects) | yes | metres, approximate | yes | no: a robot is posed |
| GLB | nodes, `n<index>` | yes | metres, approximate | yes | where it has several rigid nodes that draw |
| 3MF | objects, `o<item>[.<component>]` | yes | its declared unit, approximate | yes | no |
| STL | bodies, `b<n>` (largest first) | yes | no: the format names no unit | yes | no |

### Measure on a mesh

Measure takes two points on the surface, each exactly where the pointer is
(`@cad/core/lib/viewer/meshMeasure.js`, "Surface"): a mesh has no vertices, edges or
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
by a popover opened — puts the others back. Explode and Clip are no tools in hand: each is a
popover from its tile (`model-effects/ModelTools.jsx`), its row as it was under the strip, its
button never pressed, its effect staying on the model when it closes. An engine document has Explode, Position and its motions;
a GLB Explode, its routine and Clip; a robot Position and Clip; an STL or a 3MF only Clip.

## Host integration

```tsx
import { createCadClient } from '@cad/core/client';
import { FileViewer } from '@cad/ui/file-viewer';
import { createXbfRenderer } from '@cad/ui/renderers/xbf';
import { createCadPreferences } from '@cad/ui/renderers/workspace';
import '@cad/ui/styles.css';

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
async function receiving `PrepareContext`. The latter lets a host obtain the engine's connection only when
opening a CAD file. The host owns the connection, authorization, and any
runtime recovery actions. Construction does not fetch files or load Three.js.
Preparation resolves metadata with the viewer's abort signal; the component
and viewport are imported lazily after renderer selection.

A CAD renderer's controls are its own, over the viewport: its tool strip, the tool in hand's
sub-toolbar and its docked panel. Display is the navbar's plain-cube button, left of Preview, opening its
card. Preview is the shell's own state in
every 3D renderer, with no host prop, and the navbar gives way to Preview's own bar while it
is up (`RendererViewProps.onPreviewChange`); see [Preview](viewer-ux.md#camera-animation-and-preview)
and [the host's side](viewer-host.md#preview-and-renderer-navigation-actions).

All package exports are compiled ESM with declarations. Consumers need no
source aliases, JSX transforms for dependency `.js`, or cross-app stylesheet
paths. A bundler must support the emitted `new URL(..., import.meta.url)` worker
assets, which remain inside `@cad/core`.

## Preferences and the file's view

Everything the viewer keeps is the tab's: one record, `{ version, settings, files }`,
thrown out with the tab and kept across a reload (`@cad/ui/tab-store`; the host
side is in [viewer-host.md](viewer-host.md#files-state-and-shutdown)), and of the files
only the one on screen has a view in it (the page keeps those it left, in memory). The host hands
the store one adapter — a synchronous read and write of the whole record — and the
package owns the record. Nothing under `renderers/` touches storage, on import,
construction or ever.

**Preferences** are the tab's `settings`, read by every renderer as `CadPreferenceSource`
(`getSnapshot`, `subscribe`, `update`; `createCadPreferences` is the in-memory source a
renderer built without one gets). They hold the tool stack's layout and — for the
host — the appearance and the home's layout. The playback settings (Orbit's speed, Speed and
Loop) are not preferences: they are each file's own (`playback`, below). App light/dark appearance selects Inspect's
fixed workbench basis; the settings contain no theme
choice or custom scene settings.

**A file's view** is `files[[path, renderer id]]`, kept in the record for the file on screen
alone (`TAB_FILE_LIMIT` is one; `CadViewer` sets the view of a file it leaves — for another
file or the home — aside for the page once the departing renderer's last write has landed, and
gives it back to the record as the file is shown again: `files.retain`, the newest
`PAGE_FILE_LIMIT` (32) in the store's memory, never written), `{ version, camera, display,
playback, renderer }` (`kit/shell/fileView.js`). A reload shows the same file, and restores it,
as showing again a file the page left restores that file's:

| Kept | What |
| --- | --- |
| `camera` | The renderer's own: a scene's pose, lens and projection (a perspective snapshot, scoped to the model on read), restored in place of the open-time fit — null, or not a camera, fits; a flat view's (a board's, a schematic's, a drawing's) plane transform with the pane it was framed in (`kit/viewport/flatView.js`), placed on the pane it opens in by what it shows, and exactly itself on a pane of that size. |
| `display` | The Display settings, Clip and Explode included. |
| `playback` | The playback settings, every one of them (`kit/tools/playbar/playbackPreferences.js`): `{ orbitSpeed, speed?, loop? }`, `DEFAULT_PLAYBACK` `{ orbitSpeed: 1 }` (an old record's `autoplay` is dropped), and `speed` and `loop` once chosen (the Animation or Joints tab's Speed and Loop rows, or Preview's playbar's Playback settings) — unset, the routine's authored values apply. Kept between leaving and re-entering Preview, and across a reload of the tab. Whether Preview orbits is not kept: it opens still. |
| `renderer` | The renderer's slices, each `{ signature, value }`, restored only while the signature the renderer declares for the file on screen still matches. Robot: `pose` (joint values) and `visibility` (hidden component ids) against the description's revision. Engine document: `tree` (expanded rows, the person's alone: not a pick's reveal's nor an isolation's; hidden parts, isolated assemblies) against the document's tree, and `pose` (preset, given values, couplings) against its mechanism (`xbf/xbfViewSlices.js`). GLB, mesh: none. DXF: nothing beyond its camera. Board: `board` (its Display), `isolated`, and `board3d` (`{ mode: "2d" \| "3d", camera, projection, models }`: which is up, the 3D camera as a perspective snapshot, null for the opening view (`goHome`'s), its projection, and whether the parts' 3D models show; the record's `camera` stays the flat canvas's transform). |

| Not kept | Every open starts it afresh |
| --- | --- |
| A file left, once the page that left it has gone (a reload keeps the file on screen's alone): its whole view | The defaults, when it is opened again |
| The tool in hand | The default tool |
| The selection, measurements, the annotations | Empty |
| Preview, its camera and its Orbit | Off; the tools view's camera is the one kept, Preview opens still, and its settings are the file's (`playback`) |
| The routine, its time and whether it plays | At rest |
| Quick Edit's note | Empty, its bar following what is picked or annotated |
| Select's menu | Filter every box ticked, Selection tool Select |
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
a bar at the view's bottom, on the strip's centre line, always there (one row at rest, its attachments a row above
it only while something is referenced), which
`RendererShell` mounts for a renderer that hands it `references` — every 3D file's renderer
(a picture, `compact`, gets none); a DXF and a board mount the same bar over their canvas
(`kit/shell/useFlatView.js`). Its bar, chips and buttons are [the viewer's](viewer-ux.md#quick-edit) and
[the design system's](design-system.md#chips); what it can do follows the host
([prompt handoff](viewer-host.md#prompt-handoff)), never an app. The renderer hands
the shell what is selected as `references`, in the prompt grammar (an `.xbf`'s and a STEP's in the engine's,
`kit.xbf#kit/hand/finger.2`, `bracket.step#bracket/face 3`; a robot's links, `robot.urdf#upper_arm`; a GLB's nodes,
`model.glb#n12`, the file's `nodes[12]`; a 3MF's objects, `model.3mf#o2.1`, its build's second
item's first component; an STL's bodies, `model.stl#b2`; the file itself always
goes), and the
shell hands Quick Edit the file, its prompt (`quickEditPrompt`: the views it
carries — the view on screen, from `ShellViewport.promptCamera` and the renderer's
`viewState`, its pose and hidden and isolated parts — and the files `host.promptFiles`
makes of them, with the annotations as an annotation file) and the viewer's Escape. `quickEditPrompt.js` builds the context at
the press, from what is live then (`createQuickEditContext`), and the text a copy writes
(`copiedQuickEdit`, over core's `formatPromptMessage`), its files named from the workspace
(`host.promptFiles.folders()`), the inline packet's `input` too. The drawing tools hand it whether there is
ink, and the Annotation chip copies its `.annotation.json` file's path. Copying without
Quick Edit is the copy shortcut — the selection's references, or, while Draw is up, the
view with its annotations — which writes the clipboard directly. See
[ViewerHost](viewer-host.md) for lifetime, focus, supported content and clipboard
representation limits.

An optional `ViewerCommandSource` (`@cad/ui/renderers/workspace`) has the same
subscription shape and publishes
`selectReference: { selector, key? }` or `captureRequest: { key }`. A fresh key
requests another operation even when its selector or target file is unchanged.
Selecting a reference also expands the matching model tree row's ancestors (with every box ticked)
and scrolls it into view; the model tree is on screen whenever the panel is (pinned or peeking; on a phone, its
sheet), under every tool.
Repeating the request reveals the existing selection again without toggling it off; a face-group
reference keeps the group highlighted and reveals its active face.
Both toolbar capture and host capture commands use the same implementation.
Hosts can provide `acknowledge(kind, key)` to consume an admitted command; one that does
binds commands to the active tab and path and removes only the matching
nonce, so an old acknowledgement cannot clear a newer request or replay after a
remount. A capture waits for ready geometry; a selected reference waits until it
can resolve against the current model.

`@cad/ui/file-viewer/presentation` exports the lightweight
`ViewerLoadingOverlay` for host bootstrap and generic viewer loading presentations:
the one loading indicator (`loading/LoadingStep.jsx`, a step line over a thin bar) on the viewport's Background it
is handed. It mounts inside a relative container and requires no CAD client.

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
was left at, showing again a file the page left restores the one it was left at, and opening a
file the page has not shown fits. Presets update projection/lens while retaining viewpoint and
zoom on the same renderer, canvas and controls. Ordinary settings edits never
restart the viewport. Initial/reset/fit views use the
projected bounds rather than a bounding sphere, padded 1.1 across and, down, 1.1 on
a square or narrower viewport easing to 1.25 at 16:9 and wider
(`interactiveFitPadding`): about 91% of the limiting dimension in a side pane or on
a phone, and 80% of a wide view's height. Manual views retain their own
zoom and pose. This policy belongs to the interactive UI; snapshot/export
framing remains independent. The orientation control labels its positive X/Y/Z
axes and retains its snap and drag interactions.

See the [design system](design-system.md) (the tokens, the two scales, the components, touch),
[the viewer's layout and patterns](viewer-ux.md) (what goes where and why, the patterns),
[render types](render-types.md) and [renderer contracts](renderers.md) for changes inside the shared package.

## STEP and source separation

STEP inspection reads the document's geometry, assembly structure, and topology.
It does not search for a matching Python file or reconstruct authored operations,
parameters, or annotations. Geometry references added to prompts identify the STEP and its
selected entities, without attaching a source filename or source line.

## Selection and inspection tools

An engine document's Select picks what its menu's Filter ticks — any of Parts, Faces, Edges,
Annotations and Measurements, with Position's knobs beside them — and the view's menu adds a face's or
an edge's tangent chain (`xbf/xbfSelectionFilter.js`, `kit/tools/select/selectFilter.js`); Measure's
Filter ticks any of vertices, edges and faces, which a press takes whole (none: the free point). Explicit filters never fall
back to a different entity type. Every face and edge is to hand from the start, so nothing waits
on topology.
Shift-click adds/removes entities. A double-click on a face or edge (outside the
Parts filter) turns the view square to it, its first click's pick standing; on a component or
subassembly it isolates it, the selection kept, and on empty space it leaves isolation, or, with nothing
isolated, fits the model.

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
`@cad/core/lib/xbf/xbfEntities.js`): a face's surface read off its nodes and the normals
the engine meshed it with (a plane's normal, a cylinder's axis, origin and radius), an edge's
polyline read as Measure reads it (straight, or a flat circle about its centre); its points
where its instance stands now, the pose and Explode included. A click acts at once. The first click of a
double-click therefore selects whatever it hit, and that pick stands; the second is not a click of its own (the
browser counts it, `xbf/clickActivation.js` holds it for the `dblclick` that owns the gesture), and the
double-click isolates, leaves isolation or looks at what it is on. Two clicks wait the double-click window (220ms)
instead, and a double-click drops them: one that would take the selection away (the thing selected pressed again,
or a selected thing with Shift or a finger: `pickTakesAway`), so a double-click never shows the selection going and coming back; and one under a tool a pick
would leave (Explode, Clip: a pick there takes up Select), so a double-click there isolates and stays in the tool.
A lone one acts once the window has passed (under Explode or Clip, selecting and switching to Select). A press on
empty space clears at once. A finger's double tap (within 300ms, its window) is a double-click and a long press the
view's menu; a finger's tap adds to the selection, and on a selected thing takes it away.
Every copied reference — a chip's click, ⌘C, both menus — carries the
file's prefix: the file's absolute path, the real file name with its extension.
Escape clears the
selection after any open menu has been dismissed. Input fields
keep their own Escape behaviour.

Measure is an exclusive picking tool. Its chevron's Filter ticks, as Select's does, any of vertices,
edges and faces (`kit/tools/measure/MeasureFilterMenu.jsx`, `measureFilter.js`; all when a file opens),
and badges Measure's button with what it ticks (`measureBadge`: none for all, a kind's glyph alone, else
a funnel). A press takes an entity whole, as a STEP's Measure did
(`xbf/XbfMeasure.jsx`, `xbf/xbfMeasurePick.js`): an edge's end within 10px of the pointer is its
vertex, else the edge, else the face, of any part, open in the tree or not, kept to what is ticked (none ticked: the free point);
Shift takes the point on the model as it is. What it is comes from the document
(`@cad/core/lib/xbf/xbfMeasure.js`): a face's surface read off its mesh, an edge's
polyline; an edge's length along a curve and a face's area, beside the pointer, are the engine's
facts of it (`GET …/part/<key>/edge|face/<n>`), asked for when the pointer first rests on it.
A pair reads what the two make (`@cad/core/lib/viewer/measureEntities.js`), drawn as
every measurement is. Completed rulers are chips in its sub-toolbar while it is the tool
(`kit/tools/measure/measurementChips.jsx`'s `MeasurementsBar`, Quick Edit's chips, their card
`MeasurementCard.jsx`), and no row while there are none. They are the person's alone: nothing of
them reaches Quick Edit or its snapshots (`cad <type> snapshot --measurements` draws the rulers it is
given). Leaving Measure cancels its draft but keeps completed rulers, drawn on the model, under
every other tool.

Clip caps the cut with core's section fill (`sceneClip.js`, [Clip and Explode on any
scene](#clip-and-explode-on-any-scene)): a non-pickable display fill, not new topology or an
edit to the document. Open/non-manifold meshes cannot guarantee a solid section fill.

**Select tangent faces and Select tangent edges.** Actions of the view's menu, not settings: a click
or a box takes the face or edge it lands on, never more. Over a face, or while faces are selected,
the menu offers Select tangent faces; over an edge, or while edges are selected, Select tangent edges
(`xbfMenus.js`'s `xbfTangentSources`, `kit/shell/viewMenu.js`'s `tangentGroup`). Running one adds to
the selection the tangent chain of the face or edge pressed and of each one of its kind selected
(`xbf/xbfSelectionFilter.js`'s `tangentChain`, `withTangentChains`): the engine's groups, read off the
part's shape (`GET …/part/<key>/groups`, asked for once per part when an action first needs it: faces
joined across tangent edges, edges that continue one another at a shared vertex), the members of the
same group in the same instance. Selection never crosses instances. A plain click on a chain that is,
exactly, what is selected lets it go, as a plain click on the one face or edge selected does
(`nextSelectionIds`). The resulting faces use the existing highlight and Copy Reference controls. This
changes selection only, not CAD geometry.

### Engine document panels

An engine document's tabs of the view's panel (`xbf/XbfRenderer.jsx`), in
order, whatever the tool:

- **Model** (every document with a part, first and open at first): searched by the panel's search box
  ("Search the model"); while parts are hidden, a status line ("3 hidden", **Show all** its action); then the
  model tree (`XbfModelTree.jsx`). Its tab is there under every tool (Preview hides the panel), the tree kept
  mounted. A part file's tree is its one row, the row an assembly gives each part: its name, which selects
  it, and its eye; no Isolate, as a part has nothing to isolate it from.
- **Params** (where the document records any: the structure's `parameters`, read by
  `@cad/core/lib/xbf/xbfParameters.js`): the named numbers the model's script declares, drafts, their
  preview and Save (`XbfParametersSection.jsx`'s `useXbfParameters`, held by the renderer for as long as
  the file is on screen, so its drafts and what it saved outlive the tab's mount); see
  [Parameters](viewer-ux.md#parameters). The one control of the viewer that changes a design. A
  preview of the drafts (`client.previewModelParameters`, asked at the cadence the model's preview time
  sets: [Parameters](viewer-ux.md#parameters)) is drawn in the document's place
  (`useXbfScene`'s `preview`: read as a version is, only the parts it changed fetched, the camera where it
  is) and is never the document: the renderer's `document` and `revision`, which Export, the view's slices
  and the tab read, stay the document's; Measure follows what is drawn (`sceneRevision`).
- **Joints** (where the document carries a mechanism): its motions first, where it has any, a hairline under
  them; then the `Pose` row and the joint values (`XbfPositionSection.jsx`); and ONE Reset for both, the tab's
  actions row at its bottom right. Reaching for one of
  its controls puts the other motions at rest.

Every document with a part has a panel, its Model first (`xbfPanelSections`); only an empty one has none. What is selected is Quick Edit's chips
(`xbf/xbfChips.jsx`'s `useXbfSelectionChips`): a component
or subassembly a chip of its own, faces and edges a chip for each kind on each part,
each chip's card the key measurements. A chip shows a part's name cut at sixteen characters
with an ellipsis (`ReferenceChips.jsx`'s `capName`), the number or count after it whole, the
whole name in its card's title (a chip with no card: in its hint). In a document of one part,
which the page already names, a face or edge chip shows its kind's glyph, the kind and the number
alone ("face 1", "6 faces"); its accessible name and its card's title still say the part.

**Select's menu.** The chevron after Select's button (`SelectMenu` in
`XbfSelectionModes.jsx`, over `kit/tools/select/SelectFilterMenu.jsx` and the kit's
`SelectionSettings.jsx`) is its Selection tool section, then one row, Filter, whose submenu ticks an
engine document's kinds (`xbfSelectKinds`: Parts in an assembly, Faces, Edges, Annotations, Measurements)
after All, then Position (`xbfSelectExtras`, where the document has a mechanism). The filter is the list
of what is ticked, kept in `XBF_SELECT_DEFAULT`'s order (Parts, Faces, Edges, Position, and the
annotations and measurements): every box ticked when a file opens, and for another file. Ticking takes
Select up and leaves the submenu open. Select's button is the pointer (`SelectIcon`), Measure's the
ruler (`MeasureIcon`), each badged with what its Filter ticks (`xbfSelectBadge`, `measureBadge`:
`ToolModeIcon`; none for every kind, one kind's glyph, Position's knobs alone, else a funnel). The
renderer reads the filter's geometry (`xbfSelectionFilter.js`'s `xbfGeometryPicks`: the geometry mode
`selectGeometryMode` gives — "all", "parts", "faces", "edges", "topology" or "none" — and the booleans
`faces`, `edges` and `parts` that the scene's `pickElement` and `pickBox` take, Parts read only in an
assembly); while Select is up the press goes to a measurement first (`onSelectPress`, while Measurements
is ticked), then the annotations (`selectsAnnotations`, while Annotations is), then a part, and
Position's knobs are drawn while Position is ticked. Each earlier single choice is its kind ticked alone
and picks as it did; every box ticked is the earlier Automatic. With no geometry ticked the picker
offers nothing, the pointer lights nothing and a click lets the selection go. The geometry shapes the
tree (`treeShape`: "all" for Parts with Faces or Edges or no geometry, else "parts", "faces" or
"edges"): Parts opens every assembly and shuts every part, and Faces and Edges open every
assembly, every part pickable at once. Outside the "all" shape the tree's disclosure is locked
(`data-disclosure-locked`) and the part menus drop Expand/Collapse.

**Box select.** Select's menu opens on its two tools, its Selection tool section (`SELECT_TOOLS`: Select and Box select,
`tools` of `SelectFilterMenu`, `SelectionSettings.jsx`'s `SelectionToolSection`); the renderer keeps the one chosen (`selectTool`). Under Select a
drag turns the camera; under Box select `kit/tools/select/useBoxSelectGesture.js` turns a left-button
drag past the slop that starts on empty space into a box in the viewport's pixels and the page's
(core's `lib/viewer/boxSelect.js`, `boxFromDrag`), which takes whatever it touches, even in part,
whichever way it was drawn, drawn as one solid blue outline as it goes, holding the camera for the
press; a tap still picks. Where a drag
starts is asked at the press (`mayStart`): not on the annotation's ink (the shell's own test,
`annotationAt`) and not where the renderer says no -- the XBF renderer's `modelAt` (a ray meeting
the model's visible geometry, `pickElement` with every kind, whatever the filter, an edge only within
the couple of pixels it is drawn in, `XBF_PICK_PIXELS.edgeDrawn`, not a click's reach: a press on the
empty space just beside a part, where a box round it starts, draws the box) or a measurement
(`measureSelectHandlers`' `under`) -- so a drag on the model orbits, Shift with it, as Select's does.
The shell mounts it for a renderer that hands `RendererShell` its `boxSelect` (`{ enabled, onBox,
mayStart }`), so any renderer that adopts Box select gets its annotation half: the shell takes the ink
the box touches (`ShellViewport`'s `annotationsInBox`: the ink's screen projection,
`annotationsOnScreen`, against the box by `annotation/geometry.js`'s `annotationsInBox` over core's
`polylineTouchesBox` and `polygonTouchesBox`, a stroke at its drawn width, with what was drawn with it), under Select's filter (`selectsAnnotations`),
then hands the box to `onBox`. A renderer's measurements are its own half: `measureSelectHandlers`'
`box` takes every measurement whose dimension, as the overlay draws it (`screenSpaceDimensionLayout`),
the box touches (core's `dimensionLayoutTouchesBox`: its lines, an
arrowhead or the label's reach a press has, `dimensionLayoutHit`'s), while the filter picks
measurements. The scene judges the model (`xbfScene.js`'s `pickBox`, under the options a click's
`pickElement` is given), visible-only: faces from each open instance's triangles, confirmed by rays
on a bounded grid over the box (`boxSamplePoints`, at most 4096), and a face the grid passed between
by a ray at up to `BOX_LOOKS` points of its triangles in the box (`trianglePoints`: a sliver along a
side of the box among them); edges from its edge polylines (`segmentInBox`), each kept where no
surface stands nearer than it at a point in the box; an instance whose elements are not open, where
Parts is ticked, from the grid's hits and the same looks over its triangles in the box. So a face
partly behind another part counts by what of it shows, and something wholly hidden is never taken;
past the box's ray budget (`BOX_PROBE_MAX`) nothing more is. Hidden, dimmed and clipped geometry is
never taken. `handleBoxSelect` makes a part the node a click on it takes
(`xbfPickFrontier`), within an isolation, takes a face or edge as it is, as a click does, and hands the box to `measureSelectHandlers`' `box`. Every kind a box takes stays picked with
the others (parts, faces and edges, measurements, ink: three states, none of which lets go of another;
`kit/tools/select/boxTake.js`). With Shift it adds to each; otherwise it replaces each, a kind the
filter leaves out or the box misses included. A measurement or ink is taken wherever it is drawn,
over a hidden or isolated-away part too, as a click takes it.

The flat views (a board, a schematic, a drawing) have the same box under Select, with no tool of its
own: `useFlatBoxSelect` mounts the gesture over the flat canvas (its pan switched off for the press,
`useFlatCanvasView`'s `controls`), where a plain left drag draws it wherever it starts, a Shift,
Ctrl, Cmd, right or middle drag panning; Shift at the release adds. Each renderer finds its own
picks in the box's page box under its filter, what it touches (a board's `boardIndex.js`
`pickBox`, a schematic's page `pickBox`, a drawing's `entitiesInBox`), and `boxTake.js`'s `takeFlatBox` takes them with the ink and the
measurements. A board's box that takes nothing names its area on the working layer
(`board.areaSelector`). A guard test (`kit/tools/select/boxSelectShared.test.js`) holds every flat
renderer to the shared box and the box's element to one module.

Explode and Clip follow Measure on the strip; Explode only with two or more parts
(hidden, never disabled, once the document is known; idle until it is). Each is a popover from
its tile (`kit/tools/model-effects/ModelTools.jsx`'s `useModelTools`), not a tool in hand, with
no enable checkbox: Explode's name, its slider, its amount and Reset explode; Clip's axis
(`ClipAxisSelect`, "X ⌄", whose dropdown holds the axes as one row of buttons, as the app menu's Theme row
draws its own, then a rule, Part colours and Reverse), its slider, its amount and Reset clip
(`ModelViewControls.js`). Opening one takes up no tool and leaves the selection as it is; an
edit applies the effect and the slider at zero removes it; Reset puts the amount back at zero —
Clip's axis and settings stay. The effect stays on the model when the popover closes and under
every tool, a dot in the tile's corner while it is set. Clip's plane and slider range share the
original bounds, unaffected by pose or Explode. The lifecycle is
[the viewer's](viewer-ux.md#tools).

Joints is no tool: its controls are the view's panel's Joints tab, and its joint
handles are Select's while Select's filter ticks Position. Robot viewers use the same shell,
the shared `Pose` row and the tab's Reset, whose Default and Reset put the pose back (`kit/inspector/kinematicsControls.jsx`),
and the same filter kind. Display is not a tool: opening its card leaves the tool in hand,
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

The model tree rows are the panel's one row (`TreeRowSurface`, `dense`: 28px rows, a phone's 36, its glyph slot
on the panel's 16px line and 10px further a level, hung from faint lines under their owners'
chevrons, their kind icons light: [Rows](design-system.md#rows)). A part is a
leaf: its faces and edges are the viewport's to pick, never rows. An assembly's disclosure
button expands its children; the rest of the row selects it. A folded row (a part repeated under
one name, `pin (8)`) is pressed the same way: its chevron opens and shuts it, and the rest of the
row selects every part under it, which the row then holds, lit, as an assembly's row holds its own
selection, so a press on a row selects it and opens nothing (`xbfTree.js`'s `xbfHeldPaths`), and a second plain press on
it, while its parts are what is selected, lets them go, as any row's does (`xbfSelectionFilter.js`'s `nextSelectionIds`:
the one thing selected, exactly, pressed again; Shift, Cmd or Ctrl add or take away each part). The rows walk by the
keyboard (`primitives/tree-keys.js`, [Keyboard](viewer-ux.md#keyboard)). Labels keep the row's width;
measurements belong to Quick Edit's chips' cards. An assembly row's actions (`XbfPartActions.jsx`), shown on hover and kept
shown while they are on, are Isolate (not in a part file; while that node is isolated, an X that
leaves isolation, shown the whole time) and then Hide (the eye, off while isolated). A double-click
on a component or subassembly row isolates it too; Isolate is also in the row's context menu.
Isolating, from the tree, the model or a menu, brings the isolated row into view, as a pick does.

That menu is THE part menu, the one the viewport offers over the same part: one
descriptor (`xbfMenus.js`'s `xbfPartMenu`) and one set of actions (`partMenuActions`),
rendered by `AssemblyPartMenuItems` (`xbfMenuItems.js`), so the two cannot drift apart. Copy Reference, Select/Deselect, Isolate/Exit isolate, Exit all isolates, Hide
others, Hide/Reveal, then the tree's Expand/Collapse and Expand all/Collapse all,
and last one framing group: **Zoom to fit** and **Zoom to selection** (off without
a selection). Framing cannot contradict the tool in hand, and every item of this
menu returns to Select before it acts. The VIEWPORT's menu exists only while Select is the
active tool — under any other tool a secondary tap opens nothing (in preview there is no viewport menu),
though the native menu stays suppressed and a secondary drag still pans. The
TREE is the view's panel's, under every tool; every action of its menu returns to Select
first. A secondary tap on
empty space asks about the model as a whole (Show all, Expand all, Collapse all,
then the framing group; `xbfModelMenu`). A single-part document has no part menu — a press on
the part opens this one too — so there it opens with the part menu's reference group for the
whole part: Copy Reference. The tree starts directly below the model tree
section's head, its filter (`TreeFilterInput`, `primitives/tree-filter`, shared with the
explorer), with a conditional Show all after it; in the view's panel, the panel's search. While
parts are hidden a status line heads the tree (`3 hidden` and **Show all**; what is isolated says
so on its own row): a box on the panel's 8px lines, its glyph on the 16px one, its words where the rows' names start, its action's
text ending on the right 16px line. Clicking empty tree space clears selection.

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
alone, never in the tree: by its menu's Expand (Expand all), so that a press with every box ticked picks
its faces and edges (`xbfTree.js`'s `xbfPickFrontier`). Viewport hits select individual faces
and edges with every box ticked, Faces and Edges; the view's menu's Select tangent faces and Select tangent
edges add tangent face groups and edge chains. Double-clicking empty space exits isolation, or, with nothing isolated, fits the model.

Isolation restricts the selectable subtree without propagating an excluded
ancestor's disabled state into the isolated descendants. Hidden geometry stays
unselectable. Selection reveals expand the required ancestors and scroll once
per selection or explicit reveal command. A reveal opens a row where its chevron opens
and shuts it, the host's open rows (a folded row by its own id), so the chevron shuts
whatever a reveal opened. The host keeps who opened a row the person did not (`xbf/xbfExpansion.js`): a
pick's reveal, or an isolation and its reveal; the file's view keeps the person's rows alone, so a
reload opens what they opened and nothing a pick did, a row a reveal opened is theirs once they open or
shut it, and leaving isolation shuts what isolating opened (an isolation a reload brings back opens
again as isolating opened it). Later expansion and manual scrolling
must not pull the view back to that row.

A chip's card is read-only: under the reference's name (whose copy icon copies the whole reference,
`<file>#<selector>`; the card shows no ID row, the reference being of use only
copied) its rows are a few key facts alone (`xbfChips.jsx`'s `xbfDescriber`, from the engine's facts of the element):
a face's part and area, an edge's part and length, a part's size, volume and mass, a subassembly's
part count, size, volume and mass, each to three significant figures (a number of four figures whole) in the unit it reads
best in — no type, centre, normal, radius, component, source material or child row. A click on the chip copies its references (as Copy References
writes them, with the file's absolute path); the tree and viewport menus copy too, and
measurement previews are the Measure tool's. There is no source feature view.

Tool order, sub-toolbars, the view's panel and cleanup policies are defined in
[the viewer's layout and patterns](viewer-ux.md#tools). Keep renderer
implementations aligned with that contract instead of defining another layout here.

A selection outlives Select: under any other tool the view still lights it and
Quick Edit still carries it as chips, until it is cleared (its chips' X, Escape, a
press on the background, or a new pick). Picking is Select's alone: choosing a row in the
Model (or a host `selectReference`) under another tool returns to Select
first. Every tool works alongside a selection, as it does alongside a pose, Explode,
Clip and the annotations (the two motions among them replace each other: one motion at a time).

### Position

Position edits persist when switching tools or tabs, or shutting the panel. A robot's new
revision keeps the values, and the named pose they were chosen as, when its driven joints and
named poses are the ones in hand (`poseLogic`, `robot/poseStore.js`); when they changed, the
pose starts at the new defaults — the old values are never fitted onto other joints. Its
Position row's Default restores an engine document's as-built values (`xbf/XbfPositionSection.jsx`)
or the robot opening pose (including SRDF `home`). Preview's pose is its own. A paused motion never locks
Position: its frame is shown, and an edit lets the motion go (`onRelease`, explicitly) and takes over from that
frame. An engine document's pose is keyed by its mechanism (`useXbfPose`): a parameter edit (which also lets a
motion go, `useXbfParameters`' `onEdit`) keeps it while the joints are the same, and resets it to Default when
they changed. The Joints
tab's layout is [the viewer's](viewer-ux.md#joints).

Position's knobs (its filter kind's glyph lucide `Spline`) drag a model's joints by handles
in the viewport, under Select while its filter ticks Position. They exist where
something can be driven: a robot (URDF, SRDF) with a revolute, continuous
or prismatic joint that is not a mimic follower, and an engine document whose mechanism
has a pair that turns or slides. Robots and engine documents
open in Select with every Filter box ticked: the tool in hand is never stored, and a reload
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

Routines are never a tool of the strip, nor a bar under the model in the tools view. There they play from the
view's panel's **Animation** tab, last (`kit/tools/playbar/AnimationSection.jsx`, `data-animation-section`; none for a
file without routines), one set of controls at rest, playing and paused: the routine, a labelled dropdown row
(Clip; a mechanism's motions, Sequence) listing every routine, one too, a choice playing it from its start (the
shell's `playClip`), then Play or Pause and the scrubber, with no time readout
(`AnimationTimeControl`, its time its value text; scrubbed to 0 while not playing, the routine lets go,
`onRelease`: there is no Stop), then Speed (a dropdown: the presets, and an authored speed outside them), Loop,
labelled rows, and Reset in the tab's actions row at its bottom right (no Reset in the transport). A mechanism with joints
and motions has no Motion tab: the shell hands its motion to the renderer's Joints tab (`jointsHoldMotion`,
`JointsMotionContext`), drawn first there, one Reset for both. Leaving the tab or shutting the panel leaves a routine playing. In Preview the routine plays from Preview's
playbar (`PreviewPlaybar.jsx`): one transparent row on no surface, the routines' dropdown where there are
several, Play or Pause, the scrubber and **Playback settings** (`PlaybackMenu`, opening from its cog).
There is no Restart; the scrubber's start is the restart. A routine opens at rest. In the tools view a
paused routine's frame stays on the model, as a pose does. Each view's routine is its own, on
its own scene: Preview's (`RendererShell`'s `previewView.animation`) is at rest each time the
Preview opens, plays only when the person plays it (there is no Autoplay), and goes with Preview's
view as it closes; the tools view's is never touched, and stands as it was left. Preview
opens still, whatever Orbit did last (`shell.orbiting`). Speed and Loop are the file's, one set, chosen in the tab's rows
or Preview's Playback settings and applied to its routine (`RendererShell.jsx`) once chosen (`playback.speed`,
`playback.loop`; unset, the routine's own); they and Orbit's speed are kept between
leaving and re-entering Preview, and across a reload of the tab. Nothing under the pointer
is pickable in Preview or while a routine plays.

One motion at a time in the tools view: Explode, the Position pose and a playing routine
replace each other (`kit/tools/model-effects/motionExclusion.js`, [Clip and Explode on any
scene](#clip-and-explode-on-any-scene)); while the model is exploded there are no knobs.

Of the playback the transport preferences survive every rewind — the routine, Speed and
Loop — for as long as the file is mounted. The routine and its time are not saved: a
reloaded file starts at rest, with the Speed and Loop chosen, if any, as does a file the page
left and shows again, and a file the page has not shown starts at the defaults.

No component renders for a playing frame. While a routine plays, the animation clock calls
the renderer's frame once per tick (`usePlaybackFrames`; the GLB renderer drives its mixer so),
and the scrubber is the clock's only React subscriber. A tick is one animation frame: the
player advances the time by what the frame took (`advanceAnimationElapsed` in core's
`common/animationClock.js`) and draws it; nothing paces the frames.

### Draw

Drawing is the viewer's own ink ([annotations](annotation.md)), with no drawing SDK
behind it, and one strip tool, **Draw**, over two modes: freehand (`pencil`: the Pen, the Highlighter, the Eraser) and the
shapes (`shapes`: the Rectangle, Line, Arrow, Ellipse and Text). An engine document (an .xbf or a STEP), a GLB, a mesh, a robot, a DXF and a KiCad board offer them. (The tools themselves are the
SHELL's — `kit/tools/annotate`, `shell.tools.drawing` — and a renderer puts them on its strip;
`renderers/shell-harness` also mounts them, for tests.)

It is one plain tool of the strip (`annotation/toolbar.jsx`'s `drawStripTool`, `shell.tools.drawing`), no chevron or menu: its
button (the icon of what it draws with now: the pen's at first) takes up the one last drawn with (`session.lastFamily`); what it
draws with is chosen in its row (`AnnotationToolbar`'s tools, both families', `takeFamily` taking the family up). Its tool modes are `pencil` and `shapes`, the strip's one tool
(`drawFamilies`; a drawing key takes the family up, `pressToolKey`); telemetry counts the tool as `draw` and each tool chosen by
its own name (`pencil_pen`, `shapes_rectangle`, …). `useAnnotationSession(family, …)` is told which is in hand and keeps both
choices (`pencil`, `shape`). Both share
the session's ink and history, but not the style: it is kept per drawing kind, three slots (`session.styles`) — the Pen,
the Highlighter and Shapes (all five shapes share one) — each with its own colour, stroke width and placement, and
`session.style` is the slot of the tool in hand. While Draw is up one sub-toolbar, "Annotation
controls", hangs under the strip (`annotation/toolbar.jsx`'s `AnnotationToolbar`, drawn by `RendererShell.jsx`), two
rows on one surface with no rule (a phone's wrap where they have no room, its buttons 36px tiles):

- The **tools** (`DRAWING_ROW_ENTRIES`), a button each, the one in hand pressed: the first row the seven that put ink
  down, Pen, Highlighter, Line, Arrow, Rectangle, Ellipse and Text; the second row starts with the Eraser, which takes
  ink already down — choosing one is how Draw changes what it draws with, its family taken up.
- After it on the second row, **Colour**, **Stroke width** (its button three lines thin to thick; each weight in its
  menu a straight line at that weight) and **Placement**, dropdowns, then **Undo**, **Redo** and **Clear annotations**.
  The dropdowns show and set the tool in hand's own slot; under the **Eraser**, which puts nothing down, the three are
  disabled (greyed out, still on the row so it does not jump), and Undo, Redo and Clear stay as they were. Every stroke
  is solid: there is no line style. Undo and Redo (lucide's `Undo2`, `Redo2`) call `session.undo` and `session.redo`,
  are off where the history has no step that way (`canUndo`, `canRedo`), and show their keys in their tooltips
  (`toolShortcuts.js`'s `undoShortcuts`, by the host's `environment.platform`). The second row is seven controls, as
  the first is seven tools: Eraser, Colour, Stroke width, Placement, Undo, Redo and Clear.

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
Draw opens on the pen, and its shapes on the rectangle, each in neon red, 2px, On surface; the Highlighter opens in
neon yellow (`#ffe600`, on the palette in both schemes), 2px, On surface.

The ink Select has picked has a bar of its own (`kit/tools/annotate/AnnotationSelectionBar.jsx`):
the tool strip's surface, a size smaller, just above the ink (below it where there is
no room above) and following it as the camera and its parts move. Its Color, Stroke
width (strokes picked) dropdowns restyle the pick, one
step each; **Delete** deletes everything Select has picked, a measurement too.

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
unless Shift keeps them, while Select's filter ticks Measurement (a box takes every kind it holds at
once, `measureSelectHandlers`' `box`). The pointer resting on a measurement lights it first, a
fainter halo (its hover, through the shell's `onSelectHover`), and the part under it is not lit.

A file view has one set of annotations (`annotation/session.js`). It has no panel: while
there is ink it is Quick Edit's **Annotation** chip, its pen first — a click copies the path
of its `.annotation.json` file, its X clears the annotations as one step to undo. ⌘C or
Ctrl+C, while Draw is up, copies the view as it is on screen, ink included, as a PNG
(`host.clipboard.writeImage`).

With them put down the ink stays in the model, and its chip in Quick Edit. The next
drawing tool adds to it. Annotations are session-only and never written to tab or file state.

**Undo and Redo** are the annotations' (`kit/shell/useViewerHistory.js`, the shell's):
each piece of ink put down, erased or restyled, and a clear, is a step.
⌘Z and ⇧⌘Z (Ctrl+Z and Ctrl+Y) walk them from anywhere in the viewer but a text field, and so do the
Undo and Redo buttons on Draw's row. A Quick Edit note
carries the annotations as files: the annotation file, the views they were drawn in as a
snapshot job, and a picture of each ([annotations](annotation.md#lifetime-and-capture)).

### File navbar

The file navbar is [FileViewer's](file-viewer.md#the-navbar-and-the-explorer): the panel's toggle, where the
file has a panel, then the logo,
which opens the app menu (Back to home, the person's settings, feedback, the links, the
version), Back and Forward where the host keeps the view's history, the file's name (which
opens the explorer) and its ⋯ menu at the left (the web viewer's Export is a submenu of the
⋯); at the right only what a host or a file adds: the renderer's actions, then the view's own controls, Display
and Preview, which the view portals into the navbar's view slot, then, outermost, the host's actions
(the CAD app's Full size). Every host has the navbar; only Preview, which draws its own bar, and a compact view are
without it. The CAD renderers publish one navbar action, and only while a person has put away an
alert card the model survives: the card's own icon, which brings it back (see
[Inspect, Render and live revisions](#inspect-render-and-live-revisions)). What a person
tells the agent is Quick Edit's. The renderer's update
status is in the viewport, under the strip, never in the navbar. So a view drawn as a
picture (`compact`, as the home draws its thumbnails) needs no navbar at all.

The host's `captureRequest` command captures the view (with its annotations, when there
are some): to a composer destination it goes through the prompt-context port
(`promptContext.deliver`) with the references it depicts. The DXF renderer, which is
not on the shell, answers it with its canvas through the same port.

### Preview and the camera

Camera framing, routines and Preview follow the shared
[interaction contract](viewer-ux.md#camera-animation-and-preview).
`useViewportCamera` owns initial fit and orientation transitions. Preview's camera is
its own viewport's: framed afresh from the default direction each time it opens and kept
nowhere, while the editor's camera stays where it was, untouched, under it.
`zoomRuntimeToBounds` is the single framing act used by context-menu
Zoom to Fit and live `resetCamera`. Cube shortcuts preserve zoom and pan.

Preview is one `previewing` state the shell owns (`usePreviewState`, `kit/shell/usePreviewState.js`); a renderer whose
own gates run before the shell's hook holds
it and passes it in as `preview`, as the engine document's does. It is a 3D view's: a renderer that
offers it declares `previewable` (the engine document's, GLB, the meshes and robots do), and one that
does not has no Preview button and stays in its normal view whatever sets the state. A board, a flat view whose
picture is shown in 3D, has it too, holding the same state outside the shell (`useFlatPreview.jsx`; see the board's
paragraphs under [Shell](#shell)). Everything of Preview that is not a family's own scene is one hook for both,
`usePreviewFrame.jsx`. The
Preview button, the navbar's after Display, sets it — after covering the view in the frame of the
press ("Preparing preview…", until Preview's view has presented, its published mesh is complete and the
picture has converged) — and Escape or Exit preview, an X beside Display in Preview's bar, clears it;
no host prop reaches it.
Preview is a view of its own (`kit/shell/PreviewView.jsx`): RendererShell mounts it over the
editor's viewport box while the state is on and unmounts it as it goes. The editor's viewport
is never told: it is `suspended` (it draws nothing under Preview, and a frame asked of it
meanwhile is drawn before paint as it is uncovered), and what shows when Preview closes is
its own last frame. Each family builds Preview's scene with its own builder over the
editor's geometry (`createSibling()` for GLB, mesh, robot and engine document scenes,
`usePreviewScene.js`), with its own pose and routine.
While it is up, the frame drops the tool strip and its sub-toolbar, the tool stack and their
resize handles, Quick Edit, view cube (not mounted), alert card and viewport menu, hides the
view's panel (its sections kept mounted; Preview's own routine plays from its playbar under the
model), and every
renderer gate reads the same state: picks, hover, highlights, Measure, Draw, joint
handles and Select are off, and Explode and Clip suspended, without discarding their values.
The navbar goes too, in every host: the shell says Preview is up (`view.onPreviewChange`) and
FileViewer hides it until it closes. In its place `PreviewChrome` draws Preview's bar over the
view's top edge, on no surface: the file's name at its left as words, and at its right Preview
settings, a toggle pressed while its card is open (the Settings card, Display's family, docked under the bar's
right end and sliding in from the view's right edge as the peek does, `SettingsCard.jsx`'s `SettingsCardDock`:
`kit/shell/PreviewSettings.jsx`, Orbit, off at every entry, and its speed, then Preview's own
settings, `PreviewRenderSettings`), and Exit preview. The bar and the playbar fade together after
two seconds without pointer movement (counted from the frame that shows them, so a long frame is
never idle time) and come back on movement, a tap or keyboard focus,
held while the pointer or the focus is on either or the settings are open (`usePreviewIdle`); nothing sits under the
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

A URDF or SRDF opens in Select, with **Links** the view's panel's first tab (searched by the
panel's search box), then
**Joints** where a joint can be driven (`LinksSection`, `PositionControls`),
whatever the tool. Links is always present: it is the description's kinematic tree, not an
inventory of mesh names. `robot/robotTree.js` builds it as plain data.
Links are the rows, carrying no icon; a child link sits under its parent link
and shows the joint between them as muted text (`shoulder_pan · revolute`); the
visual components (`robotComponents` in core's `lib/urdf/robotParts.js`) are leaves under that
link, after its child links. Every visual contributes a component, including STL
meshes and built-in primitives, named as the payload labels it (`visuals[].label`,
minted by the engine: the visual's URDF `name` or, without one, its geometry —
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
to Select, leaving Select keeps it, and Escape clears it. A click acts at once but for one that would take a pick
away, which waits the double-click window, as an engine document's does; a
robot's double-click on empty space fits the model, as every view's does. Its viewport menu is a
link's or an object's reference, Select, Hide, and the framing.

Each link or component row has the Hide/Reveal eye of an assembly row
([the panel's trees](viewer-ux.md#trees); `robot/RobotVisibilityButton.jsx`), also in search results.
A link hides its own visuals, leaving child links visible and all joints active.
A partially hidden link hides its remaining visuals; a fully hidden one reveals
all of them (`robot/visibility.js`). Hidden geometry is excluded from rendering,
picking, the bounds and selection highlights: the scene takes the ids
(`setHiddenPartIds`) and keeps its meshes for a reveal without rebuilding them.
Hidden component ids are the `visibility` slice of the file view, saved against the
payload's revision beside the pose (`robot/useRobotVisibility.js`); a live reload
retains only ids still present.

The `tcad:four_bar` extension is a nonlinear mimic: the engine's URDF reader resolves it
(`cad_server.robot_payload`) and core's articulation player follows it (`common/articulation.js`). Its dependent joint has no slider in the Joints tab and no joint handle.
The authoring contract specifies the namespace, geometry and range constraints.

A link's chip card (`LinkDetails.jsx`), headed by the link's name, is the link in focus alone and a
few key facts: its mass, and the joint that holds it to its parent (name, type, and the parent link,
a press selecting it; "Root link" for the root) — never its geometry, inertia tensor or child links
(the Links tree is the hierarchy). The engine keeps every fact as the description wrote them, in the payload's
`links` and `joints` (`joints[].origin`, `limit`, `mimic`; `links[].inertial` with
`origin` and `inertia`, `visuals` and `collisions`, each mesh file with the host path
the engine resolved for it), beside the articulation it renders from. A named object shows its link and size.

What names something else can be followed. A mesh path is a link that opens
that file, by its absolute path, through the host's `onOpenFile`: the renderer resolves
it against the opened file with the mesh loader's own `resolveLocalAssetFileRef` (an
SRDF's URDF is always beside it). A `package://` reference has no path here and stays
plain text, as is every mesh path in a view that shows its file alone (no `onOpenFile`: a
host's file handler). A parent or child link name selects that link in the tree and the viewport.
A click on a link's chip copies its reference (`/path/robot.urdf#upper_arm`); a link whose
name the reference grammar cannot spell has no reference, and is left out of the prompt.


### Tool panels and dark surfaces

A renderer's sidebar sections are `ToolPanel`s drawn as tabs of the view's panel
(`kit/shell/FlatPanel.jsx`, through `ToolStackContext`'s `tabbed`): the panel's width, no
surface, scroller or grip of its own, never folding, each named by its tab and its body the tab's
page; the panel scrolls each tab and is sized from the grip on its right edge. A
renderer's own `toolPanels` are `ToolPanel`s in the tool stack under the strip and
sub-toolbar (`kit/tools/ToolStack.jsx`): every panel one width (164px),
each exactly its content's height — up to its cap, for a `resizable` one, which opens at the
column's height — until the column runs out; then a `"tree"` panel scrolls inside itself
first, the `"details"` ones next, each in proportion to its height, and a `"fixed"` one
never; and if those still do not fit, the column scrolls. The resizable panels' sizes and the
folded stack panels are one of the tab's settings (`CadPreferences.toolStack`); the view's panel —
open or collapsed, its width, its tab — is the file's, in its view
(`file-viewer/filePanel.js`).
The strip, its sub-toolbars and the stack's panels share one
translucent surface, lightly blurred (Preview's playbar is on none: a transparent row); every menu and popover over the viewport a more opaque one
with more blur and the same border; Preview's settings, read while they are up, one between them
(the view's panel is docked, on the chrome's own colour, `bg-sidebar`) (`lib/floatingSurface.js`); every scroll region is the
`ScrollArea` primitive. A submenu is portaled, never drawn inside its parent menu, which that
surface makes a containing block.

The shared dark UI and **the canvas** are neutral greys, no hue, as Figma's and VS Code's dark
themes are: the tokens at chroma 0 on the shadcn lightness steps. The canvas is the content area
behind every view, 2D and 3D, one colour from one token, `--canvas` (`oklch(0.235 0 0)` dark,
`oklch(0.94 0 0)` light), a step under the navbar and the panel (`--sidebar`). A 3D view's tools
view draws its scene on it (`resolveViewSceneSettings`'s `canvas`), a
board on it in its palette (`plot2d/theme.js`, drawn again in the browser when the theme switches),
a schematic's sheet on it and a drawing on it; what cannot read a stylesheet takes core's
`lib/appTheme.js` copy, which `src/styles/canvas.test.js` holds equal. **Which** canvas, and in which light or dark the
whole picture is drawn, is the viewport's theme, the person's Background (Light by default: a grey gradient down a 3D
view, `resolveViewSceneSettings`'s `canvas` a `[top, bottom]` pair; or Dark), never the app's
(`@cad/core/lib/viewportTheme.js`, `kit/look/useViewportTheme.js`, [the viewport's scheme](design-system.md#the-viewports-scheme)).
Preview keeps its studio (`previewDefaults`: `#222222` dark, white light, in the viewport's light or dark), and the
stills their own light backgrounds, whatever the setting.
The marks use blue branding.

## Inspect, Render and live revisions

The Model keeps the document's assemblies and parts, contextual dimensions, selection
filters and prompt-reference actions. It does not inspect model source, and never
initiates a source build. A complete previous version stays visible until its replacement
is ready.

Display selects one of six modes — Solid, Shaded, Parts, X-ray, Hidden line, Wireframe — and
the Grid switch; a mode has no settings of its own. Render is Preview's alone, its settings
Preview's settings panel; it resolves to perspective, and the shared camera defaults to
orthographic. The schema and menu behavior are specified in [Display modes](render-mode.md).
Photographic lighting and stage code stay lazy. Authored materials are read-only, with
no material override or undo state.

The host-supplied render session owns its worker leases.
The file view's display slice is the sole view-settings authority; the camera is the
mounted viewport's, saved with the view and restored in place of the fit. An engine
document's reads use the file's injected service and abort when the consumer leaves.

Opening shows in the viewport's loading overlay. An update — a newer revision
loading behind the model on screen, or a Display change being prepared, and that
change's failure with a Retry — shows centred under the tool strip and its sub-toolbar, or at the
top centre, level with where the strip would be, where there is none (a load, a compact host,
Preview): every view's frame draws it (`ViewFrame.jsx`'s `status`, `ViewUpdateStatus`; on mobile, a
spinner whose label opens on press), and none while the card says why the view's chrome is gone. An error is a card over the viewport (`ViewerAlertCard`), always;
one the model survives (`blocking: false`, the previous version still on screen)
has a Dismiss button, and stays dismissed until the alert changes, or clears and is
raised again, or another file opens. The dismissal is the frame's (`useAlertDismissal`), so a
trip to Preview keeps it, and while it stands the card's own icon, in its colour and named
after the alert, is the first of the navbar's right-hand controls, before the host's actions
(the renderer's navigation action): pressing it brings the card back, and the icon goes. A warning is a card
too, dismissible while the model is on screen:
there is no other place a problem is listed. Full diagnostics stay expandable under
Details; Retry uses FileViewer's renderer reload,
which reopens the file and does not restart the host, and Report Issue,
where the host has a tracker, opens a new issue titled "Issue: ", labelled `bug`, filled in
from the card, with the file's name and no path of the machine.

### Camera framing and zoom

100% is the original authored model bounds framed at the current angle. Zoom to fit and the live
`resetCamera` frame what is SHOWN at the current angle (`scene.shownBounds()`, else `bounds`: the parts
as they stand, exploded or posed, the hidden left out, the isolated alone), so a fit of an exploded
assembly reads under 100%. A saved revision keeps a camera the person took and its
zoom exactly, and fits a camera still untouched since the last fit when its box changed
(`kit/camera/cameraTouch.js`); Zoom to fit frames the new revision and hands the camera back. Explode, clipping, animation, kinematics, visibility, floor and
other scene effects never redefine 100%. Perspective and orthographic derive
their own baseline from that same box and the current viewport dimensions.
Selection fit may move the camera but cannot make that new framing become 100%.
`kit/camera/viewportCameraFit.js` owns the fit calculation; live posed bounds remain useful
for clipping, lighting and picking. Every fit — Zoom to fit, Zoom to selection, the first frame,
a board's 3D view — frames in the room under the view's tool strip and centres there, as a flat view's
fit does: the strip's reach is the frame's `--cad-tools-bottom` (`runtimeCamera.js`'s
`readStripClearance`, none in Preview's view), its share of the height `fitRoom`, and the camera's
target stands above the box's centre by half of what the strip takes. The 100% ruler and a resize's
rescale read the reach the last fit measured, so a sub-toolbar coming and going moves neither. The editor's view, covered by Preview, is resized with the page and never re-fitted at that size: it
rescales, so leaving Preview gives back the fit it opened with. A 3D view shows no percentage but a
board's, in its corner's zoom (`ZoomControl.jsx`'s `viewportZoom`); the viewport's `zoomPercent()`,
`subscribeCamera()` and `zoomBy(factor)` serve that pill, the zoom keys and a phone's Zoom submenu,
and the `window.__cadCamera()` test seam reads it (`zoomPercent`). The viewport's `goHome()` frames what
is shown from the opening direction, or from the direction and up a view seen from another side hands it:
a board's 3D view eases to it as it opens, from its bottom turned over the board, and the live `resetCamera` eases to
it; there is no Home button on the picture and no camera reset in Display's card. The acts that frame the
model are every view's context menu (Zoom to fit, Zoom to selection), a double-click on empty space, and the live
`resetCamera`; the view cube (top-right, absent in Preview) turns
the camera and keeps its zoom and pan, F frames the model, as the zoom's menu does, and opening a
file the page has not shown fits the model afresh (a
reload of the page restores the camera the file on screen was left at, and a file the page left is shown again at the one it was left at).
