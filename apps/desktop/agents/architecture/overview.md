# Architecture Overview

All paths are relative to `apps/emdash-desktop/`.

## Process Model

- `src/main/`: Electron main process — app lifecycle, RPC controllers, domain services, database, PTY orchestration, updater, SSH
- `src/entry/preload.ts`: minimal Electron bridge for the Wire port and file-path lookup
- `src/renderer/`: React composition shell and shared browser infrastructure
- `src/core/`: vertical slices with portable APIs, Node implementations, browser UI, contributions,
  and manifests

## Boot Sequence

`src/main/index.ts` → app lifecycle → IPC/RPC registration → window creation → renderer

- `index.ts` — Loads `.env`, normalizes PATH, initializes database, registers all wire controllers via `src/core/manifests/node/controllers.ts`, creates the main window.
- `src/core/manifests/node/controllers.ts` — Assembles the typed wire controllers from each feature's `node/wire-controller.ts`.
- `src/preload/index.ts` — Exposes `window.electronAPI` (`invoke`, `eventSend`, `eventOn`) via `contextBridge`.
- `src/renderer/lib/ipc.ts` — Creates the typed RPC client and event emitter used throughout the renderer.

## Build Tooling

- `electron.vite.config.ts` — electron-vite config for main, preload, and renderer builds.
- `vitest.config.ts` — Vitest config with five test projects: `node`, `main-db`, `fixtures`, `migrations`, and `browser` (Playwright-backed renderer tests).
- Single `tsconfig.json` (in `apps/emdash-desktop/`) for all app targets.

## Read Next

- Main process details: `main-process.md`
- Renderer details: `renderer.md`
- Shared modules and provider registry: `shared.md`
