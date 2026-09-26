# Hardcore

The desktop client: projects on the left, one agent session in the middle, an
explorer on the right that renders code, browsers, terminals, reviews and every
file type the CAD Viewer understands. cadgen and the CAD skills ship inside the
app, pinned to its own version, and every session runs with them.

Sessions own their explorer tabs and agent tools. Project headings are derived
directory groups, with no separate project lifecycle. See
[session workspaces and persistence](docs/session-workspaces.md) for ownership,
title updates, profile locations and the database migration/backup contract.

Electron 40 · electron-vite · React 19 · TypeScript · Tailwind v4 ·
shadcn/ui (stock neutral) · Vercel AI Elements · `@agentclientprotocol/sdk` ·
Monaco (code) · TipTap over remark (markdown) · PDF.js.

This app is a root npm workspace. Install dependencies in this checkout with
`npm ci` from the repository root, build shared packages, then rebuild native
modules explicitly. Do not borrow another checkout's `node_modules`: packaged
Electron dependency resolution must be verified from this workspace's tree.

`features/explorer/FileTab.tsx` is a thin host of `@hardcore/ui/file-viewer`.
Its adapters translate IPC file access, source capabilities, root identity,
persistence and CAD commands into package contracts. `renderers/index.tsx` registers
the shared viewer renderers (CAD, and DXF drawings, GLB, triangle meshes (STL, 3MF) and
robot descriptions (URDF, SRDF, SDF) as their own renderers; all get the tab's backend
connection, preferences, host commands and live binding) and this app's own
Markdown, code, image, PDF and fallback renderers, which only the desktop
registers and so live beside it in `features/explorer/renderers/` rather than in
`@hardcore/ui` (see "File renderers" below). The whole
file-tab interface is shared with web. Projects, sessions, browser/terminal/
review tabs, agent integrations and native services remain in this app.
Neither shared package imports app source, and desktop imports no web source.
The host keeps the fullscreen orbit preference in one window-wide store, built
with the shared `createStoredCadPreferences` over `localStorage` (key
`cad-viewer:orbit:v1`; `adapters/cadPersistence.ts`). Active and newly opened
roots share that preference; renderer records and the open panel belong to the
tab. The renderer records live in `hardcore.fileViewer.v1`, keyed
`[sourceId, tabId]`, merged with the shared `mergeChangedRecords`, and forgotten
when their tab closes for good (`adapters/viewStateStore.ts`).

## Dev

```sh
# From the repository root:
npm ci
npm run build:packages
npm run native:rebuild --workspace hardcore
npm run dev:desktop  # electron-vite: main, preload and renderer with HMR
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
| `HARDCORE_PREWARM` | Under `NODE_ENV=test` both pre-warms are off — the project's (viewer child + cadgen daemon on project open) and the agents' (one idle adapter per agent in the index, see "Opening a session"); `1` turns them on, as `tests/e2e/prewarm.spec.ts` and `tests/e2e/reconnect.spec.ts` do. |
| `HARDCORE_FAKE_AGENT` | Launch this stdio ACP agent instead of whatever the registry says, for every provider. The session and git suites point it at `tests/fake-agent/index.mjs`; a session needs an agent to exist at all, and a real one would make the suite a test of somebody's login state. |
Two more decide whether the window is seen at all:

| Variable | Effect |
| --- | --- |
| `HARDCORE_LAUNCH_INACTIVE` | `1` shows the window without taking focus, for a relaunch from a script while the person is working in another app. |
| `HARDCORE_E2E_HIDDEN` | `1` never shows it. `playwright.config.ts` sets this for the whole suite (see Windows nobody sees, below); `HARDCORE_E2E_HIDDEN=0 npm run e2e` puts the windows back on screen. |

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

## UI typography

The app and its shared FileViewer use the same 13px default from
[`@hardcore/ui` tokens](../../packages/ui/src/styles/tokens.css).
`src/renderer/styles/globals.css` applies `text-ui` to the body; shadcn's
`text-sm` and `text-base` controls use the same token, including menus rendered
in portals. Use this size for ordinary interface text, with smaller sizes for
secondary metadata and content-specific styles for document headings/code.
The root remains 16px at the default appearance scale, so control spacing is
unchanged; `use-appearance.ts` still scales rem-based text and layout together.

## Loading feedback

The silver Hardcore star appears while the CAD runtime/viewer starts and while
geometry loads. An initial agent connection uses a smaller version; the live
Thinking/Running status uses a 24px mark with plain, unanimated text. Waiting
for approval holds a still pose. These reuse `@hardcore/ui/loading-icon` and its
baked image (no additional WebGL context). OS/app reduced motion and hidden
windows use the still image. Existing progress counts and status words remain
the source of truth.

## Checks

Interaction motion is scoped to activity/thought reveals, composer reference
chips, and attachment previews: 100–160 ms, with at most 3 px of travel and a
small scale change. It does not animate streamed text, pane dimensions, or CAD
geometry. The OS reduced-motion preference and Settings › Appearance's Reduce
motion switch both suppress these transitions.

```sh
npm run typecheck    # tsc over both projects: node (main/preload/shared) and web (renderer)
npm test             # vitest: tests/unit/{main,shared} in node, tests/unit/renderer in jsdom,
                     # tests/browser in Playwright's Chromium (`npx playwright install chromium`)
