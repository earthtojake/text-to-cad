# CAD Viewer

A local-filesystem CAD review app. This directory is the React CLIENT; the
backend is `cadgen viewer` — the `cadgen.viewer` package in the cadgen Python
distribution — and the built client ships inside that same wheel. A viewer
serves every CAD file on the machine by its absolute path, on port 3245 or the
port `--port N` names: the page is the bare origin and `?file=` names the file (a relative one resolves
against the folder the viewer was started in). There is no hosted deployment.

This app is the browser host of `@text-to-cad/ui/file-viewer`, not the owner of
the shared CAD interface.

**Owns:** URL selection, browser history, document title/appearance, browser
persistence, the file menu's reveal route, and this app's release check.
`src/App.tsx` composes an explicit `ViewerHost` and hands it to the shared
`CadViewer` (`@text-to-cad/ui/cad-viewer`), which registers one renderer per file
family and draws the navbar and the explorer. The catalog exposes CAD
artifacts only, and the web app has no file-writing endpoints.
Follow the [shared host contract](../../packages/ui/docs/viewer-host.md) when
adding viewer features; browser effects belong in this app's adapters.
The [shared Model tree](../../packages/ui/docs/cad-renderer.md#step-panels)
owns expansion-based picking, lazy topology/feature inspection and isolation.
Web uses the same tree and file-row primitives as desktop; its HTTP adapter
does not decide which model nodes are expanded or selectable.
Feature detection runs client-side in shared UI when parts are expanded, with
a versioned memory cache reused across file switches. A page refresh loses that
cache; recognition is separate from cadgen compilation and Python inspection.
See [feature detection](../../packages/ui/docs/feature-detection.md) for rules,
limits and cancellation. This app supplies resources, not recognition logic.

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
- **Document boundary**: everything renders from the artifact, what cadgen
  resolved its optional schema-10 `.step.json` sidecar into (the catalog entry's
  `articulation`, `animation` and per-occurrence `display`: data, never code; the
  page reads no sidecar) and immutable cache views. The viewer never reads model
  source and never triggers a source build. An already-running build can publish
  complete immutable preview revisions before saving its STEP output.
- **Independent motion**: kinematics and animation compose in effect records.
  Annotation revisions reload without rebuilding geometry. A mismatched STEP
  digest leaves geometry viewable and reports unavailable annotations.
- **Loud failure**: a missing entry, an unresolvable ref, or a failed
  compile surfaces as an alert — never a silently wrong scene.

## Launching

Dev serves the client from source with HMR. Build the shared packages from the
repository root first, then invoke npm from the folder a relative `?file=`
should resolve against (outside `apps/web`):

```bash
cd <a folder of models>
VIEWER_PYTHON=<checkout>/.venv/bin/python \
  npm --prefix <checkout>/apps/web run dev -- --host 127.0.0.1
# open http://127.0.0.1:5173/?file=<an absolute path, or one relative to that folder>
```

For the spawned backend, `scripts/directoryRoot.mjs` uses `INIT_CWD`, then the
process working directory, accepting either only outside `apps/web`. If neither
qualifies, Vite defaults to the app's parent, `<checkout>/apps`. npm sets
`INIT_CWD` to the directory where you invoked it, so `--prefix` selects the app
without changing that folder. It is only where relative links resolve
(`serverInfo.start`): the backend opens any file by its absolute path.

Dev spawns the real backend — `python -m cadgen.viewer --new --api-only` on a
port of its own — and proxies `/__cad` and `/__tess_cache` to it, so there is
one implementation, not two, and Vite owns the client. `VIEWER_PYTHON` names the
interpreter that has cadgen installed (it defaults to `python3` and must be
Python 3.11 or newer); `VIEWER_BACKEND_URL` attaches to a backend you started
yourself. The shared packages must be built first; the web app itself needs no
production build for Vite development.

Prod is `cadgen viewer`, run from anywhere. It serves the client bundled by
`scripts/bundle/bundle.sh` or installed in the wheel. To explicitly select this
checkout's web build, start from the repository root:

```bash
npm run build:web
export CADGEN_VIEWER_DIST="$PWD/apps/web/dist"
cadgen viewer --host 127.0.0.1 --json
```

The launcher is unconditional and prints the URL it serves: on port 3245, or the
port `--port N` names, as any web server. Before binding it asks that port who holds it
(`GET /__cad/server`): nothing, and it starts there (`action:"started"`); this
user's viewer at the same identity, and it is REUSED (`action:"reused"`); this
user's viewer running other code, and that one is asked to exit
(`POST /__cad/shutdown`) and the launch starts on the freed port — the newest
code wins, on the same URL; anything else (another program, another user's
viewer), and it refuses, naming `--port`. `--new` binds an OS-assigned free
port, asks nothing and is never reused (dev and tests); `--dist DIR` (or
`CADGEN_VIEWER_DIST`) names another built client. The URL line (and the
`--json` line) is written only after the socket is bound and listening with the
app attached, so the first request after reading it answers — no poll, no
retry, no grace period.

A launch that STARTS a server is that server: it stays in the foreground until
it is stopped (Ctrl-C, `stop`), which is what a terminal and `npm run dev`
want. A launch that REUSES one prints and exits. `--detach` makes both return:
the server runs as a background process in its own session, its output goes
to one log in the state directory (`viewer.log`, named by the launcher's
message), and the launcher exits 0 once the server has announced itself — or
relays the server's refusal and exits non-zero. The log outlives the server so
a crash can be read afterwards, until the next detached start. Agents and
scripts use `--detach`; never pipe a foreground launch into `tail` or `head`,
which wait for an EOF a running server never sends.
`cadgen viewer stop [--port N]` asks this user's viewer on a port to exit and
waits for the port to be free. Dev lives on Vite's port (5173, strict).

The identity is the cadgen version plus content digests of the server runtime
and the selected built client, so a viewer running code that has since been
edited, pulled, or rebuilt — or another client — is replaced rather than handed
back by mistake. In a checkout, a server that finds `src/` beside the `dist/` it
serves also warns once on stderr when any source is newer than the build —
detection only; it keeps serving.

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
- **Warm work survives navigation.** The app retains one client across navigation, so its
  bounded mesh-cache write queue survives file switches. The shared renderer
  retains completed STEP working sets in a bounded CPU cache, so reopening a
  warm assembly does not reload each component. Origin and revision identities
  isolate reuse; changed files and evicted entries load normally.
  Inactive WebGL scenes are released, and a file's view (its camera, Display
  settings and pose) lasts only while it is the file on screen: a refresh brings it
  back, and leaving the file drops it.
