# Which UI Kit

The desktop app has exactly one component kit: **`@emdash/ui`** (`packages/ui`). The
legacy Tailwind/cva kit that lived at `apps/emdash-desktop/src/core/primitives/ui/browser/`
was deleted by the UI-kit unification migration — do not reintroduce it or shim to its
old APIs.

## Rules

- **Components come from `@emdash/ui`.** Buttons, dialogs, fields, inputs, selects,
  menus, tooltips, toasts, tabs, markdown, time display — import them from `@emdash/ui`.
  Do not hand-build a styled equivalent in feature code.
- **Feature-local Tailwind is for layout one-offs only.** Flex/grid/gap/padding/typography
  utilities in feature `browser/` code are fine until the separate future Tailwind-removal
  effort. Do not use Tailwind to build new reusable styled components.
- **New generic primitives go in `packages/ui`,** styled with vanilla-extract recipes and
  base-ui patterns per [UI styling conventions](ui-styling.md). Storybook stories covering
  variants and states are mandatory for every new or extended component.
- **App-specific components live in their owning feature slice** under
  `src/core/features/<feature>/browser/` (or the owning service/primitive), composed from
  `@emdash/ui` primitives. Only promote to `packages/ui` when a component is genuinely
  app-agnostic.
- **`cn()` lives at `src/core/primitives/styling/browser/cn.ts`**
  (`@core/primitives/styling/browser/cn`). It is the only sanctioned class-merging helper
  app-side; `packages/ui` does not use it.

## Choosing a popup control

- **`Select`** is for a short, bounded set of mutually exclusive values. Its popup is detached
  from the trigger and sizes to at least the trigger by default. Use `width="trigger"` when a
  form control should keep an exact column width. Avoid `alignItemWithTrigger`; it makes the
  selected row overlap the trigger and is reserved for a deliberately native-select-like
  interaction.
- **`Combobox` / `ComboboxPopover`** is for searchable or potentially large collections of
  entities such as agents, branches, remotes, machines, models, and working copies. Prefer the
  composed `ComboboxPopover` when its trigger/list/footer API is sufficient. Use
  `width="content-at-least-trigger"` when rows contain useful secondary metadata that needs more
  room than the trigger.
- **`DropdownMenu`** is for commands and actions, not choosing a persisted value. Radio and
  checkbox items are appropriate when an action menu also exposes a current preference.
- **`ContextMenu`** is the right-click variant of an action menu.
- **`Popover`** is for arbitrary interactive content that is not fundamentally a list of choices
  or commands.
- **`SplitButton`** is for a primary action with a menu of alternative actions.
- **`ComboboxPopup`** is for inline text completion anchored to an editor or input caret, such as
  mentions and slash commands.

Popup width is an explicit content decision rather than a positioning side effect. `Select`,
`Combobox`, and `DropdownMenu` content support `trigger`, `content`, and
`content-at-least-trigger` widths.

## Page-level lists

A page-level list of records is a **`CollectionView`**
(`packages/ui/src/react/patterns/collection-view/`), full stop. Card grids, trees
(`TreeView`), sidebars, popup pickers, and changed-files lists are different patterns.
The reference renderings are the stories in
`packages/ui/src/react/patterns/collection-view/collection-view.stories.tsx`; the full
locked spec lives with the unify-list-views effort.

- **One shell, two row styles**: every list is the same rounded card surface with soft
  dividers, hover/selected states, and always-on virtualization. Row content is either
  tabular `columns` (`CollectionViewColumn[]`, with `CollectionViewCell` for two-line
  text cells) or freeform `renderRow` — exactly one of the two. There is no header row.
- **State is opt-in**: pass `view` (a `createListView` instance, rendered inside its
  `Root`) for search/filter/sort/sections/selection/pagination, or plain `items` +
  `getItemKey` when no state layer is needed. Selection, sections, and loading/error
  status auto-wire in view mode; `renderSectionHeader` overrides the default
  label+count section header (for select-all headers and the like).
- **Density** is a two-value axis: `default` (60px estimate) or `compact` (36px).
  Taller measured content overrides via `estimateSize`; per-surface pixel tweaking is
  not a thing.
- **Toolbar and footer are slots**: put a `CollectionToolbar` (unchanged API) in
  `toolbar`; floating bulk bars and banners built on `ListPopoverCard` go in `footer`.
