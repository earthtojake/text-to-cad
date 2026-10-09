# Level of detail, memory, and live updates

What the viewport does in the background between "a file was selected" and
"the picture has settled": which tessellation it starts from, how it refines,
what it refuses under memory pressure, and how it follows a model that is
being rebuilt while you watch.

All of it is the STEP package path of the STEP renderer. A triangle mesh (STL, 3MF) and a
GLB have no levels: their renderers load the file whole, parse it once per revision (an
STL in a worker) and keep the decode cached, so reopening one fetches and parses nothing
(see [Mesh renderer](cad-renderer.md#mesh-renderer)).

The observable promises are in [the web app README](../../../apps/web/README.md#the-laws-that-bind-the-app);
this file is the mechanism behind them. None of it may change **exact**
geometry, measurements or explicit mesh-export tolerances — detail is a
display concern only.

| § | Covers |
|---|---|
| [1](#1-where-a-model-starts) | The standard opening level, stored and produced meshes |
| [2](#2-what-refinement-samples) | Camera sampling, offscreen components, hysteresis |
| [3](#3-admission-and-memory-pressure) | Budgets, reservations, coarsening caps |
| [4](#4-the-replacement-batch) | CID caps, the first-ready deadline, adoption receipts |
| [5](#5-cancellation-failure-and-cleanup) | Parked targets, restoration, ownership |
| [6](#6-following-an-active-build) | The edit feed, what the viewport shows, the status heartbeat |

## 1. Where a model starts

The rungs are cadgen's (`cadgen.tessellation_policy`): which levels exist, the
chord and angle tolerances each means and which one a model opens at arrive with
the server's description -- the CAD Viewer's server info, the CAD app's launch --
and the host installs them before a STEP model is drawn
(`installTessellationLadder`, `@text-to-cad/core/lib/surf/lodPolicy.js`). The
viewport only picks a rung from its camera, with the hysteresis of §2; every mesh
request and cache key names both tolerances of the rung it asks for, and one that
names fewer is refused, never filled in (`tessellationQuality`,
`@text-to-cad/core/lib/surf/tessellationCache.js`).

Every mesh the viewer draws is cadgen's (OCCT's mesh of the exact BREP, stored
by cadgen); the browser never tessellates. Every component opens at the
standard level, whatever the size of its assembly
(`renderers/step/render/initialDisplayLod.js`). The standard tier is probed a
chunk of components at a time and the stored bodies read a batch at a time
(`createInitialDisplayPlans`, `packageBatchReads.js`), the first of each the
size of the first publish, so the first geometry waits on no more than it
draws. A component the store holds no standard mesh for names the standard
tier in the `/__cad/surfaces` request that derives its surface: cadgen meshes
it in the same job, and the row carries the mesh's probe row, which the
component then reads like a stored one. Both are sized by the stored body
before their decode is admitted; one above the concurrent decode cap runs
alone only when the shared Viewer memory envelope can reserve its complete
estimate.

There is no coarse opening tier. It earned its place when the browser
tessellated: a coarse first pass painted a large assembly sooner. cadgen's
standard meshes are light, and a cold component waits on its surface either
way, so a coarse first mesh would only cost each component a second mesh job
and the store a second entry. The coarse tier is memory pressure's (§3).

Visible components stay at least at the standard level, preserving its angular
smoothness even when projected chord error alone would permit a coarser mesh. Close inspection can
request finer detail, and so does preview, which the STEP renderer draws one
scene-quality tier up (`kit/viewport/renderProfile.js`) without changing the Display
setting. The chrome does not report detail levels: the STEP renderer
records first geometry and standard detail for benchmark harnesses only
(`window.__cadViewerQuality`, `useViewportQualityStatus`), and background file
writing stays quiet. That record lives in the STEP surface, so it takes a scheduler
snapshot only when the status it derives would change (`lodSnapshotStatusKey`): a
preview orbit resamples the camera on every frame, and a snapshot per frame would
re-render the whole surface per frame — while a model streams in, redoing the
partial model's derived state each time.

## 2. What refinement samples

Refinement uses the camera and the disposable memory budget.

Static assemblies sample full transformed occurrence bounds against the camera
frustum, refining a component when at least one occurrence is on screen.
Offscreen components stay displayed: ordinary camera sampling retains their
existing detail, and memory pressure can coarsen them before visible
components. Unknown or not-yet-adopted bounds remain eligible.

A stationary camera requests the final level implied by the existing hysteresis
thresholds directly. If admission refuses that level, strictly intermediate
levels can supply measured replacement sizes for another try.

**Resampling a motionless viewport is not work.** A sample carrying the same
camera, viewport and per-component distances, visibility and selection neither
restarts the settle debounce nor republishes status, so a viewport nobody is
touching reaches settled quality and stays there. An idle scheduler reports
memory-limited targets separately from settled quality. Camera and distance
comparisons ignore floating-point noise at a 1e-10 relative tolerance, measured
against the last meaningful sample so accumulated movement still triggers work.
Visibility, selection, quality changes and explicit retries remain meaningful.

Scenes with joints, animation clips, drawing poses or an active/collapsing
exploded view keep conservative eligibility, including paused or disabled pose
capabilities. Authored visibility and material flags are not LOD filters.

## 3. Admission and memory pressure

Failed loads stay parked; denied admission retries only after the displayed
level or camera intent changes. Pressure-driven coarsening caps subsequent
refinement until the camera or viewport changes, preventing upgrade/downgrade
loops. Mesh-bound and clip-plane updates do not reset that cap. Pressure
coarsening remains singleton.

Admission can reclaim idle decode workers and retry while preserving
active consumers. Its ledger samples each live worker's own retained estimate
before admission, so a large component does not inflate every worker's charge.
Refinement reserves both replacement arrays and worker scratch space, and
includes the coarse tier's relaxed angular tolerance in its estimate.

Display arrays shared with asset caches have one CPU charge for the entire
backing allocation, including unused sections of packed buffers. GPU charges
use uploaded view sizes; CPU-only edge inputs and picking allocations are
accounted for separately.

A component that cannot fit (at open, its standard mesh; under pressure, even
the coarse level) reports a limitation and preserves the current view. **Estimates and sampled resource totals are a soft
budget, not a hard browser RSS limit.**

## 4. The replacement batch

The scheduler holds at most four distinct replacement CIDs across loading,
ready payloads and actual scene adoption. Its render and late-selector
preparation share one loader lane, and only one atomic mesh/reference
publication awaits adoption.

The Viewer uses a 128 ms first-ready collection deadline so serialized cached
reads can fill the four-component batch. It may publish a ready subset beside
one unfinished carryover; it does not guarantee selector, worker or scene
readiness. No fifth replacement starts. Admitted refinements keep filling the
batch while exact sibling reservations allow it, even after the coarse pressure
threshold is crossed; a denied reservation flushes the ready subset.

Separate user-driven topology requests keep their existing worker admission and
cache/picking accounting; they are not included in the scheduler's occupied-CID
count. Topology-only interactions also release idle workers after their sibling
requests drain.

Actual payload backing allocations are reconciled before another sibling is
admitted. Temporary sibling-capacity denials flush and retry after ownership
changes; they do not permanently park a target. Displayed levels and measured
current sizes remain unchanged until the complete exact batch adopts.

**Adoption receipts.** Replacement admission stays held until the viewer adopts
each current component payload at every occurrence and accounts for its scene
ownership. This acknowledgment schedules rendering; it is not a GPU
upload-completion fence, and modeled upload ownership remains separate. A
superseding progressive publication can satisfy it only with the same context,
revision, occurrence set and exact payload. Display geometry and demanded
selectors publish as one matching state pair, with commit receipts fencing
abandoned or replayed React updates.

Every publication lands in the ONE STEP scene the viewport adopted
(`renderers/step/scene/stepScene.js`): while the structural build key holds for
the same model, the live build reconciles its records in place, and the viewport
is told the scene changed (`viewport.commitScene()`) rather than handed a new
scene — so a progressive open or a detail swap never re-dresses every material or
re-adopts anything. The camera frames the model once, on its first publish, on
the box `assembly.json` declares for the whole of it (`bbox`, carried as the
composition's `declaredBounds`): the scene's `restBounds` is that box from the
start, so the framing, the orbit pivot, the zoom ruler, Zoom to fit, preview's
turntable and the ground's size are final before most components have arrived,
and later publishes move none of them. A descriptor without a box leaves the
scene `complete: false` until the last component is in: it is framed on what
arrived first and once more when it is whole, unless the person has taken the
camera by then. The camera sample that drives all of this is taken when the
viewport says the camera settled (`onCameraSettled`: a move, a preview orbit, or
a resize, which can expose a part without moving the camera) and when the
selection changes.

A static component publication can reuse the main adoption's completed reset
only in that same React render. Later visual or clipping changes still run
normally, as do transitions out of modules, animation, drawings or poses.

Progressive display and later detail swaps share unchanged occurrence rows and
tree metadata; changing tessellation alone does not rebuild every tree leaf.
Placement, appearance and changed bounds still update their records. Selection
pruning preserves unchanged selected, referenced and hidden ID arrays,
preventing detail publications from retaining historical workspace render
contexts through unnecessary selection updates.

Display raycast accelerators are requested only when a picking ray reaches
component bounds, then queued during idle time for one worker at a time.
Admission covers private input copies, worker scratch and the returned tree;
displayed arrays stay attached and unchanged. Releasing the last geometry owner
cancels its build, and stale results cannot attach to replacement geometry. The
first pick remains exact and may cost more on a dense component; merely loading
or refining an assembly does not build an accelerator for every component.
Inputs with a separate merged face-selection proxy still build that proxy's
accelerator on the main thread during idle time. Canonical STEP selectors use
the display meshes and do not enter that separate path.

Diagnostic snapshots identify scheduler-only ownership, batch sizes and seal
reasons. The internal size-one control uses the same admission/publication path
as groups of four.

## 5. Cancellation, failure and cleanup

Cancellation requests cleanup: switch, abort or unmount retains an outstanding
reservation until actual replacement, restoration or complete disposal proves
that the renderer has released its previous owner. Pending component maps
remain separate from adopted maps.

A failed scene update clears its partial records before rebuilding the last
adopted mesh/selector pair; it never reconciles against already-disposed
records. Restoration preserves unrelated progressive components and completed
selector loads. A second construction failure stops detail work and reports an
error. Cleanup failure keeps ownership charged until a real cleanup retry
succeeds.

A cancelled batch that actually adopted remains a displayed payload owner even
though its scheduler levels are not promoted, so cancellation does not evict
its exact cache entries.

## 6. Following an active build

STEP entries always follow active edits, showing the root preview before its
STEP save. Run the model normally; existing decorators need no new imports, and
the daemon must be running for live updates.

**The feed.** Updates arrive through a held request that wakes when this
output's build ledger changes. Unrelated jobs do not wake the tab. The server
admits 32 waiters independently of kernel workers; excess tabs retry every
500 ms. A server that answers at once instead (a host relaying requests through a
few slots all its views share, where a held request would take one) is paced by the feed: an answer
with nothing new waits out the rest of a second, and news is asked after again
within a tenth of one. An idle heartbeat revalidates saved bytes and missing geometry; closing
or switching the tab cancels the request. Older status responses cannot
overwrite newer cached progress, and saved revisions are verified from one
coherent file snapshot. Restarting the daemon expires the ephemeral session,
and rerunning the model reconnects it.

**What stays on screen.** The prior model stays visible while the next request
builds; failed updates remain visible while an idle disconnected feed retries
quietly. A complete model of the same file — a part's or an assembly's — also
remains visible while its rewritten file is rebuilt and while the replacement
meshes load (`replacingSameFileMesh`, `awaitingSameFileRevision`), reported as an
update ("Updating model…"), never as the loading screen — also when edits come
faster than revisions load, and one revision's load is cancelled for the next
(`meshStateAfterCancelledLoad`). Complete displayed component arrays remain available while a
replacement stages or fails. Reuse requires the same runtime surface input,
concrete surface object and tessellation; placements and appearance come from
the new tree. Selection, measurements and reference copying wait for matching
new geometry. A failed replacement preserves the view and reports its error;
only that file/hash stops retrying automatically. A first load that fails part
way keeps the parts it drew under its error, and refinement goes on over them: a
detail swap changes geometry only, never whether the load finished or failed
(`detailSwapMeshState`). STEP pose and animation
metadata use their normal loading path, without a promise to retain the
previous pose. Snapshot source isolation is unchanged.

**Overlapping loads.** Geometry and reference loads own their cancellation
independently; a superseded request cannot cancel its replacement. Topology
requests for one file revision union rather than supersede: a batch in flight
finishes, and one no longer wanted is simply not published.

**After a save.** The view shows the saved file. When a build writes it, the new
revision replaces the one on screen in place, keeping every component whose identity
it shares; while the build runs the model on screen says it is updating, and a failed
build leaves it on screen under its alert.

**What the viewport shows.** The navbar carries no status. Opening and
updating are the viewport's loading overlay (`ViewerLoadingOverlay`). A failure is
a card over the viewport (`kit/status/ViewerAlertCard.jsx`) with its explanation,
its next step and the full diagnostic under Details: an error always shows, and a
failed update the model survives (`blocking: false`, the previous version still on
screen) has a Dismiss button and stays dismissed until the alert changes, or
clears and is raised again. A warning is a card too, one that can be dismissed
while the model is on screen: the card is the one place a problem is said. Once a
usable current view is displayed, saving, successful completion, idle edit-feed
state and routine refinement stay quiet. A sidecar this build cannot read raises
no alert: the model renders with no kinematics, no materials and no routine, and
the migration is announced where it can be acted on — the build and the cad
skill. Existing usable views remain visible during updates and failures.

**Opening.** Opening shows one step line — **Finding file**, **Importing
model** (cadgen compiling a file its store does not hold: reading it, then its
parts, counted), **Reading model**, **Meshing parts** (cadgen deriving parts its
store lacked: a cold open), **Loading geometry** (reading stored meshes), or
**Preparing view** — with no headline above it; the loading mark itself says a
model is opening. Once the first parts are drawn, a cold open's remaining
meshing is the update line's "Meshing parts n/total…", not "Updating model…".
Counts measure
completed geometry items in the current stage, not assembly occurrences or an
overall ETA; uncounted stages are indeterminate. Render initialization uses the
same indicator against the destination backdrop until its first usable frame.
Long waits show elapsed time; interrupted progress explains that the viewer is
waiting for a response before offering recovery. Selection and edge preparation
report beside their controls, not as whole-model loading.
