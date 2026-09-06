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

Three environment variables matter in development:

| Variable | Effect |
| --- | --- |
| `HARDCORE_APTABASE_KEY` | Read at BUILD time and compiled in (see Telemetry). Unset means no network call is ever attempted. |
| `CAD_DESKTOP_PYTHON` | An interpreter with cadgen installed, used instead of the bundled runtime (see CAD runtime below). A developer's knob; the e2e suite breaks and clears the equivalent setting on purpose. |
| `HARDCORE_NO_PLUGIN_INSTALL` | Skip the launch-time install of the Hardcore plugin into the user's agents. `NODE_ENV=test` implies it. |
| `HARDCORE_FAKE_AGENT` | Launch this stdio ACP agent instead of whatever the registry says, for every provider. The session and git suites point it at `tests/fake-agent/index.mjs`; a session needs an agent to exist at all, and a real one would make the suite a test of somebody's login state. |

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
npm run build        # scripts/build.mjs: compose the plugin, electron-vite build -> out/, bundle the MCP server
npm run e2e          # playwright _electron against out/ — run `npm run build` first
```

`npm run build` is three steps in one script (`scripts/build.mjs`): the
Hardcore plugin is composed into `resources/plugin/` (`build:plugin`),
electron-vite builds main, preload and renderer into `out/`, and the MCP
server is bundled into `out/hardcore-mcp/` (`build:mcp`). Packaging runs the
same script. The renderer step compiles the CAD Viewer's client from source,
so `apps/viewer/node_modules` and `packages/cadgen-js/node_modules` have to
exist — in a worktree, symlink them from a checkout that has run `npm install`
in each (those two links are fine; only this app's own `node_modules` must be
real, see above).

`npm run e2e` writes `tests/e2e/__screenshots__/`: the shell in both themes,
Settings, one per explorer surface — `file-markdown-preview`,
`file-markdown-source`, `file-image`, `file-cad-failed` (the runtime broken
on purpose), `file-cad` (expanded), `file-cad-default` (the explorer at its default share, the tree
hidden for it) and both again at 1280×800, `file-cad-measure`, `terminal`,
`browser-empty`, `browser`, `review`, `strip`, `expanded` — every one of those
kinds in light as `*-light` — the `git-*` set for the git modes (the review
under three scopes, before and after a commit, the sidebar's worktree glyph,
Settings' per-project worktree card), the session states in both themes with
the composer at 1280×800 and 1680×1050, and `codex-open-file` from the one
test that runs a real agent (below). Look at them; they are the cheapest review of
whether the app still looks like an app, and every defect found in P3's
explorer — a tree that did not reveal the open file, a `+` that scrolled out
of reach, a terminal that replayed its scrollback twice — was found by reading
one. So were two of P7's: a session titled with a whole prompt scrolled the
sidebar sideways (Radix's scroll viewport wraps its children in a
`display: table` div, which sizes to content), and a worktree card's absolute
path ran under its own buttons.

The explorer suite opens **this repository** as its project, on purpose: a
fixture of six files would pass while the tree ignored nothing and the watcher
took ten seconds to start. The one exception is the review tab, which gets a
small repository built in `beforeAll` — reviewing this checkout made the
screenshot a function of the tree it is committed into, and it never
converged.

Two or three of the images still come back byte-different from a run that
changed nothing: a blinking cursor, a scroll position, when a font finished
rasterising. Commit them or discard them, but do not go looking for the change
— if the picture is the same, it is the same.

The session suite (`session-*.png`) drives the session UI through each of its
states with `tests/fake-agent` (`HARDCORE_FAKE_AGENT` points main at it in place
of every adapter); `codex.spec.ts` runs one real Codex session when
`HARDCORE_E2E_CODEX=1`. `keyboard.spec.ts` presses every shortcut the
Shortcuts page lists; `quit.spec.ts` times `app.quit()` with a repository
watched, a shell, a session and the CAD viewer all running, and fails above
two seconds (see Quitting, below). `persistence.spec.ts` launches the app
twice against one user-data directory — a project, a session with the fake
agent, `app.quit()`, relaunch — and asserts both come back and the session's
transcript resumes through `session/load`.

The CAD tests run against whatever runtime the app resolves on its own (see
CAD runtime, below): the bundled one once `npm run bundle:runtime` has run,
else the checkout's `.venv`. The explorer suite first breaks the runtime on
purpose — an override pointing nowhere — to see the failure card with the
interpreter's words in it, then clears the override and renders the STEP;
that render is skipped on a machine with no runtime at all (CI's test job,
which bundles nothing). The first render compiles the STEP in cadgen's build
pool and is the slow assertion of the suite.

`tests/e2e/codex-open-file.spec.ts` runs a real Codex session in a scratch
project and asks it to call `open_file`; it asserts the explorer opened the
tab and that the session recorded the tool call. It is skipped unless a
signed-in `codex` is on the machine (`codex login status`), so a runner
without one stays green. It is the only test that talks to a model.

Nothing in `npm test` loads `better-sqlite3` or `node-pty`: both are built
against Electron's ABI and will not load in a plain Node process. The migration
runner takes a structural `MigrationDb` so it can be tested anyway; everything
else that needs a real database belongs in the e2e.

## Packaging

```sh
npm run icons            # copy the docs favicon to build/icon.png (committed)
npm run cad:resources    # the cadgen wheel + constraints into resources/cadgen (from the .venv)
npm run bundle:runtime   # THE CAD RUNTIME into resources/runtime/<os>-<arch> (~1.2 GB, once per pin)
npm run package:mac      # or :win, :linux -> release/
```

`electron-builder.yml` holds the config: appId `dev.texttocad.hardcore`, and
every artifact named `Hardcore-<version>-<os>-<arch>.<ext>`. The runtime is
the product: `scripts/package.mjs` refuses to package a target whose runtime
is not under `resources/runtime/` at this version (`--no-runtime` to package
without one, for a build whose purpose is not CAD). `npm run package:mac`
with no arch flags builds arm64 and x64 and needs both runtimes;
`-- --arm64` builds and needs one (the script adds the config's target
names behind an arch flag, because electron-builder ignores a bare `--arm64`
when the config lists arches). Sizes measured on 0.5.0, mac-arm64: the
runtime is 1.24 GB on disk, the app 1.6 GB, the dmg 456 MB, the zip 468 MB
— and that is the point (plan §8, as revised): nothing downloads at first
launch.

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

`npm run icons` copies the docs site's favicon to `build/icon.png`; the mark lives
in one place and electron-builder derives the platform containers at package time.
An unpackaged app (`npm run dev`, `npx electron .`) runs inside Electron's own
binary and would show Electron's icon: main sets the Dock icon from that file
on macOS and passes it to the window on Windows and Linux when `!app.isPackaged`.

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

`resources/runtime/<os>-<arch>/` (the CAD runtime: a pinned Python with
cadgen and its whole closure installed), `resources/cadgen/` (the wheel and
its constraints) and `resources/plugin/` (the composed plugin) ship beside
the app as `extraResources`; all three are build outputs, gitignored under a
committed `.gitkeep`. `npm run build` fills the plugin; `npm run
cad:resources` fills the wheel directory from a checkout (the release
workflow drops the wheel it just built into it instead); `npm run
bundle:runtime` fills the runtime from those two (the release workflow runs
it per leg: macOS bundles `mac-arm64` natively and `mac-x64` cross, Windows
and Linux their own). The MCP server ships inside `out/hardcore-mcp/`,
unpacked from the asar so an agent can run it by path. See
`resources/README.md` for the bundler's steps, the cross-target rule and the
signing note.

## Layout

Three panes, in pixels (`PANE_LIMITS` in `src/shared/types.ts`, read by
`Shell.tsx`): a 230px sidebar (180–360), a session column of 560px by default
and never less — its transcript and composer are a 720px column centred in
it — and the explorer takes whatever is left. The two fixed widths are the
persisted preference (`settings.layout`); the explorer's is a consequence.
With the explorer collapsed the session fills the window. The strips along
the top are 32px, and whichever pane is leftmost makes room for the macOS
traffic lights (`--titlebar-inset`, keyed off `data-leftmost` on the shell).

A CAD file in the explorer is laid out by the desktop, not measured by the
viewer (`features/explorer/cad-layout.ts`): the surface is pinned to its
desktop layout with the sheet a column beside the model at any pane width,
the sheet is `clamp(36% of the pane, 240, 365)`, the file tree hides itself
for that tab when the pane cannot hold all three (its toggle brings it
back), and light/dark is the app's theme rather than the CAD theme's.

## Quitting

`app.quit()` has a budget of two seconds (`tests/e2e/quit.spec.ts`), and the
teardown in `before-quit` is written for it: every owner signals what it
owns and nothing is awaited. Electron waits for the Node side, and the Node
side waits for every child it holds a pipe to, so `src/main/children.ts`
registers every process main spawns — the viewer, the adapters, the
terminals' backends, the probes, `git` — and `before-quit` kills the probes
outright and detaches the rest; `will-quit` kills whatever ignored its
signal. Before that, a cadgen version probe (sixty-second timeout) still
importing OCP held the exit for sixty seconds, and chokidar's `close()` over
this repository blocked for most of a second, so the watchers are not closed
at all — an fsevents handle dies with the process.

What is left after `will-quit` is Chromium's own shutdown, which on this
macOS takes twelve seconds to minutes once a window has held a WebGL context
(the GPU and utility helpers hang, then the browser process retries a
CoreAnalytics XPC send; `app.exit()` is slower still, and no timer of ours
runs once the event loop has stopped). `src/main/quit-deadline.ts` keeps a
deadline from outside: a detached copy of this binary run as Node that
kills the app and its helpers 1.2 seconds after `will-quit` if they are
still there. A quit that finishes on its own — half a second without WebGL —
gives it nothing to do.

## CAD runtime

The runtime ships inside the app. Every cadgen process the app runs — the
viewer per project, the probe that reads the cadgen version — uses one
interpreter, resolved in this order (`src/main/cad/runtime.ts`):

1. `CAD_DESKTOP_PYTHON` in the environment, then the `cadPythonOverride`
   setting (no UI; a developer's and the e2e suite's knob);
2. the bundled runtime beside the app — `Resources/runtime/<os>-<arch>/` in
   a packaged app, `resources/runtime/<os>-<arch>/` in a checkout that has
   run `npm run bundle:runtime` — recognised by the `runtime.json` the
   bundler writes last;
3. a development checkout's `.venv` — the app is running from inside this
   repository (found by `VERSION` and `packages/cadgen/pyproject.toml` above
   it), which is what `npm run dev` has;
4. nothing: the status is *Missing* and says where it looked.

Inside a checkout, whichever interpreter wins runs with
`PYTHONPATH=<checkout>/packages/cadgen/src`, so the cadgen it imports is the
checkout's own — a `.venv` on a developer's machine points at one checkout
and the app may be running from a worktree of another. The bundled
interpreter runs closed to the shell's Python variables (`PYTHONHOME`,
`PYTHONPATH`, `PYTHONSTARTUP`, `PYTHONUSERBASE` dropped; `PYTHONNOUSERSITE`)
and with `PYTHONDONTWRITEBYTECODE`, because a signed bundle must not be
written into — its pycs were compiled by the bundler. Every cadgen process
also gets `CADGEN_NODE`: cadgen's DXF and mesh-export builders run in Node,
an app launched from the Finder has no `node` on its PATH, and the one Node
a packaged app is sure to have is its own Electron binary run as Node.

There is nothing to install and no "installing" state. Settings › About &
Updates carries a read-only block — the runtime (source and interpreter),
cadgen's version against the app's, the viewer backend, the Hardcore plugin
per installed agent — and Repair, which forgets the probe and looks again.
A CAD tab whose runtime did not start shows the interpreter's words, the
log (`userData/cad-runtime.log`: every failed probe, every viewer launch
that did not come up, the viewer's stderr) and Try again; it never asks the
person to set anything up.

`src/main/cad/viewer.ts` runs one `python -m cadgen.viewer --api-only --host
127.0.0.1 --json` per project root (cwd = the root, the launcher's contract),
parses its JSON line, keeps the child, restarts it on a crash with backoff,
stops it when the project is removed and on quit — and never kills an
instance the launcher reported as `reused`, because that one is somebody
else's. `cad.viewerOrigin` is how the file tab gets the origin.

## The plugin and the MCP server

Two things reach the agent from the app (plan §8), and `src/main/cad/`
owns both:

**The Hardcore plugin** — `resources/plugin/`, composed by
`scripts/build-plugin.mjs`: the repository's skills minus `cad-viewer` (the
viewer is beside the chat here) plus `skills/hardcore-app` (which replaces
the `cad` skill's `$cad-viewer` hand-off), with `.claude-plugin/plugin.json`,
`.claude-plugin/marketplace.json` and `.codex-plugin/plugin.json` naming the
plugin `cad`, the marketplace `hardcore` and the version the app's. Copies,
never symlinks. `src/main/cad/plugin.ts` installs it per agent, on first
launch and after every app update (`userData/plugin-installs.json` records
which version each agent has), and from the Agents drawer's Plugins block:

| Agent | Install | Read back |
| --- | --- | --- |
| Claude Code | `claude plugin marketplace add <resources/plugin>`, `claude plugin marketplace update hardcore`, `claude plugin install cad@hardcore` (then `claude plugin update cad@hardcore` when install says "already installed") — lands in `~/.claude/plugins/cache/hardcore/cad/<version>/` | `claude plugin list --json` |
| Codex | `codex plugin marketplace add <resources/plugin>`, `codex plugin add cad@hardcore` (idempotent) — `[marketplaces.hardcore]` in `~/.codex/config.toml`, files in `~/.codex/plugins/cache/hardcore/cad/<version>/` | `codex plugin list --json` |
| agents with only a skills directory | the skills copied to `<skillsDir>/hardcore/<skill>/` beside a `hardcore-plugin.json` version marker | that marker |

The user's other plugins and skills are never touched.

**The Hardcore MCP server** — `resources/hardcore-mcp/server.mjs`, a stdio
server on `@modelcontextprotocol/sdk` that every `session/new` carries
(`SessionManager.deps.mcpServers`). The agent spawns it — this app's own
Electron binary as Node (`ELECTRON_RUN_AS_NODE=1`), the source in a checkout,
the bundle in `out/hardcore-mcp/` when packaged — with a per-session token
and the session's cwd in its environment. Its tools: `open_file(path)`,
`reveal(path)`, `open_url(url)`, `list_open_tabs()`, `viewer_state()`,
`attach_snapshot(path)` (returned as image content, so the transcript shows
the PNG). Each call is one `POST /rpc` to `src/main/cad/mcp-bridge.ts`, a
loopback HTTP listener that refuses anything without a live session's
token; main resolves the path inside the session's project and relays the
explorer actions to the renderer as `cad.command`, which
`src/renderer/state/cad-commands.ts` performs against the stores and answers
on `cad.reply`. Snapshots are read in main. Neither adapter wants a `type`
field on a stdio entry: claude-agent-acp reads one as http/sse.

`tests/unit/main/{cad-runtime,viewer,plugin,build-plugin,mcp-server,mcp-bridge}.test.ts`
cover each piece with a fake machine, a fake child, a fake CLI, the real
build script into a temp directory, the SDK's client over an in-memory
transport, and the bridge over real loopback HTTP.

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
  ipc/{plugins,runtime}.ts  the plugin and CAD runtime branches (P5's bodies, P6's shape)
  ipc/dialogs.ts          the native folder and file choosers Settings' path rows use
  ipc/{explorer,cad}.ts   P3's handler branches: files, terminals; cad.viewerOrigin + cad.reply (P5)
  ipc/git.ts              P7's: the review's reads in a session's directory, the
                          commit, the pull request, and the worktree list
  explorer/               fs.ts (tree, ignores, read/write, chokidar watcher),
                          terminal.ts (node-pty sessions + scrollback)
  cad/                    runtime.ts (which Python: override, bundled, checkout), viewer.ts (one viewer per project root),
                          plugin.ts (the composed plugin into each agent), mcp-bridge.ts + actions.ts
                          (the MCP server's way into the explorer), index.ts (the wiring)
  projects/git.ts         status, per-file diff, commit and push; then repository
                          detection, worktrees, the keep-limit sweep and `gh pr create`
  projects/workspace.ts   a git mode as a directory: the three modes, the worktree
                          layout, and what a deleted session takes with it
src/preload/index.ts      the contextBridge: builds `window.hardcore` by walking the contract
src/shared/               types.ts (domain types as zod schemas)
  ipc/index.ts            the contract: one branch per domain, assembled from the files beside it
  ipc/define.ts           invoke / defineIpc and the types derived from a contract
  ipc/app.ts              the app.* branch: the updater's channels and its event
  ipc/acp.ts, ipc/agents.ts  the session and agent branches (P1)
  ipc/plugins.ts, ipc/runtime.ts, ipc/dialogs.ts  the plugin, CAD runtime and chooser branches (P6)
  agents.ts               provider and status schemas
  acp/types.ts, acp/reduce.ts  SessionState and the pure session/update reducer
  ipc/explorer.ts         explorer.* terminal.* and their events (P3)
  ipc/git.ts              git.* — the review's reads plus P7's worktrees
  ipc/cad.ts              cad.viewerOrigin, and cad.command / cad.reply for the MCP server
src/renderer/
  app/                    Shell (three resizable panes), App, CommandPalette
  features/sidebar        projects and their sessions (five per project, Show more, status glyphs, menus)
  features/session        the new-session state, the transcript, the composer
    view.ts               SessionState -> rows: activity-row labels, folding, the status line (pure)
    parts/                activity rows (+ Monaco diff, terminal), thoughts, permission cards, subagents
    ComposerChips.tsx     agent / project / git mode / approval / model / options chips
  features/explorer       the one tab strip and its four kinds of tab
  features/settings       the Settings route, the card-grouped rows, the agent drawer, and
                          pages/ — one module per page; search is done by the rows themselves
  lib/shortcuts.ts        the keyboard-shortcut table the Shortcuts page prints
  lib/git-mode.ts         the sidebar glyph, the composer chip's labels and which
                          modes a project can offer — one answer, two features
  hooks/use-appearance.ts accent, UI scale, code font, reduced motion, translucency as <html> tokens
  components/ui           shadcn/ui, vendored
  components/ai-elements  Vercel AI Elements, vendored (types.ts replaces the `ai` package)
  state/                  one zustand store per domain, plus bridge.ts for main's pushes and
                          cad-commands.ts for an agent's tool calls against the stores
  styles/globals.css      stock shadcn neutral tokens — the same ones apps/viewer uses
tests/unit/               vitest
tests/e2e/                playwright, against the built app
tests/fake-agent/         a scripted ACP agent on stdio (SDK agent side), also replays fixtures
tests/fixtures/acp/       recorded adapter transcripts (jsonl), written by the harness
scripts/acp-harness.mjs   run a real ACP session from the terminal; --record writes a fixture
scripts/build.mjs         npm run build: build-plugin.mjs + electron-vite + build-mcp.mjs
scripts/cad-resources.mjs the cadgen wheel and constraints into resources/cadgen, from a checkout
scripts/bundle-runtime.mjs the CAD runtime into resources/runtime/<os>-<arch>: the pinned Python
                          (scripts/python-build.json) with cadgen's closure installed, per target
resources/hardcore-mcp/   the MCP server's source (bundled into out/hardcore-mcp by the build)
skills/hardcore-app/      the skill only this app installs; composed into resources/plugin
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

## Git modes and worktrees

Every session has a working directory, and a git mode is how it got one
(plan §9). No mode is ever forced.

| Mode | `cwd` | `branch` | `worktreePath` |
| --- | --- | --- | --- |
| `none` | the project directory | — | — |
| `checkout` | the project directory | whatever it is on | — |
| `worktree` | a new worktree | a new `hardcore/<slug>` | the same directory |

`worktree` is the only one that can fail — a project that is not a repository,
or one with no commits — and it fails with a sentence rather than git's words.
The others work in a plain folder: git is optional, and a project is a
directory.

Worktrees live outside the project, one folder per project, whichever agent
made them:

```
~/.hardcore/worktrees/<project>/<slug>       branch hardcore/<slug>
```

The root and the branch prefix are settings, as are the fetch before creating,
the auto-delete and its keep limit (Settings › Git & Worktrees, which also
lists what exists per project). The slug comes from the session's first prompt
when there is one, so a directory can be matched to a thread without opening
anything. That directory is also the session's *identity* in the agent's own
store — both `codex resume` and `claude --resume` key their threads by cwd —
so a Hardcore worktree session is resumable from a terminal later.

Three things are never deleted automatically: a worktree outside the app's own
root, one with an open session, and one with uncommitted changes. The branch is
never deleted at all — a checkout can be recreated, the commits on it cannot.

The review's scopes are the other half of this. Main records HEAD when a
session is created and again at the start of every turn (`sessions.sessionHead`
and `turnHead`), and `Last turn` / `This session` are `git diff <sha>` against
the *working tree*, so an edit the agent has not committed is in the answer.
Those two scopes also move the whole read into the session's directory, which
for a worktree thread is not the project's checkout.

## How a change moves through the app

Adding an IPC channel is the shape of most work here:

1. declare it in `src/shared/ipc/<branch>.ts` with its request and response
   schemas, and spread that module into `src/shared/ipc/index.ts` — one line, so
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
