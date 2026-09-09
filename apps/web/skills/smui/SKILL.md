# Shared UI styling for the CAD Viewer

The CAD Viewer is a Vite and Tailwind v4 host of `@hardcore/ui`. Shared
components and CAD controls live in that package; the web app owns its top bar
and browser-specific composition. Read the
[UI package boundary](../../../../packages/ui/README.md) before changing a
shared control.

The package migration is a pure refactor. Preserve the current appearance and
interaction behavior of each app: typography, spacing, borders, surfaces,
responsive layout, loading states and saved preferences. Moving a component
does not authorize a redesign. Compare changes against the existing app in
both color schemes and at narrow widths.

## Tokens and ownership

- Canonical tokens live in
  [packages/ui/src/styles/tokens.css](../../../../packages/ui/src/styles/tokens.css).
  The current palette is neutral, with light and dark variants and the existing
  radius scale. Reuse those values and semantic utilities such as
  `bg-background`, `text-muted-foreground`, `border-border` and
  `text-destructive`.
- The web entry stylesheet,
  [globals.css](../../src/client/styles/globals.css), imports
  `@hardcore/ui/tokens.css` and `@hardcore/ui/styles.css`. Shared utility classes
  and assets are built by the UI package; apps do not scan another package's
  source or duplicate its token definitions.
- The host supplies the color scheme and applies its existing `.dark` behavior.
  Keep the CAD scene theme separate from host appearance, using the existing
  preference adapter and shared renderer contract.
- Preserve the current font, text case, radius, opacity and shadows of the
  affected component. There is no additional Nord palette, glass-surface rule,
  uppercase-label rule or monospace requirement to apply.
- Import reusable controls through `@hardcore/ui/primitives/*` and `cn` through
  `@hardcore/ui/utils`. The class-merging helper lives in
  [packages/ui/src/lib/utils.js](../../../../packages/ui/src/lib/utils.js).
  Keep existing host-specific controls when their appearance or behavior differs.

## Controls and interaction

Use the existing shared primitives and variants. Preserve their keyboard
navigation, focus styling, labels, disabled states and pointer behavior when
moving or wrapping them. Icon-only controls need an accessible name; use the
existing Lucide icons and tooltips. Status and error text must convey meaning
without relying only on color.

For CAD Inspector and theme-editor rows, follow
[settings-ui.md](../../../../packages/ui/docs/settings-ui.md). It defines the
existing row types, control widths, units, section structure and accessible
label conventions. Reuse those CAD controls inside the renderer instead of
adding a second settings layout.

Keep loading, empty and error states in their existing positions. Preserve
focus and dismissal behavior for menus and dialogs, and retain reduced-motion
handling for animated indicators. A visual cleanup must not remove feedback,
change a control's availability or alter selection and navigation behavior.

## Validation

Check the affected app and shared component in light and dark modes, at the
normal and narrow layouts, and with keyboard as well as pointer input. For CAD
changes, include the existing Inspector, toolbar, loading/error and preview
states; the [render checks](../../../../packages/ui/docs/render-types.md) cover
cross-format and theme behavior. Rebuild shared package output before checking
an app that consumes it, following the package README. Do not use a migration
or documentation update to change the styling baseline.
