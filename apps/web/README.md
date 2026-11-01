# CAD Viewer

A local-filesystem CAD review app. This directory is the React CLIENT; the
backend is the installation's engine, hosting the `cad_server.viewer` HTTP app.
The built client ships inside the same wheel. `cad viewer [FILE ...]` opens the
engine's one page and exits. The page addresses every document by path, `/<uuid>`: a
model's id, or a file's id once a launcher (or the page itself) registers it, derived from
the file's canonical path. `/` is the home: the library alone, the documents opened or built
before. Python scripts are never documents. There is no hosted deployment.

This app is the browser host of `@text-to-cad/ui/file-viewer`, not the owner of
the shared CAD interface.

**Owns:** URL selection (`/<id>`: `src/client/workbench/fileParam.js`), browser history, document title/appearance, browser
persistence, the file menu's reveal route, and the app menu's links (the update notice is
the server's, read from `/api/v1/server`).
`src/App.tsx` composes an explicit `ViewerHost` and hands it to the shared
`CadViewer` (`@text-to-cad/ui/cad-viewer`), which registers one renderer per file
family and draws the navbar and the explorer. The catalog exposes CAD
artifacts only. Explicit exports write only the requested download to temporary server storage.
Follow the [shared host contract](../../packages/ui/docs/viewer-host.md) when
adding viewer features; browser effects belong in this app's adapters.
The [shared Model tree](../../packages/ui/docs/cad-renderer.md#engine-document-panels)
owns expansion-based picking and isolation.
Web uses the same tree and file-row primitives as the CAD app; its HTTP adapter
does not decide which model nodes are expanded or selectable.

**May depend on:** compiled `@text-to-cad/ui` and `@text-to-cad/core` exports and app
libraries. Never another application's source. Shared packages never import
this app. The Python wheel consumes only the production build.

```text
src/
  App.tsx               the CadViewer's browser host: URL, history, title, appearance, the file menu and the library
  main.tsx              host/client bootstrap and cleanup
  host/                 browser clipboard, prompt delivery, the app menu's links, the update notice, reload under a new server
  persistence/          the tab record in sessionStorage
  client/               appearance control and styling
  shared/               app build/runtime configuration helpers
```

The root npm workspace owns installation and the lockfile. Run `npm ci` and
`npm run build:packages` from the repository root before app commands. Shared
code resolves from package `dist/`; rebuild packages after editing them. App
source still uses Vite HMR. Package styles include their own utility classes
and assets, so the app does not scan another package's source.

## The laws that bind the app

- **One boundary**: the app imports shared packages through public exports.
  The root dependency checker prevents app-to-app and package-to-app imports.
  The backend is not here: its code, its tests and its laws live with the server
  (`cad-server`).
- **Document boundary**: everything renders from the file. A STEP and an `.xbf`
  render from what the engine serves of them — the structure (names,
  colours, materials, the mechanism) and one buffer per part, read through the
  viewer (`POST /api/v1/documents`, then its kind's `/api/v1/documents/<kind>/<id>/...`,
  [docs/backend.md](docs/backend.md)) — and every other
  format from its own bytes or what the server resolved from them. The viewer never
  reads model source and never triggers a source build: a build of a document a
  view shows reaches it as the engine's next version, at once, and only the parts
  the edit changed are fetched. A part and an element are named as the engine
  names them (`f:`/`e:`/`v:` names), never by bytes, ordinals or positions, so a
  copied ref survives a rebuild.
- **Independent motion**: a document's mechanism poses its parts in the page
  (Position); the engine serves the document, never a frame of it.
- **Loud failure**: a missing entry, an unresolvable ref, or a file the engine
  cannot read surfaces as an alert — never a silently wrong scene.

## Launching

Dev serves the client from source with HMR. Build the shared packages from the
repository root first, then invoke npm from a folder of models (outside `apps/web`):

```bash
cd <a folder of models>
VIEWER_PYTHON=<checkout>/.venv/bin/python \
  npm --prefix <checkout>/apps/web run dev -- --host 127.0.0.1
# open http://127.0.0.1:5173/: a file opened there is /<its id>
```

For the spawned backend, `scripts/directoryRoot.mjs` uses `INIT_CWD`, then the
process working directory, accepting either only outside `apps/web`. If neither
qualifies, Vite defaults to the app's parent, `<checkout>/apps`. npm sets
`INIT_CWD` to the directory where you invoked it, so `--prefix` selects the app
without changing that folder. It is only the folder a launch's relative files are read from
(`serverInfo.start`, the most recent launch's): the backend opens any file by its absolute path.

Dev announces itself to the same engine with
`python -m cad_server.viewer --api-only --json` (a launch, from its folder), then
proxies the engine's API, `/api`, with the engine token. Vite owns the client and closing it leaves the engine
running. `VIEWER_PYTHON` names the interpreter with the server installed (default `python3`).
`VIEWER_BACKEND_URL` and `CAD_ENGINE_TOKEN` attach to an existing engine
using its `apiUrl` and `token`. The token is named outside `VIEWER_`, the prefix Vite hands
to the page (dev refuses a `VIEWER_` variable named like a token), and the dev server sends
no CORS headers, so no other origin reads what its token-bearing proxy answers. Build shared packages first; Vite needs no web
production build.

Prod is `cad viewer`, run from anywhere. It serves the client bundled by
`scripts/bundle/bundle.sh` or installed in the wheel. To explicitly select this
checkout's web build, start from the repository root:

```bash
npm run build:web
export CAD_VIEWER_DIST="$PWD/apps/web/dist"
cad viewer --host 127.0.0.1 --json [FILE ...]
```

The launcher ensures this installation's engine and its one page, registers each FILE (an
on-disk CAD file, or a document id the engine holds) by its id, prints its page's URL
(`/<id>`, a line each; the home's, `/`, with none), opens the first in the browser, and exits. `--json` prints the launch
record without opening a browser; `--no-open` prints only the URL. There is no
foreground viewer server and no `--detach` or `viewer stop`. `cad stop` stops
the installation's engine and all its clients; never stop an engine you did not start.

`cad serve DOC` also starts or reuses this engine, prints the document URL and
exits. It has no `--foreground` or standalone server mode.

The engine binds loopback on 3245, or, when another program holds it, the next free
port, which the installation keeps (`cad status` says which and why). `--port N`
pins its HTTP port and `--host ADDRESS` pins its bind address. If the running engine has a different
port or address, the launch fails with that conflict; it never replaces a server
or starts a second engine. A taken port that `--port` names fails, naming its holder. There are no page sessions: every launch
reuses the one page, and its folder replaces the last launch's as the one its relative files are read from.
`--dist DIR` (or `CAD_VIEWER_DIST`) selects a built client.

The JSON record includes `url`, `apiUrl`, `token`, `port`, `pid`, `start` (the folder the home
shows), `documents` (`{id, file, url}` for each FILE) and `action` (`started` or `reused`,
referring to the page). Each URL, and `token`, carries a fresh link, good for a day
(`--api-only`'s `token` is the user's token itself, for the dev proxy). The URL is usable
as soon as it is printed. Its link is exchanged for an HttpOnly, SameSite=Strict session cookie,
one for every port of the host, that lasts 30 days from its last use, and is removed from the
address bar. Programmatic clients send the link or the token as a Bearer header. Every route,
including documents, requires one. The loopback Host check,
cross-site POST guard and raw-file response headers remain. Binding `--host`
off loopback exposes these same authenticated routes; anyone with a link or the cookie has
local-file access. Keep the URL private. Vite remains on its own strict port, 5173.
A refused page load is answered 403 with a static page of a few lines, no script and no asset: a
link past its day says it has expired, any other (no link, a session 30 days unused, or a link or
cookie from before `cad server --rotate-token`) that the page needs its link, and both say to
run `cad viewer` and open the link it prints. A
loaded page whose engine stops under it says the engine is not running, in the person's
language, over the page until a read answers again. One whose engine runs and refuses its token
(after `cad server --rotate-token`) says instead that its link was replaced, and to run `cad
viewer` and open the link it prints; it keeps asking, never reloads for the refusal, and heals
once that link, opened beside it, has left the new cookie.

A page closing never stops the engine, and no timer does: it runs until `cad stop`, or
until a newer installation's engine retires it while nothing uses it.
Code changes in a checkout require
restarting an engine you own, then rerunning the launcher. Vite handles client HMR.

## Behaviours worth knowing before concluding something is broken

- **A file is named by its absolute path, and nothing walks a tree.** The
  catalog is the named file's row, computed when it is asked for; a file under
  a hidden folder opens like any other. The explorer reads one folder at a
  time, and its search skips hidden folders and `__cadgen__`, `__pycache__`,
  `build`, `coverage`, `dist`, `node_modules` and `viewer` (exact case) — except the folders
  on the way to the engine's cache (`~/.cache/texttocad`, each model's
  `documents/<id>/document.xbf`), which it lists.
  [docs/backend.md](docs/backend.md) has the rules.
- **Verify a link by loading the page**, never by curling `/api/v1/local/files` —
  that route serves raw files; an engine document is opened with `POST /api/v1/documents` and
  read under `/api/v1/documents/<kind>/<id>`, so probing it says nothing of the page.
- **Warm work survives navigation.** The app retains one client across navigation, so the
  caches keyed to its resources stay valid across file switches. The engine holds
  every document it served and each part's mesh under one memory budget (a quarter of the
  machine's memory by default, `CAD_ENGINE_MEMORY_MB`), and the last STEP reads by their
  bytes: within it, reopening a document reads and meshes nothing again; past it the least
  recently used leave memory first and are read again when asked.
  Inactive WebGL scenes are released, and a file's view (its camera, Display
  settings and pose) lasts only while it is the file on screen: a refresh brings it
  back, and leaving the file drops it.
- **Vite's transform cache can outlive HMR and hard reloads.** If a source
  edit does not show up, restart the dev server and delete
  `node_modules/.vite`.
- Export routes never open a server-side dialog: a finished file is a browser download.
  Automation tests inject the download port and use isolated documents and servers.

## Export and job status

**Export** sits at the top-right of the navbar of a STEP, XBF, held model (a model's document
the engine holds), GLB, STL or 3MF page: a dropdown of the formats that page's file writes, there at once, as nothing is
inspected first. For a model it captures the displayed revision and writes the document as its code built it: every
part, as authored. The menu chooses a format alone; a posed or partial file is a function
in the model's code. A STEP, XBF or held model offers STEP, STL, 3MF, GLB and XBF (an XBF's
XBF is its own bytes), and DXF where the view draws it flat on z=0; on a GLB, STL or 3MF page Export converts the file shown, at the
bytes on screen, to the other two mesh kinds and nothing else; a file changed since is refused.
Source and outputs stay separate.

