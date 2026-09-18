# Client-side STEP feature detection

Feature detection helps people navigate and select geometry in the shared Model
tree. It belongs to the CAD renderer in `@hardcore/ui`; web and desktop run the
same code. It reads saved geometry through the injected CAD resource service.
It never reads model source, writes artifacts or executes a CAD kernel.

Keep recognition independent of cadgen compilation, Python inspection and the
reference grammar. A recognized feature is a group of existing canonical faces
and edges, not a new kind of reference. Selecting or copying it uses the normal
occurrence-scoped reference and prompt-delivery flow. Feature labels and inferred
operations are not stable identities across document edits or recovered source
history. Recognition is optional: structural rows, rendering and part selection
must work without it.

## Demand and cancellation

1. Load the lightweight assembly descriptor to display the hierarchy.
2. The Model tree requests recognition for expanded, visible parts. Collapsed
   parts need no recognition or exact-surface request just to show their rows.
3. Resolve each requested occurrence to its component. Repeated instances share
   component analysis while retaining distinct selection IDs and placement.
4. Reuse completed recognition metadata when its exact geometry identity matches.
   Otherwise obtain the component's SURF data through the resource provider and
   analyze it in a disposable worker.
5. Publish the result, cache successful metadata, then process the next requested
   component. Each mounted inspector owns at most one active recognition worker.

Changing expansion updates the queue without restarting an active component that
is still requested. Switching between occurrences of that same component also
keeps its work. Removing the last requested occurrence cancels both pending
surface loading and worker work; queued components that are no longer requested
are skipped. Closing the inspector, changing geometry or resource scope, and
unmounting cancel the entire inspector's pending work. Cancelled jobs cannot
publish late results or populate the completed cache.

This is deliberately a sequential queue per inspector, not a global worker pool.
Completed results are reusable between mounts; pending jobs are not shared
between separate inspectors. Retry clears failed results and queues those
components again without cancelling other components that are still needed.

Loading is lazy **per component**: expanding a part analyzes that component as a
whole, not only the feature rows subsequently opened. Recognition neither expands
other parts nor blocks the initial structural tree. The stable top row counts
presented top-level features; it does not display global recognition progress.
Selection, isolation and reveal rules remain in the
[Model tree contract](cad-renderer.md#step-inspector-layout).

## Cache identity and lifetime

The completed cache key combines:

- The resource provider's root/generation scope.
- `MODELING_RECOGNITION_VERSION`.
- Exact surface input and object identities, or a provider-scoped immutable SURF
  URL for older static packages.

Do not key recognition by filename, display label or assembly occurrence. On a
warm reopen, accepted component identities can avoid surface requests altogether,
but only after root, provider generation, entry revision and runtime descriptor
match. Changed geometry or scope must never reuse the previous binding.

The least-recently-used cache holds at most **512 components / 8 MiB** of accounted
serialized metadata. Each read returns a private copy. It retains no SURF buffers,
workers, scene objects, pending promises or failed results. The active inspector
also retains its own results, including errors for explicit retry; disposing it
releases that local state. Large or evicted results may require recomputation.

This cache is **in memory**, separate from cadgen's persistent surface/mesh store
and host preference storage. Refreshing the page or restarting the app loses it.
There is no recognition sidecar, disk database, compile step or backend endpoint.

Advance `MODELING_RECOGNITION_VERSION` in
[modelingRecognitionCache.js](../src/renderers/cad/workbench/modelingRecognitionCache.js)
when inference rules, tolerances or serialized results change, including returned
labels, measurements and face/edge grouping. This is an internal algorithm
revision, unrelated to the repository's release version. Presentation-only
changes outside cached results do not require a bump. Geometry and resource
revisions remain independent parts of the key; the algorithm version replaces
neither. If configurable recognition options are introduced, their semantics
must also participate in the key.

## What the recognizer infers

The current algorithm first tries a complete extrusion, revolution or supported
solid reconstruction. Otherwise it presents an imported body with local feature
candidates and remaining geometry. That precedence is a presentation heuristic:
the same circular cut can appear as a cut extrusion or a bore in different
bodies. Changing these classifications is separate from cache/lifetime work.

- **Extrusions:** paired analytic cap contours, straight walls, side area and
  solid volume support a possible base/cut sequence. Profiles select real STEP
  boundary edges.
- **Revolutions:** full coaxial cylinder/cone solids can yield a closed axial
  profile and 360-degree revolution checked against solid volume.
- **Pockets and bosses:** local planar caps, translated rims and straight walls
  identify supported prismatic regions. Current local tests cover convex analytic
  profiles; they do not cover every pocket or boss.
- **Bores:** adjacent cylindrical patches are joined across export seams.
  Annular shoulders and full conical transitions can connect stages into blind,
  countersunk or counterbore candidates. Boundary samples and enclosed face
  bounds reject evident intrusions; they do not prove an empty volume.
- **Blends and other supported solids:** connected constant-radius
  cylindrical/toroidal blends, rounded boxes and supported ruled lofts have
  analytic recognition paths. Single curved corners are not automatically
  separate fillet operations. Shells and patterns are not invented.

Unclaimed faces remain available as other geometry. Candidate ordering is not a
modeling timeline, and a missing candidate does not establish that a feature is
absent. Measurements describe supported geometry; recognition is not engineering
validation. Independent kernel reconstruction checks belong to development tests,
not the runtime viewer or Python inspection API. Complete reconstruction claims
require both directional Boolean differences to agree; finding a local candidate
or matching its tool volume alone does not establish a rebuildable whole part.

## Limits and failures

The worker ticket permits at most 16 MiB of SURF data. Analysis rejects inputs
over 6,000 faces or 20,000 edges; the worker/ticket stage has a 10-second timeout.
These are safety limits, not promised execution times. Surface derivation before
worker startup has its own resource-service lifecycle.

Unavailable data, unsupported-size inputs, worker errors and timeouts produce a
component error and explicit retry. They do not become reusable cached results.
Other requested components can still be processed. Existing ordinary geometry
and part selection remain available. Keep workers off the UI thread, preserve
these bounds, and profile large parts before adding persistent caching or more
concurrency.

## Implementation and verification

- [useModelingRecognition](../src/renderers/cad/workbench/useModelingRecognition.js):
  descriptor demand, per-inspector queue, resource requests and cancellation.
- [modelingTree.worker](../src/renderers/cad/workbench/modelingTree.worker.js):
  resource-ticket loading, SURF parsing and inference.
- [modelingTree](../src/renderers/cad/workbench/modelingTree.js) and adjacent
  `modeling*` helpers: pure inference and canonical reference mapping.
- [modelingPresentation](../src/renderers/cad/workbench/modelingPresentation.js) and
  [ModelingTree](../src/renderers/cad/components/workbench/ModelingTree.jsx):
  occurrence binding, presentation, expansion and selection.

Keep renderer-private pure helpers here; they do not need to move to core merely
because they do not import React. Hosts implement resource effects through the
[viewer host contract](viewer-host.md), never a second recognizer.

Run `npm --prefix packages/ui test` from the repo root for helper and React
coverage. Recognition tests cover real STEP-derived fixtures, version/geometry
invalidation, cache bounds and warm reopening, expansion during pending work,
repeated instances, retry, disposal and rejected late results. Fixture provenance
lives in the [fixture guide](../src/renderers/cad/workbench/__tests__/fixtures/README.md).
Add small test-owned regression fixtures for changed inference rules. Rebuild
package exports and the bundled viewer before testing either app.
