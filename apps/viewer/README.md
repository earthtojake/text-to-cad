# CAD Viewer

A local-filesystem CAD review app. This directory is the React CLIENT; the
backend is `cadgen viewer` — the `cadgen.viewer` package in the cadgen Python
distribution — and the built client ships inside that same wheel. One instance
serves ONE directory, fixed at start; the page is always the bare origin and
`?file=` selects an artifact inside that root. There is no hosted deployment.

**PURPOSE** — the application: all UI, workflow, and session state for
reviewing CAD artifacts (catalog, tabs, selection, pose, animation,
measurements, Display controls, and Render settings).

**MAY DEPEND ON** — `cadgen-js` (the shared CAD render/runtime package at
`packages/cadgen-js`, imported by the `cadgen-js` specifier) and its own npm
dependencies, all bundled into the client AT BUILD TIME. At run time it talks
to `cadgen viewer` over `/__cad` and `/__tess_cache`, and to nothing else.

**DEPENDED ON BY** — the cadgen wheel, which carries this client's build
(`cadgen/_runtime/viewer`). No code imports from this app.

## The laws that bind the app

- **One boundary**: the client imports `cadgen-js` by name and nothing else
  from outside this directory (`scripts/selfContained.test.mjs` is the fence).
  The backend is not here: its code, its tests and its laws live with cadgen.
- **Three-input law**: everything renders from the artifact file, its
  sidecar (`<name>.step.json`), and the cache. The viewer never reads
  source code and never rebuilds on source changes — generated outputs are
  detached, and a stale artifact stays stale until someone runs its script.
  STEP entries automatically follow active edits: the runtime announces
  complete immutable preview trees while an already-running decorated build
  saves its outputs. The viewer consumes those trees and resolved kinematics,
  never source or model/output records. Without an available editing preview,
  the viewer reads the saved artifact.
- **Kinematics/animation independence**: the Kinematics tab drives the sidecar's
  mate data through the shared FK runtime; the Animation tab evaluates the
  `clips` exported by the sidecar's embedded JavaScript animation. Sidecar
  metadata revisions reload without rebuilding geometry. They
  compose in the effect records and nowhere else.
- **Loud failure**: a missing entry, an unresolvable ref, or a failed
  compile surfaces as an alert — never a silently wrong scene.
- **Actionable errors**: the viewport and file-status dialog share one heading,
  an explanation, a recovery step, and expandable full diagnostics. Browser
  transport failures retain request context and report a connection problem;
  only an explicit compiler failure is labeled as one. Reload rechecks the
  artifact status and never forces a duplicate build. Compiler output is not
  line-clamped away. A backend warning about a document's neighbours carries that
  same shape and is listed as a non-blocking warning, never as a failed entry.
- **Geometry and display readiness are separate**: a `compiled` artifact owns
  a complete immutable geometry tree. Display may still be waiting for an
  exact surface derivation or tessellation. A validated warm tessellation can
  render directly from its immutable object binding; selectors and a cache
  miss resolve the pinned surface asynchronously without recompiling geometry.

## Appearance, Display, and Render

Three separate things, and keeping them separate is the point. The mechanism,
the constants and the per-format detail are in
[docs/render-mode.md](docs/render-mode.md).

- **App appearance** is a global **System / Light / Dark** preference for the
  CHROME. It never changes the model's lighting or materials, and it persists
  across browser sessions and viewer ports.
- **Display** owns the Inspect scene: projection, style, edge visibility,
  grid, origin axes, part colors, clipping, exploded view.
- **Render** owns an isolated photographic scene: studio, quality, exposure,
  lighting, backdrop, camera — and nothing else. Nothing in it reaches CAD
  lighting, guides, edges, clipping, exploded transforms or selection effects,
  and CAD inspection camera, display and quality overrides never cross into
  it.

The navbar's **Viewing mode** menu switches Inspect ↔ Render. Their settings
are SEPARATE per-model session state: entering a mode restores that mode, never
a blend of the two, and kinematics and animation compose through the same model
pose state in both. The camera does not travel between them at all — entering a
mode fits ITS camera to the model's zero pose, so a switch is a Reset view for
the mode being entered. Quality is independent of the studio — Inspect is
Interactive, Render is **Preview** or **Final** (default Final) — and a quality
change refines the view without rebuilding exact CAD geometry. The Viewer and
`cadgen step snapshot --render` resolve photographic scenes through the same
shared implementation, so the same settings produce the same picture.

