# Renderer Patterns

All paths are relative to `apps/emdash-desktop/`.

## Feature `api/` Surfaces

A feature slice's `api/` directory is its contract with other slices, nothing more:

- `api/` holds the Wire contract, shared types, the domain client, and store interfaces + selectors
- Cross-slice UI flows through the contributions registries (`contributions/browser.ts`,
  aggregated by `src/core/manifests/browser/browser-contributions.ts`), never through `api/`
- React components never live under `api/`; they belong in `browser/`
  (enforced by the `emdash/no-tsx-in-api` lint rule; the shrink-only allowlist at repo-root
  `tooling/oxlint/allowlists/api-surfaces.json` is empty and must stay that way)

## Modal System

Modals are renderer-only feature contributions. They render as a stack, with only the top modal
responding to outside presses and close commands.

- `src/core/primitives/modals/react/` — modal definitions, catalog types, host context, the modal
  store (`modal-store.ts` — active modal state and promise outcomes), and the close-guard hook
  (`use-close-guard.ts`)
- `src/core/features/*/contributions/browser.ts` — feature-owned `modalDefs`
- `src/core/manifests/browser/modal-catalog.ts` — application modal catalog
- `src/core/manifests/browser/modal-api.ts` — catalog-bound `openModal`, `useOpenModal`, and
  `useModalController`
- `src/renderer/lib/modal/modal-renderer.tsx` — resolves and renders the active catalog definition

**Adding a modal:**
1. Create the component in its feature slice. Caller data is ordinary component props; completion
   uses `useModalController(id)`.
2. Define it with `defineModal<TResult>()({ id, component, ...chrome })`.
3. Add the definition to the owning slice's `modalDefs`.
4. Open it through the typed API and branch on the outcome:

```tsx
const openMyModal = useOpenModal('myModal');
const outcome = await openMyModal({ projectId: '123' });
if (outcome.success) {
  useResult(outcome.data);
}
```

**Rules:**
- The manifest catalog is the only runtime registry; do not add renderer-local registrations
- Keep the catalog import type-only outside runtime resolution points
- Use standalone `openModal` outside React and `useOpenModal` inside components
- Use `useCloseGuard` during critical operations that must block passive dismissal
- `useModalController` exposes `hasActiveCloseGuard` when modal UI must reflect guard state
- Use `outcome.error.reason` when a chained flow must distinguish explicit back/cancel actions from
  passive or navigation dismissal

## View System

Views use a contributions + catalog + parameterized navigation pattern.

- `src/core/primitives/views/` — `defineView` (schema-backed view definitions with `params`,
  `layout`, and optional `historyKey`) and the React runtime bindings (`registerViewRuntime`,
  which binds slots such as `MainPanel`, `WrapView`, and `TitlebarSlot`)
- `src/core/features/*/contributions/views.ts` — feature-owned view definitions
- `src/core/manifests/browser/view-catalog.ts` — the aggregated application view catalog
- `src/core/primitives/navigation/` — the navigation engine: `NavigationStore` and
  `NavigationHistoryStore` (app-scoped), `getNavigation()` selectors, and React hooks
  (`useNavigate`, `useViewParams`, `useCurrentViewParams`); the renderer bootstrap seeds the
  catalog through `seedRendererNavigationHost()` before the app scope creates the stores
- `src/core/primitives/layouts/react/layout-provider.tsx` — workspace chrome context: reads
  the per-project workspace chrome command store and exposes the layout-storage facade

**Key behaviors:**
- Calling a view definition is the only way to construct a `ViewRef`
  (`taskViewDef({ projectId, taskId })`); the schema validates params at construction, and
  `safeRef()` is the boundary for untrusted values
- `navigate(ref)` (from `useNavigate`) takes a `ViewRef`; definitions whose params are all
  optional can be called without an argument
- Params persist per-view (`useViewParams(def)` returns the current or last-recorded params);
  `useCurrentViewParams(def)` also returns `setParams` for updating the active view's params

**Rules:**
- Views without a `historyKey` are singleton history places; `historyKey` splits history per
  entity (for example per task)
- Add new views through the owning slice's `contributions/views.ts` and register them in
  `src/core/manifests/browser/view-catalog.ts`

## Workbench Layout State

