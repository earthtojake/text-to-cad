# File renderers

The viewer renderers, `cad` (STEP), `dxf`, `glb`, `mesh` (STL, 3MF) and `robot` (URDF, SRDF, SDF), and
the kit and shell they are built on are in [CAD renderer](cad-renderer.md). They are
this package's renderers because every host registers them.

A renderer only one host registers belongs to that host, with its own
dependencies and tests. It uses only this package's public exports, and they are
what a host renderer may rely on:

- `defineFileRenderer` and the registration contract from `@text-to-cad/ui/file-viewer`
  ([FileViewer](file-viewer.md)), including `fallback: true` for the one
  renderer that takes files nothing else matches, and `body` panels for a view
  that replaces the content rather than sitting in the panel column.
- The file it is handed (`FileMetadata`) and its `FileSource`, which names and
  describes files and reads nothing else: a renderer reads a file's content through
  what its host injects into it (the CAD renderers take a `CadWorkspaceService`).
  Every resource a renderer acquires carries a release; it returns that as the
  prepared document's `dispose`, and FileViewer releases it when the request is
  cancelled, the file changes, or the view unmounts.
- The host ports in `@text-to-cad/ui/host`: `useViewerHost`, and `PromptContextAction`
  for prompt delivery.
- Shared chrome from `@text-to-cad/ui/navigation` (`EmptyState`),
  `@text-to-cad/ui/primitives/*` and `@text-to-cad/ui/utils`, styled by this
  package's `styles.css` and the host's own Tailwind build.