**The Materials selection rule.** Part picking is enabled only while the STEP
Materials tab is open; face and edge selectors stay disabled, and the
photographic scene receives no selected parts — the Inspect selection tint and
occlusion ghost would repaint the material being previewed.

**Where it persists.** Material edits, their one step of undo and the panel's
part selection are the MODEL's session, held by the workspace rather than by
the panel, so leaving the tab and returning leaves all three where they were.
They live in per-file `sessionStorage` with the other ephemeral per-model state
([docs/storage.md](docs/storage.md)) — never written beside models, never into
the geometry cache, never into global app appearance. A normal geometry rebuild
preserves the render setup; authored revisions, and bare STEP geometry
revisions, invalidate material overlays; closing the browser tab ends its
session.

## Launching

Dev serves the client from source with HMR; edits to `src/` and to
`cadgen-js` show live:

```bash
cd <the directory to serve>
npm --prefix <this app> run dev -- --host 127.0.0.1
# open http://127.0.0.1:5173/?file=<path relative to that directory>
```

**Dev serves the directory you ran `npm run dev` FROM**, not this app's
directory — the backend has no directory flag in dev either, so the served root
is npm's `INIT_CWD` and the hand-off is the spawned backend's cwd. This app's
own directory is explicitly excluded: running there falls back to its parent,
which is not what anyone wants. Every other command below runs from this app's
directory.

Dev spawns the real backend — `python -m cadgen.viewer --api-only` on an
ephemeral port — and proxies `/__cad` and `/__tess_cache` to it, so there is one
implementation, not two, and Vite owns the client. `VIEWER_PYTHON` names the
interpreter that has cadgen installed (it defaults to `python3`, which on macOS
is still 3.9 — below the server's floor of 3.11 — and rarely the one with
cadgen); `VIEWER_BACKEND_URL` attaches to a backend you started yourself. No
build is needed first.

Prod is `cadgen viewer`, run FROM the directory to serve (there is no directory
flag, the cwd IS the served directory). In a checkout it serves this app's
`dist/` — build it first — and an installed wheel serves the copy it carries:

```bash
npm run build
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
version plus a content digest of the installed cadgen Python runtime and the
exact built client selected for this launch — so an instance serving a
different directory, another `--dist`, the same directory from another
install, or code that has since been edited, pulled, or rebuilt is never handed
back by mistake. The token is computed ONCE per launch, on both sides of that
comparison, and a running server never re-reads it. In a checkout, a server that
finds `src/` beside the `dist/` it serves also warns once on stderr when any
source is newer than the build.

### Auto-reload is a development convenience

A cadgen running from a SOURCE CHECKOUT watches its own Python and, when it
changes, restarts itself in place: it finishes the work in flight, re-executes
with the same arguments on the SAME port — so the URL in the browser and Vite's
proxy target both stay valid — and the page reloads itself once the new process
answers. One line, `code changed; restarting on port N`, goes to stderr. A
compile the Viewer is proxying for the browser holds the restart until it
finishes, and a burst of edits (a rebase, a bundle) produces one restart, not
forty. A `touch`, or a rebuild that produces the same bytes, produces none.

**An installed wheel does none of this.** It never watches, never restarts, and
reports `autoReload: false`; nothing edits a wheel's Python underneath a running
server, and a tool a user installed must not restart itself. The one predicate
that decides — is this cadgen a source checkout? — lives in
`cadgen/viewer/reload.py` and is not an environment variable.

Only the PYTHON is watched. Development means `npm run dev`, where Vite owns the
client and HMR already handles it. A checkout's `cadgen viewer` serves the last
`npm run build` on purpose: it is how you check the production client, not how
you develop it, and it will keep serving that build until you run it again.

## Behaviours worth knowing before concluding something is broken

- The catalog fully resolves the SELECTED file first and lists the others as
  navigation-only rows until one background scan finishes. Selecting one of
  those rows prioritizes its metadata immediately. Unchanged catalog rows and
  concurrent tree verification are reused, so loading one model never waits for
  every model.
- **STEP entries follow an active build.** The root preview shows before the
  STEP save; the prior model stays visible while the next request builds; a
  successful save leaves that revision's authored preview on screen with no
  badge; a failed update keeps the last usable view and says so. Run the model
  normally — existing decorators need no new imports — and keep the daemon
  running. The feed, the badge vocabulary and the Opening stages are
  [docs/lod.md](docs/lod.md) §6.
- **Detail is progressive.** A large assembly can start at a coarse
  tessellation and refine; anything on screen reaches at least standard detail;
  offscreen components stay displayed at the detail they have; an idle viewport
  settles and stays settled; and when memory limits prevent the requested
  detail the filename badge reports **Limited detail** while preserving the
  current view. None of this changes exact geometry, measurements or explicit
  mesh-export tolerances. The scheduler, its budgets and its adoption rules are
  [docs/lod.md](docs/lod.md).
- A schema-9 STEP sidecar includes the STEP byte digest. A mismatch displays
  **Annotations unavailable** while permitting saved geometry to render.
  Rebuild or re-annotate the pair to repair it; importing a file never rewrites
  its authored sidecar.

- **Animation's tube runtime is a separate chunk.** The flexible-tube and
  braid code loads with a document's embedded animation, so a model that
  declares none never fetches it and an animated tube still renders from its
  first frame (`packages/cadgen-js/docs/tube-deformation.md`).
- **Render mode is a separate chunk.** The photographic studio and the
  Materials editor are fetched when Render is first asked for, so the initial
  bundle carries Inspect and the workbench alone. The switch warms the chunk and
  the viewport stays under its destination backdrop until the studio applies, so
  there is no half-configured scene to catch — but a test that mounts either
  settings panel imports the panel module, not the tab builder
  ([docs/render-mode.md](docs/render-mode.md)).
- **The catalog scan skips dot-directories.** A buildable entry under
  `.review/` (or any dotted path) never appears, even when the server is
  launched from inside it.
- **Verify a link by loading the page**, never by curling `/__cad/asset` —
  that route serves raw files; generated entries render through a
  different route, so probing it 404s whether or not anything is wrong.
- **Vite's transform cache can outlive HMR and hard reloads.** If a source
  edit does not show up, restart the dev server and delete
  `node_modules/.vite`.

## The shape of the app

```
src/client/ # React app: CadWorkspace (state root), CadViewer (scene +
            #   effects application), workbench/ (tabs, sections, session
            #   state, playback), render/ (viewport)
