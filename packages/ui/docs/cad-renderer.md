# CAD renderer

The CAD renderer is the existing viewport, floating toolbar, file sheets,
reference interactions, measurement and drawing tools, animation,
loading artwork and alerts, extracted into `@hardcore/ui`. This migration is a
behavior-preserving refactor apart from the approved prompt-action mapping and
reference-tooltip removal described in [ViewerHost](viewer-host.md). Changing
a default, control, layout, saved preference or interaction requires separate
work and its own review.

The implementation is under `src/renderers/cad`. `CadFileView` and `CadViewer`
are private implementation components. Applications use the registration and
the shared `FileViewer`; they do not import another application's source.

## Kit

`src/renderers/kit` is the format-blind half of the viewer: small modules a
renderer composes, none of which asks what it is showing. The CAD renderer
(`src/renderers/cad`) is a consumer of it. The kit imports itself, shared UI
(`primitives`, `lib`, `drawing`) and the format-blind half of `@hardcore/core`
(`lib/viewer/*`, `lib/perspective.js`, `common/viewSettings.js`,
`common/sceneSettings.js`, the Render studio); a renderer imports the kit, never
the reverse.

| folder | what it is |
| --- | --- |
| `viewport/` | `useViewerRuntime` (three.js renderer lifecycle, on-demand render loop and `requestRender`, resize and device-pixel-ratio caps, context loss, keyboard orbit, teardown), `framePresentation`, `viewportBuffer`, `renderDepthPolicy`, `sceneObjects` (`disposeSceneObject`), DOM helpers. The scene in the viewport is its owner's: teardown calls the injected `disposeScene(runtime)` and `disposeStudio(runtime)`. |
| `camera/` | `runtimeCamera` (zoom percent against the authored framing, projection and lens sync, perspective snapshots, eased transitions, fit-to-bounds, recentre), `useViewportCamera` (that behaviour bound to a mounted viewport: live zoom, the perspective a session stores, the fullscreen camera swap and its restore, view-cube presets), `usePlanMode`, `viewportCameraKit` and `viewportCameraFit`, `orbitControls`, `zoomPivotReanchor`, `zoomSpeeds`, `cameraLens`, `ViewPlaneControl` (view cube), `ZoomControl`. |
| `look/` | `stageEffects` (lighting rig scaled to the model, floor, glow and shadow catcher, grid and origin axes), the Render studio boundary (`renderStudioChunk`, `studioEnvironmentCache` and its worker). The surface FINISH is data in core: `lib/viewer/surfaceFinish.js` (`resolveSurfaceFinish(theme)`, `applySurfaceFinish(root, finish)`); a scene applies it to its own materials. |
| `view-settings/` | The settings model and store (`viewSettingsStore`, `useViewSettings`, `viewerDisplaySettings`, `renderState`), applying a change to a viewport (`useAppliedViewSettings`, `viewUpdateCoordinator`, `viewUpdateGate`, `viewUpdatePlan`), and the Display tab (`DisplaySettingsTab`, `DisplayModeOptions`). |
| `tools/` | `FloatingToolBar` (the dumb strip), `toolModes` (the tool-mode state machine), `ToolbarButton`, and the format-blind tools: `draw/` (overlay, view lock, `useDrawingViewLock`), `fullscreen/` (controls and the orbit preference), `playbar/` (`ViewportAnimationBar`, `animationClock`, `usePlaybackFrames`), `pose/` (the handle overlay, canvas, drag mathematics). Screenshot capture is `@hardcore/core/lib/viewer/screenshotCapture.js`. |
| `inspector/` | `FileSheet` and its row primitives, `FileSheetTabbedSurface`, `activeSection`, `InspectorSplit`, `modelTreeSearch`, `referenceRows` (`InfoRow`, `MonoValue`, `CoordValue`). The tree row and filter box are `primitives/tree-row` and `primitives/tree-filter`. |
| `status/` | `LoadingIndicator` and `ViewerLoadingOverlay`, `ViewerAlertDialog` and `ViewerAlertBody`, `MissingFileAlert`, `StatusToast`, `ViewUpdateStatus`, `useFileActivityReport`, `artifactWarnings`. |

