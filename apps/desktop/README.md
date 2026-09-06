# Hardcore

The desktop client: projects on the left, one agent session in the middle, an
explorer on the right that renders code, browsers, terminals, reviews and every
file type the CAD Viewer understands. cadgen and the CAD skills ship inside the
app, pinned to its own version, and every session runs with them.

Electron 40 · electron-vite · React 19 · TypeScript · Tailwind v4 ·
shadcn/ui (stock neutral) · Vercel AI Elements · `@agentclientprotocol/sdk`.

A standalone npm project, like `apps/viewer` — there is no root `package.json`,
so every command below runs from `apps/desktop` (or with
`npm --prefix apps/desktop`).

## Dev

```sh
npm install          # postinstall rebuilds better-sqlite3 and node-pty for Electron
npm run dev          # electron-vite dev: main, preload and the renderer, with HMR
```

The repo's `.claude/launch.json` has a `desktop-dev` entry that runs the same
thing. The Browser pane cannot show an Electron window — visual checks go
through computer-use `app_screenshot` on the Hardcore window, or through the
Playwright screenshots below.

Two environment variables matter in development:

| Variable | Effect |
| --- | --- |
| `HARDCORE_APTABASE_KEY` | Enables telemetry (still gated on the user's own setting, which defaults to off). Unset means no network call is ever attempted. |
| `CAD_DESKTOP_PYTHON` | P5: use a checkout's `.venv` instead of the managed Python runtime. |

## Checks

```sh
npm run typecheck    # tsc over both projects: node (main/preload/shared) and web (renderer)
npm test             # vitest: tests/unit/{main,shared} in node, tests/unit/renderer in jsdom
npm run lint         # eslint flat config
npm run build        # electron-vite build -> out/
npm run e2e          # playwright _electron against out/ — run `npm run build` first
```

`npm run e2e` writes `tests/e2e/__screenshots__/`: the shell in both themes,
Settings, and one per explorer surface — `file-markdown-preview`,
`file-markdown-source`, `file-image`, `file-cad-placeholder`, `terminal`,
`browser-empty`, `browser`, `review`, `strip`, `expanded` and
`explorer-light`. Look at them; they are the cheapest review of whether the
app still looks like an app, and every defect found in P3's explorer — a tree
that did not reveal the open file, a `+` that scrolled out of reach, a
terminal that replayed its scrollback twice — was found by reading one.

The explorer suite opens **this repository** as its project, on purpose: a
fixture of six files would pass while the tree ignored nothing and the watcher
took ten seconds to start.

Nothing in `npm test` loads `better-sqlite3` or `node-pty`: both are built
against Electron's ABI and will not load in a plain Node process. The migration
runner takes a structural `MigrationDb` so it can be tested anyway; everything
else that needs a real database belongs in the e2e.

## Packaging

```sh
npm run icons        # regenerate build/icon.png (committed)
npm run package:mac  # or :win, :linux -> release/
```

`electron-builder.yml` holds the config: appId `dev.texttocad.hardcore`, mac
dmg + zip for arm64 and x64 (unsigned for now), Windows nsis x64, Linux
AppImage. `scripts/package.mjs` builds first and then stamps the repository's
`VERSION` onto the app as `extraMetadata.version` — `package.json` stays at
`0.0.0` because `VERSION` is the one canonical release version (AGENTS.md).
electron-builder derives the `.icns` and `.ico` from the single
`build/icon.png`.

## Layout

```
electron.vite.config.ts   main / preload / renderer, path aliases, the viewer's JSX-in-.js loader
electron-builder.yml      packaging and the GitHub Releases updater feed
tsconfig.node.json        main + preload + shared + node-side tests
tsconfig.web.json         renderer + renderer tests
src/main/                 the Electron main process: everything with a side effect
  index.ts                window, single-instance lock, lifecycle
  menu.ts                 app menu; View items send `ui.command` rather than reaching into the UI
  window-state.ts         persisted geometry, checked against the displays that exist now
  telemetry.ts            Aptabase, inert without a key and off without the setting
  updater.ts              electron-updater against GitHub Releases; a no-op in dev
  db/                     sqlite: migrations.ts (runner + schema), repositories.ts (rows <-> types)
  ipc/                    register.ts (validating registration), index.ts (the
                          handlers), explorer.ts and cad.ts (a phase's branch)
  agents/ acp/            P1
  explorer/               fs.ts (tree, ignores, read/write, chokidar watcher),
                          terminal.ts (node-pty sessions + scrollback)
  cad/                    P4, P5
  projects/git.ts         status, per-file diff and commit (P7 adds the modes
                          and worktrees)
src/preload/index.ts      the contextBridge: builds `window.hardcore` by walking the contract
src/shared/               types.ts (domain types as zod schemas)
  ipc/index.ts            the contract, assembled
  ipc/invoke.ts           the vocabulary a branch file needs, cycle-free
  ipc/explorer.ts         explorer.* terminal.* git.* and their events
  ipc/cad.ts              cad.viewerOrigin — P3's stub, P5's implementation
src/renderer/
  app/                    Shell (three resizable panes), App, CommandPalette
  features/sidebar        projects and their sessions
  features/session        the empty state and the composer
  features/explorer       the one tab strip and its four kinds of tab
  features/settings       the full-window Settings route and its seven pages
  components/ui           shadcn/ui, vendored
  components/ai-elements  Vercel AI Elements, vendored (types.ts replaces the `ai` package)
  state/                  one zustand store per domain, plus bridge.ts for main's pushes
  styles/globals.css      stock shadcn neutral tokens — the same ones apps/viewer uses
tests/unit/               vitest
tests/e2e/                playwright, against the built app
```

## How a change moves through the app

Adding an IPC channel is the shape of most work here:

1. declare it in `src/shared/ipc/` with its request and response schemas — a
   phase's branch is its own file there, spread into the map in `index.ts`;
2. implement it in `src/main/ipc/` — one file per branch, spread into the
   handler object in `index.ts`. `registerIpc` refuses to start if a channel
   has no handler;
3. call `window.hardcore.<branch>.<name>(...)` from a store in
   `src/renderer/state/`.

The preload needs no edit: it builds the client from the contract. Components
read stores, never IPC, so a change pushed from the menu or another window
lands in the same place a click would.

## Notes for later phases

- The renderer's Tailwind tokens are stock shadcn neutral, identical to
  `apps/viewer`'s, so P4's `CadFileView` inherits them instead of bringing a
  second theme.
- The CAD Viewer's `./file-view` entry is compiled from source by this app's
  bundler, so `electron.vite.config.ts` and `styles/globals.css` carry what
  `apps/viewer/docs/file-view.md` asks for: the scoped JSX-in-`.js` plugin,
  the `@` / `cadgen-js` / `three` aliases, `worker: { format: "es" }`, a dev
  `server.fs.allow`, the `@source` line, and the viewer's own `--ui-*` /
  `--surface-*` token block copied verbatim into both `:root` and `.dark`.
  `features/explorer/renderers/CadRenderer.tsx` imports it lazily — the
  closure is three.js and the whole viewer client, and a window that only
  opens a README should not pay for it at startup.
- `src/renderer/components/ai-elements/types.ts` holds local copies of the
  handful of types those components take from Vercel's `ai` package. All twelve
  imports were `import type`, so the package is not a dependency. Re-vendoring a
  component means repointing its `from "ai"` import at `./types`.
- P3 added exactly two dependencies, both pinned exactly: `ignore` (main —
  `.gitignore` semantics for the file tree, rather than a hand-rolled matcher
  that would disagree with git) and `@xterm/addon-web-links` (renderer — a URL
  a build prints opens in the person's browser).
- Monaco's five workers are imported as `monaco-editor/editor/editor.worker`,
  **not** `monaco-editor/esm/vs/editor/editor.worker`. Since 0.5x the package
  has an exports map whose `"./*"` already points at `./esm/vs/*.js`, so the
  older deep path resolves to `esm/vs/esm/vs/…` and the build fails with a
  message that names the file rather than the map.
