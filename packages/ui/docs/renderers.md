# File renderers

The viewer renderers, `cad` (STEP), `dxf`, `glb`, `mesh` (STL, 3MF) and `robot` (URDF, SRDF, SDF), and
the kit and shell they are built on are in [CAD renderer](cad-renderer.md). They are
this package's renderers because both apps register them.

A renderer only one host registers belongs to that host. The desktop's Markdown,
code, image, PDF and unsupported-file renderers live in the desktop app
(`apps/desktop/src/renderer/features/explorer/renderers/`), with their Monaco,
TipTap and PDF.js dependencies and their tests; its README describes them. They
use only this package's public exports, and they are what a host renderer may
rely on:

- `defineFileRenderer` and the registration contract from `@hardcore/ui/file-viewer`
  ([FileViewer](file-viewer.md)), including `fallback: true` for the one
  renderer that takes files nothing else matches, and `body` panels for a view
  that replaces the content rather than sitting in the panel column (the
  Markdown source view's).
- Text preparation through `FileSource.readText`, which opts into FileViewer's
  document session: revision-checked saves, drafts, conflicts and reloads.
- Assets through `FileSource.readAsset`. Every acquired asset URL carries a
  release lease; the renderer returns it as the prepared document's `dispose`,
  and FileViewer releases it when the request is cancelled, the file changes,
  or the view unmounts.
- The host ports in `@hardcore/ui/host`: `useViewerHost`, `PromptContextAction`
  for prompt delivery, and the live `documents` and `pdf` capabilities
  ([viewer host](viewer-host.md#live-text-and-pdf-capabilities)).
- Shared chrome from `@hardcore/ui/navigation` (`EmptyState`),
  `@hardcore/ui/primitives/*` and `@hardcore/ui/utils`, styled by this
  package's `styles.css` and the host's own Tailwind build.
