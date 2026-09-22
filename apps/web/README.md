# CAD Viewer

A local-filesystem CAD review app. This directory is the React CLIENT; the
backend is `cadgen viewer` — the `cadgen.viewer` package in the cadgen Python
distribution — and the built client ships inside that same wheel. One instance
serves ONE directory, fixed at start; the page is always the bare origin and
`?file=` selects an artifact inside that root. There is no hosted deployment.

This package was renamed from the former viewer app directory. It is the browser host of
`@hardcore/ui/file-viewer`, not the owner of the shared CAD interface.
This is a **pure refactor**: UI, UX and functionality stay the same, including
URL/history behavior, read-only actions, app appearance and camera state, CAD
selection/measurements/tools and responsive behavior.

**Owns:** URL selection, browser history, document title/appearance, catalog
file-source adapter, browser persistence, and this app's top bar/release links.
`src/App.tsx` composes an explicit `ViewerHost` and one renderer per file family. The catalog
continues to expose CAD artifacts only; this migration adds no file types or
write endpoints to the web app.
Follow the [shared host contract](../../packages/ui/docs/viewer-host.md) when
adding viewer features; browser effects belong in this app's adapters.
The [shared Model tree](../../packages/ui/docs/cad-renderer.md#step-panel)
owns expansion-based picking, lazy topology/feature inspection and isolation.
Web uses the same tree and file-row primitives as desktop; its HTTP adapter
does not decide which model nodes are expanded or selectable.
Feature detection runs client-side in shared UI when parts are expanded, with
a versioned memory cache reused across file switches. A page refresh loses that
cache; recognition is separate from cadgen compilation and Python inspection.
See [feature detection](../../packages/ui/docs/feature-detection.md) for rules,
limits and cancellation. This app supplies resources, not recognition logic.

**May depend on:** compiled `@hardcore/ui` and `@hardcore/core` exports and app
libraries. Never another application's source. Shared packages never import
this app. The Python wheel consumes only the production build.

```text
src/
  App.tsx               FileViewer browser host and renderer registration
  main.tsx              host/client bootstrap and cleanup
  adapters/             read-only catalog file source and capabilities
  host/                 browser clipboard, prompt delivery and page lifecycle
  persistence/          root-scoped view state and legacy preference migration
  client/               app top bar, browser navigation and styling
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
listening with the app attached, so the first request after reading it answers
— no poll, no retry, no grace period. `cadgen viewer list` shows every running
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
  launched from inside it.
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
  Inactive WebGL scenes are released and camera state remains file-scoped.
- **Vite's transform cache can outlive HMR and hard reloads.** If a source
  edit does not show up, restart the dev server and delete
  `node_modules/.vite`.
- Never invoke the export routes from automation — they open native save-as
  dialogs.

## Shared interface

This app exports no components. Other hosts use `@hardcore/ui/file-viewer` with
registered renderers and explicit services. Viewer content is registered through
`@hardcore/ui/renderers/step`, for `.dxf` `@hardcore/ui/renderers/dxf`, for `.glb`
`@hardcore/ui/renderers/glb`, for `.stl` and `.3mf` `@hardcore/ui/renderers/mesh`, and
for `.urdf`, `.srdf` and `.sdf` `@hardcore/ui/renderers/robot` (`App.tsx` registers all
five with the same client and preferences); all loading,
selection, panel and tool behavior is shared. Public declarations, styles and worker assets are built in that
package. See `docs/shell.md` for the host boundary and `docs/storage.md` for
browser persistence. CAD control guidance lives with the UI package.

`vite.config.mjs` adds the shared `@hardcore/ui/drawing-assets` plugin so the
Excalidraw editor in `@hardcore/ui/drawing` never fetches a font from a CDN:
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

From the repository root, `scripts/test/test-viewer-browser.sh --ci` exercises
the bundled client's format, picking, kinematics (robot joints, an SRDF group
state, a STEP mate) and camera contracts with fresh temporary fixtures and a private server/cache. Omit `--ci`
to include full cold/warm/disabled-LOD picking, scene placement and Render quality
checks. `--out /tmp/viewer-review` retains screenshots and bounded failure
diagnostics; the runner cleans up its project and processes on exit.

### Branded loading indicator

`@hardcore/ui/loading-icon` exports the decorative `LoadingIcon` independently of
the CAD renderer, so a host can show loading feedback without eagerly importing the
CAD surface. `size` controls its pixel dimensions (default 96), `className` its
placement, and `active={false}` uses the still pose. The host owns status text.
It also stays still for OS/app reduced motion and hidden documents. See
the UI package's asset documentation for asset provenance and regeneration.

### Narrow CAD panes

A file has a top-right tool strip only where it has tools. A STEP's holds Select,
Measure, Draw, plus Position and Animate where the file has joints or routines,
and Fullscreen last; pressing Select again opens its selection-filter dropdown.
Under Select a
secondary tap over a STEP opens the part menu (the shell's viewport menu, filled
by the STEP renderer); under any other tool it opens nothing. A robot description
(its own renderer) opens in Position, which leads its tools, followed by a Select
that picks whole links. Draw is a STEP tool and appears nowhere else. A DXF, a
GLB, an STL and a 3MF (their own renderers) have NO tools and no strip at all:
their viewport simply orbits, pans and zooms, and a secondary press opens
nothing. A GLB with clips shows the playbar under the model always — it is a
transport, not a tool, and the file opens at rest. A DXF is not a viewport at
all: it is a straight 2D render on a canvas (drag to pan, wheel or pinch to zoom
about the pointer, double-click to fit), and its file navbar carries Take
snapshot and the file tree's toggle, nothing else. Buttons wrap inside the pill
when an open panel or a narrow host reduces the scene width. Snapshot is a
direct action before the panel toggles in the file navbar (the file's own panel,
Display, then the file tree); the web prompt adapter copies the viewport image
and references to the clipboard.
There is no zoom control: no percentage readout, no menu behind
one, no zoom toolbar. A STEP's viewport context menu ends in Zoom to fit and Zoom
to selection (off without a selection), offered over a part, over the backdrop and
on every Features tree row; on every other 3D file the view cube's centre, "Reset
to default isometric view", frames the model again from the default direction.
Nothing in either touches the model, its motion or its display settings.
X/Y/Z labels remain visible outside the bottom-right axis endpoints.

Fullscreen (`Maximize2`) is the last button of a STEP's own tool strip; the web
header has none, and no other format offers it. The app owns this transient
state and passes it to FileViewer with `onFullscreenChange`, which FileViewer
hands to the STEP renderer alone. It hides all chrome, the nav row, the panel
column and viewport tools. Shared CAD fullscreen controls show the Animate tool's
transparent centered bottom playbar and an untooltipped orbit-settings button
plus X at top-right. Settings opens a floating, content-height panel capped by
the viewport, with one permanent Orbit section: a speed slider and numeric
input (0 stops rotation). The bottom playbar has plain play/pause and a live
scrub bar — there is no separate restart, since scrubbing to the start is the
restart — and is absent without animation. Position stays in the file's panel.
Both control areas fade after two seconds idle; an open settings panel and active
slider/keyboard interaction keep them visible.
The app honors prevented Escape events so nested pickers and settings close
before fullscreen exits; X calls `onFullscreenChange(false)`. X or Escape
restores the panel, active tool and original camera without reloading the scene.
Each entry starts at the default camera. Orbit speed persists globally through
the host preference adapter; animation shares the Animate tool's per-file state
and clocks.

## Current viewer behavior

The nav row is the tab strip: a file's toggles are its own panel, `Display`,
then the file tree, and no panel has tabs inside it. A STEP's own panel is
`Part` or `Assembly`; it stacks Features, then Position when the sidecar
declares kinematics (a `Pose` row, the joint sliders, then Reset), then Issues
when there are any. Every pose write — a named pose, a slider, a typed value, or
a Position-tool knob — is an instant jump; there is no eased transition. Reset
also stops any playing routine and hands the pose back to Position, so the two
never disagree about which one is in control afterward. A robot description's
own panel is `Robot`: its Position (a `Pose` row with any SRDF group states,
then joint sliders, then Reset), then Links, which always shows the robot's link
tree, and an SDF's metadata after Links. An
STL, a 3MF and a GLB have Display and the tree. A DXF has neither a panel of its
own nor Display — only the file tree's toggle beside Take snapshot: a drawing is
a finished 2D document, and the pane shows it and nothing else.

The open panel is not saved: a page load opens the file with its own panel, or
with nothing when it has none, and Display is never open by default. In a window
at least 520px wide, a file picked in the tree opens with the tree still up, so it
can be walked file by file, and any other open (a crumb, a link in a panel) shows
the file's own panel; below that width every open leaves the model the room, with
no panel at all. The web host stores the
panel width and the tree's expanded folders ([storage](docs/storage.md)).

Display owns a single Mode dropdown: Solid, Render, X-ray, Hidden line and Wireframe.
Modes are presets over one grouped display schema, and all settings groups are
available in every preset. Render defaults to perspective; others to orthographic.
Changing a view setting shows Custom. Display Reset restores its base preset and
disables Clip/Explode; preset selection preserves those tools. Neither operation
changes camera viewpoint/zoom, selection, the pose or app appearance.
Expanded settings groups are enabled; the minus disables and restores neutral
behavior. See [View presets](../../packages/ui/docs/render-mode.md). The file's
own panel stays mounted while Display is open, so the Features tree keeps its
disclosure and scroll.

Authored material information lives in the Model reference details; editing it
requires changing the source model or annotations. The viewer has no Materials
or Theme editor and does not restore legacy material overrides or custom themes.
These controls live in `@hardcore/ui`; the web host keeps URL/history, appearance
and root-scoped persistence. See the UI package's Render and LOD playbooks.

Large assemblies load progressively and refine visible components within memory
budgets. Warm tessellations can render before exact surface derivation. The
breadcrumb carries no status: opening and updating show in the viewport's loading
overlay, and an error is a card over the viewport whose Details keep the complete
compiler output and whose Try again reloads only that file. A failed update the
model survives can be dismissed, leaving the previous version to inspect.

A source-checkout backend can restart on Python code changes. This browser host
polls its identity and reloads when the same endpoint is ready. Installed wheels
report `autoReload: false` and never enter that loop. Vite 8 handles client HMR,
uses compiled workspace exports and honors an explicit `PORT` while retaining
strict port binding. React 19 is deduplicated with the shared packages.

Prompt actions prepare clipboard content for an external composer. References
use the complete served-root path and canonical selector grammar, rather than a
display filename suffix. Image writes begin during the user gesture with a
pending PNG Blob. A mixed text/image copy reports separate representations and
warns that some receivers paste only one; unsupported combinations fail without
silently copying a subset. No receipt claims that another app pasted or sent the
content. Bundles accept at most 128 parts and one PNG up to 20 MiB; image support
is advertised only when the browser exposes image clipboard writes. Failed
operations can be retried, while recent successful operation IDs prevent repeated
writes. Clipboard operations, page exit publication and development reload live
under `src/host`; shared UI receives their explicit ports. The browser file source
continues to expose no general write operations.

### File storage and host actions

The web `FileSource` is a read-only CAD catalog. It exposes stat, directory
listing and path search without text writes or native filesystem mutations.
Catalog content/revision changes are distinct from transient metadata progress,
so progress updates do not restart a prepared document. Native path copying and
Copy reference live in the separate host actions adapter. Reference delivery
uses the injected prompt port with the served workspace identity; ordinary path
copying uses the clipboard port and retains the existing feedback labels.

### Shared interface defaults

The host body uses the shared `text-ui` token (13px at the normal root scale).
Menus, tabs and tree rows follow the same default from
[`@hardcore/ui`](../../packages/ui/README.md); settings sheets preserve their
compact 11px labels and values. The shared renderer owns reference
layout, projected-bounds camera fitting and labeled orientation axes, so desktop
and web stay consistent without host-specific copies of those controls.
