# TypeScript And React Conventions

## TypeScript

- strict mode is enabled in `apps/emdash-desktop/tsconfig.json`
- always use explicit types, do not use `any`
- prefer module imports at the top of the file, never use require()
- single `tsconfig.json` (in `apps/emdash-desktop/`) for all app targets (main, preload, renderer, shared)

## Renderer

Paths are relative to `apps/emdash-desktop/`.

- functional React components and hooks
- app shell and the modal/view registries under `src/renderer/app/`
- feature UI under `src/core/features/<feature>/browser/`
- shared infrastructure under `src/renderer/lib/` (IPC client, modal and layout
  systems, commands, PTY frontend, providers, hooks, stores, UI primitives)

## Naming

- components: PascalCase
- hooks: `useX` camelCase or existing patterns like `use-toast.ts`
- tests: `*.test.ts`
