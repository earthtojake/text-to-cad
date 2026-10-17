# Loading, memory, and live updates

What the viewport does in the background between "a file was selected" and
"the picture has settled": which mesh each part is drawn at, how a large
assembly arrives, what it refuses when memory runs short, and how it follows a
model that is being rebuilt while you watch.

All of it is the STEP package path of the STEP renderer. A triangle mesh (STL, 3MF) and a
GLB are drawn as they are: their renderers load the file whole, parse it once per revision
(an STL in a worker) and keep the decode cached, so reopening one fetches and parses nothing
(see [Mesh renderer](cad-renderer.md#mesh-renderer)).

The observable promises are in [the web app README](../../../apps/web/README.md#the-laws-that-bind-the-app);
this file is the mechanism behind them. None of it may change **exact**
geometry, measurements or explicit mesh-export tolerances.

| § | Covers |
|---|---|
| [1](#1-the-display-mesh) | The one mesh every part is drawn at, stored and produced meshes |
| [2](#2-progressive-loading) | Batches, the one STEP scene, framing, accelerators |
| [3](#3-admission-and-memory) | Budgets, reservations, what cannot fit |
| [4](#4-failure-and-cleanup) | A scene that fails to build, ownership |
| [5](#5-following-an-active-build) | The edit feed, what the viewport shows, the status heartbeat |

## 1. The display mesh

Every STEP part is drawn at cadgen's display tolerance (`cadgen.tessellation_policy`),
and only at it: it opens there and stays there, whatever the camera, the size of
its assembly or the memory left. The tolerance is cadgen's alone; the page never
names one. Each component of a view names its **part** (`part` in `assembly.json`),
and the part's record names the display mesh the page reads to draw it
(`partRow`, `@text-to-cad/core/lib/parts/tessellationCache.js`).

Every mesh the viewer draws is cadgen's (OCCT's triangulation of the exact BREP,
every face of it verified and where needed repaired by cadgen's native library,
stored by cadgen, derived by the build pool for the build that made the model
before it reported done); the browser never tessellates. A part is named by the construction that
made its component (its key, cadgen's `STORE.md` §2), not its bytes, and a saved
file is the result it was written from wherever the file holds it, so a build's
preview revision (§5) shares its parts with the saved file that follows it. The parts' records are probed a chunk
of components at a time and their meshes read a batch at a time
(`createInitialDisplayPlans` in `renderers/step/render/initialDisplay.js`,
`packageBatchReads.js`), the first of each the size of the first publish, so the
first geometry waits on no more than it draws. A component whose part the probe
does not find is asked for in the `/__cad/parts` request, whose ready row
carries the part's record, which the component then reads like a stored one;
a part the store lacks altogether (a cleared or evicted store) is derived by one
cadgen build-pool job for the request, the loading screen saying it is meshing
parts meanwhile. Both are
admitted by what their part's record says the stored body and its decode cost
(`glb.byteLength + glb.decodedBytes`); one above the concurrent decode cap runs
alone only when the shared Viewer memory envelope can reserve all of it.

Preview draws the scene one quality tier up (`kit/viewport/renderProfile.js`: pixel
ratio, shadow and environment maps) at the same meshes. The chrome does not report
loading progress beyond its overlay: the STEP renderer records first geometry and
the whole model for benchmark harnesses only (`window.__cadViewerLoad`,
`useViewportLoadStatus`), and background file writing stays quiet.

## 2. Progressive loading

Components load with bounded concurrency and publish in batches whose ceilings
double from the first to the last (`packageProgressiveLoad.js`), so the model
paints while it loads and a cancel frees what was never published. The load order
puts the model's extreme-placed components first, so the first batch already
spans the model on screen.

Every publication lands in the ONE STEP scene the viewport adopted
(`renderers/step/scene/stepScene.js`): while the structural build key holds for the
same model, the live build reconciles its records in place, and the viewport is
told the scene changed (`viewport.commitScene()`) rather than handed a new scene —
so a progressive open never re-dresses every material or re-adopts anything.
Publishes share unchanged occurrence rows and tree metadata; placement,
appearance and changed bounds still update their records. The camera frames the
model once, on its first publish, on the box `assembly.json` declares for the
whole of it (`bbox`, carried as the composition's `declaredBounds`): the scene's
`restBounds` is that box from the start, so the framing, the orbit pivot, the zoom
ruler, Zoom to fit, preview's turntable and the ground's size are final before
most components have arrived, and later publishes move none of them. A descriptor
without a box leaves the scene `complete: false` until the last component is in:
it is framed on what arrived first and once more when it is whole, unless the
person has taken the camera by then.

Display raycast accelerators are requested only when a picking ray reaches
component bounds, then queued during idle time for one worker at a time.
Admission covers private input copies, worker scratch and the returned tree;
displayed arrays stay attached and unchanged. Releasing the last geometry owner
cancels its build, and stale results cannot attach to replacement geometry. The
first pick remains exact and may cost more on a dense component; merely loading
an assembly does not build an accelerator for every component. Inputs with a
separate merged face-selection proxy still build that proxy's accelerator on the
main thread during idle time. Canonical STEP selectors use the display meshes and
do not enter that separate path.

A closed tab keeps the complete package it showed (`render/completedPackageCache.js`,
bounded by count and bytes), so reopening it reads nothing; a same-file revision
reuses every component whose part it shares (`packageComponentReuse.js`).

## 3. Admission and memory

One ledger (`render/viewerMemoryPolicy.js`) accounts what the viewer owns or can
estimate: displayed arrays, selectors, BVHs, GPU uploads, asset caches, worker
heaps and a staged revision. A component's decode is admitted only when its
estimate fits the in-flight cap and the ledger can reserve it. Admission can
reclaim idle decode workers and the completed-package cache and retry while
preserving active consumers. Its ledger samples each live worker's own retained
estimate before admission, so a large component does not inflate every worker's
charge.

Display arrays shared with asset caches have one CPU charge for the entire
backing allocation, including unused sections of packed buffers. GPU charges
use uploaded view sizes; CPU-only edge inputs and picking allocations are
accounted for separately.

A component that cannot fit is not loaded: the ledger notes the limitation, the
load fails with its error, and the view stays up with what it drew. **Estimates
and sampled resource totals are a soft budget, not a hard browser RSS limit.**

## 4. Failure and cleanup

A scene sync that fails part way through an in-place reconciliation tears the
whole scene down (`render/sceneCleanup.js`) before it says so: it never
reconciles against already-disposed records. A cleanup that itself fails keeps
the scene reachable and its buffers charged until a real cleanup retry succeeds,
and the viewport says the scene could not be released.

## 5. Following an active build

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
replacement stages or fails. Reuse requires the same part; placements and
appearance come from the new tree. Selection, measurements and reference copying wait for matching
new geometry. A failed replacement preserves the view and reports its error;
only that file/hash stops retrying automatically. A first load that fails part
way keeps the parts it drew under its error. A STEP's articulation arrives with its
entry and its routines load on their own path; whether a pose outlives a replacement
is [Position's rule](cad-renderer.md#position), not the mesh load's. Snapshot source
isolation is unchanged.

**Overlapping loads.** Geometry and reference loads own their cancellation
independently; a superseded request cannot cancel its replacement. Topology
requests for one file revision union rather than supersede: a batch in flight
finishes, and one no longer wanted is simply not published.

**The preview, then the save.** As soon as the build's body has returned and its
parts are derived, the feed names the **preview revision** -- the result tree, the
part key of each of its components the store holds so far, and whether that is all
of them, cadgen's `STORE.md` §9b -- and the viewport draws it in place of the previous
model, labelled **Preview** where the update status sits (`ViewPreviewLabel`,
`load.currentPreview`): the wait for that build is over, though its write is not. The
preview is an entry read exactly as a saved file's catalog row is
(`workbench/previewRevision.js`, `hooks/usePreviewRevision.js`): its tree's view at
the client's `storeTreeUrl`, with the producer the feed named, and its parts by key --
so every component whose part is already drawn keeps its mesh and its row, whatever
its id in the new tree (`packageComponentReuse.js`), and a part the build has not
derived yet is waited for, never asked of cadgen, with what is named drawn meanwhile
(`createPreviewPartsGate`, the loader's `publishPending`). A build that could not name
its parts (no producer) has its view key them as for a saved file. The sidecar-driven
features work on a preview as on a saved file: the feed names the preview's
annotations -- the articulation, finishes and keyframes the build resolved against
the preview's tree, the data the sidecar will carry, keyed by the same tokens -- a
moment after its geometry, read with `previewAnnotations` and bound only when
resolved against the preview's tree. Position and the routines bind to them the moment
they are read; the finishes once the preview's geometry is on screen whole, since a
change of finishes reloads the composition. Until its own arrive, what the saved file
on screen had stays in hand by the tokens the two share, [Position's rule](cad-renderer.md#position)
for a replacement. A routine that bends a tube plays on a preview only as the one in
hand, with the saved document's skins; changed, it waits for the save. When the build
writes the file -- the feed's second event, `saved`, the tree the bytes were written
from and their digest, which lands after the result is recorded and may precede the
build's `done` -- the catalog is read at once (`useEditingPreview`) and names the saved
revision -- a revision past the one the build began over, which the feed does not call
superseded -- and it replaces the
preview in place with nothing fetched twice (the parts are the preview's, by key; a
routine is keyed by its keyframes, so a playing one is neither stopped nor rewound),
the label goes, and nothing on screen moves: no selection, measurement, ink or pose
is cleared by a preview replaced by its own save, since its refs are the same -- but on a
part the file does not verify as the result's, which the saved file names by its geometry
and the build warns of (STORE.md §3) -- where
any other change of tree clears what a revision clears today. A preview is never
presented as the file: no sidecar binds to it, the prompt resource and the live state
keep the saved file's revision (and say `preview`), snapshots and exports read the
saved file alone, and selection, measurements and reference copying resolve against
it as against any revision, by ref. Before the preview exists the model on screen
says it is updating. A failed build leaves what is on screen -- the labelled preview,
or the previous model -- under its alert, whose card says the preview is what is
shown; the preview goes when the file moves past the build (`superseded`), when the
daemon no longer lists it, or when a newer build names its own, and a build first
seen already done is the file on disk, never its preview. A save that lands while
the preview's own geometry is still loading cancels that load as any revision's
does, and probes the store for its parts again (their bodies are in hand).

**What the viewport shows.** The navbar carries no status. Opening and
updating are the viewport's loading overlay (`ViewerLoadingOverlay`). A failure is
a card over the viewport (`kit/status/ViewerAlertCard.jsx`) with its explanation,
its next step and the full diagnostic under Details: an error always shows, and a
failed update the model survives (`blocking: false`, the previous version still on
screen) has a Dismiss button and stays dismissed until the alert changes, or
clears and is raised again. A warning is a card too, one that can be dismissed
while the model is on screen: the card is the one place a problem is said. Once a
usable current view is displayed, saving, successful completion and idle
edit-feed state stay quiet. A sidecar this build cannot read raises
no alert: the model renders with no kinematics, no materials and no routine, and
the migration is announced where it can be acted on — the build and the cad
skill. Existing usable views remain visible during updates and failures.

**Opening.** Opening shows one step line — **Finding file**, **Importing
model** (cadgen compiling a file its store does not hold: reading it, then its
parts, counted), **Building model** (a model script running: every phase of its
build), **Reading model** (reading a model the store holds), **Meshing parts**
(cadgen deriving parts its store lacked: a cold open), **Loading geometry**
(reading stored meshes), **Preparing view**, or **Opening model** for a wait
with nothing more specific to say — with no headline above it; the loading mark itself says a
model is opening. Once the first parts are drawn, a cold open's remaining
meshing is the update line's "Meshing parts n/total…", not "Updating model…".
Counts measure
completed geometry items in the current stage, not assembly occurrences or an
overall ETA; uncounted stages are indeterminate. Render initialization uses the
same indicator against the destination backdrop until its first usable frame.
There is no elapsed-time clock: a long wait adds the step's detail line, and
interrupted progress explains that the viewer is waiting for a response before
offering recovery. Selection and edge preparation
report beside their controls, not as whole-model loading.
