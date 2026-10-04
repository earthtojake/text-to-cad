# FileViewer

`@text-to-cad/ui/file-viewer` exports the complete file tab: the navbar, entry
menus, the file explorer, the column a file's declared panels open in, renderer
loading, and the text editing session. It imports no concrete renderer.
Applications compose registrations from the separate `@text-to-cad/ui/renderers/*`
entry points and their own `defineFileRenderer` definitions ([renderers](renderers.md)).
A CAD host composes `CadViewer` (`@text-to-cad/ui/cad-viewer`), which is this
component with the five CAD renderers, the home and the catalog rules
([viewer host](viewer-host.md)).

```tsx
<FileViewer
  file={selectedPath}
  host={viewerHost}
  renderers={registeredRenderers}
  state={viewState}
  onStateChange={persistViewState}
/>
```

See [ViewerHost](viewer-host.md) for required host services and prompt delivery.
Create sources and registration arrays at their owning workspace or tab
lifetime. Changing their object identity cancels outstanding document work.
`source.id` is a stable root identity, independent of a server's temporary port.
Every path is relative to that source; containment and authorization remain in
the host service. The host controls navigation and keeps `FileViewerState` in its
tab store (`@text-to-cad/ui/tab-store`; `useTabViewerState` derives it for one root). Its
`renderers` section uses encoded file-path/renderer-ID pairs, each the file's view
under this root, while `panel`, `panelWidth`, and `expandedDirectories` describe chrome
— the width and the expansion are the tab's, the open panel the page's own.

The source provides metadata and optional directory, text, asset, and write
operations. Storage methods and separate native `host.fileActions` capabilities determine
which entry-menu items appear.
Rename and create fields, menu focus, and panel switching remain in FileViewer;
the host performs the operation and can update other tabs affected by it.

Sources receive an `AbortSignal` for each read and write. Noncancellable reads
still check the signal before returning. Writes and mutations report committed
receipts even if the caller cancels after dispatch; cancellation is not rollback. Each
successful `readAsset` returns a URL and its `release()` lease. A renderer must
return that release function as its prepared document's `dispose`; FileViewer
releases it on navigation, reload, cancellation, and unmount.

Use `defineFileRenderer<T>` to keep the prepared payload paired with its lazy
component. A definition supplies `id`, numeric `priority`, `matches`, `prepare`,
and `load`, and optionally `panels` and `fallback`. Larger priorities win.
Duplicate IDs and equal-priority matches
produce explicit errors. At most one registration may declare `fallback: true`;
it runs only when no ordinary registration matches. Registration construction
and matching do not load the component.

`prepare` returns `{ data, text?, dispose? }`. Supplying `text` opts into the
common document session, including revision-checked saves, dirty state,
conflicts, failures, and explicit reloads. Renderers use `document.value`,
`setValue`, `save`, and `readOnly`. Editor model identity must include
`document.key`, which includes the root, file, and reload generation. Edits made
during a pending save survive its response. External changes reload clean
documents; dirty documents retain their draft and show the existing reload
choice.

A definition's `panels({ open, ready, file, data })` returns the navbar's
panels for one prepared document, so it can read what `prepare` found (`data`).
Panel declarations use stable IDs and `content: "slot" | "body"`; FileViewer
appends the file tree (`content: "tree"`) last. The navbar holds one toggle per
panel — the explorer's at its left, after the home mark, a declared panel's at its
right — and one panel is open at a time. The tree is the file explorer, which
floats over the body's left, inset 8px like the tool strip, on a solid background
above the tools, and never resizes the body; a declared panel opens in the column
at the body's right. A CAD file declares none: its controls are
panels of its own tool stack, over the viewport, shown by the tool they belong to
([the design system](settings-ui.md#the-tool-stack)); nothing it does opens or turns
the explorer. A renderer that declares a slot panel portals it into `panelSlot`; a
body panel (the desktop markdown's source view) replaces its own content. `openPanel` and `onPanelOpen` keep every renderer panel exclusive
with the file tree. `onReady(false)` suppresses panels whose surface could not
start. `FileViewerState.panel` is `null` until someone chooses, which opens the
first panel declared `defaultOpen`, or nothing; the
tree is the default only when no file is open and the host has no home to show. `""` is nothing open. Which panel
a newly shown file opens with is the host's to apply: `navigation.openFile(path,
{ target, panel })` names it — the tree, for a file picked in the tree, so the
tree stays up while a person walks it — and without one a file shown in place or
in a new view opens at `null`, while a view already showing the file keeps its
panel.

Below 720px of its own width FileViewer is mobile (`useViewerMobile`): the
explorer and the panel column become floating sheets over the body, opened only
by their toggles (an empty tab with no home still opens on its tree) and closed on
every document change and by a pick in the tree, while the stored `panel` and
`panelWidth` stay as the wide layout left them. The width is a breakpoint boolean,
never a pixel value, so a panel drag or a resize within one layout does not
re-render the renderer. The explorer and the column are 220px by default, 140px at
least and 480px at most (`panelWidth.js`); a drag past the minimum stops at it, and
only one below half the minimum closes the panel.

A renderer is handed, besides its document: `onNavigationActionsChange`, for
its nav-row actions (`FileNavigationAction`, with an optional shorter `hint`);
`displayActions`, the host's controls for the Display settings; and `appearance`.
Its loading and update status are its own to show: a CAD renderer shows them in
its viewport. Host-specific empty,
loading, and error artwork can be supplied through `presentation`, without
duplicating the tab's placement. `presentation.home` is a host's own page for a
tab with no file (every CAD host's model library) in place of `empty`: an empty
tab opens on its file tree because the tree is all there is to reach for, but not
over a home, which is a page to see: the explorer floats over it and would cover it. Per-file renderer state is also accepted during
a departing renderer's cleanup, while it still belongs to the same root.
`navigationPath` can keep navigation unselected while a requested file is still
being resolved by a host catalog. It does not change the requested document.

The navbar is drawn only when it holds something: the way home
(`navigation.home`, with a file open), the explorer's toggle (a source with
`list`), the open file's name (`navigationPath` names it: the file's own path by
default, `null` while a host resolves it), a renderer's actions, a panel toggle,
the host's `links`, update, Settings or Full size (`fullSize`, last, where the host
shows the view small), or the unsaved-changes dot — and never for a `compact` view,
a picture (the home's thumbnails). The C mark leads every row that is drawn.
The name has a ⋯ with the explorer's menu for the file when the host can do
anything with it; it has no right-click menu and no crumbs: folders are the
explorer's to show.

The browser harness beside FileViewer exercises injected renderers, dirty and
revision state, delayed writes, changes, root isolation, navigation actions,
panel suspension, the mobile breakpoint, and resource disposal. Run it with the package test command after
building the shared packages. Chromium must be available for the browser tests.
