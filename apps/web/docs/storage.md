# Browser Storage

The web host owns browser persistence; shared UI receives state and callbacks.
There is one rule: **every tab has its own state, thrown out when the tab is
closed and kept when it is reloaded.** Nothing outlives the tab, nothing is global
and nothing crosses tabs: a new tab, a duplicated one included, starts from the
defaults. Within the tab, a model's state lasts only while it is the model on
screen: leaving it drops it.

This doc covers browser state only. Catalogs and CAD assets are backend concerns;
use [backend.md](./backend.md) for that interface.

## The URL

The URL's path names the document, `/<id>` (`src/client/workbench/fileParam.js`); the bare
path is the home. No query parameter names a file: a developer's default file
(`VIEWER_DEFAULT_FILE`, an absolute path set at build time) is resolved to its id through
the catalog, and `writeDocumentId` keeps whatever query the page carries.

Do not put dense viewer state, panel state, drawing state, or per-file controls
in the URL.

## The tab record

Everything the viewer keeps is one record in `sessionStorage`, under
`text-to-cad:tab:v1`, and one more entry, `cadgen:exporting:<path>`, for the exports still
under way (`src/host/downloads.ts`; [the app README](../README.md#export-and-job-status)) —
sessionStorage is the browser's own tab: it survives a reload and goes with the tab. The host's part is the adapter,
[tabRecord.ts](../src/persistence/tabRecord.ts): a synchronous read and write of
the whole record, handed to `createTabStore` (`@cad/ui/tab-store`), which
owns the record's shape, its version and its normalization
([tabRecord.ts](../../../packages/ui/src/tab-store/tabRecord.ts)). `main.tsx`
builds the one store; `App.tsx` hands it to `CadViewer`, which reads `FileViewer`'s state out
of it (`useTabViewerState`) and hands its `settings` to every renderer as their
preferences. Renderers never see storage: they hand the shell their view and read
it back on mount.

The record is `{ version, settings, files }`:

| Kept | Where | What |
| --- | --- | --- |
| Tab settings | `settings` | `toolStack` (the tool stack's resizable panels' sizes and its folded panels, `kit/tools/toolStackLayout.js`; the view's panel is the file's, below), `appearance` (System, Light or Dark; System until the person picks), `library` (the home's models as a grid or a list), `explorer` (the folder the name menu's Files was last in: where a model's Files starts). |
| File views | `files[[absolute file path, renderer id]]` | The file's view ([fileView.js](../../../packages/ui/src/renderers/kit/shell/fileView.js)): `camera` (the renderer's own — a scene's pose, lens and projection, restored in place of the open-time fit; a drawing's plane transform), `display` (the Display settings, Clip and Explode included), `preview` (Preview's Render settings: lighting, background, floor, part colours), `playback` (the playback settings: Orbit's speed, Autoplay, and — once chosen in the playbar's Playback settings — the Speed and Loop the routine plays with, unset meaning the routine's own; kept between leaving and re-entering Preview; defaults Orbit at 1×, Autoplay off; whether Preview orbits is not kept) and `renderer`, the renderer's own slices, each behind the signature it was written against: an engine document's (an `.xbf`'s, a STEP's) expanded rows, hidden parts and isolated assemblies, and its pose; a robot's joint values and hidden components; a board's Display, what it isolates, and whether it is shown in 2D or 3D with its 3D camera, its projection and whether its parts' 3D models show (`board3d`, never the URL). Beside them `panel`, the view's panel ([filePanel.js](../../../packages/ui/src/file-viewer/filePanel.js)), whatever the renderer: open or closed once the person has chosen (unset, it opens in a view 1024px wide or more), its width, its tab and the Selected pane's height, each unset until changed, written by the panel itself and kept in the record by the file viewer whatever the renderer writes. A slice whose signature no longer matches the file on screen is dropped; the camera, the display and the playback are always kept. Only the file on screen has a view: leaving it — for another file, or for the home — drops its view (`CadViewer`, after the view's last write as it unmounts), so opening it again starts at the defaults, while a reload of the tab, which shows the same file, brings its view back. |

| Not kept | Every open starts it afresh |
| --- | --- |
| A file the tab left: its whole view | The defaults, when it is opened again |
| The tool in hand | The renderer's default tool (Select) |
| The selection (a STEP's tree and topology, a robot's links), measurements, the drawing tools' ink | Empty |
| Preview, its camera and its Orbit | Off, opening still; its settings are the file's, above |
| The routine, its time and whether it is playing | At rest |
| Quick Edit's note | Empty, its box closed |
| The Select mode filter, hover, menus, popovers | The page's own |

Appearance applies before the first paint: the inline script in
[index.html](../index.html) reads the same key and applies `settings.appearance`
to the document, so a tab left in Dark never paints light and flips. A new tab
has no record and follows the OS.

Writes are whole and synchronous: the shell writes a file's view a moment after
each change and once more on unmount (the page's `pagehide` unmounts the app), the
store writes the record through at once, so what the tab last saw is what a
reload restores. When the viewer leaves a file for another, the file's last write
lands first and `CadViewer` then drops its view (`files.retain`); a view that has
gone writes nothing more. Storage access is explicit in the host; constructing or
importing a renderer never chooses a browser storage backend.

The record's `settings.toolStack` once kept the view's panel for every file alike
(`collapsed.flat`, `panels.flat.width`, `panels.flatDetail.height`, `tabs` by the kind of
file). A tab that still carries it gives it, once, as the starting value of the first file
with no panel of its own, which keeps it from then on; the old fields are then dropped and
never written again.

## localStorage

Nothing goes in localStorage: a value that depends on a file, a tab or a person's
choice belongs in the tab record.

## The library's pictures

The home's card pictures are not browser storage: the page draws one when a file's view settles
(`useModelThumbnail`, once per revision) and hands it to the server, which keeps it in the state
folder (`cad_server/viewer/recents.py`). They are bounded however often a file is edited: an entry
keeps at most one picture, and a board one per theme, each replaced in place by the next; only the
200 entries the home lists first keep theirs, within 64 MiB in all, least recently used out first;
an entry removed or deleted takes its pictures with it. The page asks for a picture by its name
(`?v=`), so a new picture is never hidden by an older one in a cache.