**What a view opts into.** The Display tab and `resolveViewSettings` take explicit
lists, `features: { sections, modes, surfaceStyles }` (`ViewFeatures` in
`@hardcore/core/common/viewSettings.js`): the sections the tab mounts
(`VIEW_SECTION_IDS`), the presets and the surface styles it lists. A section left
out resolves off whatever was saved, and the saved settings are never rewritten.
Core names two lists, `ALL_VIEW_FEATURES` and `EDGELESS_VIEW_FEATURES` (no Edges,
Clip or Explode; Solid and Render; Shaded and Flat). The CAD renderer passes the
first for a STEP and the second for every other format, in three places that
must agree: the view-settings store (`configure({ features })`), the Display tab,
and the headless renderer (`renderMeshScene.js`).

**Tools.** The strip draws the list it is handed: `{ id, label, icon, active,
disabled, onSelect, description?, menu?, secondPressOpensMenu?, subToolbar? }`.
`cadInteractionTools` in `cad/components/workbench/FloatingToolBar.js` builds
this renderer's list per format. `createToolModes({ defaultMode, modes })`
answers what a press does (`next`), what a saved tab may record (`persisted`) and
which tool a file opens in (`restore`); this renderer's declaration is
`CAD_TOOL_MODES` in `workbench/constants.js`. The playbar follows the clock on
the runtime it is handed (`runtime.clock`, an `AnimationClock`); the Pose overlay
takes a plain handle list.

**The scene contract** (`kit/scene.js`, a JSDoc typedef): `{ object3D, bounds,
restBounds?, dispose(), setSurfaceFinish?(finish), pick?(ray) }`. `buildModel`
(`@hardcore/core/common/cadScene.js`) and the native glTF scene
(`buildNativeGlbCadScene`) both expose `object3D`, `bounds`, `restBounds` and
`dispose()`; the native glTF scene also exposes `setSurfaceFinish`.

**The rule and its check.** Kit code names no file format, no file-kind switch
and no STEP-assembly concept (topology, selectors, display records, explode,
section clipping), in code or in comments; only `view-settings/` may name the
Clip and Explode sections a view opts into. `npm run check:boundaries` runs
`scripts/test/check-kit-boundaries.mjs`, which scans every kit source for imports
of a renderer or of a file-family core module and for those words, against a
short allowlist that carries a reason per line and fails when an entry goes
stale. The unbound-identifier test covers the kit with the renderer.

## Host integration

