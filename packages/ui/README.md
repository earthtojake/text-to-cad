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

React, ReactDOM, Three.js and Lucide are host-supplied peers. React 18 and 19
are supported: web and desktop use React 19.3.0. Each
host must resolve one copy of each peer in its browser bundle. Web uses Vite
deduplication so shared imports use its host React and Lucide versions;
these peers are not bundled into UI.

```text
src/
  host/              explicit host ports, prompt actions and React binding
  file-viewer/       FileViewer, typed source/renderer contracts, lifecycle hooks
    navigation/     breadcrumbs, file tree, entry menus and panel frame
  renderers/
    cad/            CAD viewport, inspector, scene controls and state schemas
    markdown/       preview/editor and lossless Markdown bridge
    code/           Monaco editor and worker setup
    image/          image view and zoom
    pdf/            sandboxed PDF view
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
import { createCadRenderer } from '@hardcore/ui/renderers/cad';
import '@hardcore/ui/tokens.css';
import '@hardcore/ui/styles.css';

const renderers = [createCadRenderer({ client, preferences })];
// The host supplies storage, actions, navigation and environmental ports.
<FileViewer file={selectedFile} host={host} renderers={renderers}
  state={state} onStateChange={setState} />;
```

Public entry points include `/host`, `/file-viewer`, `/navigation`, `/renderers/cad`,
`/renderers/cad/state`, `/renderers/cad/presentation`, `/renderers/cad/empty`,
`/renderers/markdown`, `/renderers/code`, `/renderers/code/editor`,
`/renderers/image`, `/renderers/pdf`, `/renderers/unsupported`, `/loading-icon`,
`/utils`, `/primitives/*`, `/tokens.css`, and `/styles.css`.
Declarations are owned here; apps need no ambient shims or aliases into this
source tree.

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
The Model inspector can reuse those accepted component identities for completed
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

The shared CAD renderer consumes the artifact, its schema-9 `.step.json`
sidecar and immutable store views. Embedded animation, authored appearance and
kinematics travel in the sidecar; an adjacent `.step.js` is a retired input.
The scene uses progressive component loading and demand-driven exact surfaces.
The geometry-based Model/Features inspector and contextual measurements remain
in Inspect, with client-bound surface requests made only while its panel is open.

Inspect uses the fixed light or dark workbench basis selected by app appearance;
legacy CAD theme preferences are not consumed. The floating toolbar switches to
Render, whose studio, materials, camera and quality have independent per-file
state. Render does not receive inspection tints or measurements. Materials
picking is enabled only while its visible panel is active. See
[Render modes](docs/render-mode.md) and [progressive detail](docs/lod.md).

A renderer publishes `FileActivity` with a loading flag, label, title, optional
tone and optional activation callback. FileViewer shows a generic filename
indicator unless the host supplies `presentation.activity`. CAD status activation
opens the shared diagnostic; Try again reloads only the selected renderer.
