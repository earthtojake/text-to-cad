# Viewer host contract

`FileViewer` requires one explicit `ViewerHost` from `@hardcore/ui/host`.
Shared UI implements rendering and document interaction; apps supply environmental
effects. No shared feature discovers Electron, browser clipboard, a backend URL,
persistent storage or page navigation. DOM, canvas, workers and layout remain
shared. Missing optional methods mean an operation is unsupported.

The host contains `files`, optional native `fileActions`, `clipboard`,
`promptContext`, `navigation`, resolved `environment.colorScheme`, and optional
lifecycle flush subscription. CAD is a separate registration supplied with a
`CadWorkspaceService`; the generic FileViewer does not import CAD. The HTTP CAD
adapter can serve both apps, while desktop owns native runtime startup/recovery.
See [workspace resources](../../core/docs/workspace-resources.md) for resource
tickets and cache identity.

Apps create services for the workspace lifetime. File tabs borrow them, while
mounted renderers own scenes, document controllers and temporary resource leases.
Unmounting one view releases its work without disposing another view's services
or admitted cache writes. Hosts dispose a service when its workspace closes.

## Interface map and implementations

The linked TypeScript definitions are the authoritative signatures. Import
their compiled public package exports in application code; these source links
are for reading and maintaining the contracts.

| Contract | Definition | Public entry point |
| --- | --- | --- |
| `ViewerHost`, `ClipboardPort`, `ViewerCommandTarget` | [Host types](../src/host/types.ts) | `@hardcore/ui/host` |
| `FileSource`, `FileActions`, mutation receipts, `FileViewerState` | [File viewer types](../src/file-viewer/types.ts) | `@hardcore/ui/file-viewer` |
| `PromptContextPort`, bundles, references and delivery receipts | [Prompt types](../../core/src/prompt/types.ts) | `@hardcore/core/prompt` |
| `CadWorkspaceService`, `CadResourceProvider`, worker tickets | [CAD service types](../../core/src/client/types.ts) | `@hardcore/core/client` |
| `CadRendererSlots`, selection props, `CadCommandSource`, `CadLiveBinding` | [CAD registration](../src/renderers/cad/index.ts) | `@hardcore/ui/renderers/cad` |
| `CadPreferenceSource` | [Viewer preferences](../src/renderers/workspace/preferences.ts) | `@hardcore/ui/renderers/cad` (also `@hardcore/ui/renderers/workspace`) |
| `GlbRendererOptions`, `LiveViewBinding`, `LiveViewController` | [GLB registration](../src/renderers/glb/index.ts), [live binding](../src/renderers/kit/shell/liveBinding.ts) | `@hardcore/ui/renderers/glb` |
| `MeshRendererOptions` (STL, 3MF), `LiveViewBinding`, `LiveViewController` | [Mesh registration](../src/renderers/mesh/index.ts) | `@hardcore/ui/renderers/mesh` |
| `RobotRendererOptions` (URDF, SRDF, SDF), `RobotLiveController`, `RobotLiveState` (`selectedLinks`, `selectedPartIds`) | [Robot registration](../src/renderers/robot/index.ts) | `@hardcore/ui/renderers/robot` |
| `ViewerCommands`, `ViewerCommandSource` (the host requests the GLB, mesh and robot renderers take) | [Viewer commands](../src/renderers/workspace/commands.ts) | `@hardcore/ui/renderers/workspace` |
| CAD snapshot validation and versioning | [CAD state](../src/renderers/cad/state.ts) | `@hardcore/ui/renderers/cad/state` |

Start with the actual composition in [web App](../../../apps/web/src/App.tsx)
or [desktop FileTab](../../../apps/desktop/src/renderer/features/explorer/FileTab.tsx).
Their imports lead to the app-owned `host/`, `adapters/` and persistence
implementations. [Web storage](../../../apps/web/docs/storage.md) documents
browser lifetimes; [desktop README](../../../apps/desktop/README.md) documents
native IPC, draft delivery and project persistence. Shared component tests can
use the [explicit fake host](../src/host/testing/host.ts).

