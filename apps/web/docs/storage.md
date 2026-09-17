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

Do not put dense viewer state, panel state, drawing state, or per-file controls
in the URL.

## localStorage

Use `localStorage` sparingly. It is durable across tabs, browser restarts, and
unrelated CAD Viewer sessions, so it should only hold global preferences.

Current intended use:

- `cad-viewer:color-scheme`: the app's System/Light/Dark appearance preference,
  used when its cross-port appearance cookie is unavailable.
- `cad-viewer:file-sheet-tab-layout:v6`: the Inspector's per-kind tab order,
  pane assignment, split state and split ratio. The active tab remains per-file
  state.

The host adapter is [cadPreferences.ts](../src/persistence/cadPreferences.ts).
It injects layout and motion preferences into the shared renderer.
Inspect and Render own their scene bases. The retired `cad-viewer:theme` key is
left untouched and is neither read nor written; saved custom themes cannot
override either mode.

Avoid adding file-specific state to `localStorage`. If the value depends on the
selected file, the active root directory, a generated asset hash, or a tab
interaction, it belongs in per-file session state instead.

## Legacy directory sessionStorage

The host reads the existing directory record through
[persistence.js](../src/client/workbench/persistence.js). Its panel and tree
fields seed root-scoped FileViewer state when no newer record exists. Legacy
directory theme overrides are ignored.

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
  tree and the Inspector both take it.

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
- `stepModule`: kinematic parameter values.
- `animation`: embedded clip, playback and elapsed-time state.
- `render`: independent photographic mode, settings, camera and quality.
- `materials`: per-file material overlays, invalidated by authored revisions.
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
records without deleting them or replacing newer renderer state. A saved
`cad-theme` panel restores the renderer's default Inspector; explicit closed,
tree and Inspector choices remain unchanged. Inspector-layout keys retain their
existing meaning. The retired reference tooltip and its reset query are no longer
consumed; their old storage record is ignored.
Writes merge changed chrome fields and renderer keys into the latest record,
so independent views cannot overwrite another document's state with a stale snapshot.
The URL remains the selected-file authority;
opening the root without a file does not silently select a different artifact.

CAD state normalizers are supplied by `@hardcore/ui/renderers/cad/state`.
Storage access is explicit in the host; constructing or importing a renderer
never chooses a browser storage backend.

Render tab rearrangements last for the current Render visit and never change the
global Inspect layout. Material undo and Materials-panel selection remain with
the active file when its panel is switched. Appearance uses a host cookie across
viewer ports, with `cad-viewer:color-scheme` as its localStorage fallback; neither
changes the per-file Render recipe. Legacy CAD theme preferences are ignored.

Pose transition animation and speed use the existing
`cad-viewer:pose-transition:v1` preference. The web adapter reads, writes and
synchronizes that key through `CadPreferences`; the shared renderer discovers no
browser storage.
