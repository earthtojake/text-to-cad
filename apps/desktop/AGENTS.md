# AGENTS.md — apps/desktop

Read `README.md` first: dev, checks, packaging and the layout tree are there.

## The plan is not in this repository

text-to-cad's design document lives outside the checkout, at
`~/robots/text-to-cad-notes/design/desktop-app.md` (user policy: design notes
are never committed). Section numbers in the comments here — "plan §3", "plan
§9" — point at it. If you cannot read it, ask; do not reconstruct it from the
code and do not write a copy into this tree.

## Directory ownership per phase

One phase owns a directory. A folder that is a stub with a comment naming its
phase is not an oversight — it is the seam.

| Phase | Owns |
| --- | --- |
| P0 (done) | the project itself, `src/preload`, `src/shared/{index,types,titlebar,globals.d}.ts`, `src/shared/ipc/{index,define,errors}.ts`, `src/main/{index,menu,window-state}.ts`, `src/main/db`, `src/main/ipc/{index,register}.ts`, `src/renderer/app` — the shell's frame and the command palette — Settings' frame, and `tests/` where no row below names the file |
| Shell & lifecycle | `src/main/{app-paths,children,quit-deadline,quitting,settings-effects,test-door}.ts`, `src/renderer/features/sidebar`, `src/renderer/lib/sidebar.ts`, `src/renderer/state/{history,workspace-root}.ts` |
| P1 (done) | `src/main/agents`, `src/main/acp` (but `acp/agent-options.ts`), `src/shared/acp` (but `acp/options.ts`), `src/shared/agents.ts`, `src/{shared,main}/ipc/{acp,agents}.ts`, `src/renderer/state/{acp,agents}.ts`, `scripts/{acp-harness,fetch-agent-icons}.mjs`, `tests/fake-agent`, `tests/fixtures/acp` |
| P2 | `src/renderer/features/session` — the transcript, activity rows, composer chips, permissions, plan card — and its path links and reference grammar, `src/renderer/state/path-links.ts`, `src/shared/cad-refs.ts`; plus what the model and effort chips are drawn from before a session exists: `src/shared/acp/options.ts`, `src/{shared,main}/ipc/agent-options.ts`, `src/main/acp/agent-options.ts`, `src/renderer/state/agent-options.ts` |
| P3 (done) | `src/main/explorer`, `src/{shared,main}/ipc/explorer.ts`, `src/shared/terminal-replies.ts`, `src/renderer/features/explorer` (but `drawing/`, `DrawingTab.tsx`, `host/` and `BrowserTab.tsx`) — file tab, tree, Monaco, review, browser, terminal — `src/renderer/state/live-documents.ts`, `scripts/{monaco-workers,pdf-assets}.mjs` |
| P4 (done) | `@text-to-cad/ui` CAD renderer and explicit `@text-to-cad/core/client`; FileTab hosts the shared FileViewer through `src/renderer/features/explorer/host/` and `src/renderer/state/{live-cad,cad-draft}.ts` |
| P5 (done) | `src/main/cad`, `src/main/integrations` (but `integrations/drawings/`), `src/{shared,main}/ipc/{cad,integrations,runtime,skills}.ts`, `resources/{cadgen,runtime,skills,text-to-cad-mcp}`, `skills/`, `scripts/{build,build-skills,build-mcp,cad-resources,bundle-runtime,perf-cad}.mjs`, `src/renderer/state/integration-commands.ts`, the `reveal` field of the explorer store and tree |
| Drawings | the drawing tab kind: `src/renderer/features/explorer/DrawingTab.tsx`, `src/renderer/features/explorer/drawing/`, `src/renderer/state/drawings.ts`, `src/main/integrations/drawings/` |
| P6 | `src/renderer/features/settings` — the pages' contents — and the choosers its path rows use, `src/{shared,main}/ipc/dialogs.ts`, `src/main/ipc/settings-fallbacks.ts` |
| P7 (done) | `src/main/projects` (`git.ts`, `workspace.ts`, `index.ts`), `src/{shared,main}/ipc/git.ts`, `src/renderer/lib/git-mode.ts`, the review tab's scopes and commit strip, Git and worktrees' per-project cards, `tests/e2e/git.spec.ts` |
| P8 (done) | `electron-builder.yml`, `build/`, `resources/brand`, `scripts/{package,make-icons,make-brand,app-version}.mjs`, `src/main/{updater,telemetry}.ts`, `src/{shared,main}/ipc/app.ts`, the CI jobs |
| Browser | the embedded browser P3's tab kind grew into: `src/main/browser/`, `src/shared/browser.ts`, `src/{shared,main}/ipc/browser.ts`, `features/explorer/BrowserTab.tsx`, `docs/browser.md` |
| Clipboard | `src/{shared,main}/ipc/clipboard.ts` — the one door to Electron's native clipboard (main-side text and PNG reads and writes, validated); renderer callers of that go through `window.textToCad.clipboard`. A copy button on the page — the vendored `terminal.tsx`, `code-block.tsx` and Streamdown's, Copy path, the terminal's selection — writes plain text with the web `navigator.clipboard.writeText`, which `clipboard-sanitized-write` in `src/main/index.ts` permits; that is not a second door to the native clipboard, and the vendored components are not rewritten to use the IPC one |
| P9 (onboarding) | `src/main/onboarding.ts`, `src/{shared,main}/ipc/onboarding.ts`, `src/renderer/features/onboarding`, `src/renderer/state/onboarding.ts`, `resources/sample/`, the `onboarding*` settings fields |

