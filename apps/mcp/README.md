# CAD app (MCP Apps)

The page an agent host renders for CAD: the same `@text-to-cad/ui` FileViewer and
renderers `apps/web` composes, behind a different host — an MCP Apps bridge
instead of an HTTP origin. The installation's engine serves its tools, page resource and HTTP routes.
`cadgen mcp` is the stateless stdio shim that agent hosts launch: it ensures that
engine, then forwards JSON-RPC to `/mcp` using its installation token. Each shim
negotiates a separate MCP session. Closing a shim releases that session and leaves
the engine, its workers and other clients alive.

Hosts present it in one of two ways, which declared capabilities select at
`initialize` (the shim translates Codex’s `codex-mcp-client` identity; any other host can declare
the `dev.texttocad/tabs` extension with the `global`, `thread` and `file`
entrypoints; an MCP Apps host advertises the `io.modelcontextprotocol/ui`
extension):

- **Tabs (Codex, and hosts that declare those entrypoints).** **CAD** in the
  sidebar (the home: the models opened before, and Open), a **CAD** tab beside
  each thread, and *Open with CAD* for a model file. The agent opens a tab once
  (`cad_open`) and drives it (`cad_show`). These remain separate because the host mounts
  the UI from static tool metadata: adding that metadata to `cad_show` would mount a new
  view on updates too. A conditional server result cannot promise host-side tab reuse. A host that declares tabs does what
  Codex does: it starts one `cadgen mcp` shim per thread. Each connects to a separate
  engine session, so an unnamed view belongs to that thread.
- **Inline (Claude Desktop, and every other MCP Apps host).** Each `cad_show`
  mounts a viewer card in the chat, and the host keeps the old cards. A card is
  the whole viewer at card size: its navbar (the logo, which opens the app menu,
  first; the file name that opens the explorer; the ⋯; then, at the right, the
  update button, Full size where the host can show a view full size, Display and
  Preview, and last Open in browser), the tool strip
  ending in Display and Preview, the file sidebar, the view cube, and Quick Edit. A
  newer card retires the older ones.

A client that renders no MCP Apps never loads this page: its `cad_show` answers
with the model's page in this machine's CAD Viewer, `/<id>` (the file registered by its id, as
a launch registers it), started if none runs (`cadgen/mcp/browser.py`), and opens no browser. `CADGEN_MCP_PRESENTATION=inline`
tells the shim that a client renders apps without advertising them, as the
reference host `basic-host` does.

