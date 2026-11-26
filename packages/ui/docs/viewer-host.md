# Viewer host contract

`FileViewer` requires one explicit `ViewerHost` from `@cad/ui/host`.
Shared UI implements rendering and document interaction; apps supply environmental
effects. No shared feature discovers Electron, browser clipboard, a backend URL,
persistent storage or page navigation. DOM, canvas, workers and layout remain
shared. Missing optional methods mean an operation is unsupported.

A view shows a file by its absolute path, or a document the engine holds by its id alone (a
model's: a lower-case UUID, `cad.engine.ids`). A file's metadata may carry `navigationPath`,
the on-disk file to act on; null says the document has no file of its own (a
model's), and then `sourceFile`, where given, is the file it is built from (a model's script, its
envelope's `source.path`): its file menu's Copy path and file manager act on that; with neither,
its file menu has only what needs no file (Browser, Export). `sourceMissing`
says the source was moved or deleted (the envelope's `source.present` false): the menu keeps Copy path
and draws what opens the source disabled with its reason, never an error. A model's navbar and Preview's bar name it by its `name`, with no glyph.
A document in a project (`FileViewerProps.project`: a folder a person opened as one, which a document is in by its
file, a model by its `.xbf`) has the project's name before its own in the navbar, and `[` and `]` move through the
files of the folder it is in; the search (⌘K) reaches the whole project on screen and every document of the library. Nothing browses the disk outside a project. Python scripts are never
documents: no view opens one, and no project lists one.

The host contains `files`, optional native `fileActions`, `clipboard`,
`promptContext`, the optional `promptFiles` (the folders a message names this computer's files from), the optional
`promptSubject` (what a prompt names the document on screen by: [Prompt handoff](#prompt-handoff)), `navigation` (the optional `openFile(path)` and
`home()`), the optional `links` (the app menu's), the optional `usage`
(`used(feature)`: what the person used, for the host's telemetry to count, never what
they made; absent, nothing is counted; and `controls(counts)`: which of the view's controls a
person used, counted once by the shared UI for every host — see below) and `environment`. `environment` carries the resolved `colorScheme`,
the resolved `locale` (the language the view reads in: the person's choice, else what the
context infers, as `@cad/ui/i18n`'s `useLanguage` resolves it; none, or one the viewer
does not speak, reads English),
the keyboard `platform` (`darwin` shows ⌘, anything else Ctrl), the app's own
`reducedMotion`, honoured beside the system's `prefers-reduced-motion`, and
`compact`: a view drawn small with no chrome (a small inline view), where a CAD renderer draws the model alone — no tools, view actions,
view cube or Quick Edit — and FileViewer draws no navbar. A view shown small in a
conversation is not compact: it is the whole viewer under its navbar, and its host hands
its own way to full size as a navbar action (the CAD app's Full size, `CadViewerProps.fullSize`).

`fileActions` is what the host can do with the document on screen, each a capability the file
menu (the navbar's ⋯) offers only where it is given: `copy-path` and `reveal` act on its file on
disk (a model's: its script, `sourceFile`), and `browser` opens the document's page in the person's
browser (its path or a model's id; the CAD app's, where a launch carried the web viewer's page).
The ⋯ draws them as Copy path, Copy link and Open in › Browser and the file manager by its name; a home
card's ⋯ offers Copy path, Copy link and Reveal (a model's card, Copy link alone). `copy-link` copies
the document's page with its link, `<engine origin>/<document id>?token=<link>`; an entry may carry
its document's `id` (a home card's does). `createCadFileActions({ link: { origin, client } })` makes it
from a CAD client's `link()` (`GET /api/v1/local/link`) and `entryOf`: the web viewer hands its page's
origin, the CAD app the engine's origin from its launch (never its tunnel's), its link asked
through the tunnel. A host that cannot make a link offers no Copy link. A host that can open the document's files in this
computer's apps adds `apps(entry, { signal })` — the files (`source`, a model's `export:<format>`s),
whether each is on disk and the apps that take it (`OpenInFiles`, `GET /api/v1/local/open-in`'s
answer; asked as the menu opens, null or a failure and the menu is as without; an app with `refuses`,
a KiCad older than the file's format, is drawn disabled with the reason, and a target's `default: false`
leaves out Default app) — and
`openApp(entry, target, app)`, which opens one in an app or in `"default"`, the OS's own: both or
neither, the entry named as the document is (its path, a model's id). `createCadFileActions({ openIn: client })`
makes both from a CAD client (`openInApps`, `openIn`, a file's id from `entryOf`); the web viewer
hands its client, the CAD app its tunnel's. A host with neither shows Open in without apps.
CAD is a separate registration supplied with a
`CadWorkspaceService`; the generic FileViewer does not import CAD. The HTTP CAD
adapter serves both apps; the engine owns runtime startup and recovery.
See [workspace resources](../../core/docs/workspace-resources.md) for resource
tickets and cache identity.

A host passes no tolerance to a renderer: an engine document's parts (an `.xbf`'s, a STEP's)
are drawn at the meshes the engine made of them.

Apps create services for the workspace lifetime. File tabs borrow them, while
mounted renderers own scenes, document controllers and temporary resource leases.
Unmounting one view releases its work without disposing another view's services
or admitted cache writes. Hosts dispose a service when its workspace closes.

`FileViewer`'s optional `presentation.error` receives `message`, `missing`, `error`
(what the source raised, for a host to read its own fields on), and `reload`, which rereads only the file that produced the error; a callback from a
departed file cannot reload its replacement.

## Interface map and implementations

The linked TypeScript definitions are the authoritative signatures. Import
their compiled public package exports in application code; these source links
are for reading and maintaining the contracts.

| Contract | Definition | Public entry point |
| --- | --- | --- |
| `ViewerHost`, `ClipboardPort`, `PromptFiles` (the folders a Quick Edit's message names files from), `usage` | [Host types](../src/host/types.ts) | `@cad/ui/host` |
| `FileSource` (`stat`, and `list` and `search` where the host has them), `FileActions`, `FileViewerState` | [File viewer types](../src/file-viewer/types.ts) | `@cad/ui/file-viewer` |
| `PromptContextPort` (`deliver`, `send`), bundles, references, delivery receipts, `formatPromptMessage` (the one message a Quick Edit is) and `snapshotPacket` (its snapshot packet, made in the page) | [Prompt types](../../core/src/prompt/types.ts) | `@cad/core/prompt` |
| `CadWorkspaceService` (the catalog of the files on screen, and what a renderer reads of a document; `projectFolder`, the folder of its project a document is in; `setModelParameters`, the Params tab's Save, and `previewModelParameters`, the model drawn at its drafts before a Save, each optional: a host that cannot carry one leaves it out, and the tab shows values without Save, or a value only once it is saved), `CadClient` (the HTTP one, `createCadClient` (`{ origin, fetch, … }`), with what only a server and its engine answer: the library, the projects, the person's settings), `openViewBundle` (the same service over a view bundle: [below](#a-view-bundles-host)), `isMissingFileError`, `CadResourceProvider`, worker tickets | [CAD service types](../../core/src/client/types.ts) | `@cad/core/client` |
| `createHttpPromptFiles` (the viewer server's `PromptFiles`: its workspace and the person's home, from `GET /api/v1/server`) | [Prompt files](../../core/src/client/promptFiles.js) | `@cad/core/client` |
| `createXbfRenderer` and its `XbfRendererOptions` (a model, held or its `.xbf`, and a STEP), `LiveViewBinding`, `LiveViewController` | [Xbf registration](../src/renderers/xbf/index.ts) | `@cad/ui/renderers/xbf` |
| `TabStore`, `TabRecordStorage`, `createTabStore`, `useTabViewerState` (the tab's one store: its settings, the view of the file on screen, and `FileViewer`'s state from both) | [Tab store](../src/tab-store/tabStore.ts), [the record](../src/tab-store/tabRecord.ts) | `@cad/ui/tab-store` |
| `CadPreferenceSource`, `createCadPreferences` (the tab's settings as renderers read them) | [Viewer preferences](../src/renderers/workspace/preferences.ts) | `@cad/ui/renderers/workspace` |
| `DxfRendererOptions` (2D drawings; declines every camera, display and selection command) | [DXF registration](../src/renderers/dxf/index.ts) | `@cad/ui/renderers/dxf` |
| `BoardRendererOptions` (KiCad boards, drawn flat; declines camera and Display commands), `BoardLiveController`, `BoardLiveState` | [Board registration](../src/renderers/board/index.ts) | `@cad/ui/renderers/board` |
| `GlbRendererOptions`, `LiveViewBinding`, `LiveViewController` | [GLB registration](../src/renderers/glb/index.ts), [live binding](../src/renderers/kit/shell/liveBinding.ts) | `@cad/ui/renderers/glb` |
| `MeshRendererOptions` (STL, 3MF), `LiveViewBinding`, `LiveViewController` | [Mesh registration](../src/renderers/mesh/index.ts) | `@cad/ui/renderers/mesh` |
| `RobotRendererOptions` (URDF, SRDF), `RobotLiveController`, `RobotLiveState` (`selectedLinks`, `selectedPartIds`) | [Robot registration](../src/renderers/robot/index.ts) | `@cad/ui/renderers/robot` |
| `ViewerCommands`, `ViewerCommandSource` (the host requests every viewer renderer takes) | [Viewer commands](../src/renderers/workspace/commands.ts) | `@cad/ui/renderers/workspace` |
| `createLiveRegistry`, `LiveRegistry` (the host's handle on the mounted view: its renderers' `live`) | [Live registry](../src/host/liveRegistry.ts) | `@cad/ui/host` |
| `documentTarget`, `folderPlace` (the one place a link, Open in new tab and the search name a document, by its id else its path, and a project's folder, as a place on the home; `navigation.hrefOf` turns each into the host's address) | [Addresses](../src/host/addresses.ts) | `@cad/ui/host` |
| `ModelLibrary`, `ModelLibrarySource`, `LibraryProject`, `LibraryFolder`, `LibraryFolderRef`, `ImportedProject`, `ImportedFileOrProject`, `LibraryNavigation`, `LibraryOrigin`, `LibraryPanel`, `LibraryFrame`, `samePlace`, `sortDocuments`, `useModelThumbnail`, `ageLabel`, `lastActivity` (a host's home, under the navbar, laid out as [the home](viewer-ux.md#the-home) says: in the navbar's slots the search and, where the host gives a chooser, Import: one button opening `importAny` where it is given (a computer whose one chooser takes a file or a folder, a Mac's), else File… (`pick`) and Folder… (`importFolder`); one place at a time (`place`, a `HomeLocation`: the host's where it keeps one, else the home's own from Recents; `onPlaceChange` as the person goes to one; `onPlaceShown`, its name as the person reads it) — Recents (`list()`), Starred (its rows' `pinned`) or one folder of a project (`folder(project, { path })`: its subfolders and every file in it; with `q`, every file below it that holds the words, flat) — chosen in its sidebar, the viewer's panel over the home (what the person chose of it handed to the host: `panel`, `onPanelChange`, a `LibraryPanel`), its projects (`projects()`) under a "+" that is `importFolder`; a project's ⋯ with Remove from CAD (`removeProject`); Sort (`sort`, `onSortChange`) and grid or list (`layout`, `onLayoutChange`); each document a card or a row, opened by `open`, starred by `change` (`"pin"`, `"unpin"`), its picture `thumbnail(model)`, its ⋯ from `fileActions`; a file that is no document (`documentKind: null`) a tile after the cards or a row after the documents', opened in an app through `fileActions`; `navigation` (`hrefOf`, `openBeside`): real links, and Open in new tab or Open in browser; `from` (a `LibraryOrigin`: the document just left) rings its card, with "Back to <name>" and Escape calling `onBack`; after a folder is imported the home goes to that project's page with a line saying what came of it) | [Model library](../src/library/ModelLibrary.tsx), [its places](../src/library/LibraryPlaces.jsx), [thumbnails](../src/library/thumbnails.ts) | `@cad/ui/library` |
| `CadViewer` (FileViewer over a CAD client, one file by absolute path or the home: the six CAD renderers, catalog following, the home, the "File does not exist" and "Could not open that file" pages, the library's pictures) | [viewer](../src/cad-viewer/CadViewer.tsx) | `@cad/ui/cad-viewer` |
| `createCadFileSource` (a CAD client as a read-only `FileSource`: `stat` through the client's `resolveEntry`), `createCadFileActions` (the file menu's Copy path, the absolute path, and Reveal, Open in's file manager), `normalizePath`, `baseName`, `joinPath`, `contentRevision` | [Catalog](../src/cad-viewer/catalog.ts) | `@cad/ui/catalog` |
| `ViewerLinks`, `viewerLinks` (the version, X, GitHub, Discord, where a new issue opens, and how a link is followed), `issueUrl` (a new issue filled in — its title, labels and body — its address kept under `ISSUE_URL_MAX`) | [Host types](../src/host/types.ts), [links](../src/file-viewer/navigation/links.js) | `@cad/ui/links` |
| `buildId` (for an app's Vite config: which build this is, "" for the release's own, whose environment names its version in `CAD_RELEASE`, else the checkout's commit) | [Build id](../scripts/build-id.mjs) | `@cad/ui/build-id` |

Start with the actual compositions: [web App](../../../apps/web/src/App.tsx) and the
MCP app's [ModelView](../../../apps/mcp/src/ModelView.tsx), both one `CadViewer`.
Its imports lead to the app-owned `host/`, `adapters/` and persistence
implementations. [Web storage](../../../apps/web/docs/storage.md) documents
browser lifetimes. Shared component tests can
use the [explicit fake host](../src/host/testing/host.ts).

## Export destinations and jobs

`ViewerHost.downloads` is an optional `DownloadPort`: `save(url, filename)` hands the
browser a ready job's same-origin file URL (`ExportService.fileUrl`) as a plain download,
so the browser's own download setting decides where it goes. Optional `remember`/`restore`
persist the page's export records (request, filename, whether the file was handed over),
never a file, handle or server path. A request names the session's epoch
(`ExportService.epoch`, asked as its export starts), so a record restored after the server
restarted is refused, never run again. No shared UI detects a browser or writes to the host
filesystem.

`CadViewer` combines that port with `CadWorkspaceService.exports` (`ExportService`).
Both are required to show Export. A host whose page cannot make a browser download
omits the port: the MCP host has no HTTP origin (every request is a `cad_http` call), so
it has no Export. The XBF renderer publishes only the displayed document and revision:
Export writes the document as its code built it, so the menu offers formats alone, never a
selection or a pose, and the formats follow from the file's kind (`export/formats.ts`), so it
has nothing to load; it says too whether its scene lies flat on z=0 (`planar`), which adds DXF. The GLB and mesh renderers publish the file shown: its path as the
document and the catalog hash of the bytes on screen as the revision, which the server checks
before it converts the file to the other mesh kinds. `FileViewer.navbarActions`, `fileMenuItems` and `overlay` are named
composition slots: the first is the navbar's right group, outermost (the CAD app's Full size, its one control now; kept as the host's slot); the second is the end of the file's ⋯ menu,
after Copy path and Open in (`CadViewer` puts Export's submenu there); the third is in the
relative viewport below it. The generic FileViewer knows nothing about export jobs.

## A CAD renderer's controls

The controls of every view (an engine document's, GLB, mesh, robot, and a DXF's, a board's and a schematic's alike)
are its own, over the viewport, in the one frame (`kit/shell/ViewFrame.jsx`): its
tool strip, the tool in hand's sub-toolbar and its docked panel (a phone's sheet), the corner's control, Quick Edit,
its view's settings (under a file's navbar Display, whose card docks at the view's right edge — a DXF's and a
schematic's the Background alone — and, for a 3D view or a board, Preview, the same on a phone) and, in Preview,
Preview's own bar
([Camera, animation and Preview](viewer-ux.md#camera-animation-and-preview)). The layout a person gives the tool stack's panels is one
of the tab's settings (`settings.toolStack` of the tab record, `@cad/ui/tab-store`),
beside the appearance and the home's layout; the panel — open or collapsed by the person (a choice that then holds on
that file at any window width; what the view's width does is not kept, nor a peek), its width (200 to 480px) and its
tab — is the file's, kept in its view as its camera is (`file-viewer/filePanel.js`, merged
into the renderer's record by `FileViewer`).
The model area is drawn in **the viewport's theme**, not the host's `colorScheme`: the person's Background
(`settings.viewportBackground` of the tab record: Light by default, or Dark), resolved by
`kit/look/useViewportTheme.js` over `@cad/core/lib/viewportTheme.js`; a renderer draws its scene and its picture in
its `scheme` and hands it to its frame, which scopes the canvas box and the corner to it
([the viewport's scheme](design-system.md#the-viewports-scheme)). A host's appearance still themes the chrome.
Every list a renderer puts in its panel (a tab of the `sidebar`) is built of the STEP/xbf Model tree's
base components, in `@cad/ui/primitives/tree-row` and `@cad/ui/primitives/tree-filter` (the row, its one
glyph slot, its name and detail, a heading, the search's lit match and count) and `VirtualRows`: a new
renderer's list adds a prop or a slot to those, never a row of its own
([the panel's trees](viewer-ux.md#trees)).

## Preview and renderer navigation actions

Preview is the shared shell's own state (`previewing`); there is no host
prop for it and a host cannot start or observe it. It is a 3D view's, and each
renderer says whether its view is one: it declares `previewable` to the shell
(`useRendererShell`), as an engine document (an `.xbf`, a STEP), GLB, STL/3MF and URDF/SRDF do. A KiCad board has it
too, the board shown in 3D as it is made, lit (`kit/shell/useFlatPreview.jsx`): the same state, button, bar and
settings, with nothing more for a host to do. A view that does
not — a DXF's 2D drawing or a schematic, which draw their own surface without the shell — has no
Preview at all, no control and not a disabled one, and nothing that asks for it
(a link or a host request, should either come to) takes it there: it keeps
the normal view. The CAD app's Full size, inline, is the host's display mode, not
Preview: it shows the normal view, of any file. Preview hides the navbar, in every host:
the renderer tells FileViewer (`RendererViewProps.onPreviewChange`), never the host, which
is not told it is on. In its place Preview draws its own bar — the file's name, Preview
settings and Exit preview — and leaving gives the host's chrome back as it was.
Preview and the tools view are two states: entering leaves the tools view's state as it
is (the pose, the routine, the selection, hidden and isolated parts, Explode and Clip,
measurements, the camera, the tool and its panels) and Preview starts from the model as
authored, with its own camera, still, and its routine at rest, drawn in Render whatever the
file's display mode (the tools view never draws Render); leaving throws Preview's state
away and gives the tools view back exactly as it was, its routine included, in the file's
mode. Preview is a view of its own, mounted over the tools view's while it is open
(`kit/shell/PreviewView.jsx`), with its own scene, camera, pose and routine, sharing only the
page's GPU device; the tools view's viewport stays mounted under it and nothing of it changes.
Nothing of Preview's state — its camera, pose, routine, whether it orbits — is persisted; its
Render settings are the file's view's (`preview`). Routines play from the panel's Animation tab in
the tools view (`AnimationSection.jsx`; a mechanism's motion from the top of its Joints tab; no playbar there) and
from Preview's playbar in Preview (`PreviewPlaybar.jsx`). Preview opens still: Orbit is off every time it opens, and its settings panel turns it
on. The file's view's `playback` — Orbit's speed, the chosen speed and loop —
is kept between visits to Preview and across a reload, and a file's routine opens at rest:
only the person plays it. The rules are in
[viewer-ux.md](viewer-ux.md#camera-animation-and-preview).

A renderer can publish `FileNavigationAction[]` through
`RendererViewProps.onNavigationActionsChange`. The CAD renderers publish one, and only
while a person has put away an alert card the model survives: the card's own icon in its
colour, named after the alert, which brings the card back (`useAlertDismissal`,
`kit/status/ViewerAlertCard.jsx`). The
shared navbar shows these first at its right, before the host's actions, outermost. Each action declares its icon, accessible label, an
optional shorter hover `hint`, disabled state and invocation callback. Registration belongs to the mounted
file generation: publish an empty list on cleanup; departing renderers cannot
replace a new file's actions. Publish only when action metadata changes; stable
commands should read the current viewport through a ref, avoiding parent/child
render loops. These actions use existing host capabilities for effects. What a
person tells the agent about a CAD file is [Quick Edit](#prompt-handoff)'s.

A renderer's controls for the view are the renderer's own: the viewer's for a 3D view, under a file's navbar
portalled into its view slot (Display, then Preview), the cube alone at the top-right;
and in Preview its bar's Display and Exit preview, the navbar hidden. The host draws none of them. The host's `captureRequest`
command is the same capture: to a composer destination it delivers the view and
the selection through `promptContext.deliver`. Neither route detects the platform.

`navigation.openFile(path)` shows a file, by its absolute path (or a document by its id), in this view: the
project's previous or next (`[`, `]` and the file menu), a renderer's link. `navigation.home(location?)`, where the host has a home,
shows it in this view, at a place on it where one is named (a `HomeLocation`: `{ view: "recents" | "pinned" |
"standalone" }`, or `{ view: "project", project }`, a project's page; Recents with none): the navbar's logo leads to
it, from a file, from a page still loading or that failed, and over the home itself (Recents). Where the host also gives
the home an address (`navigation.hrefOf({ home: { view: "recents" } })`), that logo is a real link to it, and a
modified or middle click is the browser's; without one it is a button. `CadViewer` implements both
over the host's `onShow(path, place?)` (`''` is the home, at `place`), and gives a host a home only with a
`library`: a host whose own navigation shows one file (Codex's file handler) passes none,
and its view shows that file and nothing else — no home, its logo the app menu's button (below), no
project, and no `openFile`, so a renderer's link to another file (a robot's mesh) is plain
text there.

The home's place is the host's to keep where it can name one: `CadViewerProps.place` (the web's from its address, the
CAD app's from its view's history); a host that passes none leaves it to `CadViewer`, which starts at Recents.
`onHomeShown(place, name)` says the place on screen by its name as the person reads it ("Recents", a project's), for
a host that titles its page with it. The navbar's project name, pressed over a document, shows that project's page
(`home({ view: "project", project })`) with the document remembered: the home rings its card and offers the way back
(`ModelLibrary`'s `from` and `onBack`), until another document is shown or the home is at another place.

Two things only a host knows, it hands in its ports (`CadViewerProps.host.navigation`, both optional), and `CadViewer`
passes them on in the viewer's `navigation` and to the home:

- `hrefOf(target)`: a target's own address, for a real link. A `NavigationTarget` is `{ document }` (its id; one
  whose row carries none, its path) or `{ home: HomeLocation }`. Null for a target with no address. With it, the home's
  cards, rows and sidebar rows are `<a href>` and the navbar's project name is a link (`FileProject.href`): a plain
  click shows the target in this view, and the browser's own ways open it in a new tab. A host whose pages have no
  address (a page in an app's frame) leaves it out, and every one of them is a button.
- `openBeside`: `{ kind, open(target), places? }`, a target opened beside this view, which stays as it is. `kind` is
  the item's words: `"tab"` (Open in new tab) or `"browser"` (Open in browser). `places: false`: documents alone, and
  a project's menu has no such item. A host that keeps a view's own history,
where no browser does (the CAD app's views), hands it as `history` (`ViewerHistory`:
`canGoBack`, `canGoForward`, `back()`, `forward()`; `CadViewerProps.history`): the navbar
draws Back and Forward over it, over a file and over the home alike. What the history holds is
the host's (the CAD app's: every file the view showed and each place of the home the person went to, a step like a
file, the agent's shows and the person's moves alike); the web hands none, its page having the
browser's, where each place of the home is a step too. `onShown(path | null, id | null)` says which file the
catalog has on screen, by its own path (a model by its id), and its document's id (null for the
home, or a file still resolving or missing), for a host that names its page after it or records
it. The navbar names a file by its catalog row's name (`CadViewerProps.name`, `FileViewerProps.name`: the host's
name for it where it knows one first) while it opens, then by the name its source read; a file with none, by its
path's last segment; a document named by its id, never by the id: its name's place is empty until a name is known. `CadViewer` joins the catalog's rows by that id (`client.entryOf`), not by the path the host
asked for, so a symlinked or case-variant spelling of one file is one row. The host decides what
showing a file means, because only the host knows which view shows it: the web viewer is one
page per engine and addresses every document by path, `/<id>` (a file opened by its path is asked
for its id first; a new history entry, so the browser's back and forward move between documents,
and `/` is the home), and the CAD app, which
renders in Codex (the sidebar, a tab beside each thread and a file handler) and inline in
Claude Desktop and other MCP Apps hosts, shows it in the view that asked or, from the
home, launches it.

## A view bundle's host

A view bundle (a share's view, which `cad share` has the server write) is one document's answers, written
down: a host shows it with no engine behind the page, through `openViewBundle(source)` (`@cad/core/client`),
the second implementation of `CadWorkspaceService`, whose source is a share's packs or the files held in the
page. The view is `CadViewer` with no `library`: one document and nothing else. Every
tool computed in the page works as over an engine (the display styles, Explode, Clip, Select and selection by
name, Measure, whose exact values are the part's table of facts, the joints, poses and motions, Draw and
Preview). What needs an engine is left out where it is read, by the capability each already rests on, so a
tool the document cannot use is absent, never drawn disabled:

- **Parameters** are read only, as an `.xbf` opened as a file shows them ("Edit these in the script."): the
  bundle's engine document is read as the document written down, and the service has no
  `setModelParameters` or `previewModelParameters`.
- **No next version**: its engine document is `final`, so the view reads it once and waits on nothing.
- **No Export**: the service has no `exports` and the host no `downloads`.
- **No home, Recents, projects, Open, Open in, Reveal, Copy path or Copy link**: no `library`, a file source
  that only reads its one document (`createCadFileSource`), no `projectFolder` to step through, and no
  `fileActions`, so the navbar draws no ⋯.
- **Quick Edit** keeps Copy alone (the clipboard is the destination; no composer, no `send`), and carries its
  snapshot packet as every page does (the page makes it); with no `promptFiles`, its message names its file by
  the host's `promptSubject` (below).
- **The person's settings** are the host's to keep where it can: the web keeps the language in the
  browser ([storage](../../../apps/web/docs/storage.md)); there is no Telemetry and no What's new.

## A shared view bundle's host

A shared view bundle is a view bundle a share service keeps, sealed, for anyone with its link, which is the
share's address alone, beside the files that made it (a model's `.xbf`, its code and the files its build read; a
file document's file), which `cad import <link>` gets. Its host is the view bundle's host above, unchanged: the web's
share mode (`/<id>`, [apps/web](../../../apps/web/README.md#a-shared-view-bundle)) opens it with
`openShare(id, service)` (`@cad/core/client`), which reads the share's manifest from the page's own origin, then
each file of the view from the packs it lies in, fetched once each and kept by the browser (never a pack only the
files that made it lie in), and hands them to `openViewBundle` as a lazy source, and shows that service.
Everything a bundle's view keeps and leaves out stays as it is. What the share adds lives in the host alone:
its prompts' subject (`promptSubject`): the share's link, `<origin>/<id>`, for the model, so a prompt says
`File: <origin>/<id>`, each reference `<origin>/<id>#<selectors>` (which Copy Reference and a chip copy too) and its
snapshot packet's `input` the link, and nothing else of it differs from the engine's page's for the same views,
selection, ink and words; the share's status screens (gone, damaged, a format it does not read, a
failure with Retry) and its delete page (`/<id>#delete=<secret>`). The delete secret never reaches the viewer: no
port, URL, storage or log carries it.

## Adding a shared feature

1. Implement reusable interaction and presentation in UI, with cross-consumer
   non-React domain behavior in core. Renderer-private helpers stay with their
   renderer in UI. Keep project, session and operating-system workflows in apps.
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
So do a transport's limits: a host whose channel caps one reply carries a longer body
in parts (the CAD app's tunnel reads it a range at a time), and the loader sees it whole.

## Prompt handoff

Context actions use `PromptContextPort.deliver(context)`. The CAD
app's `deliver` queues the context for the person's next message (`ui/update-model-context`); web prepares clipboard representations. Ordinary
explicit copy controls use the separate `ClipboardPort`. Delivery never
submits a prompt. `send(context)`, present only where the host has a chat to post
to, posts the context as the person's message now (`sent`); absent, nothing can
send one.

The portable types and validators live at `@cad/core/prompt`. One versioned
bundle contains ordered text, reference and attachment parts with unique IDs.
An attachment has a MIME type, name and Blob or Promise of Blob. Its optional
`about` array names reference-part IDs, so a screenshot and several selections
can travel together, its optional `label` ("Annotation") says what it is for a
message that names it by path, and its optional `path` (a path, or the promise of
one) is where it is already saved: `resolveAttachmentPaths(context)` waits for
them all. Producers freeze resource and selection identity before
asynchronous capture. Blob URLs are delivery leases, never portable identity.

A reference contains a workspace-file identity (the file's absolute path,
`/`-separated: `/a/b.step`, `C:/a/b.step`; validation rejects any other spelling), a
`cad-model` identity (a document the engine holds by its id alone: `path` is the id), or an
HTTP(S) URL (a document by its link, a shared model's page) plus a tagged
selection: `whole-resource`, `text-range`, or `cad-selector`. Text positions are
zero-based UTF-16 with an exclusive end. CAD selectors use the engine's
grammar, validated by core, not STEP entity numbers; a link's are either the engine's or a renderer's labels (its
file's kind is not in it), written as the engine writes them, which leaves a label as it is. Preserve a revision when
available; references do not promise to survive edits. Shared serialization handles quoting.

Where an agent reading a prompt could not reach the document as the view names it, the host says what its prompts
name it by (`promptSubject`): `resource` stands for the document on screen in a Quick Edit's and a screenshot's
prompt, as their file, in each reference into it, whose target it keeps, and as a Quick Edit's snapshot packet's
`input`, and in what Copy Reference and a chip copy (a pick still named in its file's own grammar, or not at all).
Without it a prompt names the document as the view does. The web's share mode names a shared model by its link
([below](#a-shared-view-bundles-host)).

`formatPromptMessage(context, { attachmentText, attachmentPath, folders })` is the one
message a Quick Edit is, whether sent, queued or copied: what the person wrote;
then `File: <path>`; then `References:` and one reference per line; then each
attachment, inline where `attachmentText` gives its text (a Quick Edit's snapshot packet), else by its label and
path, where `attachmentPath` says where it was saved. Every path in it is
named by the context's `folders` (`displayPath`): relative to the workspace the agent
works in (`start`), else from `~/`, else as it is, so an agent app that shows the message
verbatim never shows the person's home. Quick Edit asks `host.promptFiles.folders()` at
the press (the viewer server's `start` and `home`: a CAD app card's workspace is the folder its
agent app started the server's transport in); a host without it names every file whole.
No pictures are rendered, attached or sent.


A renderer's prompt action (the shell's, Quick Edit's, the drawing renderer's) reads the
subscribed destination (`usePromptDestination`) to decide what it offers: delivery to the
composer where the destination is one, a copy through the clipboard otherwise. It calls delivery during the
user gesture, before awaiting capture: browser activation and the host's destination
binding depend on this. Availability and advertised attachment/combination limits
belong to the host. Every result is acknowledged: added, copied, sent, partial,
deferred, cancelled or failed. `partIds` describes accepted/written parts, not a
claim that a different application pasted them.

The CAD app validates the complete bundle before it hands anything to its host
(`validatePromptContext`); an invalid one leaves the composer's context unchanged, and
operation IDs prevent duplicate acceptance (`createPromptDeliveryLedger`). A host that
takes no context answers with an error the person reads, and a failed delivery never
shows success.

Web supports text/reference serialization and one PNG. A combined clipboard
write reports that text and PNG are separate representations; some receivers
paste only one. Unsupported attachment types or combinations fail explicitly.
Hosts must resolve/validate accepted attachments and consume failed encoders;
they do not transfer Promise or Blob values across native IPC.

Quick Edit is the shared, host-neutral note to the agent
([Quick Edit](viewer-ux.md#quick-edit)), and its buttons are what the host can carry out.
Copy, Queue and Send carry the words and references, with a snapshot packet made
at the press when the displayed revision matches the saved input. If the viewer
retains a previous revision, Quick Edit keeps the note and
references available and explicitly says they describe that displayed revision; the
saved file may differ. It omits replay jobs rather than naming that saved file as the
picture on screen. The packet includes the current view plus distinct drawn views
with remaining ink; an equivalent drawn entry uses the exact current framing.
The input and the annotation ([annotation](annotation.md)) appear once; measurements
are the person's and never go. Projection and lens are preserved. The page makes it, the same code for every
host (`snapshotPacket`, `@cad/core/prompt`: a job per view, its picture named by its label alone, shortened to
what each view could show), and the message carries it inline and whole, whatever its size, after the
references: ``Snapshot JSON (`cad <type> snapshot --job`):`` over its compact JSON in a `json` block. Nothing is
written and no path is named. Hosts use `resolvePromptMessage` to resolve its `inlineText`, which waits for the
folders the message names files by, keeping destination binding inside the gesture. Drawing, selecting and typing
keep data in memory. Nothing renders at the press. The agent hands the packet to `cad <type> snapshot --job` as
it is (or on standard input, `-`), which draws each view with the ink over it.
**Copy Prompt** is always there: the message goes through
`ClipboardPort.writeText`, which takes a `Promise<string>` so the write starts
inside the gesture while the folders are still being asked; its references name their
files by absolute path, as copied references do (below), where the host says no folders. **Queue** is there where the
destination is a composer (`destination.kind === "composer"`): `deliver`, the
context for the person's next message. **Send** is there where the prompt port
has `send`. The context is built at the press, from what is live then; a changed
document or revision never retargets it. A Quick Edit that reached its destination
(copied, queued or sent: no `failed` or `cancelled` receipt) tells the host once,
`usage.used('quickEdit')`, for its count; a host that throws there changes nothing.

`usage.controls(counts)` is the shared UI's count of what a person did in the view
([`usage/controls.js`](../src/usage/controls.js)): `CadViewer` counts under a `ControlUsageProvider`
fed by it, and every renderer, menu and the home count through `useControlUsage()` — `used(name)` for
a press, `changed(name)` for a setting (a burst of moves is one change), `active(name, on)` for a
control that stays on (the tool in hand, Preview: a use each time it turns on, and its seconds while
it is on and the page is shown; Explode and Clip, popovers rather than tools in hand, are a `used` each
time one opens, with no seconds). A host receives, at most every minute it has something to say, as
the page is hidden and as the view goes, `[{ control, count, seconds }]`: a name of `CONTROLS`, a
closed list that the server and the receiver hold too (a name not on it is dropped here), and two whole
numbers. Never a value typed, a setting's value (unless it is itself a name on the list: a render
mode, an axis), a file's or a part's name. Only a person's act counts: what a renderer, a host command
or the agent does through the live surface is not. Both apps hand it to their server (`reportActivity({ controls })`), which
sends it with the rest of its telemetry, only with the person's yes.

`ViewerHost.promptFiles` is a `PromptFiles`: `folders()` answers the workspace a message names this computer's
files from and the person's home. `createHttpPromptFiles({ origin, fetch })` from `@cad/core/client` reads them from
the viewer server's description (`GET /api/v1/server`'s `start` and `home`). Both apps pass one; the MCP app's
reaches the server through its tunnel. A view bundle's host and a share's pass none: the page they show has no
computer's files to name.

## App-specific interfaces

The optional CAD `live` binding receives a `LiveViewController` only while its
viewport is mounted. `readState()` returns a detached serializable snapshot of
the actual resource/revision, current selections, camera and display. It reads the viewport camera directly, with its last camera snapshot as
an unmount fallback. During a rebuild that retains a predecessor mesh, its
displayed document revision remains in the snapshot until replacement. Apps
own the binding registry and any IPC/tool transport;
shared UI does not infer view state from a backend catalog or stored tab state.

The controller reads the view, applies a camera, resets framing, applies grouped Display
settings, captures a PNG and draws a library picture; `clearSelection` is each renderer's own
command, and every renderer declines `select` in words.
`thumbnail({ width, height })` is a library card's picture: it waits for the view
to settle — the renderer's own live state saying the whole file is loaded and
drawn, never a timer — then draws the model framed whole from the default
direction at the card's aspect, on its own (no floor, grid or axes, whatever the
person turned on) and on transparency, so it suits either scheme, off to the side of the view, so
the person's camera, panels and window never show in it and nothing on screen
changes (`kit/viewport/thumbnail.js`; a DXF paints its fitted drawing on a canvas
of its own, and a KiCad board its fitted board, its area in the canvas colour and nothing round it,
`drawPlot`'s `backdrop: "board"`, in the light theme's colours). The host keeps it
(`CadClient.keepThumbnail`), and the home's card shows it in both themes, never turned. A view that
goes before it settles rejects it. `useModelThumbnail`
keeps one per revision of a file per mounted view (a model rebuilt while it is
open is pictured again once its new revision is drawn), and only for the file the
view still shows. A model's document is pictured as a file is, by its id: its catalog
row's revision is the build the engine holds, so a rebuild is a new revision.
That is the only picture the viewer takes: the home draws none. A card shows the picture its row names (`thumbnail`,
the file as it now is), else its format's tile, so the home never reads a file nobody opened.
`readState().display` and `setDisplaySettings(patch)` use the same sparse display
schema as snapshots: `mode` selects `solid`, `shaded`, `parts`, `xray`, `hidden-line`,
or `wireframe` (each a look at its own defaults), `grid` switches the measuring grid,
and appearance, camera, clip and exploded are shared. Patches merge supplied fields;
a mode has no settings of its own, and a patch naming any is refused. There is no
Custom state or legacy shape migration. Render is no mode: it is Preview's, which no
live command opens, so `mode: "render"` is refused as any unknown mode is; Preview's
own settings are the viewer's panel's, not the display's. Camera projection/lens changes preserve viewport pose and zoom.
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
"Updating model…" (a drawing's: "Updating drawing…"); an engine document's rebuild says the
build's own stage while it runs ("Building geometry…", "Writing files 1/5…": the engine's
progress event, [view-updates](view-updates.md#status-placement)). Once a model has been shown,
a rebuild is an update, never the loading screen.

State remains controlled through FileViewer props, and everything the viewer keeps
is the tab's (`@cad/ui/tab-store`): one record per tab, `{ version, settings,
files }` (`version` is `TAB_RECORD_VERSION`, 2; a record another version wrote reads as
the defaults), thrown out with the tab and kept across a reload. The host supplies where it
lives through one adapter, `TabRecordStorage` — a synchronous read and write of the
whole record: the web over `sessionStorage`, the CAD app over memory
(`memoryTabRecord`) — and the package owns the record's shape, version and normalization. `settings` is
`{ toolStack, appearance, viewportBackground, library }`: tab-wide (the tool stack's layout, the
appearance, the viewport's background, the home's layout and its Sort: `library: { layout, sort }`), and what every
renderer reads as its preferences;
`files` holds the view of the file on screen, under `[absolute path, renderer id]`, and no
other: a write keeps the newest alone (`TAB_FILE_LIMIT`), and `CadViewer` sets the view
of a file it leaves — for another file or for the home — aside for the page once the
departing renderer's last write has landed (`files.retain(path | null)`; `null`, the home,
sets every view aside), in the store's memory and never in the host's storage, the newest
`PAGE_FILE_LIMIT` (32) of them, and gives it back to the record as the file is shown again.
The store reads and writes a view (`files.read`, `write`, `remove`, which forgets one, from the
page too), lists them all (`all()`) and merges a view's changes (`merge`). A reload of the tab
shows the same file, so it brings that view back; a file left and shown again in the same page
opens as it was left; a file the page has not shown starts at the defaults. In the CAD app there is one record per view: a view the host
creates again (its frame re-created) starts afresh, since nothing names a view across its
frames. A view is `{ camera, display, preview, playback, renderer }` (`kit/shell/fileView.js`):
the camera is restored in place of the open-time fit, the display settings with their
Clip and Explode, Preview's Render settings, the playback settings (Orbit's speed and the chosen speed and
loop), and the renderer's own slices each behind the
signature it was written against — a slice that no longer fits the file on screen is
dropped, the camera, the display and the playback never. Not in it, and started afresh
on every open: the tool in hand, the selection, measurements, ink, Preview, a
routine's time and Quick Edit's note. Apps merge
what a view changed into the store (`files.merge`); a stale view must not overwrite
another view's entries. Material appearance is source-owned and read-only. Live
selection and scene ownership belong to the mounted view.

A mounted view writes its view shortly after each change (the camera on every move,
debounced) and once more when it unmounts, and nothing after that; the store writes
through synchronously, so what the tab last saw is what a reload restores. Nothing
saves document content or promises an asynchronous operation will finish during page
exit. Web owns pagehide
(which unmounts the app), focus, visibility, history and reload under a new server. The CAD app
owns its frame's lifecycle and the host's messages.

The dependency checker enforces host boundaries, including worker source. The
browser harness mounts real renderers with explicit fake hosts; app tests cover
native/clipboard delivery and multiple-view state merges. Warm-cache regression
tests remain required for resource changes.

## Keyboard scope

Viewer shortcuts consume only events from their own viewer, or from the page
background after a pointer press in it, so another viewer or the composer never
receives Escape, copy or orbit keys on its behalf
([viewer-ux.md](viewer-ux.md#keyboard)). Undo and Redo (the view's one history: Draw's ink, Measure's rulers)
take ⌘ or Ctrl alike; the host's
keyboard `platform` (`environment.platform`) names the keys the hints show (⌘C or Ctrl+C, the zoom's, the panel's
`⌘\` or `Ctrl+\`), and which of ⌘K and Ctrl+K opens the search, the one key the page binds wherever the focus is.

## Host chrome slots

FileViewer draws one navbar, the same in every host, over every file and over a host's
home (the web viewer, and every view of the CAD app's: its sidebar, tabs, cards and file handler); only Preview, which
draws its own bar, and a `compact` view are without it. What a host adds over the view is its own, as its notice at the
viewport's top-right (`notice`). **The
panel's toggle is the navbar's** (`file-viewer/panelToggles.js`): the panel's frame says it (`usePanelToggles`,
through `file-viewer/panelFrame.jsx`: a view's frame for a file's panel, and the home for its sidebar, which is the
same panel), and the
navbar draws it right after the logo (the logo leads on every page, the way home in one place), the same neutral button open or shut (`aria-expanded` says which, pinned or
not). Before the view is up (its file being read, its chunk loading, or its frame mounted but its toggle not said yet)
`FileViewer` draws the toggle the view will have, from a document page's first frame, by the view's own rule
(`panelToggles.js`'s `sidebarLayout`, which `sidebars.js` re-exports): the file's choice kept for this session (its view
in `state.renderers`, by its own path or the host's `filePath`) at any width, else open where the model keeps 640px
beside the default-width panel, closed on a phone; pressable from the first frame: a press pins or unpins it, the
person's choice on the file, which the view opens with and writes as its own toggle would. A host with a phase before
it can mount the viewer (the web page's, while it asks its server what it is) draws that first frame with `FileViewer`
itself, inert: a `files` source whose `stat` never answers keeps it in this phase, asking nothing, so the navbar, the
stand-in and the cover stand where the viewer then draws them. Collapsed, a mouse resting
on it peeks the stand-in over the page (`panelPeek.js`: the page's one peek, which `FileViewer` holds and hands to the
view's frame, `PanelPeekContext`, so a card up as the view arrives stays up, taken over where it stands). Open, the panel's frame stands in its place at the width the view will draw (the kept one within the
grip's bounds, `clampPanelWidth`; `data-panel-loading`), drawn as the view's panel is while its file loads: the head's
one block (a bar where a lone title's name will stand) over its rule, then the placeholder rows, busy, on the same lines
(`panelToggles.js`'s metrics), so nothing moves as the view mounts; a view with no frame (none says so as it renders,
`PanelFrameContext`) has none, and a file that will not open has neither. The view's own toggle comes with the pointer handlers the frame hands with it (`hover`): a mouse resting on it peeks the collapsed panel over
the model as a floating card, pushing nothing, until the pointer leaves both (only the toggle's click, or ⌘\, pins it);
otherwise a collapsed panel leaves nothing over the model.
In Preview, in
every host, the navbar steps aside for Preview's own bar. Over the home the navbar has the logo (which goes to
Recents), the sidebar's toggle (said by the home before its first paint, so nothing after it moves), Back and Forward where
the host hands a `history`, then the home's own controls —
**Home** where a file shows its name, the search and
Import at the right (`ModelLibrary` portals them into the navbar's slots, `file-viewer/navbarSlots.js`) — and the
host's actions, outermost. The home's Sort and layout control stand at the right of its place's one heading row,
and its links are the app menu's. Left: the text-to-cad
logo (the "C" mark, 16px, over the home and over a document alike),
the way home where the host has a home (a link where the home has an address, a button otherwise, its hint "Home")
and the app menu's button where it has none (`AppMenu`, `file-viewer/navigation/AppMenu.jsx`), then the panel's
toggle where the page has a panel, then Back and Forward where the host hands a `history`, then, for a document in a project, the project's name and a slash (a
press shows that project's page on the home, with the document just left remembered; a link where the host gives
places an address: `FileProject.href`), then the open file's name, with no
glyph and no menu of its own, and its ⋯ menu. The
logo, Back and Forward, the project's name and the ⋯ share one style (`NAV_ITEM_CLASS`):
transparent at rest, the same accent background while the pointer is on them or their menu
is open, a pointer cursor, and no tooltip but the logo's "Home". The ⋯ offers Copy path and Reveal in Finder / Show in Explorer / Show in file
manager, each where `fileActions` can do it; Search documents with its key, where the host has the search
(`FileViewerProps.onSearch`); and for a document in no project, Import its folder as a project (the
library's `importFolder`, its chooser starting at the document's folder, a model's script's); it is absent where it
can do none (no right-click on the name). `CadViewer` finds the project from the document's catalog row
(`project`, with the `folder` the document is in) and reads that folder through the client (`projectFolder(id, { path })`),
again every three seconds while it is shown: its files, in the home's Sort, are what `[` and `]` step through. Right, only what a host or a file adds: the renderer's navigation
actions first, then the view's own Display and Preview, which the view portals into the navbar's view slot (below),
then the host's actions (`navbarActions`: `CadViewer` hands it the host's
`fullSize`, the CAD app's Full size), outermost.

The app menu is FileViewer's, built from the host's `links` and
`environment.platform` and the person's `FileViewerProps.appSettings` (which `CadViewer`
passes on). Where the host has a home (`navigation.home`) FileViewer hands it down (`navbarSlots.js`'s
`AppMenuContext`) to **the panel's foot** (`file-viewer/PanelFoot.jsx`), one component at the bottom of the sidebar on
the home (`library/LibrarySidebar.jsx`) and over a document (the view's panel, and FileViewer's stand-in for it while
the file loads), in the pinned panel, the peek and a phone's sheet alike: under a full-width rule, the host's links as
icon tiles at the left (GitHub and Discord, each where `links` gives it, then Send feedback) and at the right
corner **Settings**, a cog whose menu, opening upward, is the app menu without those links. A document's navbar has
none of it. Where the host has no home there is no foot, and the navbar's logo opens the menu, with every item, as
it always did: nothing is offered twice. It is a dropdown on the floating surface.
First the person's settings, a press keeping
the menu open: **Language** (`language`, below), the host's on/off settings (`appSettings`,
below) as checkbox items, checked at the right, and **Theme** (`colorScheme`, below); then (the logo's menu's
items; the foot's icons),
where the host has a tracker
(`links.issues`), **Send feedback**, a link to a new issue titled "Feedback: "
(`feedbackUrl`, `NavbarLinks.jsx`), for the person to finish, naming the version and
`environment.platform` — it has no label: the project has none for feedback, and what is
said may be a bug, a request or a question — then **GitHub** and **Discord**; and last, in
gray, "v<version>", which links its release notes (`links.release`). The version is the release's own build's
as it is (`v0.10.0`), and any other build's with its id (`v0.10.0-dev.b80844940`, the commit
it was built from, `-dirty` with uncommitted changes): `viewerLinks({ version, build })`,
where each app's Vite config names the build through `@cad/ui/build-id`, and a new
issue names it the same way. The home has no links of its own: they are this menu's.

**The home's sidebar is the viewer's panel** (`viewer-ux.md`, "The panel"): the same toggle, pinned and collapsed
states, peek, key, grip and phone's sheet, from the same modules. What the person chose of it (`{ open?, width? }`:
opened or closed, and the width they dragged it to; nothing until they choose) is the host's to keep:
`ModelLibrary`'s `panel` and `onPanelChange`, which `CadViewer` keeps in the tab's settings (`settings.library.panel`,
beside the home's layout and Sort), so it lasts as long as the tab and comes back after a reload. A host that keeps
nothing gets a sidebar that remembers for as long as the home is mounted. A page drawn before its app takes over
draws the same frame with `LibraryFrame` (`@cad/ui/library`, `places` null: placeholder rows).

An alert card's Report Issue opens a new issue too,
titled "Issue: " and labelled `bug`, filled in from the card (`kit/status/reportIssue.js`): its
title, message and failure, the file's name, the version and platform, then its Details, cut from
their end to keep the address, title and labels included, under `ISSUE_URL_MAX`. No path of the
machine goes with it: the file's path is its name wherever the card writes it, and a home
directory in anything else is `~/`. A label is a suggestion: GitHub applies a URL's labels only
for someone with triage access to the repository and drops them for everyone else. A link opens
the ordinary way unless the host supplies
`links.open` (a page in a sandboxed frame hands it to its host), which every link of the
menu follows. The colour scheme is the menu's Theme row (`colorScheme`, a `CadViewer`
prop); no host has a light/dark button of its own, and
Display holds no appearance control. `language` (`{ locale, inferred, choice, onChoiceChange }`, a `CadViewer` prop) is the person's
language for the app menu's Language row: `choice` null is Automatic, `inferred` what Automatic
means; both apps keep the choice in the person's settings (`/api/v1/settings`' `language`, the
`language` section of `settings.json`), so it holds for every CAD view. `appSettings` (`{ id, label, checked, info?, disabled?, onCheckedChange }[]`, `info` the
hint of an info icon beside the name; a `CadViewer` prop) are the host's own on/off settings: checkbox items of the app menu, in the
order they come (Telemetry, in both apps), the same wherever the menu
opens from; nothing of them reaches a renderer, and Display holds none. The
host owns what each one does and where it is kept.
`@cad/ui/consent` is the usage stats toggle both apps share:
`useAnalyticsConsent(consent, locale)`, which turns the host's consent call into its `appSettings` row
(Telemetry). Nothing asks: the server's telemetry is on by default once a `cad` command
has said so. The host supplies the call and where the answer is kept.
`@cad/ui/whats-new` is What's new, the dialog both apps show once after a release is installed
whose notes say what it brought (`notes.js`: by minor version, at most three items, their words the
locale files'): `useWhatsNew(whatsNew)` reads the host's call (`/api/v1/settings`' `whats_new`,
`{ seen, release }`: the releases whose notes the person has seen, kept in the `whats_new` section of
`settings.json`, and the one the engine runs) and gives the release to show and `dismiss`, which the
host hands `CadViewer` as `whatsNew`. CadViewer says it, the stock Dialog with one Got it, over the
home or a file's view once its renderer is up, never over a loading page; every way it closes keeps
it seen for every view, and a write that fails still closes it. A new person is shown nothing new: the
server decides, once, whether a device was updated (`cad_server/whats_new.py`). A host leaves
`whatsNew` out where a dialog has no room (the CAD app's cards) or while its own notice covers the
view (the engine gone).
The shell handles placement and hides the toolbar in
Preview; the host owns callbacks and preferences. None of these imply platform
detection or move application-specific release/network behavior into shared UI.

There are no document tabs in the page: the browser's tabs are the viewer's. A host says how a document or a project
opens in one. `navigation.hrefOf(target)` is a target's own address, for a real link: the navbar's project name
(`project.href`, which the host fills from it) and the search's rows are links where it answers, so ⌘ or Ctrl and a
click, a middle click and the link's own menu are the browser's, and a plain click stays in this view. A host whose
pages have no address of their own (the CAD app's, in an app's frame) has none, and they are buttons.
`navigation.openBeside` is the item that opens a target beside this view: the file menu's Open in new tab (`kind:
"tab"`) or Open in browser (`"browser"`, left out where Open in's Browser is there already) for the document on
screen, and the search's ⌘Enter and its rows' small button. Absent, neither is offered.

`CadViewer` mounts the search of every document (`search/DocumentSearch.tsx`; [Search](viewer-ux.md#search)) once,
over a document and over the home, where the host has a `library`: it reads `library.list()` and
`library.projects()` as it opens, a picture through `library.thumbnail()` for the rows on screen, and opens a row
through `library.open(row)`, as the home's cards do, so a host that keeps a card's name for the navbar until the
document is read (the web page) keeps it here too; `navigation.openFile` would take the path alone. The document on
screen and its project are `CadViewer`'s own, from the catalog.

A file that will not open leaves the navbar (where the host draws one) over a page of the host's
(`presentation.error`). `CadViewer`'s says "File does not exist" and the file's path
when it is missing (`isMissingFileError`) -- for a document named by its id, "This model is no longer held" over the
engine's words -- and "Could
not open that file" and the reason otherwise, each with a Go home button where the host has a home.

The viewport's edges and corners are the shell's, never the host's: the tool strip at the
top centre of the window (no view controls on it under a navbar, which holds Display and Preview: below), the tool
in hand's sub-toolbar under it, the one panel
(the file's structure, then its Params, Joints and Animation, as tabs) docked at the left, pinned open always pushing
the model aside (collapsed on its own where it would leave the model under 640px, until the person opens or closes it
on that file; a mouse resting on its toggle peeks
it over the model as a floating card, pushing nothing, and only the toggle pins it), Quick Edit's bar always at the bottom, one row (its attachments a row above it while something is picked), centred on the window as the strip is
(the panel never moves the strip; where they meet it the strip sits above it, and the bar centres on the model's area beside a pinned panel), the bottom row Quick Edit's alone, and at the
top-right the camera's own control alone: the view cube (a 6rem box, 2px from the right edge and 8px off the top), or a flat view's
"100%" zoom dropdown. Under a file's navbar the view's settings are its right end for every kind of file — **Display**,
a toggle whose card docks under the navbar at the view's right edge, over the cube (a 3D view's Projection | Style,
Background, Show grid; a board's Side, Mode, in 3D Projection | Style, Background; a drawing's Background,
`DisplaySettings.jsx`), then a 3D view's or a board's Preview: the
file viewer draws a view slot there (`file-viewer/navbarSlots.js`'s `NavbarViewSlotContext`) and the view portals them
in (`NavbarViewControls.jsx`). On a phone the slot holds the same Display and Preview, the picture has no cube or zoom,
and the panel is a sheet from the left (shadcn's Sheet, portalled into the viewer's element:
`ViewerElementContext`), so a host keeps the viewer's element round its view. A host that anchors the corner at the left (`--cad-viewport-corner-left`) moves the cube
or the zoom with it, mirrored at the top-left. A host's one notice goes through the shell too: `notice` is drawn at the top-right,
under the corner (an inset under its lowest control; at the top itself where the corner is at the left), once the
file is on screen, never while it loads or after it failed to, with Quick Edit stacked under
it while it stands; the home never shows it. The CAD app's file handler hands its corner (Full
size) as its notice; the web viewer has none.
Quick Edit has no host preference or persisted enable/disable state.
What Quick Edit offers follows the subscribed destination capability and
the ports, never an app name: Copy Prompt always, Queue for a composer
destination, Send where the prompt port has `send`. Native clipboard effects
remain in the host implementation.

A STEP's selection copy (a chip's click, the copy shortcut) and Draw's
copy shortcut (the view with its annotations) use `ClipboardPort` directly: the references as text, the view with its ink as a PNG through
`writeImage`. Their copy shortcut follows the same path. A double-click copies
nothing: on a face or edge it turns the view square to it, on a component or
subassembly it isolates it. The host supplies
`environment.platform` for the ⌘C / Ctrl+C hint; the web host derives that field
from its browser environment.

An alert card's Details have a copy icon in their box's top-right corner
(`kit/status/ViewerAlertCard.jsx`): it copies the whole of them, however far they scroll,
through `ClipboardPort.writeText`, and shows a tick for a moment. A host whose clipboard
refuses the write gets a line saying so under the box, where the text stays to select; a
view with no host clipboard gets no icon. Each host makes its port copy wherever it can: the
web falls back to the page's copy command when the browser refuses the asynchronous
clipboard, and so does the CAD app when its host grants its frame no clipboard.

A copied reference names its file by its absolute path (`<path>#<selector>`), a model by its
document id (`<id>#<selector>`), and so does a copied Quick Edit: every view spells a file the same way, so a reference pasted
into a chat or a tool says exactly which file it means.

Nothing of the tools view sits at the bottom centre: the bottom row is Quick Edit's, and Preview's playbar stands
there in Preview alone, for a file with routines. A host whose own control floats over
that edge (a chat's composer) sets `--cad-host-bottom-inset` on an ancestor to the height it
covers: the model library scrolls its last rows clear of it. A host whose own control
floats over the view's top-right corner sets `--cad-viewport-corner-top` to the room
it takes from the top edge, and the view's whole corner sits that much lower. To choose the
opposite corner instead, set `--cad-viewport-corner-left: 2px` and
`--cad-viewport-corner-right: auto`; their defaults are `auto` and the cube's right inset (2px). All of
the corner follows, mirrored at the top-left: the cube, or a flat view's zoom (placed from the same variable, the
corner's inset from the edge), its menu opening away from the corner
(`viewportLayout.js`'s `viewCornerLayout`).
Codex's tab presentation uses the left corner across sidebar, thread and file views (clear of its chat button).
The shared viewer consumes these layout values without identifying the host.

The update status is the view's own: every renderer's frame (`ViewFrame.jsx`) shows it centred under
the tool strip and its sub-toolbar, or at the top centre where there is no strip. The navbar carries
none.


A retained predecessor is useful for a Quick Edit's note and references, but does not prove
which bytes the file contains. While one is displayed, Quick Edit says so in the bar and in its
prompt context, and makes no replay packet. Once the matching saved revision is displayed,
snapshot handoff resumes.
