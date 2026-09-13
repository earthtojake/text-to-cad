# Quickstart

## Toolchain

- Only prerequisite: any `pnpm` on PATH. The root `package.json` pins
  `packageManager: pnpm@10.28.2` and `devEngines.runtime` node `24.14.0` with
  `onFail: "download"`, so `pnpm install` provisions the pinned pnpm and Node
  itself (no nvm or corepack needed).
- Optional: the committed `mise.toml` pins node + pnpm for mise users; `.nvmrc`
  remains as a compatibility hint.
- Workspace layout: pnpm monorepo; the Electron app lives in `apps/emdash-desktop/`

## Core Commands

Run from `apps/emdash-desktop/` (the root `package.json` also provides `dev` and `build`
aggregates that run through Nx in dependency order):

```bash
pnpm run dev
pnpm run dev:main
pnpm run dev:renderer
pnpm run build
pnpm run rebuild
pnpm run reset
```

## Validation Commands

Run from the repo root (they fan out to the workspace) or from `apps/emdash-desktop/`:

```bash
pnpm run format
pnpm run lint
pnpm run typecheck
pnpm run test
```

## Important Notes

- After native dependency changes (`better-sqlite3`, `node-pty`), run `pnpm run rebuild`.
- There are no pre-commit hooks; run the validation commands before opening or merging a PR.
