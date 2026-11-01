# Backend

The browser host talks to `cad_server.viewer`, the HTTP application hosted by the engine in the
`cad-server` Python distribution. Its source lives in
`packages/cad-server/src/cad_server/viewer/`; this app owns the React host and its build.
The wheel includes that build at `cad_server/_runtime/viewer`, beside the CAD app's one-file
page (`cad_server/_runtime/mcp`); the engine's snapshots are OCCT's and need no browser. Skills
invoke the installed distribution.

The HTTP layer uses Python's standard library and the distribution's Python floor.
It never imports the CAD kernel at module scope. Viewing renders existing files;
model source changes never trigger a rebuild. A STEP and an `.xbf` are documents
the engine serves (`cad.engine`, its daemon): the viewer asks the
engine to serve one; the page reads its routes directly, and the engine
reads, meshes and measures it in processes of its own.

## Launching

The engine serves every CAD file by absolute path on port 3245, or the port this
installation rolled to when another program held it (`cad status` says which and why),
or the one `--port N` or `CAD_ENGINE_PORT` names. Run the installed CLI from anywhere:

```bash
cad viewer --host 127.0.0.1 --json
```

The equivalent Python entry point is `python -m cad_server.viewer`, using the
interpreter where the server is installed. The launcher serves the client bundled
with the server. To use a checkout's client, build it from the repository root and
select it explicitly:

```bash
npm run build:web
export CAD_VIEWER_DIST="$PWD/apps/web/dist"
cad viewer --host 127.0.0.1 --json
```

`--dist <directory>` is the command-line equivalent of `CAD_VIEWER_DIST`.
Repository setup and editable-install instructions live in
`CONTRIBUTING.md`.

The launcher connects to this installation's engine, starting it if needed, and
exits after printing or opening its page's URL: `/<id>` for each FILE it names (an on-disk CAD
file it registers by the id of its canonical path, or a document id the engine holds), else the
home, `/`. `--json` prints the launch record without opening a browser. An explicit host or port
must match a running engine. There is one page per engine and no page session: each launch's
folder becomes the folder the home shows, replacing the last. Always use the printed URL,
including its token query; the browser exchanges the token for a same-site HTTP-only cookie.

`cad stop` stops the installation's whole engine, including its workers and
MCP sessions. Closing a page, a Vite process or a host's stdio shim does not stop it.
Python source edits require restarting your own test engine. There is no viewer
server process, source re-exec, detached launch log or per-port shutdown route.

## Development

After the root workspace dependencies and shared packages are built, invoke
Vite from the folder the home should show, outside `apps/web`:

```bash
cd <a folder of models>
VIEWER_PYTHON=<checkout>/.venv/bin/python \
  npm --prefix <checkout>/apps/web run dev -- --host 127.0.0.1
```

The launch's folder is the first of `INIT_CWD` and the process working
directory that is outside `apps/web`; otherwise Vite launches in `<checkout>/apps`. npm preserves its
invocation directory in `INIT_CWD`, so the command above chooses that folder
while `--prefix` locates the app. The folder is `serverInfo.start`: a launch's relative files
are read from it, and it bounds nothing.

Vite serves the client from source with HMR. It spawns
`python -m cad_server.viewer --api-only --json` (a launch) and proxies the engine's API, `/api`, to that
authenticated engine. `VIEWER_PYTHON` selects its interpreter; the
default is `python3`. `VIEWER_BACKEND_URL` attaches to a backend you started
separately, with its token in `CAD_ENGINE_TOKEN` (outside `VIEWER_`, the prefix Vite
hands to the page). The app needs no production build in this mode, but shared package
imports still resolve to their compiled `dist/` exports.

Vite defaults to port 5173 and refuses to roll to another port; pass `--port`
when needed. The API-only launch needs no built client; the engine is shared, and its page
serves whatever client it has. See the [app README](../README.md) for the
complete development and launcher contract.

## Files by absolute path

