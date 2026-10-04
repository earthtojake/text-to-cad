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

`cadgen viewer list` reports running instances, their roots and, for a
`--detach` launch, the log its output goes to.
`cadgen viewer stop --port <port>` stops an instance after verifying its identity.
Do not stop an instance you did not start. A detached instance's log outlives
it: a clean `stop` removes it, and one that crashed or was killed keeps it for
a day (the newest ten), so the reason can still be read.

## Development

After the root workspace dependencies and shared packages are built, invoke
Vite from the directory to serve, outside `apps/web`:

```bash
cd <the directory to serve>
VIEWER_PYTHON=<checkout>/.venv/bin/python \
  npm --prefix <checkout>/apps/web run dev -- --host 127.0.0.1
```

Dev root resolution first honors an explicit `directoryRoot` from its caller,
then the first of `INIT_CWD` and the process working directory that is outside
`apps/web`. Otherwise Vite defaults to `<checkout>/apps`. npm preserves its
invocation directory in `INIT_CWD`, so the command above chooses the served
root while `--prefix` locates the app. Open the bare origin with
`?file=<path relative to the served root>`; the URL path does not choose a root.

Vite serves the client from source with HMR. It spawns
`python -m cadgen.viewer --ephemeral --no-registry --api-only` and proxies
`/__cad` and `/__tess_cache` to that process. `VIEWER_PYTHON` selects its
interpreter; the default is `python3`. `VIEWER_BACKEND_URL` attaches to a backend
you started separately, using that backend's existing root. The app needs no
production build in this mode, but shared package imports still resolve to
their compiled `dist/` exports.

Vite defaults to port 5173 and refuses to roll to another port; pass `--port`
when needed. The development backend never enters the production instance
registry, and its API-only mode does not serve a SPA. See the
[app README](../README.md) for the complete development and launcher contract.

## Root and catalog

Each instance serves one fixed filesystem root. `LocalAssetBackend` resolves
and checks it at construction. Catalog entries include an absolute `file` and
a `rootRelativeFile` for navigation. The scan skips dot-directories and
`__cadgen__`, `__pycache__`, `build`, `coverage`, `dist`, `node_modules` and
`viewer` (`VIEWER_SKIPPED_DIRECTORIES`), and writes no `catalog.json` or hidden
catalog cache.

**The catalog is fresh on every request.** `GET /__cad/catalog` describes the
served tree as it is when the request arrives: a model file created before the
request is in it, one deleted before the request is not. The walk under that
promise remembers each directory's relevant rows (subdirectories, links, CAD
files) against the directory's own identity — device, inode, mtime, ctime —
and re-lists a directory when that identity changes, which adding, removing or
renaming an entry does. Link targets are re-stated on every request. Three
rules cover the stamps that fail to move:

- **Same tick.** A listing is served again only if the newer of its
  directory's mtime and ctime was already 2 s old when it was read, so a change
  landing in the same timestamp tick (1 s HFS+, 2 s FAT) cannot hide; a
  directory being written right now is re-listed every time.
- **Not a time.** A directory whose mtime or ctime is 0 or before 1980 — a
  macOS exFAT volume root reports 0 and never moves it — is re-listed every
  time.
- **Put back.** No listing is served for more than 10 s. tar, unzip, `rsync -a`
  and `cp -p` restore a directory's mtime after filling it; APFS, HFS+ and ext4
  still move its ctime, but FAT and exFAT have no ctime of their own and Windows
  reports creation time in its place, so there the identity can repeat exactly
  and the change shows within 10 s. The client polls every 2 s while its page is
  seen, so four polls in five stay warm.

The memo holds at most 65,536 directories, least recently walked dropped first,
and forgets a directory — with everything under it — once it is gone. A file's
content is not a listing fact: catalog rows fingerprint their own files.

