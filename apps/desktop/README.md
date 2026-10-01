# text-to-cad desktop

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

`features/explorer/FileTab.tsx` is a thin host of `@text-to-cad/ui/file-viewer`.
Its adapters translate IPC file access, source capabilities, root identity,
persistence and CAD commands into package contracts. `renderers/index.tsx` registers
the shared viewer renderers (CAD, and DXF drawings, GLB, triangle meshes (STL, 3MF) and
robot descriptions (URDF, SRDF, SDF) as their own renderers; all get the tab's backend
connection, preferences, host commands and live binding) and this app's own
Markdown, code, image, PDF and fallback renderers, which only the desktop
registers and so live beside it in `features/explorer/renderers/` rather than in
`@text-to-cad/ui` (see "File renderers" below). The whole
file-tab interface is shared with web. Projects, sessions, browser/terminal/
review tabs, agent integrations and native services remain in this app.
Neither shared package imports app source, and desktop imports no web source.
Every file tab has its own tab record (`@text-to-cad/ui/tab-store`): the viewer's
settings — the tool stack's layout — and each file's view (camera, Display
settings, preview's Playback settings, the renderer's own slices), one entry per
tab in `text-to-cad.tabs.v1` (localStorage), kept across a window reload and a
restart and forgotten when the tab closes for good (`adapters/tabStore.ts`;
`desktopTabStore(tabId)` is what the renderers and the file tab share). Nothing is
window-wide: a new tab starts from the defaults, and a preference set in one tab
is that tab's. The explorer's own chrome stays the explorer's — the panel
column's width (window-wide), each root's open folders, the open panel (with the
tab in the session strip) and the theme (an app setting in `settings`) — which is
why the record's `fileTree` and `appearance` go unused here.

## Dev

```sh
# From the repository root:
npm ci
npm run build:packages
npm run native:rebuild --workspace @text-to-cad/desktop
npm run dev:desktop  # electron-vite: main, preload and renderer with HMR
```

The Browser pane cannot show an Electron window — visual checks go
through computer-use `app_screenshot` on the text-to-cad window, or through the
Playwright screenshots below.

These environment variables matter in development:

| Variable | Effect |
| --- | --- |
| `TEXT_TO_CAD_APTABASE_KEY` | Read at BUILD time and compiled in (see Telemetry). Unset means no network call is ever attempted. |
| `CAD_DESKTOP_PYTHON` | An interpreter with cadgen installed, used instead of the bundled runtime (see CAD runtime below). A developer's knob; the e2e suite breaks and clears the equivalent setting on purpose. |
| `TEXT_TO_CAD_PREWARM` | Under `NODE_ENV=test` both pre-warms are off — the project's (viewer child, only for a root that holds a model, + cadgen daemon on project open) and the agents' (one idle adapter per agent in the index, see "Opening a session"); `1` turns them on, as `tests/e2e/cad.spec.ts` and `tests/e2e/persistence.spec.ts` do. The launch's agent probe ("Which agents are installed", under ACP) is not gated: it starts no agent. |
| `TEXT_TO_CAD_FAKE_AGENT` | Launch this stdio ACP agent instead of whatever the registry says, for every provider. The session and git suites point it at `tests/fake-agent/index.mjs`; a session needs an agent to exist at all, and a real one would make the suite a test of somebody's login state. |
| `TEXT_TO_CAD_FAKE_AGENT_ARGS` | Extra arguments for that fake agent, split on spaces (`src/main/ipc/acp.ts`). `tests/e2e/launch.ts` passes them as `fakeArgs`; `persistence.spec.ts` uses `--load-delay` to hold `session/load`. The flags are listed at the top of `tests/fake-agent/index.mjs`. |
| `FAKE_AGENT_PROFILE` | Read by `tests/fake-agent/index.mjs` from its own environment, never by the app. `claude-code` makes the fake agent answer in the Claude adapter's shape (see "ACP"). `tests/unit/main/connection.test.ts` passes it in the connection's `env`; for a dev run, set it beside `TEXT_TO_CAD_FAKE_AGENT` — main's environment reaches the agent through the login-shell capture (`src/main/agents/shell-env.ts` runs `$SHELL -ilc` with it). |
| `TEXT_TO_CAD_ONBOARDING` | Under `NODE_ENV=test` the first-run welcome and checklist are off, so a fresh test profile opens on the screen it tests; `1` turns them back on (`onboardingEnabled` in `src/main/onboarding.ts`). Outside tests onboarding is always on, and the settings fields decide whether it shows (see Onboarding). |
| `TEXT_TO_CAD_RUNTIME_CACHE` | Where `npm run bundle:runtime` keeps the downloaded python-build-standalone archives when no `--cache` is given; default `~/.cache/text-to-cad/python` (`defaultCacheDir` in `scripts/bundle-runtime.mjs`). Build-time only; the app never reads it. |

Two more decide whether the window is seen at all:

| Variable | Effect |
| --- | --- |
| `TEXT_TO_CAD_LAUNCH_INACTIVE` | `1` shows the window without taking focus, for a relaunch from a script while the person is working in another app. |
| `TEXT_TO_CAD_E2E_HIDDEN` | `1` never shows it. `playwright.config.ts` sets this for the whole suite (see Windows nobody sees, below); `TEXT_TO_CAD_E2E_HIDDEN=0 npm run e2e` puts the windows back on screen. |

## Telemetry

Anonymous counts through Aptabase, and only when two separate things are true:
a key was compiled in (`TEXT_TO_CAD_APTABASE_KEY` at build time, baked in as
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
[`@text-to-cad/ui` tokens](../../packages/ui/src/styles/tokens.css).
`src/renderer/styles/globals.css` applies `text-ui` to the body; shadcn's
`text-sm` and `text-base` controls use the same token, including menus rendered
in portals. Use this size for ordinary interface text, with smaller sizes for
secondary metadata and content-specific styles for document headings/code.
The root remains 16px at the default appearance scale, so control spacing is
unchanged; `use-appearance.ts` still scales rem-based text and layout together.

## Loading feedback

The silver text-to-cad star appears while the CAD runtime/viewer starts and while
geometry loads. An initial agent connection uses a smaller version; the live
Thinking/Running status uses a 24px mark with plain, unanimated text. Waiting
for approval holds a still pose. These reuse `@text-to-cad/ui/loading-icon` and its
baked image (no additional WebGL context). OS/app reduced motion and hidden
windows use the still image. Existing progress counts and status words remain
the source of truth.

## Onboarding

A first run opens on a welcome over the whole window instead of the shell
(`features/onboarding/Welcome.tsx`, chosen in `app/App.tsx`): three steps —
what the app is, **Connect an agent** (Claude Code and Codex, with Install and
Sign in running the same jobs as Settings › Agents, and a link there for the
rest), and a start step that offers **Try the sample** or **Open a folder…**.
Finishing or skipping sets `onboardingCompleted`. The welcome's current step is
`step` in `state/onboarding.ts`, not component state, because Settings replaces
the welcome the way it replaces the shell: "Use a different agent in Settings ›
Agents", Cmd+, or Back to app returns to the step the person left (it is held
for the window, not saved). After it, the sidebar shows a
**Getting started** checklist (`features/onboarding/GettingStarted.tsx`) whose
four items tick themselves from what the person has done — an agent installed
and signed in, a folder open, a session, a CAD file reaching the viewer
(`markViewerOpened`, called from `adapters/cadRuntime.tsx`). Closing it, or
pressing Done when it is complete, sets `onboardingChecklistDismissed`.

What the person has done is ordinary settings (`onboardingCompleted`,
`onboardingChecklistDismissed`, `onboardingViewerOpened` in `SettingsSchema`,
`src/shared/types.ts`); the renderer's derivations are `state/onboarding.ts`.
Main answers the two things that are not settings, over `onboarding.*`
(`src/{shared,main}/ipc/onboarding.ts`, `src/main/onboarding.ts`):

- `onboarding.status` — whether this run shows onboarding at all. It is off
  under `NODE_ENV=test`, so a fresh test profile opens on the screen it tests,
  unless `TEXT_TO_CAD_ONBOARDING=1`.
- `onboarding.createSample` — copies the bundled sample (`resources/sample/`:
  `l_bracket.py`, the `l_bracket.step` it builds, a README of things to ask)
  to `~/Documents/text-to-cad Sample` and answers with the project; the
  welcome selects it, unless the person went Back while it copied (main
  broadcasts no `ui.directorySelected` for it). No channel takes a directory by name. The sample is copied, never opened in
  place — a signed bundle must not be written into, and the agent will edit
  it — and a folder there that already has files in it is reused as it is,
  not overwritten. The copy is staged as `<target>.copying` (a stale one is
  discarded first) and renamed into place, so the target holds files only once
  it holds all of them. A rename that fails with EPERM, EBUSY or EACCES (Windows
  antivirus or the indexer holding the new tree) is attempted five times (one try
  and four retries) with a short backoff, then the staging tree is copied into place; a copy that dies
  there clears the target, so no half-sample is left to be taken for the
  person's own.

## Settings

Settings replaces the shell (`app/App.tsx`) and is a route, so opening it
unmounts everything under the shell. `openSettings` in `state/ui.ts` closes the
command palette and clears its query, as every other way of closing it does, so
Cmd+K after Settings opens empty.

