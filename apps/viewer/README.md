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
  line-clamped away.
- **Geometry and display readiness are separate**: a `compiled` artifact owns
  a complete immutable geometry tree. Display may still be waiting for an
  exact surface derivation or tessellation. A validated warm tessellation can
  render directly from its immutable object binding; selectors and a cache
  miss resolve the pinned surface asynchronously without recompiling geometry.

## Appearance, Display, and Render

App appearance is a global **System / Light / Dark** preference. System follows
the live OS preference. A host-scoped `cad-viewer-appearance` cookie remembers
the choice across browser sessions and viewer ports; a localStorage mirror
notifies other tabs on the same origin and provides a fallback when cookies
are blocked. The synchronous startup script applies the preference before the
app mounts. The navbar shows the resolved Sun or Moon icon; System appears only
as a dropdown choice. Neutral light and charcoal panel tokens remain independent from
the model's lighting and materials.

**Display** owns the CAD inspection projection, style, edge visibility, grid,
origin axes, part colors, clipping, and exploded view. **Shaded with edges**
shows shaded surfaces with CAD edges; **Shaded** shows those surfaces without
edges. Inspect uses the same model lighting, materials, and dark edge colors in
light and dark appearance; only the canvas and guides adapt. Edge weights are
fixed by edge type. The grid is an on/off world reference; origin axes remain independently configurable.

The navbar's **Viewing mode** icon menu switches between **Inspect** and
**Render**, showing the active mode's cube or clapperboard icon. Inspect shows only
CAD inspection tabs and restores their saved split, order, and active selection unchanged.
Render enters an isolated photographic view with **Studio** first and active;
**Materials** follows for STEP models, including those without named materials, **Kinematics**
follows when it declares pose controls, and **Animation** follows when it
provides clips. The Render tabs start in
one row on each entry. Dragging and splitting them is temporary and never
overwrites the durable per-kind CAD arrangement. The default Light or Dark
studio follows global app appearance. Backdrop customizations remain local to the model session.
The rightmost navbar button opens **Fullscreen**, hiding panels and orbiting the
model. Escape or the floating toolbar’s **Exit fullscreen** button restores the previous layout.

The compact editor controls lens and exposure, softbox rotation, size and fill,
plus backdrop color, transparency, ground visibility and position. The translucent
ground stays at the model's original Z=0 plane by default; **Lowest point**
explicitly aligns the floor to the model without moving its geometry. Khronos PBR Neutral tone mapping and a generated
softbox environment provide the Render lighting. The overhead side key models
depth, while a rear fill retains detail on dark and polished surfaces. Defaults
are checked against colored assemblies, mechanical models, and material samples
in both studios. STEP package material properties remain intact. A direct GLB
with embedded animation retains its native hierarchy, skin/morph data, textures,
and PBR materials for playback; its Animation tab appears in both Inspect and
Render. A static direct GLB uses that native hierarchy in Render, retaining
textures and PBR materials, while Inspect uses its normalized base or vertex
color and opacity for CAD interaction. 3MF retains color, and STL has no authored color. Animated GLB
measurement is unavailable because the normalized triangle picks describe only
the rest pose. A bounded load-time animation sample estimates stable framing;
the camera, floor, and studio do not refit on every playback frame.
Backdrop-colored ground fill and a restrained diffuse response keep floor
shadows and the spotlight pool subtle without changing model illumination;
transparent backgrounds retain their shadow catcher. The existing toolbar owns
image capture.

Quality is independent of the studio. Normal CAD uses its Interactive policy;
Render offers **Preview** and **Final**, and defaults to Final. Preview and Final
share the tessellation ladder, cache entries, and memory budget. Preview uses
a 1-pixel screen-error target, 2048-pixel shadow maps, and a 256-pixel softbox
environment. Final requests a 0.25-pixel screen-error target, 4096-pixel shadow maps, and a 512-pixel softbox
environment. Quality changes refine the view without rebuilding exact CAD
geometry or the model scene. Entering Render creates an ordinary-depth WebGL
runtime so the photographic ground can receive shadows; returning to CAD restores
its wide-range logarithmic-depth runtime while decoded geometry stays cached.
Close-ups fit the depth range to visible rigid components when the camera enters
the assembly bounds, preserving fine layered details without changing lighting.
Optical zoom and cropped viewports also contribute to the detail target. The
filename badge reports Limited detail when memory limits prevent requested detail. Snapshots use the same policy:
Final selects the existing finest L3 STEP tessellation and 2× capture scale unless
an explicit output scale overrides it. CAD tessellation controls cannot be combined
with a photographic snapshot request.

