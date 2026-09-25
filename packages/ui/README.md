# @hardcore/ui

The shared React interface for Hardcore. `FileViewer` is the complete file tab:
its breadcrumb row, menus, content, file tree, one panel column, loading and
error states, and common edit/save/reload lifecycle. Both `apps/web` and
`apps/desktop` consume this component through the package's compiled exports.
The desktop's project/session/window layout remains application code.

The viewer's tools, sidebars, settings, tooltips and keyboard follow one
binding [design system](docs/settings-ui.md), the same in both apps. A change to
that chrome changes the design system first. Desktop's surrounding app controls
remain local where their appearance differs.

## Ownership and dependencies

UI may import `@hardcore/core` and browser-safe React dependencies. It must not
import an application, Electron, Node services, desktop IPC schemas, app stores,
or `window.hardcore`. Hosts inject file access, capabilities, navigation,
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

File-tab chrome uses normal-weight type. Breadcrumbs, file and model rows, and
filter matches use muted/primary text color for emphasis, never bold weight. Tree
rows — files, model features, robot links — are 12px, the size of the section
titles and the filter above them.
Both tree lists inset row backgrounds 4px from their horizontal edges, including
selected, hovered and filtered rows; nesting adds indentation inside that gutter.
Every sidebar — the file tree and a file's own panel — shares a 256px minimum
width. On desktop, resizing below it closes the panel; reopening restores 280px. Below 720px of total FileViewer width, panels are dismissible floating sheets and never shrink the scene. The sheets have no extra visible title row and never scroll or translate the host page.
The view cube is hidden on mobile. Breadcrumbs and progress indicators use this same breakpoint. Panels never
scroll sideways: a Position section's labels truncate to preserve its sliders and
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
  file-viewer/       FileViewer, typed source/renderer contracts, lifecycle hooks
    navigation/     breadcrumbs, file tree, entry menus and panel frame
  renderers/
    kit/            the frame every viewer file shares: viewport, tools, panels, Display settings, status
    step/           STEP: Features tree, Position, Animate, feature recognition
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
priority, panels, asynchronous preparation, lazy component loading and disposal.
Each app registers only the file types its source supports. A renderer's code
loads when a file selects it; adding a renderer does not add a branch to FileViewer.
The registry rejects duplicate IDs and ambiguous matches.

This package ships the viewer renderers both apps register. A renderer only one
app registers is that app's own, built on the same public `defineFileRenderer`
contract: the desktop's Markdown, code, image, PDF and unsupported-file
renderers live in `apps/desktop` (see [renderers](docs/renderers.md)).

File listing is independent of renderer matching: the tree shows every entry
the host's source returns. A host that exposes arbitrary files registers a
fallback renderer (`fallback: true`) for the types nothing else matches.

```tsx
import { FileViewer } from '@hardcore/ui/file-viewer';
import { createStepRenderer } from '@hardcore/ui/renderers/step';
import { createDxfRenderer } from '@hardcore/ui/renderers/dxf';
import { createGlbRenderer } from '@hardcore/ui/renderers/glb';
import { createMeshRenderer } from '@hardcore/ui/renderers/mesh';
import { createRobotRenderer } from '@hardcore/ui/renderers/robot';
import '@hardcore/ui/tokens.css';
import '@hardcore/ui/styles.css';

// One viewer renderer per file family, sharing one client and one preference source.
const renderers = [createStepRenderer({ client, preferences }), createDxfRenderer({ client, preferences }),
  createGlbRenderer({ client, preferences }), createMeshRenderer({ client, preferences }),
  createRobotRenderer({ client, preferences })];
// The host supplies storage, actions, navigation and environmental ports.
<FileViewer file={selectedFile} host={host} renderers={renderers}
  state={state} onStateChange={setState} />;
```

Public entry points include `/host`, `/file-viewer`, `/navigation`, `/renderers/step`,
`/renderers/dxf`, `/renderers/glb`, `/renderers/mesh`, `/renderers/robot`, `/renderers/workspace`, `/file-viewer/presentation`, `/file-viewer/empty`,
`/drawing`, `/loading-icon`, `/utils`, `/primitives/*`, `/tokens.css`, and `/styles.css`.
Declarations are owned here; apps need no ambient shims or aliases into this
source tree.

`/drawing` is a separate lazy entry point for the Excalidraw editor, for temporary
sketches, with no platform discovery or persistent storage. Desktop owns its temporary Drawing tabs,
in-memory scene retention and prompt delivery; the viewer's Draw tool mounts the
same editor as an overlay in both apps.
Read [drawing](docs/drawing.md) before extending this editor or reusing it for
viewer annotations.

The required host contract, typed prompt bundles, delivery receipts and named
renderer slots are documented in [viewer host](docs/viewer-host.md). Clipboard
and page reload implementations live in the apps. Shared UI performs no
raw transport, clipboard discovery, host storage or page-navigation effects.

## Lifetimes and state

`FileSource` describes storage only: stat/list/search, optional reads and optional
write/create/rename/duplicate/trash operations. Menus derive storage capabilities
from these methods and native/copy capabilities from the separate `FileActions`
port. Missing methods remain unavailable. A web catalog source stays read-only;
listing never filters entries by renderer support.

Writes return saved, conflict, cancelled or error outcomes; mutations return
committed receipts, cancellation or typed failures. The desktop validates the
expected content revision, serializes writes to the same path and atomically
replaces its contents. Aborting a caller after dispatch does not undo a committed
operation. Hosts reconcile committed receipts even after that caller unmounts;
shared document/navigation hooks discard its late UI response.