Work outside your phase's directories only where the seam requires it — a new
IPC branch in `src/shared/ipc/<branch>.ts`, spread into `src/shared/ipc/index.ts`,
with its handlers in `src/main/ipc/<branch>.ts` spread into
`src/main/ipc/index.ts`, is expected; reshaping the shell to fit one feature is
not.

## Running it for the person

- **When a workstream lands, rebuild and relaunch the app for them.** A
  running Electron keeps the code it started with; a merge that is not
  followed by a restart is a merge they cannot see. The sequence is: stop
  the instance you launched (`pkill -TERM -f 'Electron\.app/Contents/MacOS/Electron \.$'`
  — only the dev instance, never a packaged text-to-cad.app), `npm run build`,
  then relaunch. Close every Playwright or debugging instance you started
  first, so the one window left is the current build.
- **Launch in the background.** `TEXT_TO_CAD_LAUNCH_INACTIVE=1 npx electron .`
  shows the window without taking focus (`showInactive` in
  `src/main/index.ts`), so the relaunch does not interrupt whatever they are
  doing. Run it detached (`nohup … &`) with stdout to a log file. Never a bare
  `npx electron .`: that one takes the screen.
- **A test launch shows nothing at all.** `npm run e2e` sets
  `TEXT_TO_CAD_E2E_HIDDEN=1` (`playwright.config.ts`) and main then skips `show()`
  entirely, so a suite run — a dozen windows — never appears over the person's
  screen. Playwright still drives the renderer over the DevTools protocol:
  screenshots, boxes, the mouse and the keyboard all work on an unshown
  window. Any scratch Playwright or Electron script you write sets the same
  variable, or `TEXT_TO_CAD_LAUNCH_INACTIVE=1` if it has to be visible.

## Rules that are easy to break here

Where a test holds a rule, it is named beside it; run it after touching what
the rule is about.

- **Pure refactor:** package moves preserve all app UI/UX and functionality.
  FileTab hosts `@text-to-cad/ui/file-viewer`; the viewer renderers both apps
  register live in UI, the file renderers only this app registers (Markdown,
  code, image, PDF, unsupported) live in `features/explorer/renderers/`, and
  IPC/native services and app state stay here. Never import web app source.

- **The renderer imports from `src/main` never, and from `src/shared` only
  types and pure, dependency-free modules** (zod aside) — never anything that
  touches Node, Electron or the file system. The modules it takes values from
  today: `types.ts` (the schemas, `PANE_LIMITS`), `acp/options.ts`,
  `acp/reduce.ts`, `cad-refs.ts`, `image-cap.ts`, `terminal-replies.ts`, `titlebar.ts` and
  `ipc/errors.ts`. A shared module that grows a Node import stops
  qualifying. Its one way off the page is `window.textToCad`, built from the
  contract in `src/shared/ipc/index.ts`.
  (`tests/unit/main/renderer-shared-imports.test.ts` enforces this.)
- **Every IPC channel is declared once**, as a request schema and a response
  schema. `registerIpc` validates both and refuses to start if a channel has no
  handler. Do not add an `ipcMain.handle` outside it. A branch is its own module
  under `src/shared/ipc/`, spread into the contract; `invoke` comes from
  `./define`, because importing `../ipc` from a branch is a load-time cycle.
  (`tests/unit/main/ipc-declared-once.test.ts`.)
- **Root workspace dependencies are installed in this checkout, never borrowed.** electron-builder walks
  the tree by real path: a symlinked `node_modules` resolves every transitive
  dependency to `undefined`, packages an app missing half its modules, and does
  not fail while doing it. Use root `npm ci` and explicit `npm run native:rebuild --workspace @text-to-cad/desktop`.
- **Nothing reads `process.env` for a build-time secret.** The Aptabase key is
  compiled in as `__APTABASE_KEY__` (`electron.vite.config.ts`); a packaged app
  has no build environment, and a key the launcher can set is a key anyone can
  redirect. (`tests/unit/main/build-secrets.test.ts`.)
