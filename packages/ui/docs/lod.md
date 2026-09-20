# Level of detail, memory, and live updates

What the viewport does in the background between "a file was selected" and
"the picture has settled": which tessellation it starts from, how it refines,
what it refuses under memory pressure, and how it follows a model that is
being rebuilt while you watch.

The observable promises are in [the app README](../README.md#the-laws-that-bind-the-app);
this file is the mechanism behind them. None of it may change **exact**
geometry, measurements or explicit mesh-export tolerances — detail is a
display concern only.

| § | Covers |
|---|---|
| [1](#1-where-a-model-starts) | Coarse-first admission, cached standard meshes |
| [2](#2-what-refinement-samples) | Camera sampling, offscreen components, hysteresis |
| [3](#3-admission-and-memory-pressure) | Budgets, reservations, coarsening caps |
| [4](#4-the-replacement-batch) | CID caps, the first-ready deadline, adoption receipts |
| [5](#5-cancellation-failure-and-cleanup) | Parked targets, restoration, ownership |
| [6](#6-following-an-active-build) | The edit feed, badges, the status heartbeat |

## 1. Where a model starts

Assemblies with at least 64 unique components can start at a coarser display
tessellation when standard meshes are not cached. Cached standard meshes are
preferred immediately, subject to their probed decode size and admission.
Smaller assemblies start at the standard level, except that an individually
oversized component may start coarse. A component above the concurrent decode
cap runs alone only when the shared Viewer memory envelope can reserve its
complete estimate.

Coarse geometry is a temporary preview: visible components automatically reach
at least the standard level, preserving its angular smoothness even when
projected chord error alone would permit a coarser mesh. Close inspection can
request finer detail. The top bar distinguishes preview, refinement, standard
detail, and limited or failed refinement; background file writing stays quiet.

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

Scenes with joints, embedded animation, drawing poses or an active/collapsing
exploded view keep conservative eligibility, including paused or disabled pose
capabilities. Authored visibility and material flags are not LOD filters.

## 3. Admission and memory pressure

Failed loads stay parked; denied admission retries only after the displayed
level or camera intent changes. Pressure-driven coarsening caps subsequent
refinement until the camera or viewport changes, preventing upgrade/downgrade
loops. Mesh-bound and clip-plane updates do not reset that cap. Pressure
coarsening remains singleton.

Admission can reclaim idle tessellation workers and retry while preserving
active consumers. Its ledger samples each live worker's own retained estimate
before admission, so a large component does not inflate every worker's charge.
Refinement reserves both replacement arrays and worker scratch space, and
includes the coarse tier's relaxed angular tolerance in its estimate.

Display arrays shared with asset caches have one CPU charge for the entire
backing allocation, including unused sections of packed buffers. GPU charges
use uploaded view sizes; CPU-only edge inputs and picking allocations are
accounted for separately.

A component that cannot fit even at the coarse level reports a limitation and
preserves the current view. **Estimates and sampled resource totals are a soft
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
500 ms. An idle heartbeat revalidates saved bytes and missing geometry; closing
or switching the tab cancels the request. Older status responses cannot
overwrite newer cached progress, and saved revisions are verified from one
coherent file snapshot. Restarting the daemon expires the ephemeral session,
and rerunning the model reconnects it.

**What stays on screen.** The prior model stays visible while the next request
builds; failed updates remain visible while an idle disconnected feed retries
quietly. Complete plain STEP assemblies also remain visible while replacement
meshes load. Complete displayed component arrays remain available while a
replacement stages or fails. Reuse requires the same runtime surface input,
concrete surface object and tessellation; placements and appearance come from
the new tree. Selection, measurements and reference copying wait for matching
new geometry. A failed replacement preserves the view and reports its error;
only that file/hash stops retrying automatically. STEP pose and animation
metadata use their normal loading path, without a promise to retain the
previous pose. Snapshot source isolation is unchanged.

**Overlapping loads.** Geometry and reference loads own their cancellation
independently; a superseded request cannot cancel its replacement.

**After a save.** Source files hold the authored changes; there is no hidden
durable preview document, and every explicit model run still waits for its
declared outputs. A successful save leaves that revision's authored preview
displayed without a status badge. A later successful no-op run without a new
preview, or an expired preview with a validated saved result, uses the saved
file instead.

**Badges.** The filename badge reports only **Opening**, **Updating**, **Open
failed**, **Update failed**, **Limited detail**, or **Model warning**. Once a
usable current view is displayed, saving, successful completion, idle edit-feed
state and routine refinement stay quiet. Busy badges have a spinner; failures
and detail limits have an icon and open their explanation on click. Tooltips
explain the current stage or the effect on the view, distinguish a previous
version from new geometry whose STEP write failed, and point to details when
clickable; stage counts never imply overall completion, and full diagnostics
remain in the dialog. Invalid
saved settings produce a nonblocking model warning, with rebuild guidance and
full diagnostics; geometry remains usable. Existing usable views remain visible
during updates and failures.

**Opening.** Opening shows one step line — **Finding file**, **Reading
model**, **Loading geometry**, or **Preparing view** — with no headline above
it; the loading mark itself says a model is opening. Counts measure
completed geometry items in the current stage, not assembly occurrences or an
overall ETA; uncounted stages are indeterminate. Render initialization uses the
same indicator against the destination backdrop until its first usable frame.
Long waits show elapsed time; interrupted progress explains that the viewer is
waiting for a response before offering recovery. Selection and edge preparation
report beside their controls, not as whole-model loading.
