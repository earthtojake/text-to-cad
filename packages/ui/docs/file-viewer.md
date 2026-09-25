# FileViewer

`@hardcore/ui/file-viewer` exports the complete file tab: breadcrumbs, entry
menus, the file tree, one panel column, renderer loading, and the text editing
session. It imports no concrete renderer. Applications compose registrations
from the separate `@hardcore/ui/renderers/*` entry points and their own
`defineFileRenderer` definitions ([renderers](renderers.md)).

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
the host service. The host controls navigation and persists `FileViewerState`
per source identity. Its `renderers` section uses encoded file-path/renderer-ID
pairs, while `panel`, `panelWidth`, and `expandedDirectories` describe chrome.

The source provides metadata and optional directory, text, asset, and write
operations. Storage methods and separate native `host.fileActions` capabilities determine
which entry-menu items appear.
Rename and create fields, menu focus, and panel switching remain in FileViewer;
the host performs the operation and can update other tabs affected by it.
The `leading` slot can label a host-specific root, such as a worktree.

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

A definition's `panels({ open, ready, file, data })` returns the nav row's
panels for one prepared document, so it can read what `prepare` found (`data`).
Panel declarations use stable IDs and `content: "slot" | "body"`; FileViewer
appends the file tree (`content: "tree"`) last. The nav row holds one toggle per
panel, and one panel is open at a time. A viewer file declares at most one panel,
its Settings (`viewerPanels`); whatever tabs that panel has are its own
(`FilePanelTabs`, see [the design system](settings-ui.md#sidebars-and-mobile)).
The renderer portals a slot panel into `panelSlot`; a body panel replaces its
own content. `openPanel` and `onPanelOpen` keep every renderer panel exclusive
with the file tree. `onReady(false)` suppresses panels whose surface could not
start. `FileViewerState.panel` is `null` until someone chooses, which opens the
first panel declared `defaultOpen` (a viewer file's Settings), or nothing; the
tree is the default only when no file is open. `""` is nothing open. Which panel
a newly shown file opens with is the host's to apply: `navigation.openFile(path,
{ target, panel })` names it — the tree, for a file picked in the tree, so the
tree stays up while a person walks it — and without one a file shown in place or
in a new view opens at `null`, while a view already showing the file keeps its
panel.

Below 720px of its own width FileViewer is mobile (`useViewerMobile`): the
panel column becomes a floating sheet over the body, opened only by its toggle
(an empty tab still opens on its tree) and closed on every document change,
while the stored `panel` and
`panelWidth` stay as the wide layout left them; the breadcrumbs collapse to the
current file. The width is a breakpoint boolean, never a pixel value, so a panel
drag or a resize within one layout does not re-render the renderer.

A renderer is handed, besides its document: `navigationStatusSlot`, the nav-row
element after the filename where it portals its loading and update status (the
row itself adds only the unsaved-changes dot); `onNavigationActionsChange`, for
its nav-row actions (`FileNavigationAction`, with an optional shorter `hint`);
`displayActions`, the host's controls for the Display popover;
`onPanelVisibilityChange(visible)`, which suspends the panel column and disables
its toggles while keeping the open panel and width (the shell's fullscreen uses
it; the next document restores it); and `appearance`. Host-specific empty,
loading, and error artwork can be supplied through `presentation`, without
duplicating the tab's placement. Per-file renderer state is also accepted during
a departing renderer's cleanup, while it still belongs to the same root.
`navigationPath` can keep navigation unselected while a requested file is still
being resolved by a host catalog. It does not change the requested document.

The browser harness beside FileViewer exercises injected renderers, dirty and
revision state, delayed writes, changes, root isolation, navigation actions,
panel suspension, the mobile breakpoint, and resource disposal. Run it with the package test command after
building the shared packages. Chromium must be available for the browser tests.
