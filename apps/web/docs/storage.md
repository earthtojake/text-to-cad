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
the whole record, handed to `createTabStore` (`@text-to-cad/ui/tab-store`), which
owns the record's shape, its version and its normalization
([tabRecord.ts](../../../packages/ui/src/tab-store/tabRecord.ts)). `main.tsx`
builds the one store; `App.tsx` hands it to `CadViewer`, which reads `FileViewer`'s state out
of it (`useTabViewerState`) and hands its `settings` to every renderer as their
preferences. Renderers never see storage: they hand the shell their view and read
it back on mount.

The record is `{ version, settings, files }`:

| Kept | Where | What |
| --- | --- | --- |
| Tab settings | `settings` | `toolStack` (the resizable panels' sizes, the folded panels and the closed tree, `kit/tools/toolStackLayout.js`), `appearance` (System, Light or Dark; System until the person picks), `library` (the home's models as a grid or a list), `explorer` (the folder the name menu's Files was last in: where a model's Files starts). |
| File views | `files[[absolute file path, renderer id]]` | The file's view ([fileView.js](../../../packages/ui/src/renderers/kit/shell/fileView.js)): `camera` (the renderer's own — a scene's pose, lens and projection, restored in place of the open-time fit; a drawing's plane transform), `display` (the Display settings, Clip and Explode included), `preview` (Preview's Render settings: lighting, background, floor, part colours), `playback` (the playback settings: Orbit's speed, Autoplay, and — once chosen in the Animation section's Playback settings — the Speed and Loop the routine plays with, unset meaning the routine's own; kept between leaving and re-entering Preview; defaults Orbit at 1×, Autoplay off; whether Preview orbits is not kept) and `renderer`, the renderer's own slices, each behind the signature it was written against: a STEP's expanded nodes, hidden parts, isolated assemblies, pose and large-file opt-in; a robot's joint values. A slice whose signature no longer matches the file on screen is dropped; the camera, the display and the playback are always kept. Only the file on screen has a view: leaving it — for another file, or for the home — drops its view (`CadViewer`, after the view's last write as it unmounts), so opening it again starts at the defaults, while a reload of the tab, which shows the same file, brings its view back. |

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

## localStorage

Nothing goes in localStorage: a value that depends on a file, a tab or a person's
choice belongs in the tab record.
