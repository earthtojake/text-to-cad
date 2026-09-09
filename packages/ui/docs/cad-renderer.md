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

`onCapture` receives `{ blob, file, references? }`: the original PNG composite
and its selected canonical references, captured together before the async
image operation. The host decides how to attach it to its composer.

An optional `CadCommandSource` has the same subscription shape and publishes
`selectReference: { selector, key? }` or `captureRequest: { key }`. A fresh key
requests another operation even when its selector or target file is unchanged.
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
properties below it. Tree remains the default, with selected geometry details.

Features reads a same-stem Python source through `GET /__cad/design-outline`.
The backend parses its AST without importing or executing it. It supports direct
CAD operations, sketches, simple one-operation helpers, and static scalar values.
Loops and conditionals are source containers, not evaluated instances. When a
source defines several `@step` functions, only an exact stem match is used.
Unknown expressions remain expressions. No values can be edited from this view.

This is a **source outline**, not evaluated build history or recovered STEP
history. Filename matching cannot prove that source generated the current STEP;
the panel states this and does not map operations to faces. Without an unambiguous
source, the view shows Imported geometry. No automatic feature detection or
Feature groups selection mode is offered. Existing saved multi-face references
continue to work through Tree and the host's reference callbacks.

## Selection and inspection tools

STEP's Select tool offers All, Parts, Faces, and Edges. Explicit
filters never fall back to a different entity type. Faces and Edges load topology
for the selected leaf part; selecting another part in Tree changes that target.
Shift-click adds/removes entities. Escape clears the
selection after any open menu or first-use tip has been dismissed. Input fields
keep their own Escape behaviour.

Measure has a temporary panel below its toolbar button, with Any geometry,
Points, Edges and Faces snap filters. Leaving Measure or changing models clears
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
