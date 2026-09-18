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
Preview mode calls the generic chrome visibility callback so the same preview
can hide the shared navigation and panel frame. Leaving preview restores the
previous panel selection through the existing controls.

All package exports are compiled ESM with declarations. Consumers need no
source aliases, JSX transforms for dependency `.js`, or cross-app stylesheet
paths. A bundler must support the emitted `new URL(..., import.meta.url)` worker
assets, which remain inside `@hardcore/core`.

## Preferences and per-file state

`CadPreferenceSource` exposes `getSnapshot`, `subscribe` and `update`.
`createCadPreferences` provides an in-memory implementation and an optional
host persistence callback. A host can share one source across its CAD panes.
It contains the shared pose transition preference and each file kind's
sheet-tab order/split arrangement. It never reads
browser storage on import or construction.

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
| Pose transition preference | `cad-viewer:pose-transition:v1` |
| Sheet tab order and split arrangement | `cad-viewer:file-sheet-tab-layout:v6` |
| Per-file CAD session | `cad-viewer:file-session:v1:<namespace>:<file>` |

`@hardcore/ui/renderers/cad/state` exports the existing tab/file
normalizers and width defaults for migration. `readFileSessionState` requires
an explicit `{ storage }` supplied by the host. The sheet layout helpers
`readFileSheetTabLayoutStore(storage)` and
`writeFileSheetTabLayoutStore(storage, preferences.fileSheetTabs)` likewise use
only supplied storage. `CAD_LEGACY_PREFERENCE_KEYS`
exports the directory, pose-transition and sheet-layout key names. Origins are transport locations,
not persistence namespaces for new state.

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
own 100% default. Switching Inspect/Render fits the destination mode's camera
without losing their separate stored snapshots. Initial/reset/fit views use the
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

Measure has a temporary panel below its toolbar button, with Any geometry,
Points, Edges and Faces snap filters. Measure reuses the selection-filter dropdown
component, including radio rows and keyboard behaviour; its panel uses the same
popover surface, spacing and type styles. Draw uses the same tool chooser and
panel shell, with labelled Undo/Redo/Clear actions. The View and Capture menus share the dropdown width, offset and collision boundary.
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

The STEP inspector uses one Model tab. Its rows share the file tree's row
primitive and 28px height, with the model tree's horizontal inset. The disclosure
button expands children; the rest of the row selects its canonical references.
Labels keep the row's width; summaries and measurements belong in the selected
reference details. The small eye action changes visibility, while Isolate stays
in the context menu. A fixed-height, borderless header shows the number of
top-level presented features and conditional visibility/isolation reset actions.

Parts retain their assembly hierarchy, except redundant document wrappers are
flattened for presentation. Flattening never rewrites occurrence or reference
IDs. Assembly and part expansion use the same controlled state as viewport
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

The selection pane is collapsible and resizable, but its reference fields are
visible by default without a second Details disclosure. Its item header gives
the name and multi-selection pager one row, and the kind, wrapping canonical
reference and copy action another. Measurements, center, normal and component
follow when available. Extent and
radius buttons preview the selected STEP geometry using the existing temporary
measurement overlay. Add to prompt uses canonical STEP references, optionally
with the selected measured value. There is no separate Surfaces tab or source
feature view. Display controls and per-file state retain their toolbar popover.

The toolbar has stable View, Inspect, and Markup/capture groups. View groups zoom,
a View controls menu (Pan, Orbit, and authored animation playback), and Display.
Inspect groups Select, selection filtering, and Measure. Draw stays beside a
separate Capture menu containing Copy screenshot and Ask about this view. The
groups wrap independently at narrow widths; actions keep the same group at every
width. Compact zoom keeps the editable percentage and Reset view; plus/minus
return when the viewport widens. Capture actions do not contain navigation tools.

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

STEP models place Model, Kinematics and Animation in one top tab strip by
default. Motion tabs appear only when their corresponding controls exist.
Switching tabs gives the selected controls the full panel height; playback
remains accessible from the viewer toolbar. The v6 layout resets saved STEP
arrangements to this default and preserves other file kinds’ arrangements.

Robot Kinematics uses the same preset, value and transition controls. Inspect
adds Components when a linked mesh contains authored object names, grouping
those objects under their links and connecting tree selection to the viewport.
Built-in robot primitives and unnamed mesh objects contribute no component rows.


### Inspector tabs and dark surfaces

The inspector uses the shared shadcn Tabs primitives for Model, Kinematics and
Animation, and for Geometry/Features within Model. Both levels use the default
styling and native keyboard navigation; switching views preserves mounted trees.
A single section shows its content directly without a redundant tab strip. Split panes retain tab labels
so users can move them back together. Visited trees keep disclosure and scroll
state across tab changes.

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

The floating toolbar switches Inspect and Render. Inspect uses its fixed scene
basis with per-file Display controls, while Render has its own camera, studio
and Preview/Final quality.
Entering a mode fits that mode's camera. The Studio and Materials panels load
lazily; Render's tab arrangement is temporary and never overwrites the host's
Inspect arrangement. Material overlays and undo are per-file session state.

The host-supplied render session owns its tessellation cache and worker leases.
Photographic scene state is a separate value. Surface derivation and preview
requests use that file's injected service and abort when the consumer leaves.
The Features inspector resolves exact surfaces on demand through the same client.

File status reports Opening, Updating, Limited detail and actionable failures.
Full diagnostics stay expandable; Try again uses FileViewer's renderer reload,
which rechecks the artifact and does not restart the desktop window.
