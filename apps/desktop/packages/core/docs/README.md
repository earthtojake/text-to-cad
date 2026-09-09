# @emdash/core Docs

`@emdash/core` contains transport-agnostic primitives shared by the desktop app,
workspace server, worker processes, and provider runtimes.

## Public Exports

- [`@emdash/core/primitives/path/api`](path/README.md) - pure host-aware path identity,
  normalization, resource URI, and comparison helpers.

## Boundaries

Core package docs describe reusable primitives. App-specific wiring, persistence
migrations, Electron IPC, and host runtime ownership stay in the app or workspace
server packages that own those concerns.
