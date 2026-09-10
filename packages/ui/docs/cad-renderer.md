# CAD renderer

The CAD renderer is the existing viewport, floating toolbar, file sheets,
theme editor, reference interactions, measurement and drawing tools, animation,
loading artwork and alerts, extracted into `@hardcore/ui`. This migration is a
pure refactor: every app must retain the same UI, UX and functionality. Changing
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
  source={source}
  renderers={renderers}
  state={viewerState}
  onStateChange={setViewerState}
  onOpenFile={openFile}
  appearance={{ colorScheme }}
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

Panel IDs remain `cad-theme` and `cad-file-sheet`. The shared viewer owns their
frame and open state; the renderer portals panel contents into `panelSlot`.
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
It contains the theme choice/custom settings, the already-seen tutorial
tips and each file kind's sheet-tab order/split arrangement. It never reads
browser storage on import or construction.

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
| Global theme | `cad-viewer:theme`, schema version 13 |
| Directory theme and layout | `cad-viewer:directory-session:v1` |
| Seen tutorial tips | `cad-viewer:tutorial-tips:v1` |
| Sheet tab order and split arrangement | `cad-viewer:file-sheet-tab-layout:v6` |
| Tip reset URL | `?resetTips` remains a web-host action |
| Per-file CAD session | `cad-viewer:file-session:v1:<namespace>:<file>` |

`@hardcore/ui/renderers/cad/state` exports the existing theme/tab/file
normalizers and width defaults for migration. `readFileSessionState` requires
an explicit `{ storage }` supplied by the host. The sheet layout helpers
`readFileSheetTabLayoutStore(storage)` and
`writeFileSheetTabLayoutStore(storage, preferences.fileSheetTabs)` likewise use
only supplied storage. `CAD_LEGACY_PREFERENCE_KEYS`
exports the theme/directory/tip key names. Origins are transport locations,
not persistence namespaces for new state.

## Reference and capture callbacks

`onReference` receives `{ file, selector, label?, text? }`. `file` is the complete
served-root-relative path; `selector` excludes the `#`, and is empty for the
whole file. Clipboard references keep the original shortest unique suffix.
Copy actions stay clipboard actions; Add to prompt invokes the host callback.
Reference text JSON-quotes filenames containing spaces or delimiters, for example
`"Hex Drive Screw (2).STEP"#o1`. The callback's `file` remains the literal path;
quoting only protects the text form through clipboard and prompt round trips.

`onCapture` receives `{ blob, file, references? }`: the original PNG composite
and its selected canonical references, captured together before the async
image operation. The host decides how to attach it to its composer.

An optional `CadCommandSource` has the same subscription shape and publishes
`selectReference: { selector, key? }` or `captureRequest: { key }`. A fresh key
requests another operation even when its selector or target file is unchanged.
Selecting a reference also activates the Inspector's Tree tab, expands the
matching row's ancestors, and scrolls it into view. Repeating the request
reveals the existing selection again without toggling it off; a face-group
reference keeps the group highlighted and reveals its active face.
Both toolbar capture and host capture commands use the same implementation.

`@hardcore/ui/renderers/cad/presentation` exports the lightweight
`ViewerLoadingOverlay`, `MissingFileAlert` and `StatusToast` for host bootstrap and generic
viewer loading/error presentations. Their markup and wording are the original
CAD artwork. They mount inside a relative container and require no CAD client.

## Lifetimes

The explicit `CadClient` owns its catalog and request controllers. The first
subscriber starts the catalog and its two-second poll; further subscribers
share them. The last unsubscribe stops polling. The host supplies `shouldPoll`
and connects window focus and visible `visibilitychange` events to
`refresh({ markRefreshing: false })`, preserving browser refresh behavior
without a DOM dependency in core. Catalog requests retain the ten-second
timeout and the same error text.

Each prepared CAD document owns a render session with its own tessellation
provider, primed bytes and deferred write queue. Its provider is bound to that
client's origin and abort signal. A late worker result can write only to that
session; disposing it discards queued writes and aborts its provider requests.
There is no page-wide mutable cache provider. HTTP storage still uses the
shared Python cache and its original component-key codec.

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
session-local writes. The browser integration harness exercises actual WebGL
rendering with two roots, panel switching, PNG captures, host title ownership
and state round trips through unmount/remount.

The original camera session schema stores vectors and zoom but removes runtime
scope metadata. The original viewport requires that metadata to restore a
camera, so a remount can retain the saved record while opening at its default
camera/100% readout. This was verified against the pre-migration
`normalizeTabCameraSnapshot`, its file-session test, and `CadViewer` scope
checks. The migration test preserves that observed baseline; this refactor
does not claim to fix it.

