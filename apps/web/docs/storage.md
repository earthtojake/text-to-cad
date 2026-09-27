# Browser Storage

The web host owns browser persistence; shared UI receives state and callbacks.
There is one rule: **every tab has its own state, thrown out when the tab is
closed and kept when it is reloaded.** Nothing outlives the tab, nothing is global
and nothing crosses tabs: a new tab, a duplicated one included, starts from the
defaults. The one thing outside the rule is a network cache, listed at the end.

This doc covers browser state only. Catalogs, CAD assets, and hidden STEP
GLB/topology artifacts are backend concerns; use [backend.md](./backend.md) for
that interface.

## URL Query Params

Use query params only for shareable state that should survive copying a URL:

- `file`: active catalog entry, relative to the root served by this instance.
  The page is the bare origin with `?file=`; there is no `dir` page parameter.

Do not put dense viewer state, panel state, drawing state, or per-file controls
in the URL.

## The tab record

Everything the viewer keeps is one record in `sessionStorage`, under
`hardcore:tab:v1` — sessionStorage is the browser's own tab: it survives a reload
and goes with the tab. The host's part is the adapter,
[tabRecord.ts](../src/persistence/tabRecord.ts): a synchronous read and write of
the whole record, handed to `createTabStore` (`@hardcore/ui/tab-store`), which
owns the record's shape, its version and its normalization
([tabRecord.ts](../../../packages/ui/src/tab-store/tabRecord.ts)). `main.tsx`
builds the one store; `App.tsx` reads `FileViewer`'s state out of it
(`useTabViewerState`) and hands its `settings` to every renderer as their
preferences. Renderers never see storage: they hand the shell their view and read
it back on mount.

The record is `{ version, settings, files }`:

| Kept | Where | What |
| --- | --- | --- |
| Tab settings | `settings` | `fileTree` (the panel column's width, and the folders open under each root), `toolStack` (the resizable panels' sizes and the folded panels, `kit/tools/toolStackLayout.js`), `appearance` (System, Light or Dark; System until the person picks). |
| File views | `files[[root id, file path, renderer id]]` | The file's view ([fileView.js](../../../packages/ui/src/renderers/kit/shell/fileView.js)): `camera` (the renderer's own — a scene's pose, lens and projection, restored in place of the open-time fit; a drawing's plane transform), `display` (the Display settings, Clip and Explode included), `playback` (preview's Playback settings: orbit on or off and its speed, Autoplay, and — once chosen — the Speed and Loop the routine plays with, unset meaning the routine's own; kept between leaving and re-entering preview; defaults orbit on at 1×, Autoplay off) and `renderer`, the renderer's own slices, each behind the signature it was written against: a STEP's expanded nodes, hidden parts, isolated assemblies, pose and large-file opt-in; a robot's joint values. A slice whose signature no longer matches the file on screen is dropped; the camera, the display and the playback are always kept. The fifty most recently written files stay; the oldest goes. |

| Not kept | Every open starts it afresh |
| --- | --- |
| The tool in hand | The renderer's default tool (Select) |
| The selection (a STEP's tree and topology, a robot's links), measurements, Draw's ink | Empty |
| Preview and its camera | Off; its Playback settings are the file's, above |
| The routine, its time and whether it is playing | At rest |
| The Select mode filter, hover, menus, the open panel, popovers | The page's own |
| The open panel of the host's column | `panel: null`: a page load opens a file on its own default |

Appearance applies before the first paint: the inline script in
[index.html](../index.html) reads the same key and applies `settings.appearance`
to the document, so a tab left in Dark never paints light and flips. A new tab
has no record and follows the OS.

Writes are whole and synchronous: the shell writes a file's view a moment after
each change and once more on unmount (the page's `pagehide` unmounts the app), the
store writes the record through at once, so what the tab last saw is what a
reload restores. Storage access is explicit in the host; constructing or
importing a renderer never chooses a browser storage backend.

## localStorage

One key, and it is not viewer state: `cad-viewer:latest-release:v1:<api url>`
caches the latest-release check ([ViewerLinks.jsx](../src/client/components/workbench/ViewerLinks.jsx))
so every tab does not ask GitHub again. It is a network cache with a time to
live, shared by every tab, and it says nothing about what any tab shows. Nothing
else goes in localStorage: a value that depends on a file, a root, a tab or a
person's choice belongs in the tab record.
