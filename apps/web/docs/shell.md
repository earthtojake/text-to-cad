# Hosting the shared CAD viewer

The CAD viewer every app shows is `@text-to-cad/ui/cad-viewer`'s `CadViewer`: the
shared FileViewer over one root's CAD catalog, its five renderers, the home (the
model library) with no file open, catalog following, the loading and missing-file
pages and the library's pictures. Navigation controls are lower-level
`@text-to-cad/ui/navigation` exports used by FileViewer; apps do not assemble a
second shell from them.

Web supplies the served folder's catalog (`createCatalogFileSource` from
`@text-to-cad/ui/catalog`), URL navigation (`onShow`, `?file=` and history),
browser persistence, the document title and appearance. It hands the viewer its
links (`ViewerHost.links`: its version, its build's GitHub and Discord, and what
its release check found, `src/host/viewerLinks.js`) and its appearance control
(`displayActions`); the navbar, the explorer, the toolbar and preview are the
shared package's. The root workspace builds UI's ESM, declarations, CSS and
worker assets before building the app; no source alias or JSX loader is needed.

Native file operations are desktop capabilities. Web offers copy-path actions
and, when the server advertises `reveal-path`, reveal in the file manager; it has
no filesystem-writing or editing endpoints.

See the app README for commands and `@text-to-cad/ui`'s README and type declarations
for the source, renderer and lifetime contracts.