Normal CAD settings and Render settings are separate per-model session state.
Entering Render applies its perspective camera and fixed presentation view
(shaded authored colors; guides, edges, clipping, exploded transforms, and
selection effects are off). Kinematics and animation remain available and
compose through the same model pose state used in Inspect. Returning to
CAD restores the CAD camera and inspection state; returning to Render restores
the photographic view.
Render zoom uses the subject's bounds for a stable pivot depth. Inspect zoom
anchors to the surface under the cursor, falling back to the model center.
Render pointer movement skips inspection hit tests and does not install CAD
raycast accelerators.
Mode changes keep the new canvas covered with the destination backdrop until
geometry and lighting have drawn their first frame. This transition owns no
second GPU scene and does not return during orbit or detail refinement. Render
does not receive inspection selectors or DXF bend-guide overlays; STEP and
embedded GLB animation remain independent of those inspection resources.
The Materials tab shows a compact parts list with each current assignment.
Click a part in the list or Render viewport (Shift-click for multiple), carry a
selection from Inspect, or Select all parts. Click an In this model swatch or
Preset to apply immediately; a preset creates and assigns its material together.
Undo restores the last local material change while this panel stays mounted.
A material's options menu can select every part using it. Color and surface
sliders stay behind Advanced settings. Shared editing remains explicit, with Make
unique for selection available before editing a shared material.
Part picking is enabled only while the STEP Materials tab is open; face/edge
selectors stay disabled. Appearance wrappers retain their geometry identity
for detail-adoption and disposal acknowledgments. Browser-tab material overlays
survive reload; authored revisions invalidate them, and bare STEP geometry
revisions do too. Reset authored clears local assignments and definitions.
These settings use sessionStorage with other per-model
ephemeral state; they are not written beside models, into the geometry cache,
or into global app appearance. A normal geometry rebuild preserves the
render setup. Closing the browser tab ends its session.

The top **Setup** section in Studio contains Quality. Reset sits at the bottom
of the tab and clears photographic customizations, restoring defaults for the
current global light/dark appearance while keeping the current camera pose.
The viewer has no studio preset selector or settings clipboard. Viewer and
snapshot commands resolve photographic scenes through the same cadgen-js
implementation; snapshots choose their studio and custom settings with `--render`.

## Launching

All commands run from this app's directory. Dev (Vite serves the client
from source with HMR; edits to `src/` and `packages/cadgen-js` show live):

```bash
npm run dev -- --host 127.0.0.1
# open http://127.0.0.1:5173/?file=<path relative to the served root>
```

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
back by mistake. A running server that detects either half changing refuses new
model-data requests and tells the browser to restart the Viewer; reloading that
page alone cannot update its imported Python code. In a checkout, a server that
finds `src/` beside the `dist/` it serves also warns once on stderr when any
source is newer than the build.

## Behaviours worth knowing before concluding something is broken

- The catalog fully resolves the selected file first and lists other files as
  navigation-only rows until one background scan finishes. Selecting one of those
  rows prioritizes its metadata immediately. Unchanged catalog rows and concurrent
  tree verification are reused; loading one model does not wait for every model.
