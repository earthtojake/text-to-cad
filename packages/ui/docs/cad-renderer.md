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
| Sheet tab order and split arrangement | `cad-viewer:file-sheet-tab-layout:v5` |
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

## Read-only Features view

STEP keeps its geometry **Tree** and adds a separate **Features** tab. The upper
list uses an operation/sketch hierarchy; selecting a row shows read-only
properties below it. With verified assembly links, operations belonging to one
part are nested under that part in **Parts**. Operations spanning several parts,
including repeated features, appear once under **Assembly operations**; unmapped
source operations stay there too. Single-body models retain their direct operation
list. This grouping does not invent missing helper internals or part history.
Part rows expose the existing hide/show and isolate controls, synchronized with
Tree. Isolating from Features leaves that tab open; row and panel exit controls
restore the normal view. Face-only source operations remain highlightable rather
than acquiring a misleading feature-suppression action.
Tree remains the default, with selected geometry details.

Features reads a same-stem Python source through `GET /__cad/design-outline`.
The backend parses its AST without importing or executing it. It supports direct
CAD operations, sketches, simple one-operation helpers, and static scalar values.
Loops and conditionals are source containers, not evaluated instances. When a
source defines several `@step` functions, only an exact stem match is used.
Unknown expressions remain expressions. No values can be edited from this view.

This is a **source outline**, not evaluated build history or recovered STEP
history. Filename matching alone cannot prove source/geometry correspondence.
Without an unambiguous source, the view shows Imported geometry. No automatic feature detection or
Feature groups selection mode is offered. Existing saved multi-face references
continue to work through Tree and the host's reference callbacks.

Normal model generation now records optional geometry links. For single-solid
algebraic models within its size limits, the recorder associates source statements
with surviving faces and carries a placed cutting tool's association back to its source
row. Named assembly components are linked when their identity survives into the
returned assembly. Repeat rows combine their child associations; sketch rows
highlight their consuming operation's faces, not a reconstructed sketch overlay.

The disposable cache is keyed by the exact source bytes and STEP bytes. Reading
Features never runs a generator. Before highlighting, the client requires a
complete, unique descriptor match against the loaded faces or assembly parts;
face ordinals and guessed name similarity are never used. Unsupported, ambiguous,
merged-away or stale links produce no highlight. The existing build remains valid
if inspection capture is unavailable or exceeds its budget. Newly rebuilt models
can acquire links; imported STEP without a matching source cannot.

Clicking or using arrow keys in Features previews the associated geometry using
the viewer's existing selection colour. It does not change CAD or replace the
user's actual reference selection. Escape, a viewport click, leaving Features,
or changing files clears the preview. The footer shows only the source filename.

Linked operations and loaded parts expand into an **Associated faces** group.
Each child selects one actual face and shows that face's measured properties;
these rows are topology, not reconstructed source features. Part inspection loads
one part's topology on demand, never an entire assembly's faces at once.
The X/Y/Z extent buttons preview a temporary dimension between world-axis bounding
limits using the existing ruler overlay. These are measured extents, not inferred
sketch dimensions, wall thicknesses or source parameter values. Clicking a radius
filters the preview to associated cylindrical/spherical faces with that radius.
Clicking the active measurement again, selecting another row, Escape, leaving
Features or changing files clears the temporary dimension. Inspection dimensions
are not added to the Measure tool's list or saved with the model.

When the host supports prompt context, every Features row and parameter exposes
**Add to prompt**, including source operations without geometry links. Sketch and
operation inputs appear before measured result geometry in the property panel.
The draft receives the selected source inputs, location and measured values as
plain text; valid geometry links also become the existing reference chips.
Hosts supporting only geometry references retain the linked-selection action. It sends the linked geometry through
the existing host reference callback, with a display label for the source feature.
Canonical STEP selectors and the actual file path remain the reference payload;
source row IDs are never geometry selectors. A multi-face or multi-part feature
becomes a grouped reference. Missing geometry contributes no face/part tokens; source context remains usable.
The current document is checked again before delivery. Selection alone does not modify the
draft; the action adds context without submitting a prompt. Features uses the
same floating viewer action as Tree, with the feature label and linked geometry
as its context. There is no separate Features sidebar action.