Exports work as a browser's downloads do. Choosing a format submits the job at once; nothing
is asked first. When the file is ready the page hands it to the browser as a plain download
(`src/host/downloads.ts`: a same-origin link with `download`), once, in every browser: where
it goes is the browser's own setting (its download bubble and folder, or its Save dialog for a
person who asked for one), and the page never claims it was saved. The link's URL carries no
token: the session cookie authenticates it, as it does every request the page makes.

Each export has one small single-line toast (Sonner, at the view's top right under the navbar):
a spinner while it is queued or running, and while a dropped connection is asked again,
**Preparing part.step…**, dismissed the moment the file is handed to the browser's download
(the toast shows the prepare, never a download; there is no success toast); or the engine's
one-line reason, which stays until dismissed. Exports
run independently; choosing a format again starts another.

The queue accepts up to 16 unfinished jobs per viewer session, executes them in order,
and retains at most 4 GiB of completed downloads. An artifact is deleted as soon as the
browser has fetched it whole (the server saw its GET end; a range or a broken transfer keeps
it), ten minutes after completion if nobody fetched it, when its job is released, or when the engine
stops; an active transfer holds its file until it finishes. Job records last as long as the
engine serving the page, the page session (up to 128 records), with bounded
request-ID tombstones for the session so an expired request cannot regenerate a file.
Private temporary folders left by a crash are reaped after a day by the next export.
There is no durable job registry; a server restart ends these jobs.

Reload picks up the exports still under way from this tab's session storage and reconnects
with the same request IDs; an export leaves it once its file is handed to the browser or it
fails. Each request names the session's epoch, read as its export starts, so a server
restarted since refuses it rather than running it again, and its toast says so. Client transport is `@text-to-cad/core/client`'s `ExportService`, shared UI is
`packages/ui/src/export`, and `src/host/downloads.ts` owns the browser effect.

## Shared interface

This app exports no components. Other hosts use `@text-to-cad/ui/file-viewer` with
registered renderers and explicit services. Viewer content is registered through
`@text-to-cad/ui/renderers/xbf` for `.step`, `.stp` and `.xbf`, for `.dxf` `@text-to-cad/ui/renderers/dxf`, for `.glb`
`@text-to-cad/ui/renderers/glb`, for `.stl` and `.3mf` `@text-to-cad/ui/renderers/mesh`, and
for `.urdf`, `.srdf` and `.sdf` `@text-to-cad/ui/renderers/robot` (`CadViewer` registers all
five with the same client and preferences, as it does for the MCP app); all loading,
selection, panel and tool behavior is shared. Public declarations, styles and worker assets are built in that
package: the root workspace builds UI's ESM, declarations, CSS and worker assets before building
the app, with no source alias or JSX loader. Web supplies its file source (`createCadFileSource`
from `@text-to-cad/ui/catalog`, over its CAD client), URL navigation (`onShow`, the `/<id>` path
and history), browser persistence, the document title and appearance, the viewer's links
(`ViewerHost.links`: its version, its build's GitHub and Discord, `src/host/viewerLinks.js`) and
the tab's colour scheme (`colorScheme`); the navbar, the explorer, the tool strip, the file
sidebar and Preview are the shared package's. Native file operations are host capabilities: the
web offers Copy path and Reveal in the file manager of the machine the server runs on, and has
no filesystem-writing or editing endpoint. The host boundary is
[the shared host contract](../../packages/ui/docs/viewer-host.md); browser persistence is
[docs/storage.md](docs/storage.md). CAD control guidance lives with the UI package.

`vite.config.mjs` names the build, for the version the app menu shows (`__TEXT_TO_CAD_BUILD__`,
from `@text-to-cad/ui/build-id`): none for the release's own build, whose
environment names its version in `TEXT_TO_CAD_RELEASE` (the release workflow's bundle
step), so it shows `v0.10.0`; for any other build, `vite dev` included, the commit of
this checkout, with `-dirty` when it had uncommitted changes: `v0.10.0-dev.b80844940`.

## Testing

```bash
npm run typecheck    # tsc over src/: neither the Vite build nor the tests check types
npm run test         # client + app tooling (node:test, beside the code)
```

CI runs both through `scripts/test/test-js.sh --select web`. The backend's suite
lives with the server and is not collected here; running only `npm run test` leaves
that half unchecked.

The UI's browser specs run in npm's Playwright Chromium: Metal on macOS, SwiftShader
on Linux and Windows. Compare a baseline and a refactor on the same backend.

From the repository root, `scripts/test/test-viewer-browser.sh` exercises the
bundled client's format and camera contracts through the real backend, with fresh
temporary fixtures and a private server/cache; it runs exactly what CI runs
(picking and kinematics run on every PR in the `packages/ui` browser specs).
`--only format|camera` runs one gate, and `--out /tmp/viewer-review` retains
screenshots and bounded failure diagnostics; the runner cleans up its project and
processes on exit.

### Branded loading indicator

`@text-to-cad/ui/loading-icon` exports the decorative `LoadingIcon` independently of
the CAD renderer, so a host can show loading feedback without eagerly importing the
CAD surface. `size` controls its pixel dimensions (default 96), `className` its
placement, and `active={false}` uses the still pose. The host owns status text.
It also stays still for OS/app reduced motion and hidden documents. See
the UI package's asset documentation for asset provenance and regeneration.

## Current viewer behavior

The shared [viewer design system](../../packages/ui/docs/settings-ui.md) is the
authoritative contract for the [toolbar](../../packages/ui/docs/settings-ui.md#tools-and-lifecycle),
[file sidebar and mobile layout](../../packages/ui/docs/settings-ui.md#the-file-sidebar-and-the-tool-stack),
settings controls, selection and
[Preview](../../packages/ui/docs/settings-ui.md#camera-animation-and-preview).
Keep those rules there rather than maintaining a separate web layout
specification.

The web host owns URL/history, the tab's persistence, appearance, version links
and native service adapters. Shared renderers own all model interaction. STEP and
robots open in Select, its selection filter the chevron after its button; the tool in hand's
controls are one row under the strip. An assembly's Features (Links for a robot), Position
and an SDF's metadata are the file sidebar's, a tile each at the top-left, whatever the tool. The
file's name in the navbar opens its name menu: Models and Files (the explorer).
STEP and robot files have tools on a strip at the top centre; GLB, STL and 3MF have none,
a GLB's clips or not.
Every 3D file's strip ends in Projection, Display (its settings, a popover that opens down) and
Preview, with the view cube at the bottom-right and Quick Edit at the top-right. DXF is a
2D canvas with pan, zoom, snapshot and Quick Edit, without a 3D toolbar or file sidebar.

The name menu is a popover under the file's name, two tabs over the explorer's own rows:
**Models**, the library's eight latest models (no file), by last activity, each its glyph, its
name and its age ("2h ago"), the one on screen marked, under "Filter models..."; and **Files**, the
explorer: the file's folder (a model's, the folder the explorer was last in this tab, else the
person's home folder), one folder at a
time, with "Filter files..." to find a file anywhere under it. It opens on Models over a model
and on Files over a file. Below 600px of
FileViewer width (a phone) the chrome is touch-sized and the file sidebar's tiles lead the tool strip. Preview is the shared shell's button after Display on the strip: it takes the whole page,
hiding the navbar, the tool strip and Quick Edit, opens still (Orbit, in its settings, is
off at every entry), draws the model in Render — the one place it is drawn — and draws its
own bar in the navbar's place, over the view's top edge on no surface: the file's name at
its left, Preview settings (Orbit, then Render's settings, a panel sliding in from the right
edge) and Exit preview at its right, fading with the playbar while the pointer rests. Routines play
from the sidebar's Animation section in the tools view, and from Preview's playbar under the model
in Preview (on entry only with Autoplay on); the host passes no Preview props.
The file on screen keeps its view in the tab — its camera, Display settings
(explode and clip included) and pose — so a refresh restores it; leaving the file for
another or for the home drops it, and opening it again frames it anew (see
[storage](docs/storage.md)). A rebuild of the file on screen keeps the camera once the person
has moved it, and fits it again to a changed model while they have not
([the camera rule](../../packages/ui/docs/settings-ui.md#camera-animation-and-preview)).

Authored material information lives in the selection's reference details; editing
it requires changing the source model or annotations. The viewer has no Materials
or Theme editor. These controls live in `@text-to-cad/ui`; see the UI package's
Render and loading playbooks.

A STEP or an `.xbf` loads its structure, then its parts, each at the mesh the engine
made of it, and a new version fetches only the parts it changed (the shared
[loading](../../packages/ui/docs/loading.md) playbook). The
viewport carries opening/update status, centred at its top (a progress icon on
mobile); initial loading may also use the viewport overlay, and an error is a card over the viewport whose Details keep the complete
compiler output, whose Retry reloads only that file and whose Report Issue opens a
new issue titled "Issue: ", labelled `bug`, filled in from the card. A failed update the
model survives can be dismissed, leaving the previous version to inspect.

The page checks its session's `identityToken`. Under Vite it reloads when the
served client changes. A page the engine serves never reloads into another identity
on its port: every engine has a new token, so a later engine refuses the page, and
another identity answering there is a process the page cannot authenticate. That
page stops asking and says its engine is gone. Python code does not trigger a server
restart: the engine owns other pages and sessions. Vite handles client HMR and consumes compiled workspace
exports; React is deduplicated with the shared packages.

Prompt actions prepare clipboard content for an external composer. References
name the file by its absolute path, in the canonical selector grammar. Image writes
begin during the user gesture with a pending PNG Blob. A mixed text/image copy is written as separate clipboard
representations, and its result says some receivers paste only one; unsupported combinations fail without
silently copying a subset. No receipt claims that another app pasted or sent the
content. Bundles accept at most 128 parts and one PNG up to 20 MiB; image support
is advertised only when the browser exposes image clipboard writes. Failed
operations can be retried, while recent successful operation IDs prevent repeated
writes. Clipboard operations, prompt delivery and the reload watcher live
under `src/host`; shared UI receives their explicit ports. The browser file source
exposes no general write operations.

Quick Edit has no enable/disable preference; a stale `features.quickEdit: false`
setting has no effect. The prompt destination is the clipboard, so Quick Edit offers Copy Prompt alone. Its
text goes through the clipboard port's `writeText`, which takes pending text: a
`ClipboardItem` holding the promise, so the write starts inside the gesture, or the
text itself once it arrives where the browser takes no pending item. At the press,
the server prepares a packet through the host's `promptFiles` (`createHttpPromptFiles`,
over `/api/v1/local/prompt-files`), with the shared annotation, the current view and distinct
drawn views (Measure's measurements are the person's: a packet carries none). Up to 1024 bytes of compact UTF-8 JSON goes directly
into the prompt; larger packets are written as `.snapshot.json` and named by absolute path.
No snapshot is written while drawing or typing, and no image is rendered.

### The home

The bare URL is the home: the library every CAD view shares (`@text-to-cad/ui/library`),
and nothing else, laid out after Figma's Recents in a centred column (1128px at most, on 24px
gutters, 44px under the navbar). It starts with one control row of 24px
controls: "Recent" at the left, a 17px heading on the row's line, and at the right the type filter, a dropdown
("All ▾": All, Models, Files) where both kinds are listed, the search, the grid/list
switch and, where the server's computer has a file chooser (`pick` in its info), **Open**,
which opens the desktop's own chooser (`POST /api/v1/local/pick`, `cad_server._internal.picker`) and shows
the file picked. The grid's tiles are transparent with a 1px border, at least 280px wide (three across
the full column): a picture on the muted fill, then, in a compact caption, the kind's glyph (a model's cube, a
file's plain file outline, whatever its kind) beside its name over its last activity with its verb ("Edited now",
"Viewed 5m ago", "Edited 2h ago", "Viewed 3d ago", then the short date: Edited when it changed after it was last
opened, Viewed when it was opened after it last changed). The list is a table: Name, Updated and Created over 40px
rows, each a document's glyph and name and those two ages with no verb. Every model is a tile and a row of
its own, nothing folded, and none is tied to the script it was built from: a model shows its
name, its glyph and its age. The pin and the ⋯ appear on hover (at a tile's picture's corner, at a row's end); a
pinned one keeps its pin. The ⋯ menu holds Open, a file's Copy path and Reveal (a model has
neither), Pin or Unpin, and Delete, which asks first: a model's "Delete bracket?" removes the engine's record and its saved build, its
script and exported files kept, and no other model with it; a file's "Delete bracket.step from the viewer?" removes the
engine's record of the file alone. From a file, Back to home in
the menu the navbar's C logo opens leads back to it. The home has the same navbar, the same C
logo (one 16px mark on every page) and the same menu (without Back to home, and with GitHub, Discord and X as
over a file) at the left and
the update button at the right while a newer text-to-cad is out. The home is a step of
the browser's history, as a file is: the browser's Back and Forward walk between them (the
navbar draws no arrows of its own here). A `/<id>` the server knows no file for, and no model the engine
holds, shows "This model is no longer held" with the engine's words -- the command that builds it
again, `cad run <the program that built it>` -- and Go home, titled for the state the engine
names: "This model is not saved" (`unsaved`) or "This model’s script is gone" (`detached`); a file
that is not there shows "File does not exist".

A file is opened by its path (the name menu, the home) and shown by its id: the page asks the
server for the file's envelope (`GET /api/v1/documents?path=<abs>`), whose row carries the document's `id`,
and moves to `/<id>`. Rows join by that id (`client.entryOf`), so a symlinked or case-variant
spelling of one file is one row. A model (a document with no file of its own) has no file menu;
its Files lists the folder the explorer was last in this tab, else the person's home folder
(`home` in the server's info); a file's its own folder.

The home reads the library over `GET /api/v1/documents`, each row with three times, `updated` (a
file's time on disk, a model's run), `opened` (when a page last opened it) and `created` (when the
engine first made its record: a model's first run, a file's first open; null for a record from before
it was kept), ordered pinned
first, then by the later of the two; it pins, unpins, removes a file's record (`remove`) and
deletes a model's document (`delete`) over `PATCH /api/v1/documents`, and draws each card's picture
from `GET /api/v1/documents/<id>/thumbnail`. A model's script is never read for any of it. The document on
screen says it was opened once the catalog has it (`{action: "open"}`: a file joins the
library, a model's record notes the time), and its picture
once it has settled — the model framed whole from the default direction, whatever the
camera (`{action: "thumbnail"}`). `cad_server.viewer.recents` keeps the library in the
user's state directory, shared with the CAD app.

### Usage stats (telemetry)

The server's usage stats (`cad_server/analytics.py`) are on by default once a `cad` command has said
so, once, in its output; nothing in the Viewer asks. **Telemetry** in the app menu turns
them off or on, and the answer is kept in the user's state directory, so one answer counts for
both apps. The page reads and answers it through the CAD client (`consent`, `/api/v1/settings`' `telemetry`),
and reports a person touching the page (at most every 2 s) to `/api/v1/local/activity`; a
file shown is counted as it joins the library (`PATCH /api/v1/documents`). A Quick Edit copied is counted
through the host's `usage`, and the page's own crashes -- an error nothing caught, or one a view's
boundary caught (`main.tsx`) -- are reported as core's `crashOf` makes them: the error's type and its
script frames, never its message, each once a page. The build gives every chunk a hidden source map and
a debug id its text and that map decide (`vite.config.mjs`, `@text-to-cad/core/chunk-ids`). A map leads
into the shared packages' own source, not their compiled `dist`: their modules load with the maps their
builds wrote (`@text-to-cad/core/source-maps`). The wheel
leaves the maps out and a release uploads them to PostHog, and the page
carries each chunk's id by file name (`__cadChunkIds`), and a frame names its chunk by it. The page
also reports the view controls a person used and how long each tool was up (`controls`, names
from `cad_server.analytics.CONTROLS`, since telemetry schema 7). The server holds all of it as counts in memory
-- a file once a day, by its format, never its name -- and sends them every five minutes.

### File storage and host actions

The web `FileSource` is `createCadFileSource` from `@text-to-cad/ui/catalog` over
the CAD client, the one the CAD app uses: a file's catalog row, one folder's entries
(`GET /api/v1/local/folder`) and the CAD files under a folder (the same, with `q`), with no
writes or native filesystem mutations. Catalog content/revision changes are
distinct from transient metadata progress, so progress updates do not restart a
prepared document. Native path copying and file reveal are the host's file actions
(the shared `createCadFileActions`, in `App.tsx`), which the navbar's ⋯ shows. Path
copying uses the clipboard port. Reveal is the client's guarded `POST /api/v1/local/reveal` with
the file's absolute path; the backend opens the native file manager without a shell. The
menu uses the server's platform (`/api/v1/server`) to label Finder, Explorer, or the Linux
file manager. Path copies form the first menu section. Reference copying belongs to the
renderer's selection action, rather than the file menu.

### Shared interface defaults

The host body uses the shared `text-ui` token (13px at the normal root scale).
Menus, tabs and tree rows follow the same default from
[`@text-to-cad/ui`](../../packages/ui/README.md); settings sheets preserve their
compact 11px labels and values. The shared renderer owns reference
layout, projected-bounds camera fitting and labeled orientation axes, so the CAD app
and the web stay consistent without host-specific copies of those controls.

### Navigation

The Viewer has the one navbar every app shares (see
[the host contract](../../packages/ui/docs/viewer-host.md#host-chrome-slots)): at the
left the logo (the C mark, on the home and over a file alike), which opens the app menu, then the open file's name (no glyph),
which opens the name menu (Models and Files), with its ⋯; at the right the blue update button, while a newer text-to-cad
is out, and Export over a file that writes formats. The app menu holds Back to home (the home), the
person's settings (Language — Automatic or a named language —, Telemetry, Theme), Send feedback (a new issue titled "Feedback: "),
GitHub, Discord and, in gray, the version (a link to its release notes) and "Made by @…"
(X), as in the CAD app, over a file and on the home alike.
Projection, Display and Preview are the view's, at the tool strip's end, never the navbar's;
in Preview the navbar gives way to Preview's own bar. This host
supplies the links (`src/host/viewerLinks.js`): its version (with its build's id,
`v0.10.0-dev.b80844940`, for any build but the release's own), the GitHub (where new
issues open) and Discord its build names (`VIEWER_GITHUB_URL`, `VIEWER_DISCORD_URL`);
links open in a new tab. A newer text-to-cad is the blue update button's, at the navbar's right as in the CAD app: the server's
hourly version check, read from `/api/v1/server` with the server's description as the page
starts (`main.tsx`) and again whenever the person comes back to it. A press updates
(`POST /api/v1/local/update`): the engine installs the release, updates each agent app and restarts on it,
on the same port with the same token; the button fills while it works and spins while the engine
restarts, the page reconnects every quarter second meanwhile (`useEngineReconnect`), and it reloads
once the engine answers with the new release and nothing on the page is unsaved. Should the switch fail,
the release before's engine comes back and the page reloads into it all the same: the tab notes that its
page followed the update (`src/host/followedUpdate.js`), and the page loaded says the update failed, in
its one line, with the button offered again.
A Viewer the CAD app's server opens is told of a release only where its install channel allows
it (a store's copy, which its store updates, hears nothing); one a skill opens names no channel
— a skills-only install — and is told. The browser title is the open file's or model's name alone ("bracket.step", "juno"), and "text-to-cad" on the home.
Appearance (System, Light, Dark) is the app menu's Theme row, the tab's choice (`colorScheme`,
over a file and on the home); the page has no light/dark button of its own. The original animated mark remains the shared LoadingIcon
for loading states. The C and CAD marks are the UI package's; the favicons are this
app's, exported alongside the docs brand assets. See
[the brand recipe](../../scripts/brand/README.md).

The web camera action copies only the viewport PNG through guarded
`POST /api/v1/local/clipboard`, avoiding browser clipboard permission prompts. The local
backend writes the server machine's native clipboard on macOS or Linux (wl-copy/xclip);
this is not the remote phone's clipboard when accessing a shared server. Failures
use the viewer's error presentation; successful actions are silent. A host with a
composer has no camera action: its note to the agent is Quick Edit.

## Live models

A model's page is `/<id>`, its document's id, which `python SCRIPT.py` prints (`view:`). The
page reads the document the engine holds, by id (`GET /api/v1/documents/<id>`); it never builds or
imports a script, and no folder lists one. A model has no file of its own: no file menu; its
name menu opens on Models, and its Files lists the folder the explorer was last in this tab
(the tab's settings), else the person's home folder (the server's `home`): never the folder
of the script that built it. It is in the
library by its id (the engine's record), and its picture is taken by
its id as a file's is: on screen once it settles, once per build, and on the home only while
the engine holds it. Once its worker retires or
the engine restarts, its page shows it from the engine's cache, as last built; only once the cache
holds no file of it (deleted by hand, or never saved: the engine's state `unsaved`) does its page
say it is not saved and name the command that builds it again. The page shows the engine's last
build and says nothing of the script it came from: an edit not yet built is no state of the page's;
what it shows is the engine's own run, building or failed. Rebuilding the model updates the same view through the document version stream.
