# Backend

The browser host talks to `cadgen.viewer`, the HTTP application hosted by the engine in the
`cadgen` Python distribution. Its source lives in
`packages/cadgen/src/cadgen/viewer/`; this app owns the React host and its build.
The wheel includes that build at `cadgen/_runtime/viewer`, beside the CAD app's one-file
page (`cadgen/_runtime/mcp`); cadgen's snapshots are OCCT's and need no browser. Skills
invoke the installed distribution.

The HTTP layer uses Python's standard library and the distribution's Python floor.
It never imports the CAD kernel at module scope. Viewing renders existing files;
model source changes never trigger a rebuild. A STEP and an `.xbf` are documents
the cadgen engine serves (`cadgen.engine`, its daemon): the viewer asks the
engine to serve one; the page reads its routes directly, and the engine
reads, meshes and measures it in processes of its own.

## Launching

The engine serves every CAD file by absolute path on port 3245, or the port this
installation rolled to when another program held it (`cadgen status` says which and why),
or the one `--port N` or `CADGEN_ENGINE_PORT` names. Run the installed CLI from anywhere:

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

The launcher connects to this installation's engine, starting it if needed, and
exits after printing or opening its page's URL: `/<id>` for each FILE it names (an on-disk CAD
file it registers by the id of its canonical path, or a document id the engine holds), else the
home, `/`. `--json` prints the launch record without opening a browser. An explicit host or port
must match a running engine. There is one page per engine and no page session: each launch's
folder becomes the folder the home shows, replacing the last. Always use the printed URL,
including its token query; the browser exchanges the token for a same-site HTTP-only cookie.

`cadgen stop` stops the installation's whole engine, including its workers and
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
`python -m cadgen.viewer --api-only --json` (a launch) and proxies `/__cad` to that
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
request's `?file=` — and every path in a request body — names a file by its absolute path (`/models/a.step`; on Windows `C:/models/a.step`
or `C:\models\a.step`), anywhere on the machine; a relative one is a 400
(`cadgen.viewer.backend`). Nothing is refused for where it is: no root, no
containment, and no rule about hidden folders on the way to a named file. A
UNC path (`\\host\share\a.step`) is refused, because any web page can make the
browser send a GET, and a GET must never send the machine to the network.

A view shows one file and browses from that file's folder, one folder at a
time, so nothing walks a tree to show it. `GET /__cad/catalog?file=<abs>` is
that file's row (`scanner.catalog_entry`) — `file` is its absolute path with
`/` separators, `url` where its bytes are served, `id` its document's id (the id of its
canonical path, so a symlink and its target, or two case spellings, are one row) — or no row
for a file that is not a CAD file, is gone, or has a hidden name; with no `file`, the catalog is
empty. A row asked for registers the file by its id. `GET /__cad/catalog?id=<uuid>` is the row
of the document of that id: a file registered (by a launch or a row), or in Recents; else a model
the engine holds (`file` is its id, `name` its function, `sourcePath` null: it has no file to
browse); else no row and `missing`, the engine's words for why, naming the command that builds
it again. A script is never a row. A row is computed from the file when it is asked for, so it is never
stale. It also carries `revision`, a digest of its entries that moves whenever
anything a client would see in them does: a host that cannot afford to read the
catalog on a timer (the CAD app relays every request through its host's few
shared slots) compares the revision it is told with the client's
`catalogRevision`, and reads the catalog again only when they differ.

Every format's row is its file's: `kind` (its extension), `url`, `hash` and
`bytes`, and an SRDF's paired URDF. A STEP's and an `.xbf`'s say no more than that:
they are drawn from what the cadgen engine serves of them (below), and their rows
are what a view watches for a change of the file. A row's digest is the file's
sha256, computed once per version of the file (its mtime and size). Reading a
file to hash it never holds up its deletion: the catalog opens models with delete
sharing on Windows, and a model that vanishes mid-read gets an empty hash on that
request and has no row on the next.

The explorer's two reads are `GET /__cad/folder?path=<abs>` (one folder's
subfolders and CAD files, natural order) and `GET /__cad/search?path=<abs>&q=`
(the CAD files under a folder whose path below it holds `q`, bounded by matches,
depth and time, and saying when it stopped early; `cadgen.viewer.folders`). A
relative path is a 400, a path that is not a folder a 404, one that cannot be
read a 403.

