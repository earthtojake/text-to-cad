# CAD Viewer theme guidance

The former Nord / frosted-glass SMUI styling has been replaced by the neutral
light and charcoal dark palette. Follow the current viewer contracts in
[the app README](../../README.md#appearance-display-and-render) and
[settings UI](../../docs/settings-ui.md).

- Color tokens live in `src/client/styles/globals.css`: `:root` is light and
  `.dark` is dark. Keep the existing sans-serif font and sharp corners.
- Use opaque semantic surfaces: `bg-sidebar` for panel shells, `bg-popover`
  for floating menus, and `bg-background` for controls over the canvas.
  Do not restore scene-tinted glass tokens or backdrop blur on these surfaces.
- App appearance follows its light/dark/system preference. Selecting a CAD
  scene preset does not change the app's appearance.
- The System scene follows app appearance and its CSS background token.
  Named presets and Custom retain their own scene settings.
- Use sentence case and the shared field primitives described in settings UI.
  Do not import the old uppercase terminal styling or run a UI scaffolder.
