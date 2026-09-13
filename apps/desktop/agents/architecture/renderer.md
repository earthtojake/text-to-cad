# Renderer

All paths are relative to `apps/emdash-desktop/`.

## Main Entry Points

- `src/renderer/main.tsx`: renderer bootstrap — seeds the wire connection and navigation host,
  creates the app store scope, then mounts React
- `src/renderer/App.tsx`: top-level provider composition
- `src/renderer/app/workspace.tsx`: main post-onboarding shell
- `src/core/primitives/wire/browser/connection.ts`: seeded wire-connection seam
  (`seedWireConnection` / `getWireConnection` / `domainClient`); every slice exposes a typed
  domain client from its `api/` built on `domainClient`
- `src/core/manifests/browser/view-catalog.ts`: aggregated view catalog; view definitions are
  contributed by slices (`contributions/views.ts`) via `defineView` from
  `src/core/primitives/views/`

## App Shell (`src/renderer/app/`)

- `workspace.tsx`, `welcome.tsx` — shell and top-level views (the home view is workbench-owned:
  `src/core/features/workbench/browser/home-view.tsx`)
- `app-menu-events.tsx` — native app menu event wiring
- `app-shutdown-lifecycle.tsx` — quit-confirmation and shutdown-flush handling

Modal and view registration are manifest-owned, not shell-owned:
`src/core/manifests/browser/modal-catalog.ts` and `src/core/manifests/browser/view-catalog.ts`
aggregate slice contributions.

## Feature Areas (`src/core/features/*/browser/`)

Feature-owned React components, hooks, and MobX stores live beside their portable API and Node
implementation. Major browser slices include `tasks`, `projects`, `conversations`,
`browser`, `settings`, `skills`, `mcp`, and `library`. Workbench-owned tabs,
sidebar, command palette, and onboarding UI live under `src/core/features/workbench/browser/`.
Cross-slice task-view lifecycle and workspace composition live in
`src/core/features/workbench/api/browser/task-composition.ts` and
`src/core/features/workbench/browser/task-composition-state.ts`; task, project, and workspace
stores expose feature-owned children through scoped-store tokens.

Task children have two explicit lifetimes: lightweight persistent stores survive session teardown
for as long as the task row exists (`task-persistent-stores.ts`), while operational task stores are
disposed when the task session is torn down (`task-scoped-stores.ts`).

Feature views, modals, and task tabs are exposed through `contributions/` and aggregated by
`src/core/manifests/browser/browser-contributions.ts` and
`src/core/manifests/browser/task-tab-contributions.ts`.

The command palette uses the same static contribution model. Owning slices export
`PaletteProviderDef` arrays from `contributions/browser/`, and
`src/core/manifests/browser/palette-provider-catalog.ts` aggregates the five providers for
commands, tasks, conversations, files, and projects. The workbench modal only renders
`PaletteController` output. Argumentless commands opt in separately through
`CommandPaletteItemDef` contributions aggregated by
`src/core/manifests/shared/command-palette-catalog.ts`; command matching stays in the renderer,
while task, conversation, and project providers request kind-filtered candidates through the
search slice.

## Shared Renderer Infrastructure (`src/renderer/lib/`)

`src/renderer/lib/` is a thin host shell; portable browser infrastructure lives in
`src/core/primitives/`.

- `runtime/` — bootstrap seeding (`seed-desktop-wire.ts`, `seed-navigation-host.ts`) and the
  renderer-internal aggregate Wire client (`desktop-wire-client.ts`); slices use their own
  domain clients instead
- `modal/modal-renderer.tsx` — renders the active modal from the manifest catalog; modal
  definitions, store, and close guards live in `src/core/primitives/modals/react/`
- `layout/` — workspace layout and right-sidebar composition
- `keybindings/` — keybinding dispatcher mount and browser shortcut forwarding
- `stores/` — navigation telemetry wiring; app-lifetime stores are slice-owned and ride the app
  scope (`src/core/manifests/browser/app-scoped-stores.ts`)
- `providers/`, `hooks/` — shared providers and hooks (theme, feature flags, multi-select)

Navigation lives in `src/core/primitives/navigation/`; commands and the palette live in
`src/core/primitives/commands/`, `src/core/primitives/view-scopes/`, and
`src/core/primitives/palette/`. The PTY frontend is owned by the terminals slice
(`src/core/features/terminals/`). Monaco, file rendering, file-tree projection, and
renderer-facing file runtime access are owned by `src/core/features/editor/browser/`.

## Tests

- Renderer unit tests: `src/renderer/tests/`
- Playwright-backed browser tests: `src/renderer/tests/browser/`

## When Editing Here

- Check `agents/conventions/renderer-patterns.md` for modal, view, PTY frontend, and store patterns.
- Call renderer-main methods through the owning slice's typed domain client.
- Add feature views, modals, and task tabs through the owning slice's contributions.
- The preload bridge (`src/entry/preload.ts`) exposes only `requestWirePort` and
  `getPathForFile`; keep application traffic on Wire.
