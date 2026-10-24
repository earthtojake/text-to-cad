# CAD Viewer

A local-filesystem CAD review app. This directory is the React CLIENT; the
backend is the installation's engine, hosting the `cadgen.viewer` HTTP app.
The built client ships inside the same wheel. `cadgen viewer [FILE ...]` opens the
engine's one page and exits. The page addresses every document by path, `/<uuid>`: a
model's id, or a file's id once a launcher (or the page itself) registers it, derived from
the file's canonical path. `/` is the home: Recents, Open, and the folder of the most recent
launch. Python scripts are never documents. There is no hosted deployment.

This app is the browser host of `@text-to-cad/ui/file-viewer`, not the owner of
the shared CAD interface.

**Owns:** URL selection (`/<id>`: `src/client/workbench/fileParam.js`), browser history, document title/appearance, browser
persistence, the file menu's reveal route, and this app's release check.
`src/App.tsx` composes an explicit `ViewerHost` and hands it to the shared
`CadViewer` (`@text-to-cad/ui/cad-viewer`), which registers one renderer per file
family and draws the navbar and the explorer. The catalog exposes CAD
artifacts only. Explicit exports write only the requested download to temporary server storage.
Follow the [shared host contract](../../packages/ui/docs/viewer-host.md) when
adding viewer features; browser effects belong in this app's adapters.
The [shared Model tree](../../packages/ui/docs/cad-renderer.md#engine-document-panels)
owns expansion-based picking and isolation.
Web uses the same tree and file-row primitives as desktop; its HTTP adapter
does not decide which model nodes are expanded or selectable.

**May depend on:** compiled `@text-to-cad/ui` and `@text-to-cad/core` exports and app
libraries. Never another application's source. Shared packages never import
this app. The Python wheel consumes only the production build.

```text
src/
  App.tsx               the CadViewer's browser host: URL, history, title, appearance, the file menu and the library
  main.tsx              host/client bootstrap and cleanup
  host/                 browser clipboard, prompt delivery, the app menu's links and release check, reload under a new server
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
  The backend is not here: its code, its tests and its laws live with cadgen.
- **Document boundary**: everything renders from the file. A STEP and an `.xbf`
  render from what the cadgen engine serves of them — the structure (names,
  colours, materials, the mechanism) and one buffer per part, read through the
  viewer (`/__cad/xbf`, [docs/backend.md](docs/backend.md)) — and every other
  format from its own bytes or what cadgen resolved from them. The viewer never
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
repository root first, then invoke npm from the folder the home should show (outside
`apps/web`):

```bash
cd <a folder of models>
VIEWER_PYTHON=<checkout>/.venv/bin/python \
  npm --prefix <checkout>/apps/web run dev -- --host 127.0.0.1
# open http://127.0.0.1:5173/: the home shows that folder; a file opened there is /<its id>
```

For the spawned backend, `scripts/directoryRoot.mjs` uses `INIT_CWD`, then the
process working directory, accepting either only outside `apps/web`. If neither
qualifies, Vite defaults to the app's parent, `<checkout>/apps`. npm sets
`INIT_CWD` to the directory where you invoked it, so `--prefix` selects the app
without changing that folder. It is only the folder the home shows
(`serverInfo.start`, the most recent launch's): the backend opens any file by its absolute path.

Dev announces itself to the same engine with
`python -m cadgen.viewer --api-only --json` (a launch: its folder becomes the home's), then
proxies `/__cad` with the engine token. Vite owns the client and closing it leaves the engine
running. `VIEWER_PYTHON` names the interpreter with cadgen installed (default `python3`).
`VIEWER_BACKEND_URL` and `CAD_ENGINE_TOKEN` attach to an existing engine
using its `apiUrl` and `token`. The token is named outside `VIEWER_`, the prefix Vite hands
to the page (dev refuses a `VIEWER_` variable named like a token), and the dev server sends
no CORS headers, so no other origin reads what its token-bearing proxy answers. Build shared packages first; Vite needs no web
production build.

Prod is `cadgen viewer`, run from anywhere. It serves the client bundled by
`scripts/bundle/bundle.sh` or installed in the wheel. To explicitly select this
checkout's web build, start from the repository root:

```bash
npm run build:web
export CADGEN_VIEWER_DIST="$PWD/apps/web/dist"
cadgen viewer --host 127.0.0.1 --json [FILE ...]
```

The launcher ensures this installation's engine and its one page, registers each FILE (an
on-disk CAD file, or a document id the engine holds) by its id, prints its page's URL
(`/<id>`, a line each; the home's, `/`, with none), opens the first in the browser, and exits. `--json` prints the launch
record without opening a browser; `--no-open` prints only the URL. There is no
foreground viewer server and no `--detach` or `viewer stop`. `cadgen stop` stops
the installation's engine and all its clients; never stop an engine you did not start.

`cadgen serve DOC` also starts or reuses this engine, prints the document URL and
exits. It has no `--foreground` or standalone server mode.

The engine binds loopback on an OS-assigned port. `--port N` pins its HTTP port
and `--host ADDRESS` pins its bind address. If the running engine has a different
port or address, the launch fails with that conflict; it never replaces a server
or starts a second engine. A taken port fails. There are no page sessions: every launch
reuses the one page, and its folder replaces the last launch's as the one the home shows.
An old page session's link (`/s/...`) and a document named by query (`/?doc=`, `/?file=`)
are answered with the home. `--dist DIR` (or `CADGEN_VIEWER_DIST`) selects a built client.

The JSON record includes `url`, `apiUrl`, `token`, `port`, `pid`, `start` (the folder the home
shows), `documents` (`{id, file, url}` for each FILE) and `action` (`started` or `reused`,
referring to the page). The URL is usable
as soon as it is printed. Its token is exchanged for an HttpOnly, SameSite cookie
and removed from the address bar. Programmatic clients send the token as a Bearer
header. Every route, including documents, requires it. The loopback Host check,
cross-site POST guard and raw-file response headers remain. Binding `--host`
off loopback exposes these same authenticated routes; anyone with the token has
local-file access. Keep the URL private. Vite remains on its own strict port, 5173.
A refused navigation (a tab reloaded after its engine stopped, or under a newer one) is answered
403 with a static page of a few lines, no script and no asset, saying the link no longer works
and that opening the viewer again (from the agent, or `cadgen viewer`) gives a fresh one. A
loaded page whose engine stops under it says the engine is not running, in the person's
language, over the page until a read answers again.

A page closing never stops the engine. Active requests and document version waits
keep it alive; it exits after its idle hour. Code changes in a checkout require
restarting an engine you own, then rerunning the launcher. Vite handles client HMR.

## Behaviours worth knowing before concluding something is broken

- **A file is named by its absolute path, and nothing walks a tree.** The
  catalog is the named file's row, computed when it is asked for; a file under
  a hidden folder opens like any other. The explorer reads one folder at a
  time, and its search skips hidden folders and `__cadgen__`, `__pycache__`,
  `build`, `coverage`, `dist`, `node_modules` and `viewer` (exact case).
  [docs/backend.md](docs/backend.md) has the rules.
- **Verify a link by loading the page**, never by curling `/__cad/asset` —
  that route serves raw files; generated entries render through a
  different route, so probing it 404s whether or not anything is wrong.
- **Warm work survives navigation.** The app retains one client across navigation, so the
  caches keyed to its resources stay valid across file switches. The cadgen engine holds
  every document it served, a STEP's read held by its bytes, so reopening one reads and
  meshes nothing again while its engine server lives.
  Inactive WebGL scenes are released, and a file's view (its camera, Display
  settings and pose) lasts only while it is the file on screen: a refresh brings it
  back, and leaving the file drops it.
- **Vite's transform cache can outlive HMR and hard reloads.** If a source
  edit does not show up, restart the dev server and delete
  `node_modules/.vite`.
- Export routes never open a server-side dialog: a finished file is a browser download.
  Automation tests inject the download port and use isolated documents and servers.

## Export and job status

**Export** sits at the top-right of the navbar of a STEP, XBF, held model, GLB, STL or 3MF
page. For a model it captures the displayed revision and writes the document as its code built it: every
part, as authored. The menu chooses a format alone; a posed or partial file is a function
in the model's code. Only supported formats
are offered: STEP, GLB, STL, 3MF, planar DXF and eligible XBF; an existing XBF
has **Download original XBF**. On a GLB, STL or 3MF page Export converts the file shown, at the
bytes on screen, to the other two mesh kinds and nothing else; a file changed since is refused.
Source and outputs stay separate.

**Export and download** submits the job; nothing is asked first. When the file is
ready the page hands it to the browser as a plain download (`src/host/downloads.ts`: a
same-origin link with `download`), once, in every browser: where it goes is the browser's
own setting (its folder, or its Save dialog for a person who asked for one). The link's
URL carries no token: the session cookie authenticates it, as it does every request the
page makes.

Multiple exports queue independently, each with a persistent toast at the top-right
under the navbar (on a phone, at the view's bottom) and its own **Cancel**. A queued cancellation is immediate; an
in-flight kernel operation finishes before its output is discarded. **Download again**
fetches the same artifact while it is kept; once it is gone the button is **Export again**,
which runs the same export anew. Closing a toast only hides it, and **Export → Show exports**
restores it.

The queue accepts up to 16 unfinished jobs per viewer session, executes them in order,
and retains at most 4 GiB of completed downloads. An artifact is deleted as soon as the
browser has fetched it whole (the server saw its GET end; a range or a broken transfer keeps
it), ten minutes after completion if nobody fetched it, on **Remove**, or when the engine
stops; an active transfer holds its file until it finishes. Job records last as long as the
engine serving the page, the page session (up to 128 records), with bounded
request-ID tombstones for the session so an expired request cannot regenerate a file.
Private temporary folders left by a crash are reaped after a day by the next export.
There is no durable job registry; a server restart ends these jobs.

Reload restores the page's export records from this tab's session storage and reconnects
with the same request IDs; a file already handed to the browser is not downloaded again
by itself. Client transport is `@text-to-cad/core/client`'s `ExportService`, shared UI is
`packages/ui/src/export`, and `src/host/downloads.ts` owns the browser effect.

## Shared interface

This app exports no components. Other hosts use `@text-to-cad/ui/file-viewer` with
registered renderers and explicit services. Viewer content is registered through
`@text-to-cad/ui/renderers/xbf` for `.step`, `.stp` and `.xbf`, for `.dxf` `@text-to-cad/ui/renderers/dxf`, for `.glb`
`@text-to-cad/ui/renderers/glb`, for `.stl` and `.3mf` `@text-to-cad/ui/renderers/mesh`, and
for `.urdf`, `.srdf` and `.sdf` `@text-to-cad/ui/renderers/robot` (`CadViewer` registers all
five with the same client and preferences, as it does for the MCP app); all loading,
selection, panel and tool behavior is shared. Public declarations, styles and worker assets are built in that
package. See `docs/shell.md` for the host boundary and `docs/storage.md` for
browser persistence. CAD control guidance lives with the UI package.

`vite.config.mjs` names the build, for the version the app menu shows (`__TEXT_TO_CAD_BUILD__`,
from `@text-to-cad/ui/build-id`): none for the release's own build, whose
environment names its version in `TEXT_TO_CAD_RELEASE` (the release workflow's bundle
step), so it shows `v0.7.15`; for any other build, `vite dev` included, the commit of
this checkout, with `-dirty` when it had uncommitted changes: `v0.7.15-dev.b80844940`.

It also names the build, for the version the app menu shows (`__TEXT_TO_CAD_BUILD__`,
from `@text-to-cad/ui/build-id`): none for the release's own build, whose
environment names its version in `TEXT_TO_CAD_RELEASE` (the release workflow's bundle
step), so it shows `v0.7.15`; for any other build, `vite dev` included, the commit of
this checkout, with `-dirty` when it had uncommitted changes: `v0.7.15-dev.b80844940`.

## Testing

```bash
npm run test    # client + app tooling (node:test, beside the code)
```

The backend's suite lives with cadgen and is not collected here; running only
`npm run test` leaves that half unchecked.

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
file's name in the navbar opens the explorer.
STEP and robot files have tools on a strip at the top centre; GLB, STL and 3MF have none,
a GLB's clips or not.
Every 3D file's strip ends in Display (its settings, a popover that opens down) and
Preview, with the view cube at the bottom-right and Quick Edit at the top-right. DXF is a
2D canvas with pan, zoom, snapshot and Quick Edit, without a 3D toolbar or file sidebar.

The explorer is a popover under the file's name: the file's folder, one folder at a
time, with "Filter files..." to find a file anywhere under it. Below 600px of
FileViewer width (a phone) the chrome is touch-sized and the file sidebar's tiles lead the tool strip. Preview is the shared shell's button after Display on the strip: it takes the whole page,
hiding the navbar, the tool strip and Quick Edit, opens still (Orbit, in its settings, is
off at every entry), draws the model in Render — the one place it is drawn — and keeps its
own controls in the view's top-right corner: Preview settings (Orbit, then Render's settings)
and Exit preview, with the file sidebar's Position and Animation at its top-left. Routines play
from the sidebar's Animation section, in either view (in Preview, on entry only with
Autoplay on); the host passes no Preview props.
The file on screen keeps its view in the tab — its camera, Display settings
(explode and clip included) and pose — so a refresh restores it; leaving the file for
another or for the home drops it, and opening it again frames it anew (see
[storage](docs/storage.md)).

Authored material information lives in the selection's reference details; editing
it requires changing the source model or annotations. The viewer has no Materials
or Theme editor. These controls live in `@text-to-cad/ui`; see the UI package's
Render and loading playbooks.

A STEP or an `.xbf` loads its structure, then its parts, each at the mesh the cadgen engine
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
over `/__cad/prompt-files`), with shared annotation and measurements, the current
view and distinct drawn views. Up to 1024 bytes of compact UTF-8 JSON goes directly
into the prompt; larger packets are written as `.snapshot.json` and named by absolute path.
No snapshot is written while drawing or typing, and no image is rendered.

### The home

The bare URL is the home: the library of models every CAD view shares
(`@text-to-cad/ui/library`), and Open, the desktop's file chooser (`POST /__cad/pick`),
where the server's computer has one (`serverInfo.pick`). From a file, Back to files in
the menu the navbar's C logo opens leads back to it. The home has the same navbar, its C
menu (without Back to files) at the left and the update button at the right while a newer
text-to-cad is out; under its wordmark are GitHub, Discord and X. The home is a step of
the browser's history, as a file is: the browser's Back and Forward walk between them (the
navbar draws no arrows of its own here). Under Recents the home lists the folder of the most
recent launch (`serverInfo.start`, read again each time the home is shown): its subfolders and CAD
files, a file opening by its id. A `/<id>` the server knows no file for, and no model the engine
holds, shows "This model is no longer held" with the engine's words -- the command that builds it
again, `python <the program that built it>` -- and Go home; a file that is not there shows "File
does not exist".

A file is opened by its path (Select File, the home) and shown by its id: the page asks the
catalog for the file (`GET /__cad/catalog?file=<abs>`), whose row carries the document's `id`,
and moves to `/<id>`. Rows join by that id (`client.entryOf`), so a symlinked or case-variant
spelling of one file is one row. A model (a document with no file of its own) has no Select File
and no file menu; a file's Select File lists that file's folder.

The home reads the library over `GET /__cad/recents`, pins, unpins and removes over
`POST /__cad/recents`, and draws each card's picture from `GET /__cad/thumbnail`. The
file on screen joins it once the catalog has it (`{action: "open"}`), and its picture
once it has settled — the model framed whole from the default direction, whatever the
camera (`{action: "thumbnail"}`). `cadgen.viewer.recents` keeps the library in the
user's state directory, shared with the CAD app.

### Usage stats (telemetry)

cadgen's usage stats (`cadgen/analytics.py`) are on by default once a `cadgen` command has said
so, once, in its output; nothing in the Viewer asks. **Share anonymous usage data** in the app menu turns
them off or on, and the answer is kept in the user's state directory, so one answer counts for
both apps. The page reads and answers it through the CAD client (`consent`, `/__cad/analytics`),
and reports a person touching the page (at most every 2 s) to `/__cad/analytics/activity`; a
file shown is counted as it joins the library (`/__cad/recents`). A Quick Edit copied is counted
through the host's `usage`, and the page's own crashes -- an error nothing caught, or one a view's
boundary caught (`main.tsx`) -- are reported as core's `crashOf` makes them: the error's type and its
script frames, never its message, each once a page. The build gives every chunk a hidden source map and
a debug id its text and that map decide (`vite.config.mjs`, `@text-to-cad/core/chunk-ids`). A map leads
into the shared packages' own source, not their compiled `dist`: their modules load with the maps their
builds wrote (`@text-to-cad/core/source-maps`). The wheel
leaves the maps out and a release uploads them to PostHog, and the page
carries each chunk's id by file name (`__cadChunkIds`), and a frame names its chunk by it. The server holds all of it as counts in memory
-- a file once a day, by its format, never its name -- and sends them every few minutes.

### File storage and host actions

The web `FileSource` is `createCadFileSource` from `@text-to-cad/ui/catalog` over
the CAD client, the one the CAD app uses: a file's catalog row, one folder's entries
(`GET /__cad/folder`) and the CAD files under a folder (`GET /__cad/search`), with no
writes or native filesystem mutations. Catalog content/revision changes are
distinct from transient metadata progress, so progress updates do not restart a
prepared document. Native path copying and file reveal are the host's file actions
(the shared `createCadFileActions`, in `App.tsx`), which the navbar's ⋯ shows. Path
copying uses the clipboard port. Reveal is the client's guarded `POST /__cad/reveal` with
the file's absolute path; the backend opens the native file manager without a shell. The
menu uses the server's platform (`/__cad/server`) to label Finder, Explorer, or the Linux
file manager. Path copies form the first menu section. Reference copying belongs to the
renderer's selection action, rather than the file menu.

### Shared interface defaults

The host body uses the shared `text-ui` token (13px at the normal root scale).
Menus, tabs and tree rows follow the same default from
[`@text-to-cad/ui`](../../packages/ui/README.md); settings sheets preserve their
compact 11px labels and values. The shared renderer owns reference
layout, projected-bounds camera fitting and labeled orientation axes, so desktop
and web stay consistent without host-specific copies of those controls.

### Navigation

The Viewer has the one navbar every app shares (see
[the host contract](../../packages/ui/docs/viewer-host.md#host-chrome-slots)): at the
left the C logo, which opens the app menu, then the open file's name, which opens the
explorer, with its ⋯; at the right only the blue update button, while a newer text-to-cad
is out. The app menu holds Back to files (the home), the person's settings (Share anonymous usage data), Send feedback (a new issue titled "Feedback: "),
GitHub, Discord and, in gray, the version (a link to its release notes) and "Made by @…"
(X), as in the CAD app, over a file and on the home alike.
Display and Preview are the view's, at the navbar's right end. This host
supplies the links (`src/host/viewerLinks.js`): its version (with its build's id,
`v0.7.15-dev.b80844940`, for any build but the release's own), the GitHub (where new
issues open) and Discord its build names (`VIEWER_GITHUB_URL`, `VIEWER_DISCORD_URL`);
links open in a new tab. A newer text-to-cad is the blue update button's, at the navbar's right as in the CAD app: cadgen's
daily version check, read from `/__cad/version` with the server's description as the page
starts (`main.tsx`) and again whenever the person comes back to it, and its prompt copied for
the person to paste into their agent's chat; its full install instructions open in a new tab.
A Viewer the CAD server opens says what the server's channel allows (a store's copy hears nothing);
one a skill opens names no channel, a skills-only install, which is told. Browser titles use "CAD | <filename>", or "CAD" when no file is selected.
Appearance (System, Light, Dark) is the app menu's Theme row, the tab's choice (`colorScheme`,
over a file and on the home); the page has no light/dark button of its own. The original animated mark remains the shared LoadingIcon
for loading states. The C and CAD marks are the UI package's; the favicons are this
app's, exported alongside the docs brand assets. See
[the brand recipe](../../scripts/brand/README.md).

The web camera action copies only the viewport PNG through guarded
`POST /__cad/clipboard`, avoiding browser clipboard permission prompts. The local
backend writes the server machine's native clipboard on macOS or Linux (wl-copy/xclip);
this is not the remote phone's clipboard when accessing a shared server. Failures
use the viewer's error presentation; successful actions are silent. A host with a
composer has no camera action: its note to the agent is Quick Edit.

## Live models

A model's page is `/<id>`, its document's id, which `python SCRIPT.py` prints (`view:`). The
page reads the document the engine holds, by id (`GET /__cad/catalog?id=`); it never builds or
imports a script, and no folder lists one. A model has no file of its own: no Select File, no
file menu, and it never enters saved recents or thumbnail storage. Once its worker retires or
the engine restarts, its page says it is no longer held and names the command that builds it
again. Rebuilding the model updates the same view through the document version stream.
