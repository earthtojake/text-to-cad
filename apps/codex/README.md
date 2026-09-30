# CAD app (Codex)

The page an agent host renders for the CAD plugin: **CAD** in the sidebar, the
**CAD** tab beside a thread, and *Open with CAD* for a model file. It is the same
`@text-to-cad/ui` FileViewer and renderers `apps/web` composes, behind a
different host: an MCP Apps bridge instead of an HTTP origin. Its server is
`cadgen mcp` (`packages/cadgen/src/cadgen/mcp`).

## The rules

- **One page, told what to show.** Every surface loads this one page. The tool
  that opened it returns a *launch* — `page` (`home` or `viewer`), `model`,
  `root`, `explore` — and the page renders it. The server computes the root from
  the thread's workspace; the page never guesses where it is, and nothing here
  branches on a surface's name (`surface` is only reported back to the server).
- **Host-neutral shared code.** Codex specifics live here and in `cadgen/mcp`,
  never in `packages/core` or `packages/ui`, which choose by capability (the
  prompt destination's `kind`, a port's presence). A policy test enforces it:
  `tests/python/global/test_host_neutral_packages.py`.
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
| `server.ts` | typed calls to the server's tools |
| `tunnel.ts` | the `fetch` over `cad_http` |
| `files.ts` | the read-only `FileSource` over the catalog; no listing when the launch does not browse |
| `prompt.ts` | Add to prompt: the composer via `ui/update-model-context`, references as absolute paths |
| `live.ts`, `events.ts` | the mounted view's live controller, and the `cad_events` long-poll that answers the agent (`show`, `capture`, `describe`) |

Pages: `Home.tsx` (Open Model, search, Pinned, Recent) and `ModelView.tsx`
(the FileViewer for one launch); `App.tsx` switches between them.

## Develop

```bash
npm run build:codex                          # packages, then this app
npm --prefix apps/codex run test             # jsdom units
scripts/install/codex-dev-plugin.sh --restart   # run it in the Codex app
```

`scripts/test/test-js.sh --select codex` is what CI runs: the tests, then the
build. A checkout's `cadgen mcp` serves `apps/codex/dist` when it exists
(`CADGEN_CODEX_APP_DIR` overrides it); a wheel serves `cadgen/_runtime/codex`,
built by `scripts/bundle/bundle.sh`.