- **Vite's transform cache can outlive HMR and hard reloads.** If a source
  edit does not show up, restart the dev server and delete
  `node_modules/.vite`.
- Never invoke the export routes from automation — they open native save-as
  dialogs.

## Shared interface

This app exports no components. Other hosts use `@text-to-cad/ui/file-viewer` with
registered renderers and explicit services. Viewer content is registered through
`@text-to-cad/ui/renderers/step`, for `.dxf` `@text-to-cad/ui/renderers/dxf`, for `.glb`
`@text-to-cad/ui/renderers/glb`, for `.stl` and `.3mf` `@text-to-cad/ui/renderers/mesh`, and
for `.urdf`, `.srdf` and `.sdf` `@text-to-cad/ui/renderers/robot` (`CadViewer` registers all
five with the same client and preferences, as it does for the MCP app); all loading,
selection, panel and tool behavior is shared. Public declarations, styles and worker assets are built in that
package. See `docs/shell.md` for the host boundary and `docs/storage.md` for
browser persistence. CAD control guidance lives with the UI package.

`vite.config.mjs` adds the shared `@text-to-cad/ui/drawing-assets` plugin so the
Excalidraw editor in `@text-to-cad/ui/drawing` never fetches a font from a CDN:
`drawing-assets.js` and `excalidraw/` are served in dev and emitted into
`dist/`. The 12 MB Xiaolai CJK family is excluded from this build to keep the
wheel small; CJK text falls back to a system font. See
[drawing](../../packages/ui/docs/drawing.md#offline-assets-and-upgrades).

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

Headless CAD checks use Playwright with Metal on macOS and SwiftShader on
Linux/Windows. Use the same graphics backend for baseline/refactor image
comparisons.

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
[tool stack and mobile layout](../../packages/ui/docs/settings-ui.md#the-tool-stack),
settings controls, selection and
[preview](../../packages/ui/docs/settings-ui.md#camera-animation-and-preview).
Keep those rules there rather than maintaining a separate web layout
specification.

The web host owns URL/history, the tab's persistence, appearance, version links
and native service adapters. Shared renderers own all model interaction. STEP and
robots open in Select, whose Features (Links for a robot) panel hangs under the
toolbar with the rest of the tool stack; Position's panel replaces it while Position
is the tool, and the Animation tool's (a STEP with routines) while that is. The file's
name in the navbar opens the explorer.
STEP and robot files have a top-left toolbar; GLB, STL and 3MF have none, and a GLB with
clips has the Animation panel there instead, always up. Every 3D
file has Display (its settings, a dropdown that opens down) and Preview at the navbar's
right end, the view cube at the bottom-left, and Quick Edit at the top-right. DXF is a 2D canvas with
pan, zoom, snapshot and Quick Edit, without a 3D toolbar or tool stack.

The explorer is a popover under the file's name: the file's folder, one folder at a
time, with "Filter files..." to find a file anywhere under it. Below 720px of
FileViewer width the tree panel of the tool stack starts closed (Select, pressed,
opens it). Preview is the shared shell's button beside Display: it takes the whole page,
hiding the navbar, toolbar, tool stack and
Quick Edit, orbits by default, plays routines (on entry only with Autoplay on)
and keeps its own controls where the navbar's sat — Orbit, Display, Exit preview — with
the routines and their Playback settings on the playbar; the host passes no preview props.
The file on screen keeps its view in the tab — its camera, Display settings
(explode and clip included) and pose — so a refresh restores it; leaving the file for
another or for the home drops it, and opening it again frames it anew (see
[storage](docs/storage.md)).

Authored material information lives in the selection's reference details; editing
it requires changing the source model or annotations. The viewer has no Materials
or Theme editor. These controls live in `@text-to-cad/ui`; see the UI package's
Render and LOD playbooks.

Large assemblies load progressively and refine visible components within memory
budgets. Stored meshes render before exact surface derivation. The
viewport carries opening/update status, centred at its top (a progress icon on
mobile); initial loading may also use the viewport overlay, and an error is a card over the viewport whose Details keep the complete
compiler output, whose Retry reloads only that file and whose Report Issue opens a
new issue titled "Issue: ", labelled `bug`, filled in from the card. A failed update the
model survives can be dismissed, leaving the previous version to inspect.

The page reloads once its server is other code: it asks `/__cad/server` for its
`identityToken` (cadgen's version and a digest of its Python and client) and
reloads on a new one, picking up the client, and the store, that server serves. A
source-checkout backend (`autoReload: true`) restarts on Python code changes and is
asked every 2 s, every 0.4 s while it is down; an installed one, which changes only
when another install replaces it on its port, every 5 s and whenever the window
regains focus. The same install restarting does not reload. Vite 8 handles client HMR,
uses compiled workspace exports and honors an explicit `PORT` while retaining
strict port binding. React 19 is deduplicated with the shared packages.

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

The prompt destination is the clipboard, so Quick Edit offers Copy Prompt alone. Its
text goes through the clipboard port's `writeText`, which takes pending text: a
`ClipboardItem` holding the promise, so the write starts inside the gesture, or the
text itself once it arrives where the browser takes no pending item. A sketch is
saved through the host's `attachments` (`createHttpAttachmentStore`, over
`POST /__cad/sketches`) and named in the text by its absolute path.

### The home

The bare URL is the home: the library of models every CAD view shares
(`@text-to-cad/ui/library`), and Open, the desktop's file chooser (`POST /__cad/pick`),
where the server's computer has one (`serverInfo.pick`). From a file, Back to files in
the menu the navbar's C logo opens leads back to it. Under the home's wordmark are GitHub,
Discord and X. A `?file=` that names nothing there shows "File does not exist",
with Go home.

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

The app menu's **Quick edit** (on until the person turns it off) is read and changed
the same way: the client's `features`, through `/__cad/features` (`cadgen/features.py`).
The server keeps the choice in the person's settings, beside the analytics answer, so it is
one choice with the CAD app's and holds whatever port this Viewer is served on, which the
page's own storage would not.

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
is out. The app menu holds Back to files (the home), the person's settings (Share
usage stats, Quick edit), Send feedback (a new issue titled "Feedback: "),
GitHub, Discord and, in gray, the version (a link to its release notes) and "Made by @…"
(X), as in the CAD app; the home shows GitHub, Discord and X under its wordmark instead.
Display and Preview are the view's, last at the navbar's right. This host
supplies the links (`src/host/viewerLinks.js`): its version (with its build's id,
`v0.7.15-dev.b80844940`, for any build but the release's own), the GitHub (where new
issues open) and Discord its build names (`VIEWER_GITHUB_URL`, `VIEWER_DISCORD_URL`);
links open in a new tab. A newer text-to-cad is the blue update button's, at the navbar's right as in the CAD app: cadgen's
daily version check, read from `/__cad/version` with the server's description as the page
starts (`main.tsx`) and again whenever the person comes back to it, and its prompt copied for
the person to paste into their agent's chat; its full install instructions open in a new tab.
A Viewer the CAD server opens says what the server's channel allows (a store's copy hears nothing);
one a skill opens names no channel, a skills-only install, which is told. Browser titles use "CAD | <filename>", or "CAD" when no file is selected.
Appearance is injected as an icon-bearing dropdown beside Projection in Display's
Display section, below the full-width Mode selector (`ViewerAppearance`,
through `displayActions`). The original animated mark remains the shared LoadingIcon
for loading states. The C and CAD marks are the UI package's; the favicons are this
app's, exported alongside the docs brand assets. See
[the brand recipe](../../scripts/brand/README.md).

The web camera action copies only the viewport PNG through guarded
`POST /__cad/clipboard`, avoiding browser clipboard permission prompts. The local
backend writes the server machine's native clipboard on macOS or Linux (wl-copy/xclip);
this is not the remote phone's clipboard when accessing a shared server. Failures
use the viewer's error presentation; successful actions are silent. A host with a
composer has no camera action: its note to the agent is Quick Edit.