## Host fullscreen and renderer navigation actions

`FileViewer.fullscreen` is transient host-owned presentation state, never a file
preference. It hides the shared navbar and panel frame and passes the flag to
the renderer. CAD also hides viewport controls and suspends tools/shortcuts.
Keep the viewport mounted; preserve the selected panel, tool and document state.
The app owns its header, fullscreen entry and Escape listener, and supplies
`FileViewer.onExitFullscreen`, forwarded unchanged as
`RendererViewProps.onExitFullscreen`. CAD renders its own fullscreen playback and exit controls
and invokes that callback for Exit. The host Escape listener must honor
`event.defaultPrevented`; Escape first closes an open renderer menu/overlay.
Control visibility and the fullscreen camera are transient. CAD captures the
regular camera on entry, fits the authored model at the default angle, and restores
the saved regular camera on exit. Presentation camera events never persist into
the file session. Picking listeners, drawing and measurement are suspended;
ordinary camera dragging remains available. Orbit speed is a global
`CadPreferences.orbit` preference persisted by each host adapter. The fullscreen
playbar reuses the same per-file animation runtime as the inspector.

A renderer can publish `FileNavigationAction[]` through
`RendererViewProps.onNavigationActionsChange`. The shared navbar shows these
before its panel toggles. Each action declares its icon, accessible label,
disabled state and invocation callback. Registration belongs to the mounted
file generation: publish an empty list on cleanup; departing renderers cannot
replace a new file's actions. Publish only when action metadata changes; stable
commands should read the current viewport through a ref, avoiding parent/child
render loops. These actions use existing host capabilities for effects. For
example, CAD's snapshot delivers through `host.promptContext`, which binds the
destination before waiting for the image. It never detects the platform.

## Adding a shared feature

1. Implement reusable interaction and presentation in UI, with cross-consumer
   non-React domain behavior in core. Renderer-private helpers such as
   [feature detection](feature-detection.md) stay with their renderer in UI.
   Keep project, session and operating-system workflows in apps.
2. Reuse an existing injected contract. If a new environmental effect is needed,
   extend its narrow consumer-owned interface and implement it in each app, or
   explicitly advertise that the host cannot perform it. Shared UI must not
   fall back to browser globals or branch on `isWeb`/`isDesktop`.
3. Use subscribed capability/destination state for availability and labels.
   Use a named additive slot for an extra app-enabled interface such as Quick
   Edit; the shared renderer never imports the app's component or stores.
4. Define identity, lifetime, cancellation and result semantics with the
   contract. Publish serializable view state through the controlled binding;
   the app chooses its storage. Keep workspace services stable across tab mounts.
5. Update this contract or its linked domain guide, add focused shared/adapter
   coverage and verify affected host integrations. Exercise root changes and
   late results for asynchronous effects, and warm reuse for resource changes.
   Run `npm run check:boundaries` and rebuild compiled packages before app checks.

Platform-agnostic UI can use DOM, canvas, React and renderer-owned workers.
Filesystem access, transport selection, credentials, clipboard, persistent
storage, page navigation and native process lifecycle remain host responsibilities.

## Prompt handoff

All primary context actions use `PromptContextPort.deliver(context)`. Desktop
inserts into a compatible draft; web prepares clipboard representations. Ordinary
explicit copy/paste controls use the separate `ClipboardPort`. Delivery never
submits a prompt. The reference coaching tooltip and its retired preference/reset
plumbing are removed; accessible labels remain.

The portable types and validators live at `@hardcore/core/prompt`. One versioned
bundle contains ordered text, reference and attachment parts with unique IDs.
An attachment has a MIME type, name and Blob or Promise of Blob. Its optional
`about` array names reference-part IDs, so a screenshot and several selections
can travel together. Producers freeze resource and selection identity before
asynchronous capture. Blob URLs are delivery leases, never portable identity.