- STEP entries always follow active edits, showing the root preview before its
  STEP save. The filename badge reports only **Opening**, **Updating**, **Open failed**,
  **Update failed**, **Limited detail**, or **Model warning**. Once a usable current view is displayed,
  saving, successful completion, idle edit-feed state and routine refinement stay quiet.
  Busy badges have a spinner; failures and detail limits have an icon and open their
  explanation on click. Tooltips explain the current stage or the effect on the view,
  distinguish a previous version from new geometry whose STEP write failed, and point
  to details when clickable. Stage counts never imply overall completion; full
  diagnostics remain in the dialog. Invalid saved settings produce a nonblocking model warning,
  with rebuild guidance and full diagnostics; geometry remains usable. Existing usable
  views remain visible during updates and failures.
  Opening uses one headline with **Finding file**, **Reading model**, **Loading geometry**,
  or **Preparing view** underneath. Counts measure completed geometry items in the current
  stage, not assembly occurrences or an overall ETA. Uncounted stages are indeterminate.
  Render initialization uses the same indicator against the destination backdrop until
  its first usable frame. Long waits show elapsed time; interrupted progress requests
  explain that the viewer is waiting for a response before offering recovery.
  Selection and edge preparation report beside their controls, not as whole-model loading.
  Run the model normally; existing decorators need no new imports. The daemon
  must be running for live updates. The prior model stays visible while the
  next request builds; failed updates remain visible while an idle disconnected feed retries quietly.
  Updates arrive through a held request that wakes when this output's build
  ledger changes. Unrelated jobs do not wake the tab. The server admits 32
  waiters independently of kernel workers; excess tabs retry every 500 ms.
  An idle heartbeat revalidates saved bytes and missing geometry;
  closing or switching the tab cancels the request. Overlapping geometry and
  reference loads own their cancellation independently; a superseded request cannot
  cancel its replacement. Older status responses cannot overwrite newer cached
  progress, and saved revisions are verified from one coherent file snapshot.
  Complete plain STEP assemblies also remain visible while replacement meshes
  load. Selection, measurements and reference copying wait for matching new
  geometry. A failed replacement preserves the view and reports its error;
  only that file/hash stops retrying automatically. STEP pose and animation metadata
  use their normal loading path, without a promise to retain the previous pose.
  Restarting the daemon expires the ephemeral session, and rerunning the model
  reconnects it. Source files hold authored changes; there is no hidden durable
  preview document. Every explicit model run still waits for declared outputs.
  A successful save leaves that revision's authored preview displayed without a status badge.
  A later successful no-op run without a new preview, or
  an expired preview with a validated saved result, uses the saved file instead.
  Complete displayed component arrays remain available while a replacement
  stages or fails. Reuse requires the same runtime surface input, concrete
  surface object and tessellation; placements and appearance come from the new
  tree. Snapshot source isolation is unchanged.
- Assemblies with at least 64 unique components can start at a coarser display
  tessellation when standard meshes are not cached. Cached standard meshes are
  preferred immediately, subject to their probed decode size and admission.
  Smaller assemblies start at the standard level, except an individually
  oversized component may start coarse. A component above the concurrent
  decode cap runs alone only when the shared Viewer memory envelope can reserve
  its complete estimate. Coarse geometry
  is a temporary preview: visible components automatically reach at least the
  standard level, preserving its angular smoothness even when projected chord
  error alone would permit a coarser mesh. Close inspection can request finer
  detail. The top bar distinguishes preview, refinement, standard detail and
  limited or failed refinement; background file writing stays quiet.
  Refinement uses the camera and disposable memory budget; exact geometry,
  measurements and explicit mesh-export tolerances remain unchanged.
  Static assemblies sample full transformed occurrence bounds against the camera
  frustum, refining a component when at least one occurrence is on screen.
  Offscreen components stay displayed. Ordinary camera sampling retains their
  existing detail; memory pressure can coarsen them before visible components.
  Unknown or not-yet-adopted bounds remain eligible.
  A stationary camera requests the final level implied by the existing
  hysteresis thresholds directly. If admission refuses that level, strictly
  intermediate levels can supply measured replacement sizes for another try.
  Failed loads stay parked; denied admission retries only after the displayed
  level or camera intent changes. Pressure-driven coarsening caps subsequent
  refinement until the camera or viewport changes, preventing upgrade/downgrade
  loops. Mesh-bound and clip-plane updates do not reset that cap. An idle
  scheduler reports memory-limited targets separately from settled quality.
  Scenes with joints, embedded animation, drawing poses or an active/collapsing
  exploded view keep conservative eligibility, including paused/disabled pose
  capabilities. Authored visibility and material flags are not LOD filters.
  Admission can reclaim idle tessellation workers and retry while preserving
  active consumers. Its ledger samples each live worker's own retained estimate
  before admission; a large component does not inflate every worker's charge.
  Refinement reserves both replacement arrays and worker scratch space, and
  includes the coarse tier's relaxed angular tolerance in its estimate.
  The scheduler holds at most four distinct replacement CIDs across loading,
  ready payloads and actual scene adoption. Its render and late-selector
  preparation share one loader lane, and only one atomic mesh/reference
  publication awaits adoption. The Viewer uses a 128 ms first-ready collection
  deadline so serialized cached reads can fill the four-component batch; it may
  publish a ready subset beside one unfinished carryover; it does not guarantee
  selector, worker or scene readiness. No fifth replacement starts. Admitted
  refinements keep filling the batch while exact sibling reservations allow it,
  even after the coarse pressure threshold is crossed; a denied reservation
  flushes the ready subset. Pressure coarsening remains singleton. Separate
  user-driven topology requests keep their existing worker admission and
  cache/picking accounting; they are not
  included in the scheduler's occupied-CID count.
  Actual payload backing allocations are reconciled before another sibling is
  admitted. Temporary sibling-capacity denials flush and retry after ownership
  changes; they do not permanently park a target. Displayed levels and measured
  current sizes remain unchanged until the complete exact batch adopts.
  Replacement admission stays held until the viewer adopts each current
  component payload at every occurrence and accounts for its scene ownership.
  This acknowledgment schedules rendering; it is not a GPU upload-completion
  fence. Modeled upload ownership remains separate. A superseding progressive
  publication can satisfy it only with the same context, revision, occurrence
  set and exact payload. Cancellation requests cleanup: switch, abort or unmount
  retains an outstanding reservation until actual replacement, restoration or
  complete disposal proves that the renderer has released its previous owner.
  Pending component maps remain separate from adopted maps. Display geometry
  and demanded selectors publish as one matching state pair, with commit receipts
  fencing abandoned or replayed React updates. A failed scene update clears its
  partial records before rebuilding the last adopted mesh/selector pair; it never
  reconciles against already-disposed records. Restoration preserves unrelated
  progressive components and completed selector loads. A second construction
  failure stops detail work and reports an error. Cleanup failure keeps ownership
  charged until a real cleanup retry succeeds. A cancelled batch that actually
  adopted remains a displayed payload owner even though its scheduler levels
  are not promoted, so cancellation does not evict its exact cache entries.
  Diagnostic snapshots identify scheduler-only ownership, batch sizes and seal
  reasons. The internal size-one control uses the same admission/publication
  path as groups of four.
  A static component publication can reuse the main adoption's completed reset
  only in that same React render. Later visual or clipping changes still run
  normally, as do transitions out of modules, animation, drawings or poses.
  Display arrays shared with asset caches have one CPU charge for the entire
  backing allocation, including unused sections of packed buffers. GPU charges
  use uploaded view sizes; CPU-only edge inputs and picking allocations remain
  accounted for separately. Topology-only
  interactions also release idle workers after their sibling requests drain.
  Display raycast accelerators are requested only when a picking ray reaches
  component bounds, then queued during idle time for one worker at a time.
  Admission covers private input copies, worker scratch and the returned tree;
  displayed arrays stay attached and unchanged. Releasing the last geometry
  owner cancels its build, and stale results cannot attach to replacement
  geometry. The first pick remains exact and may cost more on a dense component;
  merely loading or refining an assembly does not build an accelerator for every
  component. Inputs with a separate merged face-selection proxy still build
  that proxy's accelerator on the main thread during idle time. Canonical STEP
  selectors use the display meshes and do not enter that separate path.
  Progressive display and later detail swaps share unchanged occurrence rows
  and tree metadata; changing tessellation alone does not rebuild every tree
  leaf. Placement, appearance and changed bounds still update their records.
  Selection pruning preserves unchanged selected, referenced and hidden ID
  arrays, preventing detail publications from retaining historical workspace
  render contexts through unnecessary selection updates.
  A component that cannot fit even at the coarse level
  reports a limitation and preserves the current view. Estimates and sampled
  resource totals are a soft budget, not a hard browser RSS limit.
