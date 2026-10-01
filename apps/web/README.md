# CAD Viewer

A local-filesystem CAD review app. This directory is the React CLIENT; the
backend is `cadgen viewer` — the `cadgen.viewer` package in the cadgen Python
distribution — and the built client ships inside that same wheel. One instance
serves ONE directory, fixed at start; the page is always the bare origin and
`?file=` selects an artifact inside that root. There is no hosted deployment.

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
  App.tsx               the CadViewer's browser host: URL, history, title and appearance
  main.tsx              host/client bootstrap and cleanup
  adapters/             the file menu's actions (copies, reveal) and what it records in the model library
  host/                 browser clipboard, prompt delivery, the navbar's links and release check, development auto-reload
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
- **Document boundary**: everything renders from the artifact, its optional
  schema-9 `.step.json` sidecar and immutable cache views. The sidecar embeds
  appearance, JavaScript animation and kinematics. The viewer never reads model
  source and never triggers a source build. An already-running build can publish
  complete immutable preview revisions before saving its STEP output.
- **Independent motion**: kinematics and animation compose in effect records.
  Annotation revisions reload without rebuilding geometry. A mismatched STEP
  digest leaves geometry viewable and reports unavailable annotations.
- **Loud failure**: a missing entry, an unresolvable ref, or a failed
  compile surfaces as an alert — never a silently wrong scene.

## Launching

Dev serves the client from source with HMR. Build the shared packages from the
repository root first, then invoke npm from the directory you want to serve
(outside `apps/web`):

```bash
cd <the directory to serve>
VIEWER_PYTHON=<checkout>/.venv/bin/python \
  npm --prefix <checkout>/apps/web run dev -- --host 127.0.0.1
# open http://127.0.0.1:5173/?file=<path relative to the served root>
```

For the spawned backend, `scripts/directoryRoot.mjs` uses an explicit
`directoryRoot` supplied by its caller first, then `INIT_CWD`, then the process
working directory, accepting the latter two only outside `apps/web`. If neither
qualifies, Vite defaults to the app's parent, `<checkout>/apps`. npm sets
`INIT_CWD` to the directory where you invoked it, so `--prefix` selects the app
without changing the served root. The page URL stays at the bare origin;
`?file=` selects an artifact within that root.

Dev spawns the real backend — `python -m cadgen.viewer --api-only` on an
ephemeral port — and proxies `/__cad` and `/__tess_cache` to it, so there is one
implementation, not two, and Vite owns the client. `VIEWER_PYTHON` names the
interpreter that has cadgen installed (it defaults to `python3` and must be
Python 3.11 or newer); `VIEWER_BACKEND_URL` attaches to a backend you started
yourself, which retains its own served root.
The shared packages must be built first; the web app itself needs no production
build for Vite development.

Prod is `cadgen viewer`, run FROM the directory to serve (there is no directory
flag, the cwd IS the served directory). It serves the client bundled by
`scripts/bundle/bundle.sh` or installed in the wheel. To explicitly select this
checkout's web build, start from the repository root:

```bash
npm run build:web
export CADGEN_VIEWER_DIST="$PWD/apps/web/dist"
cd <the directory to serve> && cadgen viewer --host 127.0.0.1 --json
```

The launcher is unconditional and prints the URL it serves: a live instance
already serving that realpath with the same code on disk is REUSED
(`action:"reused"`); otherwise it binds the first free port from 3245 upward.
`--new` forces a fresh instance of the same code; an explicit `--port` is
strict; `--dist DIR` (or `CADGEN_VIEWER_DIST`) names another built client. The
URL line (and the `--json` line) is written only after the socket is bound and
listening with the app attached and the instance registered, so the first
request after reading it answers and `list`/`stop`/reuse already see it — no
poll, no retry, no grace period. Nothing about the served tree stands in front
of that line: the catalog walk happens after it, in the background.