- **Every path from the renderer arrives with the project it is relative to,
  and optionally a root within it.** Main resolves the pair against that
  project's directory — or, when the request names a `root`, against one of
  that project's own worktrees, and nothing else (`rootOf` in
  `src/main/ipc/explorer.ts`, `resolveProjectRoot` in
  `src/main/projects/workspace.ts`) — after `realpath`, so a symlink is not a
  door — and refuses anything outside. A channel that took a bare path would
  be a channel that reads any file on the machine.
  (`tests/unit/main/explorer-fs.test.ts` aims links out of the root;
  `tests/unit/main/git-paths.test.ts` does the same for a review's paths.)
- **No channel takes a directory by name.** A folder becomes a project only
  through a chooser main opened, the sample main copied, or a session that
  already records it, so no request under `projects.*` has a `path` or
  `directory` field (`tests/unit/shared/projects-no-paths.test.ts`). The one
  exception is the e2e suite's door, `src/main/test-door.ts`
  (`installE2eDoor`), installed only when `NODE_ENV=test` and
  `!app.isPackaged` — an environment variable is something anyone can set in
  front of a packaged app (`tests/unit/main/test-door.test.ts`). It answers with a
  promise started in a macrotask that the caller must await
  ([why](docs/session-workspaces.md)).
- **An `app.evaluate` that touches the database runs on a fresh stack.** It is an
  inspector interrupt and can land inside a `.all()` mid-row; start the work in
  a `setImmediate` and return its promise (`src/main/test-door.ts`).
- **A menu item that opens an input opens it from the menu's
  `onCloseAutoFocus`.** Mounting the box while the menu is closing lets the
  menu's focus handling blur it, and the blur commits the draft (Rename in
  `features/sidebar/SessionRow.tsx` and `features/session/SessionHeader.tsx`).
- **`src/renderer/components/{ui,ai-elements}` is vendored**, from the shadcn
  and AI Elements registries. It is excluded from eslint (not from the
  typechecker). These deliberate edits are in it: the `ai` package's types are
  replaced by `./types` (`components/ai-elements/types.ts`), about nine
  index accesses are guarded for `noUncheckedIndexedAccess`, `sonner.tsx` moves the toast hotkey from
  Alt+T (Option+T types a dagger on a Mac) to Cmd+Option+T on a Mac and Ctrl+Shift+T elsewhere
  (Ctrl+Alt+T is GNOME's terminal and AltGr arrives as Ctrl+Alt), names the region "Notifications"
  through `customAriaLabel`, and holds the hotkey in a module constant, `shimmer.tsx`
  sweeps a foreground-coloured band rather than a background-coloured one
  (the stock band erases the letters it passes over) and stands still under
  `useReducedMotionConfig` (motion's own reduced-motion setting skips a background-position), and `reasoning.tsx`'s
  `ReasoningContent` takes Streamdown `components` (and `rehypePlugins`), so
  a thought draws links and images through the transcript's own (a stock thought fetches any
  `https:` image on paint), and its `Reasoning` does not auto-close one the
  person opened or closed themselves; `tool.tsx` draws at most 64 KB of a
  tool's input or result (`capToolBody`, `TrimmedBody`) and a string result
  as plain text rather than as JSON; `prompt-input.tsx` does not fetch an
  attachment's `blob:` URL on submit (the CSP refuses it; the composer reads
  the File); `command.tsx`'s `CommandDialog` draws its title inside the dialog
  (stock draws it outside, a heading in the page while the dialog is shut),
  names its box through cmdk's `label`, and passes the dialog's
  `onOpenAutoFocus` and `onCloseAutoFocus` through; `message.tsx` and
  `reasoning.tsx` take their Mermaid plugin from `src/renderer/lib/mermaid.ts`
  rather than `@streamdown/mermaid`, so the diagram engine loads with the first
  diagram and not with the window. They likewise leave `@streamdown/math` out of the
  list until `src/renderer/lib/math.ts` (`useMathPlugin`) has loaded it for a
  text with a formula in it, so KaTeX is not in the window's first chunk. Re-vendoring a component means
  redoing those.
- **The renderer's first chunk stays small.** Monaco (the review tab), xterm
  (the terminal tab), the CAD client, Mermaid and KaTeX load with their first
  use; do not import them statically from the shell. A failed Mermaid or KaTeX
  import is retried by the next diagram or formula (`src/renderer/lib/mermaid.ts`,
  `math.ts`), never remembered as the window's answer. A lazy tab's fallback
  carries `data-focus-pending` so `features/explorer/focus.ts` waits for it, and
  its failure lands in the tab's own boundary: "Could not open the …" with Try
  again only for a chunk that did not load (`ChunkLoadError`, which builds a
  fresh `lazy`), "This tab hit an error" and no retry for a body that threw. The
  packages that must resolve to one copy are in `resolve.dedupe` in
  `electron.vite.config.ts`, and `tests/unit/main/renderer-bundle.test.ts`
  fails on duplicate chunks in a built bundle (CI runs it after the build with
  `TEXT_TO_CAD_BUNDLE_CHECK=1`; a local run without a fresh build passes).
  (README, "Development".)
- **A chord that acts on a hidden tab never runs while the pane is collapsed.**
  `useExplorerShortcuts` (mounted by `Shell`) lets `Mod+W` and `Mod+1..9` fall
  through to the menu when the explorer is collapsed or there is no session;
  the open-a-tab chords are the exception because `open` reveals the pane.
  `event.repeat` is swallowed, and non-mac plain Ctrl chords are skipped inside
  `[data-terminal-body]` (`src/renderer/features/explorer/ExplorerPane.tsx`).
