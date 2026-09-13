# Shared Modules

The desktop app no longer has a `src/shared/` directory. Shared code has an explicit owner under
`src/core/`:

- `src/core/primitives/<domain>/api/` contains portable vocabulary, schemas, and pure helpers.
- `src/core/features/<domain>/api/` contains feature Wire contracts.
- `src/core/features/<domain>/node/` contains main-process Wire controllers and event hosts.
- `src/core/features/<domain>/browser/` contains renderer stores, hooks, and UI.
- `src/core/features/<domain>/contributions/` exposes view, modal, tab, subject, and memento
  contributions.
- `src/core/services/` owns reusable active capabilities.
- `src/core/manifests/{shared,node,browser}/` are the application composition roots for portable
  contracts, main-process registries, and renderer contributions.

Renderer-main traffic uses Wire. The desktop contract is assembled in
`src/core/manifests/shared/desktop-wire-contract.ts`, served by
`src/main/gateway/desktop-wire.ts`, and consumed through per-slice typed domain clients built on
the seeded connection seam in `src/core/primitives/wire/browser/connection.ts` (the renderer
bootstrap seeds the connection once via `src/renderer/lib/runtime/seed-desktop-wire.ts`).
The shared manifest imports only slice API contracts. A drift test compares its keys and contract
references with the lazy Node controller registry in `src/core/manifests/node/controllers.ts`.

## Package Resolution

Workspace packages are consumed exclusively through their `package.json` `exports` maps. Every
`packages/*` package exposes a `development` condition pointing at `src/`; `dist` stays the
default, so dev and packaged builds resolve differently by design. `tsconfig.base.json` sets
`customConditions: ["development"]` so TypeScript follows the same resolution. There are no
`@emdash/*` path aliases in any tsconfig or Vite config.

Within `packages/core`, internal imports use `#`-prefixed subpath imports declared in its
`package.json` `imports` map (`#runtimes/*`, `#services/*`, `#primitives/*`).

App-internal aliases (`@/*`, `@core/*`, `@renderer/*`, `@main/*`, `@root/*`, `@tooling/*`) are
defined in `apps/emdash-desktop/tsconfig.json` and mirrored in its `electron.vite.config.ts`.

## Provider Metadata Rules

When adding a provider:

1. add or update its plugin in `packages/plugins/src/agents/impl/` and register it in
   `packages/plugins/src/agents/registry.ts`
2. add any required env passthrough in the provider's plugin definition
   (`packages/plugins/src/agents/impl/`); PTY env construction lives in
   `packages/core/src/services/pty/api/terminal-env.ts`
3. add or update hook/plugin installation and parsing in provider plugin behavior if the provider
   supports explicit events; the TUI runtime installs and hosts hooks
4. update renderer surfaces that consume agent metadata through their slice domain clients
5. add tests for non-standard spawn or detection behavior
