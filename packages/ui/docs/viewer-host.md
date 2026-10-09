# Viewer host contract

`FileViewer` requires one explicit `ViewerHost` from `@text-to-cad/ui/host`.
Shared UI implements rendering and document interaction; apps supply environmental
effects. No shared feature discovers Electron, browser clipboard, a backend URL,
persistent storage or page navigation. DOM, canvas, workers and layout remain
shared. Missing optional methods mean an operation is unsupported.

The host contains `files`, optional native `fileActions`, `clipboard`,
`promptContext`, the optional `attachments`, `navigation` (the optional `openFile(path)` and
`home()`), the optional `links` (the app menu's), the optional `usage`
(`used(feature)`: what the person used, for the host's telemetry to count, never what
they made; absent, nothing is counted) and `environment`. `environment` carries the resolved `colorScheme`,
the keyboard `platform` (`darwin` shows ⌘, anything else Ctrl), the app's own
`reducedMotion`, honoured beside the system's `prefers-reduced-motion`, and
`compact`: a view drawn as a picture (the home draws its thumbnails this way, out
of sight), where a CAD renderer draws the model alone — no tools, view actions,
view cube or Quick Edit — and FileViewer draws no navbar. A view shown small in a
conversation is not compact: it is the whole viewer, and its host hands it a way
to full size as `fullSize` (`CadViewerProps.fullSize`), the last of the navbar's own
controls (the view's follow it) and the home's. CAD is a separate registration supplied with a
`CadWorkspaceService`; the generic FileViewer does not import CAD. The HTTP CAD
adapter can serve both apps, while desktop owns native runtime startup/recovery.
See [workspace resources](../../core/docs/workspace-resources.md) for resource
tickets and cache identity.

A host installs cadgen's display tessellation ladder before a STEP model is drawn
(`installTessellationLadder` from `@text-to-cad/core/lib/surf/lodPolicy.js`), from what its
server says: the web viewer from its server info's `tessellation`, the CAD app from its
launch's. The STEP renderer picks rungs of it from the camera and holds no tolerance of its
own ([LOD](lod.md#1-where-a-model-starts)).

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
| `ViewerHost`, `ClipboardPort`, `AttachmentStore` (where a copied prompt's picture is saved), `usage` | [Host types](../src/host/types.ts) | `@text-to-cad/ui/host` |
| `FileSource` (`stat`, and `list` and `search` where the host has them), `FileActions`, `FileViewerState` | [File viewer types](../src/file-viewer/types.ts) | `@text-to-cad/ui/file-viewer` |
| `PromptContextPort` (`deliver`, `send`), bundles, references, delivery receipts and `formatPromptMessage` (the one message a Quick Edit is) | [Prompt types](../../core/src/prompt/types.ts) | `@text-to-cad/core/prompt` |
| `CadWorkspaceService` (the catalog of the files on screen, `folder`, `search`), `createCadClient` (`{ origin, fetch, … }`), `isMissingFileError`, `CadResourceProvider`, worker tickets | [CAD service types](../../core/src/client/types.ts) | `@text-to-cad/core/client` |
| `createHttpAttachmentStore` (the viewer server's `AttachmentStore`: it saves a PNG through `POST /__cad/sketches`) | [Attachment store](../../core/src/client/attachments.js) | `@text-to-cad/core/client` |
| `StepRendererOptions`, `CadLiveBinding` | [STEP registration](../src/renderers/step/index.ts) | `@text-to-cad/ui/renderers/step` |
| `TabStore`, `TabRecordStorage`, `createTabStore`, `useTabViewerState` (the tab's one store: its settings, the view of the file on screen, and `FileViewer`'s state from both) | [Tab store](../src/tab-store/tabStore.ts), [the record](../src/tab-store/tabRecord.ts) | `@text-to-cad/ui/tab-store` |
| `CadPreferenceSource`, `createCadPreferences` (the tab's settings as renderers read them) | [Viewer preferences](../src/renderers/workspace/preferences.ts) | `@text-to-cad/ui/renderers/workspace` |
| `DxfRendererOptions` (2D drawings; declines every camera, display and selection command) | [DXF registration](../src/renderers/dxf/index.ts) | `@text-to-cad/ui/renderers/dxf` |
| `GlbRendererOptions`, `LiveViewBinding`, `LiveViewController` | [GLB registration](../src/renderers/glb/index.ts), [live binding](../src/renderers/kit/shell/liveBinding.ts) | `@text-to-cad/ui/renderers/glb` |
| `MeshRendererOptions` (STL, 3MF), `LiveViewBinding`, `LiveViewController` | [Mesh registration](../src/renderers/mesh/index.ts) | `@text-to-cad/ui/renderers/mesh` |
| `RobotRendererOptions` (URDF, SRDF, SDF), `RobotLiveController`, `RobotLiveState` (`selectedLinks`, `selectedPartIds`) | [Robot registration](../src/renderers/robot/index.ts) | `@text-to-cad/ui/renderers/robot` |
| `ViewerCommands`, `ViewerCommandSource` (the host requests every viewer renderer takes) | [Viewer commands](../src/renderers/workspace/commands.ts) | `@text-to-cad/ui/renderers/workspace` |
| `createLiveRegistry`, `LiveRegistry` (the host's handle on the mounted view: its renderers' `live`) | [Live registry](../src/host/liveRegistry.ts) | `@text-to-cad/ui/host` |
| `ModelLibrary`, `ModelLibrarySource`, `useModelThumbnail` (a host's home: the CAD title over the host's links (GitHub, Discord, X), then the models opened before, pinned first, as cards or rows, and with none, where the host has a chooser, an "Open File" card that opens it; placeholder cards or rows while the list is read (again every two seconds while the home is up, so a model rebuilt meanwhile is pictured again), and a spinner over the model being opened, which takes no second press until `open` settles; `pick` only where the host has a file chooser) | [Model library](../src/library/ModelLibrary.tsx), [thumbnails](../src/library/thumbnails.ts) | `@text-to-cad/ui/library` |
| `CadViewer` (FileViewer over a CAD client, one file by absolute path or the home: the five CAD renderers, catalog following, the home, the "File does not exist" and "Could not open that file" pages, the library's pictures) | [CAD viewer](../src/cad-viewer/CadViewer.tsx) | `@text-to-cad/ui/cad-viewer` |
| `createCadFileSource` (a CAD client as a read-only `FileSource`: `stat` through the client's `resolveEntry`, `list` through `folder`, `search` through `search`), `createCadFileActions` (the file menu's Copy path, the absolute path, and Reveal), `normalizePath`, `baseName`, `joinPath`, `contentRevision` | [Catalog](../src/cad-viewer/catalog.ts) | `@text-to-cad/ui/catalog` |
| `ViewerLinks`, `viewerLinks` (the version, GitHub, Discord, where a new issue opens, the newest release and how to update, and how a link is followed), `issueUrl` (a new issue filled in — its title, labels and body — its address kept under `ISSUE_URL_MAX`) | [Host types](../src/host/types.ts), [links](../src/file-viewer/navigation/links.js) | `@text-to-cad/ui/links` |
| `buildId` (for an app's Vite config: which build this is, "" for the release's own, whose environment names its version in `TEXT_TO_CAD_RELEASE`, else the checkout's commit) | [Build id](../scripts/build-id.mjs) | `@text-to-cad/ui/build-id` |

Start with the actual compositions: [web App](../../../apps/web/src/App.tsx) and the
MCP app's [ModelView](../../../apps/mcp/src/ModelView.tsx), both one `CadViewer`.
Its imports lead to the app-owned `host/`, `adapters/` and persistence
implementations. [Web storage](../../../apps/web/docs/storage.md) documents
browser lifetimes. Shared component tests can
use the [explicit fake host](../src/host/testing/host.ts).

## A CAD renderer's controls

The controls of a CAD renderer (STEP, GLB, mesh, robot, DXF) are panels of its own tool
stack over the viewport (`settings-ui.md#the-tool-stack`), and nothing it does opens or
closes the explorer (only the file's name opens that). The tool stack's layout — the
sizes a person dragged the tree, the Reference and Position panels to, the folded panels
and whether the tree is closed — is one
of the tab's settings (`settings.toolStack` of the tab record, `@text-to-cad/ui/tab-store`),
beside the appearance and the home's layout.

## Preview and renderer navigation actions

Preview is the shared shell's own state (`previewing`); there is no host prop
for it and a host cannot start or observe it. It is a 3D view's alone, and each
renderer says whether its view is one: it declares `previewable` to the shell
(`useRendererShell`), as STEP, GLB, STL/3MF and URDF/SRDF/SDF do. A view that does
not — a DXF's 2D drawing, which draws its own surface without the shell — has no
Preview at all, no control and not a disabled one, and nothing that asks for
Preview (a link or a host request, should either come to) takes it there: it keeps
the normal view. The CAD app's Full size, inline, is the host's display mode, not
Preview: it shows the normal view, of any file. It is fullscreen
(`onFullscreenChange`, below): the navbar, with everything in it (the app menu and the
explorer too), steps aside while it lasts. It never uses the browser Fullscreen API. The shell saves the tools view's camera, fits a preview camera and restores
the tools view's exact pose on exit; nothing of preview is persisted. Orbit
starts by default, with its speed, unless the file's Orbit says otherwise: preview's
settings are the file's view's `playback` — orbit on or off and its speed, Autoplay, the
routine's chosen speed and loop — kept between previews and across a reload, and a
file's routine plays on entry only when its Autoplay is on. The rules are in
[settings-ui.md](settings-ui.md#camera-animation-and-preview).

A renderer can publish `FileNavigationAction[]` through
`RendererViewProps.onNavigationActionsChange`. The CAD renderers publish one, and only
while a person has put away an alert card the model survives: the card's own icon in its
colour, named after the alert, which brings the card back (`useAlertDismissal`,
`kit/status/ViewerAlertCard.jsx`). The
shared navbar shows these at its right, after the host's update button and before the
host's Full size and the view's own controls. Each action declares its icon, accessible label, an
optional shorter hover `hint`, disabled state and invocation callback. Registration belongs to the mounted
file generation: publish an empty list on cleanup; departing renderers cannot
replace a new file's actions. Publish only when action metadata changes; stable
commands should read the current viewport through a ref, avoiding parent/child
render loops. These actions use existing host capabilities for effects. What a
person tells the agent about a CAD file is [Quick Edit](#prompt-handoff)'s.

A renderer's controls for the view are the renderer's own, drawn into the navbar: FileViewer
hands it the box at the row's right end (`RendererViewProps.navbarSlot`, null where no navbar
is drawn), and the CAD viewer's Display and Preview, for a 3D view, are portaled there, last.
A renderer that shows its file fullscreen (the CAD viewer's Preview) says so through
`onFullscreenChange(true)`, and `false` when it stops: the navbar, the box with it, steps
aside while it lasts, and the renderer draws its own controls where they sat (preview's
corner: Orbit, Display, Exit preview). The host's `captureRequest`
command is the same capture: to a composer destination it delivers the view and
the selection through `promptContext.deliver`. Neither route detects the platform.

`navigation.openFile(path)` shows a file, by its absolute path, in this view: a pick
in the explorer, a renderer's link. `navigation.home()`, where the host has a home,
shows it in this view: from a file, the app menu's Back to files (the menu the navbar's
logo opens) leads to it, and the home itself has no navbar. `CadViewer` implements both
over the host's `onShow(path)` (`''` is the home), and gives a host a home only with a
`library`: a host whose own navigation shows one file (Codex's file handler) passes none,
and its view shows that file and nothing else — no home, its menu no Back to files, no
explorer, and no `openFile`, so a renderer's link to another file (a robot's mesh) is plain
text there. A host that keeps a view's own history,
where no browser does (the CAD app's views), hands it as `history` (`ViewerHistory`:
`canGoBack`, `canGoForward`, `back()`, `forward()`; `CadViewerProps.history`): the navbar
draws Back and Forward over it. What the history holds is the host's (the CAD app's: every file
the view showed, the agent's shows and the person's moves alike, the home being no step); the
web hands none, its page having the browser's. `onShown(path | null)` says which file the catalog
has on screen (null for the home, or a file still resolving or missing), for a host that
names its page after it or records it. The host decides what showing a file means,
because only the host knows which view shows it: the web viewer is one page per machine
and writes the file into its URL (`?file=`, a new history entry, so the browser's back
and forward move between files, and a bare URL is the home), and the CAD app, which
renders in Codex (the sidebar, a tab beside each thread and a file handler) and inline in
Claude Desktop and other MCP Apps hosts, shows it in the view that asked or, from the
home, launches it.

## Adding a shared feature

1. Implement reusable interaction and presentation in UI, with cross-consumer
   non-React domain behavior in core. Renderer-private helpers such as
   [feature detection](feature-detection.md) stay with their renderer in UI.
   Keep project, session and operating-system workflows in apps.
2. Reuse an existing injected contract. If a new environmental effect is needed,
   extend its narrow consumer-owned interface and implement it in each app, or
   explicitly advertise that the host cannot perform it. Shared UI must not
   fall back to browser globals or branch on `isWeb`/`isDesktop`.
3. Use subscribed capability/destination state for availability and labels:
   Quick Edit offers only what the destination and the prompt port can do. Use
   a named additive slot for an extra app-enabled interface; the shared
   renderer never imports the app's component or stores.
4. Define identity, lifetime, cancellation and result semantics with the
   contract. Publish serializable view state through the controlled binding;
   the app chooses its storage. Keep workspace services stable across tab mounts.
5. Update this contract or its linked domain guide, add focused shared/adapter
   coverage and verify affected host integrations. Exercise source changes and
   late results for asynchronous effects, and warm reuse for resource changes.
   Run `npm run check:boundaries` and rebuild compiled packages before app checks.

Platform-agnostic UI can use DOM, canvas, React and renderer-owned workers.
Filesystem access, transport selection, credentials, clipboard, persistent
storage, page navigation and native process lifecycle remain host responsibilities.
So do a transport's limits: a host whose channel caps one reply declares the
most one batched read may ask for (`createCadClient({ maxBatchBytes })`), and the
shared loader never asks for more; the host carries a longer body in parts (the
CAD app's tunnel reads it a range at a time), and the loader sees it whole.

## Prompt handoff

Context actions use `PromptContextPort.deliver(context)`. Desktop
inserts into a compatible draft; web prepares clipboard representations. Ordinary
explicit copy/paste controls use the separate `ClipboardPort`. Delivery never
submits a prompt. `send(context)`, present only where the host has a chat to post
to, posts the context as the person's message now (`sent`); absent, nothing can
send one.

The portable types and validators live at `@text-to-cad/core/prompt`. One versioned
bundle contains ordered text, reference and attachment parts with unique IDs.
An attachment has a MIME type, name and Blob or Promise of Blob. Its optional
`about` array names reference-part IDs, so a screenshot and several selections
can travel together, and its optional `label` ("Sketch") says what it is for a
message that names it by path. Producers freeze resource and selection identity before
asynchronous capture. Blob URLs are delivery leases, never portable identity.

A reference contains a workspace-file identity (the file's absolute path,
`/`-separated: `/a/b.step`, `C:/a/b.step`; validation rejects any other spelling)
or HTTP(S) URL plus a tagged
selection: `whole-resource`, `text-range`, or `cad-selector`. Text positions are
zero-based UTF-16 with an exclusive end. CAD selectors use core's validated
cadgen grammar, not STEP entity numbers. Preserve a revision when available;
references do not promise to survive edits. Shared serialization handles quoting.

`formatPromptMessage(context, { attachmentPath })` is the one
message a Quick Edit is, whether sent, queued or copied: what the person wrote;
then `File: <path>`; then `References:` and one reference per line; then
`Sketch: <path>` (the attachment's label) when the picture travels as a file,
where `attachmentPath` says where it was saved. A picture sent beside the text
as an image block is not named.

`PromptContextAction` (a host renderer's prompt action) reads the subscribed
destination and labels the action Add to prompt or Copy for prompt. It calls delivery during the
user gesture, before awaiting capture: browser activation and desktop destination
binding depend on this. Availability and advertised attachment/combination limits
belong to the host. Every result is acknowledged: added, copied, sent, partial,
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

Quick Edit is the shared, host-neutral note to the agent
([the design system](settings-ui.md#quick-edit)), there while the person has it on
(`features.quickEdit`, above), and its buttons are what the host can carry out. **Copy Prompt** is always there: the message goes through
`ClipboardPort.writeText`, which takes a `Promise<string>` so the write starts
inside the gesture while a sketch is still being saved; its references name their
files by absolute path, as copied references do (below), and a sketch is saved through
`host.attachments` and named by path, since text cannot carry a picture (without
`attachments`, a copied prompt names none). **Queue** is there where the
destination is a composer (`destination.kind === "composer"`): `deliver`, the
context for the person's next message. **Send** is there where the prompt port
has `send`. The context is built at the press, from what is live then; a changed
document or revision never retargets it. A Quick Edit that reached its destination
(copied, queued or sent: no `failed` or `cancelled` receipt) tells the host once,
`usage.used('quickEdit')`, for its count; a host that throws there changes nothing.

`ViewerHost.attachments` is an `AttachmentStore`: `save(image, name)` answers the
saved file's absolute path. `createHttpAttachmentStore({ origin, fetch })` from
`@text-to-cad/core/client` is the viewer server's: it posts the PNG to
`POST /__cad/sketches?name=<name>`, which keeps it as scratch in the system's
temporary directory. Both apps pass one; the MCP app's reaches the server through
its tunnel.

## App-specific interfaces

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
`thumbnail({ width, height })` is a library card's picture: it waits for the view
to settle — the renderer's own live state saying the whole file is loaded and
drawn, never a timer — then draws the model framed whole from the default
direction at the card's aspect, on its own (no floor, grid or axes, whatever the
person turned on) and on transparency, so it suits either scheme, off to the side of the view, so
the person's camera, panels and window never show in it and nothing on screen
changes (`kit/viewport/thumbnail.js`; a DXF paints its fitted drawing on a canvas
of its own). A view that goes before it settles rejects it. `useModelThumbnail`
keeps one per revision of a file per mounted view (a model rebuilt while it is
open is pictured again once its new revision is drawn), and only for the file the
view still shows.
On the home, a card on screen with no picture, or one taken before its file last
changed (`pictured` against `modified`), is pictured out of sight wherever the host
keeps pictures (`onThumbnail`): `CadViewer` mounts a viewer of its own for it, over
its own client — its own renderers and live binding, compact, behind the page at the
picture's size — one model at a time, each once per visit, and only a model whose
artifact status is already `compiled`, and keeps the picture through `onThumbnail`
as it keeps the file on screen's. The home never builds anything: an unbuilt model
keeps its placeholder until a view shows it.
`readState().display` and `setDisplaySettings(patch)` use the same sparse grouped
schema as snapshots: `mode` selects `solid`, `render`, `xray`, `hidden-line`, or
`wireframe`; camera, surfaces, edges, lighting, background, floor, grid and axes
are independent groups. Patches merge fields within a group. A mode patch
reapplies that preset before its explicit group overrides; clipping and exploded
view remain independent tools. Custom is derived from the effective overrides,
not a sixth mode. `setRenderMode(true/false)` selects Render/Solid through that
same state. Grouped camera projection/lens changes preserve the viewport's pose
and zoom. Display Reset restores the selected preset and disables both tools.
`resetCamera` frames the model again without turning the camera — exactly what
STEP's context-menu "Zoom to fit" does. Cube shortcuts change only orientation.

A file's view holds its camera: a mount restores it in place of the fit, and fits
when there is none. Live
commands reject retired field names rather than maintaining a second display
authority. Unavailable selectors fail explicitly; topology is not silently
loaded. Mutations return a view snapshot after the React frame; a mode switch
waits for the requested settings to commit, with a ten-second bound.
Loading views
reject commands, and an operation whose resource/revision changes or viewport
unmounts before completion rejects its late result. On unmount, the controller
releases its component closure and retains only its final snapshot with
`active:false`; every subsequent command requires showing the model tab first.
Hosts may cache that inactive snapshot without retaining a scene or moving focus.

## Files, state and shutdown

`FileSource` reads files; `FileActions` holds the file menu's native operations
(Copy path, Reveal), and the viewer never writes a file. Both apps read any CAD
file on the machine by its absolute path, through the viewer server: what a view
lists and searches is the server's, and a request for a file that is not there is a
`cad-file-missing` error (`isMissingFileError`).

FileViewer opens a file's document when the file is shown, and again only on `reload`: a
renderer follows its file itself. A CAD renderer (its document from
`prepareWorkspaceEntry`) reads the live catalog entry, so a content change — or a write
that briefly empties the file — loads the next revision behind the model on screen, under
"Updating model…" (a drawing's: "Updating drawing…"). Once a model has been shown, a
rebuild is an update, never the loading screen.

State remains controlled through FileViewer props, and everything the viewer keeps
is the tab's (`@text-to-cad/ui/tab-store`): one record per tab, `{ version, settings,
files }` (`version` is `TAB_RECORD_VERSION`, 2; a record another version wrote reads as
the defaults), thrown out with the tab and kept across a reload. The host supplies where it
lives through one adapter, `TabRecordStorage` — a synchronous read and write of the
whole record: the web over `sessionStorage`, the CAD app over memory
(`memoryTabRecord`) — and the package owns the record's shape, version and normalization. `settings` is
`{ toolStack, appearance, library }`: tab-wide (the tool stack's layout, the
appearance, the home's layout), and what every renderer reads as its preferences;
`files` holds the view of the file on screen, under `[absolute path, renderer id]`, and no
other: a write keeps the newest alone (`TAB_FILE_LIMIT`), and `CadViewer` drops the view
of a file it leaves — for another file or for the home — once the
departing renderer's last write has landed (`files.retain(path | null)`; `null`, the home,
drops every view). The store reads and writes a view (`files.read`, `write`, `remove`),
lists them all (`all()`) and merges a view's changes (`merge`). A reload of the tab shows
the same file, so it brings that view back; a file opened again after leaving it starts
at the defaults. In the CAD app there is one record per view: a view the host
creates again (its frame re-created) starts afresh, since nothing names a view across its
frames. A view is `{ camera, display, playback, renderer }` (`kit/shell/fileView.js`):
the camera is restored in place of the open-time fit, the display settings with their
Clip and Explode, preview's settings (Orbit on or off and its speed, Autoplay, the
routine's chosen speed and loop), and the renderer's own slices each behind the
signature it was written against — a slice that no longer fits the file on screen is
dropped, the camera, the display and the playback never. Not in it, and started afresh
on every open: the tool in hand, the selection, measurements, ink, preview, a
routine's time and Quick Edit's note. Apps merge
what a view changed into the store (`files.merge`); a stale view must not overwrite
another view's entries. Material appearance is source-owned and read-only. Live
selection and scene ownership belong to the mounted view.

A mounted view writes its view shortly after each change (the camera on every move,
debounced) and once more when it unmounts, and nothing after that; the store writes
through synchronously, so what the tab last saw is what a reload restores. Nothing
saves document content or promises an asynchronous operation will finish during page
exit. Web owns pagehide
(which unmounts the app), focus, visibility, history and reload under a new server. Desktop
owns window/runtime lifecycle and IPC.

The dependency checker enforces host boundaries, including worker source. The
browser harness mounts real renderers with explicit fake hosts; app tests cover
native/clipboard delivery and multiple-view state merges. Warm-cache regression
tests remain required for resource changes.

## Keyboard scope

Viewer shortcuts consume only events from their own viewer, or from the page
background after a pointer press in it, so another viewer or the composer never
receives Escape, copy or orbit keys on its behalf
([settings-ui.md](settings-ui.md#keyboard)). The standalone
`DrawingEditor` takes the host's keyboard `platform` as a prop for its undo and
redo keys.

## Host chrome slots

FileViewer draws ONE navbar, the same in every app and over every file; a host's home
has none (it holds the links itself, under its title). Left: the text-to-cad "C" logo,
which opens the app menu (`AppMenu`, `file-viewer/navigation/AppMenu.jsx`), then Back and
Forward where the host hands a `history`, then the open file's name and its ⋯ menu. The
logo, Back and Forward, the name and the ⋯ share one style (`NAV_ITEM_CLASS`):
transparent at rest, the same accent background while the pointer is on them or their menu
is open, a pointer cursor, and no tooltip. The name opens the explorer where the host's
files can be browsed (`files.list` and `files.search`), and is plain text where they
cannot; the ⋯ offers Copy path and Reveal in Finder / Show in Explorer / Show in file
manager, each where `fileActions` can do it, and is absent where it can do none (no
right-click on the name). Right, only what a host or a file adds: the host's update button
first (`update`, while its install is behind), the renderer's navigation actions, the
host's Full size where it shows the view small
(`fullSize`, the inline card's way to full size, in the home's row too) and, last, the
renderer's view controls in their box (`navbarSlot`: a 3D view's Display and Preview). The
navbar holds no settings.

The app menu is FileViewer's, built from the host's `navigation.home`, `links` and
`environment.platform` and the person's `FileViewerProps.appSettings` (which `CadViewer`
passes on); the home has none. It is a dropdown on the floating surface.
First **Back to files**, where the host has a home; then
the host's on/off settings (`appSettings`, below) as checkbox items, checked at the right,
which a press turns without closing the menu; then, where the host has a tracker
(`links.issues`), **Send feedback**, a link to a new issue titled "Feedback: "
(`feedbackUrl`, `NavbarLinks.jsx`), for the person to finish, naming the version and
`environment.platform` — it has no label: the project has none for feedback, and what is
said may be a bug, a request or a question — then **GitHub** and **Discord**; and last, in
gray, "v<version> · Made by @<handle>": the version links its release notes
(`links.release`) and `MadeBy` the host's X account. The version is the release's own build's
as it is (`v0.7.15`), and any other build's with its id (`v0.7.15-dev.b80844940`, the commit
it was built from, `-dirty` with uncommitted changes): `viewerLinks({ version, build })`,
where each app's Vite config names the build through `@text-to-cad/ui/build-id`, and a new
issue names it the same way. The home has GitHub, which says the
project is open source, Discord and X as icon links under its wordmark (`HomeLinks`), in
that order.

An alert card's Report Issue opens a new issue too,
titled "Issue: " and labelled `bug`, filled in from the card (`kit/status/reportIssue.js`): its
title, message and failure, the file's name, the version and platform, then its Details, cut from
their end to keep the address, title and labels included, under `ISSUE_URL_MAX`. No path of the
machine goes with it: the file's path is its name wherever the card writes it, and a home
directory in anything else is `~/`. A label is a suggestion: GitHub applies a URL's labels only
for someone with triage access to the repository and drops them for everyone else. A link opens
the ordinary way unless the host supplies
`links.open` (a page in a sandboxed frame hands it to its host), which every link of the
menu follows. `displayActions`
passes host-owned appearance controls into the Display section beside Projection
via `RendererViewProps`. `appSettings` (`{ id, section, label, checked, disabled?, onCheckedChange }[]`,
a `CadViewer` prop) are the host's own on/off settings: checkbox items of the app menu, in the
order they come (Share anonymous usage data, Quick edit, in both apps), the same in the
logo's menu and the home's; nothing of them reaches a renderer, and Display holds none. The
host owns what each one does and where it is kept. `@text-to-cad/ui/features` is the
feature switches, which both apps share: `useFeatures(features)` turns the host's call — `features()`
reads them, `features(change)` changes some and answers them all — into the features the person
left on (`ViewerFeatures`: `quickEdit`, each on until they turn it off) and their `appSettings` rows.
The host hands the first to `CadViewer` as `features` (on to FileViewer and
`RendererViewProps.features`: the shell offers no Quick Edit while it is off) and the second
with its `appSettings`, and keeps the choice where it keeps the analytics answer: the web
Viewer and the CAD app alike through the client's `features` (`/__cad/features`), in the
person's settings (`cadgen/features.py`), so it holds in every view, tab and app, across
reloads — a page's own storage would not, the web Viewer's origin changing with its port.
`@text-to-cad/ui/consent` is the usage stats toggle both apps share:
`useAnalyticsConsent(consent)`, which turns the host's consent call into its `appSettings` row
(Share anonymous usage data). Nothing asks: cadgen's telemetry is on by default once a `cadgen` command
has said so. The host supplies the call and where the answer is kept.
`@text-to-cad/ui/update` is the update button both apps share, from cadgen's version check:
`UpdateButton`, the blue button a host hands the viewer as its `update` (`CadViewerProps.update`,
first among the navbar's right-hand controls over every file, an icon, and on the home a row of its own,
labeled Update), which opens its card in a popover, and `useUpdateNotice(call, initial)`, which
starts on the notice the host already has (a CAD app's launch carries it; the web page reads it with
its server's description), so the button draws with the page, and reads the host's call again when
the page regains focus. Nothing it does is an answer the server keeps: the button stays while the
install is behind and goes once the update lands. The card sends its prompt
to the agent's chat through the host's `send`, where the host can, and otherwise copies it through
`copy`, its button then Copy prompt; the prompt has a copy icon in its top-right corner either way; the host decides which it supplies. Its
Manual installation link, the notice's `instructions`, opens through the host's `onLink`. The shell
handles placement and hides the toolbar in
preview; the host owns callbacks and preferences. None of these imply platform
detection or move application-specific release/network behavior into shared UI.

The explorer is a popover under the file's name (`FolderExplorer.jsx`;
[FileViewer](file-viewer.md#the-navbar-and-the-explorer)): it floats over the view and
never resizes it.

A file that will not open leaves the navbar over a page of the host's
(`presentation.error`). `CadViewer`'s says "File does not exist" and the file's path
when it is missing (`isMissingFileError`), and "Could not open that file" and the
reason otherwise, each with a Go home button where the host has a home.

The viewport's corners are the shell's, never the host's: the tool strip and its
stack at the top-left, Quick Edit at the top-right, and the view cube at the
bottom-left; the view's own controls (Display and Preview, a 3D view's) are the navbar's
last. A host's one notice goes through the shell too: `notice` is drawn at the top-right once the
file is on screen, never while it loads or after it failed to, with Quick Edit stacked under
it while it stands; the home never shows it. Neither app has one now.
What Quick Edit offers follows the subscribed destination capability and
the ports, never an app name: Copy Prompt always, Queue for a composer
destination, Send where the prompt port has `send`. Native clipboard effects
remain in the host implementation.

STEP's Reference panel (Copy, or Copy All with several references) and Draw's
panel (Copy, once there is ink) use `ClipboardPort` directly, including on
desktop: the references as text, the view with its ink as a PNG through
`writeImage`. Their copy shortcut and double-click topology copy follow the same
path. Double-clicking a component or subassembly isolates it instead; only
non-isolatable topology references use double-click copying. The host supplies
`environment.platform` for the ⌘C / Ctrl+C hint; the web host derives that field
from its browser environment.

An alert card's Details have a copy icon in their box's top-right corner
(`kit/status/ViewerAlertCard.jsx`): it copies the whole of them, however far they scroll,
through `ClipboardPort.writeText`, and shows a tick for a moment. A host whose clipboard
refuses the write gets a line saying so under the box, where the text stays to select; a
view with no host clipboard gets no icon. Each host makes its port copy wherever it can: the
web falls back to the page's copy command when the browser refuses the asynchronous
clipboard, and so does the CAD app when its host grants its frame no clipboard.

A copied reference names its file by its absolute path (`<path>#<selector>`), and so
does a copied Quick Edit: every view spells a file the same way, so a reference pasted
into a chat or a tool says exactly which file it means.

Preview's playback bars centre on one line, `3.5rem` above the viewport's bottom
edge; nothing else sits at the bottom centre. A host whose own control floats over
that edge (a chat's composer) sets `--cad-viewport-bottom-center` on an ancestor
to put the line on its control's, and `--cad-host-bottom-inset` to the height it
covers: the model library scrolls its last rows clear of it. Both are lengths, like
any design token, and say nothing about which host it is.

A renderer's update status is its own: the CAD renderers show it centred at the
top of the viewport, level with the tool strip. The navbar carries none.