npm run lint         # eslint flat config
npm run build        # scripts/build.mjs: compose the skills, electron-vite build -> out/, bundle the MCP server
npm run e2e          # playwright _electron against out/ — run `npm run build` first
```

`npm run build` is three steps in one script (`scripts/build.mjs`): the
app's skills are composed into `resources/skills/` (`build:skills`),
electron-vite builds main, preload and renderer into `out/`, and the MCP
server is bundled into `out/hardcore-mcp/` (`build:mcp`). Packaging runs the
same script. The renderer consumes the compiled shared-package exports and
bundles their lazy renderers, CSS, assets and workers. Run
`npm run build:packages` from the repository root after shared code changes;
app source continues to use HMR. Tests consume the same exports.

The unit suite caps workers at four; Electron uses one worker and no automatic
retries. CAD integration tests use `tests/fixtures/cad/import-smoke.step` and
private caches beneath their temporary user-data directories. CAD profiles use
short temporary paths on POSIX so Python's Unix sockets stay within platform
limits. They disable the shared build daemon (except its explicit prewarm test)
and discard inherited broker settings, so an interactive
cache or another running viewer cannot satisfy a cold test. Optional live-agent
suites remain explicit opt-ins. CI selects this app only for changes to desktop,
shared UI/core, cadgen or shared build infrastructure; see the dependency graph
in the root `CONTRIBUTING.md`.

`HARDCORE_E2E_REQUIRE_CAD=1` requires the resolved runtime to be ready and match
`VERSION`, so CAD qualification cannot pass by skipping its render, toolbar,
selection, prewarm or shutdown coverage. The macOS test job uses the checkout's
`.venv` with fresh Node/browser assets; embedded-runtime packaging has its own
qualification. The invalid-interpreter test still verifies the failure card
before clearing its override and returning to the resolved runtime.

### Windows nobody sees

The suite's windows are never shown. Every spec launches the real app, and a
run is a dozen launches: shown, they take over the screen of whoever is at the
machine, and `showInactive` only stops them stealing the focus. So
`playwright.config.ts` sets `HARDCORE_E2E_HIDDEN=1` and main skips `show()`
altogether (`ready-to-show` in `src/main/index.ts`). Nothing else changes:
Playwright drives the renderer over the DevTools protocol, so screenshots
(taken by Chromium, not by the compositor on screen), bounding boxes, the
mouse, the keyboard and `toBeVisible()` all behave as they did, and the
screenshots below are the proof — they come back with the app fully painted on
a window that was never on screen. `webPreferences.backgroundThrottling` is off
so an unshown window keeps its frames and its timers. To watch a spec instead,
`HARDCORE_E2E_HIDDEN=0 npm run e2e`.

A manual relaunch is unaffected: `HARDCORE_LAUNCH_INACTIVE=1 npx electron .`
still shows the window, without taking focus.

`npm run e2e` writes screenshots beneath each test's Playwright output directory
(`test-results/` by default, or `--output`); it never rewrites the committed
design evidence in `tests/e2e/__screenshots__/`. CI uploads that run's PNGs and,
on failure, its traces and error context; both artifacts are kept for three days.
Captures include the shell in both themes,
Settings, the traffic lights' corner in the two states that own it
(`titlebar-sidebar`, `titlebar-session`, `titlebar-settings` — the reserved
rectangle drawn over it), one per explorer surface — `file-markdown-preview`,
`file-markdown-source`, `file-markdown-editable` (the dirty dot on an edited
document), `file-markdown-raw-blocks` (raw HTML kept as its own bytes),
`file-tree-deep`, `file-crumb-menu` (a folder crumb's menu of its
neighbours, open),
`file-context-menu` (a tree row's), `file-image`, `file-cad-failed` (the runtime broken on
purpose), `file-cad` (the explorer at its widest: the sidebar hidden and the
session at its floor), `file-cad-default` (the file's Settings open beside
the model) and both again at 1280×800,
`file-cad-measure`, `file-cad-tree` and `file-cad-files` (the file tree in
that same column), `file-cad-light-chrome` (Inspect and the app in light
appearance), `render-view` (Render's photographic scene, with no Materials
editor), and `robot-kinematics` (a joint edited in the robot's Settings, on its
Position tab),
`terminal`,
`browser-empty`, `browser`, `review`, `strip`, `strip-overflow` (seven tabs in
a pane at its floor, `+` pinned to the right edge), `panes-sidebar-collapsed`
(the sidebar closed by a drag past its minimum, with the toggle that brings it
back) and `panes-history` (the bottom of the back/forward stack, back
muted) — every one of those
kinds in light as `*-light` — the sidebar's own five, dark only
(`sidebar-pinned`, a `Pinned` section above the project sections;
`sidebar-filters`, the filter menu open under the panel's header;
`sidebar-header`, a project header hovered with `+` its one control;
`project-menu`, the composer's project chip open on `Recent` and
`Open folder…`; `sidebar-waiting`, the amber glyph on
a thread the agent has stopped to ask about), the `git-*` set for the git modes (the review
under three scopes, before and after a commit, the sidebar's worktree glyph,
Settings' per-project worktree card), the session states in both themes with
the composer at 1280×800 and 1680×1050, `session-new-model-menu` (the model
menu open on the new-session screen, a group per installed provider),
`session-new-mode-menu` (the mode menu open on the new-session screen, the
`Never asks` note under the full-access row),
`session-attach-menu` (the composer's `+`), `session-context` (the context
panel open over the composer, its breakdown expanded) and
`session-context-limits` (the same panel with the account's plan limits in
it, from the fake agent's `limits` turn) — both with a `-light` — and
`codex-open-file` from the one
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
`HARDCORE_E2E_CODEX=1`. `mode-option.spec.ts` runs the same fake with
`--mode-option`, which sends its modes as a `mode` config option instead of
as `modes`: the one mode chip has to be drawn from either shape, and an
adapter that sends only the option used to get no chip at all. `keyboard.spec.ts` presses every shortcut the
Shortcuts page lists except back and forward, which `panes.spec.ts` covers
along with the pane drags, the overshoot collapse and the too-narrow window; `quit.spec.ts` times `app.quit()` with a repository
watched, a shell, a session and the CAD viewer all running, and fails above
two seconds (see Quitting, below). `persistence.spec.ts` launches the app
twice against one user-data directory — a project, a session with the fake
agent, `app.quit()`, relaunch — and asserts both come back and the session's
transcript resumes through `session/load`. `reconnect.spec.ts` is what a
click on a session row costs (see "Opening a session", under ACP): a
disconnected thread painted from its snapshot inside 300 ms with the
reconnecting line under it, switching between two threads with no spinner
either way, and — across two launches against one user-data directory, with
`HARDCORE_PREWARM=1` — the first load adopting the warm adapter, asserted
from main's own timing line. Its fake agent runs with `--load-delay`, because
an instant reconnect is a state nobody can look at.

The CAD tests run against whatever runtime the app resolves on its own (see
CAD runtime, below): the bundled one once `npm run bundle:runtime` has run,
else the checkout's `.venv`. The explorer suite first breaks the runtime on
purpose — an override pointing nowhere — to see the failure card with the
interpreter's words in it, then clears the override and renders the STEP.
CAD failure, recovery, render and appearance cases use a fresh temporary
project containing the tiny STEP fixture at its original relative path. Tree,
watcher, terminal and strip checks retain the checkout project, so generated
app bundles cannot turn CAD catalog reads into repository-wide scans. The
render is skipped only in local runs without a runtime and without
`HARDCORE_E2E_REQUIRE_CAD=1`. The first render compiles the STEP in cadgen's build
pool and is the slow assertion of the suite.

`tests/e2e/codex-open-file.spec.ts` runs a real Codex session in a scratch
project and asks it to call `open_file`; it asserts the explorer opened the
tab and that the session recorded the tool call. It is skipped unless a
signed-in `codex` is on the machine (`codex login status`), so a runner
without one stays green. It is the only test that talks to a model.

`tests/e2e/draft-workspace.spec.ts` checks transient folder drafts, confirms
folder choices create no sidebar groups or explorer tabs, and exercises the
new-worktree choice through the form. `live-car-handoff.spec.ts` is opt-in:
set `HARDCORE_E2E_LIVE_CAD=1`, `HARDCORE_E2E_CAD_SOURCE` to the small car
recipe (with `BODY_LENGTH = 160.0`), and `CAD_DESKTOP_PYTHON` to the developer
runtime. It spends provider tokens, builds a disposable worktree car, copies a
part reference into the draft, requests an edit and reopens the session.
`HARDCORE_E2E_HANDOFF_DIR` optionally retains the temporary project and writes
provider session IDs there for a separate native CLI resume check. Otherwise
it removes the temporary project. Runtime provisioning is not covered by this
UX test: its build instruction explicitly supplies the configured interpreter.

Nothing in `npm test` loads `better-sqlite3` or `node-pty`: both are built
against Electron's ABI and will not load in a plain Node process. The migration
runner takes a structural `MigrationDb` so it can be tested anyway; everything
else that needs a real database belongs in the e2e.

## Brand

The sidebar uses the original faceted star in its original blue,
beside “Hardcore” in the regular system typeface (`features/sidebar/Wordmark.tsx`).
The mark in `src/renderer/assets/brand` embeds the original star pixels with
an exterior SVG clip. It is not a path-only vector.

The Dock and packaged app icon use this same blue star on a dark tile.
The legacy H export assets below remain available separately.

HARDCORE, set in JetBrains Mono ExtraBold Italic and drawn twice: a light-blue
copy of the glyphs offset down and right, then the foreground copy on top. No
blur and no gradient — the shadow is a second crisp copy, so the mark holds up
scaled, printed, and at 16px.

```sh
npm run brand   # resources/brand/*.png
npm run icons   # build/icon.png, from src/renderer/assets/brand/hardcore-star.svg
```

| File | What it is |
| --- | --- |
| `resources/brand/hardcore-wordmark-dark.png`, `…-dark@2x.png` | the wordmark for dark surfaces — white ink over the blue. Transparent, cropped to the ink plus one margin: 1002×196 and 2004×392 |
| `resources/brand/hardcore-wordmark-light.png`, `…-light@2x.png` | the same for light surfaces, ink `#0a0a0a` |
| `resources/brand/hardcore-h.png` | the H alone, 1024×1024, transparent, dark-surface colours. Legacy export asset |
| `resources/brand/hardcore-h-dark.png`, `hardcore-h-light.png` | the H on a solid `#0a0a0a` / `#ffffff` square, 1024×1024 |
| `build/icon.png` | the app icon: the blue star on a dark squircle tile, on macOS's icon grid |

Three numbers decide how it looks, and each is a named constant in
`scripts/make-brand.mjs`:

