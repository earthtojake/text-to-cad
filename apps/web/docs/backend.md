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

A viewer serves every CAD file on the machine by absolute path, on port 3245 or
the port `--port N` names. Run the installed CLI from anywhere:

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
cadgen viewer --host 127.0.0.1 --json
```

`--dist <directory>` is the command-line equivalent of `CADGEN_VIEWER_DIST`.
Repository setup and editable-install instructions live in
`CONTRIBUTING.md`.

Before it binds, the launcher asks the port who holds it (`GET /__cad/server`).
Nothing: it starts there (`action: "started"`). This user's viewer at the same
identity — the cadgen version plus content digests of the Python runtime and
the selected built client — is reused (`action: "reused"`). This user's viewer
running other code is asked to exit (`POST /__cad/shutdown`) and the launch
starts on the freed port: the newest code wins, on the same URL. Anything else
— another program, another user's viewer — is a refusal naming `--port`.
`--new` binds an OS-assigned free port, never asks and is never reused (dev
servers and tests). Always use the printed URL. The JSON response reports
`url`, `port`, and `action` only after the socket is bound and the app is
attached.

`cadgen viewer stop [--port N]` asks this user's viewer on a port to exit and
waits for the port to be free. A `--detach` launch writes the server's output
to one log in the state directory, `viewer.log`, which outlives the server so a
crash can be read afterwards, until the next detached start.

## Development

After the root workspace dependencies and shared packages are built, invoke
Vite from the folder a developer's relative links should resolve against,
outside `apps/web`:

```bash
cd <a folder of models>
VIEWER_PYTHON=<checkout>/.venv/bin/python \
  npm --prefix <checkout>/apps/web run dev -- --host 127.0.0.1
