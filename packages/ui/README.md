# @text-to-cad/ui

The shared React interface for text-to-cad. `FileViewer` is the complete file view:
one file by its absolute path (`/a/b.step`, `C:/a/b.step`, `/`-separated in every
app), or the host's home with none, under a navbar — the logo that opens the app's
menu, the file's name and the explorer it opens, the file menu — with the file's
content and the loading and error states ([FileViewer](docs/file-viewer.md)).
`CadViewer` (`@text-to-cad/ui/cad-viewer`) is the CAD viewer every app shows:
FileViewer over a CAD client, with the five CAD renderers, the home (the model
library) and the standard loading and missing-file pages. `apps/web` and `apps/mcp` consume both through the package's compiled
exports; a host's own project, session and window layout remains application code.

The viewer's tools, file sidebar, settings, tooltips and keyboard follow one
binding [design system](docs/settings-ui.md), the same in both apps. A change to
that chrome changes the design system first. Desktop's surrounding app controls
remain local where their appearance differs.

## Ownership and dependencies

UI may import `@text-to-cad/core` and browser-safe React dependencies. It must not
import an application, Electron, Node services, desktop IPC schemas, app stores,
or `window.textToCad`. Hosts inject file access, capabilities, navigation,
persistence, appearance and CAD services. Importing a package starts no polling,
workers or host storage writes and changes neither document title nor theme.

Shared UI is platform-agnostic: components must not detect web versus desktop
to choose their behavior. Express environmental differences through injected
capabilities and app-supplied named slots. React, DOM, canvas and responsive
layout remain shared; operating-system details and app workflows belong to the
host. Follow [the feature-extension workflow](docs/viewer-host.md#adding-a-shared-feature)
when introducing a new integration.

The design system's default UI size is 13px (`text-ui` in
[src/styles/tokens.css](src/styles/tokens.css)); `text-sm` and `text-base`
resolve to that same size for shared and host controls. Hosts apply `text-ui`
to their body; FileViewer also sets it at its own boundary. Use this default
for ordinary interface text, navigation and tabs. Settings sheets retain their
explicit compact scale: 12px section headings, 11px labels and control values,
and 10px metadata (see [settings UI](docs/settings-ui.md)). Document headings
and code retain their content styles.
Dropdown, select-popup and context-menu primitives default to the same 11px
compact text (`text-tiny`, 16px line height), including checkbox/radio items
and submenus. These defaults belong to the
primitives, including desktop's app-level equivalents; consumers do not add
per-menu font-size overrides. Portals set their own compact text size rather
than inheriting the trigger or host body's size.
Viewer hover hints use `TooltipHint` from the shared tooltip primitive, with
11px text and a 400ms delay. Use short action names, omit redundant hints on
obvious or already labeled controls, and show full tree/field names only when
clipped. Native HTML `title` attributes are not used for interface tooltips.

The token uses rems so desktop UI scaling still works without changing the
normal 16px root or shrinking layout spacing.