Parameters expand into individual read-only rows. Selecting a source constant
previews the linked operations that explicitly reference it, including tracked
scalar aliases, helper arguments, helper globals and repeat inputs. Reassigned,
shadowed and uncertain bindings do not imply a global-parameter link. This is a
bounded source association, not complete dependency analysis. An operation's
property values are also clickable and preview that operation's geometry.
Neither interaction creates a dimension annotation: parameter values alone do
not establish measurement endpoints. Missing associations remain unhighlighted.

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
panel shell, with labelled Undo/Redo/Clear actions. The compact toolbar's More
tools menu shares the dropdown width, offset and collision boundary. Direct
actions such as Pan, Orbit and screenshot capture remain direct actions.
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

Features part rows reuse Tree's hide/show and isolate controls. These affect
viewer visibility only; they never suppress an authored operation. Isolation
keeps Features open and offers an exit in the panel. Source-free imports list
actual parts under Imported geometry, without inventing construction history.
Single-body models expose hide/show on the Features model row even when source
operations have no geometry links, mapped to the existing whole-model render target. Their context menu omits isolate/hide-other actions because there
are no other components to isolate from. Tree visibility actions use the row's
selection target, including visual rows that alias a part.

Selected rows show associated geometry's world-axis bounding size, summed face
area when the entire face selection has area data, and available cylindrical or
spherical surface radii. Source parameters are labelled separately. Bounds do
not imply extrusion depth or volume; surface radii do not imply recognised holes.
Missing geometry/data is not replaced with zero or a partial total. Part bounds
come from the display geometry and may reflect tessellation precision.

### Tangent face selection

The selection filter offers **Tangent faces**. Clicking a face selects its connected
chain across edges classified as tangent by the loaded STEP topology; sharp,
unknown, boundary and nonmanifold edges stop the chain. Selection never crosses
occurrences or solid shapes. Shift-click adds a chain, or removes it if the whole
chain is already selected. The resulting faces use the existing highlight and
Add to prompt controls. An assembly part loads its topology through Tree first,
as with the Faces filter. This changes selection only, not CAD geometry.

Authored sketch rows beneath top-level operations are expanded when Features
opens. Repeats and assembly part groups keep their existing collapsed state;
imports do not acquire invented sketches.

Selection filters keep All, Parts, Faces and Edges together. **Connected
selection** groups Edge chain and Tangent faces separately; the measurement filter menu keeps
its existing options.

Profile inputs (rectangles, circles, etc.) retain their authored shape names;
only an explicit BuildSketch source block is labeled Sketch. This source outline
is not a recovered parametric history, and importing STEP alone does not invent
sketches or CAD operations.

Edge chain uses tessellated edge endpoints within the same solid/occurrence and
a shared face, with a 0.00001 model-unit endpoint tolerance. It follows corners
where only one continuation exists and a unique smooth continuation at branches;
ambiguous branches, missing endpoints, and closed single edges stop traversal.
Shift toggles the resulting group and Add to prompt uses its canonical edge refs.

Feature prompt context is a compact single line: source location and, when
selected, a parameter or measurement. Full child lists, parameter dumps and
unrelated measured facts stay in the inspector. Imported geometry with valid
references adds only its chip unless a particular measurement was selected.

Feature capture retains exact surviving faces of rounded surfaces; uncertain
overlap of unsupported curved patches remains unlinked. Fillets consuming a
previously collected edge list still compare against the prior result, so they
cannot claim unchanged faces from earlier operations. Source and STEP hashes
and the viewer's unique face matching remain required before highlighting.
