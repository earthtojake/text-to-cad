# @hardcore/ui

The shared React interface for Hardcore. `FileViewer` is the complete file tab:
its breadcrumb row, menus, content, file tree, one panel column, loading and
error states, and common edit/save/reload lifecycle. Both `apps/web` and
`apps/desktop` consume this component through the package's compiled exports.
The desktop's project/session/window layout remains application code.

The package extraction and host-boundary migration preserve behavior. Preserve the existing UI, UX and
functionality of docs, web and desktop: styling, labels, defaults, shortcuts,
file actions, editing and conflict behavior, CAD interactions, persistence,
and narrow layouts. The approved exceptions are the shared primary prompt action
(Add to prompt in desktop, clipboard delivery in web) and removal of the
reference coaching tooltip. Other features or visual changes require separate review.
The viewer's shared controls keep their original appearance. Desktop's
surrounding app controls remain local where their existing appearance differs.

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
The token uses rems so desktop UI scaling still works without changing the
normal 16px root or shrinking layout spacing.

File-tab chrome uses normal-weight type. Breadcrumbs, file and model rows, and
filter matches use muted/primary text color for emphasis, never bold weight.
Both tree lists inset row backgrounds 4px from their horizontal edges, including
selected, hovered and filtered rows; nesting adds indentation inside that gutter.
Every panel — the file tree, a file's own panel, Display — shares a 256px minimum
width. Resizing below it closes the panel; reopening restores 320px. Panels never
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
    markdown/       preview/editor and lossless Markdown bridge
    code/           Monaco editor and worker setup
    image/          image view and zoom
    pdf/            PDF.js pages, text selection and host-bound capture
    unsupported/    Not supported message and optional OS-open action
  primitives/       shared controls retaining the viewer's existing styling
  lib/              browser helpers
  loading/          shared loading animation
  styles/           canonical tokens and component CSS
  assets/           lightweight UI assets
dist/               generated ESM, declarations, CSS, assets and worker modules
```

`FileViewer` has no concrete renderer imports. A registration describes matching,
priority, panels, asynchronous preparation, lazy component loading and disposal.
Each app registers only the file types its source supports. CAD, Monaco and
TipTap load when selected; adding a renderer does not add a branch to FileViewer.
The registry rejects duplicate IDs and ambiguous matches.

File listing is independent of renderer matching: the tree shows every entry
the host's source returns. Hosts that expose arbitrary files register the
unsupported fallback, which shows “Not supported” without reading the file's
contents, plus “Open externally” when the host provides that action.

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
`/renderers/dxf`, `/renderers/glb`, `/renderers/mesh`, `/renderers/robot`, `/renderers/workspace`, `/renderers/step/state`, `/file-viewer/presentation`, `/file-viewer/empty`,
`/renderers/markdown`, `/renderers/code`, `/renderers/code/editor`,
`/renderers/image`, `/renderers/pdf`, `/renderers/unsupported`, `/loading-icon`,
`/utils`, `/primitives/*`, `/tokens.css`, and `/styles.css`.
Declarations are owned here; apps need no ambient shims or aliases into this
source tree.

`/drawing` is a separate lazy entry point for the Excalidraw editor, for temporary
sketches, with no platform discovery or persistent storage. Desktop owns its temporary Drawing tabs,
in-memory scene retention and prompt delivery; web's viewer remains unchanged.
Read [drawing](docs/drawing.md) before extending this editor or reusing it for
viewer annotations.

The required host contract, typed prompt bundles, delivery receipts and named
renderer slots are documented in [viewer host](docs/viewer-host.md). Clipboard
and page reload implementations now live in the apps. Shared UI performs no
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
watchers. CAD's state entry point supplies existing schema validation for safe
legacy restoration. Capabilities determine menus: a read-only web source cannot
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
helper tests, React/editor tests and real Chromium
integration tests for renderer preparation, saves/conflicts, root changes,
multiple instances, cancellation and disposal. App integration and packaged
runtime checks remain with their hosts. See [renderer contracts](docs/renderers.md)
for the non-CAD behavior that must remain unchanged.

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

A file's controls are nav-row panels, never tabs inside a panel. From left to
right a file has its own panel (a STEP's `Part` or `Assembly`, a robot's `Robot`),
then `Display`, then the file tree; a mesh has no panel of its own, and a DXF has
only the file tree. A file's own panel stacks sections under headings that never
collapse (`FilePanelSections`): a STEP's Features, Position when it declares
kinematics, and Issues when it has any; a robot description's Position and Links
(SDF adds its SDF metadata). Links is the description's link tree, with the Model
tree's rows, filter and Reference pane; see [robot links](docs/cad-renderer.md#robot-links).
Which panel a file opens with is the host's to apply
(`ViewerHost.navigation.openFile(path, { target, panel })`): a file picked in the
tree asks for the tree, so the tree stays up while a person walks it; any other
open gets the file's own panel, or nothing when it has none. Display is never open
by default, and no panel is saved per file. Switching to Display keeps the file's
panel mounted behind it, preserving the tree's disclosure and scroll.
The Display panel uses a compact properties layout with 28px headers/controls, no extra
header-to-content padding, 4px row gaps and 8px section bottoms. Mode contains equal-width Mode and
Projection dropdowns; Explode is a separate section. Surfaces stays expanded,
and perspective uses the standard lens without a separate Camera section. Optional settings sections are
feature gates: title/plus click enables, only the trailing minus disables, and
gray/collapsed means neutral/off. Reopening resets values to defaults, including
Clip offsets/Flip and Explode's amount (50%). Explode stays open when its slider
returns to 0%; only the minus collapses it. The fixed section order is Mode,
Surfaces, Explode, Clip, Edges, Grid, Axes, Lighting, Background, Floor, and no
preset reorders it. Grid and Axes are separate, with matching default colors.
Floor and Background have no redundant enable/transparency checkboxes; opacity
lives in color pickers with checkerboard previews.
Hover only highlights controls; it never writes settings. One per-file settings store serves controls, agent
commands and persistence, and retains unchanged renderer inputs across edits;
see [View state and updates](docs/render-mode.md#state-and-updates).
Expensive settings use [staged viewport updates](docs/view-updates.md): controls
remain authoritative, preparation is replaceable, and captures await presentation.

Solid, Render, X-ray, Hidden line and Wireframe are presets over one grouped
settings schema. Every preset exposes the same groups. Render defaults to
perspective; others to orthographic. Changed view values show Custom; Reset
restores the base preset. Clip/Explode are tools outside presets and Custom,
preserved along with camera viewpoint/zoom, motion and selection. The viewer
inherits host light/dark appearance and defaults to Preview lighting quality;
snapshots default to Light and Final. Explicit grouped values override these
context defaults. Retired saved states migrate on restore; new commands use the
closed grouped schema. See [View presets](docs/render-mode.md).

Authored material color, finish and opacity are read-only in every style; the
Model reference section shows their properties. There is no Materials editor or
persisted material override. See [View styles](docs/render-mode.md) and
[progressive detail](docs/lod.md).

The breadcrumb names the file and carries no status. Opening and updating show
in the viewport's own loading state, and an error as a card over the viewport;
a failed update the model survives can be dismissed, leaving the previous
version to inspect. Try again reloads only the selected renderer.
