# Backend

The browser host talks to `cadgen.viewer`, the HTTP service shipped in the
`cadgen` Python distribution. Its source lives in
`packages/cadgen/src/cadgen/viewer/`; this app owns the React host and its build.
The wheel includes that build at `cadgen/_runtime/viewer`, alongside the Node
and browser runtimes used by the CLI. Skills invoke the installed distribution.

The HTTP layer uses Python's standard library and requires Python 3.11 or newer.
It imports the lightweight cadgen catalog and store helpers, but never imports
the CAD kernel at module scope. Viewing renders existing artifacts, their
optional `<name>.step.json` kinematics sidecar and `<name>.step.js` authored
render module, and their cached geometry. Model source changes never trigger a
rebuild. The one compile operation offered by the viewer is importing a foreign
STEP through cadgen's build worker pool.

## Launching

Run the installed CLI from the directory to serve. Its working directory is
the root; there is no directory flag:

```bash
cadgen viewer --host 127.0.0.1 --json
```

The equivalent Python entry point is `python -m cadgen.viewer`, using the
interpreter where cadgen is installed. The launcher serves the client bundled
with cadgen. To use a checkout's client, build it from the repository root and
select it explicitly:

```bash
npm run build:web
export CADGEN_VIEWER_DIST="$PWD/apps/web/dist"
cd <the directory to serve>
cadgen viewer --host 127.0.0.1 --json
```

`--dist <directory>` is the command-line equivalent of `CADGEN_VIEWER_DIST`.
Repository setup and editable-install instructions live in
`CONTRIBUTING.md`.

The launcher reuses a live instance for the same resolved root and code identity.
That identity includes the cadgen version and the newest server/client file
mtime, so rebuilding a checkout changes the reuse key. Otherwise it binds the
first free port from 3245 upward. `--new` forces another instance of the same
code; an explicit `--port` is strict and fails if occupied. Always use the
printed URL, including its port. The JSON response reports `url`, `port`, and
`action` only after the socket is bound and the app is attached.

`cadgen viewer list` reports running instances and their roots.
`cadgen viewer stop --port <port>` stops an instance after verifying its identity.
Do not stop an instance you did not start.

## Development

After the root workspace dependencies and shared packages are built, run Vite
from `apps/web`:

```bash
VIEWER_PYTHON=<checkout>/.venv/bin/python npm run dev -- --host 127.0.0.1
```

Vite serves the client from source with HMR. It spawns
`python -m cadgen.viewer --ephemeral --no-registry --api-only` and proxies
`/__cad` and `/__tess_cache` to that process. `VIEWER_PYTHON` selects its
interpreter; the default is `python3`. `VIEWER_BACKEND_URL` attaches to a backend
you started separately. The app needs no production build in this mode, but
shared package imports still resolve to their compiled `dist/` exports.

Vite defaults to port 5173 and refuses to roll to another port; pass `--port`
when needed. The development backend never enters the production instance
registry, and its API-only mode does not serve a SPA. See the
[app README](../README.md) for the complete development and launcher contract.

## Root and catalog

Each instance serves one fixed filesystem root. `LocalAssetBackend` resolves
and checks it at construction. Catalog entries include an absolute `file` and
a `rootRelativeFile` for navigation. The scan skips dot-directories and writes
no `catalog.json` or hidden catalog cache.

Both `/__cad/server` and `/__cad/catalog` expose `rootId`, a stable identity for
the normalized filesystem root. The host uses it for source and session-state
identity; changing the server port does not name a different root.

`/__cad/asset` applies root containment, hidden-path rules and the served-asset
extension filter. Model scripts are excluded. Absolute references returned by
the catalog are valid only when they resolve inside the root. Artifact status
and compile routes apply the same containment rule, so compilation cannot be
used to reach an outside file indirectly through the store.

## Artifacts and the shared store

`cadgen.viewer.artifact_status` reads artifact/store state and advisory build
progress. Generated artifacts stay detached from their source: the viewer does
not execute model scripts or rebuild generated outputs. When generation is
needed, the alert names the CLI command. `/__cad/server` therefore reports
`stepArtifactGenerationAvailable: false`.

A raw foreign `.step` or `.stp` without a current render artifact can be
imported. `cadgen.viewer.cadgen_ops` delegates to cadgen's compile entry point in
a worker process; the kernel runs there, and failures and progress return as
structured results. Import availability is reported as `stepImportAvailable`.
The service uses its own installed cadgen runtime, never an interpreter found
inside the served directory.

Store layout and I/O have one implementation. `cadgen.viewer.store_paths` is a
thin adapter over `cadgen.catalog`, `cadgen.store` and the source-sidecar helpers;
it returns the strings and dictionaries expected by HTTP routes. The viewer
does not maintain a second store layout. See
`packages/cadgen/STORE.md` for objects,
document indexes, output records and cache-root resolution.

The tessellation routes likewise delegate reads, writes and TESB batch framing
to `cadgen.store.tess_cache`. `index/mesh/<key>` points to the object containing
the cached bytes. The shared JavaScript entry codec and key scheme live in
`@hardcore/core/lib/surf/tessellationCache.js`. Cache names are validated before
access because this shared store is outside the served root.

The browser host constructs a `CadClient` from `@hardcore/core/client` and
injects it into the CAD renderer. Catalog subscriptions share the client's
two-second poll and stop when its last subscriber leaves. Each prepared render
session owns its tessellation provider, work queue and cancellation signal;
there is no page-global provider registration. Session disposal releases its
resources, and the host disposes the client when finished. A cache miss or
failure falls back to ordinary tessellation; `CADGEN_MESH_CACHE=0` disables
cache reads and writes.

## HTTP routes

| Route | Purpose |
|---|---|
| `GET /__cad/server` | Server identity, root and capabilities. |
| `GET /__cad/catalog` | Current catalog and root identity. |
| `GET /__cad/asset?file=...` | Allowed artifact bytes inside the served root. |
| `GET /__cad/store?file=...` | Virtual render assets from the shared store. |
| `GET /__cad/design-outline?file=...` | Read-only Python source outline for a STEP; never executes source or recovers STEP history. |
| `GET /__cad/artifact?file=...` | Artifact status and advisory progress. |
| `POST /__cad/artifact?file=...` | Import a foreign STEP; `&force=1` requests a rebuild. |
| `GET /__tess_cache/<key>.tess` | Read a tessellation-cache entry. |
| `POST /__tess_cache/<key>.tess` | Best-effort tessellation-cache write-back. |
| `POST /__tess_cache/batch` | Read a batch of entries in a TESB container. |

Every POST must send `x-cadgen-viewer: 1`. The custom header forces a browser
preflight for cross-origin POSTs, and the server sends no CORS headers. When
bound to loopback, Host validation also refuses non-local names as a
DNS-rebinding defense. The trust model is documented in
`cadgen.viewer.http_app`; keep these gates intact.

The service serves local bytes and JSON. It has no download/export, native
file-manager or HTTP shutdown route. CLI generation/export and host-native
actions remain outside this HTTP interface.

Backend tests live in `tests/python/packages/cadgen/viewer` and are run by
`scripts/test/test-python.sh`. The web app's `npm run test` covers its JavaScript
host only.
