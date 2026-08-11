# Viewer: large-package rendering plan

**Update 2026-07-09 — mesh-only consolidation. Instancing removed; ONE render path.**
The whole instancing engine and its plumbing were **deleted** in favor of a single
render path: **per-occurrence `THREE.Mesh` over SHARED component geometry** (never baked,
never instanced). This was a deliberate call for a single, maintainable strategy after the
instancing effort proved that GPU-instancing fights every per-occurrence feature the viewer
needs (a `partId` per occurrence for selection/hover/focus/hidden, a real matrix per
occurrence for explode + param animation, and per-part edges). The parity work made instanced
*approach* per-mesh, but through a parallel, more complex code path (pseudo-records, instance
buffer flushes, a selection-only screen-space edge overlay) — two engines to maintain for one
result. Shared geometry gets the same scaling win without the second path.

What shared geometry keeps and what it costs, vs the two prior approaches:

| | baked per-mesh (old default) | cid instancing (removed) | **shared geometry (now)** |
|---|---|---|---|
| GPU vertices (falcon_heavy) | 1.40M (12.3× inflation) | 114k | **114k** |
| compose (falcon_heavy) | ~140 ms | 12 ms build | **~18 ms** |
| heap (falcon_heavy, live) | ~301 MB | — | **~135 MB** |
| draw calls | 2,142 | ~141 | 2,142 |
| selection / face-select | full | instance recolor | **full (per-Mesh `partId`)** |
| explode / param animation | full | pseudo-records | **full (per-Mesh matrix)** |
| per-part edges | full | selection-only overlay | **full (cached per component)** |

How it works: `buildComposedPackageMeshData` keeps ONE component-local copy of each unique
component's geometry and emits one lightweight part per occurrence carrying `sourceMesh`
(the shared component meshData), a `sourceMeshKey` (`<cid>:<colourMode>`), the occurrence
`transform`, and component-local `sourcePartRanges`. `cadScene.buildPartGeometryEntry` caches
one `BufferGeometry` (with surface-edge attributes) per `sourceMeshKey`, so each component's
geometry + edges upload **once** and every occurrence is a `THREE.Mesh` reusing it, placed by
its transform at render time (`partTransformsBaked:false`). Nothing per-occurrence is baked.
Verified obligations: per-occurrence override colours drive the material as an sRGB hex string
(the descriptor authors linear RGB → `linearRgbToHex` → `readSourceColor` round-trips to the
same albedo the baked path shaded); mirrored occurrences render via the negative-determinant
transform + the `DoubleSide` surface material (no per-occurrence winding flip); face selection
maps unchanged because `sourcePartRanges` are component-local. In-browser: raptor3 (colours,
part/face selection, exploded, param animation) + falcon_heavy (2,142 occurrences, 690-part
selection, ~135 MB) + headless snapshot. The draw-call count is unchanged from baked per-mesh;
`BatchedMesh`/merge is the future lever if draw calls (not memory) ever dominate — but the
target models render fine and the user set no draw-call benchmark. **Everything below this line
is the historical instancing plan, superseded by this consolidation.**

---

Recorded 2026-07-06. Target workload: falcon_heavy-class component-GLB
packages — 2,142 occurrences over 141 unique components (top cid ×108,
seven more ×54), 24 distinct override colors; starship_stack is 2,562/282.
All findings below were adversarially verified against the code and the
actual falcon_heavy descriptor.

## Where the time and memory go today

- `packages/cadjs/src/lib/assembly/meshData.js:399-599`
  (`buildComposedPackageMeshData`): bakes every occurrence transform into
  fresh arrays in a synchronous main-thread per-vertex JS loop — 1,397,652
  composed vertices (12.3× the 113,748 unique ones), ~77 MB.
- `packages/cadjs/src/common/cadScene.js:670-744, 1784-1833, 1898-1909`:
  re-slices those arrays into one BufferGeometry + one physical material +
  one `THREE.Mesh` **per occurrence** (colors copied three times; 2,142
  `computeBoundingSphere` calls) → ~2,142 draw calls, ~66 MB GPU buffers.
  No `InstancedMesh`/`BatchedMesh`/merge anywhere in cadjs or viewer.
