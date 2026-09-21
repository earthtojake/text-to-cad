# The backend contract

The client never reads a filesystem path. It talks to HTTP routes under
`/__cad/*` and `/__tess_cache/*`, and the backend on the other side resolves
those to files.

**The backend is not in this directory.** It is `cadgen viewer` — the
`cadgen.viewer` package in the cadgen Python distribution — and its code, its
tests and its own laws live there. This file records only what the CLIENT may
assume, so that a change on either side has one place to disagree with. Launch,
reuse and dev-vs-prod are in [the app README](../README.md#launching).

## What the server is, and is not

- **One backend, one implementation.** Dev and production reach the same
  server; dev only adds a Vite proxy hop. A behaviour difference between them
  is a bug, not a code path.
- **One root per instance.** The served directory is the process's cwd, fixed
  at start. No request names a directory — there is no `dir` parameter
  anywhere, and `?file=` is always resolved inside the served root. Anything
  resolving outside it is refused, unconditionally, including on the route
  that compiles.
- **The render path runs no CAD kernel.** The one kernel action — importing a
  foreign STEP — is submitted as a compile job to cadgen's build pool; it is
  never work the server process does. Nothing in the server imports the kernel
  at module scope.
- **The server never touches the network.** Every byte it serves or reads is
  local.
- **In a source checkout ONLY, the server restarts itself.** When cadgen's
  Python changes, a checkout's server finishes the work in flight and
  re-executes on the same port; `/__cad/server` answers `autoReload: true` and
  its `identityToken` becomes a new value, which is the client's cue to reload
  the page. An installed wheel answers `autoReload: false`, never watches and
  never restarts — it is a development convenience, not a product behaviour,
  and it is not switched on by an environment variable. The full rationale is
  in `cadgen/viewer/reload.py`; the client half is
  `src/client/workbench/viewerAutoReload.js`.
- **No route hands a path to a desktop program.** The server answers with bytes
  and JSON. It never spawns a file manager or any other GUI application, and
  there is no download route, no content-disposition header, and no export
  route of any kind.

## Routes

| Method | Route | Answers |
|---|---|---|
| GET | `/__cad/server` | server features and availability flags |
| GET | `/__cad/catalog` | the scan of the served root, schema v4 |
| GET | `/__cad/artifact?file=…` | artifact status |
| POST | `/__cad/artifact?file=…` | compile the target (`&force=1` to redo) |
| GET | `/__cad/preview` | the active build's announced preview, when there is one |
| GET | `/__cad/store` | immutable store objects for a resolved tree |
| GET | `/__cad/asset?file=…` | raw file bytes, for rendering |
| POST | `/__cad/surfaces`, `/__cad/surfaces/cancel` | request / cancel a display-surface derivation |
| GET/POST | `/__tess_cache/<key>.tess` | one shared component-tessellation entry |
| POST | `/__tess_cache/batch`, `/__tess_cache/probe` | a bounded batch read, and a metadata probe |

An unrecognised `/__cad/*` path is a bad API call, not a page. `/__cad` without
the trailing slash is not an API path and falls through to the SPA.

**Verify a link by loading the page, never by curling `/__cad/asset`.** That
route serves raw files only; a generated entry's geometry arrives through
`/__cad/store`, so probing `asset` 404s whether or not anything is wrong.

## The two browser gates

The server binds loopback and serves unauthenticated: the loopback bind is the
trust boundary against other processes and machines. Loopback is NOT a boundary
against the user's own browser, so two gates defend against that specifically.

1. **Host validation.** A request whose Host names anything but
   `127.0.0.1` / `localhost` / `::1` is refused — the DNS-rebinding case, where
   an attacker domain re-resolves to loopback and the browser treats the server
   as same-origin. Skipped when bound non-loopback.
2. **Every POST must send `x-cadgen-viewer: 1`.** The value carries no meaning.
   `POST /__cad/artifact` compiles its target and all parameters ride the query
   string, so a cross-origin POST would otherwise be a no-preflight "simple
   request". A custom header forces a preflight instead. A POST without it gets
   403; GETs are unaffected.

**No `Access-Control-*` header is served, deliberately.** Their absence is what
makes the same-origin policy block cross-origin reads, and what makes that
preflight fail. Do not add them.

## What may be served

`?file=` resolution applies the served-asset extension filter BEFORE the
containment check, so a wrong extension is 404 and a right extension outside
the root is 403. A model script (`.py`) is not in the served-asset set and is
therefore unreachable through any route: the server serves OUTPUTS, never
source.

## Artifact status

Status is a verdict from pure file reads — no kernel, no source. The document's
byte digest resolves to one immutable geometry tree whose complete required
closure must verify. The wire states are `not-compiled`, `compiling`,
`compiled` and `failed`.

- **Complete native geometry means `compiled`.** Display-surface derivation and
  browser pixels have separate lifecycles, so a `compiled` artifact may still be
  waiting for a surface or a tessellation.
- Missing or damaged required geometry means `not-compiled`.
- Saved documents never consult source scripts, model records or source
  currency. Generated outputs are DETACHED from their source code: the viewer
  never treats "the script changed since this artifact was built" as a reason
  to rebuild, and it never rebuilds a generated entry — a generated model with
  no artifact reports an error naming the build (`python <model>.py`), not a
  build offer.
- "Is a build in flight" is not decided here. It is read from the daemon's job
  ledger, matched to the document by declared output path, and shown
  advisorily.

A raw `.step`/`.stp` with no tree in the store is importable: `POST
/__cad/artifact` submits the compile as an ordinary build-pool job. A STEP file
carries no cadgen metadata of any kind, so whatever produced it is irrelevant.

## The tessellation cache

`/__tess_cache/*` is the shared component-tessellation cache — the same store
the export CLI and the snapshot host use. The entry codec, the key scheme
(`<cid>-t<tessellator-version>-l<chord>-a<angle>`) and the TESB batch format
live in `cadgen-js` (`lib/surf/tessellationCache.js`); the client registers a
provider at bootstrap.

So component loads and viewport-LOD re-tessellations are cache hits whenever
ANY consumer — a snapshot, an export, a previous viewer session — tessellated
the component before, and misses write back. Entries are opaque bytes living
OUTSIDE every served root, so names are strictly validated.
`CADGEN_MESH_CACHE=0` disables both directions, and every cache failure
degrades to plain in-page tessellation.

## Storage tiers, in one rule

The cadgen cache root (`$CADGEN_CACHE_DIR`, else the platform cache directory)
holds everything CONTENT-ADDRESSED and DISPOSABLE: the component store, the
kernel op memo, and this mesh cache. Deleting any of it costs a rebuild, never
correctness — and nothing collects it automatically; `cadgen store info` and
`cadgen store gc` are the only sweepers.

The model's own folder holds everything meaningful: the artifact and its
sidecar. Browser-side tiers — query params, localStorage, directory and
per-file sessionStorage — are [storage.md](./storage.md).
