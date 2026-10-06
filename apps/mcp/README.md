# CAD app (MCP Apps)

The page an agent host renders for CAD: the same `@text-to-cad/ui` FileViewer and
renderers `apps/web` composes, behind a different host — an MCP Apps bridge
instead of an HTTP origin. Its server is `cadgen mcp`
(`packages/cadgen/src/cadgen/mcp`).

Hosts present it in one of two ways, which the server tells apart at
`initialize` (Codex names itself `codex-mcp-client`; any other host can declare
the `dev.texttocad/tabs` extension with the `global`, `thread` and `file`
entrypoints; an MCP Apps host advertises the `io.modelcontextprotocol/ui`
extension):

- **Tabs (Codex, and hosts that declare those entrypoints).** **CAD** in the
  sidebar (the home: the models opened before, and Open), a **CAD** tab beside
  each thread, and *Open with CAD* for a model file. The agent opens a tab once
  (`cad_open`) and drives it (`cad_show`). A host that declares tabs does what
  Codex does: it starts one `cadgen mcp` process per thread, since a call that
  names no view reaches the thread's own tab.
- **Inline (Claude Desktop, and every other MCP Apps host).** Each `cad_show`
  mounts a viewer card in the chat, and the host keeps the old cards. A card is
  the whole viewer at card size: its navbar (the logo, which opens the app menu,
  first; the file name that opens the explorer; the ⋯; then, at the right, the
  update button, and Full size last where the host can show a view full size), the
  tools, the view cube with Display and Preview on top of it, and Quick Edit. A
  newer card retires the older ones.

A client that renders no MCP Apps never loads this page: its `cad_show` answers
with the model's link in this machine's CAD Viewer, started if none runs
(`cadgen/mcp/browser.py`), and opens no browser. `CADGEN_MCP_PRESENTATION=inline`
tells the server that a client renders apps without advertising them, as the
reference host `basic-host` does.

## The rules

- **One page, told what to show.** Every surface loads this one page. The tool
  that opened it returns a *launch* — `page` (`home` or `viewer`) and `model`, a
  file's absolute path or none — and the page renders it: the shared CAD viewer
  showing that file, or the home. Agents name models by absolute path only, and
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
  model opened from it is shown in place. Under the home's wordmark are GitHub,
  Discord and X.