- `viewer/src/client/components/workbench/hooks/useCadAssets.js:527-536`:
  component GLBs parsed on the main thread (`loadRenderGlb` without
  `preferWorker`, though the worker path exists) at concurrency 3.
- Barycentric edge attributes force un-indexed 3-verts-per-triangle
  geometry that is composed and uploaded even when the display mode draws
  no edges (~42 MB copies, ~21 MB GPU upload).
- `useViewerPicking.js:638-663`: hover raycasts rebuild the visible-mesh
  array and intersect all 2,142 meshes per rAF; hover changes rewrite
  material state across all records.

## Phases

**Phase 0 — benchmark harness (prerequisite). DONE.**
`packages/cadjs/bench/composePackageBench.mjs` — a Node harness (no GPU) that
loads a warmed `__cadgen__` package, parses every component GLB, and times +
measures the meshData-layer structural costs the plan's wins are stated in.
Run: `cd packages/cadjs && node bench/composePackageBench.mjs [package-dir]`
(needs `three` resolvable — dev: symlink `viewer/node_modules/three` into
`packages/cadjs/node_modules/`; and a warmed package on disk).
Structural metrics (draw calls, vertex inflation, compose ms) are covered
here; GPU upload / frame rate / felt main-thread stall still need an
in-browser check per phase.

**falcon_heavy baseline (pre-Phase-1):** 2,142 occurrences · 141 unique
components · **2,142 draw calls** · 113,748 unique → **1,397,652 composed
vertices (12.29×)** · 465,884 composed triangles · 53.3 MiB composed
buffers · 140 ms compose. These are the numbers Phases 2–3 must move.

**Phase 1 — parallel worker parsing (small).** `preferWorker: true` for
package component loads, concurrency 3 → min(hardwareConcurrency, 8), fix
the serial shared path (`source.js`) to `Promise.all`. Win: est. 2–4×
time-to-first-render; zero render-path risk. Ship first.

**Phase 2 — compose off the main thread, once (medium).** Move
`buildComposedPackageMeshData` into the existing GLB worker (transferable
arrays); stop the per-part re-slice by sharing one geometry with draw
ranges until Phase 3 replaces it; skip barycentric/class composition and
upload when the display mode draws no edges. Win: removes the 0.5–2 s
main-thread stall and ~150 MB of peak heap; −21 MB GPU upload with edges
off.

**Phase 3 — cid-keyed instancing (large, the headline).**

*Core engine — DONE (`227ebfd8`).* `packages/cadjs/src/lib/assembly/
instancedScene.js` `buildInstancedPackageScene(THREE, descriptor,
componentMeshDataByCid)` builds one `InstancedMesh` per (component × mirror
bucket): unique geometry uploaded once, per-instance 4×4 matrix + optional
override color, occurrence-id instance mapping, DoubleSide mirror bucket.
Bench-proven on falcon_heavy: **2,142 → 141 draw calls (15.2×), 1.40M →
114k GPU vertices (12.29×), 138 ms compose → 12 ms build.** Unit-tested
(bucketing / matrix == transform / occurrence-id map / instance color /
mirror). NOT yet wired into the live path — zero regression so far.

*Integration increments (each its own commit + gate):*
1. **Render wiring — DONE (`308c7261`).** `buildComposedPackageMeshData`
   attaches `packageInstancing:{descriptor, componentMeshDataByCid}`;
   `buildInstancedDisplayRecords` builds the instanced group;
   `modelOptionsForRenderJob` threads the flag; snapshot re-bundled. Gate
   met: flag-off snapshot **byte-identical** (SHA1 dc7e7dd5); bench 15.2×
   draws / 12.29× GPU verts.
2. **Picking — DONE (`333190d2`).** `partIdFromIntersection`
   (`viewer/.../hooks/instancePicking.js`) maps `InstancedMesh` raycast
   `instanceId` → occurrence id via `userData.cadInstanceOccurrenceIds`;
   `pickPartReferenceFromIntersections` uses it. Extracted as a pure module
   so it unit-tests in Node without the hook's Vite-only imports.