scripts/    # app tooling incl. selfContained.test.mjs
            #   (the boundary fence), the dev-backend spawn helpers, and
            #   the DOM-free React harness and module hooks that component
            #   and hook tests render the client through
docs/       # subsystem docs — the map below
dist/       # built client (gitignored); what `cadgen viewer` serves in a
            #   checkout and what the wheel bundles
```

### The subsystem docs

| Document | What it settles | Read it before |
|---|---|---|
| [docs/settings-ui.md](docs/settings-ui.md) | The CURATED design-system reference: anatomy, tokens, type scale, row kinds, states, the new-row checklist | touching any settings control — this one is BINDING |
| [docs/render-types.md](docs/render-types.md) | The capability registry and the render-backend contract: viewer code asks what a format CAN DO, never what it IS | any change that touches more than one file format |
| [docs/render-mode.md](docs/render-mode.md) | Appearance persistence, Display vs Render ownership, the Studio editor, quality constants, depth/zoom, the Materials tab | changing a mode, a control, or a quality number |
| [docs/lod.md](docs/lod.md) | Progressive detail: admission, memory budgets, the replacement batch and its receipts, and the live-edit feed | changing what the viewport loads, refines, or shows while a build runs |
| [docs/storage.md](docs/storage.md) | The four browser persistence tiers and the closed per-file slice set | adding any state that has to survive a reload |
| [docs/backend.md](docs/backend.md) | The HTTP contract the client may assume: routes, the two browser gates, containment, the tessellation cache | changing a request the client makes |

## Testing

```bash
npm run test    # client + app tooling (node:test, beside the code)
```

The backend's suite lives with cadgen and is not collected here; running only
`npm run test` leaves that half unchecked.

Headless UI verification uses Playwright with `--use-angle=metal` —
the default software WebGL renderer is not what users see.

### The browser gate

The repository's browser gate (`test-viewer-browser.sh`, under its test
scripts) drives the BUILT Viewer in a real Chromium against fixtures it
generates itself. It comes in two sizes:

- `--ci` — about 2 minutes: format, pick, kinematics, camera.
- no flag — about 4 minutes: every gate.
- `--only <gate>` — one gate while working on it.

`--ci` is the subset that is safe to automate: it opens one file per load path
(STEP package, mesh, drawing, robot), picks a face and toggles it, drives a
joint five ways, and switches viewing mode. Nothing in it reads a frame rate or
sleeps toward a conclusion — every assertion settles on state the app publishes,
so a slower runner is slower, not redder.

The rest stays manual, because it reads pixels in ways a software rasterizer
will not reproduce: `picking` brute-force-clicks for a pixel on the silhouette
(~26 probes at the 700 ms activation window, the most expensive gate here) and
scores edge-highlight fragmentation pixel by pixel; `scene` compares mean
luminance between appearance presets and between the Inspect grid and the Render
floor. `quality` is deterministic and is the first gate to promote if the budget
grows; it is out only on cost.

Both sizes print `[setup] Ns` and `[gate NAME] Ns`, so a run that got slower
says where.

## Kinematics

Every model with poses gets the same tab, under the same name, whichever file it
came from: a STEP model's mates and a robot's joints are one control to the
person using them. It holds three subsections, top to bottom. POSE is the
model's named configurations as a dropdown. VALUES is one row per DOF, with Reset
and Copy at its foot. TRANSITION is how the model travels between poses. Pose and
Transition render only for a file that declares poses, so a plain URDF opens
straight onto its values.

Applying a pose is a MOTION, not a write: the mechanism travels to it over
`poseTransition.js`'s tween, because reading a mechanism means watching which DOF
turns which way. Both sheets ease the same way — the curve is
`easeUrdfJointAnimation`, taken from the robot module rather than restated, so
one pose change cannot feel unlike another. Animate and Speed are a viewer
preference rather than a per-file setting, since someone who wants the snap wants
it in every file, and OFF writes the target values in the same frame rather than
transitioning quickly. Speed is hidden while Animate is off, not greyed: a
control that cannot apply is better gone than present and refusing.

## Robot components

URDF, SRDF, and SDF files with named objects in their linked meshes expose a
Components tab beside Kinematics. A robot sheet opens on KINEMATICS — posing the
robot is what the file is for — and selecting a component jumps to Components.

Components is a tree with the STEP tree's look: a row per link, collapsed, with
the count of objects it owns; expanding one lists its objects beneath it. Links
start collapsed because a real robot's inventory is long (a corpus arm is 78
objects across 8 links, 51 under one of them) and the first question is which
links exist. Selecting a row highlights that mesh object in the viewport;
picking it in the viewport selects it, expands its link and scrolls to its row.
Ctrl/Cmd/Shift-click toggles additional components. Objects retain their visual
transforms as joints move. Unnamed objects remain rendered but are omitted from
the inventory; a file without named objects has no Components tab.

**Components is an Inspect affordance.** The per-object split happens only while
the Render session is off, so Render keeps the per-visual geometry a robot has
always had: its photographic scene receives no component selection, and the
Materials tab's targets stay the robot's visuals rather than the objects inside
them. A mesh object whose loader ranges do not describe a slice of its visual is
reported once on the console and leaves that visual whole — it contributes no
component rows, and the robot renders unchanged.

A selected component's FACTS sit at the foot of the Components tab, not in a tab
of their own: they are about the row just clicked, and a tab for them would stand
empty whenever nothing was selected. Colour, link, triangle and vertex counts,
and the object's size on the robot in millimetres — its mesh-space box scaled by
the visual's transform, since a link mesh keeps its own file's units and the
`<mesh scale>` lives in that transform. Colour leads because a cadgen mesh export
groups objects BY colour, so it is what tells two rows of one link apart.

There is no reference string to copy. There was one, a locator of the form
`robot.urdf#link=arm&visual=...&object=...`, and nothing anywhere parses it: no
CLI and no skill accepts that grammar, so copying it led nowhere. If robot
components ever need a locator, it should be the shape STEP already uses
(`file#selector`) and it should ship with the door that reads it.
`visual` is the parsed visual ID (`<link>:v<one-based visual ordinal>` for URDF);
`object` is the mesh loader's object ID and `index` its zero-based position in the
loaded mesh's parts list. `name` preserves the authored object name. Resolve the
link and visual in the robot description to find the mesh file, then identify
that mesh object using its name and index. Repeated mesh instances have distinct
references because they belong to different visuals. SRDF locators name the SRDF
file and resolve visuals through its paired URDF. SDF uses its parsed visual IDs.
These locators describe mesh objects for prompts; they are not STEP face selectors
and are not accepted by the STEP selector CLI. They remain stable across pose
changes, but reordering visuals or re-exporting a mesh can change the identifiers.