A launch that STARTS a server is that server: it stays in the foreground until
it is stopped (Ctrl-C, `stop`), which is what a terminal and `npm run dev`
want. A launch that REUSES one prints and exits. `--detach` makes both return:
the server runs as a background process in its own session, its output goes
to a log beside its registry entry
(`<tmp>/cadgen-viewer-info/viewer-<launch-time>-<random>.log`, named by the
launcher's message and by `list`), and the launcher exits 0 once the server
has announced itself — or relays the server's refusal and exits non-zero. The
log outlives the server so a crash can be read afterwards: a clean `stop`
removes it; an instance that crashed or was killed keeps it for a day, the
newest ten at most. Agents and scripts use `--detach`; never pipe a foreground
launch into `tail` or `head`, which wait for an EOF a running server never
sends.
`--detach` refuses `--no-registry`, since `list`/`stop` are the only way to
find a detached server again. `cadgen viewer list` shows every running
instance; `cadgen viewer stop --port <n>` ends one. Do not stop instances you
did not start. Dev lives on Vite's port (5173, strict) and never enters the
instance registry.

Reuse keys on realpath(served directory) × an identity token — the cadgen
version plus content digests of the server runtime and the selected built
client — so an instance serving a different directory, the same directory
from another install, or code that has since been edited, pulled, or rebuilt is
never handed back by mistake. In a checkout, a server that finds `src/` beside
the `dist/` it serves also warns once on stderr when any source is newer than
the build — detection only; it keeps serving.

## Behaviours worth knowing before concluding something is broken

- **The catalog scan skips dot-directories.** A buildable entry under
  `.review/` (or any dotted path) never appears, even when the server is
  launched from inside it. It also skips `__cadgen__`, `__pycache__`, `build`,
  `coverage`, `dist`, `node_modules` and `viewer` (exact case). Everything
  else is walked — a project's `tmp/` included.
- **Every catalog request is fresh, and a warm one is cheap.** A new model
  appears on the next request and a deleted one is gone from it. The server
  remembers each directory's listing against that directory's own stamps, for
  at most 10 s, so a root with a few hundred thousand scratch files costs one
  stat per directory on most requests, not one entry per file; the first walk
  after launch (done in the background) and one poll in five pay for every
  file. Where a directory's stamps can be put back (an extract that restores
  times onto FAT, exFAT or a Windows disk) a change can take those 10 s to show.
  [docs/backend.md](docs/backend.md) has the rule.
- **Verify a link by loading the page**, never by curling `/__cad/asset` —
  that route serves raw files; generated entries render through a
  different route, so probing it 404s whether or not anything is wrong.
- **Large catalogs are partial.** Path-only `catalogPending` entries support
  navigation but are not renderable metadata. The shared client resolves the
  selected file explicitly and polls active files. Other files' placeholders
  must not erase resolved metadata; a newer complete entry still invalidates
  that file's view. The app retains one root client across navigation, so its
  bounded mesh-cache write queue survives file switches. The shared renderer
  retains completed STEP working sets in a bounded CPU cache, so reopening a
  warm assembly does not reload each component. Root, origin and revision
  identities isolate reuse; changed files and evicted entries load normally.
  Inactive WebGL scenes are released, and a file's camera lives only while its
  viewer is mounted.
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

The web host owns URL/history, root-scoped persistence, appearance, version links
and native service adapters. Shared renderers own all model interaction. STEP and
robots open in Select, whose Features (Links for a robot) panel hangs under the
toolbar with the rest of the tool stack; Position's panel replaces it while Position
is the tool. The navbar has no panel of the file's: the explorer's is its one toggle.
STEP and robot files have a
top-left toolbar; GLB, STL and 3MF have none. Every 3D file has Display settings
and Preview among the view actions on top of the view cube at the bottom-left,
and Quick Edit at the top-right. DXF is a 2D canvas with pan, zoom, snapshot and
Quick Edit, without a 3D toolbar or tool stack.

The file explorer floats over the view's left and never resizes it. Below 720px of
FileViewer width it is a floating sheet over the viewer and the tree panel of the
tool stack starts folded. Preview is the shared shell's button among the view
actions: it keeps the navbar and the explorer, hides the toolbar, tool stack and
Quick Edit, orbits by default, plays routines (on entry only with Autoplay on)
and offers Playback and Display settings; the host passes no preview props.
The camera is never stored, so a refresh frames the file anew; Display settings,
pose and explode are kept per file through the shared state contract (see
[storage](docs/storage.md)).

Authored material information lives in the selection's reference details; editing
it requires changing the source model or annotations. The viewer has no Materials
or Theme editor. These controls live in `@text-to-cad/ui`; see the UI package's
Render and LOD playbooks.

Large assemblies load progressively and refine visible components within memory
budgets. Warm tessellations can render before exact surface derivation. The
viewport carries opening/update status, centred at its top (a progress icon on
mobile); initial loading may also use the viewport overlay, and an error is a card over the viewport whose Details keep the complete
compiler output and whose Try again reloads only that file. A failed update the
model survives can be dismissed, leaving the previous version to inspect.