A row is computed once per version of its file, whoever asks first: a read that
arrives while the same version's digest or row is being computed waits for that
computation rather than repeating it, and a read of a file that has changed since
asks about the new version. A version is the file's mtime and size and, for a save
by rename inside one tick of a coarse clock (HFS+, FAT, some shares), its inode and
ctime. A STEP whose tree the store cannot read whole (an object of it missing or
damaged) is the one row computed again on every read: it lists the document as
unbuilt, with no hash and a URL that names no tree, as the artifact status calls it
not compiled, and the compile that repairs the store restores the same bytes at the
same hashes, which moves nothing a version is made of. A build the client is
watching (its build feed,
`GET /__cad/preview`) that saves a file starts that file's row on a thread of the
server's as soon as the daemon's ledger lists the save (`cadgen.viewer.warm`),
so the catalog read that follows the build finds it computed or joins it. The
watched file goes first, since a parent saves after its children, and a lazy
root (the CAD app's whole filesystem, which lists only what a view names) warms
nothing else. The row is still the file's: its digest is read from the file's
bytes, and the tree the ledger says the build saved only starts that tree's
capture alongside. Warming is best effort: a row it cannot compute, or a thread
it cannot start, is left to the read, and the feed answers regardless.
Reading a file to hash it never holds up its deletion: the catalog opens models
with delete sharing on Windows, and a model that vanishes mid-read gets an empty
hash on that request and is gone on the next. A filesystem whose directory
listings are themselves cached, such as an NFS mount with attribute caching, is
only as fresh as that cache.

Both `/__cad/server` and `/__cad/catalog` expose `rootId`, a stable identity for
the normalized filesystem root. The host uses it for source and session-state
identity; changing the server port does not name a different root.

The catalog also carries `revision`, a digest of its entries that moves whenever
anything a client would see in them does. A host that cannot afford to read the
whole catalog on a timer (the CAD app relays every request through its host's
few shared slots) compares the revision it is told with the client's
`catalogRevision`, and reads the catalog again only when they differ.

`/__cad/asset` applies root containment, hidden-path rules and the served-asset
extension filter. Model scripts are excluded. It and `/__cad/store` serve a
project's files as data, never as pages: each response carries
`x-content-type-options: nosniff` and `content-security-policy: default-src 'none';
sandbox`, so a file opened straight in the browser (a robot description's XML can
carry an XHTML `<script>`) runs no script and has an origin of its own. The
renderers fetch the bytes, which neither header affects. Absolute references returned by
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
`@text-to-cad/core/lib/surf/tessellationCache.js`. Cache names are validated before
access because this shared store is outside the served root.

The browser host constructs a `CadClient` from `@text-to-cad/core/client` and
injects it into the viewer renderers. Catalog subscriptions share the client's
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
| `GET /__cad/catalog` | Current catalog, root identity and `revision`. |
| `GET /__cad/asset?file=...` | Allowed artifact bytes inside the served root. |
| `GET /__cad/store?file=...` | Virtual render assets from the shared store. |
| `GET /__cad/drawing?file=...` | A `.dxf` flattened to 2D render primitives; the DXF pane's only source. |
| `GET /__cad/artifact?file=...` | Artifact status and advisory progress. |
| `POST /__cad/artifact?file=...` | Start importing a foreign STEP and answer at once (`compiling`; `compiled` when there is nothing to build); `&force=1` requests a rebuild. The import is followed through `GET /__cad/artifact`, whose `failed` carries the job's reason until the file's bytes change. |
| `POST /__cad/sketches?name=...` | Save a PNG a copied prompt names by path (a Quick Edit's sketch) as scratch in the system's temporary directory; answers its absolute path. |
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

## `GET /__cad/drawing`

A 2D drawing is rendered on the SERVER. `cadgen.drawing_payload` runs ezdxf's
drawing add-on over the `.dxf`'s modelspace and returns what every entity
flattens to — text outlined, dimensions exploded, hatches filled or patterned,
block inserts placed — so the client draws primitives and never parses DXF.

`cadgen dxf snapshot` draws the SAME payload: its resolver calls
`cadgen.drawing_payload` too, writes the bytes where the headless page can fetch
them, and the page paints them with `@text-to-cad/core/lib/drawing2d` — the module
the DXF pane paints with. One flattening, one renderer, so the CLI cannot
produce a picture this route could not.

`?file=` takes the same refs the asset route does (root-relative, or the
absolute path the catalog hands out) and applies the same containment rule:
outside the root is 403, a hidden path component or a missing file is 404, and
anything that is not a `.dxf` is 400. An unreadable drawing is 400 with the
reason and the repair; the server retries a damaged file through
`ezdxf.recover` before giving up. The answer is `application/json;
charset=utf-8`, uncompressed (the backend has no gzip helper and this route did
not add one).

```jsonc
{
  "schemaVersion": 1,
  "units": { "insunits": 4, "name": "Millimeters", "toMillimetres": 1.0 },
  "bounds": [minX, minY, maxX, maxY],        // null when nothing was drawn
  "layers": [{ "name": "CUT", "color": "#ff0000", "count": 12 }],
  "primitives": [{ "type": "lines", "layer": "CUT", "color": "#ff0000",
                   "geometry": [[0, 0, 40, 0]] }]
}
```

- **Coordinates** are DXF modelspace coordinates, **y up**, rounded to 4
  decimals and written as integers where they are whole. `bounds` is computed
  from those same rounded numbers and includes Bezier control points, so it is
  a conservative box that never clips.
- **`color: null`** means the drawing's default pen (ACI 7 — "whatever
  contrasts with the background"). The client paints those with the theme's
  foreground, which is why one payload serves both the light and the dark
  theme. Every other ACI and every true colour is a literal `#rrggbb`. A layer
  row's `color` is null on the same rule. Lineweights are not in the payload:
  the client draws hairlines, as AutoCAD does with LWDISPLAY off.
- **`primitives[].type`** is ezdxf's own vocabulary: `point` (`[x, y]`),
  `lines` (`[[x0,y0,x1,y1], …]`), `path` (SVG-like `["M"|"L"|"Q"|"C"|"Z", …]`
  commands), `filled-paths` (a list of those command lists, even-odd filled)
  and `filled-polygon` (an explicitly closed `[[x, y], …]` ring).
- **`layers`** lists only layers that drew something, in first-seen order.

The payload is derived data, cached in the store's `drawing` index under the
document's content hash plus the extraction scheme, so a second request for
unchanged bytes re-serves stored bytes without entering — or importing —
ezdxf. See `packages/cadgen/STORE.md` §2.

Rendering is CPU-bound Python on the request thread (~0.1 s for a 1k-entity
drawing, ~0.7 s for 10k on a warm laptop), and the server is a
`ThreadingHTTPServer`, so a large cold drawing holds the GIL against other
requests for about that long. If drawings that size become routine, the
escalation is cadgen's build pool — the same move the STEP import made — not a
second thread pool here.