- **Sorting UI** is the shared `SortSelect` bound to `view.useSort()` — sort keys and
  labels live in the sort spec, never re-declared in the UI.
- **Multi-select mechanics are framework-given** (modifier-click toggle, shift-range);
  the default presentation is a hover-revealed leading checkbox column plus a floating
  `ListPopoverCard` bulk bar. Row click opens the item and never mutates.
- **Row actions are tiered**: context menu for the full set, trailing ellipsis menu for
  discoverability on management tables, hover buttons for at most 1–2 high-frequency
  actions. Destructive actions go last, separated, destructive-styled, with a confirm
  modal when irreversible.
- **An empty state is mandatory** (`EmptyState` is the default content; rich
  interactive empty states are allowed); `Spinner` is the loading default. Custom
  `EmptyState` slot content must pass `bare` — the card paints its own surface, so
  the component's panel background would patch over it.
- **Query-backed lists use `useQueryListSource`**: when the data comes from React
  Query, bridge the query result into the view with
  `useQueryListSource(query, buildItems)` (an `external` list source) instead of
  `observable.box` bridges or hand-rolled loading/error branches. Routing is then
  framework-owned: `loading` + no rows → `loadingSlot`; `error` + no rows →
  `errorSlot`; rows present → rows render even during refetch or on refetch failure
  (stale rows stay, silently — surfaces that must announce a refetch failure add
  their own `footer` banner); no rows and idle → `emptySlot`. The toolbar is always
  visible, including while loading. `reload()` is a no-op for these views — refetch
  through the query owner.
- **Removed**: `ColumnList` and `ListPage` no longer exist — `CollectionView` replaced
  both (its `columns`/`CollectionViewColumn`/`CollectionViewCell` vocabulary is the
  former `ColumnList` shape). Raw `ListView` chrome remains exported as an internal
  escape hatch for surfaces that cannot fit the shell (for example the workbench
  sidebar lists); it is not a pattern for new page surfaces.

## Settings pages

Settings pages follow one canonical anatomy, built from the settings pattern family in
`@emdash/ui/react/patterns`. The reference rendering is the "Page anatomy" story in
`packages/ui/src/react/patterns/settings/settings.stories.tsx`.

- **Header**: every settings page starts with `PageLayout.Header sticky` with a `title`
  and a `description`. If the page needs an Electron window drag region, use its
  `draggable` prop; do not hand-roll `WebkitAppRegion` divs.
- **Section stack**: the page owns the spacing between sections (a vertical stack with
  `space-y-8` or equivalent). Sections do not space themselves.
- **Sections**: each group of settings is a `SettingsSection`. The optional `title`
  renders the inset level-3 heading; children are wrapped in `SettingsCard` +
  `SeparatedList` (row gap via `gap`, default `1rem`). Content that brings its own
  surface — a custom card component, a tile grid — uses the `bare` prop and renders its
  surface itself. Do not compose raw `h3` headings or ad-hoc bordered divs.
- **Rows**: each setting is a `SettingsRow` (label, optional description, right-aligned
  control). The desktop app's local `SettingRow` wrapper (settings feature slice) adapts
  the `title` prop name; either is fine app-side. Controls come from `@emdash/ui`
  primitives (`Switch`, `Select`, `Input`, `Button`, …).
- **Tile pickers**: a small set of visual, mutually exclusive choices rendered as tiles
  (for example the color mode switcher) uses `SelectableCard` per tile inside a `bare`
  section — not hand-rolled `<button>`s.
- **Registration**: pages are contributed with `defineSettingsPageContribution` and
  aggregated in `src/core/manifests/browser/settings-page-contributions.ts`; the anatomy
  above applies to slice-contributed settings pages too.

## Theming

- `@emdash/ui` components are themed by `--em-*` tokens generated by `@emdash/theme`
  and loaded via `@emdash/ui/style.css`.
- Theme switching keys off the shared `emlight`/`emdark` class names; the app mounts the
  `@emdash/ui` `ThemeProvider` so `useTheme` works app-wide.
- App chrome tokens (`--background`, `--foreground`, …) live in
  `apps/emdash-desktop/src/renderer/index.css` and mirror the generated palette so chrome
  and `@emdash/ui` components render identically. Extend tokens there only for app chrome;
  component-level colors belong in `packages/ui` recipes.
- Markdown math rendering requires the host to load `katex/dist/katex.min.css`; the app
  does this in `src/renderer/main.tsx`.
