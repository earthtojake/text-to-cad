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

The viewer's tools, tool stack, settings, tooltips and keyboard follow one
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
and submenus. Menu shortcuts use 10px metadata. These defaults belong to the
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
never bold weight. The explorer's rows are 12px, the size of the section titles and
the filter above them; the tool stack's trees (Features, Links) are denser, in the
panels' 11px text ([the tool stack](docs/settings-ui.md#the-tool-stack)). Both inset
row backgrounds 4px from their horizontal edges, including selected, hovered and
filtered rows; nesting adds indentation inside that gutter.
The file explorer is a popover under the navbar's file name (`FolderExplorer.jsx`):
18rem wide, no taller than 28rem or the room below it, with no resize handle. It
floats over the view and never resizes it or moves its tools. A file's controls are
panels of the viewer's own tool stack under the toolbar, one width for every panel
until a person sizes one, bounded by the viewer's height. FileViewer is mobile below
720px of its own width; progress indicators use this same breakpoint. Panels never
scroll sideways: a Position panel's labels truncate to preserve its sliders and
inputs.

React, ReactDOM, Three.js and Lucide are host-supplied peers. React 18 and 19
are supported: web and desktop use React 19.3.0. Each
host must resolve one copy of each peer in its browser bundle. Web uses Vite
deduplication so shared imports use its host React and Lucide versions;
these peers are not bundled into UI.

```text
src/
  host/              explicit host ports, prompt actions and React binding
  drawing/           reusable Excalidraw editor; desktop scratch drawing host
  cad-viewer/        CadViewer (FileViewer + the five CAD renderers + the home), and a CAD client as a FileSource
  file-viewer/       FileViewer, typed source/renderer contracts, the document lifecycle hook
    navigation/     the navbar, the app menu and its links, the folder explorer, the file menu
  library/           a host's home: the models opened before, to open again, and their pictures
  renderers/
    kit/            the frame every viewer file shares: viewport, tools, panels, Display settings, status
    step/           STEP: Features tree, Position, routines, feature recognition
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
import { createStepRenderer } from '@text-to-cad/ui/renderers/step';
import { createDxfRenderer } from '@text-to-cad/ui/renderers/dxf';
import { createGlbRenderer } from '@text-to-cad/ui/renderers/glb';
import { createMeshRenderer } from '@text-to-cad/ui/renderers/mesh';
import { createRobotRenderer } from '@text-to-cad/ui/renderers/robot';
import '@text-to-cad/ui/tokens.css';
import '@text-to-cad/ui/styles.css';

// One viewer renderer per file family, sharing one client and one preference source.
const renderers = [createStepRenderer({ client, preferences }), createDxfRenderer({ client, preferences }),
  createGlbRenderer({ client, preferences }), createMeshRenderer({ client, preferences }),
  createRobotRenderer({ client, preferences })];
// The host supplies storage, actions, navigation and environmental ports.
<FileViewer file={selectedFile} host={host} renderers={renderers}
  state={state} onStateChange={setState} />;
```

