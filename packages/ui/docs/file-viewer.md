# FileViewer

`@cad/ui/file-viewer` exports the complete file view: one file by its
absolute path, under the navbar (or alone, `chrome: "bare"`), with the project it is in (its name
in the navbar, and `[` and `]` through its documents), renderer loading, and the
loading and error pages.
It imports no concrete renderer. Applications compose registrations from the
separate `@cad/ui/renderers/*` entry points and their own
`defineFileRenderer` definitions ([renderers](renderers.md)). A CAD host composes
`CadViewer` (`@cad/ui/cad-viewer`), which is this component with the six
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
has a home; a view that shows one file alone has neither, and no project) and keeps
`FileViewerState` in its tab store (`@cad/ui/tab-store`; `useTabViewerState`
derives it): `renderers`, under encoded `[file path, renderer ID]` keys, each the
file's view.

A source reads files and never writes them. `stat(path)` answers a file's metadata; it
browses no folder: moving between files is the project's (`project`, below). What the file
menu offers is the host's separate `fileActions` capabilities. Sources receive an `AbortSignal` for each read;
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
file's controls are its own, over the viewport: its tool strip and the tool in hand's
sub-toolbar, with its panel docked beside it
([the panel](viewer-ux.md#the-panel)); the view's
controls (Display, whose card holds a 3D view's Projection, and Preview) stand at the navbar's right end, portalled
into its view slot (with no navbar they end its strip), and in Preview its own bar holds
Preview's, the navbar hidden.

Below 600px of its own width FileViewer is mobile (`useViewerMobile`). The width is a
breakpoint boolean, never a pixel value, so a resize within one layout does not
re-render the renderer. Its root says which (`data-viewer-layout`), and the page's stylesheet reads it: a phone's
type and touch targets a step up, page-wide, so a menu portalled out of the view matches it. Only the page's own
viewer says so. A viewer that is not the page's (a library card's picture, drawn out of sight at 480px:
`OffscreenPicture.tsx`) pins its layout (`layout="mobile"` or `"desktop"`), measures nothing and carries no
`data-viewer-layout`, and the page-wide rules ignore anything inside `[data-offscreen-picture]`, so Home's type never
changes while its cards get their pictures.

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

## The navbar and the project

The navbar is drawn over every file from the moment one is asked for, and over the
host's home — only its logo and menu, without Back to home, Back and Forward where the
host keeps the view's history, and the host's actions, where they stand over
a file — never for a `compact` view (a
picture: the home's thumbnails), never where the host asks for the view alone
(`chrome: "bare"`, `FileViewerProps.chrome`; the default is `"page"`: the CAD app hands
`"bare"` to its file handler alone, whose host's file tree is its navigation), and not while a renderer says its
Preview is up (`RendererViewProps.onPreviewChange`): the viewer's Preview draws its own
bar in its place and gives it back as it closes. Over a file, left to right:

- the view's panel toggle, where the file has a panel (`panelToggles.js`, said by the view's frame): the strip's
  28px tile, the same neutral button open or shut, which shows and hides the panel (`⌘\` or `Ctrl+\`), a mouse
  resting on it peeking the collapsed panel over the view;
- the text-to-cad "C" logo (named Menu, with no chevron; the same 16px mark over the home),
  which opens the app menu
  (`navigation/AppMenu.jsx`): Back to home where the host has a home
  (`navigation.home`), Search documents with its key where the host has the search (`onSearch`),
  the person's settings (`appSettings`), Send feedback, GitHub,
  Discord and, in gray, the version and who made it. FileViewer builds it from
  `host.links`, `appSettings` and `environment.platform`. A host with no home has the
  logo and the menu too, without Back to home;
- Back and Forward, where the host keeps the view's own history (`history`, a
  `ViewerHistory`: the CAD app's views; a browser's page has its own and hands none): two
  arrows, each there always and disabled where it has nowhere to go;
- where the document is in a project (`project`), the project's name and a slash, muted (Figma's
  location before a file's name): a press goes to the host's home at that project (`project.onShow`). Where the
  host gives that page an address (`project.href`) it is a real link: a plain click is `onShow`, and a modified
  or middle click, or the link's menu, the browser's new tab. It truncates as the row narrows, down to 80px; under
  that, and on a phone, it is a control-sized folder tile named by the project: the file's name keeps its width,
  up to 65% of the row;
- the open file's name, alone: no glyph, no chevron, and no menu of its own;
- the ⋯ file menu, from the document itself outwards: Copy path, Copy link; Open in new tab
  (`navigation.openBeside`, `{ document }` the document on screen; "Open in browser" where its `kind`
  is `browser`, and left out where Open in's Browser is there already); Open in, a submenu of Browser
  (`fileActions.perform.browser`) and the file manager by its name (Finder, File Explorer, File
  manager: `reveal`); then the host's own items (`fileMenuItems`: the viewer's Export submenu); and
  last, after a rule, the project: Previous in project and Next in project, their keys `[` and `]`
  at the right, each off at its end (a project of more than one document), or for a document in no
  project, Import its folder as a project (`onImportFolder`, where the host can: its chooser,
  starting at the document's folder, so the person picks the level). Each only where the
  host's `fileActions` can do it (Copy path and the file manager need a file on disk: a
  model's act on its script, `sourceFile`, and it has neither where none is named; a source moved
  or deleted, `sourceMissing`, draws what opens it disabled with its reason), and no ⋯
  where there is nothing. The menu and its submenus are shadcn's own width.

The logo, Back and Forward, the project's name and the ⋯ are one kind of control: transparent
at rest, the same accent background while the pointer is on it and while its menu is open, a
pointer cursor, and no tooltip (the project's folder tile has one: its name).

At the right, only what a host or a file adds: a renderer's actions; the view's own controls, Display (the plain
cube, whose card holds how the picture is drawn, a 3D view's Projection among it) and a 3D view's or a board's Preview,
which the view portals into the navbar's view slot (`navbarSlots.js`); and last, outermost, the host's own
(`navbarActions`: the CAD app's Full size, inline). Back and Forward are a desktop row's alone: a phone's has no room
for them. Preview's settings and Exit preview are Preview's bar's.

The view's panel is the document's own: no project list leads it. `[` and `]` move to the previous and next of
the project's documents (`project.documents`, in the host's order, a document gone skipped, nothing past either
end), opened through `navigation.openFile`, the name the navbar shows kept until the host reads the document
(`projectKeys.js`). FileViewer hands the two to its view (`ProjectKeysContext`, a ref, so a project read again
re-renders no view), and the view's own keys reach them (`useProjectKey`, from `kit/shell/useViewerShortcuts.js`):
single keys, never in a field, held, with a modifier or in Preview. The ⋯'s Previous and Next do the same; both are
counted (`project_previous`, `project_next`). A view that shows its file alone (no `navigation.openFile`) has none.

`onSearch`, where the host has the search of every document (`CadViewer` mounts `search/DocumentSearch.tsx`), is the
app menu's Search documents and ⌘K (Ctrl+K off a Mac, by `environment.platform`), bound by FileViewer from anywhere on
the page but Preview, and never over another dialog ([Search](viewer-ux.md#search)).

The browser harness beside FileViewer exercises injected renderers, source and file
changes, navigation actions, the project's name and the file menu, the mobile breakpoint,
and resource disposal. Run it with the package test command after building the shared
packages. Chromium must be available for the browser tests.