- A schema-9 STEP sidecar includes the STEP byte digest. A mismatch displays
  **Annotations unavailable** while permitting saved geometry to render.
  Rebuild or re-annotate the pair to repair it; importing a file never rewrites
  its authored sidecar.

- **The catalog scan skips dot-directories.** A buildable entry under
  `.review/` (or any dotted path) never appears, even when the server is
  launched from inside it.
- **Verify a link by loading the page**, never by curling `/__cad/asset` —
  that route serves raw files; generated entries render through a
  different route, so probing it 404s whether or not anything is wrong.
- **Vite's transform cache can outlive HMR and hard reloads.** If a source
  edit does not show up, restart the dev server and delete
  `node_modules/.vite`.
- Never invoke the export routes from automation — they open native save-as
  dialogs.

## The shape of the app

```
src/client/ # React app: CadWorkspace (state root), CadViewer (scene +
            #   effects application), workbench/ (tabs, sections, session
            #   state, playback), render/ (viewport)
scripts/    # app tooling incl. selfContained.test.mjs
            #   (the boundary fence) and the dev-backend spawn helpers
docs/       # subsystem docs; settings-ui.md is the CURATED design-system
            #   reference for all settings UI work — binding, read it
            #   before touching controls
dist/       # built client (gitignored); what `cadgen viewer` serves in a
            #   checkout and what the wheel bundles
```

## Testing

```bash
npm run test    # client + app tooling (node:test, beside the code)
```

The backend's suite lives with cadgen and is not collected here; running only
`npm run test` leaves that half unchecked.

Headless UI verification uses Playwright with `--use-angle=metal` —
the default software WebGL renderer is not what users see.