```tsx
import { createCadClient } from '@hardcore/core/client';
import { FileViewer } from '@hardcore/ui/file-viewer';
import { createCadPreferences, createCadRenderer } from '@hardcore/ui/renderers/cad';
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
const renderers = [createCadRenderer({ client, preferences })];

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

`createCadRenderer` accepts an existing client or an async function receiving
`PrepareContext`. The latter lets desktop obtain the local backend only when
opening a CAD file. The host owns backend startup, authorization, and any
runtime recovery actions. Construction does not fetch files or load Three.js.
Preparation resolves metadata with the viewer's abort signal; the component
and viewport are imported lazily after renderer selection.

The CAD renderer declares the Inspector panel, `cad-file-sheet`. The shared
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
preferences, robot joint values and large-file opt-in. Asset signatures retain
the original invalidation rules. DXF render settings remain session state and
do not modify the generated package. Playback time is saved when stopped or
unmounted, and opening a file does not resume playback automatically.

Hosts preserve these existing preference keys and precedence when migrating:

| Data | Existing storage key / rule |
| --- | --- |
| Directory layout | `cad-viewer:directory-session:v1` (legacy theme fields ignored) |
| Global fullscreen orbit speed | `cad-viewer:orbit:v1` |
| Per-file CAD session | `cad-viewer:file-session:v1:<namespace>:<file>` |

`@hardcore/ui/renderers/cad/state` exports the existing tab/file
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
controls use `host.clipboard`. `CadViewer` only produces screenshot pixels.
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

`@hardcore/ui/renderers/cad/presentation` exports the lightweight
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
stale-operation rules and [`live.ts`](../src/renderers/cad/live.ts) for signatures.

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
generation, preventing URL cache reuse across changed credentials or origins. Mutable native GLB scenes and animation mixers remain
separately owned.

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

The optional `@hardcore/ui/renderers/cad/empty` entry exports `EmptyCadBackdrop` for the web host’s missing-file presentation. It lazily mounts the same empty CAD viewport with the host’s `colorScheme`, and overlays its `children`. It owns no file access, catalog subscription, or persisted state. This preserves the original grid and camera behind `MissingFileAlert` without loading CAD into the master viewer.

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
in the context menu. The tree starts directly below `Filter model…`, the file
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
preference (`createTabRecord` in `workbench/state.js`): a robot tab with no
recorded tool opens in Pose, one last left in Select comes back in Select, and
nothing else ever restores into Pose, so a STEP always opens in Select. It is
absent in fullscreen. While it is active the model picks nothing, hovers
nothing and casts no model ray (`pickMode` NONE, as in Animate); the camera
orbits, pans and zooms exactly as under every other tool, and the knobs are the
only interactive things. Leaving keeps the pose.

One handle system serves both formats. `workbench/jointHandles.js` holds two
adapters that turn a description and its CURRENT pose into one plain list, in
model space: `{ id, label, kind, pivot, axis, toward, value, min, max, unit,
onChange }`. A robot's joint frame is the solved child link frame (less an SDF
joint's static child offset); a STEP mate's world-at-rest axis is carried by the
accumulated delta of its child, the composition `kinematicsDeltas` uses, so a
handle rides a mate chain of any depth. A fixed joint, a fastened mate and a
mimic follower have no handle. A STEP DOF that a coupling drives KEEPS its
handle and writes through the coupling (`poseControlWrite`), as its slider does:
a coupling has no axis to hang a handle on, and a gear train whose every member
is geared would otherwise have none. The list is rebuilt from the pose on screen,
so sliders, presets, Reset and a handle further up the chain all carry the
knobs along.

`onChange` is the Kinematics tab's own change handler
(`handleUrdfJointValueChange`, `handleStepModuleParameterChange`), so limits,
mimic followers, couplings, the SRDF group state, persistence and the sliders
are decided in one place and stay in step; the drag itself never clamps. A
continuous joint's drag winds freely and is stored as one turn, (-180, 180],
which is what its slider spans.

A handle is a thin arm from the joint's pivot to a small round knob, with the
joint's travel drawn faintly through the knob: the limit arc (the full circle
for a continuous joint or a range of a turn or more) or a slider's limit track.
A turning joint's arm lies in its rotation plane toward the child's geometry,
so the knob sits on the moving part and turns with it; a child centred on its
own axis (a wheel, a roll joint, a turntable) takes a perpendicular fixed in the
child's frame instead, and concentric STEP members fan their arms round the
shared axis, decided at rest. A slider's arm runs along its axis from where the
child now is. Above twelve handles a model rests as knobs alone and the arm and
travel appear with the pointer. Hovering or holding a knob shows its name and
value (`shoulder  42.0°`, `lift  0.120 m`).

The handles are drawn on a 2D canvas over the viewport (`kit/tools/pose/JointHandleOverlay.jsx`,
`jointHandleCanvas.js`), like the measurement rulers, not as scene objects: the
arm is 44 CSS pixels at every zoom and under either projection, always on top,
and nothing of it reaches captures, render mode, bounds, shadows or picking.
`useJointHandles.js` keeps no React state: the list lands in a ref, a frame loop
repaints only when the camera, the list or the pointer changed, and the label
is written into its element. A press within 12 px of a knob (22 px for touch)
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
still while it lasts (`animateMode` in `CadViewer.js`): the transformed selector
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
(`usePlaybackFrames`), for STEP routines and embedded GLB clips alike. The
scrubber is the clock's only React subscriber. Because the pass now runs inside
the tick, the clock's adaptive pacing measures a frame's real cost. A frame that
only moved parts skips material and instance-membership reconciliation: the
effects pass reports whether a style, visibility or highlight changed
(`applyStepModuleEffectsToRecords`), and moved instances sync their own matrix.

### Draw

Draw is the shared [drawing editor](drawing.md) (Excalidraw) laid transparently
over the viewport. The chunk loads on the first use of the tool, and the surface
stays hidden until the editor has its scene, so its default white page never
flashes over the model. Pressing Draw again, like Measure, ends the session.

The editor's own toolbar, `DrawingToolbar`, is placed by the viewer as a second
row under the interaction tools in the same button metrics: Select and move
drawings, Pan view, Pen, Line, Arrow, Rectangle, Ellipse, Text, Fill area and
Eraser, then Color, Undo, Redo and Clear drawing. It shows the editor's active
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
Inspector is only Display (STL, 3MF, GLB): there the model gets the room until a
person opens it (`cadPanels(ready, file)`). Snapshot uses the host prompt-context port: desktop attaches
the viewport image and references to the owning session's draft; web copies
through its clipboard adapter. DXF also contributes its 2D/3D projection action.
The shared FileViewer renders these registered actions without importing CAD.

Zoom is a small muted percentage at the right of the Inspector tab strip. Its
menu offers zoom steps, 100%, fit, selection fit, Reset camera and Reset model.
The viewport has no zoom toolbar. Reset camera uses the original authored
bounds; Reset model also restores authored motion and disables spatial tools
while preserving display settings. See [settings-ui.md](settings-ui.md). X/Y/Z labels
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

STEP and embedded GLB keep their existing transports and renderer-scoped clocks;
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
no Kinematics tab. A mesh (STL, 3MF, GLB) has only Display: its measurements
are the Measure tool's panel under the toolbar, as for STEP, and an embedded
GLB clip is the Animate tool's. An Inspector with a single section draws it as
a single selected tab, so every Inspector reads the same way.
Each section requires its own sidecar block and stays expanded, without a gate.
Every pose write is a jump: a slider drag, a typed number, a Pose knob, a named
pose (a STEP sidecar's pose, an SRDF group state) and Reset all put the model
where it IS from that frame on, for robots and STEP alike. There is no eased
pose transition and no preference for one; motion over time is the Animate
tool's. Each format has one write path (`writeUrdfJointValues` in
`CadFileView.js`; `writeParameters` in `useStepMotionControls.js`).
Switching display mode leaves every tab and the active selection intact.
Tab order follows the format's section descriptors and cannot be customized.
The retired split/reorder preference is ignored in both hosts. A stored section
ID the current format does not have is simply not open, and the sheet lands on
the format's first tab — there is no table of retired IDs to keep alive. A
legacy list selects its last available tab. New selections and viewport-driven
reveals store one active section ID.

Robot Kinematics uses the same preset and value controls.

### Robot links

URDF, SRDF and SDF place **Kinematics | Links | Display** in the tab strip.
Kinematics is always the leftmost tab and the one the sheet lands on (an SDF's
metadata tab follows Links; an SRDF without joint controls has no Kinematics).
Links is always present: it is the description's kinematic tree, not an
inventory of mesh names. `workbench/robotTree.js` builds it as plain data.
Links are the rows, carrying no icon; a child link sits under its parent link
and shows the joint between them as muted text (`shoulder_pan · revolute`); the
named objects inside a link's meshes (`robotComponents`) are leaves under that
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

Selection reuses mesh-part picking. Every robot mesh part names its link, so a
link is hovered and selected in the viewport as all of its parts, and a viewport
pick of a part that is not a named object selects its link; a named object
still selects itself (Shift/Ctrl/Cmd add). A link with no geometry selects its
row and details only. As for STEP, a robot selection exists only while Select
is the tool: choosing a row or a part under another tool returns to Select, and
leaving Select clears it.

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
that file through the host's `onOpenFile`: `CadFileView` resolves it against the
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
for clipping, lighting and picking. Zoom controls live in the Inspector header percentage menu.
