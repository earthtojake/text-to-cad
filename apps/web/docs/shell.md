# Hosting the shared FileViewer

The complete file-tab interface lives in `@hardcore/ui/file-viewer`. Web and
desktop both render that component. Navigation controls are lower-level
`@hardcore/ui/navigation` exports used by FileViewer; apps do not assemble a
second shell from them.

Web supplies a read-only catalog source, the CAD renderer registration, URL
navigation, browser persistence and appearance. Its top bar and release links
remain in this app. The root workspace builds UI's ESM, declarations, CSS and
worker assets before building the app; no source alias or JSX loader is needed.

This is a pure refactor. The same rows, menus, panels, controls, shortcuts and
CAD interactions retain their existing behavior and appearance. Native file
operations remain desktop capabilities, while web continues to offer the
existing open/copy actions. No new filesystem or editing endpoints are added.

See the app README for commands and `@hardcore/ui`'s README and type declarations
for the source, renderer and lifetime contracts.