Source subscriptions distinguish content and metadata changes from added,
deleted and moved entries. Content changes reload a clean document or mark its
draft stale; metadata changes do not discard a draft. Renames carry drafts to
the new path and remap every expanded/cached descendant. Hosts reconcile other
open tabs too. Deletes prune descendant listings while dirty editors retain
an explicit stale draft. Successful saves preserve typing made during the write.

A source has a stable root identity independent of a server's ephemeral port.
File state is scoped by root, path and renderer. Changing source or file aborts
pending preparation, releases prepared assets, and discards stale async results.
A renderer owns its viewport and resources; the host owns its CAD client. Last
render-session disposal releases shared worker leases. One viewer cannot replace
another viewer's cache provider or camera state.

Completed STEP CPU working sets can outlive a viewport in the shared renderer's
bounded cache. They retain exact decoded component buffers and copy structural
metadata for each mount; scene objects, controls and pending work are not cached.
Reuse is scoped to root, resource-provider generation and file revision. See
[CAD resource lifetime](docs/cad-renderer.md) for cache bounds and invalidation.
The Features tree can reuse those accepted component identities for completed
recognition metadata after the runtime descriptor also matches, avoiding surface
requests on a warm reopen without retaining another copy of the geometry.

The host owns stored state. The web adapter retains browser URL/history and
session preferences; desktop retains its explorer/project preferences and IPC
watchers. Both build the viewer's orbit preference with
`createStoredCadPreferences` and merge renderer records with
`mergeChangedRecords`. A viewer's per-file record holds its Display settings,
its tool and its renderer's slice, never a camera. Capabilities determine menus: a read-only web source cannot
acquire editing or native operations merely by rendering this component.

## Development and verification

From the repository root:

```sh
npm ci
npx --no-install playwright install chromium
npm run build:packages
npm run typecheck --workspace @hardcore/ui
npm test --workspace @hardcore/ui
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
integration tests for renderer preparation, saves/conflicts, root changes,
multiple instances, cancellation and disposal. App integration and packaged
runtime checks remain with their hosts, and so do the tests of a host's own
renderers. See [renderer contracts](docs/renderers.md) for what a host renderer
may rely on.

## CAD document updates

The STEP renderer consumes the artifact, its schema-9 `.step.json`
sidecar and immutable store views. Embedded animation, authored appearance and
kinematics travel in the sidecar; an adjacent `.step.js` is a retired input.
The scene uses progressive component loading and demand-driven exact surfaces.
The Model tree shares the file tree's row and filter primitives. Its visible expansion
controls viewport selection, exact topology and optional feature recognition;
collapsed parts do not trigger whole-assembly analysis, and neither does its
filter, which searches names without expanding anything. Contextual measurements
remain available in Render too. See [model tree and recognition](docs/cad-renderer.md#step-panel)
for selection, isolation, demand and cache ownership.

Feature detection stays client-side in this renderer, separate from cadgen
compilation, Python inspection and reference syntax. Both apps reuse its worker
and versioned, bounded memory cache; it adds no persistent store. Read
[feature detection](docs/feature-detection.md) before changing inference rules,
cache identity, cancellation or recognition limits.

A file can expose one optional `Settings` panel with the sliders icon in the
nav row, beside the file tree. `FilePanelTabs` reads each section's `role`, not
its name: when a `model` and a `position` section both exist it separates them
into Features / Position or Links / Position tabs, whose primary views are always
open, with no collapse headers. Both stay mounted to preserve scroll and tree
state; only the active tab does background work. Without Position, the model
panel shows directly. Each tab has one scrolling column and the selection
Reference pinned at its foot. Issues and SDF metadata remain with the model tree.
Links is the description's link tree, with the Model
tree's rows, filter and Reference pane; see [robot links](docs/cad-renderer.md#robot-links).
Which panel a file opens with is the host's to apply
(`ViewerHost.navigation.openFile(path, { target, panel })`): a file picked in the
tree asks for the tree, so the tree stays up while a person walks it; any other
open gets the file's own panel, or nothing when it has none. No panel is saved
in a file's record. Display is a toolbar popover, never a panel.
The binding [viewer design system](docs/settings-ui.md) defines tool lifecycle,
sidebar navigation, mobile layout, section density, keyboard scope, tooltips
and fullscreen. RendererShell owns the top-left toolbar and bottom-right cube;
Display is the last toolbar item and Animate is conditional on clips.
Fullscreen is a separate top-right action, the shell's own, and preserves the
parent navbar. Keep app-specific effects in the
[host contract](docs/viewer-host.md), not in renderer components.

One per-file settings store serves controls, live commands and persistence.
Presets use the canonical grouped schema; see [View presets](docs/render-mode.md).
Expensive changes use [staged viewport updates](docs/view-updates.md): controls
remain authoritative, preparation is replaceable, and captures await presentation.
Camera transforms remain local to a mounted viewer; refresh/reopen fits the file.

Authored material color, finish and opacity are read-only in every style; the
Model reference section shows their properties. There is no Materials editor or
persisted material override. See [View styles](docs/render-mode.md) and
[progressive detail](docs/lod.md).

The navbar names the file and carries compact loading/update status. An error
appears as a card over the viewport;
a failed update the model survives can be dismissed, leaving the previous
version to inspect. Try again reloads only the selected renderer.