There is no served directory. The page addresses each document by its id (`/<id>`); every
request's `?path=` — and every path in a request body — names a file by its absolute path (`/models/a.step`; on Windows `C:/models/a.step`
or `C:\models\a.step`), anywhere on the machine; a relative one is a 400
(`cad_server.viewer.backend`). Nothing is refused for where it is: no root, no
containment, and no rule about hidden folders on the way to a named file. A
UNC path (`\\host\share\a.step`) is refused, because any web page can make the
browser send a GET, and a GET must never send the machine to the network.

A view shows one file and browses from that file's folder, one folder at a
time, so nothing walks a tree to show it. `GET /api/v1/documents?path=<abs>` is
that file's envelope (below), its row (`scanner.catalog_entry`) its `entry` — `file` is its absolute path with
`/` separators, `url` where its bytes are served, `id` its document's id (the id of its
canonical path, so a symlink and its target, or two case spellings, are one row) — or no row
for a file that is not a CAD file, is gone, or has a hidden name (no envelope); with an empty
`path`, none. A file asked for is registered by its id. `GET /api/v1/documents/<uuid>` is the envelope
of the document of that id: a file registered (by a launch or a row), or in Recents; else a model
the engine holds (`file` is its id, `name` its function, `sourcePath` null: it has no file to
browse); else a 404 whose `error` is the engine's words for why, naming the command that builds
it again, and whose `state` the engine's (`unsaved`, `detached`). A script is never a row. An
envelope says what the document is: `id`, `kind` (`model`, or a file's by its extension: `xbf`,
`step`, `stl`, `glb`, `3mf`, `dxf`, `urdf`, `srdf`, `sdf`), `name`, `version`, `state` (a model's,
the engine's: `live`, `held`, `building`, `failed`; a file's `live`), `source` (a model's script and
function, a file's path), `producers`, `api` (where its kind's reads are,
`/api/v1/documents/<kind>/<id>`), `exports` (the formats its Export offers), and for a document
the engine serves, `held` (whether the engine holds its read now, asked without starting one). A row is computed from the file when it is asked for, so it is never
stale. It also carries `revision`, a digest of its entries that moves whenever
anything a client would see in them does: a host that cannot afford to read the
catalog on a timer (the CAD app relays every request through its host's few
shared slots) compares the revision it is told with the client's
`catalogRevision`, and reads the catalog again only when they differ.

Every format's row is its file's: `kind` (its extension), `url`, `hash` and
`bytes`, and an SRDF's paired URDF. A STEP's and an `.xbf`'s say no more than that:
they are drawn from what the engine serves of them (below), and their rows
are what a view watches for a change of the file. A row's digest is the file's
sha256, computed once per version of the file (its mtime and size). Reading a
file to hash it never holds up its deletion: the catalog opens models with delete
sharing on Windows, and a model that vanishes mid-read gets an empty hash on that
request and has no row on the next.

The explorer's two reads are `GET /api/v1/local/folder?path=<abs>` (one folder's
subfolders and CAD files, natural order) and the same with `&q=`
(the CAD files under a folder whose path below it holds `q`, bounded by matches,
depth and time, and saying when it stopped early; `cad_server.viewer.folders`). A
relative path is a 400, a path that is not a folder a 404, one that cannot be
read a 403.