File-tab chrome uses normal-weight type. The navbar's file name, the explorer's and
the model tree's rows, and filter matches use muted/primary text color for emphasis,
never bold weight. The explorer's rows are compact 24px lines in 12px text, the size of
the section titles and the filter above them, a folder opening inline under itself; the
file sidebar's trees (Model tree, Links) are 24px lines in its smaller 11px text
([the file sidebar](docs/settings-ui.md#the-file-sidebar-and-the-tool-stack)). Both inset
row backgrounds 4px from their horizontal edges, including selected, hovered and
filtered rows; nesting adds indentation inside that gutter.
The file explorer is a popover under the navbar's file name (`FolderExplorer.jsx`):
18rem wide, no taller than 28rem or the room below it, with no resize handle. It
floats over the view and never resizes it or moves its tools. A file's controls are
the viewer's own: the tool strip at the view's top centre, the tool in hand's sub-toolbar
under it, and the file sidebar's tiles at its top-left, a section's panel under them bounded by the viewer's height.
FileViewer is mobile below 600px of its own width; progress indicators use this same
breakpoint. The sidebar never scrolls sideways: Position's labels truncate to preserve its
sliders and inputs.

React, ReactDOM, Three.js and Lucide are host-supplied peers. React 18 and 19
are supported: web and desktop use React 19.3.0. Each
host must resolve one copy of each peer in its browser bundle. Web uses Vite
deduplication so shared imports use its host React and Lucide versions;
these peers are not bundled into UI.

```text
src/
  host/              explicit host ports, prompt actions and React binding
  annotation/        the drawing tools' (Pencil and Shapes) session, toolbar and ink geometry (its 3D ink is renderers/kit/tools/annotate)
  cad-viewer/        CadViewer (FileViewer + the five CAD renderers + the home), and a CAD client as a FileSource
  file-viewer/       FileViewer, typed source/renderer contracts, the document lifecycle hook
    navigation/     the navbar, the app menu and its links, the folder explorer, the file menu
  library/           a host's home: the models opened before, to open again, and their pictures
  renderers/
    kit/            the frame every viewer file shares: viewport, tools, panels, Display settings, status
    xbf/            an engine document (.xbf) and a STEP: model tree, Position
    robot/          URDF, SRDF and SDF: Position and Links
    glb/, mesh/     GLB, and STL/3MF triangle meshes
    dxf/            2D drawings
    workspace/      a viewer file's catalog entry and document load
    harness/, shell-harness/  surfaces the browser suites drive
  primitives/       shared controls: buttons, menus, selects, sheets, tooltips, tree rows
  lib/              browser helpers
  loading/          shared loading animation
  styles/           canonical tokens and component CSS
  assets/           lightweight UI assets
dist/               generated ESM, declarations, CSS, assets and worker modules
```

`FileViewer` has no concrete renderer imports. A registration describes matching,
priority, asynchronous preparation, lazy component loading and disposal.
Each app registers only the file types its source supports. A renderer's code
loads when a file selects it; adding a renderer does not add a branch to FileViewer.
The registry rejects duplicate IDs and ambiguous matches.

This package ships the viewer renderers. A renderer only one app registers is
that app's own, built on the same public `defineFileRenderer` contract (see
[renderers](docs/renderers.md)).

File listing is independent of renderer matching: the explorer shows every entry
the host's source lists. A host that opens arbitrary files registers a
fallback renderer (`fallback: true`) for the types nothing else matches.

```tsx
import { FileViewer } from '@text-to-cad/ui/file-viewer';
import { createDxfRenderer } from '@text-to-cad/ui/renderers/dxf';
import { createGlbRenderer } from '@text-to-cad/ui/renderers/glb';
import { createMeshRenderer } from '@text-to-cad/ui/renderers/mesh';
import { createRobotRenderer } from '@text-to-cad/ui/renderers/robot';
import { createXbfRenderer } from '@text-to-cad/ui/renderers/xbf';
import '@text-to-cad/ui/tokens.css';
import '@text-to-cad/ui/styles.css';

// One viewer renderer per file family, sharing one client and one preference source.
const renderers = [createDxfRenderer({ client, preferences }), createGlbRenderer({ client, preferences }),
  createMeshRenderer({ client, preferences }), createRobotRenderer({ client, preferences }),
  createXbfRenderer({ client, preferences })];
// The host supplies storage, actions, navigation and environmental ports.
<FileViewer file={selectedFile} host={host} renderers={renderers}
  state={state} onStateChange={setState} />;
```

Public entry points include `/host`, `/file-viewer`, `/tab-store`, `/navigation`,
`/renderers/dxf`, `/renderers/glb`, `/renderers/mesh`, `/renderers/robot`, `/renderers/xbf`, `/renderers/workspace`, `/file-viewer/presentation`, `/file-viewer/empty`,
`/cad-viewer`, `/catalog`, `/links`, `/library`, `/consent` (the app menu's Share anonymous usage data row and its state), `/loading-icon`, `/utils`, `/primitives/*`,
`/tokens.css`, and `/styles.css`. `/catalog` (a CAD client as a `FileSource`, the file menu's
Copy path and Reveal, and the one spelling of an absolute path: `normalizePath`, `baseName`,
`joinPath`) and `/links` (the navbar's link defaults) are pure modules, with no React, for a
host's adapters and their unit tests.

A CAD host composes `CadViewer` rather than FileViewer and the renderers: it hands
over its CAD client, its ports (`files` is `createCadFileSource(client)`), its tab store,
the file on screen (absolute; `''` is the home) and how to show another (`onShow`), and
its library.

```tsx
import { CadViewer, createCadFileSource } from '@text-to-cad/ui/cad-viewer';

const host = { files: createCadFileSource(client), clipboard, promptContext, environment };
<CadViewer client={client} host={host} tabStore={tabStore} live={live} file={file}
  onShow={showFile} library={library} onThumbnail={keepPicture} />;
```
Declarations are owned here; apps need no ambient shims or aliases into this
source tree.

The viewer's drawing tools (Pencil and Shapes) are native ink projected into the model, with no drawing
SDK and no persistent storage. Read [annotation](docs/annotation.md) before extending it.

The required host contract, typed prompt bundles, delivery receipts and host
chrome slots are documented in [viewer host](docs/viewer-host.md). Clipboard
and page reload implementations live in the apps. Shared UI performs no
raw transport, clipboard discovery, host storage or page-navigation effects.

## Lifetimes and state

`FileSource` describes what a view reads, by absolute path: `stat` (one file's
metadata) and, where the host's files can be browsed, `list` (a folder's entries)
and `search` (the files under a folder, saying when it stopped early). It reads and
never writes. The file menu's Copy path and Reveal come from the separate
`FileActions` port; a missing method remains unavailable, and listing never filters
entries by renderer support.

FileViewer opens a file's document when the file is shown, and again only on `reload`:
its renderer follows the file's changes in place. A late answer to an aborted read is
discarded.

A source has a stable `id` independent of a server's ephemeral port. A saved view is
scoped by file path and renderer, and a document by source, path and reload
generation. Changing source or file aborts
pending preparation, releases prepared assets, and discards stale async results.
A renderer owns its viewport and resources; the host owns its CAD client. Last
render-session disposal releases shared worker leases. One viewer cannot replace
another viewer's cache provider or camera state.

The host owns where state lives; the package owns what it is. Everything the
viewer keeps is one tab record (`@text-to-cad/ui/tab-store`: the tab's settings and
the view of the file on screen — its camera, Display settings and the renderer's own
slices), thrown out with the tab and kept across a reload. Leaving a file, for
another or for the home, drops its view (`CadViewer`), and an update of it keeps what
still fits the new revision. The web keeps it in `sessionStorage`, the CAD app in
memory, one record per view; both hand `createTabStore` one
synchronous read/write adapter and take `FileViewer`'s state from it. The tool in
hand, the selection and measurements are never stored. Capabilities determine menus:
the file menu offers only what `FileActions` can perform.

## Development and verification

From the repository root:

```sh
npm ci
npx --no-install playwright install chromium
npm run build:packages
npm run typecheck --workspace @text-to-cad/ui
npm test --workspace @text-to-cad/ui
npm run check:boundaries
```

`check:boundaries` also holds `src/renderers/kit` format-blind: it imports no renderer
and names no file format ([Kit](docs/cad-renderer.md#kit)).

Rebuild shared packages after editing them; hosts resolve `dist`, never `src`.
Install the npm Playwright browser even if Python's snapshot browser is already
installed; they may require different Chromium revisions. On Linux, add
`--with-deps` to the browser install command if its system libraries are absent.
The Node runner caps file concurrency at four so JSX transforms and Chromium
setup do not compete with one process per host CPU. The UI suite includes Node
helper tests, React component tests and real Chromium
integration tests for renderer preparation, file and source changes,
multiple instances, cancellation and disposal. App integration and packaged
runtime checks remain with their hosts, and so do the tests of a host's own
renderers. See [renderer contracts](docs/renderers.md) for what a host renderer
may rely on.

## CAD document updates

A STEP opens in the engine document's renderer (`renderers/xbf`), as an `.xbf` does: the page
reads what the cadgen engine serves of it through the viewer (`client.engineDocument`,
`/__cad/xbf`) — its structure and one buffer per part — and reads no source or sidecar. A
rebuild reaches the view as the engine's next version, and only the parts the edit changed are
fetched. Both the tools view and its independent Preview draw the engine's meshes.
The Model tree shares the explorer's row and filter primitives. Its rows are the
document's assemblies and parts, a part a leaf whose faces and edges the viewport picks;
its expansion controls viewport selection, and its filter searches
names without expanding anything. See [the engine document renderer](docs/cad-renderer.md#engine-document-renderer)
for selection, isolation and references.

A CAD file's controls are the shell's chrome over the viewport. The tool strip at the top
centre holds the file's tools — a STEP's Select (its selection filter the chevron after it),
Pencil and Shapes (plain buttons: what each draws with is the row under the strip), Measure, then, after a thin rule, Explode and Clip; a robot's Select, Pencil, Shapes, Measure and Clip; a GLB's
Select (its nodes), Pencil, Shapes, Measure, Explode (several parts) and Clip; a 3MF's Select (its
objects), Pencil, Shapes, Measure and Clip; an STL's Pencil, Shapes and Clip — then, with no rule between, a
3D view's Display (its settings, a popover that opens down) and Preview. The tool in hand's
controls are one row under the strip, its sub-toolbar (`kit/tools/SubToolbar.jsx`):
the drawing tools' colour, stroke width, placement and history; Explode's and Clip's slider rows.
What there is to read of the file is the file sidebar at the top-left, whatever the tool
(`kit/tools/FileSidebar.jsx`): an assembly's Model tree, a robot's Links, Position, an SDF's
metadata, and Animation for a file with routines, a tile each at the top-left, a tile opening its
section in a panel under them, one at a time; each section's panel is sized from its
bottom-right grip, Quick Edit's, and keeps its own size. On a phone it is one tile, opening one panel with the sections as tabs. Sidebar sections stay mounted, so a tree keeps its scroll and expansion;
only what is on screen does background work. What is picked is Quick Edit's chips. Links is
the description's link tree, with the Model tree's rows and search box; see
[robot links](docs/cad-renderer.md#robot-links).
The binding [viewer design system](docs/settings-ui.md) defines tool lifecycle,
the file sidebar, mobile layout, section density, keyboard scope, tooltips
and Preview. RendererShell owns the strip and its sub-toolbar at the top centre, the file
sidebar, Quick Edit at the top-right and the cube at the bottom-right. Preview (preview
mode) is the shell's own, the one place Render is drawn — whatever the file's display mode,
which has no Render — and takes the whole page, the navbar and the strip with it; its own
controls stand in the view's top-right corner — Preview settings (Orbit, off at every entry,
and its speed, then Render's settings) and Exit preview — and the file sidebar offers its
Position and Animation alone at the top-left; nothing sits under the model. Routines play from
the sidebar's Animation section, in either view. Preview and the tools view are two views,
each with its own viewport, scene, camera, pose and routine over the page's one GPU device:
Preview starts from the model as authored and leaves the tools view's state untouched, and
leaving it throws Preview's away and gives the tools view back exactly as it was
([Preview](docs/settings-ui.md#camera-animation-and-preview); its mechanism,
[Preview and the camera](docs/cad-renderer.md#preview-and-the-camera)). Keep app-specific
effects in the [host contract](docs/viewer-host.md), not in renderer components.

One per-file settings store serves controls, live commands and persistence.
Presets use the canonical grouped schema; see [View presets](docs/render-mode.md).
Expensive changes use [staged viewport updates](docs/view-updates.md): controls
remain authoritative, preparation is replaceable, and captures await presentation.
The camera is part of the file's view: a refresh restores the one the file on screen
was left at, and opening a file — again after leaving it, too — fits it.

Authored material color, finish and opacity are read-only in every style. There
is no Materials editor or persisted material override. See [View styles](docs/render-mode.md) and
[loading](docs/loading.md).

The navbar leads with the C logo, which opens the app's menu: Back to files where the host
has a home, the person's settings (Share anonymous usage data), Send feedback
(a new issue titled "Feedback: " where the host has a tracker), GitHub, Discord and, in
gray, the version and who made it. Where the host keeps the view's own history (the CAD
app's views), Back and Forward follow, disabled where they have nowhere to go. It names the
file — the name opens the explorer — and offers its ⋯ menu (Copy path, Reveal). They share one look: transparent until the
pointer is on them or their menu is open, with no tooltip. At the right is only what a host
or a file adds: the host's update button, a dismissed alert's icon, the host's Full size
and, last, the view's own controls (a 3D view's Display and Preview). With no file a view
shows the host's home, the model library, under the same navbar (its logo and menu, without
Back to files, Back and Forward where the host keeps the view's history, and the host's
update and Full size): its wordmark, byline and GitHub,
Discord and X, then the models opened before, pinned first, with their pictures, and Open
where the host has a file chooser. A file that
does not exist shows "File does not exist" and its path, and any other failure to open
"Could not open that file" and why, each with Go home where the host has a home. A
renderer's loading and update status is its own, in its viewport. An error appears as a
card over the viewport; a failed update the
model survives can be dismissed, leaving the previous version to inspect, and the card's own
icon, the first of the navbar's right-hand controls after the update button while it is put
away, brings it back.
Retry reloads only the selected renderer; Report Issue, where the host has a tracker, opens a
new issue titled "Issue: ", labelled `bug`, filled in from the card, with the file's name and
no path of the machine. The card's Details have a copy icon at their top-right corner, which
copies all of them through the host's clipboard.