See [settings controls](settings-ui.md), [render capabilities](render-types.md)
and [renderer contracts](renderers.md) for changes inside the shared package.

The optional `@hardcore/ui/renderers/cad/empty` entry exports `EmptyCadBackdrop` for the web host’s missing-file presentation. It lazily mounts the same empty CAD viewport with the host’s `preferences` and `colorScheme`, and overlays its `children`. It owns no file access, catalog subscription, or persisted state. This preserves the original grid and camera behind `MissingFileAlert` without loading CAD into the master viewer.

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
Shift-click adds/removes entities. Escape clears the
selection after any open menu or first-use tip has been dismissed. Input fields
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

The STEP inspector uses one Model tab. Parts retain their assembly hierarchy and
existing visibility/context actions. Faces, Edges, and Bodies are presentation
folders, initially collapsed. The Face list menu switches between individual
faces and grouping by surface type inside each part; no entity IDs change.
Selecting a face/edge group uses the existing multi-reference selection. External
reference reveals expand the presentation ancestors so the selected row remains
reachable. The standalone model keeps one root instead of a duplicate wrapper.

Selection details are collapsible and resizable. Measured extents, area, and radii
appear first, with the existing reference details behind a disclosure. Extent and
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

The **Model → Features** view reads existing assembly/SURF assets automatically as the
current file’s geometry becomes available. It recognizes one unique component at
a time in a bounded, disposable worker and shares results across repeated
instances. It never discovers Python files, writes models, or
changes CADgen. The existing Model inspector remains the document-geometry view.

For constant-section solids, paired analytic cap contours, straight side surfaces,
side area and solid volume support a possible base-extrude / cut-extrude sequence.
The recovered sketch profiles reference actual STEP boundary edges. Full coaxial
cylinder/cone solids can instead yield a closed axial profile and 360-degree
revolution, checked against the solid volume. These are inferred modeling choices,
not original history or editable source constraints. Line/circle contours support these paths. Analytic recognition also
proposes ruled lofts and rounded-box fillets; shell and pattern
operations are not invented.

Other solids remain **Imported body**. Local planar caps, translated rims and
straight walls can identify a pocket or boss inside a more complex body. Adjacent
coaxial cylindrical patches are merged across export seams into bore candidates;
annular shoulders and full conical transitions can join their stages. Boundary
samples and enclosed face bounds reject evident material inside a proposed bore.
These are conservative analytic tests, not a general proof of an empty volume.
Other children include partial cut candidates, connected constant-radius
cylindrical/toroidal fillet candidates and all remaining faces. Candidate ordering is not a reconstructed timeline. Single curved corners
are deliberately not promoted into separate fillet operations. Profiles and their
individual edges, operations and remaining geometry all use the native canonical
reference selection and floating Add to prompt action, scoped to the occurrence.
The STEP assembly hierarchy exposes every part directly, with recognition counts
and expandable operations; a difficult first component cannot hide the rest of
the assembly. The first recognized part expands automatically. Long lists group
same-kind operations into inspection folders, never inferred patterns.
Annotation-only components show a no-faces state. Recognition continues while
the current file’s Geometry/Features views switch, and stops on disposal or when the
viewer invalidates its geometry. Completed results stay in memory for that file
revision. Retry processes only failed components. Every displayed operation and
selection remains scoped to its assembly occurrence.

Independent local OCP validation rebuilds the inferred complete plans and compares
both directional Boolean differences. This is a development check; the client
runs analytic checks only, not an in-browser CAD kernel.

External regression fixtures come from pinned FreeCAD/pythonOCC STEP samples;
provenance is recorded alongside the fixtures. Development checks distinguish
local tool occupancy from a successful remove/restore Boolean round trip. A
partial feature match does not establish a rebuildable history for the whole
part, particularly when the independent Boolean reconstruction fails.

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


### Inspector tabs and dark surfaces

The inspector uses the shared shadcn Tabs primitives for Model, Kinematics and
Animation, including native keyboard navigation. A single section shows its
content directly without a redundant tab strip. Split panes retain tab labels
so users can move them back together. Visited trees keep disclosure and scroll
state across tab changes.

The shared dark UI uses neutral charcoal tokens. Workbench Dark uses a slightly
lighter `#333333` canvas; existing custom scene themes and light mode are preserved.
The shared loading star and desktop wordmark/icon use blue branding.