3. **Selection / hover / hidden / focus — DONE (`db5c1aed`).**
   `applyInstancedVisualState` recolors via `instanceColor` (selection/hover),
   dims the base color under focus, and collapses hidden instances to a zero
   matrix — restoring from base color/matrix arrays stashed at build time.
   `applyPartVisualState` routes instanced records through it with the same
   hierarchical `partIdMatchesSet` matcher.
6. **Size policy + default-on — DONE.** `shouldInstancePackageScene` is
   tri-state: `instancePackages:true|false` forces on/off; left undefined the
   size policy decides — a package instances once it has
   `≥ INSTANCE_MIN_OCCURRENCES` (128) occurrences. So huge packages
   (falcon_heavy 2,142) instance by default in both the viewer and snapshots,
   while small/medium assemblies stay on the full-featured per-mesh path.
   `resolveInstancePackagesFlag` keeps the render-job flag tri-state.

*Deferred as documented gaps for instanced (large) packages — NOT bugs:*
4. **Exploded view.** The per-record explode engine already excludes instanced
   records (`recordCanExplode` needs a non-null `partId`), so explode is a
   graceful no-op on a fully-instanced model rather than a crash. Per-occurrence
   explode on a 2,000-part rocket is visual noise and costly to build; small
   assemblies that actually use explode stay per-mesh below the size threshold.
   Revisit only if a mid-size instanced package needs it.
5. **Edges / silhouette.** Instanced buckets carry no per-part edge/silhouette
   overlays (the per-mesh path builds `EdgesGeometry` per record). Edge soup
   over 2,000+ occurrences is low value; a selection-only instanced-edge overlay
   is the future path if wanted.
7. **Zoom-to-fit a selected occurrence — RESOLVED in Phase 4** (see below).
   Instanced records carry no per-record `partBounds` (bounds are per instance,
   not per bucket), so `autoZoom.js displayRecordsBounds()` skipped them and
   "zoom to fit selection" on an instanced occurrence no-op'd ("No geometry to
   fit"). (Found + confirmed in the pre-PR audit; fixed by
   `instancedOccurrenceBounds` in the Phase-4 pass.)

The pre-PR adversarial audit also surfaced and **fixed** three defects before
merge: a `major` — focus mode dropped every instanced bucket from the pick
raycast set (`shouldRaycastRecordForPick` now keeps instanced buckets; the
per-occurrence hidden/focus filter runs downstream); and two `minor`s — the
bucket material ignored a component's baked vertex colors (now forwarded), and
`settingsSignature` omitted `instancePackages` so a runtime `update()` toggle
would not rebuild (now included).

Win (as shipped, for packages over the size threshold): 2,142 → ~141 draw
calls (15×), GPU vertices 1.40M → 114k (12.3×), ~60 MB GPU saved, hover/
visibility loops shrink 15×, and the Phase-2 compose loop disappears entirely
(instances need no baked vertices). Verified obligations:
- mirrored occurrences (negative-determinant transforms) get their own
  DoubleSide bucket — DONE;
- picking via `InstancedMesh` raycast `instanceId` → occurrence id — DONE;
- hover/highlight via per-instance color — DONE (per-instance recolor);
- exploded view / per-part edges — deferred gaps (see 4/5 above);
- translucent parts: currently share the bucket material (no per-instance
  transparency sort). Acceptable for opaque rocket hardware; a translucent
  fallback bucket remains the future path if a translucent large package appears.

**Phase 4 — interaction polish + gap execution (branch
`claude/viewer-phase4-instanced-interaction`).** Executed as a mix of
implementations and measured declines (like the edit-path A-set):

