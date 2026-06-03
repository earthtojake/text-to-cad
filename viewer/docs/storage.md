# Browser Storage

CAD Viewer has four browser persistence tiers. Choose the smallest tier that
matches the lifetime and sharing behavior the user expects.

This doc covers browser state only. Catalogs, CAD assets, hidden STEP
GLB/topology artifacts, and hosted Blob uploads are backend concerns; use
[backend.md](./backend.md) for that interface.

## URL Query Params

Use query params only for shareable state that should survive copying a URL:

- `file`: active catalog entry, always relative to the active `dir` directory.
- `dir`: local filesystem directory to scan. It may be absolute or relative to
  the directory where the Viewer server was started. When omitted, the Viewer
  uses the active directory remembered for the tab, or the directory where the
  server was started when that is the only active directory.
- `refs`: copied CAD references and selection targets.
- `moveit2Ws`: explicit MoveIt2 websocket override for local or hosted sessions.

Do not put dense viewer state, panel state, drawing state, or per-file controls
in the URL.

## localStorage

Use `localStorage` sparingly. It is durable across tabs, browser restarts, and
unrelated CAD Viewer sessions, so it should only hold global preferences.

Current intended use:

- `cad-viewer:theme`: global saved-theme library, active theme id, and saved
  appearance settings.

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
- `theme`: app-wide unsaved theme settings for the current tab. Saved theme
  presets and the active saved preset id still belong to `localStorage`.

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