The agent also has `cad_export`, `cad_snapshot` and `cad_inspect` in
all presentations, including text-only hosts. They use the Python operations,
not page state. Each tool starts work with a request ID and polls or cancels its
own operation; there is no `cad_job` tool. See the
[operation contract](../../packages/cadgen/README.md#agent-operations) for progress,
retry, cancellation and explicit server-host destinations. No tool builds source
text: to build a shape, wrap the shape in a decorated function and run its script.
Inspection never builds. The web viewer's Export is a browser download; this page has no Export, having no HTTP origin to download from.

## The rules

- **One page, told what to show.** Every surface loads this one page. The tool
  that opened it returns a *launch* — `page` (`home` or `viewer`) and `model`, a
  file's absolute path, a model's document id, or none — and the page renders it: the shared
  CAD viewer showing that document, or the home. Agents name a file by its absolute path and a
  model by the id its script printed (a script is never a document), and
  nothing here branches on a surface's name but one: `surface: file` (below).
- **A launch is enough to start.** It also carries what the server is — its
  `protocol`, `version` and `platform` — and the home's carries its `recents`,
  so the page asks nothing before it draws. A launch from another build (a tab
  the host restored after an update, a past chat's card) says so: the page
  reads only its own protocol's.
- **Every view has a home.** Back to files, first in the menu the navbar's C logo
  opens, goes to it: the library (the models opened before, in any view or the web
  viewer) and Open with the desktop's chooser, where this computer has one
  (`pick`). The sidebar (`cad_home`) and a tab with nothing to show open on it; a
  model opened from it is shown in place. The home has the same navbar (the C menu, Back
  and Forward, the update button, Full size and Open in browser); under its wordmark are GitHub,
  Discord and X.
- **A view browses from its file's folder.** The file name in the navbar opens
  the explorer: one folder at a time, its subfolders and then its CAD files,
  starting at the file's, a subfolder opening inline at a press and in the
  explorer's place at a double-click; as many of the last three folders as fit whole as a
  breadcrumb, those above them under "…"; and "Filter files..." finds the files
  anywhere under the folder (the server's bounded `/__cad/search`). A pick shows
  the file and closes it. Nothing says where a view may browse: a tab, a card and
  the web viewer browse the same way.
- **A view keeps its own history.** As a browser keeps a tab's: every file a
  view showed, and the home, in order, the agent's shows and the person's own
  moves alike (`ModelView.tsx`). The navbar's Back and Forward, after its logo,
  over a file and on the home, walk it, each disabled where it has nowhere to go:
  from a file opened on the home, Back returns home and Forward to the file. A
  move after a Back drops what was ahead, and a show of what is already on screen
  adds nothing.
  It is the view's, in memory: another tab or card has its own, and a view opened
  again starts with one step. Going back opens that model afresh, as a browser's
  Back does in the web viewer. A file handler's view, which shows its file alone,
  has neither button.
- ***Open with CAD* is the file alone.** `cad_file` (`surface: file`) shows the
  file the host handed over, and nothing else, for as long as it is open: no home
  and no explorer (the host's own file tree is its navigation), no Back or Forward,
  and a renderer's link to another file (a robot's mesh) is plain text. Its navbar
  still has the C logo and its menu, without Back to files. The agent reads it
  (`cad_view` lists it) but shows nothing in it: `cad_show` refuses its view, and
  the page ignores a show that reaches it anyway.
- **An agent reads the sidebar too, and shows beside its thread.** Each MCP session
  owns its conversation views. Sidebar views alone are shared across sessions in the
  engine’s memory (`cadgen/mcp/sidebar.py`). Selection and capture replies cross sessions
  directly, with no file registry. `cad_show` targets the thread’s tab unless it names
  the sidebar’s view. A session closing removes its sidebar views; stale views expire
  by the same heartbeat rule as other views.
- **Two requests to the network: the version check, and analytics with consent.**
  Both go to `api.texttocad.dev` (`apps/api`). Once a day at most, cadgen
  reads the version feed (`cadgen/updates.py`): one anonymous GET, with no id and
  nothing about the person (`CADGEN_UPDATE_CHECK=0` turns it off; never in CI or from
  a source tree). While this install is behind, the navbar and the home show the
  shared blue `UpdateButton` (`@text-to-cad/ui/update`): first among the navbar's
  controls, over a file and over the home. A launch carries the
  notice the server last read, so the button draws with the page; the page reads it
  again (`/__cad/version`) when the person comes back to it. It opens the update card: "A new version of text-to-cad
  is available. Send a message to your agent asking it to update to the latest
  version:", and a prompt worded like the install message, "Update text-to-cad to
  0.9.0 from https://github.com/earthtojake/text-to-cad".
  **Send to agent** posts it as the person's message (`ui/message`) where the host
  takes messages (`chatReach`); elsewhere the card's button is **Copy prompt**.
  The prompt has a copy icon in its top-right corner either way. **Manual installation** opens the docs site's
  Install section (`https://www.texttocad.dev/install`) through `ui/open-link`, for a
  person whose agent cannot do it. The agent does
  the update, with the commands under its app's heading in the text-to-cad README;
  nothing here updates anything.
  A text client gets the same line with its first `cad_show` result. Where the
  install came from is its channel, which each plugin's startup config names in
  the server's environment (`CADGEN_INSTALL_CHANNEL`, `cadgen/_internal/channel.py`),
  with `CADGEN_AUTO_UPDATED=1` where something else keeps the copy up to date: only a
  copy nothing else updates checks and is told. A store's copy (the Claude or OpenAI directory, the Cursor
  Marketplace) is left to its store, and Gemini's extension to Gemini. The telemetry: the server
  counts its use -- tool calls (not the page's plumbing), view activity from each
  view's sync (`focused`), and the files views show (counted by format, once a day,
  as a view adds one to the library) --
  and sends the counts at most every five minutes (`cadgen/analytics.py`): never a path,
  an argument or a file. A Quick Edit that went is counted through the host's `usage`, and
  crashes are reported too: a tool's call or a route that failed for no reason its caller
  gave, and the page's own (`main.tsx`, its frames named by the chunks the inline loader
  made blob URLs of, and by each chunk's debug id), as their type and frames, never a message.
  The build keeps a source map of each chunk as the page runs it (`dist/sourcemaps`, which a
  release uploads to PostHog), leading into the shared packages' own source, whose modules
  load with their maps (`@text-to-cad/core/source-maps`): every edit the build makes to a
  module or a chunk is folded into rolldown's map, each import's placeholder is as wide as the
  blob URL that replaces it, and the chunk's debug
  id is the one its edited text and map decide (`@text-to-cad/core/chunk-ids`), never the
  id of the unedited chunk the CAD Viewer may ship. It is on by default once
  a `cadgen` command has said so, once, and nothing asks. The app menu's **Share usage
  stats** (`appSettings`, through `/__cad/analytics`) changes the answer, one answer for
  this app and the browser viewer. The channel is reported with the
  counts; it decides nothing there. The agent's `cad_http` reads the setting with
  `GET /__cad/analytics` and turns it off with `POST /__cad/analytics`, body
  `{"share":false}` (base64 in the tool call). This works with no open page and
  in text-only hosts. Opt-out deletes the installation ID and requests deletion
  of data sent under it. The reply's `saved:false` means persisting the choice
  failed; agents cannot opt in.
- **Told how it is presented, before it greets the host.** A host that mounts
  views inline is served the page with `<meta name="cad-presentation"
  content="inline">` in its head: the page offers that host `inline` and
  `fullscreen`. A tab host is served the file's bytes and offered `fullscreen`,
  as before inline hosts existed. `test_codex_contract` pins what Codex is
  served; supporting another host must not change it.
- **Inline views are named and ordered by the server.** Each inline launch
  carries `view` (the token the agent passes to `cad_view` and `cad_screenshot`:
  one MCP session may serve many chats, and no host says which) and `order`
  (`{createdAt, seq}`). The views of a chat elect the newest over a
  `BroadcastChannel`. The others keep a still of their last frame, stop polling,
  stop sending context, and tell the server they are closed.
- **Quick Edit offers only what the chat takes.** `chatReach` reads the
  `hostCapabilities` the host answers `ui/initialize` with. **Queue** (the
  context for the person's next message, `ui/update-model-context`) needs
  `updateModelContext`; a tab host is not asked: Codex forwards the method
  whether or not its frame declares it. **Send** (the person's message now,
  `ui/message`) needs `message`. Both actions capture the current view and distinct drawn views at the
  press. Up to 1024 bytes of compact UTF-8 snapshot JSON goes into the text; larger
  packets are written as `.snapshot.json` and named by saved path. Views share the annotation. No images or file bytes are attached,
  even where the host accepts images. A host that takes neither gets Copy Prompt alone
  (`unavailablePromptContext`): Queue and Send are left out, not disabled. In
  Codex, Send from a thread's CAD tab posts into that thread; from the
  sidebar page it goes to the page's own chat tab.
- **Host-neutral shared code.** Host specifics live here and in `cadgen/mcp`,
  never in `packages/core` or `packages/ui`, which choose by capability (the
  prompt destination's `kind`, a port's presence, `environment.compact`). A policy
  test enforces it: `tests/python/global/test_host_neutral_packages.py`.
- **The web client's data path, unchanged.** `createCadClient` gets a `fetch`
  that sends each request as a `cad_http` tool call against the placeholder
  origin `http://cad.invalid`; the server hands it to the viewer's own router,
  over its own model library and analytics. Everything the page asks of the
  server travels this way, as the web page asks its own: the models -- a STEP's
  and an `.xbf`'s reads too, dispatched directly to the engine's document router
  that serves them (`/__cad/api/...`) -- the
  library and its pictures, Open (`/__cad/pick`), Reveal, the person's analytics
  answer and language, the update check. One route is the server's own, not the
  viewer's: `/__cad/browser`, the web viewer's page of what the view shows, and
  `/__cad/browser/open`, which opens that page in the person's browser, for Open in browser. Only the clipboard stays the host's: a
  view copies through its frame. `cad_sync` and `cad_capture_reply` remain app-only
  and are absent in text-only hosts. `cad_http` is shared with agents: without
  an app capability, only telemetry status and opt-out are authorized. Every
  page launch includes a session capability in result `_meta["dev.texttocad/httpToken"]`,
  which [MCP Apps hosts deliver to the UI](https://github.com/modelcontextprotocol/ext-apps/blob/main/specification/2026-01-26/apps.mdx#2-tool-results), outside model context; content and structured content never
  carry it. The page sends `x-cadgen-app` with HTTP calls, and the same capability
  as the `app` argument of `cad_sync` and `cad_capture_reply`, which refuse a call
  without it: a host is asked to keep app-only tools from the model, and the server
  does not rely on it. The server validates
  it before routing or serving cached ranges. An arbitrary guard header, view
  id, or caller assertion cannot grant app access; another session's capability
  fails. The local host itself retains installation-level authority.
  The fetch is a distinct function, so workers are handed bytes rather than URLs.
- **No reply a host cannot read.** A reply is one JSON-RPC message, its body
  base64 (4/3 of its size), and a host that caps one message closes the
  connection past the cap, disconnecting its shim and views: the MCP
  TypeScript SDK's stdio reader caps it at 10 MiB unless a host sets more
  (Claude Code 16 MiB, Claude Desktop 32 MiB). So no `cad_http` reply carries
  more than 4 MiB of body (`TUNNEL_REPLY_MAX_BYTES`), a message under 5.6 MB,
  for any model: every GET asks for its first 4 MiB as a byte range,
  and a longer body comes back a range at a time, which the tunnel puts together
  for the client. A part of a body that changed meanwhile (its `etag`) fails the
  read. The server refuses any reply still longer (502), and an agent's
  screenshot longer than that, rather than send it. 4 MiB loads as fast as 8 MiB
  did. The server produces such a body once: each later part names it
  (`if-range: <etag>`) and is cut from the body the first part kept, never by
  running the route again.
- **One file.** The build inlines scripts, styles and workers (as blobs) into
  `dist/index.html`, and fails if anything would be left outside it: the host
  serves one resource and nothing beside it. Its scripts are still split where
  the app imports lazily (each renderer): each chunk is a gzip'd string
  that becomes a blob module only when something imports it, so a view parses
  what it shows rather than all of the app (`vite.config.mjs`).
- **Nothing waits unseen.** While the home's list is read, placeholder cards (or
  rows) stand where the models will be; a model being opened shows a spinner over
  its picture, and takes no second press, until the launch switches to the
  viewer, whose own progress takes over.
- **Nothing is held open, and a view makes one call a second.** A host relays
  every call its views make through a few slots they all share, and holds a call
  until one frees: a call held open by one view queues every model load, picture
  and pick of the others behind it. So a view syncs (`cad_sync`, `host/sync.ts`),
  answered at once, about once a second (`views.POLL_SECONDS`). Up go what it
  shows — its model, its state whenever that changed (what `cad_view` reads),
  that a person just touched it — and what it watches: its file's catalog entry.
  Back come the agent's requests for it
  (`show`, `capture`), and the catalog's revision, which the view reads again only
  when it moved. A sync that brought news (an event) is followed by the next sooner.
  A STEP or an `.xbf` the view shows asks the engine for its next version about once a
  second, answered at once (`cadgen/mcp/tunnel.py`), and a document the engine is still
  reading answers `202` until it holds it: neither holds a call.

- **A capture is of the model asked about, once it is drawn.** An agent captures
  right after it opened a view, showed a model or rebuilt one, so `cad_screenshot`
  waits rather than refusing: for a view it just opened (a tab from `cad_open`, a
  card from `cad_show`) to sync for the first time (`OPENING_SECONDS`), then for
  the view to show that model loaded and drawn (`host/capture.ts`,
  `CAPTURE_SETTLE_MS`), within `views.CAPTURE_SECONDS` in all. A capture asked with
  a show is of the model shown, never of the one the view is leaving. What it
  cannot wait out it says: a card the chat never drew, a model that did not finish
  loading, a view out of sight that did not answer.

## Protocol migration

Protocol 9 replaces protocol 8: `cad_sync` and `cad_capture_reply` take the session's
app capability as an argument, as `cad_http` takes it as a header, and refuse a call
without it or with another session's; a page from an earlier build says CAD was updated.
Protocol 8 replaced protocol 7: reopen restored views so their launch carries the
app capability. `cad_telemetry` is removed, with no alias; agents use `cad_http`
with `GET /__cad/analytics` or opt-out `POST` and base64 `eyJzaGFyZSI6ZmFsc2V9`.
The obsolete `/__cad/features` route and shared client's `features()` are removed.
Quick Edit has no enable/disable setting in either app; stale `features.quickEdit`
values have no reader and cannot hide it. Settings files need no conversion.

## Host adapter (`src/host`)

| Module | What it is |
| --- | --- |
| `bridge.ts` | JSON-RPC 2.0 over `postMessage`: requests, the opening tool's result, host context, teardown |
| `server.ts` | typed calls to the page's three tools: its sync, its answer to a capture, and `cad_http` |
| `tunnel.ts` | the `fetch` over `cad_http`, a long body a range at a time, and the CAD client over it (`App.tsx` makes one per view): the library, Open, Reveal and the person's settings among its requests |
| `prompt.ts` | Quick Edit's chat: `chatReach`, what the host's chat takes, and the prompt port over it — Queue through `ui/update-model-context` (a text block titled `Quick edit · <file>` naming the snapshot path, kept until the host clears its model context), Send through `ui/message` — with references as absolute paths (Copy Prompt spells them as copied references are) |
| `live.ts`, `sync.ts` | the mounted view's live controller (`@text-to-cad/ui/host`'s registry), and its sync (`cad_sync`), every second: its state for the agent, the agent's requests (`show`, `capture`) and the catalog's revision |
| `presentation.ts` | how the host presents the page, and the election that retires older inline views |
| `clipboard.ts` | the frame's clipboard, every copy's: the asynchronous clipboard where the host grants it (the resource asks for `clipboardWrite`), else the page's own copy command, still inside the press, for text |

`ModelView.tsx` is the page: the shared `CadViewer` (`@text-to-cad/ui/cad-viewer`,
the one the web Viewer shows) showing the launch's model, with this host's ports — its
tunnel (which also carries a Quick Edit's views and annotation to the server, which makes their files: `promptFiles`), the
explorer's folders and search over it (`createCadFileSource`), its chat, its file menu
(copy path, Reveal), the app menu's links (its Send feedback and
an alert's Report Issue open a new issue), followed through `ui/open-link`,
and its home: the library, with Open, the desktop's file chooser, where any file can be
chosen. A view keeps its tab record in memory (`App.tsx`): the model on screen keeps
its view — camera, Display settings, pose — through updates of it, and leaving it for
another model or the home drops it, as in the web Viewer. A view the
host creates again (its frame re-created) starts afresh: nothing names a view across its
frames, so there is nothing to keep its record under. `App.tsx` frames it (full page, or
an inline card whose height the host is told; its Full size is the last of the navbar's
own controls before the view's). Last in the navbar, in every presentation, Open in browser
opens the web viewer's page of what the view shows — the document's, `/<id>` with the
viewer token, or the home's. The server opens it itself, on this computer: a press posts
the document the card shows (its path or id, never a URL) to `POST /__cad/browser/open`, a
`cad_http` route of the app's alone, and the server opens the browser on an owner-only
redirect file, so the token is on no command line (a host need not follow a link to a
loopback page, and Codex does not). Only where the server can open no browser (503: no
display, a remote shell) does the card open the page through `ui/open-link`. The card asks
the server for the page (`GET /__cad/browser`, app-only too, answered by the same
`browser.viewer_url` a text-only host's `cad_show` links) whenever what it shows changes,
and draws no button where the engine gives no page. In a tab, Codex's composer floats over the page, and the
home's list scrolls clear of it (`--cad-host-bottom-inset`). The cube sits at bottom-left
in this tab presentation, across sidebar, thread and file views, so the composer and
sidebar chat button can occupy bottom-right. `App.tsx` supplies
`--cad-viewport-corner-left: 2px` and `--cad-viewport-corner-right: auto`;
inline hosts (including full-size cards) retain the default bottom-right placement.

## Engine transport

The engine exposes authenticated Streamable HTTP at `/mcp`. Its private installation
socket supplies the endpoint and token; the shim sends Bearer authentication.
Initialize creates an opaque `Mcp-Session-Id`, which accompanies subsequent POSTs
and DELETE. Requests negotiate a supported MCP protocol revision. JSON replies need
no SSE stream, so GET returns 405. Missing sessions return 400; expired sessions 404.
When the engine restarts or a session's idle hour passes, the shim opens a new session
with the host's own initialize and sends again only the request the engine refused
unseen (404, or a refused connection); the host never reconnects. Views, operations
and the app capability start over with the new session, and mutations are never replayed.
Host-specific capability corrections live in `mcp/shim.py`. Version polls use `wait=0`
in the page’s tunnel so they never occupy a host call slot. The engine has no such
host-specific timing rule. The manifests continue to launch `cadgen mcp`.

## Develop

```bash
npm run build:mcp                             # packages, then this app
npm --prefix apps/mcp run test               # jsdom units
scripts/install/dev_install.py codex --restart  # run it in the Codex app
scripts/install/dev_install.py claude-desktop   # run it in Claude Desktop (then restart it)
```

`scripts/test/test-js.sh --select mcp` is what CI runs: the tests, then the
build. A build names itself in the app menu (`vite.config.mjs`, through
`@text-to-cad/ui/build-id`): the release's own build shows `v<VERSION>`, any other
`v<VERSION>-dev.<commit>`, the commit of the checkout it was built from. Every host
`dev_install.py` takes is in CONTRIBUTING.md ("Test In Agent Apps"). A checkout's `cadgen mcp` serves `apps/mcp/dist` when it exists
(`CADGEN_MCP_APP_DIR` overrides it); a wheel serves `cadgen/_runtime/mcp`,
built by `scripts/bundle/bundle.sh`.

## Live model addresses

The catalog and open/show actions accept `script.py::name` as well as file paths. Python scripts open to a declaration list read without
execution; selecting a model explicitly builds it. The shared viewer's In memory
collection reads the installation engine's live metadata. It never enters saved
recents or thumbnail storage, and disappears on worker retirement or engine restart.
Rebuilding a named model updates the same view through the document version stream.

The stdio peer exits with its host session; it deletes only that MCP session.
There is no viewer subprocess or file-backed sidebar registry to clean up.
Restart the installation engine explicitly after editing its Python source.