`/api/v1/local/files` (and a file document's `source`) sends only CAD files, and never a file whose own name is hidden:
a model script, a config, a `.json` beside a model or a key is a 404 whatever path names
it. It and the engine's document routes serve files as data, never as pages: each
response carries `x-content-type-options: nosniff`
and `content-security-policy: default-src 'none'; sandbox`, so a file opened
straight in the browser (a robot description's XML can carry an XHTML
`<script>`) runs no script and has an origin of its own. The renderers fetch the
bytes, which neither header affects. No `Access-Control-*` header is ever
served to a page by its cookie or a link in its URL, so another site can make the
browser send a request but never read the answer. The one exception is the
engine's, before any route: a request carrying a day link as its `Authorization`
Bearer (a CAD card reading the engine directly, `apps/mcp`), and its preflight,
are answered for the origin that sent them, with no credentials
(`cad_server.viewer.engine_app.EngineApp.preflight`).

## Engine documents: a STEP and an `.xbf`

A STEP (`.step`, `.stp`) and an `.xbf` open in the engine document renderer
(`@text-to-cad/ui`'s `renderers/xbf`), drawn from what the engine serves
of them (`cad_server.viewer.documents`). `POST /api/v1/documents` with `{"path": <abs>}` (or
`{"id"}`) acquires the file, or the document of that id as the engine holds it (never built), in
the already-running engine and answers `201 {id, kind, api}`, where `api` is
`/api/v1/documents/<kind>/<id>` on this same origin. The engine reads a file once and
holds it. XBF and STEP reads run in child processes; their kernel objects never
enter the HTTP process. A request waits at most two seconds before returning
`202 {"id", "kind", "api", "state": "reading", "retryMs": 0, "building"}` with `Retry-After`. The
envelope's `held` answers whether the engine holds it, without starting a read; the home
pictures a STEP only when it is held.

A kind's routes (`/api/v1/documents/<kind>/<id>/structure`, `parts/<key>` and its
`faces|edges|vertices/<ordinal>`, `groups` and `volume`, `measure`, `kinematics`, `pose`, `mesh`),
`/api/v1/look` and its `environment`, and `/api/v1/documents/<id>/version` dispatch directly to
the engine's own document reads, in process: structure, one buffer per part, element facts,
groups, volume, look, environment image and version wait. There is no network relay or separate viewer port.
The web page uses bounded version waits; the MCP page asks with `wait=0` so a
version check occupies no host call slot while waiting for an edit. The same
router handles reads tunneled through `cad_http`, in process. Document buffers
and routes retain the raw-file response headers and engine authentication.
The wire format is the engine README's **Wire format** section.

The browser host constructs a `CadClient` from `@text-to-cad/core/client` and
injects it into the viewer renderers. Catalog subscriptions share the client's
two-second poll and stop when its last subscriber leaves. The client's
`engineDocument(file)` answers the document's API URL on the client's origin and the
fetch every read of it is made with (the CAD app's goes over its tunnel).

## HTTP routes

Everything a page calls is under `/api/v1` (the pages themselves are `/`, `/<id>` and the CAD app's
module `/app`). Every refusal is JSON, `{"error", "hint"}` (what is wrong, and what to do), with its
status: an unknown route, kind or id is a 404 (never the page), a route asked with a method it does
not take a 405 naming the ones it does (`Allow`), a body over its route's limit a 413. A route on a
document of another kind is a 404 naming the right one (`"<id> is a step"`).

| Route | Purpose |
|---|---|
| `GET /api/v1/server` | Server identity: `app` (`cad-viewer`), `release` (the release the engine runs: a page that reconnects to another reloads), `identityToken`, `platform` (which file manager Reveal opens), `user`, `home` (the person's home folder: where a model's Files starts with nowhere else to start), `start` (the folder of the most recent launch, which its relative files are read from), `pick` (whether the home offers Open: the machine has a file chooser), `port`, `pid`; `instance`, a random token of this start of the engine (a page that reconnects to another reloads); `kinds` (`reads`, the document kinds, and `exports`, each kind's formats); and `notice` and `update` (below). |
| `GET`/`PUT /api/v1/settings` | The person's settings, one for every CAD view: `{language: {locale}, telemetry: {sharing, reason, policy}}` (`cad_server/language.py`; whether usage stats are sent, and why: nothing asks). PUT takes part of it, `{language: {locale}}` (null is Automatic) or `{telemetry: {share}}` (the app menu's toggle; `saved` says whether it was kept), and answers the whole. `telemetry` is null on a server that keeps no usage stats. |
| `GET /api/v1/look`, `/api/v1/look/environment` | The look the regular display modes are drawn in, and its Radiance image. |
| `GET /api/v1/documents` | The model library every CAD view shares, `{documents}`: pinned first, then by last activity; each row with `opened` (when a page last opened it) and `updated` (a file's time on disk, a model's run: a script is never read for it), its document's `id`, `kind` and `api`, and its record's kind (`record`: `file`, `model`, `shape`). `?kind=`, `?q=` (in its name or path), `?limit=`; `?path=<abs>` one file's envelope (above). `GET /api/v1/documents/<kind>` is that kind's rows. |
| `POST /api/v1/documents` | `{path}` (or `{id}`): a file opened as a document (above). |
| `PATCH /api/v1/documents` | `{action, path, png?}`: `open` (an existing CAD file on screen, counted for analytics; a model's id, whose record notes the time), `pin`, `unpin`, `remove` (a file's record, the file kept), `delete` (a model's document and record: the engine's `delete`), `thumbnail`; answers the library as it now is. |
| `GET /api/v1/documents/<id>` | The document's envelope (above), or a 404 saying why. |
| `DELETE /api/v1/documents/<id>` | A model's document and record deleted (the engine's `delete`); a file's record forgotten, the file kept. 204. |
| `GET /api/v1/documents/<id>/version` | Its version, waited on (`?after=&wait=&progress=`): the engine's version wait. |
| `GET /api/v1/documents/<id>/thumbnail` | Its library picture (`?v=` its name, which the page sends to keep an older one out of a cache). |
| `POST /api/v1/documents/<id>/exports` | An export of it (below). |
| `GET /api/v1/documents/<kind>/<id>/...` | Its kind's reads: a model's, an `.xbf`'s and a STEP's `structure`, `parts/<key>` (and `faces\|edges\|vertices/<ordinal>`, `groups`, `volume`), `measure`, `kinematics`, `POST pose`, `POST mesh`; a DXF's `drawing` (below); a robot description's `structure` (`cad_server.robot_payload`: its articulation, its visuals at rest) and `parts/<hash>`, a primitive the engine meshed, by its digest; and every file's `source`, its bytes. |
| `GET /api/v1/local/files?path=...` | A CAD file's bytes, by its absolute path (a robot's link mesh, a file a model's file names beside it). |
| `GET /api/v1/local/folder?path=...[&q=...]` | One folder's subfolders and CAD files; with `q`, the CAD files under it whose path holds `q`, bounded. |
| `POST /api/v1/local/reveal` | `{path}`: show a file in the desktop's file manager. |
| `POST /api/v1/local/pick` | Open the machine's own file chooser (`cad_server._internal.picker`) and answer the file picked; the home offers it where the server's `pick` says there is one. |
| `POST /api/v1/local/clipboard` | A PNG onto this machine's clipboard: the web page's picture copy, which asks the browser for no permission. |
| `POST /api/v1/local/activity` | What the page did, for telemetry: `{touched: true}`, a person touched it; `{quickEdit: true}`, a Quick Edit went; `{controls: [{control, count, seconds}]}`, the view controls used (names from `cad_server.analytics.CONTROLS`); `{crash}`, the page crashed (core's `crashOf`: its type and frames, checked again by the server, never a message). Its body may run to 16 KiB. |
| `GET /api/v1/local/update` | `{notice, release, instance, update}`: whether a newer text-to-cad is out (the update button's `notice`, `{latest, version}`, or null), the release the engine runs, and the update a press started (`state`: `idle`, `working`, `restarting` or `failed`; its `target`, its last `progress` frame, its `error`): on the engine a failed switch started again, `failed` with that switch's error, for minutes (`Update.recall`). `GET /api/v1/server` says the same. |
| `POST /api/v1/local/update` | The update button's press (`cad_server._internal.update`): the newest release installed, set up and switched to; answers `202` with what `GET /api/v1/local/update` says, at once. Not on an engine that cannot hand itself over (409). |
| `GET /app` | The CAD app's module (`app.js`), which the shell a host keeps loads (`cad_server.mcp.ui`); 404 with none built. |
| `POST /api/v1/local/prompt-files` | `{name, input, views: [{label, camera, display?, kinematics?, jointValues?, animation?, selection?, width?, height?}], annotation?, acceptInline?}` (at most 16 views; Measure's measurements never travel in one): validate a Quick Edit's packet in memory and answer `200 {ok, inline}` (compact JSON up to 1024 bytes, only with `acceptInline: true`), else `200 {ok, snapshot}` (the absolute path of the `.snapshot.json` written), or a 400. Nothing renders and no PNG is written: `cad snapshot --job` draws the packet later. Carries `x-cadgen-viewer`, as the GET below does. |
| `GET /api/v1/local/prompt-files/<name>` | One of those JSON files, from this process's prompt-files directory only. |

Every request that changes something (POST, PUT, PATCH, DELETE) must send `x-cadgen-viewer: 1`.
The custom header forces a browser preflight for cross-origin requests, and the engine answers that preflight only when it asks for
`authorization` among the card's headers; the request it clears must then carry a day link as
its Bearer credential (above). When
bound to loopback, Host validation also refuses non-local names as a
DNS-rebinding defense. The trust model is documented in
`cad_server.viewer.http_app`; keep these gates intact.

The service serves local bytes and JSON; its host-native actions are the ones above (reveal,
clipboard, pick), and its one write to the person's machine is a browser download:
`POST /api/v1/documents/<id>/exports` `{requestId, epoch, source: {doc, revision}, format}` queues an
export (202) of the displayed document as its code built it -- the document of that id, which the
request's `source` must name (a mesh file by its path)
([the app README](../README.md#export-and-job-status)); `GET /api/v1/exports` is the session's
epoch, `GET /api/v1/exports/<job>` a job's state (`?after=&wait=`), and `GET /api/v1/exports/<job>/file`
the download, whose file goes once the browser has it whole or after ten minutes. CLI exports
remain outside this HTTP interface.

Backend tests live in `tests/python/packages/cad_server/viewer` and are run by
`scripts/test/test-python.sh`. The web app's `npm run test` covers its JavaScript
host only.

## A DXF's `drawing`

A 2D drawing is rendered on the SERVER. `cad_server.drawing_payload` runs ezdxf's
drawing add-on over the `.dxf`'s modelspace and returns what every entity
flattens to — text placed, dimensions exploded, hatches filled or patterned,
block inserts placed — so the client draws primitives and never parses DXF.

`cad snapshot` draws a drawing by OCCT in the engine (`engine/render/drawing.py`),
from the engine's own reading of the file, as this pane draws it: from above, fitted,
hairlines in their pens, on the light or dark paper. This route
(`GET /api/v1/documents/dxf/<id>/drawing`) is the pane's alone.

The drawing is opened by its absolute path (`POST /api/v1/documents`), as every file is: a
relative ref, or anything that is not a CAD file, is 400, and a missing file 404. An unreadable drawing is 400 with the
reason and the repair; the server retries a damaged file through
`ezdxf.recover` before giving up. The answer is `application/json;
charset=utf-8`, uncompressed (the backend has no gzip helper and this route did
not add one).

```jsonc
{
  "schemaVersion": 3,
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

The route reads the file whole on every request and holds each answer in the
viewer's memory by those bytes — the last 8, the one asked for least recently
going first; nothing is written. A second request for unchanged bytes (the file
touched, copied or put back) is answered from memory without entering — or
importing — ezdxf, and other bytes are rendered from the bytes read, so an
answer is always the payload of the bytes it is held by. Every DXF takes this one
path, one a model wrote and a vendor's alike.

Bytes it holds no answer for are rendered OFF the request
(`cad_server/viewer/drawings.py`): the request starts the render on a thread of its
own, or joins the one already running for those bytes, and waits on it at most
2 s. A render that ends within that is the answer; one still running answers
`202 {"state": "drawing", "retryMs": 0}`, and the client asks again after
`retryMs` (the CAD app's tunnel holds 0.25 s and asks for 750 ms, since its calls
share the host's few slots). The client bounds each request by how long the
server stays silent — 10 s to the headers, then 10 s between parts of the body —
never by how long a drawing takes, so a drawing that renders for a minute opens,
and a server that stopped answering still fails. One render per drawing: every
request for the same bytes joins it, and its answer is held when it ends.
Rendering is CPU-bound Python (~0.2 s for 2,000 lines of text, ~1 s for 6,000,
~3 s for 100,000 LINEs on a warm laptop) and still holds the GIL against the
server's other threads while it runs. If drawings that size become routine, the
escalation is a process of its own — as the engine reads a STEP — not a thread
pool here.
