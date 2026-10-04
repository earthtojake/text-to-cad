# Viewer host contract

`FileViewer` requires one explicit `ViewerHost` from `@text-to-cad/ui/host`.
Shared UI implements rendering and document interaction; apps supply environmental
effects. No shared feature discovers Electron, browser clipboard, a backend URL,
persistent storage or page navigation. DOM, canvas, workers and layout remain
shared. Missing optional methods mean an operation is unsupported.

The host contains `files`, optional native `fileActions`, `clipboard`,
`promptContext`, the optional `attachments`, `navigation` (with an optional
`home`), the optional navbar `links`, `environment` and the optional
live-document bindings `documents` and `pdf`. `environment` carries the resolved `colorScheme`,
the keyboard `platform` (`darwin` shows ⌘, anything else Ctrl), the app's own
`reducedMotion`, honoured beside the system's `prefers-reduced-motion`, and
`compact`: a host showing the view small, inline in a conversation, where a CAD
renderer draws the model alone — no tools, view actions, view cube or Quick
Edit — and FileViewer draws no navbar (the host offers its own way
to full size, where it drops `compact`). CAD is a separate registration supplied with a
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
| `ViewerHost`, `ClipboardPort`, `AttachmentStore` (where a copied prompt's picture is saved) | [Host types](../src/host/types.ts) | `@text-to-cad/ui/host` |
| `FileSource`, `FileActions`, mutation receipts, `FileViewerState` | [File viewer types](../src/file-viewer/types.ts) | `@text-to-cad/ui/file-viewer` |
| `PromptContextPort` (`deliver`, `send`), bundles, references, delivery receipts and `formatPromptMessage` (the one message a Quick Edit is) | [Prompt types](../../core/src/prompt/types.ts) | `@text-to-cad/core/prompt` |
| `CadWorkspaceService`, `CadResourceProvider`, worker tickets | [CAD service types](../../core/src/client/types.ts) | `@text-to-cad/core/client` |
| `createHttpAttachmentStore` (the viewer server's `AttachmentStore`: it saves a PNG through `POST /__cad/sketches`) | [Attachment store](../../core/src/client/attachments.js) | `@text-to-cad/core/client` |
| `StepRendererOptions`, `CadLiveBinding` | [STEP registration](../src/renderers/step/index.ts) | `@text-to-cad/ui/renderers/step` |
| `TabStore`, `TabRecordStorage`, `createTabStore`, `useTabViewerState` (the tab's one store: its settings, the view of the file on screen, and `FileViewer`'s state from both) | [Tab store](../src/tab-store/tabStore.ts), [the record](../src/tab-store/tabRecord.ts) | `@text-to-cad/ui/tab-store` |
| `CadPreferenceSource`, `createCadPreferences` (the tab's settings as renderers read them) | [Viewer preferences](../src/renderers/workspace/preferences.ts) | `@text-to-cad/ui/renderers/workspace` |
| `DxfRendererOptions` (2D drawings; declares no panel, and declines every camera, display and selection command) | [DXF registration](../src/renderers/dxf/index.ts) | `@text-to-cad/ui/renderers/dxf` |
| `GlbRendererOptions`, `LiveViewBinding`, `LiveViewController` | [GLB registration](../src/renderers/glb/index.ts), [live binding](../src/renderers/kit/shell/liveBinding.ts) | `@text-to-cad/ui/renderers/glb` |
| `MeshRendererOptions` (STL, 3MF), `LiveViewBinding`, `LiveViewController` | [Mesh registration](../src/renderers/mesh/index.ts) | `@text-to-cad/ui/renderers/mesh` |
| `RobotRendererOptions` (URDF, SRDF, SDF), `RobotLiveController`, `RobotLiveState` (`selectedLinks`, `selectedPartIds`) | [Robot registration](../src/renderers/robot/index.ts) | `@text-to-cad/ui/renderers/robot` |
| `ViewerCommands`, `ViewerCommandSource` (the host requests every viewer renderer takes) | [Viewer commands](../src/renderers/workspace/commands.ts) | `@text-to-cad/ui/renderers/workspace` |
| `createLiveRegistry`, `LiveRegistry` (the host's handle on the mounted view: its renderers' `live`) | [Live registry](../src/host/liveRegistry.ts) | `@text-to-cad/ui/host` |
| `ModelLibrary`, `ModelLibrarySource`, `ModelPictureSource`, `useModelThumbnail` (a host's home: the CAD title over the host's links, then the models opened before, pinned first, as cards or rows, and with none an "Open File" card that opens the chooser; placeholder cards or rows while the list is read (again every two seconds while the home is up, so a model rebuilt meanwhile is pictured again), and a spinner over the model being opened, which takes no second press until `open` settles; `pick` only where the host has a file chooser; `pictureFrom` where it can reach a model to picture it) | [Model library](../src/library/ModelLibrary.tsx), [thumbnails](../src/library/thumbnails.ts) | `@text-to-cad/ui/library` |
| `CadViewer` (FileViewer over one root's CAD catalog: the five CAD renderers, catalog following, the home, the loading and missing-file pages, the library's pictures) | [CAD viewer](../src/cad-viewer/CadViewer.tsx) | `@text-to-cad/ui/cad-viewer` |
| `createCatalogFileSource`, `createCadFileActions`, `rootPath`, `pathUnderRoot`, `referencePath` (a CAD catalog as a read-only `FileSource`, the file menu's copies and reveal, the paths a root names a file by) | [Catalog](../src/cad-viewer/catalog.ts) | `@text-to-cad/ui/catalog` |
| `ViewerLinks`, `viewerLinks` (the version, GitHub, Discord, where a new issue opens, the newest release and how to update, and how a link is followed), `issueUrl` (a new issue filled in — its title, labels and body — its address kept under `ISSUE_URL_MAX`) | [Host types](../src/host/types.ts), [links](../src/file-viewer/navigation/links.js) | `@text-to-cad/ui/links` |

Start with the actual compositions: [web App](../../../apps/web/src/App.tsx) and the
MCP app's [ModelView](../../../apps/mcp/src/ModelView.tsx), both one `CadViewer`.
Its imports lead to the app-owned `host/`, `adapters/` and persistence
implementations. [Web storage](../../../apps/web/docs/storage.md) documents
browser lifetimes. Shared component tests can
use the [explicit fake host](../src/host/testing/host.ts).

## What a CAD renderer does not use

A CAD renderer (STEP, GLB, mesh, robot, DXF) declares no `panels`, and reads none of
`RendererViewProps.openPanel`, `panelSlot` or `onPanelOpen`: its controls are panels of
its own tool stack over the viewport (`settings-ui.md#the-tool-stack`), and nothing it
does opens, closes or turns the host's explorer or panel column. FileViewer still hands every
renderer those props — they are the generic panel contract, which the file tree and
the desktop markdown's source view use. A host's stored `panel` naming the retired CAD
Settings panel (`cad-file`) resolves as nothing open. The tool stack's layout — the
sizes a person dragged the tree, the Reference and Position panels to, the folded panels
and whether the tree is closed — is one
of the tab's settings (`settings.toolStack` of the tab record, `@text-to-cad/ui/tab-store`),
beside the orbit speed and playback.

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
(`onFullscreenChange`, below): the navbar, with everything in it, the explorer and the
panel column step aside while it lasts. It never uses the browser Fullscreen API. The shell saves the tools view's camera, fits a preview camera and restores
the tools view's exact pose on exit; nothing of preview is persisted. Orbit
starts by default, with its speed, unless the file's Playback settings say otherwise:
they are the file's view's `playback` — orbit on or off and its speed, Autoplay, the
routine's chosen speed and loop — kept between previews and across a reload, and a
file's routine plays on entry only when its Autoplay is on. The rules are in
[settings-ui.md](settings-ui.md#camera-animation-and-preview).

A renderer can publish `FileNavigationAction[]` through
`RendererViewProps.onNavigationActionsChange`. The CAD renderers publish one, and only
while a person has put away an alert card the model survives: the card's own icon in its
colour, named after the alert, which brings the card back (`useAlertDismissal`,
`kit/status/ViewerAlertCard.jsx`). The
shared navbar shows these at its right, before any declared panel's toggle and the
host's links. Each action declares its icon, accessible label, an
optional shorter hover `hint`, disabled state and invocation callback. Registration belongs to the mounted
file generation: publish an empty list on cleanup; departing renderers cannot
replace a new file's actions. Publish only when action metadata changes; stable
commands should read the current viewport through a ref, avoiding parent/child
render loops. These actions use existing host capabilities for effects. What a
person tells the agent about a CAD file is [Quick Edit](#prompt-handoff)'s.

A renderer with controls of its own for the view draws them into
`RendererViewProps.navbarSlot`, at the navbar's right end after the host's Settings (the CAD
viewer's Display and Preview, for a 3D view); it is null where no navbar is drawn. A
renderer that shows its file fullscreen (the CAD viewer's Preview) says so through
`onFullscreenChange(true)`, and `false` when it stops: the navbar, the explorer
and any declared panel step aside while it lasts. The host's `captureRequest`
command is the same capture: to a composer destination it delivers the view and
the selection through `promptContext.deliver`. Neither route detects the platform.

`navigation.openFile(path, { target, panel })` shows a file in this view
(`"current"`) or in a new one, where the host has more than one (`"new"`).
`navigation.home()`, where the host has a home, shows it in this view: from a file,
the navbar leads with a back arrow to it, and the home itself has no navbar.
`CadViewer` implements both over the host's `onShow`, and gives a host a home only
with a `library`. `panel`
is the panel the file opens with: FileViewer asks for the tree (`"tree"`) for a
file picked in the tree, so the tree stays up while a person walks it. Without a
panel, a file shown in place or in a new view starts at `FileViewerState.panel:
null` (its own default), and a view already showing the file keeps what it has
open. The host applies it because only the host knows which view shows the file:
web writes it into its one view's state, and desktop into the tab it selects or
creates.

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
   coverage and verify affected host integrations. Exercise root changes and
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

A reference contains a workspace-file identity or HTTP(S) URL plus a tagged
selection: `whole-resource`, `text-range`, or `cad-selector`. Text positions are
zero-based UTF-16 with an exclusive end. CAD selectors use core's validated
cadgen grammar, not STEP entity numbers. Preserve a revision when available;
references do not promise to survive edits. Shared serialization handles quoting.
The web adapter maps workspace files to full served-root paths for external chats.

`formatPromptMessage(context, { resolvePath, attachmentPath })` is the one
message a Quick Edit is, whether sent, queued or copied: what the person wrote;
then `File: <path>`; then `References:` and one reference per line; then
`Sketch: <path>` (the attachment's label) when the picture travels as a file,
where `attachmentPath` says where it was saved. A picture sent beside the text
as an image block is not named.

`PromptContextAction` (the PDF renderer's prompt action) reads the subscribed
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
inside the gesture while a sketch is still being saved; its references are
spelled as copied references are (below), and a sketch is saved through
`host.attachments` and named by path, since text cannot carry a picture (without
`attachments`, a copied prompt names none). **Queue** is there where the
destination is a composer (`destination.kind === "composer"`): `deliver`, the
context for the person's next message. **Send** is there where the prompt port
has `send`. The context is built at the press, from what is live then; a changed
document or revision never retargets it.

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
changed (`pictured` against `modified`), is pictured out of sight where the host's
library says how (`pictureFrom(model)`: the CAD client that reads it, its path
there, and where the picture is kept): `CadViewer` mounts a viewer of its own for
it — its own renderers and live binding, compact, behind the page at the picture's
size — one model at a time, each once per visit, and only a model whose artifact
status is already `compiled`. The home never builds anything: an unbuilt model keeps
its placeholder until a view shows it. The MCP app's library draws from the model's
whole filesystem, whose lazy root reads only that file.
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

`FileSource` contains storage operations; `FileActions` contains native/menu
operations. Typed mutation receipts report committed changes independently of
caller cancellation. An abort after commit is not rollback. Content, metadata,
add, delete and move notifications have distinct meanings. Desktop reconciles
all affected tabs; web is a read-only CAD catalog, with no arbitrary filesystem
access or editing.

A document that follows its file itself is `live` (`PreparedDocument.live`; every CAD
renderer's, from `prepareWorkspaceEntry`, which a registration passes on whole): a
content change — or a write that briefly empties the file — never opens it again,
because its renderer reads the live catalog entry and loads the next revision behind
the model on screen, under "Updating model…" (a drawing's: "Updating drawing…").
Once a model has been shown, a rebuild is an update, never the loading screen. Only the
file going away (a delete, or a move) reopens a live document; a text document still
reopens on a content change, or marks a dirty draft stale.

State remains controlled through FileViewer props, and everything the viewer keeps
is the tab's (`@text-to-cad/ui/tab-store`): one record per tab, `{ version, settings,
files }`, thrown out with the tab and kept across a reload. The host supplies where it
lives through one adapter, `TabRecordStorage` — a synchronous read and write of the
whole record: the web over `sessionStorage`, the desktop over its per-tab store — and
the package owns the record's shape, version and normalization. `settings` is
tab-wide (the file tree's width and expansion, the tool stack's layout, the
appearance, the home's layout) and is what every renderer reads as its preferences;
`files` holds the view of the file on screen, under `[root, path, renderer]`, and no
other: a write keeps the newest alone (`TAB_FILE_LIMIT`), and `CadViewer` drops the view
of a file it leaves — for another file, for the home, or for another root — once the
departing renderer's last write has landed (`files.retain`). A reload of the tab shows
the same file, so it brings that view back; a file opened again after leaving it starts
at the defaults. In the CAD app the record is in memory, one per view: a view the host
creates again (its frame re-created) starts afresh, since nothing names a view across its
frames. A view is `{ camera, display, playback, renderer }` (`kit/shell/fileView.js`):
the camera is restored in place of the open-time fit, the display settings with their
Clip and Explode, preview's Playback settings (orbit on or off and its speed, Autoplay,
the routine's chosen speed and loop), and the renderer's own slices each behind the
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
(which unmounts the app), focus, visibility, history and development reload. Desktop
owns window/runtime lifecycle and IPC.

The dependency checker enforces host boundaries, including worker source. The
browser harness mounts real renderers with explicit fake hosts; app tests cover
native/clipboard delivery and multiple-view state merges. Warm-cache regression
tests remain required for resource changes.

## Keyboard scope

Monaco keeps its editor-local save binding. Viewer shortcuts consume only events
from their own viewer, or from the page background after a pointer press in it,
so another viewer or the composer never receives Escape, copy or orbit keys on
its behalf ([settings-ui.md](settings-ui.md#keyboard)). The standalone
`DrawingEditor` takes the host's keyboard `platform` as a prop for its undo and
redo keys.

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
and captures use the source identity and path, never the asset URL. The desktop's
PDF renderer is this port's consumer ([renderer contracts](renderers.md)).

PDF hosts may provide `host.pdf.assetBaseUrl`, an absolute trailing-slash URL
containing the pinned PDF.js `cmaps/`, `standard_fonts/`, `wasm/`, and `iccs/`
assets. Hosts bundle and serve these assets with their notices; shared UI never
discovers a CDN. These support predefined CJK encodings, standard fonts,
JPEG2000/JBIG2 images and color profiles. Hosts allowing WebAssembly should
permit its compilation in CSP without enabling JavaScript eval.

## Host chrome slots

FileViewer draws ONE navbar, the same in every app and over every file; a host's home
has none (it holds the links itself, under its title). Left: a back arrow to the home
(`navigation.home`) where the host has one, then the file explorer's toggle where the
host's files can be browsed (`files.list`), then the open file's name and its ⋯ menu,
which is the explorer's own entry menu for that file (no right-click on the name).
With no file open the name's place says "Select file" (words, not a control), and
the page says "Ask the agent to show a model". Right: the host's update button first (`update`,
while its install is behind), the renderer's navigation actions, any declared panel's toggle, then Settings,
the person's: FileViewer draws the control its composer hands it (`FileViewerProps.settings`)
over every file, just before the renderer's view controls and never among them, and `CadViewer`
hands it the Settings popover (`SettingsPopover`, `kit/shell/SettingsPopover.jsx`) the home has
too — one component, the same sections in both. It shows the version beside its title, the
host's own settings (`appSettings`, below) under it, then Feedback where the host has a
tracker (`links.issues`): a button, Open Issue, that opens a new issue titled "Feedback: " (`feedbackUrl`,
`NavbarLinks.jsx`), for the person to finish, naming the version and `environment.platform`
(`CadViewer` hands the popover the platform). It has no label: the project has none for
feedback, and what is said may be a bug, a request or a question. Its footer has "Made by @…"
(`MadeBy`, the host's X account) at its left and Discord and GitHub (`CommunityLinks`) at its
right. The home has GitHub (`GitHubLink`), which says the project is open source, and Settings
under its wordmark, in that order. An alert card's Report Issue opens a new issue too,
titled "Issue: " and labelled `bug`, filled in from the card (`kit/status/reportIssue.js`): its
title, message and failure, the file's name, the version and platform, then its Details, cut from
their end to keep the address, title and labels included, under `ISSUE_URL_MAX`. No path of the
machine goes with it: the file's path is its name wherever the card writes it, and a home
directory in anything else is `~/`. A label is a suggestion: GitHub applies a URL's labels only
for someone with triage access to the repository and drops them for everyone else. A link opens
the ordinary way unless the host supplies
`links.open` (a page in a sandboxed frame hands it to its host). `displayActions`
passes host-owned appearance controls into the Display section beside Projection
via `RendererViewProps`. `appSettings` (`{ id, section, label, checked, disabled?, onCheckedChange }[]`,
a `CadViewer` prop) are the host's own on/off settings: they are Settings' sections, one per
`section` the settings name (Analytics, in both apps), drawn as checkbox rows, the same in the
viewer's navbar and on the home; nothing of them reaches a renderer, and Display holds none. The
host owns what each one does and where it is kept. `@text-to-cad/ui/features` is Settings'
Features, which both apps share: `useFeatures(features)` turns the host's call — `features()`
reads them, `features(change)` changes some and answers them all — into the features the person
left on (`ViewerFeatures`: `quickEdit`, each on until they turn it off) and their Settings rows.
The host hands the first to `CadViewer` as `features` (on to FileViewer and
`RendererViewProps.features`: the shell offers no Quick Edit while it is off) and the second
with its `appSettings`, and keeps the choice where it keeps the analytics answer: the web
Viewer through its server's `/__cad/features`, the CAD app through `cad_features`, both in the
person's settings (`cadgen/features.py`), so it holds in every view, tab and app, across
reloads — a page's own storage would not, the web Viewer's origin changing with its port.
`@text-to-cad/ui/consent` is the analytics
prompt both apps share: `ConsentCard` (the card) and
`useAnalyticsConsent(consent)`, which turns the host's consent call into the card's state, its
answer and the Analytics setting; the host supplies the call and where the answer is kept.
`@text-to-cad/ui/update` is the update button both apps share, from cadgen's version check:
`UpdateButton`, the blue button a host hands the viewer as its `update` (`CadViewerProps.update`,
first among the navbar's controls over every file and first in the home's row), which opens
`UpdateCard` in a popover, and `useUpdateNotice(call)`, which reads the host's call, again when the
page regains focus. Nothing it does is an answer the server keeps: the button stays while the
install is behind and goes once the update lands. The card sends its prompt
to the agent's chat through the host's `send`, where the host can, with a Copy prompt icon beside it
(`copy`), and otherwise copies it through `copy` alone; the host decides which it supplies. Its
Manual installation link, the notice's `instructions`, opens through the host's `onLink`, as the
`ConsentCard`'s privacy policy does through `onPolicy`. The shell
handles placement and hides the toolbar in
preview; the host owns callbacks and preferences. None of these imply platform
detection or move application-specific release/network behavior into shared UI.

The explorer floats over the body's left (`FileExplorer.jsx`), inset like the
tool strip and above it, and never resizes the view; a file's declared panels open
in the column at the body's right (`FilePanelColumn.jsx`). One panel is open at a
time, the explorer included.

The viewport's corners are the shell's, never the host's: the tool strip and its
stack at the top-left, Quick Edit at the top-right, and the view cube at the
bottom-left. A host's one notice goes through the shell too: `notice` (the
`ConsentCard`) is drawn at the top-right once the
file is on screen, never while it loads or after it failed to, with Quick Edit stacked under
it until it is answered; the home never shows it. The view's own controls (Display and Preview, a 3D view's) are the
renderer's, drawn into the navbar's right end after Settings (`navbarSlot`).
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

A copied reference names its file as the host's `FileSource.referencePath(path)`
spells it, and so does a copied Quick Edit; a source without one leaves the
file's path under its root. A root whose relative paths mean nothing outside the
viewer (a whole filesystem) gives the absolute path. The host decides because
only it knows its root.

Preview's playback bars centre on one line, `3.5rem` above the viewport's bottom
edge; nothing else sits at the bottom centre. A host whose own control floats over
that edge (a chat's composer) sets `--cad-viewport-bottom-center` on an ancestor
to put the line on its control's, and `--cad-host-bottom-inset` to the height it
covers: the file tree and the model library scroll their last rows clear of it,
and a revealed row stops above it. Both are lengths, like any design token, and
say nothing about which host it is.

A renderer's update status is its own: the CAD renderers show it centred at the
top of the viewport, level with the tool strip. The navbar carries none, and a host
that shows one file without naming it, browsing it or linking anywhere gets no row.
