# @hardcore/ui

The shared React interface for Hardcore. `FileViewer` is the complete file tab:
its breadcrumb row, menus, content, file tree, one panel column, loading and
error states, and common edit/save/reload lifecycle. Both `apps/web` and
`apps/desktop` consume this component through the package's compiled exports.
The desktop's project/session/window layout remains application code.

This extraction is a **pure refactor**. Preserve the existing UI, UX and
functionality of docs, web and desktop: styling, labels, defaults, shortcuts,
file actions, editing and conflict behavior, CAD interactions, persistence,
and narrow layouts. New features or visual changes require a separate change.
The viewer's shared controls keep their original appearance. Desktop's
surrounding app controls remain local where their existing appearance differs.

## Ownership and dependencies

UI may import `@hardcore/core` and browser-safe React dependencies. It must not
import an application, Electron, Node services, desktop IPC schemas, app stores,
or `window.hardcore`. Hosts inject file access, capabilities, navigation,
persistence, appearance and CAD services. Importing a package starts no polling,
workers or host storage writes and changes neither document title nor theme.

React, ReactDOM, Three.js and Lucide are host-supplied peers. React 18 and 19
are supported: web retains React 18.3.1, while desktop retains 19.2.8. Each
host must resolve one copy of each peer in its browser bundle. Web uses Vite
deduplication so shared imports use its original React and Lucide versions;
these peers are not bundled into UI.

```text
src/
  file-viewer/       FileViewer, typed source/renderer contracts, lifecycle hooks
    navigation/     breadcrumbs, file tree, entry menus and panel frame
  renderers/
    cad/            CAD viewport, inspector, themes, tools and state schemas
    markdown/       preview/editor and lossless Markdown bridge
    code/           Monaco editor and worker setup
    image/          image view and zoom
    pdf/            sandboxed PDF view
    unsupported/    existing OS-open fallback
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

```tsx
import { FileViewer } from '@hardcore/ui/file-viewer';
import { createCadRenderer } from '@hardcore/ui/renderers/cad';
import '@hardcore/ui/tokens.css';
import '@hardcore/ui/styles.css';

const renderers = [createCadRenderer({ client, preferences })];
// The host supplies source, selectedFile, state and the corresponding callbacks.
<FileViewer file={selectedFile} source={source} renderers={renderers}
  state={state} onStateChange={setState} onOpenFile={openFile}
  appearance={{ colorScheme: 'light' }} />;
```

Public entry points include `/file-viewer`, `/navigation`, `/renderers/cad`,
`/renderers/cad/state`, `/renderers/cad/presentation`, `/renderers/cad/empty`,
`/renderers/markdown`, `/renderers/code`, `/renderers/code/editor`,
`/renderers/image`, `/renderers/pdf`, `/renderers/unsupported`, `/loading-icon`,
`/clipboard`, `/utils`, `/primitives/*`, `/tokens.css`, and `/styles.css`.
Declarations are owned here; apps need no ambient shims or aliases into this
source tree.

## Lifetimes and state

A source has a stable root identity independent of a server's ephemeral port.
File state is scoped by root, path and renderer. Changing source or file aborts
pending preparation, releases prepared assets, and discards stale async results.
A renderer owns its viewport and resources; the host owns its CAD client. Last
render-session disposal releases shared worker leases. One viewer cannot replace
another viewer's cache provider or camera state.

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
The UI suite includes Node helper tests, React/editor tests and real Chromium
integration tests for renderer preparation, saves/conflicts, root changes,
multiple instances, cancellation and disposal. App integration and packaged
runtime checks remain with their hosts. See [renderer contracts](docs/renderers.md)
for the non-CAD behavior that must remain unchanged.