- **The blue is `#62b7ec`**, for the legacy H exports. The icon this replaced
  (`apps/docs/public/favicon.png`, still the docs site's favicon and untouched)
  is a shaded 3D render with no single hex, so the constant is the mean of its
  opaque unambiguously-blue pixels in the light luminance band: the star's lit
  faces. Its neighbours are `#3e90ce` below and `#a3e2fd` above.
- **The offset is 9% of the cap height**, right and down by the same amount, so
  the light reads as coming from the top left. Cap height, not font size,
  because that is what the eye measures an offset against. Much under 6% and the
  blue vanishes under the ink at this weight.
- **The monogram's ink is 72% of its square**, on its taller axis. This applies to the legacy H exports; the star icon uses its own centered inset.

`scripts/make-brand.mjs` renders every PNG in headless Chromium (the project's
Playwright), from an SVG whose `<text>` baseline is placed off the real face's
canvas ink metrics — so the crop is the letters, not the font's line box. The
face is embedded as a data URL, so what is installed on the machine cannot
change the output. Both scripts are deterministic: run either twice and the
bytes match.

**The font is `resources/brand/fonts/JetBrainsMono-ExtraBoldItalic.woff2`**,
from JetBrains Mono 2.304, under the SIL Open Font License 1.1. The licence
travels with the font, as the OFL requires: `OFL.txt` sits beside it in that
directory and must stay there.

## Packaging

```sh
npm run brand            # the wordmark and the H into resources/brand (committed)
npm run icons            # the sidebar star onto a tile -> build/icon.png (committed)
scripts/bundle/bundle.sh --clean  # cadgen's package runtime; ignored build output
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

The runtime bundler installs the exact wheel file under `resources/cadgen/`.
Release CI validates that there is one wheel matching the release version and
uses that path both to derive dependency constraints and to build every target
runtime; pip indexes and caches may supply dependencies, but never substitute a
different cadgen build.

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

`npm run icons` composites the sidebar's blue star onto its tile and writes
`build/icon.png`; the mark lives in one place and electron-builder derives the
platform containers — the macOS `.icns`, the Windows `.ico` — from that one PNG
at package time. An unpackaged app (`npm run dev`, `npx electron .`) runs inside
Electron's own binary and would show Electron's icon: main sets the Dock icon
from the same file on macOS and passes it to the window on Windows and Linux
when `!app.isPackaged`. See **Brand** above for what it is drawn from.

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

`electron-updater` checks the GitHub Releases of `earthtojake/text-to-cad`.
Release CI builds every installer from the exact commit it tags, then creates
or resumes that commit's Release with the cadgen wheel and sdist, installers,
blockmaps and `latest*.yml` feeds as peer assets. None of those build outputs
is committed. `src/main/updater.ts` checks ten seconds after
launch and every six hours, with `autoDownload` off: the app says an update
exists and downloads when asked. Settings › About & Updates is the whole UI.
Development builds report `unsupported` and check nothing.

### What is bundled

`resources/runtime/<os>-<arch>/` (the CAD runtime: a pinned Python with
cadgen and its whole closure installed), `resources/cadgen/` (the wheel and
its constraints) and `resources/skills/` (the composed skills) ship beside
the app as `extraResources`; all three are build outputs, gitignored under a
committed `.gitkeep`. `npm run build` fills the skills; `npm run
cad:resources` fills the wheel directory from a checkout after verifying the
ignored cadgen `_runtime` bundle is complete (the release
workflow drops the wheel it just built into it instead); `npm run
bundle:runtime` fills the runtime from those two (the release workflow runs
it per leg: macOS bundles `mac-arm64` natively and `mac-x64` cross, Windows
and Linux their own). The MCP server ships inside `out/hardcore-mcp/`,
unpacked from the asar so an agent can run it by path. See
`resources/README.md` for the bundler's steps, the cross-target rule and the
signing note.

## Layout

Three panes in a flex row, in pixels (`PANE_LIMITS` in `src/shared/types.ts`,
read by `Shell.tsx`): a 230px sidebar (180–480), the session taking what is
left with a 320px floor — its transcript and composer are a 720px column
centred in it — and a 740px explorer (280 up to the window less the session's
floor and the sidebar). The two side panes are `width: Npx` and are the
persisted preference; the session's width is a consequence, so there is no
number for it beyond the floor. Two separators (`[data-separator]`,
`app/PaneSeparator.tsx`) size the side panes: drag, or focus one and use the
arrow keys; Enter, Space or a double click closes the pane.
The sidebar, session, explorer tabs and Settings share a 48px top strip
(`--titlebar-height`), with their controls vertically centred. Whichever pane
is leftmost makes room for the macOS traffic lights (`--titlebar-inset`, keyed off `data-leftmost` on
the shell — `sidebar` or `session`, and nothing else). The controls of that
row never move on screen (Codex's rule): the sidebar's toggle sits right after
the traffic lights with back and forward beside it — in the sidebar's title
strip while it is open, at the left of the session's title bar once it is
gone — and the explorer's toggle sits at the window's right edge — in the
session's title bar while the explorer is shut, at the end of the explorer's
tab strip once it is open.
The session's title bar and the explorer's tab strip carry a rule beneath
them; the projects panel does not.

**One source of truth per side pane**, `{ collapsed, width }`: the sidebar's in
`settings.layout` (sqlite), the explorer's per session in `state/explorer.ts`
(localStorage). Everything on screen is derived from those two pairs — which
panes are rendered, where each toggle is drawn, which pane reserves the
corner. **A collapsed pane is not rendered at all**, so a toggle is in the
document exactly once and "the toggle did nothing" cannot be a state. There is
no panel library: `react-resizable-panels` kept a collapse of its own beside
ours, and the two disagreed — a drag under a minimum sometimes snapped back and
sometimes closed a pane without recording it, which left the only toggle inside
the pane that had just gone away.

**A drag stops at a pane's minimum; 40px past it the pane closes.** That
overshoot (`PANE_LIMITS.overshoot`) is deliberate: a pane that collapsed the
moment a drag touched its minimum closed itself on the stray pixel of a drag
that meant "as narrow as it goes". A collapse keeps the width, so the toggle
brings the pane back the size it was. Widths are written once, when the gesture
ends.

**Back and forward** (`state/history.ts`) walk the top level: a project's
new-session screen and its threads, which is everything the session pane can
show. Entries are recorded by watching the selection rather than pushed by each
of the half-dozen doors into "show me this thread"; back and forward set the
selection, so they never push. Deleted sessions' entries are stepped over, the
buttons are muted rather than hidden at the ends of the stack, and the keys are
`Mod+[` and `Mod+]` (the app menu's View submenu carries the accelerators).
The explorer's tabs are not in this history and Settings is not an entry —
it replaces the shell and comes back to whatever was under it.

**The traffic lights' room is measured, not guessed.** Main pins the cluster
where the layout expects it (`trafficLightPosition`, vertically centred in the
strip) and asks Chromium for the region the window controls occupy
(`titleBarOverlay`); the renderer reads that region — the Window Controls
Overlay geometry, which is also the CSS `env(titlebar-area-x)` — and writes it
into `--titlebar-inset` (`src/renderer/lib/titlebar.ts`), following it when it
changes. Pinning fixes where the buttons *start*; how wide the cluster is
belongs to AppKit and has moved between macOS releases, so the number in the
CSS (84px, `.platform-mac` in `globals.css`, beside the constant in
`src/shared/titlebar.ts`) is only what the first frame paints with and what a
window without an overlay falls back to. Fullscreen takes the buttons away and
the inset goes to 0 with them. Windows and Linux keep their native frame and
reserve nothing.

Nothing interactive may start inside that inset, in any state: the sidebar open
or dragged to its narrowest, the sidebar hidden with the session's bar at the
window's edge, the window at its minimum size, Settings (which replaces the
shell and reserves the room in its own header), the palette over any of them.
`tests/e2e/titlebar.spec.ts` walks those states and fails on a control whose box
reaches into the corner, on a leftmost bar whose first control starts inside it,
on a strip that is not a drag region or a control that did not opt out of it,
and on the measurement drifting from the constant — the last one being how a
macOS that draws the buttons differently announces itself. Its screenshots
(`titlebar-*.png`) draw the reserved rectangle over the corner, because the
lights themselves are AppKit's and never appear in a screenshot of the page.

**The sidebar and the explorer collapse; the session never does.** It has no
collapsed state at all: 320px is a floor the separators stop against rather
than a threshold past which the pane disappears. There is no fullscreen
explorer either — the one control that could take the session away is gone —
so the widest the explorer gets is the window less a hidden sidebar and that
floor. When the window is too narrow for all three minimums, the explorer
gives way first and the sidebar second, by *collapsing*: the state is written,
so the person is left with two toggles rather than a session pane pushed off
the right of the window. Growing the window back does not reopen them; the
toggles do.

**No project, no explorer.** The pane is a view of a directory: with none
bound, `Shell` renders neither the panel nor its separator, the session has
the window, and the toggle in the title bar, the palette's `Toggle explorer`
row and `Mod+Alt+B` are all absent or inert (`toggleCollapsed` refuses a
preference it has nowhere to file). A project brings the pane back with that
project's own remembered state.

**The sidebar is sections, not a tree** (`features/sidebar`, Claude Code's
shape). Its header is the app's name with the two controls that act on the
whole list — search (the command palette) and the sliders that open the
filter menu — then a nav list of one row, `New`: a plus in an accent ring,
the active project's new-session screen and the same thing `Cmd+N` does.
Under that, one grey header per project with a flat list of that project's
threads. The header is the project: its name and a chevron that collapses the
section (persisted per project in `settings.sidebar`), and on the right `+`,
a thread in *that* project — and nothing else. A search glyph and a copy of
the sliders used to appear on it on hover; neither was ever about one project
(the palette searches every thread and the filter settings are global), and a
control that only exists under the pointer is a control nobody finds.
The header's right-click menu starts a session, copies the directory path,
or reveals it in the OS. There are no project rename or delete actions: these
are directory groups derived from sessions, not saved project records. A
directory with no matching sessions has no sidebar header. Archiving or
deleting its last active session removes its active group; archived sessions
remain available in Settings and the Archived filter. Worktree sessions group
under their original checkout directory. Selecting a new folder opens an
in-memory composer draft; its group appears only when a session is created. A session row is its **state** as a leading glyph (a hollow
circle idle, a pulsing dot while a turn streams, an amber triangle waiting on
a permission, a red one after a failure, a spinner ring connecting —
`lib/sidebar.ts`), the title, git's own glyph when the thread runs in a
worktree or on a branch of its own, and a `…` on hover for pin, rename,
archive and delete. `Pinned` is the first section when anything is pinned,
and a pinned thread lives **only** there — never twice.

The filter menu is global, and it is opened from the panel's own header:
`Status` (Active / Archived / All), `Environment` (All / Local / Worktree —
our git modes), `Group by` (Project, or None for one flat list), `Sort by`
(Last activity / Created / Name) and `Show branch`. It is stored in `settings.sidebar` and applied by one pure
function over the index (`sidebarSections` in `lib/sidebar.ts`), which is also
where the rules live that a screenshot cannot check: a pinned thread is
excluded from its directory section, empty sections never appear (including
pinned-only directories), and every section is sorted the same way. Directory
labels and their order are derived from the session index; there is no durable
project list to synchronize.

**The explorer is closed until something opens it**, and the session then
fills the window. Opening a file, a review, a browser or a terminal shows it —
from the tree, the tab strip, the command palette or an agent's
`open_file` — because every one of those goes through `state/explorer.ts`'s
`open`/`openFile`. That state is the explorer store's rather than
`settings.layout`'s and is remembered **per session** (localStorage) along with
the pane's width, and only a person's own toggle or drag writes it: an agent
opening a file shows the pane without deciding anything for next time.

A CAD file in the explorer is laid out by the shared FileViewer, which measures
its own width: from 720px up, a file's panels are drawn in the file tab's own
panel column beside the model (see "The panels a file has"); below it they are
floating sheets over the model, the crumbs collapse to the file and the view
cube is hidden. The explorer pane opens at 740px (`PANE_LIMITS.explorer.default`),
so a fresh pane in the default 1440px window is the wide layout, with room for
the 280px panel column beside the model; a narrower window or a dragged
separator takes it below the breakpoint. The app owns light/dark appearance. Inspect uses its
fixed light (`#f0f4f9`) or dark (`#333333`) canvas; Render starts from the
matching photographic studio and keeps its model-local backdrop edits.

A markdown file opens as a document you can type in — a ProseMirror editor
over TipTap's schema, saved with `Cmd/Ctrl+S` like any other file, with
`View source` still there for the bytes. What it writes back is the file it
opened, block for block: every top-level block (and every list item) carries
the exact slice of the file it came from, and only the ones that changed are
re-printed, by remark, using the bullet, emphasis and wrap column the file
already uses. A whole-document serializer moves 18 lines of this
repository's `README.md` and 149 of its `AGENTS.md` on a one-word edit; this
moves the block. Raw HTML, link reference definitions and footnotes have no
node in the schema and are held as their own bytes. See
`features/explorer/renderers/markdown/document.ts` for the whole argument, and
`tests/unit/renderer/markdown-{document,editor}.test.ts` for the proof, which is run against
these three files.

**Paths in a transcript are links** when they exist (plan §8). `features/session/links` is
the whole of it: a remark plugin marks every path-shaped token in an
agent's prose — `models/bracket.step`, `README.md`, a code span holding a
path — as a link candidate; `state/path-links.ts` asks main which of them
exist, one `explorer.exists` per message per root rather than one per
token, and caches the answers until `files.changed` says otherwise; and
the `a` component draws a candidate as a button once it is known to be a
file or a folder, and as the words it was otherwise. A file opens in the
explorer with its renderer; a folder is revealed in the tree; a path with
a selector (`bracket.step#o1.2`, `#label.f45`) opens the file in the
viewer and hands the selector to the STEP renderer's command source. Paths
are relative to the thread's root — its worktree when it has one.

Activity summaries stay neutral even when a call fails. A separate red failure count marks a folded group, and its failed rows show a red **Failed** indicator; expand a row for the original error. Completed thinking rows use an ellipsis, with a spinner while thinking is active. Status comes from the agent’s tool-call status, not from words in its output.

**The transcript is the one part of the window that selects.** `body` is
`user-select: none` — this is a desktop chrome, and a drag across a sidebar
should not paint it blue — which quietly made every word an agent wrote
uncopyable. `[data-transcript]` sets `user-select: text` back
(`styles/globals.css`), so prose, a person's own prompt, a fenced code
block and an activity row's summary line all select; only the transcript's
own controls (the jump pill, an error row's buttons, a permission card's
answers) opt out again. Anything else that needs selecting says so with
`data-selectable`, the same as a path in Settings.

**The composer is an editor, not a textarea** (`features/session/composer`).
A CAD reference typed into it — `models/bracket.step#o1.2`, `#label.f45`,
`bracket.step` — becomes a chip the moment the space after it lands, a
pasted prompt's references become chips at once, and the viewer's Add to
prompt action places a chip in the box and focuses it
(the host's prompt-context service). The chip is an inline atom in a
one-paragraph ProseMirror document: Backspace removes it whole, the arrow
keys step over it and select it as a unit, and it prints back to its plain
token on send, so what the agent reads is exactly the text. The draft in
the composer store stays the source of truth; the editor is a view of it
(`references.ts` is the two functions between them, and the unit test is
the round trip). AI Elements' `PromptInput` is untouched — its form, its
attachments and its submit are as vendored — because the editor keeps the
form's `message` field for it; its footer is the one part not used, since
send shares the sentence's row.

**The box is one row until there is more to show.** Empty, it is a single
line of text with send centred at its right end; it grows with what is
typed to eight lines and then scrolls inside. The floor and the ceiling are
the editor's `min-h`/`max-h` and are the arithmetic of its own line height
(`composer/ComposerEditor.tsx`), which is what the e2e measures — "one row"
is a question about a line of text, not about a pixel count. Two things had
to go for it: a `min-h` of three lines, and send in a footer under the box,
which made the smallest possible composer a line to type in plus a line
holding one button. The row of chips is still under the box, outside it.
The viewer's camera button ("Ask about this
view") renders the viewport to a PNG and
accepts it together with selected references on the composer store (`acceptContext`), which the composer's
attachments pick up and send as an ACP image block.

Click a composer reference chip, or focus its button with Tab and press
Enter, to open its model and select the referenced geometry. The draft and
its caret stay intact, and activating a chip never submits the prompt.
References open relative to the chat’s workspace or the new draft’s pinned
workspace. A bare selector requires a CAD tab in that same workspace;
otherwise the app asks you to open the model first. This uses the viewer’s
existing `selectReference` contract; hover does not alter its selection.

References added from a named part or feature show the model filename alongside
its label, for example `car.step · wheel_front_left`. Switching model tabs does
not change a reference's filename. Long names truncate within the chip; the
full label is available on hover. The
full file/selector remains in the tooltip and is still the text sent to the
agent. Names are optional display metadata scoped to the draft; typed or
unresolved references keep their file/selector fallback.

Image attachments show a contained thumbnail beside the filename, with an always-visible remove control. Click the thumbnail (or focus it and press Enter) to inspect the full image. Escape, Close or the backdrop dismisses the preview and returns focus to the thumbnail; the draft is unchanged. Explorer tabs use a bordered active state and visible keyboard focus on selection and close controls.

The viewer's Copy Reference(s) button, ⌘C and the copy items in its menus are
clipboard-only. A STEP's viewport and model-tree menus also offer **Add to
prompt**, which adds that reference to the draft, and the navbar's snapshot
adds the current view and the selected references together. Each tab delivers
only to the session that owns it. A workspace mismatch is rejected, and
switching to another chat never redirects context. Nothing is sent until the
user submits.

FileViewer receives an explicit `ViewerHost`: workspace files/actions, live
documents, native clipboard, prompt delivery, navigation and environment
(appearance, keyboard platform and the app's reduced-motion setting).
Follow the [shared host contract](../../packages/ui/docs/viewer-host.md) when
adding integrations; native effects and session workflows belong in this app.
Prompt delivery binds the tab's immutable owner session when the host is
created, validates the entire bundle before one acceptance, and preserves its
text/reference/attachment order. Changing chats before or during encoding does
not redirect the result or steal composer focus. Deleted or archived
destinations cancel delivery. Recent operation receipts are bounded to 256
entries; pending captures are bounded to 16. Bundles accept at most
128 parts. Attachments must be supported images or UTF-8 text, at most
20 MiB each and 40 MiB together. Ordinary clipboard effects use the validated
`clipboard` IPC branch for plain text and PNGs up to 16 MiB; the renderer never accesses
Electron's native clipboard directly.

Incoming CAD selection and capture requests bind the project, tab, path and root
at request time. Only that active document receives them; replacing or closing
the target clears them. Nonce-specific acknowledgement prevents consumed requests
from replaying when the viewer remounts, while a repeated reference click creates
a fresh request.

Each changed file in Review has **Request revision**. It appends the file and
review scope to the draft, plus selected original or modified code and its line
numbers when present, and focuses the composer for the requested change.

`reference-ux.spec.ts` checks this with the toy car STEP: set
`HARDCORE_E2E_CAD_MODEL` and `CAD_DESKTOP_PYTHON`. It uses the fake agent to
verify the exact outgoing token, plus the real viewer to check the label,
reopening, absence of the retired tooltip and Escape selection behavior.

The composer's paperclip opens one picker for files and photos. The viewer's
camera button adds the current view and selected references to the draft.
There is no microphone: macOS dictation can type into the editor.

## The model, the effort and the mode

The composer has a chip for the model and one for how hard it should think,
and **so does the new-session screen** — which is where the decision actually
gets made, and where until recently there was only a list of vendors.

An agent says which models it has in its `session/new` reply, so a screen
with no session has nothing to draw. `src/main/acp/agent-options.ts` is the
answer: every live session's config options are written to sqlite against its
agent (migration 6, `agent_options`), on `session/new`, on `session/load` and
on every `config_option_update`; an installed agent that has never run here is
**probed** once — spawn the adapter, `initialize`, `session/new` in the
project's directory with the same MCP servers a real session gets, keep the
config options, close without prompting. One probe per agent at a time, and a
probe never `npx`-fetches an adapter for an agent whose CLI is not on the
machine: a session is something a person asked for and worth a download, a
probe is speculative. An agent that cannot answer — not installed, not signed
in, adapter will not start — contributes **no** models, which is the whole of
"do not show models that cannot be run".

So the new-session strip is project · git mode above the box, with the mode,
the model and the effort in the row under it, and the
model chip **is** the agent chip: its menu is grouped by provider, one group
per installed agent that answered, and picking `Opus` picks Claude Code the
way picking `GPT-6-Astra` picks Codex. In a live session the same chip is
scoped to that session's agent. Either way the choice is stored, so the next
session starts where the last one was left, and `SessionManager.create`
applies it: the model, **then** the effort (switching model is what changes
which effort levels exist), then the mode. Every one of those is best-effort:
an adapter that refuses one logs and the session goes on.

**The effort belongs to the model, the model and the mode to the provider**
(migration 9). Claude reports its `effort` option for whichever model the
session is on, with the levels *that* model has — one has `Xhigh` and the next
does not — so a single level per agent named no model in particular: switching
model carried the outgoing model's level onto the incoming one, and switching
back forgot the earlier pick. `agent_options` therefore keeps two maps beside
`default_model` and `default_mode`: `default_efforts`, the level picked per
model, and `effort_options`, the levels each model offers — filled in as live
sessions report them, because a session on one model is the only thing that
ever says what the other's are. Reselecting a model brings its level and its
list back together; picking a model touches neither. On create the effort is
read *after* the model has landed, against the model the session is actually
on, so a refused model does not drag the wanted model's level in behind it.

The mode is the third of them and the one worth spelling out, because it is
**the** permission control (below). Its default is the mode the person last
left this agent in, remembered against the provider like the model; until
they have picked one it is the provider's own auto-approval
preset — `_meta.kind: auto_review`, which is Claude's `auto` and Codex's
`agent` — rather than the adapter's most cautious default. Whichever of ACP's
two shapes the agent sends its modes in is where the answer goes:
`session/set_mode` over `modes`, or a `mode`-category config option
(`modeChoice` in `src/shared/acp/options.ts`, which prefers `modes` — it is
the protocol's own field and the one both adapters' `current_mode_update`
reports against). Changing the mode in a live thread stores it as that
agent's default too, so the next session starts where the last was left.

**Permissions are the mode, and only the mode.** There were two levels for a
while: the agent's own mode *and* an approval setting of Hardcore's own ("Ask"
/ "Approve for me") which could answer an incoming `session/request_permission`
with the agent's allow-once option before the person saw it. That is two
answers to one question — and no way to tell, when a request did not appear,
which of the two decided it. The app-side one is gone: nothing in
`src/main/acp/client.ts` answers a request, every request that arrives is a
card in the transcript with the agent's own options as its buttons, and what
the agent asks about at all is what its mode says. So the one mode chip is
also the one permission control, and it is on the new-session screen as well
as in a live thread — a shield, the agent's names, no sublabels. The single
exception to "no sublabels" is the mode whose `_meta.kind` is `full_access`
(Claude's `Bypass permissions`, Codex's `Full access`), which carries a muted
`Never asks` under its name: it is the one choice that removes every
checkpoint, and the menu should say so before it is made.

Which option is which lives in `src/shared/acp/options.ts`, read by both
processes, because main applies these answers and the chips draw them and one
file is where the two agree. Neither dropdown prints the agent's
per-option `description`: a menu of models is a list of names, and a paragraph
under each is a wall to read past rather than a choice to make. The `fast`
switch, when an agent has one, is the last row of the model menu — it is a
property of the model, not a second decision.

**The project chip is where a folder is chosen, and the only place one is
added.** Its menu is `Recent` — the projects in order of when they were last
worked in, which is the newest `updatedAt` of any of their sessions
(`lib/projects.ts`, over the index, because a project has no `lastUsedAt` of
its own and should not grow one) — a check on the one this screen is for,
then `Open folder…`: the same native chooser the sidebar's `Add project` row
used to open, followed by that folder's new-session screen
(`hooks/use-open-folder.ts`). Codex's shape, minus its `No folder` row: a
session here always belongs to a folder. There is no `Add project` button
any more, because adding a folder *is* choosing one; the two states with no
chip to open keep a button of their own (the sidebar's card and the
"Add a project to get started" screen), and the command palette has the row
for the keyboard.

There is no options chip. It held whatever else the agent exposed, which in
practice meant Claude's "main-thread agent persona" — a list of every custom
agent a person's plugins had installed — behind a settings glyph. The
composer is four decisions, not a settings panel.

All of it is one row **under** the box, not inside it. The box holds the
sentence and send; `+` and the chips sit on a 28px line beneath it — `+` and
the mode on the left, the model, the effort and the context
ring on the right, with a wider gap between those three because they are
three decisions rather than one run of text. The new-session screen is the
same shape: its context strip (project · git mode) above
the box, the same `+`, mode, model and effort row below it. No chip has a chevron:
six of them saying "this opens" about six controls that are visibly the
same control is six glyphs' worth of a row that would rather spend the
space on a label.

How full the context window is is a 16px ring at the end of that row
(`features/session/ContextMeter.tsx`) — the arc is what is used, quiet under
half, amber to four fifths, the destructive colour above it, and the numbers
are its tooltip. Clicking it opens a panel that **stays** open until Escape,
a click outside, or the ring again; hover does nothing, because a popover
that closes when the pointer leaves cannot be read down its length. In it:
the window as a segmented bar with `292.3k / 1M (29%)`; the account's plan
usage limits when the agent reports any — a row per limit with what it is,
when it comes back and how much of it is gone; and behind `See detailed
breakdown` (remembered per session, for as long as the window lives) the
agent's own categories and the session's token accounting — fresh input,
cache reads, cache writes, output, summed across the thread and for the last
turn. That accounting used to be a chip at the end of every turn and a
`22 files changed` pill over the composer; the first put a number nobody
reads mid-thread into the transcript once per turn, and the second said what
the Review tab says.

Neither of the two extras comes from ACP. No adapter sends the categories —
Claude's `usage_update` is `used`/`size`/`cost` with a `_claude/origin`
`_meta`, Codex's is `used` and `size` — so the reducer reads a breakdown out
of `_meta` (any key ending in `breakdown`) and the panel shows no categories
at all when there are none; Claude Code's own `/context` categories are
computed inside that CLI and never cross the protocol. The plan limits are
the Claude adapter forwarding the SDK's `rate_limit_event` as a
`usage_update` whose `_meta._claude/rateLimit` is one `SDKRateLimitInfo` —
one limit type per event, so the reducer keeps the latest of each in
`rateLimits` and normalises the two units on the way in (`utilization` to a
fraction, `resetsAt` to epoch milliseconds). Codex sends nothing of the kind
and the section is absent for it. Every field is read defensively: an event
this build does not understand is ignored rather than thrown on.

What a turn cost in dollars is in none of it: it is a number nobody acts
on mid-thread, and a price tag on a box someone is about to type into is a
poor thing to put in front of them.

## The explorer strip

The strip's `+` is one button and a menu of the five kinds, each with its
binding — ⌘T file, ⇧⌘R review, ⇧⌘B browser, ⌃` terminal, ⇧⌘D drawing
(`lib/shortcuts.ts` is the table the menu prints and `ExplorerPane` answers
to). It sits **after the last tab, inside the scrolling row**, and is
`position: sticky` at its right edge: it slides along with the tabs until the
row is longer than the pane, and then stops at the pane's edge with the tabs
passing underneath it. In the flow alone it was the button that scrolled off
at six tabs in a 45% pane; pinned outside the row it was always reachable and
never part of it. The file tree's open folders and its listings live in the explorer
store, not in the file tab, because opening a file makes a tab and the pane
mounts one tab at a time.

Every session owns its own explorer tabs, active tab, expanded folders and pane
width/collapse state. A new session starts empty, including another session in
the same directory. A new-chat draft has no explorer until a session exists.
Tab `sessionId` is immutable; `projectId` is only the directory identity used by
filesystem services. Reviews always use their owning session's revisions.

Ordinary tab edits are saved after a 400 ms debounce, keyed by session ID.
Drawing tabs/scenes are excluded from IPC persistence and database writes.
Switching sessions flushes the departing snapshot, retains its in-memory strip
and restores the destination's own strip. Writes serialize per session; unrelated
sessions load independently. Background agent commands open/show/close only
that agent's tabs and never navigate the user's selected session. Browser pages
and PTYs enforce the same session ownership, even for identical directories.
Unsaved text drafts and renderer view settings belong to their tab; shared
immutable CAD geometry caches can still be reused. Archiving/deleting a session
releases live browser/terminal/drawing/CAD resources. Archive keeps unsaved
text drafts in window memory for restoration (quitting still discards drafts), flushes and
retains ordinary tab metadata for restoration; deleting the session removes it.
Failed tab restoration displays a retry action without replacing stored tabs.

### Drawings

Choose **Drawing** from `+` (or ⇧⌘D / Ctrl+Shift+D) for a light Excalidraw
sketchpad. Edit the name in the drawing header; agents can supply a name on open
or rename an existing sketch. Names remain in memory alongside the scene. Pan
and drawing tools share the top toolbar, with menu/style/undo controls directly
below in narrow panes; the lock control is hidden. Freehand, shapes, arrows and text become visual prompt context with
**Add to prompt**. This appends a PNG and sketch description to the owning
session's draft, preserving existing text and never submitting it. The
destination is part of the tab's identity; even a late callback after changing
chats cannot redirect the result. Deleted or archived sessions cancel delivery.

Drawings live only in renderer memory. Switching tabs or sessions keeps them;
closing the tab, archiving/deleting its session, reloading or exiting discards them.
An image already added to a draft or transcript is a separate copy. This
scratch surface has no file import/export, autosave, Mermaid insertion, image
embedding or scene-editing MCP tool. The `drawings` integration provides
`open_drawing({title?})`, `rename_drawing({tabId,title})`, `drawing_state({tabId})` and
`capture_drawing({tabId})`. Opening a saved `.excalidraw` as a regular file
continues to show its source text.

The shared editor is `@hardcore/ui/drawing`; desktop owns its temporary
lifetime and prompt port. Fonts are bundled for offline use by the shared
`@hardcore/ui/drawing-assets` Vite plugin (desktop ships the full set) and the
editor loads only on opening a Drawing tab. Read [the drawing contract](../../packages/ui/docs/drawing.md)
for limits, asset licensing and the reuse boundary for future CAD overlays.

### File renderers

The shared viewer renderers come from `@hardcore/ui/renderers/*`. Markdown, code,
image, PDF and the unsupported fallback are this app's own, because web
registers none of them: `features/explorer/renderers/{markdown,code,image,unsupported}`,
and PDF as a plugin, beside G-code's toolpath viewer, in `src/plugins/` (its
[README](src/plugins/README.md): a plugin is a file type's viewer, tools and skills in one folder),
each a `defineFileRenderer` registration from `@hardcore/ui/file-viewer` over the
package's public exports only (the contract a host renderer may rely on is
`@hardcore/ui`'s [renderer contracts](../../packages/ui/docs/renderers.md)).
Monaco, TipTap, remark and PDF.js are this app's dependencies, not the package's.

They keep the Markdown document and source views, Monaco's configuration and
save binding, image fit and actual-size controls, PDF presentation and the
unsupported-file fallback. Text preparation uses `FileSource.readText`; image and
PDF preparation use `FileSource.readAsset`, whose release lease is the prepared
document's `dispose`. Monaco setup and editor constants are `renderers/code/editor`
(the session's diff view reuses them). Model URIs include source, document, and
mounted-view identity so two FileViewer instances cannot share draft or cursor
state, while a mounted editor keeps a stable model through ordinary renders.
Markdown loads that editor only when its source view (`View source`, a `body`
panel with the id `source`, persisted like any other panel id) is opened.

PDF uses Mozilla PDF.js with a per-document worker, real text layer, page
navigation and a prompt capture action. Rendering, extraction and captures
share the same loaded document. The host provides asset bytes and the live
`host.pdf` binding. Reads accept at most 50 pages and one million characters;
page canvases are bounded to 4096 pixels on their longest side. Extraction
is not OCR. Page and selection identity is captured before asynchronous prompt
delivery. Page state persists through the renderer's state slice.

Code and Markdown source selections offer “Use selection in prompt” in Monaco's
context menu. This sends a zero-based UTF-16 text range and the selected bytes
through PromptContext. External live-buffer replacements update the Markdown
visual editor without echoing another edit or discarding unaffected source
formatting. Dirty text can survive view unmounts through the host draft store.
The image, PDF and fallback views follow the shared viewer design system's type
scale and breakpoint (`tests/unit/renderer/file-renderers.test.tsx` checks it).

Their tests are this app's: `tests/unit/renderer/{file-renderers,file-renderer-registrations,markdown-*}`
in jsdom, and `tests/browser/pdf-renderer.test.mjs`, which serves a FileViewer
with the PDF renderer from this app's root through its own Vite server and drives
PDF.js's real worker, text selection and capture in Playwright's Chromium.

### Live files and terminals

A file tab keeps its `file` kind and chooses a renderer: CAD, PDF, Markdown,
code, image or unsupported. The `documents` integration reads the live text
buffer, including unsaved typing, and requires its revision before replacing
or saving it. Tab/session switches retain drafts and inactive read snapshots;
reactivate a text file before editing or saving. Dirty tabs refuse ordinary
and agent-driven close; the UI provides explicit discard. These drafts last
for the app window, not across quitting. PDF tools operate on the same PDF.js
document as the page on screen. See [workspace integrations](docs/integrations.md)
for the complete tab/renderer/integration mapping and lifecycle rules.

Terminal tabs are views of main-owned PTYs. Switching tabs does not stop a
process or lose its scrollback. The `terminals` integration creates, reads,
writes and stops those same PTYs through scoped tab IDs. Reads return an output
sequence and input revision; writes require both, preventing a tool from racing
new output or user typing. Closing a terminal releases its process; stopping
it leaves the output available until close. A provider's own shell tool has
separate process IDs and does not automatically create a Hardcore terminal tab.

Directory listings show every regular file and directory, including dotfiles,
Git-ignored outputs, dependency folders and unsupported formats. Renderer
support determines what opens in the file tab; it never hides a tree row.
Unknown types open with **Not supported**. Listings are lazy and complete for
each expanded directory. The bounded fuzzy index visits project content before
dependency caches so cache files do not crowd generated CAD outputs out of the
search budget. Background recursive watching respects the root's Git ignore
rules and excludes dependency caches so packaged runtimes do not create tens
of thousands of watchers. Every browsed directory and every opened file's
parent receives a direct watch, including Git-ignored outputs. Those files stay
live without expanding their folders, and all watches close when their root's
last owner leaves.

### The file tab's nav

One row: the breadcrumb, with the unsaved dot and the file's loading or update
status after the file's name; then, at the right end, the renderer's actions
(a viewer file's snapshot), one toggle per panel the file declares, and the
files toggle last, which stays there whatever is open and whatever kind of
file it is. The tree's header is its filter and nothing else. There is no
`Copy path` button and no `Open ▾`: those are items in the entry menus.

The row itself is the CAD Viewer's — `@hardcore/ui/navigation`, inside the complete shared FileViewer that web
viewer draws too, so the two apps have one nav row and not two that resemble
each other. This app supplies the branch label before the crumbs (`leading`,
drawn by `FileTab.tsx`) and, through a source adapter, the two things only it
has: where a directory listing comes from and the entry menus on a crumb
(`features/explorer/adapters/fileSource.ts`).

The desktop `FileSource` exposes validated IPC storage operations separately
from native/copy `FileActions`. Writes return structured revision conflicts,
never parsed error text. Main serializes same-path writes, checks the expected
content revision immediately before a same-directory atomic replacement, and
preserves file permissions. Cancellation cannot reverse a dispatched commit.
Committed move events remap every matching tab and cached/expanded subtree;
delete events prune descendant listings. A bounded mutation-receipt history
prevents the broadcast and initiating caller's receipt from applying a move
twice. External edits preserve dirty drafts and refresh clean documents.

**Every crumb is a menu of its neighbours** (`@hardcore/ui/navigation`'s
`Breadcrumbs.jsx`, the model in its `crumbs.js`), the way the CAD Viewer's
breadcrumb is. The crumbs
are the path's segments **below the root** — `STL/link_plate.stl` is `STL ›
link_plate.stl` — and each one's menu is its **parent's** listing with the
crumb itself marked: the first crumb drops down the root's entries, a folder
crumb drops down what sits beside that folder, and the file crumb drops down
its siblings. There is no crumb for the project or the worktree, and that is
the rule rather than an omission: a root's neighbours are outside the project,
and a menu in this pane never lists anything above the root. A file at the
root is one crumb, listing the root. A worktree tab keeps a **branch label**
before the crumbs — it names the root, so it has no menu, but which copy of
the tree a file is in is the one thing its name does not say. Directories
come first, each a submenu
of its own listing read when it is opened; picking a file opens it *in this
tab* — the crumb is the tab's address bar, unlike the tree's rows, which open
tabs. Below the viewer's 720px breakpoint the crumbs collapse to the file's
own. The listings are the tree's own (`useTree`), so a folder the tree
has read costs the menu nothing and the two never disagree.

**The file crumb carries a `⋯`** immediately after its name ("File actions"),
which opens the same entry menu the right-click does — one table
(`@hardcore/ui/navigation`'s `entry-menu.js`), one set of actions, drawn as a dropdown instead of a
context menu. A right-click is not a control anybody can see, and the file's
own menu is the one worth pointing at.

**Right-click a crumb or a tree row** for the entry menu
(`@hardcore/ui/navigation`'s `entry-menu.js` is the table, `entry-actions.ts` what each item does,
`@hardcore/ui/navigation`'s `EntryMenu.jsx` draws one from the other; the tree has one menu over
the whole list aimed at the row that was clicked, and the empty space under
the rows is the root). A file: Open (tree rows only — a crumb is the open
file, and a file is one tab: opening it again by any door focuses that
tab) · Open with default app · Open with… · Reveal in Finder (Show in Explorer / Show in file manager)
· Copy path · Copy relative path · Copy reference (CAD files: copy the path
through the native clipboard port and deliver the typed workspace reference
through the injected prompt destination) ·
Rename · Duplicate · Move to Trash. A folder: New file · New folder · Open
in terminal · Reveal · Copy path · Copy relative path · Rename · Move to
Trash; the root has no Rename and no Trash. The one destructive item is
alone at the bottom and goes to the OS trash (`shell.trashItem`) with no
dialog — the trash is the undo. Rename and the two `New …` are typed in
place (`@hardcore/ui/navigation`'s `InlineName.jsx`: Enter commits, Escape cancels, clicking away
commits, the stem is selected and the extension is not); from a crumb they
go to the tree, which is shown for them. F2 renames the tree's cursor row,
⌘⌫ (Ctrl+Delete) trashes it. Every edit is an `explorer.*` request main
resolves against the root and refuses outside it (`src/main/explorer/fs.ts`
for create/rename/duplicate, plain Node and unit-tested; trash, reveal and
`Open with…` — a chooser over `/Applications` then `open -a`, the shell's
own Open With on Windows — in `src/main/ipc/explorer.ts`). A rename or a
trash keeps the strip honest: tabs showing the file or anything under the
folder are re-pointed or closed. `Open in terminal` on a folder is the one
`terminal.create` whose `cwd` is under a root rather than a root.

### The panels a file has

**One panel column, one list of panels, one open at a time**
(`@hardcore/ui/navigation`'s `panels.js`; the column is its `FilePanelColumn.jsx`).
The list is what the open file's renderer declares plus the **file tree**,
which is the last entry and not a special case; the nav row draws one icon
button per entry with `aria-pressed`, highlighted while its panel is open,
in that order — so the files toggle is last and never moves, and the one
control that is always there is always in the same place. Opening any panel
closes whatever was open.

Markdown declares one, the two readings of the same bytes (`View source` /
`View preview`). A viewer file declares at most one: its **Settings**
(`cad-file`, the sliders glyph), and only a STEP and a URDF, SRDF or SDF have
one (`viewerPanels(ready, { file: true })`). Its sections are Features (Links
for a robot) and Position, shown as two tabs when a file has both. An STL, a
3MF, a GLB and a DXF declare none; Display is a toolbar popover, never a panel.
Code, images and PDFs declare none, leaving the tree as the whole list.

A declaration identifies where its content belongs: `tree` is the app's file
tree, `slot` is a box the renderer draws into, and `body` replaces the file
content, as markdown's source view does. A viewer file's panels use `slot` and
portal into the file tab's panel column. Every panel shares one border, width,
resize handle and header treatment.

**The tab owns which panel is open**, as one id in `FileTabSchema.panel`,
persisted with the tab. `null` is the renderer's default — a viewer file's own
panel (a STEP's, a robot's), else nothing; the tree is the default only for a
tab with no file — while `""` preserves a deliberately closed panel. A new tab,
and a crumb that points this tab at another file, start at `null`. A file picked
in the tree asks for the tree (`openFile(path, { target: "new", panel: "tree" })`):
its tab — new, or the one already showing it — opens with the tree up, so the tree
can be walked file by file; `openSessionTab` applies a requested panel in the same
strip update that selects the tab, and leaves a tab's panel alone when none is
asked for. While any panel is open — the tree included — a viewport pick turns
it to the file's Settings (`onPanelOpen`), and the Position tool opens Settings
on its Position tab; a pick with nothing open leaves it closed. Below the
viewer's 720px breakpoint the tab's panel is not consulted: a file opens with
no sheet, a sheet opens from its toggle, and neither a pick nor a tool opens one. A CAD tab whose runtime
failed declares no panels, leaving only the files toggle. Saved `cad-theme`
panel choices read as `null`.

### Inspect and Render

CAD controls are shared with web, and the shared
[viewer design system](../../packages/ui/docs/settings-ui.md) is their contract;
what follows is what a desktop tab shows. Every 3D file has a toolbar at the
top left, ending in **Display**
([tools and lifecycle](../../packages/ui/docs/settings-ui.md#tools-and-lifecycle)).
A STEP's is Select, Draw, Measure, Explode, Clip, then Position where the
sidecar declares kinematics and Animate where it declares routines, then Display.
A tool with a corner mark has a menu (Select's selection filter, Measure's
snapping, Animate's routine, speed and loop); Explode and Clip are toggles whose
panels sit beneath the toolbar. A robot description's is Select (which picks
whole links; Shift, Ctrl or Cmd adds one), Position where it has movable joints,
then Display; it opens in Select. An agent's select command on a robot fails
with a sentence saying so; its clearSelection clears the link selection. Draw is
a STEP tool and appears nowhere else. A GLB, an STL and a 3MF have nothing to
select: their toolbar is Display, plus Animate for a GLB with clips, and an
agent's select command on one fails with a sentence saying so. The playbar
shows while Animate is active and in fullscreen. Buttons wrap inside the
toolbar in a narrow pane. Display is a popover tool: it takes the pointer from the
active tool, and closing it hands the pointer to the file's default tool
(Select, where there is one).

The file navbar's snapshot action (the camera) attaches the viewport PNG and
the selected references to this tab's owning session draft through the
prompt-context adapter; it does not send a message. There is no zoom control
anywhere: no percentage readout, no menu behind one, no zoom toolbar. A STEP's
viewport context menu ends in Zoom to fit and Zoom to selection (off without a
selection), offered over a part, over the backdrop and on every Features tree
row. The view cube sits at the bottom right, hidden below the 720px breakpoint
and in fullscreen: its faces turn the camera to the six plane views and its
corners to the isometric views, keeping the zoom. Neither touches the model, its
motion or its display settings. The camera is never stored, so reopening a file
frames it afresh.

**Fullscreen** is the shared shell's own button, a small two-arrow icon at the
top right of the viewport
([camera, animation and fullscreen](../../packages/ui/docs/settings-ui.md#camera-animation-and-fullscreen)).
It keeps this app's navbar, hides the toolbar and suspends the sidebar, orbits
by default, and offers an Orbit menu and, for a file with animations, a Play
menu; Escape or its X exits and puts the camera back. The host passes nothing
for it.

A STEP's Settings holds Features, then Issues when there are any, and Position
when the sidecar declares kinematics (a `Pose` choice with its Reset, then the
joint sliders); with Position present, Features and Position are separate tabs.
Animate's playback and Position's pose retain independent runtimes, enable state
and actions; every pose write (a value, a named pose, a Position-tool knob,
Reset) is an instant jump, and Reset also stops any playing routine and hands
the pose back to Position. A robot's Settings holds Links (the link tree, an
SDF's metadata after it) and Position for the joints, as two tabs when both are
there. A DXF drawing has no toolbar and no Settings: it is a straight 2D render
on a canvas — drag to pan, wheel or pinch to zoom about the pointer,
double-click to fit — and the navbar carries only Take snapshot and the files
toggle.

Display's first section holds the Mode dropdown (Solid, Render, X-ray, Hidden
line, Wireframe) and Projection; Surfaces, Edges, Grid / Axes, Lighting (with
its Preview/Final quality), Background and Floor follow. A robot, a GLB, an STL
and a 3MF have no CAD edges, so they offer only Solid and Render and no Edges
section. Switching modes never reframes the camera
or changes the open panel. Display settings, Clip and Explode persist in the
tab's record for the file.
The file's Settings stays mounted while Display is open, so the Features tree
keeps its disclosure and scroll.

Settings › Appearance owns the app's System, Light and Dark preference; the
desktop adds no appearance control to Display. Authored materials are read-only
in every display mode, with names and properties in the selection's reference
details. There is no Materials tab, local assignment or material undo state.
Use prompts to change source material assignments or properties.

Embedded STEP animation modules load through temporary Blob URLs in the
renderer. Its content security policy permits `blob:` scripts for this path,
while retaining the restrictions on remote scripts, inline scripts and `eval`.
The shared loader revokes each URL after module evaluation; no adjacent
JavaScript file is discovered or written.

Neither a display-mode change nor a photographic setting changes the app's appearance. The
Electron `theme` suite samples the document through these interactions, and
`cad-scenes` checks Display settings, a robot's Position controls, authored material details
and the absence of a Materials editor. See the shared [Render modes](../../packages/ui/docs/render-mode.md)
playbook for the mode bases and camera behavior.

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

On POSIX, an app-owned viewer runs in its own process group. Its transient CAD
workers are stopped when the viewer exits or the app quits, including workers
that outlive the viewer process. Reused external viewers and the shared warm
daemon belong to separate groups and are left running.

What is left after `will-quit` is Chromium's own shutdown, which on this
macOS takes twelve seconds to minutes once a window has held a WebGL context
(the GPU and utility helpers hang, then the browser process retries a
CoreAnalytics XPC send; `app.exit()` is slower still, and no timer of ours
runs once the event loop has stopped). `src/main/quit-deadline.ts` keeps a
deadline from outside: a detached copy of this binary run as Node that
kills the app and its helpers at an absolute deadline, 1.2 seconds from
`before-quit`. It is armed after `will-quit`, once state is saved, and counts
teardown and watchdog startup toward the same budget. A quit that finishes
on its own — half a second without WebGL —
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
cadgen's version against the app's, the viewer backend, the skills root
every session is handed — and Repair, which forgets the probe and looks again.
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

The viewer does not wait for the first CAD file. When the explorer binds to
a project (or a session's worktree), the renderer calls `cad.warm`, and main
starts what the first CAD file would have paid for on its own clock: the
runtime probe, the viewer for that root, and cadgen's warm build daemon
(`src/main/cad/daemon.ts` spawns `python -m cadgen.daemon`, the registered
command a cadgen client spawns for itself, detached and never stopped — it is
the person's daemon, shared with every terminal, and it retires on its own
idle timeout). Once per interpreter per app run, and never when
`CADGEN_DAEMON=0`. Measured with `scripts/perf-cad.mjs`: the first STEP open
after launch had paid 0.9 s for the probe and the viewer and ~3 s for the
daemon's start inside its first compile; warmed at project open both are done
before the click, and `viewerOrigin` shares the launch already in flight.

## Skills and tools in a session

The app gives each session focused skills and independent domain MCP servers.
`src/main/integrations/registry.mjs` is their shared composition point; the
[workspace integration guide](docs/integrations.md) defines resource scopes,
lifetimes, prompt handoff and the recipe for adding a domain. Nothing installs
into an agent's own configuration: no plugin, marketplace or copy into
`~/.claude/skills`, and no mandatory umbrella `hardcore-app-use` skill.

**Skills.** `scripts/build-skills.mjs` composes repository skills plus the
registry's app skills into `resources/skills/`. The standalone `cad-viewer`
skill is replaced by the focused embedded-viewer handoff. Browser, PDF,
documents, terminals and drawings supply their own instructions; upstream
skills retain licenses and provenance. The app supplies cadgen/Python on PATH,
and the embedded CAD skill directs agents to that runtime.

At launch `src/main/integrations/skills.ts` materializes real copies into both
native loader layouts:

```
<userData>/skills/<version>/.claude/skills/<skill>/SKILL.md
<userData>/skills/<version>/.agents/skills/<skill>/SKILL.md
```

This is rebuilt when the app version or composed content changes and is
idempotent otherwise. `hardcore-skills.json` is written last as the completion
marker. Symlinks are never shipped. Every `session/new` and `session/load`
receives the root in both `additionalDirectories` and `_meta.additionalRoots`;
adapters read whichever spelling they understand. Claude Code and Codex use
their native skill-root mechanisms. Other adapters retain the concise first
prompt preamble; workspace `list_skills` and `read_skill` read the same root.
These are discovery options, not a requirement to load every skill on a turn.

**MCP servers.** The registry supplies separate `hardcore-workspace`,
`hardcore-browser`, `hardcore-pdf`, `hardcore-cad`, `hardcore-documents`,
`hardcore-terminals` and `hardcore-drawings` entries. Each runs the shared
`resources/hardcore-mcp/server.mjs` executable with its domain selected in the
environment, using this app's Electron binary as Node. Packaging bundles it
in `out/hardcore-mcp/`, including Playwright's upstream packages/runtime assets.
The browser entry bootstraps a scoped native connection and runs Playwright MCP;
other domains register their app-owned tools from the registry. Each session/domain gets a different token, restricted
to that integration's registered methods; a domain's tool does not acquire
another domain's capabilities. The stdio entries omit `type`, because the ACP
adapters otherwise interpret them as HTTP/SSE.

The loopback bridge in `src/main/integrations/mcp-bridge.ts` authenticates the
session, checks method ownership and validates its schema. Native services
operate in main; UI-bound calls use `integrations.command` / `integrations.reply`
and `src/renderer/state/integration-commands.ts`. Main resolves the session's
project/worktree, and the owning service checks tab/resource identity again.
Background reads do not change focus. A capture tool returns an image; an
Add to prompt action separately binds a compatible draft and never sends it.

Provider-owned filesystem/shell tools still access disk and their own process
IDs. They do not read unsaved editor buffers or control Hardcore's terminals.
Use the app's document and terminal integrations for those live resources.
Existing disk watchers reconcile changes made by ordinary repository tools.

**Runtime.** `CadRuntime.sessionPath` puts the app's pinned CAD runtime ahead
of the login-shell PATH. In a packaged runtime, `<userData>/bin/cadgen` invokes
`python -m cadgen.cli`; it does not depend on a build-machine pip shebang.
Python discovery, daemon startup and CAD viewer backend lifetime stay in
`src/main/cad/`, separate from generic integration plumbing.

The unit suites cover the registry, skill composition/materialization, MCP
registration, authenticated loopback bridge and domain ownership/conflicts.
Browser/PDF integration tests exercise the actual page/renderer; live-document
tests cover retained drafts, revision conflicts and stale capability cleanup.
`tests/e2e/integrations.spec.ts` runs a hidden Electron app with the opt-in fake
ACP scenario: it spawns the actual session-supplied stdio servers with the MCP
SDK, validates all seven registrations and token isolation, and exercises live
text/PDF/drawing/terminal resources without spending model credits.

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
                          sessions.ts (index + live connections),
                          agent-options.ts (what each agent's sessions can be configured
                          with, cached between them — see The model and the effort)
  ipc/{acp,agents}.ts     the P1 handler branches, spread into ipc/index.ts
  ipc/agent-options.ts    agentOptions.*: the cache, the probe and the stored defaults
  ipc/{skills,runtime}.ts   the skills root and CAD runtime branches (P5's bodies, P6's shape)
  ipc/dialogs.ts          the native folder and file choosers Settings' path rows use
  ipc/{explorer,cad}.ts   files, terminals; cad.viewerOrigin + cad.warm
  ipc/integrations.ts    scoped integration command/reply relay
  ipc/git.ts              P7's: the review's reads in a session's directory, the
                          commit, the pull request, and the worktree list
  explorer/               fs.ts (complete listings, read/write, scoped watchers),
                          terminal.ts (node-pty sessions + scrollback)
  cad/                    runtime.ts (which Python: override, bundled, checkout), viewer.ts (one viewer per project root),
                          daemon.ts (the warm build daemon, started at project open),
                          index.ts (CAD runtime wiring)
  integrations/           registry.mjs + domain/module.mjs (tools and focused skills),
                          manager.ts, skills.ts, mcp-bridge.ts + actions.ts (generic relay),
                          domain services/actions and lifecycle policy
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
  ipc/agent-options.ts    agentOptions.* — the model and effort chips before a session exists
  acp/options.ts          which option is the model, which is the effort, which mode is
                          the agent's own auto preset (both processes read this one file)
  ipc/skills.ts, ipc/runtime.ts, ipc/dialogs.ts  the skills, CAD runtime and chooser branches (P6)
  agents.ts               provider and status schemas
  acp/types.ts, acp/reduce.ts  SessionState and the pure session/update reducer
  ipc/explorer.ts         explorer.* terminal.* and their events (P3)
  ipc/git.ts              git.* — the review's reads plus P7's worktrees
  ipc/cad.ts              cad.viewerOrigin and cad.warm
  ipc/integrations.ts    integrations.command / integrations.reply for domain MCP tools
src/renderer/
  app/                    Shell (three panes in a flex row), App, CommandPalette
    PaneSeparator.tsx     one pane divider: drag, arrow keys, and the overshoot collapse
    PaneToggles.tsx       the sidebar's and explorer's toggles, and back/forward
  lib/panes.ts            the pane geometry: clamps, the overshoot rule, what fits (pure)
  features/sidebar        projects as sections, their sessions flat, Pinned, the filter menu
  lib/sidebar.ts          which sections exist and what is in them: the status/environment
                          filters, pinned-only-once, the grouping, the sort, the state glyph (pure)
  lib/projects.ts         the project chip's `Recent` order, out of the session index (pure)
  hooks/use-open-folder.ts  `Open folder…`: the chooser, then that folder's new-session screen
  features/session        the new-session state, the transcript, the composer
    view.ts               SessionState -> rows: activity-row labels, folding, the status line (pure)
    parts/                activity rows (+ Monaco diff, terminal), thoughts, permission cards, subagents
    ComposerChips.tsx     project / git mode / mode / model / effort chips
    ContextMeter.tsx      the context ring at the end of the composer's row, and the
                          panel behind it: the window, the plan limits, the tokens
  features/explorer       the one tab strip and its five kinds of tab
    drawing/              temporary Excalidraw host and prompt attachment action
    adapters/fileSource.ts  this app's file/navigation service: the listings, read a
                          directory at a time over IPC, and the crumb entry menus
    renderers/            the file-tab renderers: index.tsx composes the shared viewer
                          renderers with this app's own, which live here —
      code/               Monaco, self-hosted, and its worker setup (code/editor)
      markdown/           the document editor and its `View source` panel
      markdown/document.ts  markdown <-> the editor's document, keeping every block the
                          person did not touch byte for byte (remark; read its header)
      markdown/schema.ts  the editor's schema: TipTap's starter kit plus tables, task
                          lists, images, a raw-markdown atom and the source attributes
      image/, pdf/        image fit and zoom; PDF.js pages, text layer and live binding
      unsupported/        the fallback: “Not supported”, and Open externally
  features/settings       the Settings route, the card-grouped rows, the agent drawer, and
                          pages/ — one module per page; search is done by the rows themselves
  lib/shortcuts.ts        the keyboard-shortcut table the Shortcuts page prints
  lib/git-mode.ts         the sidebar glyph, the composer chip's labels and which
                          modes a project can offer — one answer, two features
  hooks/use-appearance.ts accent, UI scale, code font, reduced motion, translucency as <html> tokens
  components/ui           shadcn/ui, vendored
  components/ai-elements  Vercel AI Elements, vendored (types.ts replaces the `ai` package)
  state/                  one zustand store per domain, plus bridge.ts for main's pushes and
                          integration-commands.ts for an agent's tool calls against the stores
    history.ts            back and forward over the top level, recorded from the selection
  styles/globals.css      stock shadcn neutral tokens — the same ones apps/web uses
tests/unit/               vitest
tests/e2e/                playwright, against the built app
tests/fake-agent/         a scripted ACP agent on stdio (SDK agent side), also replays fixtures
tests/fixtures/acp/       recorded adapter transcripts (jsonl), written by the harness
scripts/acp-harness.mjs   run a real ACP session from the terminal; --record writes a fixture
scripts/build.mjs         npm run build: build-skills.mjs + electron-vite + build-mcp.mjs
scripts/cad-resources.mjs the cadgen wheel and constraints into resources/cadgen, from a checkout
scripts/bundle-runtime.mjs the CAD runtime into resources/runtime/<os>-<arch>: the pinned Python
                          (scripts/python-build.json) with cadgen's closure installed, per target
scripts/make-brand.mjs    npm run brand: the wordmark and the H monogram into resources/brand
scripts/make-icons.mjs    npm run icons: the sidebar star onto its tile -> build/icon.png
resources/brand/          the committed marks, and the JetBrains Mono face they are set in
resources/hardcore-mcp/   the MCP server's source (bundled into out/hardcore-mcp by the build)
skills/                  focused domain instructions and licensed upstream skills,
                          selected by the integration registry for resources/skills
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
terminals instead of node-pty), prints every update, and `--record` writes
every wire frame as jsonl. A permission request is answered by the script
itself, with the agent's own allow-once option: the app answers none — the
session's mode decides what is asked and a request that arrives is answered
in the transcript — and a terminal with no transcript has to say something,
unattended, for a recording run to finish. Those recordings are the reducer's test corpus
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

### Opening a session

The agent owns the transcript, so a session that is not connected has
nothing to draw and getting it back is a spawn, an `initialize` and a
`session/load`. Measured on this machine with the npx cache warm, per phase
(`src/main/acp/timing.ts` logs the same line at every load):

| | spawn + `initialize` | `session/load` | cold total | with a warm adapter |
| --- | --- | --- | --- | --- |
| Claude Code | 0.95–1.16 s | 1.41–1.47 s | **2.2–2.6 s** | 1.29 s |
| Codex | 0.66–0.72 s | 0.15–0.20 s | **0.8–0.9 s** | 0.20 s |

That was a spinner over the whole pane, and what replaces it is a paint in
**30–40 ms** with the reconnect underneath. Three mechanisms, each a module
beside `sessions.ts`:

- **The snapshot** (`acp/snapshots.ts`, migration 10). Every reduced state
  main sees is written to sqlite, debounced by 750 ms, and clicking a
  disconnected row paints *that* — 30–40 ms, measured by
  `tests/e2e/reconnect.spec.ts` — with `Reconnecting…` in the composer's row
  while the real load runs behind it. The live state replaces the picture
  when it lands, and the replay's reducer events are dropped in the meantime
  (`reconnecting` in `state/acp.ts`) or every turn would arrive twice. The
  cap is **4 KB per bulk field of a tool call** (`stream`, each text or diff
  in `content`, and `input`/`output`, which are dropped rather than
  truncated) and **512 KB of JSON per session**, met by dropping the oldest
  turns; both apply to the snapshot only, never to the live state or to
  anything the agent is told. A session created before this migration has no
  snapshot and still waits behind "Connecting to …".
- **The keep-alive** (`acp/live.ts`). Selecting another session closes
  nothing: four adapters stay alive behind the sessions that are not on
  screen, so switching back is a paint with no load at all. The oldest
  beyond four is closed and its row goes to `closed`, which is what makes
  the next click on it reconnect. A turn in flight is never evicted — the
  limit is exceeded until it ends.
- **The warm pool** (`acp/warm.ts`). A second and a half after launch, one
  idle adapter per agent the index says is in use is spawned and
  `initialize`d, and the first `create` or `load` for that agent adopts it
  instead of spawning (`warm=yes` in the timing line). It is worth the
  machinery because that is where the seconds are: measured against the real
  adapters, a load drops from 2.16 s to 1.29 s for Claude and from 0.90 s to
  0.20 s for Codex. The `spawn()` call itself is a millisecond — what costs
  is the adapter's own boot, and it shows up inside the `initialize` round
  trip.
  One per agent, handed out once and replaced. An adapter cannot be moved
  between directories, so it is matched on the `cwd` it was spawned in: a
  worktree session spawns its own. There are no sessions in the index on a
  first launch, so this does nothing until the second — and it is gated the
  way the CAD pre-warm is (`HARDCORE_PREWARM=1` under `NODE_ENV=test`).

What is left of the seconds is the `session/load` replay itself, which is
the agent's own work and is now behind a transcript rather than in front of
one.

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

### The explorer's root

A worktree is outside the project directory, so the explorer cannot be
rooted at the project alone: a session working in
`~/.hardcore/worktrees/text-to-cad/model-the-wrist` writes its STEP there,
and `open_file` on it has to open *that* file, in a tree that lists *that*
directory, served by a viewer run from it. The **root** is the concept that
carries this (`ExplorerRoot` in `src/shared/types.ts`): `null` for the
project directory, else the absolute path of one of the project's own
worktrees.

- The explorer store has an active root, derived from the active session
  (`state/bridge.ts`, `explorerRootFor`): a worktree thread's worktree,
  otherwise the project. Selecting another thread restores that session's
  strip and root; a new-session draft has no explorer. Switching starts the new root's
  watcher and keeps each root's tree state (open folders, listings) apart,
  because the checkout and a worktree are different trees with the same
  names in them.
- A file tab carries the root it was opened in (`FileTabSchema.root`) and
  keeps it after the person switches threads; the nav row shows the
  worktree's name with a branch glyph, before the crumbs and without a menu
  of its own. A terminal opened while a worktree
  thread is active starts there (`TerminalTab.cwd`). A review's
  `All changes` uses its owning session's directory. The CAD tab
  asks `cad.viewerOrigin` for its root, and main runs one `cadgen viewer`
  per root — a worktree gets its own, stopped when its last session is
  deleted.
- Every filesystem `explorer.*` request names `{ projectId, root? }`, and main's
  `rootOf` (`src/main/ipc/explorer.ts`) resolves the pair with
  `resolveProjectRoot` (`src/main/projects/workspace.ts`): the project
  directory, or a directory under the project's worktree folder, and a
  sentence for anything else. The MCP bridge resolves an agent's paths
  against the session's root the same way (`src/main/integrations/actions.ts`,
  `sessionRoot`), and the `integrations.command` it produces names the root so the
  renderer opens the file where it is. `files.changed` names the root its
  paths are relative to.

`tests/e2e/worktree.spec.ts` runs the whole path with the fake agent: a
worktree session writes a file, calls `open_file` through the MCP server,
and the tab, the breadcrumb, the tree and a new terminal all root at the
worktree; starting a new session opens an independent, empty explorer.

### CAD references and session drafts

Viewer references and captures always enter the draft of the session that owns
that viewer tab. The host carries the owner ID before any asynchronous work,
and checks that the session still exists, is unarchived, and shares the file's
workspace before accepting context. It never chooses a different destination
from the currently selected chat. The same rule applies to files, CAD, PDFs,
drawings, browsers, terminals and review selections.

New-chat text drafts remain separate per directory. They have no explorer until
a session is created. An ordinary new chat sends only its Git mode; main
chooses and validates its working directory.

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

## Embedded browser

Browser tabs borrow persistent native pages owned by the browser domain. UI and
agent tools share the same Chromium target, partitioned by project and root.
The [browser guide](docs/browser.md) documents the pinned Playwright MCP runtime,
scoped native CDP adapter, compact responses, supported operations, packaging and
validation. The upstream package owns browser tools; Hardcore owns native pages
and their tabs. No second browser is installed.

## Shared package integration

`@hardcore/ui/file-viewer` owns the whole file-tab interface. Desktop's thin
FileTab binds IPC, persisted explorer state and host commands. Renderer
registrations load shared implementations lazily. The package supplies compiled
ESM, declarations, CSS and workers; consumer source aliases, copied tokens,
JSX loaders and handwritten viewer declarations are removed.

The explorer owns one lazy CAD connection per root with open file tabs. Tab
switches borrow that connection, preserving catalog and bounded cache work while
the inactive viewport is unmounted. Closing the root's last file tab or leaving
the project disposes the connection and cancels its pending work. Each acquisition
checks main's current viewer origin; a restarted backend replaces the old client.

The STEP renderer separately retains completed STEP CPU geometry in a
bounded cache, including assemblies larger than the component LRU. Returning
to a warm file restores that geometry without reloading its components; the
file's camera, display settings and motion state remain separate. Reuse requires
the same root, backend origin and revision. Eviction or an edited file takes
the normal load path. No inactive WebGL scene is retained.

Root workspace installation keeps React, ReactDOM, Three.js and Radix identities
consistent. `viewer-peers.test.ts` verifies the installed package graph; real
Electron tests verify the rendered integration. Packaging still bundles the
complete Python runtime and native Node dependency closure.

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

### STEP inspection and replay experiment

Scripted inspection uses the bundled cadgen Python API: `read_step` for native
geometry, `read_scene` for revision-scoped selections, and `cadgen.geometry`
for exact queries. Copied viewer references resolve through `scene.resolve()`;
the retired inspect CLI is not part of the desktop agent workflow. The app's
handoff skill defers validation policy to the bundled `cad` skill. These queries
require no viewer, tessellation or inferred feature tree.

The shared Model tree infers read-only features from existing SURF geometry
when a visible part is expanded. Expansion also controls viewport selection and
exact topology loading; desktop supplies no separate tree or inference backend.
It does not consult Python source or run kernel reconstruction. See the shared
[model-tree contract](../../packages/ui/docs/cad-renderer.md#step-panel)
for isolation, reveal and selection granularity. The client-side
[feature detection guide](../../packages/ui/docs/feature-detection.md) covers
rules, cancellation and the versioned memory cache shared by the UI in both apps.
Completed results survive file switches within the renderer, but not app
restarts. Recognition is separate from cadgen compilation and Python inspection;
desktop adds no recognition service or persistent store.

Replay and GIF/video export live separately on
[`amy/step-reconstruction-playback`](https://github.com/earthtojake/text-to-cad/tree/amy/step-reconstruction-playback).
On that branch only, launch with `CADGEN_RECONSTRUCTION_EXPERIMENT=1` to test them.