- **The no-native-title rule covers the desktop screens its test renders.**
  Interface hints are the kit's `TooltipHint`, never a `title` attribute
  (`packages/ui/README.md`), and `tests/unit/renderer/no-native-title.test.tsx`
  renders the session, the sidebar, Settings, the agent drawer, the tab strip
  and the review. A new screen is added to that test.
  `tests/unit/renderer/a11y-source.test.ts` also scans every renderer source for
  a `title` attribute on a plain tag or on a component that spreads onto one
  (`Attachment`, `DialogTitle`), which no rendered state can miss; a
  component's own `title` prop that ends in a `TooltipHint` is not one.
- **Keyboard focus is visible.** A control revealed by `group-hover:opacity-100`
  carries a `focus-visible:opacity-100` (or `group-focus-within:opacity-100`) twin, and a button that takes
  `outline-none` draws the kit's ring (`focus-visible:ring-[3px]
  focus-visible:ring-ring/50`). `tests/unit/renderer/a11y-source.test.ts` scans
  `src/renderer` for both (named groups and prefixed `focus-visible:outline-none`
  included; a focus tint or a `hover:ring` is not a ring); an override made
  elsewhere goes on its allowlist, keyed by file and a snippet of the site, with
  the reason.
- **The agent table on a warm launch is the last launch's.** `agents.list`
  answers from the `__agents` settings row with every row `probing`; a caller
  that would act on a row (refuse an agent as not installed, hand a binary to a
  login) waits for `AgentDetector.freshWithin(PROBE_WAIT_MS)` and treats null
  as unknown, never as absent. A screen must not say "signed out" for a
  `probing` row: the welcome, the setup cards and the drawer say "Checking…",
  and the Agents page's dot stays idle (README, "ACP").
- **Nothing is installed into an agent's configuration.** text-to-cad's skills
  and its tools are given to each session — the skills root as an additional
  directory on `session/new` and `session/load` (both spellings) plus a
  preamble for the agents that ignore it, the MCP server in `mcpServers`, the
  runtime in front of the session's `PATH` (README, "Skills and tools in a
  session"). There is no plugin, no marketplace, no write to `~/.claude` or
  `~/.codex`, and no first-launch install step. Do not add one back: a
  person's own agent configuration is theirs, and an app that edits it is an
  app they cannot uninstall cleanly.
  (`tests/unit/main/agent-config-untouched.test.ts`.)
- **Adapter versions are pinned exactly.** `CLAUDE_ADAPTER` and
  `CODEX_ADAPTER` in `src/main/agents/registry.ts` name one version each,
  launched through `npm exec --yes --prefer-offline --no-audit --no-fund
  --no-update-notifier --package=<pkg>@<version>` and
  never a global install (`tests/unit/main/registry.test.ts`). Bump by the
  recipe: `npm view <package> version`, change the constant, run
  `scripts/acp-harness.mjs` for that agent in a scratch directory, re-record
  its fixture (README, "ACP").
- **The CAD runtime ships inside the app.** `resources/runtime/<os>-<arch>/`
  is a complete Python with cadgen installed (`scripts/bundle-runtime.mjs`),
  resolved right after an explicit override; a packaged app downloads and
  installs nothing, and `scripts/package.mjs` refuses to package without it.
  Do not add a first-launch install, a progress state, or a Settings page for
  it back: a runtime that is not there is a failure the CAD tab reports, not a
  state the person is asked to fix. A packaged build says "This copy of
  text-to-cad has no CAD runtime … Reinstall the app"; a checkout keeps the
  list of interpreters it looked for (`missingMessage` in
  `src/main/cad/runtime.ts`).
- **The updater's Restart is a pushed `installing` state with a deadline.**
  `installUpdate` (`src/main/updater.ts`) pushes `installing` before it asks
  Electron to quit and sets `INSTALL_DEADLINE_MS`; past it the status is an
  `error` that keeps the staged version, the scheduled checks resume, and the
  same button retries. An offer survives a background check, a check never
  overwrites a downloading, downloaded or installing state, and an updater that
  is inactive for the install (development, an AppImage without `APPIMAGE`, a
  snap) is `unsupported`, never `idle`.
- **`package.json` stays at version `0.0.0`.** The repository's `VERSION` is
  the canonical release version; `scripts/app-version.mjs` reads it and both
  the build and `scripts/package.mjs` stamp it. Do not hand-edit it.
- **Exact dependency versions, no ranges.** Everything the later phases need is
  already installed, so a phase should not have to touch `package.json`. The
  one exception is the workspace links, `"@text-to-cad/core": "*"` and
  `"@text-to-cad/ui": "*"`: those resolve to the root workspace's packages,
  not to a registry, and `*` is how npm workspaces spell that.
  (`tests/unit/main/package-json.test.ts` holds this and the version above.)
- **No symlinks, ever** (repo-wide law: installers disagree about them and one
  drops them silently).
- **Nothing goes in the traffic lights' corner.** On macOS AppKit paints the
  close/minimise/zoom buttons over the top-left of the window, so the leftmost
  pane's strip reserves `--titlebar-inset` and no control may start inside it.
  The inset is measured from Chromium's window-controls overlay
  (`src/renderer/lib/titlebar.ts`), not typed into a stylesheet; the constant
  in `src/shared/titlebar.ts` is the fallback, and `tests/e2e/shell.spec.ts`
  fails when the two drift or when any state puts a control in the corner. A
  new full-window route reserves the room itself, the way Settings does.

- **Focus is handed on whenever the control under it unmounts, and a refused
  action keeps focus on its control.** A permission answer goes to the
  composer, a refused one stays on the card; rename's Enter and Escape go to
  the title button; every Reconnect or Retry on the session screen, the
  transcript's included, goes through `handToComposer` (`reconnectFromBar` and
  `retry` in `SessionView.tsx` both start with it); leaving Settings goes to the composer
  (`focusSessionHome`, `src/renderer/app/pane-focus.ts`, where `PANE_HOMES` is
  shared with F6); a pane that collapses under focus hands it to its toggle.
- **Every route has exactly one `main`.** The shell's session, Settings and the
  Welcome each draw their own; a search in Settings has one (hidden) h1 and
  the pages are h2.
- **A streaming live region is `aria-busy` while it streams, and not while it
  waits on a permission.** The transcript (`Transcript.tsx`) holds its
  announcements back until a turn settles, but a permission card must be
  announced. A failure is `role="alert"`, a wait or a count is
  `role="status"`.
- **A side pane is `{ collapsed, width }` and nothing else** — the sidebar's in
  `settings.layout`, the explorer's per session in `state/explorer.ts`. What is
  rendered, where each toggle is drawn and which pane reserves the traffic
  lights' corner are all derived from those two pairs, and **a collapsed pane is
  not rendered at all**, so a toggle exists in the document exactly once. Do not
  add a second collapse: a panel library with its own flag, or a width
  recomputed into shares behind the preference, is what made a drag under a
  minimum sometimes snap back and sometimes close a pane with no toggle left
  anywhere to reopen it. The geometry is `lib/panes.ts` (pure) and the drag is
  `app/PaneSeparator.tsx`; the session never collapses, and 40px past a
  minimum is the collapse (`PANE_LIMITS.overshoot`).
- **Every shortcut is a row in `src/renderer/lib/shortcuts.ts`, and every
  Application row with a modifier is a menu accelerator** in
  `src/main/menu.ts` — and every accelerator is a row
  (`tests/unit/main/shortcuts-menu.test.ts`). Add a key to both or to
  neither (the renderer-only rows are listed in the test). The table lists
  everything but the development build's `Reload App` (a packaged app has
  none); the toast chord in `components/ui/sonner.tsx` is the row "Focus the
  notifications", a two-binding row (`otherBinding`: Cmd+Option+T on a Mac,
  Ctrl+Shift+T elsewhere).
- **A global chord is checked on all three platforms.** It types no character
  with Option on a Mac (Option+T is a dagger), does not arrive as AltGr on a
  European keyboard (Ctrl+Alt), and is not GNOME's Ctrl+Alt+T.
- **The docs point at things that exist.** Every backticked path under src,
  tests, scripts or docs in README.md, AGENTS.md, `docs/` and
  the headers of the modules `tests/unit/main/doc-paths.test.ts` lists names
  something on disk, and the README's screenshot paragraph and the e2e specs
  name the same shots (`tests/unit/main/readme-screenshots.test.ts`). Rename a file, fix
  the sentence.
- **No bottom panel.** The terminal is a fourth explorer tab kind. Everything
  secondary lives in the one strip.
- **Each session owns its explorer and tools.** New sessions start with no
  tabs. Every tab, retained strip, terminal and browser target is scoped to
  the session id; sharing a directory grants no access to another session's
  tabs. Background tools never change the selected session. Read
  [session workspaces](docs/session-workspaces.md) before changing ownership.
- **Projects are derived directory groups, not saved entities.** The session
  index owns the directory identity. A folder choice before the first prompt
  is a transient draft; archiving the last session hides its group without
  deleting session data. Never reintroduce a project-delete cascade.
- **The renderer never picks a session's working directory.** It sends a git
  mode; main resolves it (`src/main/projects/workspace.ts`), creates the
  worktree, and writes `cwd`, `branch` and `worktreePath` onto the row. The one
  exception is Settings' `New session in this worktree`, which names a directory
  that already exists — and main checks it is the project or one of that
  project's own worktrees before running anything in it.
- **A review's `Last turn` and `This session` are revisions, not times.** Main
  records a snapshot tree of the working tree when a session is created and
  again at the start of every turn (`sessions.sessionHead` / `turnHead`;
  `snapshotTree` in `src/main/projects/git.ts`) — only the session mark of a
  worktree main cut fresh is a commit; the renderer sends the scope's *name*
  and main resolves it. Uncommitted work from before the turn is in the tree,
  so it is not the turn's. Two commits can share a second, and `--before=`
  picks a commit rather than a moment, so a timestamp cannot do this job.
- **A mark never fails or delays a turn or a create.** The turn and create
  paths wait on the snapshot at most `MARK_WAIT_MS` (5 s,
  `src/main/acp/sessions.ts`); past it a turn keeps the previous `turnHead` and
  a session mark is the commit, and the snapshot goes on. One snapshot runs per
  `<session id>/<kind>`, and a second asker takes the first's result. Whoever
  finds the row gone unpins its marks: the late snapshot, a create that failed,
  a turn whose session was deleted while it ran. Only a mark writes objects — a
  review's read lists untracked files in a throwaway index by intent-to-add — and
  an untracked file over 8 MiB (`SNAPSHOT_MAX_BYTES`) is left out of the tree,
  never hashed. Counting an untracked file for the review reads at most 1 MiB
  whole; a larger one is streamed and remembered by size and mtime.
- **A snapshot of the transcript is never filed while its connection replays,
  and never replaces a stored transcript with an empty one.** `onEvent` skips
  the write while the state is `connecting`; a reload that fails `discard`s the
  pending write and `loadNow` flushes before it starts, so the previous
  snapshot is the only copy of the history and stays whole
  (`src/main/acp/snapshots.ts`).
- **A closed or errored connection ends its open turn and settles its calls.**
  The reducer (`src/shared/acp/reduce.ts`) treats `status: closed` and
  `status: error` as the turn's end — calls and subagents `cancelled` or
  `failed` — because the adapter will send neither `prompt/end` nor
  `prompt/error`, and `retire` (`src/main/acp/sessions.ts`) files that closed
  state so a repaint from the snapshot is not a session still streaming. Every
  turn end cancels the cards still pending, and main cancels the client's
  pending permissions first, before it dispatches `prompt/end`. Content behind
  `prompt/end` lands on the closed last turn as a part of its own, and a
  settled call is never revived by a later `in_progress`.
- **A row's `connecting` has an exit on every path.** `create` ends it in
  success (`idle`), in `settleAfterFailedCreate` (`idle` again, the failure a
  note in `session.status.error`, while the connection is alive; the renderer
  holds it in `setupNotes` and shows it above the composer with a Retry setup
  button that calls `sessions.retrySetup`, never `load`; a retry's answer for a
  session forgotten or disconnected meanwhile is dropped), or by
  removing the row (`abandonCreate`) when the adapter is dead or the row is
  gone; a row closed under the create keeps that state (`stillConnecting`
  guards the write of `idle`). `loadNow`'s catch sets `error`; `boot` makes a
  stale one `closed`. A row left at `connecting` is a box that never opens.
- **A `create` that reached `session/new` resolves with its live session.**
  Only a dead adapter or a deleted row rejects, and it takes the row, the
  connection and the worktree that create cut with it (`abandonCreate`); a
  delete rejects with `DELETED_WHILE_STARTING`, which `NewSession` swallows.
  The renderer adopts the row a resolved create returns and offers no second
  create for it.
- **The composer follows the row and the connection together.**
  `src/renderer/features/session/SessionView.tsx` reads a session as
  `connecting` when the state says so or when the row does and no reconnect
  behind a painted transcript is under way, and `state()` reports `connecting`
  for a live idle connection whose create is still open. Neither alone is the
  truth: the reducer says idle from `session/new`, the row says `connecting`
  until the preferences and marks have landed.
- **A prompt holds its session against eviction until its turn ends, and a
  create until it returns.** `held` (`src/main/acp/sessions.ts`) is part of
  `busy` beside `running`, `waiting` and `connecting`; the connection is idle
  through the turn mark and the create's preferences, and the keep-alive limit
  would close it under them.
- **"In use" for a worktree is one function, `sessionsUsing`**
  (`src/main/projects/git.ts`): sessions that are not archived and run in the
  worktree, under it, or record it. Settings' count, Delete's refusal, the
  keep-limit sweep, a session's release and the CAD viewer's stop (archive and
  delete, `forgetCadSession`) all ask it; an archived session holds no worktree.
  Delete from Settings is kept on four grounds, and the row says which
  (`keptBecause`, `features/settings/pages/GitPage.tsx`): locked
  (`git worktree lock`), git could not check it for unsaved work, unsaved
  work (uncommitted changes or ignored files that are not a disposable
  cache), and an open session. Main refuses a worktree in use even forced
  and unsaved work unless the request says `force`; a lock is git's own
  refusal.
- **A settings write main refuses is rolled back and said, and a key with a
  write in flight keeps its value until that write settles.** `patch`
  (`src/renderer/state/settings.ts`) puts back what main last reported for the
  keys it owns and toasts; an older reply or `settings.changed` never moves a
  key a newer write owns, and `setLayout`/`setSidebar` build their whole object
  from the optimistic state.
- **One bad stored settings field never breaks the others.** Each field parses
  alone (`parseFields` in `src/main/db/repositories.ts`) and a refused one takes
  its default; `settings.fallbacks` reports it in `refused`, field to stored
  text. A stored value of the wrong JSON type is `refused`, never `gone`; a path
  that is a file is `gone` with the reason `file`, and a path with nothing at
  it with `missing` — the row says "a file, not a folder" for the one and
  "no longer exists" for the other.
- **The viewer warm is gated by a model in the root; the daemon is not.**
  `warmCad` starts a root's viewer only when `hasCadFile` finds a model in it,
  and warms the build daemon on every bind (unless the kernel is `missing` or
  `unsupported`). At most three viewers run, and the least recently asked-for
  is stopped for a fourth unless a CAD tab is open on its root (`openCadRoots`,
  non-archived sessions), so the bound is exceeded rather than a tab's viewer
  evicted.
- **A viewer launch checks its generation after every await, and every stop
  bumps it.** `ViewerManager` compares the root's stop generation after the
  runtime resolves, when the launcher announces and when a restart's backoff
  ends; `stop` and `stopAll` bump it, so a stop that lands mid-launch is
  never overtaken by the launch or the restart that was already under way
  (`tests/unit/main/viewer.test.ts`).
- **A live viewer command replies only once its effect is committed, and the
  predicate compares against what the runtime records, not the request.**
  `attachLiveBinding` waits a settled frame and the command's predicate, at
  most ten seconds, then "The viewer did not finish applying this command."
  (what each command waits for: [Live commands](../../packages/ui/docs/cad-renderer.md#live-commands)).
  That sentence reaches the agent because main's relay waits 12 s
  (`VIEWER_REPLY_TIMEOUT_MS`) for the viewer commands, its clock starting before
  the IPC send; "the text-to-cad window did not answer within 12 s (is one open?); the command may still complete, so check before retrying" means a window was there and
  none replied, and with no window at all the refusal is the different sentence "no text-to-cad window is open; open one and retry". A reply on the call returning would hand an agent a state the
  command had not produced yet.
- **Every capture goes through `imageResult`.** It redraws an image over
  `MAX_IMAGE_BYTES` smaller and refuses it only when it cannot be made to fit,
  so no tool result larger than the model takes enters a transcript
  (`src/renderer/state/image-result.ts`).
- **The quit deadline spares the warm daemon by pid, never by process group.**
  The app-owned viewer is `detached` too, so a group spare would spare it; the
  watchdog gets `daemonPids()` (a daemon's pid leaves it when it exits, so a
  reused pid is never spared), and its one probe runs under a timeout so a
  hung `ps` cannot stall the final kill. Windows has no spare list and its tree
  kill takes the daemon (`src/main/quit-deadline.ts`, README "Quitting").
- **A browser harness gets a fresh dependency cache per run.** A Vite server
  under `tests/browser` takes a new temp `cacheDir`, names what its scan cannot
  see in `optimizeDeps.include`, and asserts the page loaded once
  (`tests/browser/pdf-renderer.test.mjs`).
- **A pass that touches `packages/ui` runs the kit boundary check.**
  `node scripts/test/check-kit-boundaries.mjs` from the root: the kit is
  format-blind in its comments too.
- **A git write child is signalled at quit, never killed first.**
  `endTrackedChildren` sends a commit, push or worktree add/remove SIGTERM so
  git drops its `index.lock`; `will-quit` kills what is left
  (`src/main/children.ts`).
- **A browser tab id can come back over new contents, and every guard keys to
  the contents.** The `destroyed` handler ignores a target a later page replaced
  under the same id, the CDP adapter keys its sessions and target ids to the
  owning contents, and `disposePages` acts only for the newest call of a session
  (`docs/browser.md`).
- **A typed address survives blur.** The address bar's draft is dropped by
  Escape or by the URL moving while the field is not focused, never by a URL
  change under a focused field; a committed one shows until the page moves on,
  and an Enter during input-method composition is not a commit
  (`src/renderer/features/explorer/BrowserTab.tsx`).

- **A migration's backup is named by the newest version.** `db()` writes
  `before-v<latest>-<ms>.bak` with `latest` the last entry of `MIGRATIONS`, and
  `tests/e2e/session-storage.spec.ts` derives the name from `MIGRATIONS.at(-1)`
  rather than typing a number; a new migration edits neither.
- **A watch is returned with the root it was taken with.** A file source gives
  its opened paths back through the project and root it was created for
  (`requestAt`, `adapters/fileSource.ts`), and the store unwatches the root it
  had bound (`previous.root`), never the root the explorer has since moved to.
- **A terminal spawns once per tab.** `spawning` in `TerminalTab` is keyed by
  tab id, not by component instance, so a double effect or a body that unmounts
  and mounts while `terminal.create` is in flight cannot start a second shell
  that would be an orphan counting toward the agent's 16.
- **A deduped tab is disposed like a close.** `dedupeFileTabs` returns the tabs
  it drops, and the two writers of a strip (`commit` and `updateSessionStrip`,
  `state/explorer.ts`) run `disposeTab` on them, the function `close` uses, so
  a dropped duplicate's document record, CAD state and tab store are released
  as a close releases them.
- **Path containment is `climbsOut`/`isInside`** (`src/main/explorer/fs.ts`),
  never a `startsWith("..")` on a `path.relative`: a folder named `..keep` is an
  ordinary name and climbs nowhere (`tests/unit/main/git-paths.test.ts`,
  `client.test.ts`, and `mcp-bridge.test.ts` for `attach_snapshot`).
- **A check that is followed by an open re-checks the handle.** `readSnapshot`
  (`src/main/integrations/actions.ts`) opens the file, then resolves the path
  again with a fresh `realpath`, which must still be inside the workspace and
  name the very file the handle holds (`fstat` device and inode). A path is a
  claim about the moment it was checked; a link swapped in after it is not
  followed out of the root (`tests/unit/main/mcp-bridge.test.ts`).
- **A job's running state comes from the store.** `useJob(agentId, kind)`
  (`features/settings/AgentDrawer.tsx`) reads the running job from
  `useAgents.jobs`, not from component state, so a drawer or welcome that
  remounts finds the installer under way and disables Install and Sign in. The
  job is seeded in the store when main names it (`seedJob`, `state/agents.ts`),
  not on its first byte, so a silent install is found too.
- **A draft that resyncs from the store compares the normalised value.**
  `useDraft` (`features/settings/SettingCard.tsx`) takes a `same()` predicate;
  a field whose text is parsed on the way in (the Advanced environment) says
  when the store's value is its text, or the blur that saves it rewrites what
  the person typed (`tests/unit/renderer/agent-advanced.test.tsx`).
- **A session mutation writes the row first.** Create writes the row before it
  spawns the agent; archive and delete write it before they revoke tokens,
  dispose pages, kill shells or release a worktree. A write that throws leaves
  the session whole with its tools, and a create whose `repo.upsert` throws
  releases the worktree it cut and its tokens (`abandonCreate`)
  (`tests/unit/main/acp-archive-order.test.ts`, `tests/unit/main/sessions.test.ts`). Archive first joins an
  in-flight create, bounded at `ARCHIVE_WAIT_MS`, so it closes a session that
  exists rather than one about to be removed; `prompt` and `NewSession` never
  reconnect an archived row.
- **A precondition is re-checked immediately before the irreversible step.** The
  worktree sweep asks `stillEligible` again right before `git worktree remove`,
  because the checks before it are several git calls and a session can open in
  between (`removeWorktree`, `src/main/projects/git.ts`).
- **A row records whether its create cut the worktree.** `worktreeOwned` is set
  when the create made a fresh worktree and not when it was handed one
  (`New session in this worktree`); `boot` and `abandonCreate` release only
  the worktrees that flag names.
- **A relayed command reports possible completion on abort or timeout.**
  Once `RendererCommands.request` has sent a command the window may have
  applied it, so a timeout says the command "may still complete", an abort
  after the send says it "may already have been applied", and the bridge says
  "was applied, but the request was aborted before the reply" for a handler
  that finished first; none reads as a failure with nothing done
  (`tests/unit/main/mcp-bridge.test.ts`).
- **The terminals an agent can create are capped, and the cap is checked
  before the pty is registered.** `Terminals.create` takes `maxPerSession`
  (16 for `create_terminal`, counting every pty of the session, the person's
  own and stopped ones included), so concurrent calls cannot each see room
  (`tests/unit/main/terminal-actions.test.ts`).
- **A persisted id of a live resource is released on load unless a live one
  answers to it.** `explorer.loadTabs` nulls a terminal tab's `ptyId` that no
  pty of the session owns, because ptys die with the app
  (`tests/unit/main/terminal-ipc.test.ts`).
- **Nothing lands on its final path until it is complete.** A save writes a
  temporary sibling and renames it (`src/main/explorer/fs.ts`); the onboarding
  sample is copied to `<target>.copying` and renamed into place, so a copy that
  dies leaves staging for the next run to discard, never a half-sample that
  reads as the person's own (`tests/unit/main/onboarding.test.ts`).
- **A probe's timeout must survive a slow runner's spawn, so a budget is fitted
  by needing fewer probes.** Starting a process on a loaded CI runner outran the
  150 ms an earlier quit watchdog gave two probes; it now runs one, with room
  for it (`WATCHDOG_PROBE_TIMEOUT_MS`, `src/main/quit-deadline.ts`).
- **A unit test asserts no wall-clock bound, except where a documented budget is
  the contract.** The two exceptions are the quit watchdog's budget
  (`tests/unit/main/quit-deadline.test.ts`) and the teardown's
  (`tests/unit/main/quit-sequence.test.ts`); a bound anywhere else fails on a
  loaded machine and says nothing about the code.

Domain MCP servers and focused skills are composed by `src/main/integrations/registry.mjs`. Read [the integration contract](docs/integrations.md) before adding session-to-app capabilities.
