# CAD app (MCP Apps)

The page an agent host renders for CAD: the same `@text-to-cad/ui` FileViewer and
renderers `apps/web` composes, behind a different host — an MCP Apps bridge
instead of an HTTP origin. Its server is `cadgen mcp`
(`packages/cadgen/src/cadgen/mcp`).

Hosts present it in one of two ways, which the server tells apart at
`initialize` (Codex names itself `codex-mcp-client`; an MCP Apps host advertises
the `io.modelcontextprotocol/ui` extension):

- **Tabs (Codex).** **CAD** in the sidebar, a **CAD** tab beside each thread,
  and *Open with CAD* for a model file. The agent opens a tab once (`cad_open`)
  and drives it (`cad_show`).
- **Inline (Claude Desktop, and every other MCP Apps host).** Each `cad_show`
  mounts a viewer card in the chat, and the host keeps the old cards. A card
  shows the model and, where the host takes model context, Add To Prompt (a
  compact viewer), goes full size on request, and a newer card retires the
  older ones.

A client that renders no MCP Apps never loads this page: its `cad_show` answers
with the model's link in the CAD Viewer, started or reused for its folder
(`cadgen/mcp/browser.py`), and opens no browser. `CADGEN_MCP_PRESENTATION=inline`
tells the server that a client renders apps without advertising them, as the
reference host `basic-host` does.

## The rules

- **One page, told what to show.** Every surface loads this one page. The tool
  that opened it returns a *launch* — `page` (`home` or `viewer`), `model`,
  `root`, `explore` — and the page renders it: the shared CAD viewer over the
  launch's root, showing its model or, with none, the home. Every launch names a
  root, the home's included. The server computes the root from the workspace; the
  page never guesses where it is, and nothing here branches on a surface's name
  (`surface` is only reported back to the server).
- **The root follows context, as the host's own file tree does.** A model in the
  thread's project (Codex's workspace, or the roots a host lists) browses that
  project's catalog: `workspace`. A model with no project around it — the
  sidebar's Open Model, a chat with no folder — browses its filesystem: `global`,
  rooted at `/` or its drive and never walked. Its explorer reads each folder it
  opens (`/__cad/list`) from wherever the model is, up and down, and its catalog
  holds only the file on screen; a hidden folder the file is in still shows, so
  the tree reaches it. The home browses the workspace, else the filesystem the
  user's home is on, and a file picked in its explorer is launched by the server
  (`cad_launch`), as the library's are. A surface that shows one file (*Open with
  CAD*, an inline card) has no explorer, and reads only that file.
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
- **Add To Prompt only where it lands.** It sends `ui/update-model-context`. An
  inline host that does not declare `updateModelContext` in the
  `hostCapabilities` it answers `ui/initialize` with gets a viewer with no
  prompt action at all (`unavailablePromptContext`), not a disabled one. A tab
  host is not asked: Codex forwards the method whether or not its frame
  declares it.
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
  beside it.
- **No loading states of our own.** Opening a model switches straight to the
  viewer; the viewer's own progress is the only progress UI.

## Host adapter (`src/host`)

| Module | What it is |
| --- | --- |
| `bridge.ts` | JSON-RPC 2.0 over `postMessage`: requests, the opening tool's result, host context, teardown |
| `server.ts` | typed calls to the server's tools, `cad_reveal` among them: the file menu's Reveal, in the desktop's file manager (the server is on the person's machine) |
| `tunnel.ts` | the `fetch` over `cad_http` |
| `files.ts` | a filesystem's read-only `FileSource`, a folder at a time, whose copied references name files by absolute path (a project's is `@text-to-cad/ui/catalog`'s, as the web Viewer's is); no listing when the launch does not browse |
| `prompt.ts` | Add to prompt: the composer via `ui/update-model-context`, references as absolute paths; `reachesComposer`, whether the host has one |
| `live.ts`, `events.ts` | the mounted view's live controller (`@text-to-cad/ui/host`'s registry), and the `cad_events` long-poll that answers the agent (`show`, `capture`, `describe`) |
| `presentation.ts` | how the host presents the page, and the election that retires older inline views |

`ModelView.tsx` is the page: the shared `CadViewer` (`@text-to-cad/ui/cad-viewer`,
the one the web Viewer shows) over one launch's root, with this host's ports — its
tunnel, its composer, its file menu (copy path, copy relative path under a project,
Reveal through `cad_reveal`), the navbar's links, followed through `ui/open-link`,
and its library, with Open Model: the desktop's file chooser. With no model it is
the home; the navbar's C mark goes back to it (the launch a view opened on, when it
opened on the home). `App.tsx` frames it (full page, or an inline card with its
full-size button). In a tab, the viewer's bottom action sits on the line of Codex's
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
