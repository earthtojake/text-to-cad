# Browser Storage

CAD Viewer has four browser persistence tiers. Choose the smallest tier that
matches the lifetime and sharing behavior the user expects.

This doc covers browser state only. Catalogs, CAD assets, hidden STEP
GLB/topology artifacts, and hosted Blob uploads are backend concerns; use
[backend.md](./backend.md) for that interface.

## URL Query Params

Use query params only for shareable state that should survive copying a URL:

- `file`: active catalog entry, always relative to the directory in the URL path.
  The path itself is the directory the Viewer scans — there is no `dir` param on
  the page URL (`dir` survives only inside `/__cad/asset` request URLs).
- `moveit2Ws`: explicit MoveIt2 websocket override for local or hosted sessions.
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
  Presets are read-only and are never stored — only named. The key is absent
  while the theme is `system` with no custom slot.
- `cad-viewer:tutorial-tips:v1`: ids of the one-shot tutorial tips the user has
  dismissed. A tip is recorded only when its close button is pressed — clicking
  away, Escape, and reloads all leave it unrecorded, so it comes back on the next
  chance until it is actually acknowledged. Cleared by `?resetTips=1`.

Avoid adding file-specific state to `localStorage`. If the value depends on the
selected file, the active root directory, a generated asset hash, or a tab
interaction, it belongs in per-file session state instead.

## Directory sessionStorage

Use directory-level `sessionStorage` for temporary app-wide UI state that should
survive reloads in the same browser tab, should not become a durable global
preference, and should not vary by selected file. Use
`src/client/workbench/persistence.js` rather than creating one-off storage keys.

Current keys:

```text
cad-viewer:directory-session:v1
cad-viewer:active-dir:v1
```

Current `cad-viewer:directory-session:v1` fields:

- `fileViewerOpen`: app-wide file viewer open/closed state.
- `fileViewerExpandedDirectoryIds`: app-wide open folder ids for the file
  viewer tree. When absent, the first selected file on page load seeds the
  initial expanded folder tree; an empty array means all folders are closed.
- `fileViewerWidthPx`: app-wide custom file viewer width, stored only when it
  differs from the default.
- `fileSheetOpen`: app-wide file sheet open/closed state.
- `fileSheetWidthPx`: app-wide custom file sheet width, stored only when it
  differs from the default.
- `theme`: a directory-level theme override for the current tab, in the same
  `{themeId, custom}` shape as the global key. The global theme itself belongs
  to `localStorage`.

`cad-viewer:active-dir:v1` stores the tab's preferred directory after a `?dir=`
URL is loaded or a directory is selected.

Do not put selected-file state, model controls, drawing state, or
generated-asset decisions in directory session state. Those belong in per-file
session state.

## Per-File sessionStorage

Prefer per-file `sessionStorage` for viewer state that should survive reloads in
the same browser tab without becoming a durable global preference. Use
`src/client/workbench/fileSessionState.js` rather than creating one-off storage
keys.

Per-file state is namespaced by the active root directory and keyed by file:

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

When adding another large-file control, reuse the `largeFile` slice instead of
adding a separate session storage key.
