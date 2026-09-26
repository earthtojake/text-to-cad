# Hosting the shared FileViewer

The complete file-tab interface lives in `@hardcore/ui/file-viewer`. Web and
desktop both render that component. Navigation controls are lower-level
`@hardcore/ui/navigation` exports used by FileViewer; apps do not assemble a
second shell from them.

Web supplies a read-only catalog source, the viewer renderer registrations, URL
navigation, browser persistence and appearance. It fills FileViewer's slots with
its own brand (`leading`), release links (`navigationActions`) and appearance
control (`displayActions`); the nav row, toolbar, sidebars and fullscreen are the
shared package's. The root workspace builds UI's ESM, declarations, CSS and
worker assets before building the app; no source alias or JSX loader is needed.

Native file operations are desktop capabilities. Web offers copy-path actions
and, when the server advertises `reveal-path`, reveal in the file manager; it has
no filesystem-writing or editing endpoints.

See the app README for commands and `@hardcore/ui`'s README and type declarations
for the source, renderer and lifetime contracts.