Workbench layout follows a strict ownership model (see
`.scratch/workbench-state-architecture/spec.md` history for rationale):

- **Chrome state lives in command stores, one per subject.** Task chrome
  (`sidebarCollapsed`, `sidebarTab`, `terminalDrawerOpen`) and workspace chrome
  (`leftSidebarOpen`, `zen`) are memento-backed state objects mutated only through
  named commands (`toggleSidebar`, `openSidebarTab`, `enterZenMode`, ...) — never
  through field setters. The shared mechanism is `defineChromeStore` in
  `src/core/primitives/chrome-stores/`.
- **Panel visibility is store-driven conditional rendering, never programmatic panel
  writes.** Closed = unmounted. Collapsible surfaces bind through
  `useCollapsiblePanelBinding` from `@emdash/ui` (next to `Resizable`), which turns
  drag-below-threshold into a semantic close command. No `panel.collapse()` /
  `expand()` / `resize()` / `setLayout()` calls exist in app code, and no
  `display:none` toggling of workbench surfaces.
- **Pixel sizes belong to react-resizable-panels alone**, persisted via
  `useResizableDefaultLayout` with a memento-backed `LayoutStorage` facade
  (`createLayoutStorage` in `src/core/primitives/mementos/browser/`). Sizes are never
  MobX observables and never persisted to localStorage.
- **Persisted view state renders below a hydration gate.** The task view gates on
  `space.isHydrated`; the storage facade dev-asserts on reads before hydration.

## PTY Frontend (`src/core/features/terminals/`)

The PTY frontend is owned by the terminals slice:

- `api/browser/pty/pty.ts` — `FrontendPty` class; subscribing fetches the main-process ring
  buffer and registers the consumer in one synchronous tick, so there is no renderer-side buffer
  and no missed output
- `api/browser/pty/pty-session.ts` — session lifecycle
- `api/browser/pty/prompt-injection.ts` — prompt injection
- `browser/pty/pty-pool-provider.tsx` — `TerminalPoolProvider` managing reusable xterm.js
  instances
- `contributions/browser/pty/pty-pane.tsx` — terminal pane component
- `browser/pty/pty-input-buffer.ts`, `browser/pty/pty-keybindings.ts`,
  `browser/pty/pty-clipboard.ts` — input handling

**Rules:**
- Historical output comes from the main-process ring buffer; do not add renderer-side buffering
- `sessionId` format: `makePtySessionId(projectId, scopeId, leafId)` from
  `src/core/primitives/pty/api/pty-session-id.ts` — deterministic

## React Query Context Pattern

Context providers use React Query for data fetching with optimistic updates:

```tsx
// Pattern used in the settings slice (useAppSettingsKey) and similar providers.
// Fetching goes through the owning slice's domain client.
const { data } = useQuery({
  queryKey: ['resource'],
  queryFn: async () => (await getExampleClient()).get(),
});
const mutation = useMutation({
  mutationFn: async (args) => (await getExampleClient()).update(args),
  onMutate: async (args) => {
    // optimistic update via queryClient.setQueryData
  },
  onError: () => {
    // rollback via queryClient.setQueryData with previous snapshot
  },
});
```

**Rules:**
- Contexts combine React Query + local state, not standalone useState
- Use `useAppSettingsKey(key)` for fine-grained per-setting hooks
- Optimistic updates must include rollback on error

## State Outside React

For state that must survive React unmounts or be shared across unrelated components:

- **App-scoped stores** — app-lifetime stores are slice-owned and ride the scoped-store
  mechanism: `createAppScope()` (`src/core/primitives/scoped-stores/browser/`) builds them at
  bootstrap from the contributions aggregated in
  `src/core/manifests/browser/app-scoped-stores.ts`; access them through per-slice typed
  selectors (for example `getNavigation()` from
  `src/core/primitives/navigation/browser/navigation-selectors.ts`)
- **`useSyncExternalStore`-compatible stores** — e.g., the memento hooks in
  `src/core/primitives/mementos/react/` and the layout-storage facade in
  `src/core/primitives/mementos/browser/`
- **MobX task and project stores** — slice-owned; access them through selectors
  (`src/core/features/tasks/api/browser/task-state/task-selectors.ts`,
  `src/core/features/projects/api/browser/stores/project-selectors.ts`) and task view hooks,
  never directly