Public entry points include `/host`, `/file-viewer`, `/tab-store`, `/navigation`, `/renderers/step`,
`/renderers/dxf`, `/renderers/glb`, `/renderers/mesh`, `/renderers/robot`, `/renderers/workspace`, `/file-viewer/presentation`, `/file-viewer/empty`,
`/cad-viewer`, `/catalog`, `/links`, `/library`, `/consent` (the analytics card and its state), `/features` (the app menu's feature rows: `useFeatures`), `/drawing`, `/loading-icon`, `/utils`, `/primitives/*`,
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

`/drawing` is a separate lazy entry point for the Excalidraw editor, for temporary
sketches, with no platform discovery or persistent storage. Desktop owns its temporary Drawing tabs,
in-memory scene retention and prompt delivery; the viewer's Draw tool mounts the
same editor as an overlay in both apps.
Read [drawing](docs/drawing.md) before extending this editor or reusing it for
viewer annotations.

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

Completed STEP CPU working sets can outlive a viewport in the shared renderer's
bounded cache. They retain exact decoded component buffers and copy structural
metadata for each mount; scene objects, controls and pending work are not cached.
Reuse is scoped to workspace, resource-provider generation and file revision. See
[CAD resource lifetime](docs/cad-renderer.md) for cache bounds and invalidation.
The Features tree can reuse those accepted component identities for completed
recognition metadata after the runtime descriptor also matches, avoiding surface
requests on a warm reopen without retaining another copy of the geometry.

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

The STEP renderer consumes the artifact, its schema-9 `.step.json`
sidecar and immutable store views. Embedded animation, authored appearance and
kinematics travel in the sidecar; an adjacent `.step.js` is a retired input.
The scene uses progressive component loading and demand-driven exact surfaces.
The Model tree shares the explorer's row and filter primitives. Its visible expansion
controls viewport selection, exact topology and optional feature recognition;
collapsed parts do not trigger whole-assembly analysis, and neither does its
filter, which searches names without expanding anything. Contextual measurements
remain available in Render too. See [model tree and recognition](docs/cad-renderer.md#step-panels)
for selection, isolation, demand and cache ownership.

Feature detection stays client-side in this renderer, separate from cadgen
compilation, Python inspection and reference syntax. Both apps reuse its worker
and versioned, bounded memory cache; it adds no persistent store. Read
[feature detection](docs/feature-detection.md) before changing inference rules,
cache identity, cancellation or recognition limits.

A CAD file's controls are `ToolPanel`s in the tool stack, shown by the tool they
belong to. Select shows Features (a robot's Links) and, with a selection, the Reference; Position shows Position; Display and Draw show
their own panels; kept effects (Explode, Clip, Measure's results) follow. A panel
whose tool is not up stays mounted, hidden, so a tree keeps its scroll and expansion;
only what is on screen does background work. The tree's X closes it alone (Select stays
the tool, marked) until a press on Select brings it back; it starts closed for a single
part and on a phone, open for an assembly, until a person chooses.
The tree, the Reference and Position are each sized by their own bottom-right grip, Quick
Edit's. SDF metadata is a Select panel
too. Links is the description's link tree, with the Model tree's rows, filter
and Reference panel; see [robot links](docs/cad-renderer.md#robot-links).
The binding [viewer design system](docs/settings-ui.md) defines tool lifecycle,
the tool stack, mobile layout, section density, keyboard scope, tooltips
and preview. RendererShell owns the top-left toolbar, Quick Edit at the top-right and the
bottom-left cube, with a 3D view's controls on top of it: Display (its settings, a
dropdown that opens up), then Preview. Preview is the shell's own mode, where routines
play and the model orbits, and takes the whole page, the navbar with it; its corner
controls (Playback settings, Exit preview) sit in that same box over the cube's corner,
where Display and Preview sat. Keep app-specific effects in the
[host contract](docs/viewer-host.md), not in renderer components.

One per-file settings store serves controls, live commands and persistence.
Presets use the canonical grouped schema; see [View presets](docs/render-mode.md).
Expensive changes use [staged viewport updates](docs/view-updates.md): controls
remain authoritative, preparation is replaceable, and captures await presentation.
The camera is part of the file's view: a refresh restores the one the file on screen
was left at, and opening a file — again after leaving it, too — fits it.

Authored material color, finish and opacity are read-only in every style. There
is no Materials editor or persisted material override. See [View styles](docs/render-mode.md) and
[progressive detail](docs/lod.md).

The navbar leads with the C logo, which opens the app's menu: Back to files where the host
has a home, the person's settings (Share usage stats, Quick edit), Send feedback
(a new issue titled "Feedback: " where the host has a tracker), GitHub, Discord and, in
gray, the version and who made it. It names the file — the name opens the explorer — and
offers its ⋯ menu (Copy path, Reveal). The three share one look: transparent until the
pointer is on them or their menu is open, with no tooltip. At the right is only what a host
or a file adds: the host's update button, a dismissed alert's icon and the host's Full
size.
With no file a view shows the host's home, the model library: the models opened before,
pinned first, with their pictures, and Open where the host has a file chooser, under its
wordmark and GitHub, Discord and X. A file that
does not exist shows "File does not exist" and its path, and any other failure to open
"Could not open that file" and why, each with Go home where the host has a home. A
renderer's loading and update status is its own, in its viewport. An error appears as a
card over the viewport; a failed update the
model survives can be dismissed, leaving the previous version to inspect, and the card's own
icon, the first of the navbar's right-hand controls after the update button while it is put
away, brings it back.
Retry reloads only the selected renderer; Report Issue, where the host has a tracker, opens a
new issue titled "Issue: ", labelled `bug`, filled in from the card, with the file's name and
no path of the machine.