A reference contains a workspace-file identity or HTTP(S) URL plus a tagged
selection: `whole-resource`, `text-range`, or `cad-selector`. Text positions are
zero-based UTF-16 with an exclusive end. CAD selectors use core's validated
cadgen grammar, not STEP entity numbers. Preserve a revision when available;
references do not promise to survive edits. Shared serialization handles quoting.
The web adapter maps workspace files to full served-root paths for external chats.

`PromptContextAction` reads the subscribed destination and labels the shared
action Add to prompt or Copy for prompt/reference. It calls delivery during the
user gesture, before awaiting capture: browser activation and desktop destination
binding depend on this. Availability and advertised attachment/combination limits
belong to the host. Every result is acknowledged: added, copied, partial,
deferred, cancelled or failed. `partIds` describes accepted/written parts, not a
claim that a different application pasted them.

Desktop captures the compatible draft destination before awaiting attachments,
validates the complete bundle and rechecks that destination before atomic draft
acceptance. Switching chats cannot redirect an in-flight capture. Existing text
and attachments survive; operation IDs prevent duplicate acceptance. Workspace
mismatch uses the app's explicit Start chat here recovery. Invalid attachments
leave the draft unchanged. Direct capture failure never shows success.

Web supports text/reference serialization and one PNG. A combined clipboard
write reports that text and PNG are separate representations; some receivers
paste only one. Unsupported attachment types or combinations fail explicitly.
Hosts must resolve/validate accepted attachments and consume failed encoders;
they do not transfer Promise or Blob values across native IPC.

## App-specific interfaces

CAD's `slots.selectionExtras` mounts an optional React component beside shared
selection actions. It receives immutable typed selection, `selectionKey`,
disabled state and `createContext({text, capture})`. It receives no scene, stores,
IPC or arbitrary internal setters. Shared actions remain visible. Apps may supply
a future Quick Edit interface through this seam; this refactor introduces no new
Quick Edit workflow.

The renderer owns placement and visibility. A contributed popover owns its focus,
Escape handling and cleanup, stops events it consumes, and closes or invalidates
its draft when `selectionKey` changes. Freeze the context when starting the
interaction; a changed document/revision must not silently retarget it. Submission
uses the same host prompt port. Session-specific controls stay in apps.

The optional CAD `live` binding receives a `CadLiveController` only while its
viewport is mounted. `readState()` returns a detached serializable snapshot of
the actual resource/revision, current selections, camera, display and render
mode. It reads the viewport camera directly, with its last camera snapshot as
an unmount fallback. During a rebuild that retains a predecessor mesh, its
displayed document revision remains in the snapshot until replacement. Apps
own the binding registry and any IPC/tool transport;
shared UI does not infer view state from a backend catalog or stored tab state.

The controller selects available selectors, clears selection, applies a camera,
resets framing, applies grouped View settings, selects presets and captures a PNG.
`readState().display` and `setDisplaySettings(patch)` use the same sparse grouped
schema as snapshots: `mode` selects `solid`, `render`, `xray`, `hidden-line`, or
`wireframe`; camera, surfaces, edges, lighting, background, floor, grid and axes
are independent groups. Patches merge fields within a group. A mode patch
reapplies that preset before its explicit group overrides; clipping and exploded
view remain independent tools. Custom is derived from the effective overrides,
not a sixth mode. `setRenderMode(true/false)` selects Render/Solid through that
same state. Grouped camera projection/lens changes preserve the viewport's pose
and zoom. Display Reset restores the selected preset and disables both tools. The
Inspector zoom menu is framing only; `resetCamera` frames the model again
without turning the camera, exactly as its "Reset Zoom" does.

