# Browser Storage

The web host owns browser persistence; shared UI receives state and callbacks.
Choose the smallest persistence tier that matches the lifetime and sharing
behavior the user expects. View state is the root-scoped record below; the
legacy directory record is read only as a fallback for the panel width and the
tree's expanded folders.

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
- `cad-viewer:orbit:v1`: the fullscreen orbit speed (below).

The host adapter is [cadPreferences.ts](../src/persistence/cadPreferences.ts).
It injects the orbit preference into the shared renderer.
Inspect and Render own their scene bases. The retired `cad-viewer:theme` key is
left untouched and is neither read nor written; saved custom themes cannot
override either mode.

Avoid adding file-specific state to `localStorage`. If the value depends on the
selected file, the active root directory, a generated asset hash, or a tab
interaction, it belongs in per-file state instead.

## Root-scoped FileViewer state

The host's [fileViewer.ts](../src/persistence/fileViewer.ts) reads and writes
`hardcore:file-viewer:v1:<encoded rootId>` in `sessionStorage`. It holds the
panel column's width, the tree's expanded directories and renderer state keyed
by file and renderer. It never holds the open panel: a page load is a file
opened directly, so it opens with the file's own default panel (`panel: null`),
whatever the last page had open. `rootId` is the server's normalized
filesystem-root identity, independent of its port. The retired reference
tooltip and its reset query are no longer consumed; their old storage record is
ignored.
Writes merge changed chrome fields and renderer keys into the latest record,
so independent views cannot overwrite another document's state with a stale snapshot.
The URL remains the selected-file authority;
opening the root without a file does not silently select a different artifact.

Per-file state is intentionally tab-local. Do not sync these keys from
`storage` events; two tabs viewing the same file must be free to keep different
display and tool settings. Camera position, target and zoom live only in the mounted viewer; every reload frames the model fresh. Older saved cameras are ignored. A STEP, GLB, mesh or robot entry is the
shell's per-file record, `{ version, camera: null, display, tool, renderer }`
([shellState.js](../../../packages/ui/src/renderers/kit/shell/shellState.js));
a DXF entry is only the view a person moved it to. A STEP's own `renderer` slot
keeps its tree selection, expansion and hidden parts, its pose, its animation
and its large-file opt-in. Material appearance
comes from the model and its sidecar, never session storage. Reuse the record's
slices when adding a control instead of adding a separate storage key.

The panel column's width defaults are supplied by
`@hardcore/ui/renderers/step/state`. Storage access is explicit in the host;
constructing or importing a renderer never chooses a browser storage backend.

Appearance uses a host cookie across viewer ports, with `cad-viewer:color-scheme`
as its localStorage fallback; neither changes the per-file Render recipe. Legacy
CAD theme preferences are ignored.

Fullscreen orbit speed uses `cad-viewer:orbit:v1`. The web adapter reads, writes
and synchronizes that key through `CadPreferences`; the shared renderer discovers
no browser storage. It is global across files and synchronized across windows.
A stored `cad-viewer:pose-transition:v1` from an older viewer is ignored: pose
writes no longer ease.
Fullscreen camera changes are transient and never enter file-session snapshots.
