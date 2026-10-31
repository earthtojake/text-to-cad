# FileViewer

`@text-to-cad/ui/file-viewer` exports the complete file view: one file by its
absolute path, under the navbar (or alone, `chrome: "bare"`), with the name menu its name opens
(Models and Files), renderer loading, and the loading and error pages.
It imports no concrete renderer. Applications compose registrations from the
separate `@text-to-cad/ui/renderers/*` entry points and their own
`defineFileRenderer` definitions ([renderers](renderers.md)). A CAD host composes
`CadViewer` (`@text-to-cad/ui/cad-viewer`), which is this component with the five
CAD renderers, the home and the standard error pages ([viewer host](viewer-host.md)).

```tsx
<FileViewer
  file={selectedPath}   // absolute; null is the host's home
  host={viewerHost}
  renderers={registeredRenderers}
  state={viewState}
  onStateChange={persistViewState}
/>
```

See [ViewerHost](viewer-host.md) for required host services and prompt delivery.
Create sources and registration arrays at their owning workspace or tab
lifetime. Changing their object identity cancels outstanding document work.
`source.id` is a stable identity, independent of a server's temporary port. Every
path is absolute and `/`-separated (`/a/b.step`, `C:/a/b.step`); containment and
authorization remain in the host service. The host controls navigation
(`navigation.openFile(path)` where the view can show another file, and `home()` where it
has a home; a view that shows one file alone has neither, and no name menu) and keeps
`FileViewerState` in its tab store (`@text-to-cad/ui/tab-store`; `useTabViewerState`
derives it): `renderers`, under encoded `[file path, renderer ID]` keys, each the
file's view.

A source reads files and never writes them. `stat(path)` answers a file's metadata;
where its files can be browsed, `list(directory)` answers a folder's entries and
`search(directory, query)` the files under a folder whose path below it holds the
query, saying when it stopped early. What the file menu offers is the host's
separate `fileActions` capabilities. Sources receive an `AbortSignal` for each read;
noncancellable reads still check the signal before returning. A renderer that
acquires a resource (a URL lease, a worker) returns its release as the prepared
document's `dispose`; FileViewer calls it on navigation, reload, cancellation and
unmount.

Use `defineFileRenderer<T>` to keep the prepared payload paired with its lazy
component. A definition supplies `id`, numeric `priority`, `matches`, `prepare`,
and `load`, and optionally `fallback`. Larger priorities win.
Duplicate IDs and equal-priority matches
produce explicit errors. At most one registration may declare `fallback: true`;
it runs only when no ordinary registration matches. Registration construction
and matching do not load the component.