A source-checkout backend can restart on Python code changes. This browser host
polls its identity and reloads when the same endpoint is ready. Installed wheels
report `autoReload: false` and never enter that loop. Vite 8 handles client HMR,
uses compiled workspace exports and honors an explicit `PORT` while retaining
strict port binding. React 19 is deduplicated with the shared packages.

Prompt actions prepare clipboard content for an external composer. References
use the complete served-root path and canonical selector grammar. Image writes
begin during the user gesture with a pending PNG Blob. A mixed text/image copy is written as separate clipboard
representations, and its result says some receivers paste only one; unsupported combinations fail without
silently copying a subset. No receipt claims that another app pasted or sent the
content. Bundles accept at most 128 parts and one PNG up to 20 MiB; image support
is advertised only when the browser exposes image clipboard writes. Failed
operations can be retried, while recent successful operation IDs prevent repeated
writes. Clipboard operations, prompt delivery and development reload live
under `src/host`; shared UI receives their explicit ports. The browser file source
exposes no general write operations.

The prompt destination is the clipboard, so Quick Edit offers Copy Prompt alone. Its
text goes through the clipboard port's `writeText`, which takes pending text: a
`ClipboardItem` holding the promise, so the write starts inside the gesture, or the
text itself once it arrives where the browser takes no pending item. A sketch is
saved through the host's `attachments` (`createHttpAttachmentStore`, over
`POST /__cad/sketches`) and named in the text by its absolute path.

### No file open

With no file open, the navbar keeps its place: the explorer's toggle, then the words
"Select file" where a file's name goes, and the page says "Ask the agent to show a
model". The explorer does not open by itself.

### The model library

The Viewer has no home: the library of models every CAD view shares is the Codex
sidebar's to show (`@text-to-cad/ui/library`). The Viewer only writes to it, through
`POST /__cad/recents`: the file on screen joins it once the catalog has it
(`{action: "open"}`), and its picture once it has settled — the model framed whole
from the default direction, whatever the camera (`{action: "thumbnail"}`).
`cadgen.viewer.recents` keeps the library in the user's state directory, shared with
every other Viewer and the MCP app.

### File storage and host actions

The web `FileSource` is the served folder's read-only CAD catalog
(`createCatalogFileSource` from `@text-to-cad/ui/catalog`, the one the MCP app uses
for a project). It exposes stat, directory listing and path search without text
writes or native filesystem mutations. Catalog content/revision changes are
distinct from transient metadata progress, so progress updates do not restart a
prepared document. Native path copying and file reveal live in the separate host
actions adapter (`src/adapters/fileActions.ts`, over the shared
`createCadFileActions`), which the navbar's ⋯ and the explorer's right-click menu
share. Path copying uses the clipboard port. Reveal uses guarded `POST /__cad/reveal` with a root-relative
path; the backend rejects paths outside the served directory, including symlink
escapes, and opens the native file manager without a shell. The menu uses the
server platform to label Finder, Explorer, or the Linux file manager, and only
offers reveal when the server advertises `reveal-path`. Path copies form the first menu section. Reference copying belongs
to the renderer's selection action, rather than the file menu.

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
left the explorer's toggle and the open file's name with its ⋯ ("Select file" with
none open); at the right the renderer's snapshot action,
then the version, whose menu holds GitHub and Discord. This host supplies the links
(`src/host/viewerLinks.js`): its version, the GitHub and Discord its build names
(`VIEWER_GITHUB_URL`, `VIEWER_DISCORD_URL`), and what GitHub's latest-release API
says, so the version reads "Update" when a newer release is out; links open in a new
tab. Browser titles use "CAD | <filename>", or "CAD" when no file is selected.
Appearance is injected as an icon-bearing dropdown beside Projection in the Display
panel's Display section, below the full-width Mode selector (`ViewerAppearance`,
through `displayActions`). The original animated mark remains the shared LoadingIcon
for loading states. The C and CAD marks are the UI package's; the favicons are this
app's, generated alongside the docs brand assets. See
[the brand recipe](../../scripts/brand/README.md).

The web camera action copies only the viewport PNG through guarded
`POST /__cad/clipboard`, avoiding browser clipboard permission prompts. The local
backend writes the server machine's native clipboard on macOS or Linux (wl-copy/xclip);
this is not the remote phone's clipboard when accessing a shared server. Failures
use the viewer's error presentation; successful actions are silent. A host with a
composer has no camera action: its note to the agent is Quick Edit.
