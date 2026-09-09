# FileViewer

`@hardcore/ui/file-viewer` exports the complete file tab: breadcrumbs, entry
menus, the file tree, one panel column, renderer loading, and the text editing
session. It imports no concrete renderer. Applications compose registrations
from the separate `@hardcore/ui/renderers/*` entry points.

```tsx
<FileViewer
  file={selectedPath}
  source={fileSource}
  renderers={registeredRenderers}
  state={viewState}
  onStateChange={persistViewState}
  onOpenFile={(path, options) => navigate(path, options?.target)}
  appearance={{ colorScheme }}
/>
```

Create sources and registration arrays at their owning workspace or tab
lifetime. Changing their object identity cancels outstanding document work.
`source.id` is a stable root identity, independent of a server's temporary port.
Every path is relative to that source; containment and authorization remain in
the host service. The host controls navigation and persists `FileViewerState`
per source identity. Its `renderers` section uses encoded file-path/renderer-ID
pairs, while `panel`, `panelWidth`, and `expandedDirectories` describe chrome.

The source provides metadata and optional directory, text, asset, and write
operations. Optional action callbacks determine which entry-menu items appear.
Rename and create fields, menu focus, and panel switching remain in FileViewer;
the host performs the operation and can update other tabs affected by it.
The `leading` slot can label a host-specific root, such as a worktree.

Sources receive an `AbortSignal` for each read and write. Noncancellable host
transports must still check that signal before returning an answer. Each
successful `readAsset` returns a URL and its `release()` lease. A renderer must
return that release function as its prepared document's `dispose`; FileViewer
releases it on navigation, reload, cancellation, and unmount.

Use `defineFileRenderer<T>` to keep the prepared payload paired with its lazy
component. A definition supplies `id`, numeric `priority`, `matches`, `prepare`,
and `load`. Larger priorities win. Duplicate IDs and equal-priority matches
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

Panel declarations use stable IDs and `content: "slot" | "body"`. The renderer
portals a slot panel into `panelSlot`; a body panel replaces its own content.
`openPanel` and `onPanelOpen` keep every renderer panel exclusive with the file
tree. `onReady(false)` suppresses panels whose surface could not start.
`onChromeVisibilityChange(false)` supports an immersive preview and resets on
the next document. Host-specific empty, loading, and error artwork can be
supplied through `presentation`, without duplicating the tab's placement.
`onActivityChange` publishes work on the current file to `presentation.activity`;
hosts can preserve their existing filename indicator. `narrowCrumbs` optionally
overrides automatic breadcrumb folding. Per-file renderer state is also accepted
during a departing renderer's cleanup, while it still belongs to the same root.
`navigationPath` can keep navigation unselected while a requested file is still
being resolved by a host catalog. It does not change the requested document.

The browser harness beside FileViewer exercises injected renderers, dirty and
revision state, delayed writes, changes, root isolation, navigation actions,
preview mode, and resource disposal. Run it with the package test command after
building the shared packages. Chromium must be available for the browser tests.
