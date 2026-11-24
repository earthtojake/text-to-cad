# @cad/ui

The shared React interface for text-to-cad. `FileViewer` is the complete file view:
one file by its absolute path (`/a/b.step`, `C:/a/b.step`, `/`-separated in every
app), or the host's home with none, under a navbar — the logo that opens the app's
menu, the file's name and the name menu it opens (Models and Files), the file menu — with the file's
content and the loading and error states ([FileViewer](docs/file-viewer.md)).
`CadViewer` (`@cad/ui/cad-viewer`) is the viewer every app shows:
FileViewer over a CAD client, with the six CAD renderers, the home (the model
library) and the standard loading and missing-file pages. `apps/web` and `apps/mcp` consume both through the package's compiled
exports; a host's own project, session and window layout remains application code.

The viewer's tools, panel, settings, tooltips and keyboard follow two binding documents, the same in
both apps: the [design system](docs/design-system.md) (the tokens, the two scales, the components, touch)
and [the viewer's layout and patterns](docs/viewer-ux.md) (what goes where and why, the patterns). A change to
that chrome changes them first. The CAD app's surrounding host controls
remain its own.

**The viewer is read-only, with one exception.** It writes no document's content and no file of
one (an export is a download of a new file; the home's Delete removes the engine's record and cache
of a document, never its file). Changing a design belongs to the agent and the code, and every
viewer tool (Select, Measure, Draw, Quick Edit, the filters and displays) exists to show the
person the design and to give the agent feedback. The exception is a model's **Params** tab
([Parameters](docs/viewer-ux.md#parameters)): its Save asks the engine to set the named numbers
the model's script declares (`client.setModelParameters`, `POST /api/v1/documents/model/<id>/parameters`),
the one way the engine writes them. The engine, not the page, rewrites each number in
the script where its last run recorded it, after checking the script is the one that ran, and builds
the model again; the page then reads the rebuilt document as it reads any new version. Before a Save,
the view draws the model at the drafts (`client.previewModelParameters`,
`POST /api/v1/documents/model/<id>/preview`): the engine builds it for this page alone and writes
nothing, and the preview is never the document (what Export, a snapshot, another page or the agent
reads). Nothing else in the viewer changes a design: no other control writes a script, a document or a
file, and a document read from a file (an `.xbf`) shows its parameters read-only. A host whose client
cannot save leaves the method out, and the tab shows the values without Save; one that cannot preview
leaves that method out, and the view shows a value once it is saved. What was saved is told to the
agent once, with the next Quick Edit, and values drawn but not saved with every one sent meanwhile.

## Ownership and dependencies

UI may import `@cad/core` and browser-safe React dependencies. It must not
import an application, Node services, desktop IPC schemas, app stores,
or `window.textToCad`. Hosts inject file access, capabilities, navigation,
persistence, appearance and CAD services. Importing a package starts no polling,
workers or host storage writes and changes neither document title nor theme.

Shared UI is platform-agnostic: components must not detect web versus the CAD app
to choose their behavior. Express environmental differences through injected
capabilities and app-supplied named slots. React, DOM, canvas and responsive
layout remain shared; operating-system details and app workflows belong to the
host. Follow [the feature-extension workflow](docs/viewer-host.md#adding-a-shared-feature)
when introducing a new integration.

The design system's type is [two scales](docs/design-system.md#the-type-scale) of three sizes and a heading, each
on a fixed line height ([src/styles/tokens.css](src/styles/tokens.css) and
[src/styles/globals.css](src/styles/globals.css)). A desktop's, the reference: `text-tiny` 11/16 (tooltips, shortcut
hints, small metadata), `text-xs` 12/16 (the view's panel, Quick Edit, the sub-toolbars, and every menu,
dropdown and context menu), `text-ui` 13/20 (app chrome: the navbar, dialogs, the Home; the default, which
`text-sm` and `text-base` resolve to for shared and host controls) and `text-heading` 15/20 semibold (the one
heading). A phone's (the viewer's mobile layout, under 600px) takes each step 2px up: 13/18, 14/20, 15/20 and
17/22. Hosts apply `text-ui` to their body; FileViewer also sets it at its own boundary.
Document headings and code retain their content styles. The menu (`DropdownMenu`, every value picker's list
too: `ValueDropdown`), context-menu and tooltip
primitives set their own size and line, including checkbox/radio items and submenus, portals included;
consumers do not add per-menu font-size overrides. These defaults belong to the primitives, including the CAD
app's host-level equivalents.
Viewer hover hints use `TooltipHint` from the shared tooltip primitive, with
`text-tiny` text (11px; a phone's 13) and a 400ms delay. Use short action names, omit redundant hints on
obvious or already labeled controls, and show full tree/field names only when
clipped. Native HTML `title` attributes are not used for interface tooltips.

The token uses rems so a host's UI scaling still works without changing the
normal 16px root or shrinking layout spacing.

The model area takes the person's Background (Light by default, or Dark), never the app's theme: the
scene, its overlays and a 2D view's paper are drawn in the viewport's theme (`@cad/core/lib/viewportTheme.js`, the
scene's colours written once), the chrome in the app's ([the palette](docs/design-system.md#the-palette),
[the viewport's scheme](docs/design-system.md#the-viewports-scheme)).
Every control's label is `FieldLabel` (muted), its value the foreground.

File-tab chrome uses normal-weight type. The navbar's file name, the explorer's and
the model tree's rows, and filter matches use muted/primary text color for emphasis,
never bold weight. The explorer's rows are compact 24px lines in 12px text, the size of
the section titles and the filter above them, a folder opening inline under itself; the
view's panel's lists — every one of them, the Model, the Links, the Parts, the Nets, the Hierarchy,
the Layers — share the STEP/xbf Model tree's base components (`primitives/tree-row.jsx`'s row, slot,
name, detail and heading, `primitives/tree-filter.jsx`'s search highlight and count, `VirtualRows`),
never a view's own, in the panel's 12px text, one glyph slot a row
([the panel's trees](docs/viewer-ux.md#trees)). Both inset
row backgrounds 5px from their horizontal edges, including selected, hovered and
filtered rows; nesting adds indentation inside that gutter.
The name menu is a popover under the navbar's file name: Models and Files as stock Tabs over
the explorer's rows (`ModelList.jsx`, `FolderExplorer.jsx`),
17.5rem wide, no taller than 28rem or the room below it, with no resize handle. It
floats over the view and never resizes it or moves its tools. A file's controls are
the viewer's own: the tool strip at the view's top centre, the tool in hand's sub-toolbar
under it, and the one panel docked at its left, the canvas the narrower for it while it pushes it aside (a mouse
resting on its collapsed toggle peeks it over the view instead, a floating card pushing nothing, pinned only by the toggle).
FileViewer is mobile below 600px of its own width; progress indicators use this same
breakpoint. The panel never scrolls sideways: Joints' labels truncate to preserve its
sliders and inputs.

React, ReactDOM, Three.js and Lucide are host-supplied peers. React 18 and 19
are supported: the web viewer and the CAD app use React 19.3.1. Each
host must resolve one copy of each peer in its browser bundle. Web uses Vite
deduplication so shared imports use its host React and Lucide versions;
these peers are not bundled into UI.

```text
src/
  host/              explicit host ports, prompt actions and React binding
  annotation/        the drawing tool's (Draw: freehand and shapes) session, toolbar and ink geometry (its 3D ink is renderers/kit/tools/annotate)
  cad-viewer/        CadViewer (FileViewer + the six CAD renderers + the home), and a CAD client as a FileSource
  file-viewer/       FileViewer, typed source/renderer contracts, the document lifecycle hook
    navigation/     the navbar, the app menu and its links, the folder explorer, the file menu
  library/           a host's home: the models opened before, to open again, and their pictures
  renderers/
    kit/            the frame every viewer file shares: viewport, tools, panels, Display settings, status
    xbf/            an engine document (.xbf) and a STEP: model tree, Params, Joints
    robot/          URDF and SRDF: Links and Joints
    glb/, mesh/     GLB, and STL/3MF triangle meshes
    dxf/            2D drawings
    workspace/      a viewer file's catalog entry and document load
    harness/, shell-harness/  surfaces the browser suites drive
  primitives/       shared controls: buttons, menus, the value dropdown, sheets, tooltips, tree rows
  lib/              browser helpers
  loading/          the one loading indicator: a step line over a thin bar
  styles/           canonical tokens and component CSS
  assets/           lightweight UI assets
dist/               generated ESM, declarations, CSS, assets and worker modules
```

The marks' provenance is [src/assets/README.md](src/assets/README.md);
the DXF and robot renderers' fixtures are described beside them
([dxf](src/renderers/dxf/__fixtures__/README.md), [robot](src/renderers/robot/__fixtures__/README.md)).

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
import { FileViewer } from '@cad/ui/file-viewer';
import { createDxfRenderer } from '@cad/ui/renderers/dxf';
import { createGlbRenderer } from '@cad/ui/renderers/glb';
import { createMeshRenderer } from '@cad/ui/renderers/mesh';
import { createRobotRenderer } from '@cad/ui/renderers/robot';
import { createXbfRenderer } from '@cad/ui/renderers/xbf';
import '@cad/ui/tokens.css';
import '@cad/ui/styles.css';

// One viewer renderer per file family, sharing one client and one preference source.
const renderers = [createDxfRenderer({ client, preferences }), createGlbRenderer({ client, preferences }),
  createMeshRenderer({ client, preferences }), createRobotRenderer({ client, preferences }),
  createXbfRenderer({ client, preferences })];
// The host supplies storage, actions, navigation and environmental ports.
<FileViewer file={selectedFile} host={host} renderers={renderers}
  state={state} onStateChange={setState} />;
```

Public entry points include `/host`, `/file-viewer`, `/tab-store`, `/navigation`,
`/renderers/dxf`, `/renderers/glb`, `/renderers/mesh`, `/renderers/robot`, `/renderers/xbf`, `/renderers/workspace`, `/file-viewer/presentation`,
`/cad-viewer`, `/catalog`, `/links`, `/library`, `/consent` (the app menu's Telemetry row and its state), `/whats-new` (the What's new dialog, its notes and when it shows), `/i18n` (the locales and the translation hook), `/i18n/locale` (which locale a person reads in, with no dictionary: for a page that says a few words before anything else loads), `/build-id` (what a Vite config names the build with), `/utils`, `/primitives/*`,
`/tokens.css`, and `/styles.css`. `/catalog` (a CAD client as a `FileSource`, the file menu's
Copy path and Reveal, and the one spelling of an absolute path: `normalizePath`, `baseName`,
`joinPath`) and `/links` (the navbar's link defaults) are pure modules, with no React, for a
host's adapters and their unit tests.

A CAD host composes `CadViewer` rather than FileViewer and the renderers: it hands
over its CAD client, its ports (`files` is `createCadFileSource(client)`), its tab store,
the file on screen (absolute; `''` is the home) and how to show another (`onShow`), and
its library.

```tsx
import { CadViewer, createCadFileSource } from '@cad/ui/cad-viewer';

const host = { files: createCadFileSource(client), clipboard, promptContext, environment };
<CadViewer client={client} host={host} tabStore={tabStore} live={live} file={file}
  onShow={showFile} library={library} onThumbnail={keepPicture} />;
```
Declarations are owned here; apps need no ambient shims or aliases into this
source tree.

The viewer's drawing tool (Draw: freehand and shapes) is native ink projected into the model, with no drawing
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
viewer keeps is one tab record (`@cad/ui/tab-store`: the tab's settings and
the view of the file on screen — its camera, Display settings, Preview's Render settings,
its playback settings and the renderer's own slices), thrown out with the tab and kept across a reload. Leaving a file, for
another or for the home, sets its view aside for the page, which gives it back as the file is
shown again (`CadViewer`), and an update of it keeps what still fits the new revision. The web keeps it in `sessionStorage`, the CAD app in
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
npm run typecheck --workspace @cad/ui
npm test --workspace @cad/ui
npm run check:boundaries
```

`check:boundaries` also holds `src/renderers/kit` format-blind: it imports no renderer
and names no file format ([Kit](docs/cad-renderer.md#kit)).

Rebuild shared packages after editing them; hosts resolve `dist`, never `src`.
Install the npm Playwright browser even if Python Playwright's (the viewer's launch
smoke test's) is already installed; they may require different Chromium revisions. On Linux, add
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

A document is what a person reviews: a file in a format the viewer reads, or a model the engine built from
code. The viewer exists so that a person can review an agent's subjective output and answer it through the
tools, annotate, select and quick edit; every renderer serves that review.

A STEP opens in the engine document's renderer (`renderers/xbf`), as an `.xbf` does: the page
reads what the engine serves of it through the viewer (`client.engineDocument`,
`/api/v1/documents/<kind>/<id>`) — its structure and one buffer per part — and reads no source or sidecar. A
rebuild reaches the view as the engine's next version, and only the parts the edit changed are
fetched. Both the tools view and its independent Preview draw the engine's meshes.
The Model tab's tree shares the explorer's row and filter primitives. Its rows are the
document's assemblies and parts, a part a leaf whose faces and edges the viewport picks;
its expansion controls viewport selection, and its filter searches
names without expanding anything. See [the engine document renderer](docs/cad-renderer.md#engine-document-renderer)
for selection, isolation and references.

A CAD file's controls are the shell's chrome over the viewport. The tool strip at the top
centre holds the file's tools — a STEP's Select (its selection filter the chevron after it),
Draw (one plain button; its row under the strip holds the freehand and shape tools), Measure, then Explode and Clip; a robot's Select, Draw, Measure and Clip; a GLB's
Select (its nodes), Draw, Measure, Explode (several parts) and Clip; a 3MF's Select (its
objects), Draw, Measure and Clip; an STL's Select (its bodies), Draw and Clip.
No rule parts the strip, at Figma's toolbar's proportions (a 40px bar of 28px tiles 5px in; a phone's tiles 36px). The view's settings are the navbar's,
for every kind of file: **Display** (the plain cube, no chevron; a toggle whose card, `kit/shell/DisplaySettings.jsx`,
docks under the navbar at the view's right edge, the sidebar's peek card mirrored), then a 3D view's Preview, and a
board's. The corner at the top-right keeps only the camera's own control: a 3D view's cube, or a flat view's one "100%"
zoom dropdown. The strip holds tools only, and a phone's More only the tools that do not fit it. A phone's picture has no corner control. The bottom row is Quick Edit's alone. The tool in hand's
controls hang under the strip, its sub-toolbar (`kit/tools/SubToolbar.jsx`):
Draw's two rows of seven (the tools that put ink down; then the Eraser, Colour, Stroke width, Placement, Undo, Redo
and Clear); Measure's chips. Explode's and
Clip's slider rows open in a popover from their tiles, taking up no tool.
The view's one panel, docked at the left, whatever the tool
(`kit/shell/FlatPanel.jsx`): one head row, as Figma's Layers panel's — a tab per part of the file's structure (a STEP's or
an .xbf's Model, a robot's Links; a board's Parts, Nets and Layers, a
schematic's Parts, Nets and Hierarchy, a drawing's Layers), then, only where the file has them, its Params, Joints and
Animation (`ToolPanel`s; their rows `kit/inspector/panelRows.jsx`), then Search, an icon that turns the head's row into the one search box, in the tabs' (or the title's) place, nothing under
it moving, its results one tree's hits or, where several tabs are searched (a board's, a schematic's), one list grouped
by tab (one tab is a plain title, in the tabs' own block, so the head never changes height) — its lists at its full height, in one
12px text size and 28px rows, a row's one glyph on the 16px line and its name 32px in. What is picked is read in Quick
Edit's chip list (each reference its kind and key facts: `kit/inspector/inspect.js`'s descriptions); the hover tip over
the canvas is the frame's (`kit/shell/ViewFrame.jsx`). Pinned open, the panel always pushes the model aside; collapsed, a mouse
resting on its toggle peeks it over the model, a floating card 4px in from the edges, its content where the docked
panel's is, pushing nothing, kept nowhere and pinned only by the toggle (`kit/shell/usePanelPeek.js`); until the
person opens or closes it on a file, it follows the view, collapsed where it would leave the model under 640px, never
written, and after that their choice holds on that file at any width (`kit/shell/sidebars.js`); it is 232px wide
(budgeted for three tabs) until its grip sets another width, from 200 to 480px at any window width, its toggle the navbar's first control, before the logo (`file-viewer/panelToggles.js`; ⌘\); on a
phone the toggle opens it as a sheet from the left (`primitives/sheet.jsx`).
Its tabs stay mounted, so a tree keeps its scroll and expansion;
only what is on screen does background work. What is picked is Quick Edit's chips. Links is
the description's link tree, with the Model's rows and search box; see
[robot links](docs/cad-renderer.md#robot-links).
The binding [viewer layout and patterns](docs/viewer-ux.md) defines tool lifecycle,
the view's panel, mobile layout, keyboard scope, tooltips
and Preview, and the binding [design system](docs/design-system.md) section density, the components and touch.
RendererShell owns the strip and its sub-toolbar at the top centre of the window, the
panel docked at its left (the strip and Quick Edit centred on the window over it), Quick Edit's bar at the bottom and the
cube alone at the top-right. Preview (preview
mode) is the shell's own, the one place Render is drawn — whatever the file's display mode,
which has no Render — and takes the whole page, the navbar and the strip with it, in every
host; in the navbar's place its own bar, on no surface, names the file and holds Display
(Orbit, off at every entry, and its speed, then Render's settings, sliding in from the right
edge) and Exit preview, fading with the playbar while the pointer rests; for a file with
routines, Preview's own playbar sits under the model. Routines play in the tools view from the panel's
Animation tab (a mechanism's motion from the top of its Joints tab; Speed and Loop its rows, its scrubber's start
the rest pose), and from Preview's own playbar in Preview. Preview and the tools view are two views,
each with its own viewport, scene, camera, pose and routine over the page's one GPU device:
Preview starts from the model as authored and leaves the tools view's state untouched, and
leaving it throws Preview's away and gives the tools view back exactly as it was
([Preview](docs/viewer-ux.md#camera-animation-and-preview); its mechanism,
[Preview and the camera](docs/cad-renderer.md#preview-and-the-camera)). Keep app-specific
effects in the [host contract](docs/viewer-host.md), not in renderer components.

One per-file settings store serves controls, live commands and persistence.
Presets use the canonical grouped schema; see [Display modes](docs/render-mode.md), and
[render types](docs/render-types.md) for the rule that shared viewer code never asks what a
format is, and the format → icon map it does read.
Expensive changes use [staged viewport updates](docs/view-updates.md): controls
remain authoritative, preparation is replaceable, and captures await presentation.
The camera is part of the file's view: a refresh restores the one the file on screen
was left at, a file the page left is shown again at the one it was left at, and opening a file
the page has not shown fits it.

Authored material color, finish and opacity are read-only in every style. There
is no Materials editor or persisted material override. See [View styles](docs/render-mode.md) and
[loading](docs/loading.md).

The navbar leads, over a file with a panel, with the panel's toggle, then the logo (the C mark, over the
home and over a document alike), which opens the app's menu: Back to home where the host
has a home, the person's settings (Language, Telemetry, Theme), Send feedback
(a new issue titled "Feedback: " where the host has a tracker), GitHub, Discord and, in
gray, the version and who made it. Where the host keeps the view's own history (the CAD
app's views), Back and Forward follow on a desktop (a phone has no room for them), disabled where they have nowhere to go. It names the
file (no glyph) — the name opens Models and Files — and offers its ⋯ menu (Copy path; Open in,
a submenu of Browser where the host has one and Finder, File Explorer or File manager; then
Export, a submenu of the formats; a model's Copy path and file manager act on its script). They share one look: transparent until the
pointer is on them or their menu is open, with no tooltip. At the right is only what a host
or a file adds: a dismissed alert's icon, the host's actions (the
CAD app's Full size), after the view's own, which it portals into the navbar's view slot (Display, then a 3D view's
or a board's Preview). The navbar is there in every host; only Preview, which draws its own bar, and a compact view
are without it. With no
file a view shows the host's home, the model library, under the same navbar (its logo and menu,
without Back to home, Back and Forward where the host keeps the view's history, and the host's
actions): one control row (Recent; the type filter, the search, grid or list),
then the library alone: the documents opened or built before, pinned first, as Figma-style
tiles with their pictures or as a table of rows, each with its pin and a ⋯ menu ending in
Delete, which asks first. A file that
does not exist shows "File does not exist" and its path, and any other failure to open
"Could not open that file" and why, each with Go home where the host has a home. A
renderer's loading and update status is its own, in its viewport. An error appears as a
card over the viewport; a failed update the
model survives can be dismissed, leaving the previous version to inspect, and the card's own
icon, the first of the navbar's right-hand controls while it is put
away, brings it back.
Retry reloads only the selected renderer; Report Issue, where the host has a tracker, opens a
new issue titled "Issue: ", labelled `bug`, filled in from the card, with the file's name and
no path of the machine. The card's Details have a copy icon at their top-right corner, which
copies all of them through the host's clipboard.

The native `.kicad_pcb` renderer lives in `src/renderers/board/`, using the same file service,
selection, Measure, annotation and Quick Edit host capabilities as the other renderers. A board has Preview as a 3D
file has (the same button right of Display, bar, settings, less Part colours, and camera), showing the board as it is
made, lit, in a view of its own (`board/BoardPreviewView.jsx` over the kit's `usePreviewFrame.jsx`); its 2D/3D Mode
and its tools are untouched by it ([a board in 3D](docs/viewer-ux.md#a-board-in-3d)).
It consumes the core plot payload; authoring and DRC belong to KiCad and the `cad` command.
The `.kicad_sch` renderer, `src/renderers/schematic/`, is the same flat plot view from the kit
(`kit/viewport/usePlotView.js`, `kit/inspector/CircuitTree.jsx`, `kit/tools/select/SelectFilterMenu.jsx`),
read a sheet at a time (`GET .../kicad_sch/<id>/plot?sheet=<path>`, the hierarchy's index with the
first): its Parts, Nets and Hierarchy in the view's panel, the Hierarchy and a sheet symbol's double-click
to move between sheets (each keeping its view for the session), drawn in the viewport's Background (its Display
card's one row), never the app's theme; ERC belongs to the
`cad` command.
