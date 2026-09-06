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

`npm run e2e` writes `tests/e2e/__screenshots__/shell.png` (plus `shell-dark`,
`shell-light` and `settings`). Look at them; they are the cheapest review of
whether the app still looks like an app.

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
  ipc/                    register.ts (validating registration) + index.ts (the handlers)
  agents/                 registry.ts (the provider table), detect.ts (login-shell PATH, which,
                          versions, auth), shell-env.ts, install.ts + auth.ts (pty jobs via jobs.ts)
  acp/                    connection.ts (adapter process + SDK + stream tap + reducer),
                          client.ts (fs/terminal/permission), terminals.ts (+ pty/process backends),
                          sessions.ts (index + live connections)
  ipc/{acp,agents}.ts     the P1 handler branches, spread into ipc/index.ts
  explorer/               P3
  cad/                    P4, P5
  projects/git.ts         P7
src/preload/index.ts      the contextBridge: builds `window.hardcore` by walking the contract
src/shared/               ipc.ts (the contract), ipc/define.ts (the helpers), ipc/{acp,agents}.ts
                          (P1's channels and events), types.ts (domain types as zod schemas),
                          agents.ts (provider/status schemas), acp/types.ts + acp/reduce.ts
                          (SessionState and the pure session/update reducer)
src/renderer/
  app/                    Shell (three resizable panes), App, CommandPalette
  features/sidebar        projects and their sessions
  features/session        the empty state and the composer
  features/explorer       the one tab strip
  features/settings       the full-window Settings route and its seven pages
  components/ui           shadcn/ui, vendored
  components/ai-elements  Vercel AI Elements, vendored (types.ts replaces the `ai` package)
  state/                  one zustand store per domain, plus bridge.ts for main's pushes
  styles/globals.css      stock shadcn neutral tokens — the same ones apps/viewer uses
tests/unit/               vitest
tests/e2e/                playwright, against the built app
tests/fake-agent/         a scripted ACP agent on stdio (SDK agent side), also replays fixtures
tests/fixtures/acp/       recorded adapter transcripts (jsonl), written by the harness
scripts/acp-harness.mjs   run a real ACP session from the terminal; --record writes a fixture
```

## ACP

Every session is one adapter process driven by `@agentclientprotocol/sdk`
(`src/main/acp/connection.ts`). The provider table in
`src/main/agents/registry.ts` says how each agent is launched, installed and
signed in; the detector probes the user's login-shell PATH for them.

```sh
node scripts/acp-harness.mjs codex /tmp/scratch "Reply with exactly: ok"
node scripts/acp-harness.mjs claude-code /tmp/scratch "Create hello.txt, then run ls" \
    --record tests/fixtures/acp/claude-code-session.jsonl
node scripts/acp-harness.mjs codex /tmp/scratch "What did we do?" --load <acpSessionId>
```

The harness runs the same `SessionConnection` main does (child_process
terminals instead of node-pty), prints every update, auto-answers permission
requests (`--approval ask` to answer by hand), and `--record` writes every
wire frame as jsonl. Those recordings are the reducer's test corpus
(`tests/unit/shared/reduce.test.ts`) and what `tests/fake-agent` replays for
the connection tests. Re-record after an adapter upgrade; never run the
harness against this repository, use a scratch directory.

Two things learned from the real adapters that the code now depends on:

- Both adapters accept the draft subagent capability and then send update
  kinds (`subagent_spawned`, `subagent_state_update`) that SDK 1.4.0's schema
  rejects. The connection reads every `session/update` raw off the wire and
  only forwards the kinds the SDK knows, so the reducer sees everything.
- A terminal started from inside a Claude Code session carries that session's
  environment (`CLAUDECODE`, `CLAUDE_CODE_*`, its `ANTHROPIC_BASE_URL`). A
  nested `claude` then reports itself logged out and the adapter answers
  `Authentication required`. `shell-env.ts` strips those when it sees the
  marker. The Claude fixture on this machine is the auth-failure exchange for
  that reason (`claude-code-auth-required.jsonl`); a machine with a signed-in
  `claude` (`claude auth status` → `loggedIn: true`) records a full session.

## How a change moves through the app

Adding an IPC channel is the shape of most work here:

1. declare it in your phase's file under `src/shared/ipc/` (or `src/shared/ipc.ts`
   for P0's branches) with its request and response schemas — a new file is
   one spread line in the contract and one in the event map;
2. implement it in the matching `src/main/ipc/<phase>.ts`, spread into
   `src/main/ipc/index.ts` — `registerIpc` refuses to start if a channel has
   no handler;
3. call `window.hardcore.<branch>.<name>(...)` from a store in
   `src/renderer/state/`.

The preload needs no edit: it builds the client from the contract. Components
read stores, never IPC, so a change pushed from the menu or another window
lands in the same place a click would.

## Notes for later phases

- The renderer's Tailwind tokens are stock shadcn neutral, identical to
  `apps/viewer`'s, so P4's `CadFileView` inherits them instead of bringing a
  second theme.
- `@viewer/*` resolves to `apps/viewer/src/client`, and a scoped Vite plugin
  runs the viewer's JSX-in-`.js` files through esbuild's `jsx` loader. Nothing
  imports it yet; the config is ready for P4.
- `src/renderer/components/ai-elements/types.ts` holds local copies of the
  handful of types those components take from Vercel's `ai` package. All twelve
  imports were `import type`, so the package is not a dependency. Re-vendoring a
  component means repointing its `from "ai"` import at `./types`.