```

The spawned backend is started in the first of `INIT_CWD` and the process working
directory that is outside `apps/web`; otherwise Vite starts it in `<checkout>/apps`. npm preserves its
invocation directory in `INIT_CWD`, so the command above chooses that folder
while `--prefix` locates the app. The folder is `serverInfo.start`: the page
resolves a relative `?file=` against it, and it bounds nothing.

Vite serves the client from source with HMR. It spawns
`python -m cadgen.viewer --new --api-only` and proxies `/__cad` and
`/__tess_cache` to that process. `VIEWER_PYTHON` selects its interpreter; the
default is `python3`. `VIEWER_BACKEND_URL` attaches to a backend you started
separately. The app needs no production build in this mode, but shared package
imports still resolve to their compiled `dist/` exports.

Vite defaults to port 5173 and refuses to roll to another port; pass `--port`
when needed. The development backend's `--new` port is its own, and its
API-only mode does not serve a SPA. See the [app README](../README.md) for the
complete development and launcher contract.

## Files by absolute path

There is no served directory. Every `?file=` — and every path in a request body
— names a file by its absolute path (`/models/a.step`; on Windows `C:/models/a.step`
or `C:\models\a.step`), anywhere on the machine; a relative one is a 400
(`cadgen.viewer.backend`). Nothing is refused for where it is: no root, no
containment, and no rule about hidden folders on the way to a named file. A
UNC path (`\\host\share\a.step`) is refused, because any web page can make the
browser send a GET, and a GET must never send the machine to the network.

A view shows one file and browses from that file's folder, one folder at a
time, so nothing walks a tree to show it. `GET /__cad/catalog?file=<abs>` is
that file's row (`scanner.catalog_entry`) — `file` is its absolute path with
`/` separators, `url` where its bytes are served — or no row for a file that is
not a CAD file, is gone, or has a hidden name; with no `file`, the catalog is
empty. A row is computed from the file when it is asked for, so it is never
stale. It also carries `revision`, a digest of its entries that moves whenever
anything a client would see in them does: a host that cannot afford to read the
catalog on a timer (the CAD app relays every request through its host's few
shared slots) compares the revision it is told with the client's
`catalogRevision`, and reads the catalog again only when they differ.

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
watching (its build feed, `GET /__cad/preview`) that saves the file starts the
file's row on a thread of the server's as soon as the daemon's ledger lists the
save (`cadgen.viewer.warm`), so the catalog read that follows the build finds it
computed or joins it; only the watched file is warmed, never the other files the
build saved. The row is still the file's: its digest is read from the file's
bytes, and the tree the ledger says the build saved only starts that tree's
capture alongside. Warming is best effort: a row it cannot compute, or a thread
it cannot start, is left to the read, and the feed answers regardless. Reading a
file to hash it never holds up its deletion: the catalog opens models with delete
sharing on Windows, and a model that vanishes mid-read gets an empty hash on that
request and has no row on the next.

The explorer's two reads are `GET /__cad/folder?path=<abs>` (one folder's
subfolders and CAD files, natural order) and `GET /__cad/search?path=<abs>&q=`
(the CAD files under a folder whose path below it holds `q`, bounded by matches,
depth and time, and saying when it stopped early; `cadgen.viewer.folders`). A
relative path is a 400, a path that is not a folder a 404, one that cannot be
read a 403.

`/__cad/asset` sends only CAD files and their `.step.json`/`.stp.json`
sidecars, and never a file whose own name is hidden: a model script, a config
or a key is a 404 whatever path names it. It and `/__cad/store` serve files as
data, never as pages: each response carries `x-content-type-options: nosniff`
and `content-security-policy: default-src 'none'; sandbox`, so a file opened
straight in the browser (a robot description's XML can carry an XHTML
`<script>`) runs no script and has an origin of its own. The renderers fetch the
bytes, which neither header affects. No `Access-Control-*` header is ever
served, so another site can make the browser send a request but never read the
answer.

## Artifacts and the shared store

`cadgen.viewer.artifact_status` reads artifact/store state and advisory build
progress. Generated artifacts stay detached from their source: the viewer does
not execute model scripts or rebuild generated outputs. When generation is
needed, the alert names the CLI command.

A raw foreign `.step` or `.stp` without a current render artifact can be
imported. `cadgen.viewer.cadgen_ops` delegates to cadgen's compile entry point in
a worker process; the kernel runs there, and failures and progress return as
structured results. Import availability is reported as `stepImportAvailable`.
The service uses its own installed cadgen runtime, never an interpreter found
beside a model.

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
access: a request names an entry of the store, never a path.

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
| `GET /__cad/server` | Server identity: `identityToken`, `autoReload`, `platform` (which file manager Reveal opens), `user`, `start` (where relative links resolve), `pick` (a file chooser exists), `port`, `pid`. |
| `GET /__cad/catalog?file=...` | One file's catalog row and its `revision`. |
| `GET /__cad/folder?path=...` | One folder's subfolders and CAD files. |
| `GET /__cad/search?path=...&q=...` | The CAD files under a folder whose path holds `q`, bounded. |
| `GET /__cad/asset?file=...` | A CAD file's or sidecar's bytes. |
| `GET /__cad/store?file=...` | Virtual render assets from the shared store. |
| `GET /__cad/drawing?file=...` | A `.dxf` flattened to 2D render primitives; the DXF pane's only source. |
| `GET /__cad/artifact?file=...` | Artifact status and advisory progress. |
| `POST /__cad/artifact?file=...` | Start importing a foreign STEP and answer at once (`compiling`; `compiled` when there is nothing to build); `&force=1` requests a rebuild. The import is followed through `GET /__cad/artifact`, whose `failed` carries the job's reason until the file's bytes change. |
| `GET /__cad/recents` | The model library every CAD view shares. |
| `POST /__cad/recents` | `{action, path, png?}`: `open` (an existing CAD file on screen; counted for analytics), `pin`, `unpin`, `remove`, `thumbnail`; answers the library as it now is. |
| `GET /__cad/thumbnail?name=...` | A library picture, by its content name. |
| `POST /__cad/pick` | The desktop's own file chooser, held open while the person chooses: `{path}`, `{cancelled: true}`, a 400 naming the kinds CAD opens, a 500 with the chooser's own sentence (one already open among them). |
| `POST /__cad/reveal` | `{path}`: show a file in the desktop's file manager. |
| `POST /__cad/clipboard` | A PNG onto this machine's clipboard: the web page's picture copy, which asks the browser for no permission. |
| `GET`/`POST /__cad/analytics` | Whether the person's usage stats are sent, and why; `{share}` is their answer (the app menu's toggle). Nothing asks. |
| `POST /__cad/analytics/activity` | What the page did, for telemetry: `{touched: true}`, a person touched it; `{quickEdit: true}`, a Quick Edit went; `{crash}`, the page crashed (core's `crashOf`: its type and frames, checked again by the server, never a message). |
| `GET`/`POST /__cad/features` | The features a person can turn off, and their change of some. |
| `GET /__cad/version` | Whether a newer text-to-cad is out: the update button's `notice`, or null. |
| `POST /__cad/sketches?name=...` | Save a PNG a copied prompt names by path (a Quick Edit's sketch) as scratch in the system's temporary directory; answers its absolute path. |
| `POST /__cad/shutdown` | Exit: a newer launch replacing this viewer, or `cadgen viewer stop`. Answers 202, then stops and frees the port. |
| `GET /__tess_cache/<key>.tess` | Read a tessellation-cache entry. |
| `POST /__tess_cache/<key>.tess` | Best-effort tessellation-cache write-back. |
| `POST /__tess_cache/batch` | Read a batch of entries in a TESB container. |

Every POST must send `x-cadgen-viewer: 1`. The custom header forces a browser
preflight for cross-origin POSTs, and the server sends no CORS headers. When
bound to loopback, Host validation also refuses non-local names as a
DNS-rebinding defense. The trust model is documented in
`cadgen.viewer.http_app`; keep these gates intact.

The service serves local bytes and JSON. It has no download/export route, and
its host-native actions are the ones above (reveal, pick, clipboard). CLI
generation/export remain outside this HTTP interface.

Backend tests live in `tests/python/packages/cadgen/viewer` and are run by
`scripts/test/test-python.sh`. The web app's `npm run test` covers its JavaScript
host only.

## `GET /__cad/drawing`

A 2D drawing is rendered on the SERVER. `cadgen.drawing_payload` runs ezdxf's
drawing add-on over the `.dxf`'s modelspace and returns what every entity
flattens to — text placed, dimensions exploded, hatches filled or patterned,
block inserts placed — so the client draws primitives and never parses DXF.

`cadgen dxf snapshot` draws the SAME payload: its resolver calls
`cadgen.drawing_payload` too, writes the bytes where the headless page can fetch
them, and the page paints them with `@text-to-cad/core/lib/drawing2d` — the module
the DXF pane paints with. One flattening, one renderer, so the CLI cannot
produce a picture this route could not.

`?file=` names the drawing by its absolute path, as every route does: a
relative ref, or anything that is not a `.dxf`, is 400, and a missing file 404. An unreadable drawing is 400 with the
reason and the repair; the server retries a damaged file through
`ezdxf.recover` before giving up. The answer is `application/json;
charset=utf-8`, uncompressed (the backend has no gzip helper and this route did
not add one).

```jsonc
{
  "schemaVersion": 2,
  "units": { "insunits": 4, "name": "Millimeters", "toMillimetres": 1.0 },
  "bounds": [minX, minY, maxX, maxY],        // null when nothing was drawn
  "layers": [{ "name": "CUT", "color": "#ff0000", "count": 12 }],
  "fonts": [{ "family": "Arial", "weight": 400, "italic": false }],
  "primitives": [{ "type": "lines", "layer": "CUT", "color": "#ff0000",
                   "geometry": [[0, 0, 40, 0]] },
                 { "type": "text", "layer": "0", "color": null, "text": "NOTE 1",
                   "font": 0, "height": 2.5, "width": 12.94,
                   "transform": [1, 0, 0, 1, 10, 20] }]
}
```

- **Coordinates** are DXF modelspace coordinates, **y up**, rounded to 4
  decimals and written as integers where they are whole. `bounds` is computed
  from those same rounded numbers and includes Bezier control points and each
  string's box, so it is a conservative box that never clips.
- **`color: null`** means the drawing's default pen (ACI 7 — "whatever
  contrasts with the background"). The client paints those with the theme's
  foreground, which is why one payload serves both the light and the dark
  theme. Every other ACI and every true colour is a literal `#rrggbb`. A layer
  row's `color` is null on the same rule. Lineweights are not in the payload:
  the client draws hairlines, as AutoCAD does with LWDISPLAY off.