- **Zoom-to-fit a selected instanced occurrence — DONE** (was gap #7).
  `instancedScene` stores each bucket's component-local AABB and exposes
  `instancedOccurrenceBounds(mesh, matches)`, a pure resolver that transforms
  the box by each matching instance's base matrix. `buildInstancedDisplayRecords`
  attaches it as `instancedBoundsFor`; `autoZoom.displayRecordsBounds` calls it
  for instanced records. Selecting a part and "zoom to fit" now frames it.
- **Per-hover incremental instance update — DONE.** `applyInstancedVisualState`
  used to rewrite every instance and dirty the whole GPU buffer on each hover
  transition (2,142 re-uploads for falcon_heavy). It now tracks a per-instance
  state code and rewrites only instances whose state changed, dirtying a bucket
  only when it actually changed — a hover touches ~2 instances, not 2,142. This
  is the substance of the old "diff hover state changes" Phase-4 item; it lands
  in the shared engine (also benefits snapshot).
- **Visible-mesh-set caching — DECLINED (evidence).** The array rebuild is cheap
  CPU; the cost that mattered was the raycast against N meshes, already cut ~15×
  by instancing (raycast is now against ~141 InstancedMeshes). Caching adds
  fragile invalidation (must also track per-record `mesh.visible`) for a
  negligible gain. Not worth the regression surface.
- **three-mesh-bvh — DECLINED (evidence).** A bvh is only justified by slow
  picking; post-instancing picking is not hot. Adding a dependency + build step
  for no measured need fails the cost/benefit test.
- **Exploded view (instanced) — DEFERRED (concrete sketch).** Now tractable atop
  `instancedOccurrenceBounds`: feed the explode engine per-occurrence
  pseudo-records (partId=occurrence id, partBounds=per-occurrence world bounds),
  then map each occurrence's resulting translation to a per-instance matrix
  offset (base × translation) applied like the hidden/base matrix write. Deferred
  because a 2,000-part radial explode is visual noise and the size threshold keeps
  explode-using small assemblies on the full-featured per-mesh path; revisit if a
  mid-size instanced package needs it.
- **Per-part edges (instanced) — DEFERRED.** Selection recolor already conveys
  selection; a selection-only instanced-edge overlay (EdgesGeometry of the
  selected component placed at the instance matrix) is the future path.

NOTE: `matrixAutoUpdate = false` for baked transforms is ALREADY applied
(`packages/cadjs/src/common/displayRecordTransform.js:9`, tested in
`modelRuntime.test.js`) — not a remaining item.

## Phase 3 scoping reality (checked against the code)

The record system in `cadScene.js` is one-mesh-per-occurrence end to end:
`makeRecord` (`:1784-1833`) builds a per-part `BufferGeometry` slice + its
own `MeshPhysicalMaterial` + `THREE.Mesh` + optional edge and silhouette
child objects, and every downstream behavior keys on the per-record
`partId` — selection/hover/hidden/focus (`partIdMatchesSet`, `:1235-1238`),
exploded `baseTransform`, per-record effect/opacity/highlight, and pick via
`mesh.userData.partId` + `intersectObjects(perPartMeshes)`. Converting to
`InstancedMesh` is therefore not a local swap: it needs an instance-aware
selection/pick/explode/edge layer (instanceId ↔ occurrence, per-instance
color/visibility, selection-only edges) living beside or replacing the
record system, and it changes the shared module that also drives headless
snapshot rendering (bundled into `skills/cad/scripts/snapshot/runtime/
snapshot-render.js` via `bundle.sh`). Recommended execution: a dedicated
effort landing behind a default-off `instancePackages` render setting,
gated by (a) this bench (draw calls/vertices), (b) snapshot pixel-parity
across all six display modes, (c) an in-browser pass (Preview MCP or
manual) for hover/pick/explode/transparency before the default flips.
Strategy to bound blast radius: instance only the common opaque,
non-mirrored occurrences; fall back to the existing per-mesh record for
transparent / negative-determinant / edge-heavy parts so nothing regresses.

## Constraints

- Instancing lives in `packages/cadjs` (framework-agnostic); the viewer app
  keeps only UI state. Snapshot rendering shares cadScene, so Phase 3 must
  keep snapshot output pixel-equivalent (harness includes a snapshot diff).
- Verification per phase: screenshot parity across display modes
  (solid/rendered/transparent/edges), picking + exploded + params-sidecar
  regression on falcon_heavy, starship_stack, tom, and one small model.