General's **Default project folder** (`defaultProjectFolder` in `SettingsSchema`,
`features/settings/pages/GeneralPage.tsx`) is where the Open folder chooser
opens (`projects.add` passes it as `defaultPath` when it is still a directory,
`defaultPathOption` in `src/main/ipc/index.ts`); Clear returns the choice to
the OS. The choosers Settings' own path rows open (`dialogs.chooseDirectory`
and `dialogs.chooseFile`, `src/main/ipc/dialogs.ts`) start from the row's
value through `existingPath`, which drops a `defaultPath` that is missing, so
the sheet opens where the OS would have put it; for the folder chooser it also
drops one that is now a file, so it agrees with `projects.add`. A remembered
folder that is gone gets a quiet note on its row: General's Default project
folder ("This folder no longer exists, so the chooser opens where it last
did.") and Git and worktrees' Worktree folder ("…it is created again with the
next worktree."). A remembered path that is now a file gets its own wording
("This is a file, not a folder, …") and no promise of being created again,
since a folder cannot be made there.

**Settings persist optimistically** (`state/settings.ts`). A write moves the
store at once and goes out over IPC; the reply, the whole object, is the
correction. A write main refuses or fails brings no reply: the keys it owns go
back to what main last reported and a "Could not save the setting" toast says
why. Ownership is per key: while a write is in flight its value wins over an
older reply and over a `settings.changed` event, and a key a newer write owns
keeps that write's value when an older one fails. `layout`, `sidebar` and
`agentOverrides` travel as whole objects (the patch is only top-level
partial), so `setLayout` and `setSidebar` build theirs from the optimistic
state, never from a copy an old reply just reverted. On the way out main
parses each stored field on its own (`parseFields`), so one that no longer
parses takes its default and leaves the others alone. `settings.fallbacks()`
(`src/main/ipc/settings-fallbacks.ts`, read by `useSettingsFallbacks`, asked
again whenever settings change) returns `{ refused, gone }`: `refused` is every
top-level field that failed its own parse, field to stored text; `gone` is a
remembered `defaultProjectFolder` or `worktreeRoot` that parses but is no
longer a folder, field to `{ path, reason }` with `reason` `missing` (nothing
there) or `file` (a file is). A stored value of the wrong JSON type is
`refused`, never `gone`: the note for `gone` says the folder no longer exists,
which would be untrue; a path that is a file is `gone` with the `file` reason,
and its note says so. The
Git page keeps its worktree lists for the visit (`worktree-cache.ts`): a card
that mounts reads afresh over the kept list, only a change in which sessions
run where (id, cwd, worktreePath, archived) invalidates on `sessions.changed`,
a deleted worktree invalidates, and closing Settings clears the cache.

The Settings search hides a row through `useRowMatch`. The Agents page's group
headings ("Installed (4)") count the rows that search leaves, by the same row
text (`agentRowText` in `features/settings/pages/AgentsPage.tsx`), so a heading
never claims rows the search hid.

The agent drawer's Advanced fields, Extra arguments and Environment, are drafts
(`useDraft`): written on blur, and on unmount for an edit the drawer closed on
(Esc) before any blur. Environment saves as `KEY=value` records, so `useDraft`
takes a `same` predicate and the field compares the parse of its text with the
store's value; comments and malformed lines the person typed stay in the box
after the blur that saved them. A line with no `KEY=` is not saved, and the
field says which lines ("Line 3 has no KEY=value and will not be saved").

## Checks

Interaction motion is scoped to activity/thought reveals, composer reference
chips, and attachment previews: 100–160 ms, with at most 3 px of travel and a
small scale change. It does not animate streamed text, pane dimensions, or CAD
geometry. The OS reduced-motion preference and Settings › Appearance's Reduce
motion switch both suppress these transitions, app-wide: `MotionConfig` in
`app/App.tsx` carries the setting ("always" with the switch, else the OS's) to
every motion component, and the shimmer stands still under it.

```sh
npm run typecheck    # tsc over both projects: node (main/preload/shared) and web (renderer)
npm test             # vitest: tests/unit/{main,shared} in node, tests/unit/renderer in jsdom,
                     # tests/browser in Playwright's Chromium (`npx playwright install chromium`; CI installs only the
                     # headless shell, `--only-shell`, which is all they launch)
npm run lint         # eslint flat config
npm run lint:file -- src/main/index.ts   # lint named files only (same config)
npm run build        # scripts/build.mjs: compose the skills, electron-vite build -> out/, bundle the MCP server
npm run e2e          # playwright _electron against out/ — run `npm run build` first
```

`npm run build` is three steps in one script (`scripts/build.mjs`): the
app's skills are composed into `resources/skills/` (`build:skills`),
electron-vite builds main, preload and renderer into `out/`, and the MCP
server is bundled into `out/text-to-cad-mcp/` (`build:mcp`). Packaging runs the
same script. The renderer consumes the compiled shared-package exports and
bundles their lazy renderers, CSS, assets and workers. Run
`npm run build:packages` from the repository root after shared code changes;
app source continues to use HMR. Tests consume the same exports.

**The renderer's first chunk is kept small on purpose.** Five heavy modules
load with their first use rather than with the window: the review tab's Monaco
(`ReviewTab`, `React.lazy` in `features/explorer/ExplorerPane.tsx`),
xterm with the first terminal tab (`load-terminal.ts`, also fetched once the
window is idle and again when a new terminal is asked for), the CAD client
(`adapters/cadRuntime.tsx` imports `@text-to-cad/core/client` when a file's
connection is first acquired; a chunk that does not load surfaces as a
`CadRuntimeError` with reason `viewer-failed`, so the tab shows the "CAD
viewer did not start" card), Mermaid (`src/renderer/lib/mermaid.ts`, on the
first diagram; an import that fails is retried by the next diagram, as math's
is, not remembered for the life of the window) and KaTeX (`src/renderer/lib/math.ts`: `hasMath` says whether a
text may hold a formula, `useMathPlugin` imports the plugin and KaTeX's
stylesheet together on the first one, and that text is drawn untypeset until
the import lands). While a lazy tab's chunk loads, `ExplorerPane` draws a
`TabLoading` placeholder that carries `data-focus-pending`; `focusTabBody`
(`features/explorer/focus.ts`) waits on that marker instead of falling back to
the strip tab, so the first terminal a window opens still takes the keyboard.
A chunk that fails to load is drawn by the tab's own boundary as "Could not
open the review/terminal" with Try again (`lazyTab`, `TabBoundary`); a body
that throws shows "This tab hit an error" with no retry.
`electron.vite.config.ts` lists the packages Rollup must resolve to one copy in
`resolve.dedupe` — React, and Shiki with its `@shikijs/*` packages (a second
Shiki under `@streamdown/code` was ~230 grammars and themes emitted twice).
`tests/unit/main/renderer-bundle.test.ts` reads `out/renderer/assets` after a
build and fails when two chunks share a base name and a size. Without a build,
or with one older than the config, it logs why and passes; CI's Desktop job
runs it again after the build step with `TEXT_TO_CAD_BUNDLE_CHECK=1`, under
which a missing bundle fails, an assets directory with no js, css or wasm
chunks fails (an empty list of twins would call a failed build clean), and the
age guard is skipped. A plain run stands aside for both.

The unit suite caps workers at four; Electron uses one worker and no automatic
retries. The git and workspace suites take their repositories from
`tests/unit/main/git-fixtures.ts`: each shape (committed, pushed, pushed with a
remote a commit ahead) is built once per test file in a template directory and
copied per test, with `origin` repointed at the copy's own remote. CAD integration tests use `tests/fixtures/cad/import-smoke.step` and
private caches beneath their temporary user-data directories. CAD profiles use
short temporary paths on POSIX so Python's Unix sockets stay within platform
limits. They disable the shared build daemon (except its explicit prewarm test)
and discard inherited broker settings, so an interactive
cache or another running viewer cannot satisfy a cold test. No suite runs a
real agent (see below). CI selects this app only for changes to desktop,
shared UI/core, cadgen or shared build infrastructure; see the dependency graph
in the root `CONTRIBUTING.md`.

`TEXT_TO_CAD_E2E_REQUIRE_CAD=1` requires the resolved runtime to be ready and match
`VERSION`, so CAD qualification cannot pass by skipping its render, toolbar,
selection, prewarm or shutdown coverage. The macOS test job uses the checkout's
`.venv` with fresh Node/browser assets; embedded-runtime packaging has its own
qualification. The invalid-interpreter test still verifies the failure card
before clearing its override and returning to the resolved runtime.

### Windows nobody sees

The suite's windows are never shown. Every spec launches the real app, and a
run is a dozen launches: shown, they take over the screen of whoever is at the
machine, and `showInactive` only stops them stealing the focus. So
`playwright.config.ts` sets `TEXT_TO_CAD_E2E_HIDDEN=1` and main skips `show()`
altogether (`ready-to-show` in `src/main/index.ts`). Nothing else changes:
Playwright drives the renderer over the DevTools protocol, so screenshots
(taken by Chromium, not by the compositor on screen), bounding boxes, the
mouse, the keyboard and `toBeVisible()` all behave as they did, and the
screenshots below are the proof — they come back with the app fully painted on
a window that was never on screen. `webPreferences.backgroundThrottling` is off
so an unshown window keeps its frames and its timers. To watch a spec instead,
`TEXT_TO_CAD_E2E_HIDDEN=0 npm run e2e`.

A manual relaunch is unaffected: `TEXT_TO_CAD_LAUNCH_INACTIVE=1 npx electron .`
still shows the window, without taking focus.

`npm run e2e` writes screenshots beneath each test's Playwright output directory
(`test-results/` by default, or `--output`); it never rewrites the committed
design evidence in `tests/e2e/__screenshots__/`. CI uploads that run's PNGs and,
on failure, its traces and error context; both artifacts are kept for three days.
What the specs capture, and nothing else: `shell-light` and `shell-dark`;
the traffic lights' corner in the states that own it (`titlebar-sidebar`,
`titlebar-session`, `titlebar-settings` — the reserved rectangle drawn over
it); `settings-<page>` for General, Agents, Appearance, Git, Shortcuts and
About, and `settings-agent-codex` / `settings-agent-claude-code`;
`strip-overflow` (a pane at its floor with more tabs than fit, `+` pinned to
the right edge) — all from `shell.spec.ts`. From `explorer.spec.ts`, the
explorer pane only: `file-markdown-preview`, `file-markdown-source`,
`file-tree-deep`, `file-image`, `terminal`, `drawing-with-prompt` (a drawing
attached to the draft) and `browser-app-shell` (a browser tab's page and
selection added to the prompt). From `cad.spec.ts`: `file-cad-failed` (the
runtime broken on purpose) and `file-cad`. From `git.spec.ts`:
`git-review-all`, `git-review-committed`, `git-commit-panel` (the review
tab's commit strip), `worktree-explorer` and `git-settings-worktrees` (Settings' per-project worktree card, whole window).
From `session.spec.ts`: `session-new`, `session-new-model-menu` (a group per
installed provider), `session-new-mode-menu` (the `Never asks` note under the
full-access row), `session-streaming`, `session-permission`,
`session-completed`, `session-expanded`, `session-1280x800` and
`session-1680x1050`, `session-context` (the context panel, its breakdown
expanded), `session-context-limits` (the account's plan limits, from the fake
agent's `limits` turn), `session-cancelled`, `session-error`,
`session-resumed`, `session-auth`, `activity-collapsed-light`,
`activity-expanded-light` and `transcript-links`. From
`transcript-layout.spec.ts`: `transcript-light`, `transcript-dark` and
`transcript-expanded`; from `browser-service.spec.ts`, `browser-use-native`
(the native page as Browser Use captured it). A failing spec leaves Playwright's own `test-failed-<n>.png` and `trace-<n>.zip`: the launcher's test fixture (`tests/e2e/launch.ts`, which a spec imports instead of Playwright's) traces every
app a test launches and, only when that test fails, writes `trace-<n>.zip` (with DOM snapshots, which Playwright's own `trace.zip` for these specs lacks); it writes no screenshot of its own, since that would repeat `test-failed-<n>.png`.
A green test writes none of them. The committed
`tests/e2e/__screenshots__/` (`file-cad-failed`, `file-markdown-editable`,
`file-markdown-raw-blocks`, `file-tree-deep`) is older evidence no spec
rewrites. Look at them; they are the cheapest review of
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
states with `tests/fake-agent` (`TEXT_TO_CAD_FAKE_AGENT` points main at it in place
of every adapter). `tests/unit/main/mode-option.test.ts` runs the same fake with
`--mode-option`, which sends its modes as a `mode` config option instead of
as `modes`: the one mode chip has to be drawn from either shape, and an
adapter that sends only the option used to get no chip at all. `shell.spec.ts` presses
the shortcuts that need a real window, beside the pane drags, the overshoot collapse and
the traffic lights' corner; `cad.spec.ts` ends by quitting with a repository
watched, a shell, a session and the CAD viewer all running, and asserts no
child is left behind (see Quitting, below). `persistence.spec.ts` launches the app
twice against one user-data directory — a project, sessions with the fake
agent, `app.quit()`, relaunch — and asserts everything comes back and the
transcript resumes through `session/load`. It is also what a click on a
session row costs (see "Opening a session", under ACP): a disconnected thread
painted from its snapshot while the reconnecting line is still under it,
switching between two threads with no spinner either way, and — with
`TEXT_TO_CAD_PREWARM=1` on the second launch — the first load adopting the
warm adapter, asserted from main's own timing line. Its second launch runs the
fake agent with `--load-delay`, because an instant reconnect is a state nobody
can look at.

The CAD tests run against whatever runtime the app resolves on its own (see
CAD runtime, below): the bundled one once `npm run bundle:runtime` has run,
else the checkout's `.venv`. `cad.spec.ts` first breaks the runtime on
purpose — an override pointing nowhere — to see the failure card with the
interpreter's words in it, then clears the override and renders the STEP in
the same tab. It uses a fresh temporary project containing the tiny STEP
fixture, so CAD catalog reads never become repository-wide scans. The
render is skipped only in local runs without a runtime and without
`TEXT_TO_CAD_E2E_REQUIRE_CAD=1`. The first render compiles the STEP in cadgen's build
pool and is the slow assertion of the suite.

`tests/e2e/git.spec.ts` checks transient folder drafts, confirms folder
choices create no sidebar groups or explorer tabs, and exercises the
new-worktree choice through the form. Its review assertions wait, file by
file, for that file's block to carry `data-review-ready` (`review-diff.tsx`
sets it once the editor has drawn) before counting editors, so a slow run
fails on the file it was still drawing. No test talks to a model: every agent
in the suite is the fake.

Nothing in `npm test` loads `better-sqlite3` or `node-pty`: both are built
against Electron's ABI and will not load in a plain Node process. The migration
runner takes a structural `MigrationDb` so it can be tested anyway; everything
else that needs a real database belongs in the e2e.

## Brand

The sidebar uses the original faceted star in its original blue,
beside “text-to-cad” in the regular system typeface (`features/sidebar/Wordmark.tsx`).
The mark in `src/renderer/assets/brand` embeds the original star pixels with
an exterior SVG clip. It is not a path-only vector.

The Dock and packaged app icon use this same blue star on a dark tile.

TEXT-TO-CAD, set in JetBrains Mono ExtraBold Italic and drawn twice: a light-blue
copy of the glyphs offset down and right, then the foreground copy on top. No
blur and no gradient — the shadow is a second crisp copy, so the mark holds up
scaled, printed, and at 16px.

```sh
npm run brand   # resources/brand/*.png
npm run icons   # build/icon.png, from src/renderer/assets/brand/text-to-cad-star.svg
```

| File | What it is |
| --- | --- |
| `resources/brand/text-to-cad-wordmark-dark.png`, `…-dark@2x.png` | the wordmark for dark surfaces — white ink over the blue. Transparent, cropped to the ink plus one margin: 1347×196 and 2694×392 |
| `resources/brand/text-to-cad-wordmark-light.png`, `…-light@2x.png` | the same for light surfaces, ink `#0a0a0a` |
| `build/icon.png` | the app icon: the blue star on a dark squircle tile, on macOS's icon grid |

Two numbers decide how the wordmark looks, and each is a named constant in
`scripts/make-brand.mjs`:

- **The blue is `#62b7ec`**. The icon this replaced
  (`apps/docs/public/favicon.png`, still the docs site's favicon and untouched)
  is a shaded 3D render with no single hex, so the constant is the mean of its
  opaque unambiguously-blue pixels in the light luminance band: the star's lit
  faces. Its neighbours are `#3e90ce` below and `#a3e2fd` above.
- **The offset is 9% of the cap height**, right and down by the same amount, so
  the light reads as coming from the top left. Cap height, not font size,
  because that is what the eye measures an offset against. Much under 6% and the
  blue vanishes under the ink at this weight.

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
npm run brand            # the wordmark into resources/brand (committed)
npm run icons            # the sidebar star onto a tile -> build/icon.png (committed)
scripts/bundle/bundle.sh --clean  # cadgen's package runtime; ignored build output
npm run cad:resources    # the cadgen wheel + constraints into resources/cadgen (from the .venv)
npm run bundle:runtime   # THE CAD RUNTIME into resources/runtime/<os>-<arch> (~1.2 GB, once per pin)
npm run package:mac      # or :win, :linux -> release/
```

`electron-builder.yml` holds the config: appId `dev.texttocad.desktop`, and
every artifact named `text-to-cad-<version>-<os>-<arch>.<ext>`. The runtime is
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
| Windows | nsis x64 (`…-win-x64-setup.exe`) |
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
| `CSC_LINK`, `CSC_KEY_PASSWORD` (`--mac`) | signed, not notarised — on a laptop only; on CI (`CI` or `GITHUB_ACTIONS` set) the build is refused |
| `APPLE_*` without `CSC_LINK` (`--mac`, CI) | refused: notarisation credentials with no certificate to sign with |
| …plus `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`, `APPLE_TEAM_ID` | signed and notarised |
| `WIN_CSC_LINK`, `WIN_CSC_KEY_PASSWORD` (`--win`) | Authenticode-signed installer |

`CSC_LINK` is the Apple certificate and nothing else. electron-builder falls
back to it for Windows when `WIN_CSC_LINK` is unset, which would sign the
installer with the Apple cert and pin its subject as the publisher every later
update is checked against, so `scripts/package.mjs` drops the Apple variables
from any invocation that is not `--mac` and refuses `--mac` together with
another os while `CSC_LINK` is set. Linux builds are never signed. The release
workflow hands the Apple secrets to the macOS leg and `WIN_CSC_LINK` and
`WIN_CSC_KEY_PASSWORD` to the Windows leg, so adding the secrets is all it
takes to sign; until then both installers are unsigned.

`hardenedRuntime` and the entitlements (`build/entitlements.mac*.plist`) are
configured either way but only applied by codesign, so an unsigned build never
exercises them: the first check that the app launches under them is a signed
build, which on a laptop is `CSC_LINK` set by hand.

### Updates

`electron-updater` checks the GitHub Releases of `earthtojake/text-to-cad`.
Release CI builds every installer from the exact commit it tags, then creates
or resumes that commit's Release with the cadgen wheel and sdist, installers,
blockmaps and `latest*.yml` feeds as peer assets. None of those build outputs
is committed. `src/main/updater.ts` checks ten seconds after
launch and every six hours, with `autoDownload` off: the app says an update
exists and downloads when asked. Settings › About and updates is the whole UI.
Development builds report `unsupported` and check nothing; so does an install the
updater is inactive for (an AppImage run without `APPIMAGE`, a snap), whose check
answers with no result. `idle` means the feed said there is nothing newer; it
is also what a release that lacks this platform's feed file (`latest-mac.yml`
and the like, while the assets are still uploading) reads as, logged rather than
shown as an error.

An offer survives a background check. A check started from `available` does not
swap the Download button for a spinner: `update-available` refreshes the
offer, `update-not-available` retires it to `idle`, and a check that fails
leaves it on offer. A check is refused while an update is downloading,
downloaded or installing (`busyWithUpdate`): the answer is the current status,
and the feed's own events cannot knock `downloaded` back to `available`.
A failure is one sentence, never the library's text: a socket error
(`ERR_`, `ENOTFOUND`, `ECONNRESET` and the like, by the first line or the
error's code) reads "Could not reach GitHub to check for updates." (or "…to
download the update." for a download), a 404 from the provider "No release is
published yet.", any other GitHub failure "GitHub did not answer the update
check.", and anything else its first line. The renderer's own `fail`
(`state/updates.ts`), for a rejected IPC call, strips Electron's "Error
invoking remote method" wrapper to main's sentence, keeps it on the row and
toasts only the headline "Could not reach the updater". The About row is a
`role="status"` region; the download's percentage is drawn outside it, beside
the progress bar, so a number that changes every second is not read out.
A download that reports no progress for `DOWNLOAD_STALL_MS` (60 s, restarted by every
`download-progress`) is stalled: the download is cancelled (its `CancellationToken`, so electron-updater
does not hand the hung one back to the next attempt), progress it still delivers is ignored, and the
row becomes an error reading "The download stalled; try again." with Try again, which checks afresh
and starts a new download. A Restart that never quits is called stuck after
`INSTALL_DEADLINE_MS` and retried by pressing Restart again; a retry that is itself stuck has
no further recovery than quitting the app, which is a known limit.
Restart pushes an `installing` status (the row reads "Restarting…" and stays
off) until the quit; if neither the quit nor an installer error arrives within a
minute the status becomes an `error` that keeps the staged version, and Restart
can be pressed again.

electron-updater reads the latest *published* Release, so one without a
platform's feed would strand every installed app on that platform. A run whose
artifacts lack `latest-mac.yml` or `latest.yml` still tags and uploads, but
leaves the Release a draft (installed apps keep the previous feed); re-running
the failed desktop jobs re-runs the publish and releases it. Linux is
best-effort, so `latest-linux.yml` is not required.

A run resumes a version that is already tagged only when the tag points at the
commit being run and its Release is a draft or missing: dispatch the workflow
on the tagged commit. A later push with the same version, or a published
Release, stops at the gate; a `gh` error other than "release not found" fails
the gate rather than guessing.

The tag job runs on `!cancelled()` and tests only the publish job's result, so
a desktop platform that fails, or a leg that hits its timeout, delays the tag
rather than preventing it, while a cancelled run tags nothing.

### What is bundled

`resources/runtime/<os>-<arch>/` (the CAD runtime: a pinned Python with
cadgen and its whole closure installed), `resources/cadgen/` (the wheel and
its constraints) and `resources/skills/` (the composed skills) ship beside
the app as `extraResources`; all three are build outputs, gitignored under a
committed `.gitkeep`. Two more are committed and copied as they are:
`resources/sample/` (the onboarding sample, Try the sample) and
`src/main/browser/vendor/LICENSE`, which lands as
`notices/browser-use-browser-harness-js-LICENSE`. `npm run build` fills the skills; `npm run
cad:resources` fills the wheel directory from a checkout after verifying the
ignored cadgen `_runtime` bundle is complete (the release
workflow drops the wheel it just built into it instead); `npm run
bundle:runtime` fills the runtime from those two (the release workflow runs
it per leg: macOS bundles `mac-arm64` natively and `mac-x64` cross, Windows
and Linux their own). The MCP server ships inside `out/text-to-cad-mcp/`,
unpacked from the asar so an agent can run it by path. See
`resources/README.md` for the bundler's steps, the cross-target rule and the
signing note.

The release workflow checks out without git-lfs, and the root tracks `*.step`
in LFS, so a checked-out resource can arrive as a 130-byte pointer.
`scripts/package.mjs` looks through every checked-out extraResource after the
build and refuses to package one that is a pointer — take it out of LFS with a
`.gitattributes` beside it, as `resources/sample/` has, or `git lfs pull`.

A runtime is current only for the wheel it was installed from. `bundle:runtime`
records the wheel's name and `wheelSha256` in the runtime's `runtime.json`,
and `scripts/package.mjs` treats a bundle whose hash differs from the wheel now
in `resources/cadgen/` as missing. `npm run cad:resources` rebuilds the wheel
under the same `cadgen-<version>` name but with a new hash, so a
`bundle:runtime` has to follow it before the next package.

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
`tests/e2e/shell.spec.ts` walks those states and fails on a control whose box
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

**No session, no explorer.** The pane belongs to a session: with none
selected (the new-session screen), `Shell` renders neither the panel nor its
separator, the session pane has the window, and the toggle in the title bar,
the palette's `Toggle explorer` row and its chord (Cmd+Option+B on a Mac, Ctrl+Shift+E elsewhere) are all absent or inert
(`setCollapsed` in `state/explorer.ts` refuses a preference it has nowhere to
file). Selecting a session brings the pane back with that session's own
remembered state.

**The sidebar is sections, not a tree** (`features/sidebar`, Claude Code's
shape). Its header is the app's wordmark alone. Under it is a nav list of
one row, `New`: a plus in an accent ring, the new-session screen and the same
thing `Cmd+N` does — and at that row's right the two controls that act on the
whole list, search (the command palette) and the sliders that open the filter
menu (`features/sidebar/Sidebar.tsx`).
Under that, one grey header per project with a flat list of that project's
threads. The header is the project: its name and a chevron that collapses the
section (persisted per project in `settings.sidebar`), and on the right `+`,
a thread in *that* project — and nothing else. A search glyph and a copy of
the sliders used to appear on it on hover; neither was ever about one project
(the palette searches every thread and the filter settings are global), and a
control that only exists under the pointer is a control nobody finds.
The header's right-click menu starts a session, copies the directory path,
or reveals it in the OS. Revealing a project directory — here, from a
session's header menu and from Settings' worktree cards — is
`shell.showItemInFolder({ projectId, root?, worktrees? })`: the project, one
of its own worktrees (`root`), or the folder its worktrees live in
(`worktrees: true`). It never takes a bare path; main resolves the request
against the project and refuses anything else (`src/main/ipc/explorer.ts`).
The session's own header menu, the `…` beside its title
(`features/session/SessionHeader.tsx`), is Rename, Copy path, Reveal in
Finder (Show in Explorer on Windows, Show in file manager on Linux — `revealLabel` from the UI package, as the explorer's entry menu and Settings use), then **Disconnect agent** — main closes the adapter and the
transcript stays on screen, marked closed, under a Reconnect bar (a turn
that was streaming ends there, its running tool calls cancelled) — or, for a
session already disconnected, **Reconnect** in its place; then Archive and
Delete.
There are no project rename or delete actions: these
are directory groups derived from sessions, not saved project records. A
directory with no matching sessions has no sidebar header. Archiving or
deleting its last active session removes its active group; archived sessions
leave the sidebar and come back through the filter menu's `Status` → Archived, where a row's `…` offers Unarchive
(Settings has no list of them). Archiving, from the row or the session header, toasts "Thread archived." with an
**Undo** that unarchives it. Worktree sessions group
under their original checkout directory. Selecting a new folder opens an
in-memory composer draft; its group appears only when a session is created. A session row is its **state** as a leading glyph (a hollow
circle idle, a pulsing dot while a turn streams, a ringed dot in the info
colour waiting on a permission ("it needs you", not a warning), a red triangle after a failure, a spinner ring connecting —
`lib/sidebar.ts`), the title, git's own glyph when the thread runs in a
worktree or on a branch of its own, and a `…` on hover or when it takes
keyboard focus, for pin, rename, archive and delete. `Pinned` is the first section when anything is pinned,
and a pinned thread lives **only** there — never twice.
A collapsed project's header carries the strongest state among the rows it
hides — waiting over working — as the same glyph, named for what it counts ("1
thread waiting for you"), so a thread that needs the person is never out of
sight behind a collapse; an expanded section shows the rows and no extra mark.
Rename in the row's menus (and the header's) only flags the choice; the box opens once the menu has closed, from `onCloseAutoFocus` (see "Focus coming back"). A pin, archive or delete that main refuses leaves the thread as it was (main writes the row first and only then closes or retires the adapter, so a refused write has touched nothing) and says so in the rename's shape — "Could not pin
(unpin, archive, unarchive, delete) the thread: …" — and a refused archive or delete keeps the open session open — a delete whose rejection leaves no row behind (the renderer re-reads the list) is not refused, the thread is gone. A delete whose row is gone but whose disposal throws still succeeds, keeping the worktree on disk.

The filter menu is global, and it is opened from the panel's own header:
`Status` (Active / Archived / All), `Environment` (All / Local / Worktree —
our git modes), `Group by` (Project, or None for one flat list), `Sort by`
(Last activity / Created / Name) and `Show branch`. *Last activity* is `updatedAt`, which a prompt, a turn opening or
closing, a permission asked or answered, a title or a rename moves — and a connection's own life (opening a closed
thread, a keep-alive eviction, a failed connect), a pin, an archive and an unarchive (so Undo puts the row back where it was) do not, so rows do not jump under the pointer. It is stored in `settings.sidebar` and applied by one pure
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
its own width: from 720px up, the file tree — a CAD file's one host panel —
is drawn in the file tab's own panel column beside the model (see "The panels
a file has"), and the tool stack hangs under the viewer's toolbar; below it
the tree is a floating sheet over the model, the crumbs collapse to the file
and the view cube is hidden. The explorer pane opens at 740px
(`PANE_LIMITS.explorer.default`), so a fresh pane in the default 1440px window
is the wide layout, with room for the 220px panel column beside the model; a narrower window or a dragged
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
are relative to the thread's root — its worktree when it has one — and an
absolute path (`/Users/me/proj/models/a.step`) links when it lies inside that
root, read against it (a root with a space in it too: `remarkPathLinks` is given
the root); one outside the root is only words, since nothing outside the
project opens in the explorer. The plugin marks an absolute path's URL
(`?abs`), because rehype-harden spells a workspace path `/models/x` too and
`/etc/hosts` would otherwise read as `<root>/etc/hosts`; a link the agent wrote
by hand with a leading `/` is still read as a workspace path. An image at an
absolute path under the root is read the same way. A failed `explorer.exists` is not
an answer: the path stays words and is asked again on the next hover or click
(and at the next `files.changed`), not pinned as "not a path".

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
Enter sends and Shift+Enter breaks the line, as the shortcuts table says; no
other Enter chord does anything (the editor's hard break is rebound to
Shift+Enter alone, so Cmd/Ctrl+Enter does not add a line).

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
References open relative to the session’s workspace or the new draft’s pinned
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

A drop is accepted across the whole session view — the transcript, the chips
row and the queue strip as well as the box — and goes through the same sort. A
composer that is disabled (no live agent) takes no drop at all: the drop does
nothing and the cursor reads not allowed.

A file is sorted the moment it is attached (paperclip, paste or drop), not
when the prompt is sent. Images and UTF-8 text up to 256 KB
(`MAX_INLINE_TEXT_BYTES` in `composer/attachments.ts`) attach as before. An
image over the model's limit (`MAX_IMAGE_BYTES`, the file size whose base64
stays under 5 MiB, the same cap a viewer capture is fitted to) is redrawn
smaller as a PNG when it is attached, and a toast says so when that changed what
the file is — an animated GIF or WebP comes out a still image ("<name> was scaled
down to a still image to fit the model's limit."), any other format a PNG (an
animated PNG is read by its type, `image/png`, so it is not told apart from a
still one and gets no still-image notice); one that cannot be brought under it is
refused with "<name> is larger than the model takes (about 3.75 MB of image)
and could not be scaled down, so it was not attached." The send checks again
and drops such an image with the same sentence. A
CAD file the viewer renders (`CAD_EXTENSIONS`) never goes in as bytes: one
already in the project folder — matched by name and byte size, since Electron
gives the renderer no path for a picked file — is inserted as its path, the
same token a typed reference chip sends; one outside the folder is refused
with a note to copy it in and refer to it by path. Any other binary, and text
over the cap, is refused with the reason. A prompt holding a block the agent's
`promptCapabilities` say it cannot take — an image, a file's contents — is
refused by main before any turn starts (`refused` on the `sessions.prompt`
reply, `src/main/acp/sessions.ts`): the session stays idle, the composer keeps
the draft, and a toast says why — naming the agent and what to do ("Codex
cannot take an image in a prompt. Remove the attachment to send.",
`SessionConnection.refusal`). The attachment strip empties with the text when
the message is accepted, not when its turn ends (`prompt` settles at the end
of the turn); a prompt refused afterwards puts its files back in the strip. A queued prompt main refuses goes back into the
box as it was taken, behind any put back before it, so the box reads in queue
order, and the queue goes on. A prompt that is out but whose turn has not started (the box is `submitted`, while the
session still reads idle for a moment) queues the next one too: Enter in a session sends then and the prompt goes behind it,
though the button keeps its spinner (`queueWhileSubmitted`, which `SessionView` computes in `composerFlags`, `features/session/view.ts`:
true only while a prompt is in flight (`sending`) on a session that is not itself still connecting or loading). A box that reads
`submitted` for a first load or a create does not take Enter: its prompt would race the setup. The new-session screen never passes it,
because its `submitted` is a create in progress and a second Enter would create a second session. Two Enters before the first has
taken the draft (it awaits the attachments' bytes) send once: `Composer` holds a synchronous guard from Enter to `takeDraft`. A turn the person stops (Stop or Esc) with something queued pauses the queue the way a failed one
does (Stop with nothing queued pauses nothing): the queue row reads "Paused after you stopped" with the same Resume (the reason is kept on the pause, so a Resume main then refuses reads "Paused after an error"), and
the next queued prompt waits for it (or for a prompt typed meanwhile, which goes
out first) instead of starting behind the Stop. A new session's first prompt refused this way
goes back into that session's box — the session was created and selected
before the prompt went out (`NewSession.tsx`); only a create that fails keeps
the new-session screen, with the error and Try again. A create that fails with
the person elsewhere (on another thread, or another project's new-session
screen) shows a toast with the error and Try again, which returns to the
new-session screen that holds the restored draft. A create that outlasts a
click on another thread or project does not pull them back to the session it
made. Whatever the error, the card on the screen carries Try again (it sends what
the box holds, as the sign-in card's does; a box emptied since gets the failed
attempt's text and notes back first, so it retries the last form values, and the
button is drawn only while there is an attempt to retry) beside Open Settings › Agents and Dismiss.
Settings' "New session in this worktree" (`runUiCommand`, `new-session` with a
`cwd`) closes Settings before it starts the thread; if the start fails a toast
says "Could not start a session in this worktree: <reason>" rather than leaving
a bare console line.

Image attachments show a contained thumbnail beside the filename, with an always-visible remove control. Click the thumbnail (or focus it and press Enter) to inspect the full image. Escape, Close or the backdrop dismisses the preview and returns focus to the thumbnail; the draft is unchanged. Explorer tabs use a bordered active state and visible keyboard focus on selection and close controls.

The viewer's Copy Reference(s) button, ⌘C and the copy items in its menus are
clipboard-only. A STEP's viewport and model-tree menus also offer **Add to
prompt**, which adds that reference to the draft, and the navbar's snapshot
adds the current view and the selected references together. Each tab delivers
only to the session that owns it. A workspace mismatch is rejected, and
switching to another session never redirects context. Nothing is sent until the
user submits.

FileViewer receives an explicit `ViewerHost`: workspace files/actions, live
documents, native clipboard, prompt delivery, navigation and environment
(appearance, keyboard platform and the app's reduced-motion setting).
Follow the [shared host contract](../../packages/ui/docs/viewer-host.md) when
adding integrations; native effects and session workflows belong in this app.
Prompt delivery binds the tab's immutable owner session when the host is
created, validates the entire bundle before one acceptance, and preserves its
text/reference/attachment order. Changing sessions before or during encoding does
not redirect the result or steal composer focus. Deleted or archived
destinations cancel delivery. Recent operation receipts are bounded to 256
entries; pending captures are bounded to 16. Bundles accept at most
128 parts. Attachments must be supported images or UTF-8 text, at most
20 MiB each and 40 MiB together. Ordinary clipboard effects use the validated
`clipboard` IPC branch for plain text and PNGs up to 16 MiB; the renderer never accesses
Electron's native clipboard directly. A copy button on the page (the vendored
components', Copy path, the terminal's selection) writes plain text with the web
`navigator.clipboard.writeText`, which the app's permission handler allows as
`clipboard-sanitized-write`.

Incoming CAD selection and capture requests bind the project, tab, path and root
at request time. Only that active document receives them; replacing or closing
the target clears them. Nonce-specific acknowledgement prevents consumed requests
from replaying when the viewer remounts, while a repeated reference click creates
a fresh request.

Each changed file in Review has **Request revision**. It appends the file and
review scope to the draft, plus selected original or modified code and its line
numbers when present, and focuses the composer for the requested change.
Review stays current on its own: file changes re-read git's status, at most
one read per 500 ms (`STATUS_GAP_MS` in `ReviewTab.tsx`), and re-read only the
diffs of files the answer says changed. A diff that cannot be read says so,
with git's words and a Retry. A refresh that fails keeps the last answer on
screen, marked stale under a "Could not refresh" line with Try again.
A failed or timed-out `git show` is never drawn as an empty side (a file that read
as wholly added while its header counted +3 −2): the diff fails with "could not read
<path> at <revision>: <git's words>". A submodule is one line, "submodule <path> at
<sha>", on each side, not an empty editor. A failed commit keeps git's lines as
lines, and the messages above are shown without Electron's "Error invoking remote
method" wrapper.

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
probe never fetches the pinned adapter for an agent the detector does not list
as installed (`SessionManager.canProbe` in `src/main/acp/sessions.ts`; a
launch override such as `TEXT_TO_CAD_FAKE_AGENT` counts as installed): a
session is something a person asked for and worth a download, a probe is
speculative. An agent that cannot answer — not installed, not signed
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
while: the agent's own mode *and* an approval setting of text-to-cad's own ("Ask"
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
then `Open folder…`: the native folder chooser, followed by that folder's
new-session screen (`hooks/use-open-folder.ts`). The palette, the session pane
and the chip use `useOpenFolderOrToast`, which says a chooser or `projects.add`
that rejects in a "Could not open that folder" toast and reads as a cancelled
chooser; the welcome keeps its own inline line on the plain `useOpenFolder`. The
chooser opens at Settings › General's Default project folder
(`defaultProjectFolder`, empty for the OS's choice) when that folder still
exists as a directory; a moved or deleted one is left out. Codex's shape, minus its
`No folder` row: a session here always belongs to a folder. There is no
`Add project` button, because adding a folder *is* choosing one. The one
state with no chip to open — no folder at all — is the "Choose a folder to
get started" screen, whose own `Open folder…` button is the chooser
(`features/session/SessionPane.tsx`); the sidebar then says only "No sessions
yet". The command palette has the row for the keyboard.

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

## Keyboard

Every shortcut is a row in `src/renderer/lib/shortcuts.ts`, which Settings ›
Keyboard shortcuts prints. A row holds two bindings when the platforms differ: one that would arrive as AltGr
off a Mac carries an `otherBinding` (`bindingFor` in `lib/shortcuts.ts`). Toggle explorer is Cmd+Option+B on a Mac and
Ctrl+Shift+E elsewhere, in the menu (`main/menu.ts`), in `Shell`'s key handler and on the page; the toast chord
(`components/ui/sonner.tsx`) is the row "Focus the notifications", Cmd+Option+T on a Mac and Ctrl+Shift+T elsewhere, and
is renderer-only (no menu accelerator). A chord with Option on a Mac is matched on the physical key
(`event.code`, `KeyB`), because Option+B types "∫" and `event.key` is never "b" (`Shell`'s handler; the
toast chord's hotkey is `KeyT` already; no other chord uses Alt). The ones the app menu also declares are its accelerators, so
they work with focus inside a webview (see "Rules that are easy to break" in
AGENTS.md). The menu's New Session and Settings… with no window open one and
hold the command until its page calls `ui.ready` (`src/main/menu.ts`): pushed
at load, it could arrive before the page listened. A view toggle with no
window does nothing.

**Landmarks and panes.** Every route has exactly one `main`. In the shell the
session is the `main`, the sidebar an `aside`, the explorer a named `section`,
which also scopes each pane's own `<header>` (`app/Shell.tsx`); Settings and
the Welcome each have their own `main`. Settings' nav is named "Settings".
While a query is typed the pages are stacked under one visually hidden h1
("Search results") with each page's title an h2, and a status region, there
before the first keystroke, says "N rows match" (it counts rows, not pages).
The composer's editor is named "Prompt", and the document title is
"text-to-cad — Settings", "text-to-cad — Welcome", or "text-to-cad — " followed
by the selected session's title (`app/App.tsx`). F6 and Shift+F6 move focus to the
next and the previous pane on screen, skipping one that is shut, and on the
window's capture phase, so they work from inside an editor or a terminal. Where
focus lands in a pane it has not been in (`PANE_HOMES`) lives in
`app/pane-focus.ts`, which F6 and the return from Settings share. Focus returns to where it
last was in that pane while that element is still there; the first time it
lands on the sidebar's current session, the composer, or the explorer's strip
tab, else the pane's first control. A pane that closes with focus in it — ⌘B,
⌘⌥B, its toggle, a drag past its minimum — hands that focus to its toggle,
now in the session's title bar, so the next ⌘B or Enter brings the pane back
(`useFocusSurvivesCollapse`). ⌘⌥B opening the explorer takes focus into it:
its strip's tab, else `+`.

**The explorer.** The tab strip is one Tab stop (`TabStrip.tsx`): the arrows,
Home and End move focus between tabs without selecting them — manual
activation, because a selected terminal or browser tab mounts a pty or a
webview — and Enter or Space selects; Delete closes the focused tab and focus
goes to its neighbour, or to `+` after the last. The file tree is a roving
single Tab stop as well (see "The file tab's nav"). A file opened from a tab's
tree or crumbs takes focus with it, to the tree's cursor row in the new tab
(`features/explorer/focus.ts`); a tab the person opens or picks gives its body
focus when the body can take it (a terminal once its shell is attached), else
its strip tab. Monaco and the terminal would keep Tab for themselves: Ctrl+Shift+M
on every platform toggles tab-focus mode (Monaco's own binding on macOS, added
elsewhere in `renderers/code/editor/setup.ts`; one switch for every terminal
in `TerminalTab.tsx`), and while it is on Tab and Shift+Tab leave the editor
or the shell.

**Focus coming back.** Whenever the control that has focus unmounts, focus is
handed on, and an action that is refused leaves it on its control. The command
palette and Settings' agent drawer hand focus back to what had it when they
close (`hooks/use-return-focus.ts`), since neither has a trigger for Radix to
return it to. A permission answer goes to the composer; one main refuses keeps
focus on the card, which says why. Rename opens its box only after the menu that chose it has closed, from the menu's `onCloseAutoFocus` (the row's `…` menu, its context menu and the session header's menu): while the menu is still closing, Radix's focus scope takes focus off the box and then hands it to the trigger, and either blur would commit the draft. Rename's Enter or Escape goes to the title
button, and settles the edit for good: a blur that follows (a browser may blur the
box as it unmounts) commits nothing, so Escape never renames. Enter on a pane separator closes the pane and hands focus to that pane's
toggle (the separator reads its width through `aria-valuetext`). A
disconnected session's Reconnect bar goes away with its button, so focus waits
on the composer's row and goes into the box once the agent is back; every
Reconnect, Retry, Install and sign-in retry on the session screen, the
transcript's included, goes through the composer handoff, `handToComposer`
(`features/session/SessionView.tsx`; `reconnectFromBar` is it plus the load, and the
transcript's Retry is it plus the resubmit), for the same reason. The transcript's Retry is one resend at a time: from the first click the button is disabled and reads "Retrying…" until the resubmit settles, and `retry` ignores a second call while one is out, so a double-click cannot queue the same prompt twice. Leaving Settings
unmounts the button that had focus, so `focusSessionHome` (`app/pane-focus.ts`)
puts it in the composer, waiting one frame for the editor to mount. The
context ring takes focus into its panel on open and gets it back on close.
A global chord is checked on all three platforms before it is bound: it must
not type a character with Option on a Mac, must not arrive as AltGr
(Ctrl+Alt) on a European keyboard, and must not be GNOME's Ctrl+Alt+T. The
toast list's chord, Cmd+Option+T on a Mac and Ctrl+Shift+T elsewhere
(`components/ui/sonner.tsx`), moves focus into the notifications, and is not a
row of `lib/shortcuts.ts`: its binding differs by platform, and the table holds
one portable string per row. Toasts sit top
right under the title strip (`app/App.tsx`), clear of the composer they would
otherwise cover. The selected session row and Settings' current page carry
`aria-current="page"`. A session row's keyboard focus ring is drawn around the
whole row (`has-[[data-session-row-title]:focus-visible]` in
`features/sidebar/SessionRow.tsx`), not around the title button inside it. The
command palette leaves out its Sessions group when there is no open session. A
session row is searched on its title, its project's name and its branch, and a
project row on the project's name only; ids and paths are not text to match
(`scoredOnKeywords` in `app/CommandPalette.tsx`).

## The explorer strip

The strip's `+` is one button and a menu of the five kinds, each with its
binding — ⌘T file, ⇧⌘R review, ⇧⌘B browser, ⌃` terminal, ⇧⌘D drawing
(`lib/shortcuts.ts` is the table the menu prints and `useExplorerShortcuts`
in `ExplorerPane.tsx` answers to). It sits **after the last tab, inside the scrolling row**, and is
`position: sticky` at its right edge: it slides along with the tabs until the
row is longer than the pane, and then stops at the pane's edge with the tabs
passing underneath it. In the flow alone it was the button that scrolled off
at six tabs in a 45% pane; pinned outside the row it was always reachable and
never part of it. The file tree's open folders and its listings live in the explorer
store, not in the file tab, because opening a file makes a tab and the pane
mounts one tab at a time. `listDirectory` stats a directory's entries 64 at a
time (`LIST_STAT_BATCH` in `src/main/explorer/fs.ts`).

The strip's chords are `useExplorerShortcuts` (`ExplorerPane.tsx`), mounted by
`Shell` because the pane is not rendered while collapsed. With no session every
chord falls through to the menu. The open-a-tab chords run with the pane
collapsed, because `open` reveals it; ⌘W and ⌘1..9 act on tabs the person
cannot see then, so they fall through to the menu too (⌘W closes the window).
A held key (`event.repeat`) is swallowed rather than repeated, ⌘W included even
once the last tab is closed, so it does not go on to close the window. On
Windows and Linux the plain Ctrl chords are skipped while the focus is inside a
terminal (`[data-terminal-body]`), where they are the shell's; the Ctrl+Shift
chords and Ctrl+` still run there.
Ctrl+` is matched by the physical key (`event.code` "Backquote"), so a layout where the
backtick is a dead key, and sends "Dead", still opens a terminal.

A tab is reordered by dragging its chip (a plain HTML5 drag). The insertion
line is drawn before the chip under the pointer on its left half and after it on
its right half, so the last position is reachable. The move happens when the
chip is dropped; a drag that ends any other way (Escape, a release outside the
strip) reorders nothing. A file tab's tooltip is its path, always; any other
tab's tooltip is its title, shown only when the chip clips it. A terminal the
agent opened (`tab.agent`) shows an "agent" badge in its footer; the tab's
`readOnly` field is stored as false and nothing sets it.

The review and terminal bodies are lazy tabs (`lazyTab` and `LazyTab` in
`ExplorerPane.tsx`). A chunk that fails to load lands in the tab's boundary
(`TabBoundary`) as a `ChunkLoadError`: "Could not open the review" or "Could not
open the terminal", with Try again, which builds a fresh `lazy` and fetches the
chunk again. A body that throws while rendering shows "This tab hit an error"
with the error's message and no Try again, because fetching its chunk again
would throw again.

Every session owns its own explorer tabs, active tab, expanded folders and pane
width/collapse state. A new session starts empty, including another session in
the same directory. A new-session draft has no explorer until a session exists.
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
Both write the session row first and tear the tools down after, so a write that
throws (a locked database, a missing row) leaves the session active with its
tokens, pages and shells intact.
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
sessions cannot redirect the result. Deleted or archived sessions cancel delivery.

Drawings live only in renderer memory. Switching tabs or sessions keeps them;
closing the tab, archiving/deleting its session, reloading or exiting discards them.
An image already added to a draft or transcript is a separate copy. This
scratch surface has no file import/export, autosave, Mermaid insertion, image
embedding or scene-editing MCP tool. The `drawings` integration provides
`open_drawing({title?})`, `rename_drawing({tabId,title})`, `drawing_state({tabId})` and
`capture_drawing({tabId})`. Opening a saved `.excalidraw` as a regular file
continues to show its source text.

The shared editor is `@text-to-cad/ui/drawing`; desktop owns its temporary
lifetime and prompt port. Fonts are bundled for offline use by the shared
`@text-to-cad/ui/drawing-assets` Vite plugin (desktop ships the full set) and the
editor loads only on opening a Drawing tab. Read [the drawing contract](../../packages/ui/docs/drawing.md)
for limits, asset licensing and the reuse boundary for future CAD overlays.

### File renderers

The shared viewer renderers come from `@text-to-cad/ui/renderers/*`. Markdown, code,
image, PDF and the unsupported fallback are this app's own, because web
registers none of them: `features/explorer/renderers/{markdown,code,image,pdf,unsupported}`,
each a `defineFileRenderer` registration from `@text-to-cad/ui/file-viewer` over the
package's public exports only (the contract a host renderer may rely on is
`@text-to-cad/ui`'s [renderer contracts](../../packages/ui/docs/renderers.md)).
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
PDF.js's real worker, text selection and capture in Playwright's Chromium. A browser
harness gets a fresh dependency cache per run (`cacheDir` a new temp directory) and
names what Vite's scan cannot see (`optimizeDeps.include`: `react/jsx-dev-runtime`,
the automatic JSX runtime), then asserts the page loaded once; a late discovery
re-optimises and reloads mid-test, and a stale cache would hide it locally and show
it in CI.

### Live files and terminals

A file tab keeps its `file` kind and chooses a renderer: CAD, PDF, Markdown,
code, image or unsupported. The `documents` integration reads the live text
buffer, including unsaved typing, and requires its revision before replacing
or saving it. `read_document` returns at most 2 MiB of characters
(`MAX_DOCUMENT_CHARS`, held equal to the renderer's `MAX_BRIDGE_DOCUMENT_CHARS`
by `live-documents.test.ts`); past that `truncated` and `note` lead the JSON,
ahead of `content`, so a client that clips the tail keeps them, the cut backs
off a split surrogate pair, and the revision still names the whole buffer. A
buffer over the cap cannot be edited through the bridge — the edit is refused
and the person edits it in the editor. Tab/session switches retain drafts and inactive read snapshots;
reactivate a text file before editing or saving. A text file over 4 MiB
(`MAX_TEXT_BYTES` in `src/main/explorer/fs.ts`) opens read-only, cut at the
cap, and one whose bytes are not UTF-8 opens read-only too — a save would
write replacement characters over them. A `files.changed` event carries a
content `revision` only for a changed file a tab has open and that is within
the cap, so the editor that saved can tell its own write from an agent's;
nothing else is read. Dirty tabs refuse ordinary
and agent-driven close; the UI provides explicit discard. These drafts last
for the app window, not across quitting. PDF tools operate on the same PDF.js
document as the page on screen. See [workspace integrations](docs/integrations.md)
for the complete tab/renderer/integration mapping and lifecycle rules.

Terminal tabs are views of main-owned PTYs. Switching tabs does not stop a
process or lose its scrollback. The `terminals` integration creates, reads,
writes and stops those same PTYs through scoped tab IDs. Reads return an output
sequence and input revision; writes require both, preventing a tool from racing
new output or user typing. Closing a terminal releases its process; stopping
it leaves the output available until close. `stop_terminal` signals the shell
and waits up to two seconds: `exited: true` with the `exitCode`, or `exited:
false` when the program is still running. A provider's own shell tool has
separate process IDs and does not automatically create a text-to-cad terminal tab.
A session holds at most 16 ptys, stopped ones and the person's own included
(each keeps its scrollback until its tab closes); `create_terminal` refuses past
that, checked before the pty is registered so concurrent calls cannot overshoot.
`explorer.loadTabs` releases a saved `ptyId` that no live pty of the session
answers to, so a restored terminal starts a fresh shell instead of attaching to
one that died with the app; a live pty (a renderer reload) keeps its id. A tab
the agent opened carries `agent: true`, and its respawn through
`terminal.create` puts the runtime launchers in front of `PATH` again.
`TerminalTab`'s key handler copies a selection on Cmd/Ctrl+C and passes Cmd/Ctrl+K
to the command palette. Paste is xterm's own paste listener, which brackets the
text when the shell asked for it; the Cmd/Ctrl+V branch of the handler only
returns false so Ctrl+V does not reach the shell as `^V`, and writes nothing (a
second write ran a pasted command twice, once unbracketed).
A shell that ends is said so over the footer, not in it: a `role="status"` banner reads
"The shell exited (code N)." with a Try again button, which kills the old pty and
starts a fresh shell (the lazy-tab error pattern). A pty that cannot be attached to,
or written to, puts the unwrapped sentence from main in the same banner, and a spawn
that fails shows it under "No shell" without Electron's "Error invoking remote
method" wrapper.

A terminal an agent asks for through ACP's `terminal/*` (`src/main/acp/terminals.ts`)
is separate from those ptys, and its output reaches the transcript's activity row
as `terminal.output`. A released one hands over nothing more: no chunk and no
exit. A process that exits having written nothing sends its exit chunk with
`silent`, and the store (`receiveTerminalOutput` in `state/acp.ts`) then clears
that terminal's cold mark, so the row reads `(no output)`. A terminal already in
a state when the store took it (a snapshot, a reload, a background session's
reconnect) is cold: a finished command whose output the store never held reads
"Output not kept after reload" instead.

Over IPC (`terminal.*`, `src/shared/ipc/explorer.ts`), `terminal.create` takes
the project, the session, an optional `cwd` (checked against the project and
its worktrees) and the size — never a shell or its arguments: every tab runs the person's login
shell (`src/main/explorer/terminal.ts`). After that a pty is named by
`{ id, sessionId }` on `terminal.write`, `resize`, `attach` and `kill`, and
main refuses a request whose session does not own the pty, so one session's
renderer state cannot type into another session's shell.

Directory listings show every regular file and directory, including every
dotfile except `.git` (the tree and the filter leave out Git's own folder, or
the `.git` file of a worktree, unless the open file is inside it),
Git-ignored outputs, dependency folders and unsupported formats. Renderer
support determines what opens in the file tab; it never hides a tree row.
Unknown types open with **Not supported**. Previews that cannot be shown keep the same way out:
an image or PDF over the 24 MB preview limit (`PREVIEW_LIMIT_BYTES` in `FileLoadError.tsx`, which
`file-preview-errors.test.tsx` holds equal to `MAX_BINARY_BYTES` in `src/main/explorer/fs.ts`) reads
"This file is too large to preview" with "<name> is <size>; previews open files up to 24 MB.", an
image the browser cannot decode reads "This image could not be decoded.", and a PDF that PDF.js
refuses reads "This PDF could not be opened: <reason>." with no page toolbar. Each offers Open
externally when the host has it. Listings are lazy and complete for each expanded directory. The
filter lists at most 200 matches and the index holds at most 20,000 files; when either cap cuts
something it says "Showing the first 200 of N matches; the index stopped at 20,000 files" (or "The
index stopped at 20,000 files; some matches may be missing"), and an index that cannot be read says
"Could not search the files: <reason>". The bounded fuzzy index visits project content before
dependency caches so cache files do not crowd generated CAD outputs out of the
search budget. `listPaths` reads the next 16 directories (`LIST_READ_AHEAD`)
while it takes the current one apart, and consumes them in the order they were
found, so a capped walk returns the same paths a serial one would
(`scripts/bench/explorer-list-paths/` compares the two, manually). Background recursive watching respects the root's Git ignore
rules and excludes dependency caches so packaged runtimes do not create tens
of thousands of watchers. Every browsed directory and every opened file's
parent receives a direct watch, including Git-ignored outputs. Those files stay
live without expanding their folders, and all watches close when their root's
last owner leaves.

An opened file is held per path (`FileWatchers` in `src/main/explorer/fs.ts`),
with its inode. The watcher reports a rename as a removal and an addition, so
a batch that removes an open file waits `MOVE_WAIT_MS` (250 ms) for the
addition, and a removal and an arrival with the same inode become one `moved`
change: the tab follows the file to its new name, and its holds go with it.
The app's own save is an atomic rename, a new inode at the same path, so the
inode is taken again whenever the file changes under its name. A removal drops
the path's inode; when a path a tab still holds reappears (a checkout away and
back), the inode is taken again on its arrival. An opened link
is an alias: its target's directory is watched and the target's changes are
repeated under the link's name; the link's own inode is its identity. When
`ln -sfn` re-points it, the inode is taken again and the alias moves to the
new target (a target outside the root is none), so its changes are the ones
repeated and renaming the link still moves its tab; moving the target leaves
the link dangling — a removal to its tab. A linked
directory lists its children under the link's own path (`links/vendor/a.txt`), read through the
real one, so a link and its target never produce the same row twice. A
tab that remounts gives its paths back and takes them again; a release that
overtakes the watch it follows is counted (`arriving`, `owed`) and given back
once that watch holds, so no hold is left behind.

A watcher that dies, or cannot start (on Linux, usually the inotify limit),
is not left silent: main publishes `files.watch-error` and the renderer toasts
"Live updates stopped: <reason>. Reload the tab to re-arm them." once per root
(`reportWatchFailure` in `state/explorer.ts`); a `watch` that is rejected says
"Live updates did not start: <reason>. Reload the tab to re-arm them." The next
`watch` of that root closes the dead watcher and builds it again.

### The file tab's nav

One row: the breadcrumb, with the unsaved dot and the file's loading or update
status after the file's name; then, at the right end, the renderer's actions
(a viewer file's snapshot), one toggle per panel the file declares, and the
files toggle last, which stays there whatever is open and whatever kind of
file it is. The tree's header is its filter and nothing else. There is no
`Copy path` button and no `Open ▾`: those are items in the entry menus.

The row itself is the CAD Viewer's — `@text-to-cad/ui/navigation`, inside the complete shared FileViewer that web
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
Committed move events — the app's own renames, and an agent's `mv` of an
open file, paired by inode in the watcher (above) — remap every matching tab
and cached/expanded subtree;
delete events prune descendant listings. A bounded mutation-receipt history
prevents the broadcast and initiating caller's receipt from applying a move
twice. External edits preserve dirty drafts and refresh clean documents. A dirty
draft whose file changed on disk shows "This file changed on disk since you
opened it." with Reload and Keep mine; Keep mine adopts the disk's current
revision, so the next Save writes your text over it. A dirty draft whose file
was deleted shows "This file was deleted on disk; Save will create it again."
and Save, after Keep mine, creates the file.

A failed IPC call reaches every renderer caller as the handler's own sentence:
the preload bridge (`src/preload/index.ts`) strips Electron's `Error invoking
remote method '…': IpcError:` wrapper once, with `errorMessage`
(`src/shared/ipc/errors.ts`), so the viewer says "that file is gone" and not
the wrapper around it.

A directory that cannot be listed (a deleted root, a permission error, a
worktree gone on restore) says why where its rows would be, with a Retry:
"Reading…" is only ever the wait for an answer. A refresh that fails on a
directory already drawn keeps its rows and toasts instead.

**Every crumb is a menu of its neighbours** (`@text-to-cad/ui/navigation`'s
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
(`@text-to-cad/ui/navigation`'s `entry-menu.js`), one set of actions, drawn as a dropdown instead of a
context menu. A right-click is not a control anybody can see, and the file's
own menu is the one worth pointing at.

**Right-click a crumb or a tree row** for the entry menu
(`@text-to-cad/ui/navigation`'s `entry-menu.js` is the table, `entry-actions.ts` what each item does,
`@text-to-cad/ui/navigation`'s `EntryMenu.jsx` draws one from the other; the tree has one menu over
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
place (`@text-to-cad/ui/navigation`'s `InlineName.jsx`: Enter commits, Escape cancels, clicking away
commits, the stem is selected and the extension is not); from a crumb they
go to the tree, which is shown for them. The tree is one Tab stop: the arrows
move focus row to row, and the focused row is the cursor every key acts on —
F2 renames it, ⌘⌫ (Ctrl+Delete) trashes it. Every edit is an `explorer.*` request main
resolves against the root and refuses outside it (`src/main/explorer/fs.ts`
for create/rename/duplicate, plain Node and unit-tested; trash, reveal and
`Open with…` — a chooser over `/Applications` then `open -a`, the shell's
own Open With on Windows — in `src/main/ipc/explorer.ts`). A rename or a
trash keeps the strip honest: tabs showing the file or anything under the
folder are re-pointed or closed. Trashing a folder closes every open tab
under it; a tab with unsaved changes stays open and is named in a toast ("Moved to Trash, but 1
open tab could not be closed: <path> (<reason>)"), and the other tabs still close. `Open in terminal` on a folder is the one
`terminal.create` whose `cwd` is under a root rather than a root.

### The panels a file has

**One panel column, one list of panels, one open at a time**
(`@text-to-cad/ui/navigation`'s `panels.js`; the column is its `FilePanelColumn.jsx`).
The list is what the open file's renderer declares plus the **file tree**,
which is the last entry and not a special case; the nav row draws one icon
button per entry with `aria-pressed`, highlighted while its panel is open,
in that order — so the files toggle is last and never moves, and the one
control that is always there is always in the same place. Opening any panel
closes whatever was open.

Markdown declares one, the two readings of the same bytes (`View source` /
`View preview`). A CAD file — STEP, robot, GLB, STL, 3MF, DXF — declares none:
its Features, Links, Reference, Issues and Position are panels of the viewer's
own tool stack over the viewport
([the tool stack](../../packages/ui/docs/settings-ui.md#the-tool-stack)), and
nothing it does opens or turns this column. Display is a popover in the
viewport's top-right bar, never a panel. Code, images and PDFs declare none, leaving the tree as the whole list.

A declaration identifies where its content belongs: `tree` is the app's file
tree, `slot` is a box the renderer draws into, and `body` replaces the file
content, as markdown's source view does. Every panel shares one border, width,
resize handle and header treatment.

**The tab owns which panel is open**, as one id in `FileTabSchema.panel`,
persisted with the tab. `null` is the default: the first declared panel that
asks to be open, which today is only the tree of a tab with no file — so a file
opens with nothing open — while `""` preserves a deliberately closed panel. A
new tab, and a crumb that points this tab at another file, start at `null`. A
file picked in the tree asks for the tree (`openFile(path, { target: "new", panel: "tree" })`):
its tab — new, or the one already showing it — opens with the tree up, so the tree
can be walked file by file; `openSessionTab` applies a requested panel in the same
strip update that selects the tab, and leaves a tab's panel alone when none is
asked for. Below the viewer's 720px breakpoint the tab's panel is not consulted:
a file opens with no sheet and a sheet opens from its toggle. A stored panel id
no panel in the list has — the retired CAD Settings (`cad-file`), or markdown's
source view on a tab now showing a `.step` — resolves as nothing open
(`resolveOpenPanel`); saved `cad-theme` and `cad-display` choices read as `null`.

### Inspect and Render

CAD controls are shared with web, and the shared
[viewer design system](../../packages/ui/docs/settings-ui.md) is their contract;
what follows is what a desktop tab shows. STEP and robot files have a toolbar at
the top left
([tools and lifecycle](../../packages/ui/docs/settings-ui.md#tools-and-lifecycle)).
A STEP's is Select, Draw, Measure, Explode, Clip, then Position where the
sidecar declares kinematics.
No tool has a menu on the strip: what a tool can be set to (Select's modes,
Measure's snapping, Position's joints) is its panel beneath the
toolbar while it is up; Explode and Clip are toggles whose panels sit there too. A robot description's is Select (which picks
whole links; Shift, Ctrl or Cmd adds one), Position where it has movable joints,
and it opens in Select. An agent's select command on a robot fails
with a sentence saying so; its clearSelection clears the link selection. Draw is
a STEP tool and appears nowhere else. A GLB, an STL and a 3MF have nothing to
select: they have no toolbar, and an
agent's select command on one fails with a sentence saying so. Routines and
clips play only in preview, whose playbar sits under the model. Buttons wrap inside the
toolbar in a narrow pane. Display is not a tool: its settings are a popover
from the button beside Preview, and opening it leaves the tool in hand.

The file navbar's snapshot action (the camera) attaches the viewport PNG and
the selected references to this tab's owning session draft through the
prompt-context adapter; it does not send a message. There is no zoom control
anywhere: no percentage readout, no menu behind one, no zoom toolbar. A STEP's
viewport context menu ends in Zoom to fit and Zoom to selection (off without a
selection), offered over a part, over the backdrop and on every Features tree
row. The view cube sits at the bottom right, hidden below the 720px breakpoint
and in preview: its faces turn the camera to the six plane views and its
corners to the isometric views, keeping the zoom. Neither touches the model, its
motion or its display settings. The camera is never stored, so reopening a file
frames it afresh.

**Preview** is the shared shell's own button, a play circle in the viewport's
top-right bar beside Display settings
([camera, animation and preview](../../packages/ui/docs/settings-ui.md#camera-animation-and-preview)).
It keeps this app's navbar and file tree column, hides the toolbar and tool
stack, orbits by default, and offers Playback settings (for a file with
routines its Routine, Speed, Loop and Autoplay, then Orbit) beside the same
Display settings; the routine plays on entry only with Autoplay on. Escape or
its X ("Exit preview") exits, stops the routine and puts the tools view's
camera back. The host passes nothing for it.

A STEP's tool stack holds Select's Features, then the Reference while
something is selected and Issues when there are any; Position's panel (a `Pose`
choice with its Reset, then the joint sliders) is there while that tool is up,
when the sidecar declares kinematics.
Preview's playback and Position's pose retain independent runtimes, enable state
and actions; every pose write (a value, a named pose, a Position-tool knob,
Reset) is an instant jump, and Reset also stops any playing routine and hands
the pose back to Position. A robot's holds Select's Links (the link tree), the
Reference, an SDF's metadata panel for a `.sdf`, and Position for the joints.
A DXF drawing has no toolbar and no tool stack: it is a straight 2D render
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
The tool stack stays as it is while the Display popover is open, so the Features
tree keeps its disclosure and scroll.

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

Neither a display-mode change nor a photographic setting changes the app's appearance.
`cad.spec.ts` checks that the embedded viewer never writes the document's
theme (`data-theme`, `data-theme-preference`, `cad-viewer:theme` all stay
unset); `shell.spec.ts` samples the document's scheme through launch and a
theme change. See the shared [Render modes](../../packages/ui/docs/render-mode.md)
playbook for the mode bases and camera behavior.

## Quitting

`app.quit()` has a budget of two seconds (`tests/e2e/cad.spec.ts` quits with everything running and
asserts two things: the process is gone within it, and `before-quit`'s own teardown, the
`[quit] teardown Nms` line, took at most 250 ms (`tests/e2e/quit-budget.ts` has the derivation:
the teardown is synchronous, about 6 ms locally, and counts toward the watchdog's deadline).
It echoes main's `[quit]` lines and prints
`[quit-budget] app.quit() to pid gone: N ms of 2000 ms (deadline 1200 ms)` and the teardown's share
whether it passes or fails, and records both as the `quit-ms` and `quit-teardown-ms` annotations,
so a CI log shows which part of the budget a slow run spent. `tests/unit/main/quit-sequence.test.ts`
pins the same teardown bound against the real `before-quit` handler, with a `close()` that blocks
shown to exceed it), and the
teardown in `before-quit` is written for it: every owner signals what it
owns and nothing is awaited. Electron waits for the Node side, and the Node
side waits for every child it holds a pipe to, so `src/main/children.ts`
registers every process main spawns — the viewer, the adapters, the
terminals' backends, the probes, `git` — and `before-quit` kills the probes
outright, sends a git write (commit, push, worktree add/remove) SIGTERM so it
can drop its `index.lock` (signalled, not waited for: the write may outlive
the quit and finish, or be killed at `will-quit`), and detaches the rest; `will-quit` kills whatever
ignored its signal. Before that, a cadgen version probe (sixty-second timeout) still
importing OCP held the exit for sixty seconds, and chokidar's `close()` over
this repository blocked for most of a second, so the watchers are not closed
at all — an fsevents handle dies with the process.

On POSIX, an app-owned viewer runs in its own process group. Its transient CAD
workers are stopped when the viewer exits or the app quits, including workers
that outlive the viewer process. A reused external viewer is not a child
of this app and is never touched. The shared warm daemon outlives the app by
design and is spared by pid, not by group (the app-owned viewer has a group of
its own too, so sparing a group would spare it); on Windows the deadline's tree
kill takes the warm daemon with it. The deadline, below, has the mechanism.

What is left after `before-quit` is Chromium's own shutdown, which on this
macOS takes twelve seconds to minutes once a window has held a WebGL context
(the GPU and utility helpers hang, then the browser process retries a
CoreAnalytics XPC send; `app.exit()` is slower still, and no timer of ours
runs once the event loop has stopped). `src/main/quit-deadline.ts` keeps a
deadline from outside: a detached copy of this binary run as Node that
kills the app and its helpers at an absolute deadline, 1.2 seconds from
`before-quit`. It is armed once, at the end of `before-quit`, once state is saved
(`will-quit` arms it only if `before-quit` did not, having thrown before reaching its `try`), so a stall between the two — a
window that never acks its unload, a main-process error dialog (an
`uncaughtException` while quitting exits at once) — is bounded too. It counts
teardown and watchdog startup toward the same budget. On POSIX it kills every
direct child except the warm daemon, which it spares by pid (the app hands it
`daemonPids()` from `src/main/cad/daemon.ts`, which drops a daemon's pid when it exits so a reused pid is never spared; sparing by process group would
also spare the app-owned viewer, which is `detached` too). A child that leads a
group of its own, like the viewer, is killed as a group, so its compile workers
go with it; Chromium's helpers are killed singly. (A viewer reused from another
run is not a child of this app and is never touched.) Its one probe, `ps -axo pid=,ppid=,pgid=` (every process with its parent and group;
the children are the rows whose parent is the app, and their groups come from the same rows), runs
under `WATCHDOG_PROBE_TIMEOUT_MS` so a hung `ps` cannot stall the final kill of the app; the timeout is
that long because starting a process on a loaded CI runner took more than the 150 ms an earlier
two-probe version allowed, and a probe that times out leaves every child alive. The quit budget is
a number in one place: `tests/unit/main/quit-deadline.test.ts` adds the deadline, the probe timeout and
the slack for starting the watchdog and the kill landing, requires the sum to fit the two-second budget,
and requires a run with the probe hanging to finish inside it, so raising the probe timeout fails there.
If the probe fails or times out
no children are found, and only the app is killed (its helpers go with the browser process they
serve, or are left to the OS). The rows of a `ps` that exits non-zero are read as well, for a
variant that fails yet still prints what it found; no such variant has been measured. macOS and
Linux (procps) `ps` both take `-a -x -o`, and a field with an empty name (`pid=`) drops the header. A quit that finishes
on its own — half a second without WebGL —
gives it nothing to do. On Windows there is no spare list: the deadline runs
`taskkill /PID <app> /T /F`, which follows the parent pid through `detached`, so
a quit that reaches the deadline ends the warm daemon too and it is cold-started
by the next launch. (A quit that finishes on its own leaves it running.)

`before-quit` in `src/main/index.ts` calls `markQuitting()` first, before any
step that can throw; the listener in `src/main/menu.ts` is registered later
and keeps a mark of its own. Every teardown step after it (updater, CAD,
integrations, ACP, agents, settings effects, browser, explorer, window state,
database, children) runs under its own `try`, so one that throws is logged and
the rest still run, the database close among them, and the deadline is armed
in a `finally`. `will-quit` logs `[quit] will-quit`, kills what ignored its
signal and arms the deadline if `before-quit` did not. Outside a quit, an
`uncaughtException` shows `dialog.showErrorBox` once the app is ready, unless
`NODE_ENV=test`, so a packaged app with no console still says what broke;
during a quit it logs, kills the tracked children and exits at once.

An update's quit is different. electron-updater spawns the NSIS installer
(Windows) or the new AppImage (Linux) as a child of the app and then quits,
so `before-quit-for-update` marks the quit as an update's
(`markQuittingForUpdate` in `src/main/quitting.ts`) and the watchdog then
kills the app's own process only — no `taskkill /T`, no child scan — rather
than the installer with it. macOS keeps the tree kill: Squirrel's ShipIt is
launched by launchd, not the app, so there is only helpers to spare. And an
install that is refused (an unsigned update on macOS, an installer that fails
to spawn) comes back as the updater's `error`, which puts back the scheduled
checks `installUpdate` stopped (`src/main/updater.ts`), so the session goes on
checking.

The unsaved-draft ask is skipped by that quit on purpose (a Cancel there would strand the
restart), so Restart asks before it requests the install: with a document holding text that
is not on disk, `useUpdates.install` shows "Restart now and discard unsaved changes?" with
Restart / Not now and requests nothing until Restart is pressed.

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

There is nothing to install and no CAD-runtime install state. Settings › About and
updates carries a read-only block — the runtime (source and interpreter),
cadgen's version against the app's, the viewer backend, the skills root
every session is handed — and Repair, which forgets the probe and looks again.
The probe is cadgen's own report, `python -m cadgen.cli doctor --json`, which
runs cadgen's kernel check (the one the STEP path runs). A kernel that fails
to load is *Failed*; one that is missing, that the check refuses, or whose
check did not finish in time is *Ready — CAD kernel: <state>* with the check's
words beneath, because the viewer never imports the kernel and GLB, STL and
DXF still open — and a STEP build that fails then quotes those words in its
recovery line. Only `missing` and `unsupported` keep the build daemon from
being warmed on it (`DAEMON_BLOCKING_KERNEL` in `src/main/cad/runtime.ts`); a
`timeout` says nothing about the kernel, so the daemon is still warmed, and
that probe is not cached — the next status asks again. A probe that *fails*
(no interpreter, cadgen not importable, a kernel that fails to load) is
remembered for a minute, because `cad.warm` asks on every session bind and a
broken interpreter would otherwise run a doctor per bind; Repair and an
override change clear it at once, and so does the runtime card's Try again in a
CAD tab, which calls `runtime.repair()` and then reloads the viewer.
A CAD tab whose runtime did not start shows the failure's words — for a
missing runtime, "This copy of text-to-cad has no CAD runtime … Reinstall the
app" in a packaged build and the list of interpreters it looked for in a
checkout (`missingMessage`) — with Try
again, and Reveal log — `runtime.revealLog` shows the log
(`userData/cad-runtime.log`: every failed probe, every viewer launch that did
not come up, the viewer's stderr; cut back in place to its last 1 MB whenever it passes 4 MB) in the file manager. The request carries no
path: main names the one file, and answers `{ revealed: false }` when it does
not exist yet. The tab never asks the person to set anything up.

`src/main/cad/viewer.ts` runs one `python -m cadgen.viewer --api-only --host
127.0.0.1 --json` per project root (cwd = the root, the launcher's contract),
parses its JSON line, keeps the child, restarts it on a crash with backoff
(1 s doubling to 30 s), and gives up after five crashes in a row; an instance
that stays up five minutes resets the count, and a viewer asked for again after
giving up launches afresh. Every launch, restart and stop shares a generation
per root: a stop bumps it, a launch or restart checks it after each await, so a
stop during the backoff or the launch stays a stop, and `stopAll` also stops
roots still launching. A worktree's viewer stops when the last open session in
that worktree is archived or deleted (`forgetCadSession` in
`src/main/cad/index.ts`, asking `sessionsUsing` over the other sessions). At
most three of its own run: opening a fourth stops the least recently asked-for
one whose root has no CAD tab open (`openCadRoots`: the persisted strips of
sessions that are not archived), and when every other has one the bound is
exceeded rather than a tab's viewer stopped. All stop on quit. It never kills an
instance the launcher reported as `reused`, because that one is somebody
else's. The manager's injectables are `spawn`, `probe`, `delay`, `now`,
`inUse` and `maxLive`. `cad.viewerOrigin` is how the file tab gets the origin.

The viewer does not wait for the first CAD file. When the explorer binds to
a project (or a session's worktree), the renderer calls `cad.warm`, and main
starts what the first CAD file would have paid for on its own clock. The
runtime probe and the daemon are global, so every bind runs them, whatever the
root holds; the viewer is per root, so it starts only if the root holds a
`.step`/`.stp`/`.stl`/`.3mf`/`.glb`/`.gltf`/`.dxf`/`.urdf`/`.srdf`/`.sdf` file
within three folders (`hasCadFile`: a breadth-first scan of at most 400 directory
listings, skipping `node_modules` and dot folders, and not cached, so every
bind repeats it; any other root gets its viewer when a CAD tab opens). The daemon is cadgen's warm build daemon
(`src/main/cad/daemon.ts` spawns `python -m cadgen.daemon`, the registered
command a cadgen client spawns for itself, detached and never stopped — it is
the person's daemon, shared with every terminal, and it retires on its own
idle timeout; it starts in `userData`, so it holds no project folder open). Once per interpreter per app run, and never when
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
`~/.claude/skills`, and no mandatory umbrella `text-to-cad-app-use` skill.
A tool that needs the window (open a file, capture a view) is relayed to it; with
every window closed (macOS keeps the app running) the agent is told at once,
"no text-to-cad window is open; open one and retry", rather than after the wait
for a reply, which is ten seconds, twelve for the viewer's live commands and thirty
for a capture (the tiers are in the [integration guide](docs/integrations.md)).

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

`text-to-cad-skills.json` is written last as the completion marker and records
the version, the skill names and a SHA-256 of the composed skills' content. The
root is rebuilt when any of those differ, or when either layout no longer hashes
to the recorded content (an edited copy), and is idempotent otherwise; a dev
build, whose version never changes, therefore picks up an edited SKILL.md on the
next launch. The root is an additional directory of every session, so an
agent, or a prompt injected into one, must not be able to change what later
sessions of every agent load: the copies are read-only files (0444, execute
bits kept), re-materialised from the hash on every launch. Directories stay
writable so the app's data can be deleted with a plain recursive `rm`; an
agent can therefore still unlink and replace a file, and the hash check is what
undoes that. Symlinks are never shipped. Every `session/new` and `session/load`
receives the root in both `additionalDirectories` and `_meta.additionalRoots`;
adapters read whichever spelling they understand. Claude Code and Codex use
their native skill-root mechanisms. Other adapters retain the concise first
prompt preamble; workspace `list_skills` and `read_skill` read the same root.
A root that could not be made (the copy failed, as opposed to nothing being composed) is
not a missing build: Settings › Agents says "Skills could not be set up: <reason>", and the
workspace `list_skills` and `read_skill` fail with that same sentence (the reason travels to
the MCP server in `TEXT_TO_CAD_SKILLS_ERROR`) rather than answering an empty list.
`session/new` sets the preamble and the first `session/prompt` the agent takes
consumes it: a prompt the agent rejects before it has streamed anything (a
title or a command list does not count) puts it back, so the retry still
carries it. `loadSession` sets it only for a session that was never prompted —
one whose replay has no user turn and whose stored transcript has no agent
answer; a resumed session's history has it.
These are discovery options, not a requirement to load every skill on a turn.

**MCP servers.** The registry supplies separate `text-to-cad-workspace`,
`text-to-cad-browser`, `text-to-cad-pdf`, `text-to-cad-cad`, `text-to-cad-documents`,
`text-to-cad-terminals` and `text-to-cad-drawings` entries. Each runs the shared
`resources/text-to-cad-mcp/server.mjs` executable with its domain selected in the
environment, using this app's Electron binary as Node. Packaging bundles it
in `out/text-to-cad-mcp/`, including Playwright's upstream packages/runtime assets.
The browser entry bootstraps a scoped native connection and runs Playwright MCP;
other domains register their app-owned tools from the registry. Each session/domain gets a different token, restricted
to that integration's registered methods; a domain's tool does not acquire
another domain's capabilities. The stdio entries omit `type`, because the ACP
adapters otherwise interpret them as HTTP/SSE.

The loopback bridge in `src/main/integrations/mcp-bridge.ts` authenticates the
session, checks method ownership and validates its schema. `McpBridge.stop`
aborts the in-flight calls, drops every token, disposes the resources and then
always closes its listener, so a disposal that rejects is surfaced to the caller
without leaving a loopback port open. Native services
operate in main; UI-bound calls use `integrations.command` / `integrations.reply`
and `src/renderer/state/integration-commands.ts`. Main resolves the session's
project/worktree, and the owning service checks tab/resource identity again.
Background reads do not change focus. A capture tool returns an image; an
Add to prompt action separately binds a compatible draft and never sends it.

Provider-owned filesystem/shell tools still access disk and their own process
IDs. They do not read unsaved editor buffers or control text-to-cad's terminals.
Use the app's document and terminal integrations for those live resources.
Existing disk watchers reconcile changes made by ordinary repository tools.

**Runtime.** `CadRuntime.sessionPath` puts the app's pinned CAD runtime ahead
of the login-shell PATH. With the bundled runtime that is `<userData>/bin` and
nothing else: `cadgen` (invokes `python -m cadgen.cli`, independent of a
build-machine pip shebang), `python3` and `python` launchers for the bundled
interpreter. The bundle's own `bin/` is not on the PATH, and the interpreter is
PEP 668 externally managed, so an agent's `pip install` is refused with a
pointer to a `--system-site-packages` venv (resources/README.md, "The
runtime"). A checkout's `.venv/bin` is put on the PATH as it is.
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
  menu.ts                 app menu; items send `ui.command` rather than reaching into the UI —
                          settings, sidebar/explorer toggles, new session, palette, back/forward
                          (the enum in src/shared/ipc/index.ts; there is no review command).
                          New Session and Settings… with no window open one and hold the
                          command until its page calls `ui.ready`, which returns what was held;
                          Close (Mod+W) from a focused browser page is handed to the app's
                          renderer as the key (it closes the tab), else closes the window;
                          Reload Page (Mod+R) reloads the focused browser page and nothing else
                          (`browserService.forwardFromFocused` / `reloadFocused`)
  window-state.ts         persisted geometry, checked against the displays that exist now
  telemetry.ts            Aptabase, inert without a key and off without the setting
  settings-effects.ts     the settings that are instructions to the OS: login item, menu-bar
                          item, macOS vibrancy — applied at boot and on every settings write
  updater.ts              electron-updater against GitHub Releases; a no-op in dev
  app-paths.ts            appVersion, appRoot, resourcesDir (checkout vs packaged)
  children.ts             every child process main spawns, tracked so `before-quit` can end them
  quit-deadline.ts        a watchdog process that ends the app if Chromium's shutdown hangs
                          past `before-quit` (see Quitting)
  quitting.ts             whether the app is on its way out (`before-quit`, or earlier for an
                          update), so the unsaved-draft guard lets the unload through
  test-door.ts            the e2e suite's folder choice from main's side (`__textToCadE2E`),
                          installed only under `NODE_ENV=test` in a development build
  onboarding.ts           whether this run shows onboarding, and the sample project copy
  db/                     sqlite: migrations.ts (runner + schema), repositories.ts (rows <-> types)
  ipc/                    register.ts (validating registration) + index.ts (the handlers)
  agents/                 registry.ts (the provider table), detect.ts (login-shell PATH, which,
                          versions, auth, and the launch-probe order — see ACP), cache.ts (its table between
                          launches), shell-env.ts, install.ts + auth.ts (pty jobs via jobs.ts)
  acp/                    connection.ts (adapter process + SDK + stream tap + reducer),
                          client.ts (fs/terminal/permission), terminals.ts (+ pty/process backends),
                          sessions.ts (index + live connections),
                          agent-options.ts (what each agent's sessions can be configured
                          with, cached between them — see The model and the effort)
  ipc/{acp,agents}.ts     the P1 handler branches, spread into ipc/index.ts
  ipc/agent-options.ts    agentOptions.*: the cache, the probe and the stored defaults
  ipc/{skills,runtime}.ts   the skills root and CAD runtime branches (P5's bodies, P6's shape)
  ipc/dialogs.ts          the native folder and file choosers Settings' path rows use
  ipc/settings-fallbacks.ts
                          settings.fallbacks: { refused, gone } — stored values read as defaults
  ipc/{explorer,cad}.ts   files, terminals; cad.viewerOrigin + cad.warm
  ipc/integrations.ts    scoped integration command/reply relay
  ipc/browser.ts          browser.*: the embedded browser's pages, scoped to a live session
  ipc/clipboard.ts        clipboard.*: plain text and validated PNGs to and from the OS
  ipc/onboarding.ts       onboarding.status and onboarding.createSample
  ipc/git.ts              P7's: the review's reads in a session's directory, the
                          commit, the pull request, and the worktree list
  explorer/               fs.ts (complete listings, read/write, scoped watchers),
                          terminal.ts (node-pty sessions + scrollback)
  browser/                service.ts (one WebContentsView per browser tab, keyed by session,
                          project and root), connections.ts + cdp.ts (the scoped CDP endpoint
                          the Playwright MCP drives), harness.ts + vendor/ (Browser Use's
                          CDP bindings) — see docs/browser.md
  cad/                    runtime.ts (which Python: override, bundled, checkout), viewer.ts (one viewer per project root),
                          daemon.ts (the warm build daemon, started at project open),
                          index.ts (CAD runtime wiring)
  integrations/           registry.mjs + domain/module.mjs (tools and focused skills),
                          manager.ts, skills.ts, mcp-bridge.ts + actions.ts (generic relay),
                          domain services/actions and lifecycle policy
  projects/index.ts       re-exports git.ts: the project services main imports
  projects/git.ts         status, per-file diff, commit and push; then repository
                          detection, worktrees, the keep-limit sweep and `gh pr create`
  projects/workspace.ts   a git mode as a directory: the three modes, the worktree
                          layout, and what a deleted session takes with it
src/preload/index.ts      the contextBridge: builds `window.textToCad` by walking the contract
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
  ipc/browser.ts          browser.* — the embedded browser's pages (browser.ts beside ipc/
                          holds the page and input schemas)
  ipc/clipboard.ts        clipboard.* — plain text up to 1 MiB, PNGs up to 16 MiB
  ipc/onboarding.ts       onboarding.* — whether onboarding shows, and the sample project
  ipc/errors.ts           errorMessage: the handler's own words out of Electron's invoke wrapper
src/renderer/
  app/                    Shell (three panes in a flex row), App, CommandPalette
    PaneSeparator.tsx     one pane divider: drag, arrow keys, and the overshoot collapse
    PaneToggles.tsx       the sidebar's and explorer's toggles, and back/forward
    pane-focus.ts         PANE_HOMES (where focus lands in a pane) for F6 and the return from Settings
  lib/mermaid.ts, lib/math.ts  Streamdown's Mermaid and KaTeX plugins, imported on first use
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
    host/                 the `ViewerHost` ports this app hands FileViewer: prompt delivery
                          (promptContext.ts), the native clipboard, CAD commands, load failures
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
  features/onboarding     Welcome.tsx (the first-run welcome over the window) and
                          GettingStarted.tsx (the sidebar checklist after it) — see Onboarding
  features/settings       the Settings route, the card-grouped rows, the agent drawer, and
                          pages/ — one module per page; search is done by the rows themselves
    settings-value.ts     the page's read and write path over the store, and useSettingsFallbacks
    worktree-cache.ts     the Git page's worktree lists, kept for the Settings visit
  lib/shortcuts.ts        the keyboard-shortcut table the Shortcuts page prints
  lib/git-mode.ts         the sidebar glyph, the composer chip's labels and which
                          modes a project can offer — one answer, two features
  hooks/use-appearance.ts accent, UI scale, code font, reduced motion, translucency as <html> tokens
  components/ui           shadcn/ui, vendored
  components/ai-elements  Vercel AI Elements, vendored (types.ts replaces the `ai` package)
  state/                  one zustand store per domain, plus bridge.ts for main's pushes and
                          integration-commands.ts for an agent's tool calls against the stores
    history.ts            back and forward over the top level, recorded from the selection
    workspace-root.ts     `explorerRootFor`: the explorer root the selected session names
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
scripts/make-brand.mjs    npm run brand: the wordmark into resources/brand
scripts/make-icons.mjs    npm run icons: the sidebar star onto its tile -> build/icon.png
resources/brand/          the committed marks, and the JetBrains Mono face they are set in
resources/text-to-cad-mcp/   the MCP server's source (bundled into out/text-to-cad-mcp by the build)
skills/                  focused domain instructions and licensed upstream skills,
                          selected by the integration registry for resources/skills
```

## ACP

Every session is one adapter process driven by `@agentclientprotocol/sdk`
(`src/main/acp/connection.ts`). The provider table in
`src/main/agents/registry.ts` says how each agent is launched, installed and
signed in; the detector probes the user's login-shell PATH for them.

**Which agents are installed** is a probe (`AgentDetector` in
`src/main/agents/detect.ts`): the login shell's environment, `which` for each
provider's binaries, a `--version` run and an auth check, all in parallel across
providers. `prewarmAgents` (`src/main/ipc/acp.ts`) starts it at launch,
ungated, so it overlaps the renderer's load; `hydrate()` in `state/bridge.ts`
starts the renderer's `agents.list` beside the settings and session loads but
does not put it in front of restoring the explorer. Every finished probe is
written to the settings table under the key `__agents`
(`src/main/agents/cache.ts`), and the table is trusted on the next launch only
when it was written by the same app version and holds every provider. Then:

- A **warm launch** answers `agents.list` at once with that table, every row
  flagged `probing`, and the probe replaces it through `agents.status` (a row
  from a probe never carries the flag). Settings and the new-session screen
  draw a probing row's unauthenticated state as "Checking…" rather than "Not
  signed in". The welcome's Continue reads a disabled "Checking…" while any row
  is probing, the setup cards and the drawer show "Checking…" where a cached
  "not installed" would draw Install, and the Agents page's dot stays idle (not
  green) beside "checking sign-in…" until the probe confirms.
- **Install and Sign in** are disabled while their job runs. The running job for
  an agent and kind is read from `useAgents.jobs` by `useJob(agentId, kind)`
  (`features/settings/AgentDrawer.tsx`), not from component state, so a drawer
  closed and reopened, or a welcome left for Settings and back, finds the
  installer under way and attaches its log instead of offering a second one.
  A job is in that store from the moment main names it, not from its first byte
  (`seedJob` in `state/agents.ts`), so a row remounted while a silent install
  is still quiet finds it.
  A failed run's "Install failed (exit N)" / "Sign in failed (exit N)" is worded
  only while the step is undone (`useJob`'s `done`: installed, signed in), and a
  newer job of the kind replaces the failed one a mount started.
  A start main refuses (no job exists to carry an exit code) is worded "Install could not start: …" / "Sign in could not
  start: …" in the same alert slot, with no log under it, and clears on the next try. The Agents page's Refresh that
  rejects draws the "Could not read the agent list" alert a failed first read does.
- A **cold launch** (no usable cache) waits for the first probe for at most
  `PROBE_WAIT_MS` (3 s), then answers with whatever it has, which may be empty.
  An empty table is "not checked yet", not "nothing installed": a send from the
  new-session screen before the probe has landed is held with "Still checking
  which agents are installed…" and goes out when the probe finds an agent; "Install
  an agent first" is shown only once the probe has answered and found none.
- If the probe fails while the table is still the last launch's, or has none and the
  rows are the registry's, its rows stay
  but carry `probeFailed` instead of `probing` (a row a login has since re-checked
  does not); when every row has it the
  renderer treats it as a failed read, and the new-session screen shows "Could
  not check for agents" with a retry rather than "No agent ready".
  A login shell that cannot be read (it exits non-zero, times out after 20 s, or
  prints no PATH) is such a failure: `loginEnvOutcome` reports it as `failed`,
  the probe marks every row `probeFailed` (even over a good last-launch table),
  writes nothing to the `__agents` cache, and still hands sessions the process
  environment to spawn with. The renderer's next `agents.list` (the card's
  retry) captures the shell afresh instead of reusing the failed capture.
- A forced `refresh` (the Agents page's Refresh) asked while an unforced probe is out is not
  answered by it, because that probe reused the cached login environment: a forced probe runs
  right after it, and the table the caller gets is the later one.
- Anything that would act on a row waits for this launch's probe, through
  `freshWithin(PROBE_WAIT_MS)`: `agents.login` (a CLI installed since has no
  binary path in last launch's row) and the check that refuses a session as
  "not installed". Past the wait, `login` starts from the stale row and the
  session goes on to spawn, whose own failure says what is missing. The
  idle-adapter pre-warm waits on `settled()`, the first table, and shares the
  probe rather than starting a second one.

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
the connection tests. Re-record after bumping an adapter's pinned version
(below); never run the harness against this repository, use a scratch
directory.

The reducer (`src/shared/acp/reduce.ts`) treats a permission request that finds
no turn open — the prompt ended or was cancelled and the adapter asked late — as
history, not as a turn: it rides on the last agent turn, or on a closed turn of
its own, and the session reads `waiting` until it is answered. Answering a
request changes only the turn that holds it; every other turn keeps its
identity, so a long transcript does not re-render. A `closed` or `error` status
also ends the open turn, since the adapter is gone and will send neither
`prompt/end` nor `prompt/error`: `closed` stops it (stop reason `cancelled`,
which the transcript shows as "Stopped"; pending and in-progress calls and
running subagents become `cancelled`), `error` ends it with no stop reason
(they become `failed`), and either marks every card still pending `cancelled`,
since whoever would take the answer is gone. `prompt/end`, whatever its stop
reason, and `prompt/error` cancel pending cards as well; main cancels the
client's pending permissions just before it dispatches `prompt/end`, so the
cards and the requests agree. A call that is settled or completed is never
revived by a late `in_progress`. Content that arrives behind `prompt/end` (a chunk,
a tool call, a subagent spawn or a permission request the adapter sent late) is
added to the last agent turn and marked by the turn's `lateFrom`, the index of
the first part that came late. The transcript draws those parts after the turn's
footer ("Stopped", "The agent declined.", the limit line), under a quiet label,
"Arrived after the turn ended", so they never read as if they came before the
stop. A `session/load` replay cannot say either again (it has no `prompt/end`, so
late text merges into the answer, and it closes every agent turn `end_turn`), so
after the replay the connection dispatches `turns/restored`, built from the stored
snapshot by `turnFactsFrom`: turns are matched by position for as long as each
user turn says the same thing, an agent turn takes the stored stop reason and its
`lateFrom`. A replay with the same number of parts keeps `lateFrom` as stored; a
replay that merged text chunks into fewer parts is cut again where the stored text
before `lateFrom` ends (the `split` on the fact), so the late text is its own part
again and both facts come back. If the stored text is not a prefix of the replayed
text, neither fact is restored: the turn reads `end_turn` with no label rather than
showing late text under a stop it did not belong to. What a reload restores is those
two facts, nothing else, and turns after the first user turn that differs from the
stored one are not matched at all. In the renderer, `receiveState` (`state/acp.ts`) clears a session's
`loadErrors` once the state it takes says the agent is up (`idle`, `running` or
`waiting`). In main, an `initialize` failure goes through `describe`
(`src/main/acp/connection.ts`) as `session/new`, `session/load` and
`session/prompt` failures do: the method and the agent's message with a
sign-in hint, or, when the adapter has exited, which agent stopped and when.

Three things learned from the real adapters that the code now depends on:

- Each adapter is pinned to an exact version in `src/main/agents/registry.ts`
  — `CLAUDE_ADAPTER` (`@agentclientprotocol/claude-agent-acp` 0.84.0) and
  `CODEX_ADAPTER` (`@agentclientprotocol/codex-acp` 1.13.1) — and launched as
  `npm exec --yes --prefer-offline --no-audit --no-fund --no-update-notifier
  --package=<pkg>@<version> -- <bin>`: fetched once into npm's cache, never a
  global install or a bare `npx`. `--prefer-offline` because `--prefer-online`
  puts a registry round trip in front of every spawn, and with a proxy
  refusing connections that held a session start for 71 s before npm fell
  back to its cache. Settings › Agents shows the pin beside the CLI's own
  version. To bump one: `npm view <package> version`, change the constant,
  run `scripts/acp-harness.mjs` for that agent in a scratch directory, and
  re-record its fixture.
- Both adapters accept the draft subagent capability and then send update
  kinds (`subagent_spawned`, `subagent_state_update`) that SDK 1.4.0's schema
  rejects. The connection reads every `session/update` raw off the wire and
  only forwards the kinds the SDK knows, so the reducer sees everything.
- A terminal started from inside a Claude Code session carries that session's
  environment. A nested `claude` then reports itself logged out and the
  adapter answers `Authentication required`. When `CLAUDECODE` is set,
  `src/main/agents/shell-env.ts` strips everything `HOST_SESSION_PATTERN`
  names — `CLAUDECODE`, `CLAUDE_CODE_*`, `CLAUDE_PID`, `CLAUDE_EFFORT`,
  `CLAUDE_TMPDIR`, `CLAUDE_PLUGIN_DATA`, `CLAUDE_AGENT_SDK_*`,
  `CLAUDE_PREVIEW_*` — and `ANTHROPIC_BASE_URL`; without the marker a user's
  own `ANTHROPIC_BASE_URL` (a proxy) stays, and `CLAUDE_CONFIG_DIR` always
  stays, being the person's own choice. The login shell starts from
  `stripHostSession(processEnv())` and nothing is stripped from the environment
  it prints, so the person's own rc exports (a `CLAUDE_CODE_OAUTH_TOKEN`, say)
  survive. The Claude fixture on this machine is the auth-failure exchange for
  that reason (`claude-code-auth-required.jsonl`); a machine with a signed-in
  `claude` (`claude auth status` → `loggedIn: true`) records a full session.
  Until one is recorded, the fake agent's `claude-code` profile
  (`FAKE_AGENT_PROFILE`, in the environment table under Development) answers
  in the shape a real Claude session showed — its modes and config options,
  the 129-command list after `session/new`, mid-turn and after
  `session/load`, a title sent live only.

A new session's row is written before its adapter answers, at `connecting`,
and its `acpSessionId` is stored on its own right after `session/new` returns —
before the preferences and the marks — so a crash while those are pending does
not take a connected session with it. A create that fails before that answer
removes the row and, for a worktree it cut, the worktree. One that fails after
it while the connection is alive resolves: the row goes `idle`, the composer
opens, and the failure is a note in `session.status.error`
(`settleAfterFailedCreate`), worded "The session started, but setting it up
failed: <cause>". The renderer keeps it in `setupNotes` (`state/acp.ts`,
fed by `bridge.ts`) and shows it as an alert above the composer with a Retry
setup button; the composer stays sendable, because the session did start. Retry
setup is `sessions.retrySetup` (`SessionManager.retrySetup`): it re-runs the
same `applyPreferences` a create runs on the live, idle connection, and answers
with the new note or null, which drops it. A session that is not `idle` throws
"The session is busy; set it up again when it is idle." (a refusal, shown as is); a retry that fails is
the note "Setting it up again failed: <cause>", composed by main (also re-broadcast as the
session's status error). The renderer's answer is dropped when the session was
forgotten or disconnected meanwhile (a generation check in `retrySetup`,
`state/acp.ts`), and the alert is hidden while the session shows a load error or
is loading (`SessionView.tsx`), the note staying held underneath. It is not a `load`: a `load` on a live
connection only re-broadcasts its state and retries nothing. The next `load`, a
disconnect (`close`), a closed status from the adapter itself (a crash or exit,
through `receiveEvent`) or a forget clears the note, and the alert is never drawn
beside the "Agent disconnected" bar; it is not persisted, so a window reload drops
it. Retry setup is disabled and reads "Retrying setup…" until the answer comes
back, and a retry main refuses (it throws, as for a busy session) becomes the note with
main's own words, unprefixed: nothing was tried, so it is not reported as a failed try.
One whose connection is dead, or whose row is gone,
is abandoned (`abandonCreate`): the connection is retired, the row removed, the
worktree that create cut released, and `create` rejects with the failure that ended it, even
when the store refuses to remove the row too (that is logged, and the marks are still unpinned and
the worktree still released). The same happens when
the store refuses the settle too, so nothing stays `connecting` behind a live
connection. A create whose row the person deleted while it started rejects with
`DELETED_WHILE_STARTING` (`shared/ipc/errors.ts`), which `NewSession` swallows:
no failure card, no toast. A row closed under the create keeps that state; only
a row still `connecting` is written `idle` (`stillConnecting`).
`boot()`, on the first call after
launch, removes every row with no `acpSessionId` that no create in this run
owns — a create cut short by a quit, which can never be loaded — unpins its
marks, and, when the row records `worktreeOwned` and a `worktreePath`, releases
the worktree that create cut (`releaseWorkspace(…, { abandoned: true })`); a
worktree the create was handed is left alone. A row whose directory is missing or unmounted is not of that kind: it is
never deleted for that.

An archive during a create waits for the create to settle, then closes the row;
past ten seconds (a hung `initialize` or `session/new`) it closes under the
create instead, which removes the row and its worktree and rejects.
`prompt` does not reconnect an archived row (it rejects with "This thread is
archived; unarchive it first."): the first prompt a `NewSession` sends as its
create returns would otherwise run a turn in the thread that was put away, and
`NewSession` skips the send for a row the index says is archived, leaving the
draft in that thread's box. An archived transcript the person opened and
Reconnected has a connection, and is prompted as any other.

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
  main sees is written to sqlite, debounced by 750 ms — except while a
  connection is still connecting (a reload's replay is the beginning of
  the transcript, and never replaces the stored one) — and clicking a
  disconnected row paints *that* — 30–40 ms; `tests/e2e/persistence.spec.ts`
  asserts it lands before the load — with `Reconnecting…` in the composer's row
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
  the next click on it reconnect. A busy connection is never evicted — the
  limit is exceeded until it is not: a turn in flight (`running`, `waiting`),
  one still `connecting`, and anything in `held` — a create from its spawn
  until it returns, a prompt from its refusal check until its turn ends (idle
  through the turn mark, which waits on git). `ensureLoaded` (`state/acp.ts`) does
  nothing for a session the renderer holds whose status is not `closed`, and
  for one it does not hold it asks main for the stored state
  (`sessions.state`, which also says whether main's connection is `live`): a
  live connection is painted and left alone, so a just-created session is not
  reconnected (a reconnect drops turn events until it answers, and would
  repaint from a snapshot older than the prompt just sent). Only a `closed` or
  absent connection with no live counterpart in main starts a `load`. A
  session's `create` is in `creating` from before `session/new` until it
  returns; `load` and a prompt (`ensureLive`) wait on it, and `state()` reports
  `connecting` for a live idle connection whose create is still open, since
  the row says `connecting` until the preferences and marks have landed. The
  renderer gates the composer on the row and the connection together
  (`SessionView.tsx`): `connecting` is `state.status === "connecting"` or
  `row.status === "connecting" && !reconnecting`, and the composer reads
  `submitted` when `(connecting || loading) && !reconnecting` or when the
  composer store has a prompt `sending`.
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
  worktree session spawns its own. It is matched on the rest of what it was
  spawned with too — the environment, the runtime on `PATH`, the skills root,
  the launch — and one spawned before any of those changed is closed rather
  than adopted. There are no sessions in the index on a
  first launch, so this does nothing until the second — and it is gated the
  way the CAD pre-warm is (`TEXT_TO_CAD_PREWARM=1` under `NODE_ENV=test`).

What is left of the seconds is the `session/load` replay itself, which is
the agent's own work and is now behind a transcript rather than in front of
one.

With no load at all, what a switch costs is React mounting the transcript,
and a turn is some sixty nodes. So `features/session/Transcript.tsx` mounts
the last 12 turns (`TRANSCRIPT_WINDOW`) when it opens and the rest a window
at a time (a `Show N earlier turns` button at the top, with a sentinel
`EarlierTurns` mounts the next window from once it is within a screen), keeping
what they were reading where it was. The window is set when the transcript
opens and only grows: a turn that arrives is added and nothing mounted is
dropped. The sentinel acts only after the person has reached for earlier turns
since the pane was last at the bottom (`reached`: an upward wheel, a touch
move, ArrowUp, PageUp, Home or Shift+Space, or a press on the pane itself,
which is its scrollbar) or when the pane is too short to scroll, because the
pane starts at the top and animates down, so the sentinel is in reach for a
moment on every switch.
A turn holding a pending permission request, in a tool call or a subagent, is
always mounted together with every turn after it, and answering the request
does not hand those turns back. The turns mounted above where the window began
sit in an `aria-live="off"` container, so a screen reader does not announce old
turns as news while a turn that arrives below is announced. The log region is
`aria-busy` while an agent turn streams (not while it waits on a permission
answer), so the per-word streaming is not read token by token. Measured on
a 40-turn session switched to seven times: the median switch went from 90
to 45 ms and the transcript from about 1 900 nodes to about 580.
`content-visibility: auto` was tried first and measured slightly worse — the
cost is the mounting, not the layout.

## Git modes and worktrees

Every session has a working directory, and a git mode is how it got one
(plan §9). No mode is ever forced.

| Mode | `cwd` | `branch` | `worktreePath` |
| --- | --- | --- | --- |
| `none` | the project directory | — | — |
| `checkout` | the project directory | whatever it is on | — |
| `worktree` | a new worktree | a new `text-to-cad/<slug>` | the same directory |

git and its hooks run under the login shell's environment (PATH included) once
`loginEnv` has captured it at launch (`onLoginEnv` in `agents/shell-env.ts` feeds
`git.ts`; Refresh in Settings › Agents refreshes it too), so Homebrew's git,
git-lfs and a hook that calls node work from a Dock launch. Until the capture
lands, git runs under the process environment and no call waits for it; on
Windows the process environment is always used. Either way the
repository-location variables (`GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`, `GIT_NAMESPACE`,
`GIT_CEILING_DIRECTORIES`, and the common-dir, object-directory and prefix ones) are stripped, so a login
shell that exports one cannot point every call at another repository, and `LC_ALL` and `LANG` are
pinned to `C` for every git call (the app matches git's English, such as "dubious ownership"; a hook
inherits the pin).

Worktree paths are compared by real path (`git.sameRealPath` / `git.isUnderReal` resolve
symlinks in the part that exists), because `git worktree list` answers real paths:
a `worktreeRoot` that is a symlink (`~/wt`, or `/tmp` and `/var` on a Mac) still
lists, sweeps and deletes, and a session spelled through the link still holds its
worktree. A new worktree's recorded path is the real one.

`worktree` is the only one that can fail — a project that is not a repository,
or one with no commits — and it fails with a sentence rather than git's words.
The others work in a plain folder: git is optional, and a project is a
directory.

"Not a repository" is not the only reason a folder has no repository, and the
Review tab, the mode chip (its Local item and its worktree item both) and worktree mode say which. Git is missing
("git is not installed or not on PATH"), the folder is gone ("<folder> no
longer exists"), git refuses it for dubious ownership ("git will not open this
folder because another user owns it (add it to git's safe.directory to trust it)"),
or git did not answer in time ("git did not answer in time, so this folder could not be read"). The
reason rides on `status` and `projectInfo` as `problem`; a folder that is just
a folder has none, and gets the plain "not a git repository".
Each reason has its own title in the Review tab ("Git is not installed", "Folder is
gone", "Git will not open this folder", "Git did not answer"), over one capitalised
sentence, and only the reasons that do not already say what follows add ", so there is
nothing to review."

Worktrees live outside the project, one folder per project, whichever agent
made them:

```
~/.text-to-cad/worktrees/<project-slug>-<8hex>/<slug>       branch text-to-cad/<slug>
```

The eight hex digits are a hash of the project's path, so two projects that
share a basename never share a folder (`projectWorktreeDir` in
`src/main/projects/workspace.ts`). A bare `<project-slug>` folder is the
layout of builds before the hash; its worktrees are still listed and accepted,
but only ones git says belong to this project's repository
(`legacyProjectWorktreeDir`).

The root and the branch prefix are settings, as are the fetch before creating,
the auto-delete and its keep limit (Settings › Git and worktrees, which also
lists what exists per project; a project whose worktrees cannot be read shows its card with "Could not read the worktrees: …"
in place of the list, and a failed Delete's message goes when the next read lands. A folder or file chooser that itself
fails toasts "Could not open the folder chooser: …" / "…file chooser: …"). The slug comes from the session's first prompt
when there is one, so a directory can be matched to a thread without opening
anything. That directory is also the session's *identity* in the agent's own
store — both `codex resume` and `claude --resume` key their threads by cwd —
so a text-to-cad worktree session is resumable from a terminal later.

A branch prefix git would refuse cannot be typed in: the field says why and
writes nothing. One stored before that check existed is read as the default
(`text-to-cad/`), and `settings.fallbacks()` (`src/shared/ipc/index.ts`,
handler in `src/main/ipc/settings-fallbacks.ts`) returns `{ refused, gone }`:
`refused` holds the stored text of every top-level field that failed its own
parse, `gone` the remembered `defaultProjectFolder` or `worktreeRoot` that is no
longer a folder, with `reason` `missing` or `file` (a wrong-typed value is
`refused`, never `gone`). The Git page
(`GitPage.tsx`) flags a refused `branchPrefix` in a warning beside the field
with **Use default**, which stores the default over it; a gone folder shows a
quiet note on its row.

A worktree that belongs to a session is deleted automatically only when
auto-delete is on. The exception is a create that fails: its row goes, and the
worktree that create made goes with it whatever the setting
(`releaseWorkspace(…, { abandoned: true })` in `src/main/projects/workspace.ts`,
called from `SessionManager.create` through `abandonCreate`, and from `boot` for
a dead create's row) — never a worktree it was handed by `New
session in this worktree`. With auto-delete on, deleting a session removes its
worktree, never forced (`releaseWorkspace`), and the keep-limit sweep
(`pruneProjectWorktrees` in `src/main/ipc/git.ts`) starts once a new
worktree's session row is written (`sessionWorkspaceSettled`), unawaited, so
the new one is already protected and the session's start never waits. It
also clears a worktree whose folder was deleted by hand, which has nothing
left to lose (`folderGone` in `src/main/projects/git.ts`); Settings lists such
a worktree as clean, so Delete there is open to it. It never removes a worktree outside the project's
worktree folders, a locked one, one that holds the `cwd`, `projectId` or
`worktreePath` of a session row that is not archived, or a create still
in flight, or one with unsaved work (`hasUnsavedWork`): uncommitted changes,
ignored files that are not a disposable cache, a detached HEAD whose commits
no branch, remote branch or tag reaches (`for-each-ref --contains HEAD` over
`refs/heads`, `refs/remotes` and `refs/tags`), or a rebase, merge, cherry-pick,
revert or bisect left half done (`strandedWork`). An archived session holds no worktree.
"In use" is one function, `sessionsUsing` in `src/main/projects/git.ts`: the
sessions that are not archived and run in the worktree, in a folder inside it,
or record it as their `worktreePath`. It answers Settings' open-session count,
Delete's refusal, and a session's release of its own worktree; the sweep's
`protectedPaths` applies the same not-archived filter. The sweep asks it again right before `git worktree remove` (`stillEligible` on `removeWorktree`), so a session that opened during the checks keeps its folder; a worktree it could not remove is logged. Settings' Delete is
refused on two grounds: a worktree in use (main answers "N sessions are still
using that worktree", and the row says "A session is still open in this
worktree.") and a locked one (`git worktree lock`; the row says it is kept
until it is unlocked). The row disables Delete and gives the reason through
`keptBecause` in `GitPage.tsx`, which also covers uncommitted changes
or ignored files (`dirty`), commits only the checkout holds (`stranded`: a detached
HEAD no branch, remote branch or tag reaches, or a merge or rebase left half done), and a worktree git
could not check (`unsavedWork` answers both, split by kind). `keptBecause` gives the stranded kinds one sentence, "This worktree holds
commits on a detached HEAD no branch reaches, or an unfinished rebase or merge, that deleting it would lose.",
and a worktree git could not check another, "Git could not check this worktree for uncommitted changes,
ignored files, or commits only it holds, so it is kept."; the line under the branch says "commits on a
detached HEAD, or an unfinished merge or rebase" or "could not check for unsaved work". The row's "no branch" is the short
form of the rule above, which also counts a remote branch or a tag. The limit counts only unlocked, unheld
worktrees in the project's worktree folders; one with unsaved work counts
toward it and is then kept. Deleting a worktree by hand says why it refused, in the words of `removeWorktree`: "that worktree has uncommitted changes",
"that worktree has ignored files that removing it would delete: <up to three names, and N more>",
"that worktree has work removing it would lose: <it is on a detached HEAD whose commits no branch holds | a rebase is in progress in it>"
(the second half names the operation: a rebase, merge, cherry-pick, revert or bisect),
"could not check that worktree for unsaved work, so it was kept: <git's reason>", and, from the last look before git removes
anything (`stillEligible`), "a session started in that worktree while it was being checked, so it was kept".
A branch is deleted only when a failed create abandons the
worktree it made, and then only while it still points where it was cut
(`deleteBranchAtBase`; with no recorded head, only if `git branch -d` would
take it) — a checkout can be recreated, the commits on it cannot.

The review's scopes are the other half of this. Main records a snapshot
of the working tree when a session is created and again at the start of every
turn (`sessions.sessionHead` and `turnHead`: a tree made from a throwaway copy
of the index with `add -A`, so untracked files are in and `.gitignore` applies,
and pinned under `refs/text-to-cad/<session id>/` so `gc` cannot prune it; the
refs go when the session is deleted). An untracked file over 8 MiB
(`SNAPSHOT_MAX_BYTES`) is left out of the tree, so a large CAD export beside the
source is not hashed into `.git/objects` every turn; under `Last turn` it reads
as untracked, as if added since the mark. The pinned refs are ordinary refs:
`git push --mirror` would send `refs/text-to-cad/*`, and with them the trees of
untracked, non-ignored files not yet pushed, so anything that must not leave the
machine belongs in `.gitignore`. `Last turn` / `This session` compare that
tree with a snapshot of the working tree as it is now, so an edit the agent has
not committed is in the answer and work from before the turn began is not. A
session that cut a fresh worktree keeps that worktree's base commit as its
`sessionHead`, which is also what its branch is deleted against; one that opens
an existing worktree (`New session in this worktree`) marks the tree as it is,
since earlier uncommitted work may be in it; marks recorded as commits by older builds
still work as `git diff <sha>` against the working tree.
A mark never fails or delays a turn or a create past `MARK_WAIT_MS` (5 s, in
`src/main/acp/sessions.ts`). Past it a turn keeps the previous `turnHead` and a
session mark falls back to the commit (`HEAD`, or the empty tree in a
repository with no commits), and the snapshot goes on running. There is one
snapshot at a time per `<session id>/<kind>`: a second asker, the next turn's
say, takes the first's result rather than stacking another `add -A` that could
land after it and re-point the ref. A snapshot that lands for a row that is gone
(deleted, or a create that failed) unpins the marks it just made; the create's
own marks are started before the spawn and settled after `session/new`, so they
run alongside it. A snapshot that fails (`tree === null`: an unreadable file, git-lfs
missing from the PATH, a full disk) is treated like a late one: the previous mark stays, with the log line
"[acp] no turn snapshot of <cwd>; kept the previous mark" (`session` for a session mark), and with no previous mark the commit is the mark.

The sidebar row's `+8 −1` is a different count from the review's: main tallies the diffs the agent
*reported* (`changedFiles`, `insertions`, `deletions`, from `tallyUpdate` in `src/main/acp/sessions.ts`), not git. A turn writes
the tally when it settles (`persistTally`), also when it is cut short, then without stamping `updatedAt`
(`touch: false`); an edit that arrives after the turn settled, a background task finishing say, is written
at once, but only while the session is idle, because a `session/load` replay counts the whole history again from
zero and must not overwrite the row halfway. After a reload the replay's diffs are counted again; an adapter that
replays none leaves the persisted counts as `baseFiles`, which later edits add to, so
a file edited again then counts twice (its path is not known).
A read of either scope lists the untracked files in a throwaway copy of the
index (`add --intent-to-add` of just those paths, no objects written), and the
reads of one review share it while the real index and the untracked set stay the
same. That index is kept per repository root, keyed by the real index's
`inode:mtime:size` and a hash of the untracked paths; an unused one lives 30
seconds for the next poll and every one is removed at exit. A build that fails
fails the read: falling back to the real index would show every untracked file
from before the mark as deleted.
Counting an untracked file for the review reads it whole up to 1 MiB; a larger
one is streamed a megabyte at a time (after the NUL test on its first 8000
bytes) and its counts are remembered by size and mtime, so the half-second
status poll does not read it again. Past 512 MiB, git's own
`core.bigFileThreshold`, it counts as binary without being read. A diff of a
working-tree file is refused past 4 MiB (`MAX_TEXT_BYTES`, `readWorkingCopy`).
Those two scopes also move the whole read into the session's directory, which
for a worktree thread is not the project's checkout.

A scope's revisions arrive from the renderer and end up as git argv, so main
validates them before git starts (`assertSafeScope` in
`src/main/projects/git.ts`): a range's `from` and `to` must be commit ids, and
`since` must be one of the review header's presets. Every git call that takes
a review scope's revision also puts `--end-of-options` in front of it, so a
value shaped like `--output=…` is a revision git rejects, never an option.
That flag needs git 2.24 or newer.
The throwaway index a snapshot and a review read through is seeded from the real one found with `rev-parse --git-path index`, resolved against the repository, not `--path-format=absolute` (git 2.31), so 2.24 stays the floor.

The commit strip's button reads **Push** when the tree has no changed files and
the branch is ahead (`pushState` answers `{ dirty, ahead }` in one status
read), **Commit or push** when a remote exists, else **Commit**. A `Commit or
push` that finds a clean tree with commits ahead pushes them and reports that it
only pushed, rather than failing on "nothing to commit" after a push that
failed. `ahead` is porcelain's count for a branch with an upstream; without one
(a first push that failed) `commitsAhead` counts the commits on no remote
branch, and skips that walk, answering 0, when the repository has no remote. A
branch with no upstream pushes with `--set-upstream` to its
`branch.<name>.remote`, else the only remote there is, else `origin`. A git
write (commit, push, worktree add or remove) times out after 10 minutes and a
read after 60 seconds; a failure reads as the last 20 lines of stderr, or of
stdout when stderr is blank (a commit hook's reason, "nothing to commit").

### The explorer's root

A worktree is outside the project directory, so the explorer cannot be
rooted at the project alone: a session working in
`~/.text-to-cad/worktrees/text-to-cad-1a2b3c4d/model-the-wrist` writes its STEP there,
and `open_file` on it has to open *that* file, in a tree that lists *that*
directory, served by a viewer run from it. The **root** is the concept that
carries this (`ExplorerRoot` in `src/shared/types.ts`): `null` for the
project directory, else the absolute path of one of the project's own
worktrees.

- The explorer store has an active root, derived from the active session
  (`explorerRootFor` in `state/workspace-root.ts`, re-exported by `state/bridge.ts`): a worktree thread's worktree,
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
  per root — a worktree gets its own, stopped when its last open session is
  archived or deleted.
- Every filesystem `explorer.*` request names `{ projectId, root? }`, and main's
  `rootOf` (`src/main/ipc/explorer.ts`) resolves the pair: first any `cwd` or
  `worktreePath` a session of the project records (handed on in the recorded
  spelling), then `resolveProjectRoot` (`src/main/projects/workspace.ts`) —
  the project directory, a directory under the project's hashed worktree
  folder, or one under the legacy bare folder whose worktree git lists as the
  project's — and a sentence for anything else. The MCP bridge resolves an agent's paths
  against the session's root the same way (`src/main/integrations/actions.ts`,
  `sessionRoot`), and the `integrations.command` it produces names the root so the
  renderer opens the file where it is. `files.changed` names the root its
  paths are relative to.

`tests/e2e/git.spec.ts` runs the whole path with the fake agent: a
worktree session writes a file, calls `open_file` through the MCP server,
and the tab, the breadcrumb, the tree and a new terminal all root at the
worktree; starting a new session opens an independent, empty explorer.

The agent's `attach_snapshot` reads an image (PNG, JPEG, WebP, GIF, at most 3.75 MB of file so the base64 stays under the model's 5 MB, and only when the file's first bytes are that image type)
in main from one handle, opened non-blocking and checked with `fstat`. Once it is
open the path is resolved again with a fresh `realpath`, which must still be
inside the workspace (`climbsOut`, so a folder named `..keep` is fine) and name
the file the handle holds (same device and inode); a path swapped for a link out
of the root between the check and the open is refused.

The captures the app makes itself (`capture_view`, `capture_drawing`,
`capture_pdf`) all pass through `imageResult` (`src/renderer/state/image-result.ts`):
one over the same limit is redrawn smaller (up to six passes, a side never
below 64 px), or refused when it cannot fit. `capture_view` also rejects with
"the viewer's WebGL context is lost; try again once it restores" while the
GPU context is gone. A shrunk result carries `scaled: true`, `scale` (how
much each side shrank) and, for a PNG source, `scaledFrom: {width, height}`, so
an agent can map a pixel it reads off the picture back to the original.

### CAD references and session drafts

Viewer references and captures always enter the draft of the session that owns
that viewer tab. The host carries the owner ID before any asynchronous work,
and checks that the session still exists, is unarchived, and shares the file's
workspace before accepting context. It never chooses a different destination
from the currently selected session. The same rule applies to files, CAD, PDFs,
drawings, browsers, terminals and review selections.

New-session text drafts remain separate per directory. They have no explorer until
a session is created. An ordinary new session sends only its Git mode; main
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
3. call `window.textToCad.<branch>.<name>(...)` — from a store in
   `src/renderer/state/` when what comes back is state other components show.
   Events go through `state/bridge.ts`.

The preload needs no edit: it builds the client from the contract. Anything
shared — sessions, settings, the explorer's tabs and trees — is a store, so a
change pushed from the menu or another window lands in the same place a click
would. A component may invoke a channel directly when the answer is its own:
a one-shot read (`explorer.stat`, `git.status`, `app.info`) or an action whose
result nothing else keeps (`shell.openExternal`, `explorer.rename`,
`git.commit`) — about twenty files under `features/` do. The one component
that subscribes to events itself is `features/explorer/TerminalTab.tsx`
(`terminal.data`, `terminal.exit`): a terminal's bytes are written straight
into the xterm that draws them, sequenced against its scrollback snapshot.

## Embedded browser

Browser tabs borrow persistent native pages owned by the browser domain. UI and
agent tools share the same Chromium target, partitioned by session, project
and root (`browserScopeKey` in `src/main/browser/service.ts`): one session's
tabs share storage, two sessions in the same directory do not.
The [browser guide](docs/browser.md) documents the pinned Playwright MCP runtime,
scoped native CDP adapter, compact responses, supported operations, packaging and
validation. The upstream package owns browser tools; text-to-cad owns native pages
and their tabs. No second browser is installed.

## Shared package integration

`@text-to-cad/ui/file-viewer` owns the whole file-tab interface. Desktop's thin
FileTab binds IPC, persisted explorer state and host commands. Renderer
registrations load shared implementations lazily. The package supplies compiled
ESM, declarations, CSS and workers; consumer source aliases, copied tokens,
JSX loaders and handwritten viewer declarations are removed.

The explorer owns one lazy CAD connection per root with open file tabs; the
client module behind it is imported when the connection is first acquired. Tab
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