- **A view browses from its file's folder.** The file name in the navbar opens
  the explorer: one folder at a time, its subfolders and then its CAD files,
  starting at the file's; the last three folders as a breadcrumb, those above
  them under "…"; and "Filter files..." finds the files anywhere under the folder
  (the server's bounded `/__cad/search`). A pick shows the file and closes it.
  Nothing says where a view may browse: a tab, a card and the web viewer browse
  the same way.
- ***Open with CAD* is the file alone.** `cad_file` (`surface: file`) shows the
  file the host handed over, with no home and no explorer: the host's own file
  tree is its navigation. Its navbar still has the C logo and its menu, without
  Back to files.
- **An agent reads the sidebar too, and shows beside its thread.** Codex runs the sidebar page
  in a thread, and a server process, of its own, so no thread's agent syncs with it. Each process
  publishes its sidebar views beside the model library (`cadgen/mcp/sidebar_views.py`), and an
  agent's `cad_view` and `cad_screenshot` mean the view a person touched last of its thread's
  tabs and the sidebar's. A model it shows goes to its thread's tab (`cad_open` when there is
  none): Codex keeps the sidebar page running while the person is in a thread, so a model sent
  there lands where nobody is looking. Only a `cad_show` that names the sidebar's view reaches
  it. Only sidebar views are shared; a thread's tabs are that conversation's.
- **Two requests to the network: the version check, and analytics with consent.**
  Both go to `api.texttocad.dev` (the docs site's `/v1`). Once a day at most, cadgen
  reads the version feed (`cadgen/updates.py`): one anonymous GET, with no id and
  nothing about the person (`CADGEN_UPDATE_CHECK=0` turns it off; never in CI or from
  a source tree). While this install is behind, the navbar and the home show the
  shared blue `UpdateButton` (`@text-to-cad/ui/update`): first among the navbar's
  controls, and on the home a row of its own, labeled Update. A launch carries the
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
  Marketplace) is left to its store, and Gemini's extension to Gemini. The analytics: the server
  notes its use -- tool calls (not the page's plumbing), view activity from each
  view's sync (`focused`), and the files views show (counted as a view adds one to
  the library), as salted one-way codes --
  and sends it once a minute (`cadgen/analytics.py`): never a path, an argument or
  a file. It is on by default once a `cadgen` command has said so, once, and nothing
  asks; file codes go only with the person's yes. The app menu's **Share usage
  stats** (`appSettings`, through `/__cad/analytics`) changes the answer, one answer for
  this app and the browser viewer. Its **Quick edit** (on until
  the person turns it off) is read and changed the same way, through `/__cad/features`, and kept
  beside the analytics answer (`cadgen/features.py`): one choice for the sidebar, every
  thread's tab, every inline card and the browser viewer. The channel is reported with the
  counts; it decides nothing there. The agent's `cad_telemetry` reports the
  setting and turns it off, never on.
- **Told how it is presented, before it greets the host.** A host that mounts
  views inline is served the page with `<meta name="cad-presentation"
  content="inline">` in its head: the page offers that host `inline` and
  `fullscreen`. A tab host is served the file's bytes and offered `fullscreen`,
  as before inline hosts existed. `test_codex_contract` pins what Codex is
  served; supporting another host must not change it.
- **Inline views are named and ordered by the server.** Each inline launch
  carries `view` (the token the agent passes to `cad_view` and `cad_screenshot`:
  one process may serve many chats, and no host says which) and `order`
  (`{createdAt, seq}`). The views of a chat elect the newest over a
  `BroadcastChannel`. The others keep a still of their last frame, stop polling,
  stop sending context, and tell the server they are closed.
- **Quick Edit offers only what the chat takes.** `chatReach` reads the
  `hostCapabilities` the host answers `ui/initialize` with. **Queue** (the
  context for the person's next message, `ui/update-model-context`) needs
  `updateModelContext`; a tab host is not asked: Codex forwards the method
  whether or not its frame declares it. **Send** (the person's message now,
  `ui/message`) needs `message`, and carries a sketch as an image block only
  where the host declares `message.image`; a host that declares it and still
  refuses one (JSON-RPC -32602) gets the sketch saved and named by path
  instead. A host that takes neither gets Copy Prompt alone
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
  server travels this way, as the web page asks its own: the models, the
  library and its pictures, Open (`/__cad/pick`), Reveal, the person's analytics
  answer and features, the update check. Only the clipboard stays the host's: a
  view copies through its frame. So the page has three tools of its own:
  `cad_sync`, `cad_capture_reply` and `cad_http`, and a client with no page (a
  text client) is listed none of them, so nothing there answers for the person.
  The fetch is a distinct function, so workers are handed bytes rather than URLs.
- **No reply a host cannot read.** A reply is one JSON-RPC message, its body
  base64 (4/3 of its size), and a host that caps one message closes the
  connection past the cap, ending the server and every view on it: the MCP
  TypeScript SDK's stdio reader caps it at 10 MiB unless a host sets more
  (Claude Code 16 MiB, Claude Desktop 32 MiB). So no `cad_http` reply carries
  more than 4 MiB of body (`TUNNEL_REPLY_MAX_BYTES`), a message under 5.6 MB,
  for any model: the client asks for batched reads of at most that (the web
  client asks for 32 MiB), every GET asks for its first 4 MiB as a byte range,
  and a longer body comes back a range at a time, which the tunnel puts together
  for the client. A part of a body that changed meanwhile (its `etag`) fails the
  read, and the cache verifies a tessellation's digest of the whole as of any
  body. The server refuses any reply still longer (502), and an agent's
  screenshot longer than that, rather than send it. 4 MiB loads as fast as 8 MiB
  did.
- **One file.** The build inlines scripts, styles, workers (as blobs) and the
  drawing editor's fonts (as data URIs) into `dist/index.html`, and fails if
  anything would be left outside it: the host serves one resource and nothing
  beside it. Its scripts are still split where the app imports lazily (each
  renderer, the drawing editor and its libraries): each chunk is a gzip'd string
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
  that a person just touched it — and what it watches: its file's catalog entry
  and the build feed of a model being edited. Back come the agent's requests for it
  (`show`, `capture`), the catalog's revision, which the view reads again only
  when it moved, and each feed's status (whether a build is running or failed:
  the view shows the saved file), handed to the client as its
  `editingPreviewFeed`. A sync that brought news (an event, a moving build) is
  followed by the next sooner.

## Host adapter (`src/host`)

| Module | What it is |
| --- | --- |
| `bridge.ts` | JSON-RPC 2.0 over `postMessage`: requests, the opening tool's result, host context, teardown |
| `server.ts` | typed calls to the page's three tools: its sync, its answer to a capture, and `cad_http` |
| `tunnel.ts` | the `fetch` over `cad_http`, a long body a range at a time, and the CAD client over it (`App.tsx` makes one per view): the library, Open, Reveal and the person's settings among its requests |
| `prompt.ts` | Quick Edit's chat: `chatReach`, what the host's chat takes, and the prompt port over it — Queue through `ui/update-model-context` (a text block titled `Quick edit · <file>` and the sketch's image block, kept until the host clears its model context), Send through `ui/message` — with references as absolute paths (Copy Prompt spells them as copied references are) |
| `live.ts`, `sync.ts` | the mounted view's live controller (`@text-to-cad/ui/host`'s registry), and its sync (`cad_sync`), every second: its state for the agent, the agent's requests (`show`, `capture`), the catalog's revision and its build feeds |
| `presentation.ts` | how the host presents the page, and the election that retires older inline views |

`ModelView.tsx` is the page: the shared `CadViewer` (`@text-to-cad/ui/cad-viewer`,
the one the web Viewer shows) showing the launch's model, with this host's ports — its
tunnel (which also carries a copied prompt's sketch to the server: `attachments`), the
explorer's folders and search over it (`createCadFileSource`), its chat, its file menu
(copy path, Reveal), the app menu's links (its Send feedback and
an alert's Report Issue open a new issue), followed through `ui/open-link`,
and its home: the library, with Open, the desktop's file chooser, where any file can be
chosen. A view keeps its tab record in memory (`App.tsx`): the model on screen keeps
its view — camera, Display settings, pose — through updates of it, and leaving it for
another model or the home drops it, as in the web Viewer. A view the
host creates again (its frame re-created) starts afresh: nothing names a view across its
frames, so there is nothing to keep its record under. `App.tsx` frames it (full page, or
an inline card whose height the host is told; its Full size is the navbar's last control). In a tab, preview's playbar sits on the line of Codex's
composer, which floats over the page (`--cad-viewport-bottom-center`), and the
home's list scrolls clear of it (`--cad-host-bottom-inset`).

## Develop

```bash
npm run build:mcp                             # packages, then this app
npm --prefix apps/mcp run test               # jsdom units
scripts/install/dev_install.py codex --restart  # run it in the Codex app
scripts/install/dev_install.py claude-desktop   # run it in Claude Desktop (then restart it)
```

`scripts/test/test-js.sh --select mcp` is what CI runs: the tests, then the
build. Every host `dev_install.py` takes is in CONTRIBUTING.md ("Test In Agent
Apps"). A checkout's `cadgen mcp` serves `apps/mcp/dist` when it exists
(`CADGEN_MCP_APP_DIR` overrides it); a wheel serves `cadgen/_runtime/mcp`,
built by `scripts/bundle/bundle.sh`.
