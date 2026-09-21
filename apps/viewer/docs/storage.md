# Browser Storage

CAD Viewer has four browser persistence tiers. Choose the smallest tier that
matches the lifetime and sharing behavior the user expects.

This doc covers browser state only. Catalogs, CAD assets, and hidden STEP
GLB/topology artifacts are backend concerns; use [backend.md](./backend.md) for
that interface.

## URL Query Params

Use query params only for shareable state that should survive copying a URL:

- `file`: the active catalog entry, relative to the served root. The page is
  always the bare origin: an instance serves ONE directory, fixed when it was
  launched, so no URL anywhere names a directory — there is no `dir` param on
  the page URL and none on a `/__cad` request either.
- `resetTips`: debug-only. Clears the record of seen one-shot tutorial tips so
  they fire again. It applies once during bootstrap and is then stripped from
  the address bar, so it is a reset action rather than a persistent mode.

Do not put dense viewer state, panel state, drawing state, or per-file controls
in the URL.

## localStorage

Use `localStorage` sparingly. It is durable across tabs, browser restarts, and
unrelated CAD Viewer sessions, so it should only hold global preferences.

Current intended use:

- `cad-viewer:color-scheme`: a same-origin mirror of the global System / Light /
  Dark app appearance. The host-scoped `cad-viewer-appearance` cookie is the
  canonical cross-port value; the mirror supports storage events and acts as a
  fallback when cookies are blocked.
- `cad-viewer:tutorial-tips:v1`: ids of the one-shot tutorial tips the user has
  dismissed. A tip is recorded only when its close button is pressed — clicking
  away, Escape, and reloads all leave it unrecorded, so it comes back on the next
  chance until it is actually acknowledged. Cleared by `?resetTips=1`.
- `cad-viewer:file-sheet-tab-layout:v6`: the draggable per-kind CAD tab order,
  split assignment, and split ratio. Render starts with a separate single-row
  Studio-first arrangement on every entry; its temporary drag/split changes are
  never written to this store.

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
cad-viewer:file-session:v3:<namespace>:<fileKey>
cad-viewer:file-session:index:v3:<namespace>
```

Per-file session state is intentionally tab-local. Do not sync these keys from
`storage` events; two tabs viewing the same file must be free to keep different
camera, display, tool, and sheet settings.

Existing slice intent:

The slice set is closed — it is the frozen `FILE_SESSION_SLICE_SCHEMA` in
`fileSessionState.js`, and a slice with a `signatureKey` is dropped when the
artifact it was read from changes:

- `tab`: file sheet section expansion, reference selection, part visibility,
  camera, tools, and drawing history.
- `display`: normal CAD display controls for the model.
- `render`: Render mode, its active Studio/Animation tab, sparse photographic
  configuration, and separate CAD/Render camera state. Studio defaults follow
  global app appearance; the session does not store a studio choice. The slice
  accepts exposure, softbox, backdrop, lens, and Preview/Final quality values.
  Display stays in the CAD slice and never enters the Render payload.
- `stepModule`: STEP pose enablement and DOF values.
- `animation`: the selected clip, whether it drives the model, and its clock.
  It shares the `stepModule` signature because both are read out of the one
  sidecar, so a rebuilt sidecar invalidates both.
- `materials`: the tab-local material definitions and their part assignments,
  invalidated by an authored revision.
- `urdf`: joint values and motion-planning controls.
- `largeFile`: large-file decisions such as selectable topology opt-in.

When adding another large-file control, reuse the `largeFile` slice instead of
adding a separate session storage key.