`prepare` returns `{ data, dispose? }`. FileViewer opens a file's document when the
file is shown, and again only on `reload`: a renderer follows its file's changes
itself (every CAD renderer loads the next revision behind what is on screen). A CAD
file's controls are its own, over the viewport: its tool strip, the tool in hand's
sub-toolbar, and its file sidebar
([the design system](settings-ui.md#the-file-sidebar-and-the-tool-stack)); the view's
controls (Projection, Display, Preview) end its strip, and in Preview its own bar holds
Preview's, the navbar hidden: nothing of the view is the navbar's.

Below 600px of its own width FileViewer is mobile (`useViewerMobile`). The width is a
breakpoint boolean, never a pixel value, so a resize within one layout does not
re-render the renderer.

A renderer is handed, besides its document: `onNavigationActionsChange`, for its
nav-row actions (`FileNavigationAction`, with an optional shorter `hint`), hidden
while it reports `onReady(false)`; `appearance`; and `onOpenFile(path)`, which shows another file, by
its absolute path, in this view (a robot's mesh), absent where the view shows its file alone. Its loading and update status are its
own to show: a CAD renderer shows them in its viewport. Host-specific pages are supplied through `presentation`,
without duplicating the view's placement: `home` is a host's own page for a view with
no file (every CAD host's model library), under the navbar; `loading`; and
`error({ message, missing, error })` for a file that will not open, `missing` when it does
not exist, `error` what the source raised (a host reads its own fields on it). Per-file renderer state is also accepted during a departing renderer's
cleanup, while it still belongs to the same source.

## The navbar and the explorer

The navbar is drawn over every file from the moment one is asked for, and over the
host's home — only its logo and menu, without Back to home, Back and Forward where the
host keeps the view's history, and the host's update and actions, where they stand over
a file — never for a `compact` view (a
picture: the home's thumbnails), never where the host asks for the view alone
(`chrome: "bare"`, `FileViewerProps.chrome`; the default is `"page"`: the CAD app hands
`"bare"` to its file handler alone, whose host's file tree is its navigation), and not while a renderer says its
Preview is up (`RendererViewProps.onPreviewChange`): the CAD viewer's Preview draws its own
bar in its place and gives it back as it closes. Over a file, left to right:

- the text-to-cad "C" logo (named Menu, with no chevron; the same 16px mark over the home),
  which opens the app menu
  (`navigation/AppMenu.jsx`): Back to home where the host has a home
  (`navigation.home`), the person's settings (`appSettings`), Send feedback, GitHub,
  Discord and, in gray, the version and who made it. FileViewer builds it from
  `host.links`, `appSettings` and `environment.platform`. A host with no home has the
  logo and the menu too, without Back to home;
- Back and Forward, where the host keeps the view's own history (`history`, a
  `ViewerHistory`: the CAD app's views; a browser's page has its own and hands none): two
  arrows, each there always and disabled where it has nowhere to go;
- the open file's name, alone (no glyph; its chevron where it opens the name menu): a
  button that opens the name menu where the view can show another document, and plain text
  otherwise;
- the ⋯ file menu: Copy path, and Reveal in Finder / Show in Explorer / Show in file
  manager, each only where the host's `fileActions` can do it, and no ⋯ where it can do
  none.

The logo, Back and Forward, the name (where it opens the name menu) and the ⋯ are one kind of control: transparent
at rest, the same accent background while the pointer is on it and while its menu is open, a
pointer cursor, and no tooltip.

At the right, only what a host or a file adds: the host's update button, a renderer's
actions, and last the host's own (`navbarActions`: the web viewer's Export). A renderer's own
view controls are never here: a 3D view's Projection, Display and Preview end its tool strip,
and Preview's settings and Exit preview are Preview's bar's.

The name menu is a popover under the file's name, a fixed 17.5rem wide and never resized. It
floats over the view, so opening it resizes nothing, and it is built anew on each opening. Two
stock shadcn Tabs top it, **Models** and **Files**, each as wide as its label, over the
explorer's own style; it opens on Models over a model and on Files over a file, and a menu with
one of the two has no tabs. **Models** (`navigation/ModelList.jsx`) lists the models of the
host's library (`FileViewerProps.recent`, a `list()` of `RecentDocument`s; a row whose `kind` is
a model's or a shape's), by last activity (the later of each row's `opened` and `updated`),
eight at most, in the explorer's compact rows: the model's glyph, the name, and its age with no
verb at the right, under "Filter models..." (every word in the name, the filter taking the
keyboard as the explorer's does); the model on screen is highlighted, a row opens it through
`navigation.openFile`, and there is no footer.
**Files** is the explorer (`navigation/FolderExplorer.jsx`). It starts in the open file's
folder, or `explorerFolder` for a document with no file of its own (a model's: the folder the
explorer was last in, which `onExplorerFolderChange` hands the host each time it changes, else
the person's home folder; never the script's),
its filter taking the keyboard (on a phone the menu holds focus itself, so no
keyboard comes up). It lists one folder at a time through `source.list`: the folder's
subfolders, then its CAD files, the open file highlighted, in compact rows (a folder's glyph
its disclosure chevron). A press on a subfolder opens it inline, under itself and a little
further in, reading it through `source.list` the first time; a double-click opens it in the
explorer's place. A breadcrumb shows as many of
the last three folders of the one it is in as fit whole, measured before it is painted:
a crumb is never cut, the farthest giving way first to a "…" button whose menu lists the
folders above the crumbs to jump to, and only the folder it is in, alone beside the "…",
is cut to the row. A crumb, as a double-click does, opens a folder in place, and there is
no up arrow. "Filter files..." searches every file nested under the folder it is
in through `source.search`: the client waits 150 ms after the last keystroke and
aborts the search before it, and each match shows its path below the folder, the
subfolders muted before the name. An answer that is `truncated` adds "Stopped early.
Keep typing to narrow the search." The viewer server bounds both reads
(`GET /__cad/folder`, `/__cad/search`): hidden and build folders are left out of each,
and a search stops at 200 results, about 1.5 s or depth 24, walking a folder it reaches
twice once. A pick opens the file through `navigation.openFile` and closes the popover.
Up and Down move between the filter and the rows; Escape closes it like any popover.

The browser harness beside FileViewer exercises injected renderers, source and file
changes, navigation actions, the explorer and the file menu, the mobile breakpoint,
and resource disposal. Run it with the package test command after building the shared
packages. Chromium must be available for the browser tests.