Persisted pre-grouped file sessions migrate once at the state boundary: their
old display and photographic payload become this display record; the render
session slice retains only the camera snapshot. Live commands reject retired
field names rather than maintaining a second display authority. Unavailable selectors fail explicitly; topology is not silently
loaded. Mutations return a view snapshot after the React frame; a mode switch
waits for the requested settings to commit, with a ten-second bound.
Loading views
reject commands, and an operation whose resource/revision changes or viewport
unmounts before completion rejects its late result. On unmount, the controller
releases its component closure and retains only its final snapshot with
`active:false`; every subsequent command requires showing the model tab first.
Hosts may cache that inactive snapshot without retaining a scene or moving focus.

## Files, state and shutdown

`FileSource` contains storage operations; `FileActions` contains native/menu
operations. Typed mutation receipts report committed changes independently of
caller cancellation. An abort after commit is not rollback. Content, metadata,
add, delete and move notifications have distinct meanings. Desktop reconciles
all affected tabs; web remains its existing read-only CAD catalog. This migration
does not grant web arbitrary filesystem access or enable editing there.

State remains controlled through FileViewer props. Apps merge changed chrome
fields and document/renderer slices into the current root state; a stale view
must not overwrite another view's independent fields. Existing versioned camera,
pose and layout state restores through the same schemas. Material appearance
is source-owned and read-only; legacy material override slices are ignored. Global
preferences belong to the app/window, document snapshots to workspace/path,
and live selection/scene ownership to the mounted view.

Lifecycle flush publishes the current view state; it does not save document
content or promise an asynchronous operation will finish during page exit.
Web owns pagehide, focus, visibility, history and development reload. Desktop
owns window/runtime lifecycle and IPC. Existing dirty-editor behavior remains.

The dependency checker enforces host boundaries, including worker source. The
browser harness mounts real renderers with explicit fake hosts; app tests cover
native/clipboard delivery and multiple-view state merges. Warm-cache regression
tests remain required for resource changes.

## Scoped commands

An optional `host.commands.bind(target)` registers this mounted viewer's
save/reload/focus methods and returns an unbind function. A target includes
source identity, path and document generation. Captured commands fail with
`stale` after navigation, reload, source replacement or unmount. Saves acknowledge
conflicts and failures; a stale completion can report that the old document's
write committed without updating its replacement. Each app owns dispatch to its
intended view; there is no global command bus or new menu action.

Monaco retains its editor-local save binding. CAD keyboard shortcuts consume
only events from their viewer or its last pointer-owned background, so another
viewer or the composer does not receive Escape/undo on its behalf. Existing
reverse CAD selection/capture commands remain tab-scoped domain commands;
ordinary native window Reload retains its existing app behavior.

## Live text and PDF capabilities

An optional `host.documents` supplies a draft store with workspace/path identity
and binds the mounted text buffer. Draft retention is host-owned and survives
view unmounts. Shared UI restores a draft against fresh disk metadata, marking
external revision changes stale. Explicit reload discards it. The live buffer
revision is separate from the disk revision: read/edit/save commands compare the
live token before acting, and saving still uses FileSource's disk conflict check.
Bindings reject calls after unmount; the desktop may retain read-only snapshots
for inactive tabs, tagged `active: false`, and refuse edits until reactivated.

`host.pdf.bind` registers page state, bounded page text reads, navigation and
PNG capture on the renderer's actual PDF.js document. It exposes no disk write
or script execution. Binary sources supply `ManagedFileAsset.bytes` for PDF
preparation; shared UI discovers no transport. Each mounted PDF owns its worker,
loading task, canvas and text layer, all released on unmount. Page references
and captures use the source identity and path, never the asset URL. See
[renderer contracts](renderers.md) for PDF and text selection behavior.

PDF hosts may provide `host.pdf.assetBaseUrl`, an absolute trailing-slash URL
containing the pinned PDF.js `cmaps/`, `standard_fonts/`, `wasm/`, and `iccs/`
assets. Hosts bundle and serve these assets with their notices; shared UI never
discovers a CDN. These support predefined CJK encodings, standard fonts,
JPEG2000/JBIG2 images and color profiles. Hosts allowing WebAssembly should
permit its compilation in CSP without enabling JavaScript eval.
