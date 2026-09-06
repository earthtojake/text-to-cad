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

Unlike `apps/viewer`, a worktree cannot borrow another checkout's
`node_modules` through a symlink: electron-builder resolves the dependency tree
by real path, and a `node_modules` that lives outside the project resolves every
transitive dependency to `undefined`. The build still succeeds; the app it
produces dies at launch on a missing module. Run `npm ci` here.

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
| `HARDCORE_APTABASE_KEY` | Read at BUILD time and compiled in (see Telemetry). Unset means no network call is ever attempted. |
| `CAD_DESKTOP_PYTHON` | P5: use a checkout's `.venv` instead of the managed Python runtime. |

## Telemetry

Anonymous counts through Aptabase, and only when two separate things are true:
a key was compiled in (`HARDCORE_APTABASE_KEY` at build time, baked in as
`__APTABASE_KEY__` by `electron.vite.config.ts` — a packaged app has no build
environment to read, and a key settable by whoever launches the binary is a key
anyone can point at their own project), and the user's `telemetry` setting is
on. That setting is on with an opt-out (plan §14) and is read per event, so
turning it off in Settings › General stops the next one, not the next launch —
and Settings prints the table below beside the switch rather than linking to
it.

Four events, and the union type in `src/main/telemetry.ts` is the whole
vocabulary — adding a fifth is a change to that type:

| Event | Property |
| --- | --- |
| `app_launched` | — |
| `session_created` | `agent` — the registry id (`claude-code`, `codex`, …) |
| `file_opened` | `extension` — `step`, `md`, `py`, … |
| `settings_changed` | `key` — the settings field's name, never its value |

Aptabase adds the app version, the OS and a per-install random id. Nothing here
carries a path, a file name, a project name, a prompt, or an agent's output.

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
npm run icons        # regenerate build/icon.{png,icns,ico} (committed)
npm run package:mac  # or :win, :linux -> release/
```

`electron-builder.yml` holds the config: appId `dev.texttocad.hardcore`, and
every artifact named `Hardcore-<version>-<os>-<arch>.<ext>`.

| Platform | Targets |
| --- | --- |
| macOS | dmg + zip, arm64 and x64 |
| Windows | nsis x64 (`…-windows-x64-setup.exe`) |
| Linux | AppImage + deb, x64, best-effort |

`scripts/package.mjs` is the way in. It builds first, then stamps the
repository's `VERSION` onto the app as `extraMetadata.version` — `package.json`
stays at `0.0.0` because `VERSION` is the one canonical release version
(AGENTS.md) — and passes anything else through to electron-builder, so
`npm run package:mac -- --arm64 --x64` works.

`npm run icons` writes all three icons from one script: no image toolchain, no
binary assets, and changing the mark is a diff.

### Signing

Decided by the environment and nothing else. There is no signed/unsigned pair
of configs to keep in step — the secrets are there or they are not:

| Set | Result |
| --- | --- |
| nothing | unsigned; `CSC_IDENTITY_AUTO_DISCOVERY=false`, so a certificate in your keychain cannot quietly change the artifact |
| `CSC_LINK`, `CSC_KEY_PASSWORD` | signed |
| …plus `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`, `APPLE_TEAM_ID` | signed and notarised |

`hardenedRuntime` and the entitlements (`build/entitlements.mac*.plist`) are on
either way, so the first signed build is not the first time they are exercised.

### Updates

`electron-updater` against the GitHub Releases of `earthtojake/text-to-cad` —
the same Release the repo tags, which is where `release-publish.yml`'s `desktop`
job attaches the installers. `src/main/updater.ts` checks ten seconds after
launch and every six hours, with `autoDownload` off: the app says an update
exists and downloads when asked. Settings › About & Updates is the whole UI.
Development builds report `unsupported` and check nothing.

### What is bundled

`resources/cadgen/` (the wheel) and `resources/plugin/` (the composed plugin)
ship beside the app as `extraResources`. Both are committed empty; P5 fills
them, and the release workflow drops the wheel it just built into the first.
See `resources/README.md`.

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
  settings-effects.ts     the settings that are instructions to the OS: login item, menu-bar
                          item, macOS vibrancy — applied at boot and on every settings write
  updater.ts              electron-updater against GitHub Releases; a no-op in dev
  db/                     sqlite: migrations.ts (runner + schema), repositories.ts (rows <-> types)
  ipc/                    register.ts (validating registration) + index.ts (the handlers)
  agents/                 registry.ts (the provider table), detect.ts (login-shell PATH, which,
                          versions, auth), shell-env.ts, install.ts + auth.ts (pty jobs via jobs.ts)
  acp/                    connection.ts (adapter process + SDK + stream tap + reducer),
                          client.ts (fs/terminal/permission), terminals.ts (+ pty/process backends),
                          sessions.ts (index + live connections)
  ipc/{acp,agents}.ts     the P1 handler branches, spread into ipc/index.ts
  ipc/{plugins,runtime}.ts  P6's branches, answering for P5 until it lands
  ipc/dialogs.ts          the native folder and file choosers Settings' path rows use
  explorer/               P3
  cad/                    P4, P5
  projects/git.ts         P7
src/preload/index.ts      the contextBridge: builds `window.hardcore` by walking the contract
src/shared/               types.ts (domain types as zod schemas)
  ipc.ts                  the contract: one branch per domain, assembled from ipc/
  ipc/define.ts           invoke / defineIpc and the types derived from a contract
  ipc/app.ts              the app.* branch: the updater's channels and its event
  ipc/acp.ts, ipc/agents.ts  the session and agent branches (P1)
  ipc/plugins.ts, ipc/runtime.ts, ipc/dialogs.ts  the plugin, CAD runtime and chooser branches (P6)
  agents.ts               provider and status schemas
  acp/types.ts, acp/reduce.ts  SessionState and the pure session/update reducer
src/renderer/
  app/                    Shell (three resizable panes), App, CommandPalette
  features/sidebar        projects and their sessions
  features/session        the empty state and the composer
  features/explorer       the one tab strip
  features/settings       the Settings route, the card-grouped rows, the agent drawer, and
                          pages/ — one module per page; search is done by the rows themselves
  lib/shortcuts.ts        the keyboard-shortcut table the Shortcuts page prints
  hooks/use-appearance.ts accent, UI scale, code font, reduced motion, translucency as <html> tokens
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

1. declare it in `src/shared/ipc/<branch>.ts` with its request and response
   schemas, and spread that module into `src/shared/ipc.ts` — one line, so
   several phases can add branches at once. Import `invoke` from
   `./define`, never from `../ipc`: the contract imports the branches, and
   importing it back is a cycle that fails at load time;
2. implement it in `src/main/ipc/<branch>.ts` and spread that into
   `src/main/ipc/index.ts` — `registerIpc` refuses to start if a channel has no
   handler;
3. call `window.hardcore.<branch>.<name>(...)` from a store in
   `src/renderer/state/`. Events go through `state/bridge.ts`, never through a
   listener in a component.

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
