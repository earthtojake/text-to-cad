# CAD app (MCP Apps)

The page an agent host renders for CAD: the same `@text-to-cad/ui` FileViewer and
renderers `apps/web` composes, behind a different host — an MCP Apps bridge
instead of an HTTP origin. Its server is `cadgen mcp`
(`packages/cadgen/src/cadgen/mcp`).

Hosts present it in one of two ways, which the server tells apart at
`initialize` (Codex names itself `codex-mcp-client`; an MCP Apps host advertises
the `io.modelcontextprotocol/ui` extension):

- **Tabs (Codex).** **CAD** in the sidebar (the home: the models opened before,
  and Open), a **CAD** tab beside each thread, and *Open with CAD* for a model
  file. The agent opens a tab once (`cad_open`) and drives it (`cad_show`).
- **Inline (Claude Desktop, and every other MCP Apps host).** Each `cad_show`
  mounts a viewer card in the chat, and the host keeps the old cards. A card
  shows the model alone (a compact viewer: no tools, view actions, cube or Quick
  Edit), goes full size on request, and a newer card retires the older ones.
  Full size is the whole viewer, Quick Edit included.

A client that renders no MCP Apps never loads this page: its `cad_show` answers
with the model's link in the CAD Viewer, started or reused for its folder
(`cadgen/mcp/browser.py`), and opens no browser. `CADGEN_MCP_PRESENTATION=inline`
tells the server that a client renders apps without advertising them, as the
reference host `basic-host` does.

## The rules

- **One page, told what to show.** Every surface loads this one page. The tool
  that opened it returns a *launch* — `page` (`home` or `viewer`), `model`,
  `root`, `explore` — and the page renders it: the shared CAD viewer over the
  launch's root, showing its model, or the home. Every launch names a root, the
  home's included. The server computes the root from the workspace; the page never
  guesses where it is, and nothing here branches on a surface's name (`surface` is
  only reported back to the server).
- **A launch is enough to start.** It also carries what the server is — its
  `protocol`, `version` and `platform` — and the home's carries its `recents`,
  so the page asks nothing before it draws. A tab restored from an older build
  is launched again by today's server; one that still disagrees says so.
- **Only the sidebar has a home.** `cad_home` is its one launch with `page: home`:
  the library, and Open with the desktop's chooser. A model opened from it gets a
  back arrow to it in place of an explorer. Every other surface is about files a
  thread or chat shows, and has no home: with nothing shown yet it says "Ask the
  agent to show a model".
- **Only a project is browsed.** A model in the thread's project (Codex's
  workspace, or the roots a host lists) browses that project's catalog:
  `workspace`, with `explore`. A model with no project around it — opened from the
  home, or outside the workspace — is shown on its own: a `global` root at `/` or
  its drive, whose catalog holds only the file on screen (a hidden folder it is in
  included) and which nothing lists. *Open with CAD* and an inline card show one
  file and have no explorer either.
- **One request to the network: the newest release.** The page asks the server
  once (`cad_release`); the server asks GitHub's latest-release API at most every
  six hours and keeps the answer in the user's state directory (`release.json`,
  shared by every process), and a failure is no answer. A newer release is the
  blue download button (the navbar's, and the home's under its wordmark).
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
  origin `http://cad.invalid`; the server hands it to the viewer's own router.
  The fetch is a distinct function, so workers are handed bytes rather than URLs.
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
  that a person just touched it — and what it watches: its root's catalog and
  the build feed of a model being edited. Back come the agent's requests for it
  (`show`, `capture`), the catalog's revision, which the view reads again only
  when it moved, and each feed's status, handed to the client as its
  `editingPreviewFeed`. A sync that brought news (an event, a moving build) is
  followed by the next sooner.

## Host adapter (`src/host`)

| Module | What it is |
| --- | --- |
| `bridge.ts` | JSON-RPC 2.0 over `postMessage`: requests, the opening tool's result, host context, teardown |
| `server.ts` | typed calls to the server's tools, `cad_reveal` among them: the file menu's Reveal, in the desktop's file manager (the server is on the person's machine) |
| `tunnel.ts` | the `fetch` over `cad_http` |
| `files.ts` | a filesystem's read-only `FileSource`: the file on screen, never listed, whose copied references name files by absolute path (a project's is `@text-to-cad/ui/catalog`'s, as the web Viewer's is) |
| `prompt.ts` | Quick Edit's chat: `chatReach`, what the host's chat takes, and the prompt port over it — Queue through `ui/update-model-context` (a text block titled `Quick edit · <file>` and the sketch's image block, kept until the host clears its model context), Send through `ui/message` — with references as absolute paths (Copy Prompt spells them as copied references are) |
| `live.ts`, `sync.ts` | the mounted view's live controller (`@text-to-cad/ui/host`'s registry), and its sync (`cad_sync`), every second: its state for the agent, the agent's requests (`show`, `capture`), the catalog's revision and its build feeds |
| `presentation.ts` | how the host presents the page, and the election that retires older inline views |

`ModelView.tsx` is the page: the shared `CadViewer` (`@text-to-cad/ui/cad-viewer`,
the one the web Viewer shows) over one launch's root, with this host's ports — its
tunnel (which also carries a copied prompt's sketch to the server: `attachments`), its
chat, its file menu (copy path, copy relative path under a project,
Reveal through `cad_reveal`), the navbar's links, followed through `ui/open-link`,
and, on the sidebar, its library, with Open: the desktop's file chooser, where any file can be chosen.
With no model there it is the home, and a model opened from it has the navbar's back
arrow to it. `App.tsx` frames it (full page, or an inline card with its
full-size button). In a tab, preview's playbar sits on the line of Codex's
composer, which floats over the page (`--cad-viewport-bottom-center`), and the
home's and the explorer's lists scroll clear of it (`--cad-host-bottom-inset`).

## Develop

```bash
npm run build:mcp                             # packages, then this app
npm --prefix apps/mcp run test               # jsdom units
scripts/install/codex-dev-plugin.sh --restart   # run it in the Codex app
scripts/install/claude-dev-server.sh            # run it in Claude Desktop (then restart it)
```

`scripts/test/test-js.sh --select mcp` is what CI runs: the tests, then the
build. A checkout's `cadgen mcp` serves `apps/mcp/dist` when it exists
(`CADGEN_MCP_APP_DIR` overrides it); a wheel serves `cadgen/_runtime/mcp`,
built by `scripts/bundle/bundle.sh`.
