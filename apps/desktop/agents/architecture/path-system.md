# Path System

`@emdash/core/primitives/path/api` is the source of truth for portable file identity and lexical
path operations. The detailed package docs live in
[`packages/core/docs/path/README.md`](../../packages/core/docs/path/README.md).

## Ownership

- `packages/core/src/path/` owns pure structured path primitives, resource URI
  encoding, and comparison keys.
- Desktop placement resolution owns repository and worktree location policy. It combines the target
  host's home directory from `files.getHomeDir`, desktop settings, per-project overrides, and UI
  input, then sends absolute paths to the host runtime.
- Repository destinations default to `~/emdash/repositories/<name>` with numeric suffix allocation.
  Worktree pools default to `~/emdash/worktrees/<repo-basename>-<hash8(repo-path)>`; the workspace
  planner adds the sanitized branch leaf.
- Runtime and app layers own host resolution, native string conversion,
  filesystem I/O, realpath checks, authorization, and persistence migrations.
- Renderer code should eventually prefer `ResourceUri` or structured refs over
  raw absolute strings, but existing consumers are not migrated by the foundation
  module.

## Representation Rules

- Use `HostFileRef` for a full file address on a host.
- Use `ScopedPath` for root-relative operations such as Git paths, watcher
  events, tree entries, and bulk calls.
- Use `ResourceUri` for serialized identity.
- Use `ResourceKey` for in-memory dedupe and maps.
- Use explicit `PathProfile` semantics instead of `node:path` behavior when
  interpreting cross-host paths.

## Future Adoption Map

- Core `files` path helpers can delegate lexical operations to
  `@emdash/core/primitives/path/api`.
- Desktop `RuntimePath` and SSH path helpers can become adapters around
  structured path parsing/formatting.
- Git models can represent repo-relative file coordinates as
  `PortableRelativePath`.
- fs-watch can normalize native events into `ScopedPath` before batching and
  coalescing.
- workspace-server schemas can move from documented string conventions to
  structured path schemas.
- Renderer tabs, tree nodes, Monaco models, comments, and view-state snapshots
  can migrate from raw path strings to `ResourceUri`.

Do not add filesystem I/O, `realpath()`, host registry state, or app-specific
authorization to `packages/core/src/path/`.