- **`primitives[].type`** is ezdxf's own vocabulary: `point` (`[x, y]`),
  `lines` (`[[x0,y0,x1,y1], …]`), `path` (SVG-like `["M"|"L"|"Q"|"C"|"Z", …]`
  commands), `filled-paths` (a list of those command lists, even-odd filled)
  and `filled-polygon` (an explicitly closed `[[x, y], …]` ring) — and `text`.
- **`text`** is one line of text where ezdxf placed it (a TEXT, an MTEXT line or
  word, a dimension's measurement): the string, its face (`font`, an index into
  `fonts`), its cap `height`, the advance `width` ezdxf measured in that face, and
  `transform`, `[a, b, c, d, e, f]` in Canvas 2D's order, from the string's own
  space (baseline-left at the origin, y up) to the drawing — alignment, rotation,
  width factor, mirroring and block transforms already in it. The client sets the
  string at that cap height in the face it has under that name and stretches it to
  `width`, so a face that differs from the server's keeps the server's layout.
  Text inside a clipped block reference arrives outlined (`filled-paths`), since
  only paths can be clipped. Outlined, a line of text was ~23 KB; as `text` it is
  ~150 bytes.
- **`layers`** lists only layers that drew something, in first-seen order.

The payload is derived data, cached in the store's `drawing` index under the
document's content hash plus the extraction scheme, so a second request for
unchanged bytes re-serves stored bytes without entering — or importing —
ezdxf. See `packages/cadgen/STORE.md` §2.

Bytes the store has not drawn are rendered OFF the request
(`cadgen/viewer/drawings.py`): the request starts the render on a thread of its
own, or joins the one already running for those bytes, and waits on it at most
2 s. A render that ends within that is the answer; one still running answers
`202 {"state": "drawing", "retryMs": 0}`, and the client asks again after
`retryMs` (the CAD app's tunnel holds 0.25 s and asks for 750 ms, since its calls
share the host's few slots). The client bounds each request by how long the
server stays silent — 10 s to the headers, then 10 s between parts of the body —
never by how long a drawing takes, so a drawing that renders for a minute opens,
and a server that stopped answering still fails. One render per drawing: every
request for the same bytes joins it, and its answer is kept for 30 s after it
ends, so the next request is answered even where the store could not keep it.
Rendering is CPU-bound Python (~0.2 s for 2,000 lines of text, ~1 s for 6,000,
~3 s for 100,000 LINEs on a warm laptop) and still holds the GIL against the
server's other threads while it runs. If drawings that size become routine, the
escalation is cadgen's build pool — the same move the STEP import made — not a
thread pool here.