`/__cad/asset` sends only CAD files, and never a file whose own name is hidden:
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
(`cadgen.viewer.engine_app.EngineApp.preflight`).

## Engine documents: a STEP and an `.xbf`

A STEP (`.step`, `.stp`) and an `.xbf` open in the engine document renderer
(`@text-to-cad/ui`'s `renderers/xbf`), drawn from what the cadgen engine serves
of them (`cadgen.viewer.documents`). `GET /__cad/xbf?file=<abs or id>` acquires the
file, or the document of that id as the engine holds it (never built), in the already-running
engine and answers `{doc, url}`, where `url` is
`/__cad/api/doc/<doc>` on this same origin. The engine reads a file once and
holds it. XBF and STEP reads run in child processes; their kernel objects never
enter the HTTP process. A request waits at most two seconds before returning
`202 {"state": "reading", "retryMs": 0}`. `&held=1` answers `{held}` without
starting a read; the home pictures a STEP only when it is held.

`GET /__cad/api/...` dispatches directly to the engine's document routes:
structure, one buffer per part, element facts, groups, volume, look, environment
image and version wait. There is no network relay or separate viewer port.
The web page uses bounded version waits; the MCP page asks with `wait=0` so a
version check occupies no host call slot while waiting for an edit. The same
router handles reads tunneled through `cad_http`, in process. Document buffers
and routes retain the raw-file response headers and engine authentication.
The wire format is the engine README's **Wire format** section.

The browser host constructs a `CadClient` from `@text-to-cad/core/client` and
injects it into the viewer renderers. Catalog subscriptions share the client's
two-second poll and stop when its last subscriber leaves. The client's
`engineDocument(file)` answers the document's URL on the client's origin and the
fetch every read of it is made with (the CAD app's goes over its tunnel).

## HTTP routes

| Route | Purpose |
|---|---|
| `GET /__cad/server` | Server identity: `app` (`cad-viewer`), `identityToken`, `platform` (which file manager Reveal opens), `user`, `home` (the person's home folder: where a model's Files starts with nowhere else to start), `start` (the folder of the most recent launch, which its relative files are read from), `pick` (whether the home offers Open: the machine has a file chooser), `port`, `pid`. |
| `GET /__cad/catalog?file=...` | One file's catalog row, with its document `id`, and its `revision`. |
| `GET /__cad/catalog?id=...` | The row of the document of that id, or none and `missing`, with `missingState` (`unsaved`, `detached`) for the page's title. |
| `GET /__cad/folder?path=...` | One folder's subfolders and CAD files. |
| `GET /__cad/search?path=...&q=...` | The CAD files under a folder whose path holds `q`, bounded. |
| `GET /__cad/asset?file=...` | A CAD file's bytes. |
| `GET /__cad/xbf?file=...` | A STEP, an `.xbf` or a document id, served by the cadgen engine: `{doc, url}`, `202 {state: "reading", retryMs}` while the engine reads it, or the engine's refusal (400). `&held=1`: `{held}`, without starting a read. |
| `GET /__cad/api/...` | Direct engine routes: document structure, part buffers, element facts, groups, volume, look, image and version wait. |
| `GET /__cad/drawing?file=...` | A `.dxf` flattened to 2D render primitives; the DXF pane's only source. |
| `GET /__cad/robot?file=...&mesh=...` | A robot description's payload (`cadgen.robot_payload`: its articulation, its visuals at rest), and with `mesh=<hash>` a primitive cadgen meshed, by its digest. |
| `GET /__cad/recents` | The model library every CAD view shares: pinned first, then by last activity; each row with `opened` (when a page last opened it) and `updated` (a file's time on disk, a model's run: a script is never read for it). |
| `POST /__cad/recents` | `{action, path, png?}`: `open` (an existing CAD file on screen, counted for analytics; a model's id, whose record notes the time), `pin`, `unpin`, `remove` (a file's record, the file kept), `delete` (a model's document and record: the engine's `delete`), `thumbnail`; answers the library as it now is. |
| `GET /__cad/thumbnail?name=...` | A library picture, by its content name. |
| `POST /__cad/reveal` | `{path}`: show a file in the desktop's file manager. |
| `POST /__cad/pick` | Open the machine's own file chooser (`cadgen._internal.picker`) and answer the file picked; the home offers it where the server's `pick` says there is one. |
| `POST /__cad/clipboard` | A PNG onto this machine's clipboard: the web page's picture copy, which asks the browser for no permission. |
| `GET`/`POST /__cad/analytics` | Whether the person's usage stats are sent, and why; `{share}` is their answer (the app menu's toggle). Nothing asks. |
| `POST /__cad/analytics/activity` | What the page did, for telemetry: `{touched: true}`, a person touched it; `{quickEdit: true}`, a Quick Edit went; `{controls: [{control, count, seconds}]}`, the view controls used (names from `cadgen.analytics.CONTROLS`); `{crash}`, the page crashed (core's `crashOf`: its type and frames, checked again by the server, never a message). Its body may run to 16 KiB. |
| `GET`/`POST /__cad/language` | The person's language for the CAD views (`cadgen/language.py`): `{locale, inferred, choice}`; `{choice}` sets it (null is Automatic). |
| `GET /__cad/version` | Whether a newer text-to-cad is out: the update button's `notice`, or null. |
| `POST /__cad/prompt-files` | `{name, input, views: [{label, camera, display?, kinematics?, jointValues?, animation?, selection?, width?, height?}], annotation?, acceptInline?}` (at most 16 views; Measure's measurements never travel in one): validate a Quick Edit's packet in memory and answer `200 {ok, inline}` (compact JSON up to 1024 bytes, only with `acceptInline: true`), else `200 {ok, snapshot}` (the absolute path of the `.snapshot.json` written), or a 400. Nothing renders and no PNG is written: `cadgen snapshot --job` draws the packet later. Carries `x-cadgen-viewer`, as the GET below does. |
| `GET /__cad/prompt-files/<name>` | One of those JSON files, from this process's prompt-files directory only. |

Every POST must send `x-cadgen-viewer: 1`. The custom header forces a browser
preflight for cross-origin POSTs, and the engine answers that preflight only when it asks for
`authorization` among the card's headers; the request it clears must then carry a day link as
its Bearer credential (above). When
bound to loopback, Host validation also refuses non-local names as a
DNS-rebinding defense. The trust model is documented in
`cadgen.viewer.http_app`; keep these gates intact.

The service serves local bytes and JSON; its host-native actions are the ones above (reveal,
clipboard, pick), and its one write to the person's machine is a browser download:
`POST /__cad/exports` `{requestId, epoch, source: {doc, revision}, format}` queues an export
(202) of the displayed document as its code built it
([the app README](../README.md#export-and-job-status)); `GET /__cad/exports` is the session's
epoch, `GET /__cad/exports/<id>` a job's state (`?after=&wait=`), and `GET /__cad/exports/<id>/file`
the download, whose file goes once the browser has it whole or after ten minutes. CLI exports
remain outside this HTTP interface.

Backend tests live in `tests/python/packages/cadgen/viewer` and are run by
`scripts/test/test-python.sh`. The web app's `npm run test` covers its JavaScript
host only.

## `GET /__cad/drawing`

A 2D drawing is rendered on the SERVER. `cadgen.drawing_payload` runs ezdxf's
drawing add-on over the `.dxf`'s modelspace and returns what every entity
flattens to — text placed, dimensions exploded, hatches filled or patterned,
block inserts placed — so the client draws primitives and never parses DXF.

`cadgen snapshot` draws a drawing by OCCT in the engine (`engine/render/drawing.py`),
from the engine's own reading of the file, as this pane draws it: from above, fitted,
hairlines in their pens, on the light or dark paper. This route is the pane's alone.

`?file=` names the drawing by its absolute path, as every route does: a
relative ref, or anything that is not a `.dxf`, is 400, and a missing file 404. An unreadable drawing is 400 with the
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
path, one a cadgen model wrote and a vendor's alike.

Bytes it holds no answer for are rendered OFF the request
(`cadgen/viewer/drawings.py`): the request starts the render on a thread of its
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
