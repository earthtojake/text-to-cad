# Browser Storage

The web host owns browser persistence; shared UI receives state and callbacks.
This pure refactor retains existing preference values and session lifetimes.
Choose the smallest persistence tier that matches the lifetime and sharing
behavior the user expects. New view-state writes use the root-scoped record
below; legacy records remain readable for migration.

This doc covers browser state only. Catalogs, CAD assets, and hidden STEP
GLB/topology artifacts are backend concerns; use [backend.md](./backend.md) for
that interface.

## URL Query Params

Use query params only for shareable state that should survive copying a URL:

- `file`: active catalog entry, relative to the root served by this instance.
  The page is the bare origin with `?file=`; there is no `dir` page parameter.
- `resetTips`: debug-only. Clears the record of seen one-shot tutorial tips so
  they fire again. It applies once during bootstrap and is then stripped from
  the address bar, so it is a reset action rather than a persistent mode.

Do not put dense viewer state, panel state, drawing state, or per-file controls
in the URL.

## localStorage

Use `localStorage` sparingly. It is durable across tabs, browser restarts, and
unrelated CAD Viewer sessions, so it should only hold global preferences.

Current intended use:

- `cad-viewer:theme`: the active theme id (`system`, a built-in preset id, or
  `custom`) plus the single custom settings blob, if the user has edited one.
  Presets are read-only and are never stored — only named. An absent key
  resolves to `system` with no custom slot.
- `cad-viewer:tutorial-tips:v1`: ids of the one-shot tutorial tips the user has
  dismissed. A tip is recorded only when its close button is pressed — clicking
  away, Escape, and reloads all leave it unrecorded, so it comes back on the next
  chance until it is actually acknowledged. Cleared by `?resetTips=1`.
- `cad-viewer:file-sheet-tab-layout:v5`: the Inspector's per-kind tab order,
  pane assignment, split state and split ratio. The active tab remains per-file
  state.

The host adapter is [cadPreferences.ts](../src/persistence/cadPreferences.ts).
It injects preferences into the shared renderer and retains the existing theme
storage-event synchronization.

Avoid adding file-specific state to `localStorage`. If the value depends on the
selected file, the active root directory, a generated asset hash, or a tab
interaction, it belongs in per-file session state instead.

## Legacy directory sessionStorage

The host reads the existing directory record through
[persistence.js](../src/client/workbench/persistence.js). Its panel and tree
fields seed root-scoped FileViewer state when no newer record exists. The host
continues writing the tab's theme override here through `cadPreferences.ts`.

Retained key:

```text
cad-viewer:directory-session:v1
```

Recognized `cad-viewer:directory-session:v1` fields:

- `fileViewerOpen`: whether the **file tree** is the open panel. Nullable:
  absent is "nobody has said", which resolves to the shared panel list's own
  default (`@hardcore/ui/navigation`'s `panels.js` — the tree, unless the open file's
  Inspector claims it). A stored `false` is a person who closed the panel and
  must come back to it closed, which a plain boolean could not tell apart from
  a first visit.
- `fileViewerExpandedDirectoryIds`: the file tree's open folder ids. Absent is
  a tree that has never been touched; an empty array means all folders are
  closed. The tree reveals the open file's own ancestors either way.
- `fileSheetOpen`: whether the **Inspector** is the open panel, the same way.
- `fileSheetWidthPx`: the panel column's custom width, stored only when it
  differs from the default. There is one column and so one width — the file
  tree, the theme editor and the Inspector all take it.
- `theme`: a directory-level theme override for the current tab, in the same
  `{themeId, custom}` shape as the global key. The global theme itself belongs
  to `localStorage`.

Do not put selected-file state, model controls, drawing state, or
generated-asset decisions in directory session state. Those belong in per-file
session state.

## Legacy per-file sessionStorage

Per-file state survives reloads in the same browser tab without becoming a
durable global preference. The host's
[fileViewer.ts](../src/persistence/fileViewer.ts) restores existing records with
the validated reader exported by `@hardcore/ui/renderers/cad/state`.

Legacy records use a namespace and file key; the former standalone web host
used the default namespace. They remain readable without being rewritten or
deleted:

```text
cad-viewer:file-session:v1:<namespace>:<fileKey>
cad-viewer:file-session:index:v1:<namespace>
```

Per-file session state is intentionally tab-local. Do not sync these keys from
`storage` events; two tabs viewing the same file must be free to keep different
camera, display, tool, and sheet settings.

Existing slice intent:

- `tab`: file sheet section expansion, reference selection, part visibility,
  camera, tools, and drawing history.
- `dxf`: DXF preview thickness and bend settings.
- `stepModule`: STEP module enablement, parameter values, and animation state.
- `urdf`: joint values and motion-planning controls.
- `largeFile`: large-file decisions such as selectable topology opt-in.

Current writes store these slices in the CAD renderer's per-file state inside
the root-scoped record. Reuse the existing slices when adding a control instead
of adding a separate storage key.

## Root-scoped FileViewer state

The host's [fileViewer.ts](../src/persistence/fileViewer.ts) reads and writes
`hardcore:file-viewer:v1:<encoded rootId>` in `sessionStorage`. It holds the shared
panel/width, expanded directories and renderer state keyed by file and renderer.
`rootId` is the server's normalized filesystem-root identity, independent of
its port. The host restores legacy directory and validated per-file session
records without deleting them or replacing newer renderer state. Global theme,
tutorial-tip and Inspector-layout keys keep their existing names and meanings.
The URL remains the selected-file authority;
opening the root without a file does not silently select a different artifact.

CAD state normalizers are supplied by `@hardcore/ui/renderers/cad/state`.
Storage access is explicit in the host; constructing or importing a renderer
never chooses a browser storage backend.
