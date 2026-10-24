# Resource ownership and reuse

How the shared render code owns, shares, reuses and releases the expensive
things: component geometry, GPU buffers, BVH accelerators and decode
workers. Workspace resource reads and their cache
generations are specified in [workspace services](workspace-resources.md).

The one-sentence laws are in [the package README](../README.md#the-laws-that-live-here);
this file is the mechanism each of them constrains. Nothing here may be traded
away for speed: **reuse is an optimization, never a change in exact geometry,
persistent cache identity or occurrence identity.**

| § | Covers |
|---|---|
| [1](#1-shared-ownership-and-disposal) | More than one scene owner, and who disposes |
| [2](#2-the-demand-boundary) | Raycast accelerators built only when a ray needs one |
| [3](#3-reuse-without-changing-geometry) | Recomposition, instancing, culling, material pass keys |
| [4](#4-decode-workers) | The GLB and STL workers, leased by render sessions |

## 1. Shared ownership and disposal

Component geometry and edge textures can have more than one scene owner; only
the last release disposes shared GPU/BVH state.

- Full scene disposal includes host-reparented groups and records attached by
  an interrupted reconciliation.
- Cleanup retires completed ownership steps. A thrown disposal remains
  retryable and cannot release another scene's share twice.
- Failed initial construction cleans its partial scene before throwing, or
  transfers the still-owned scene with an explicit cleanup error for retry.
- Disposable resource admission never changes exact geometry or persistent
  cache identity.
- A scene's sibling (`createSibling()` of `lib/render/glbScene.js`,
  `lib/render/meshScene.js`, `lib/urdf/robotScene.js`) draws over the source's
  geometry through `lib/render/sharedGeometry.js`: `shareGeometry` gives it the
  source's index and attribute objects, so one renderer drawing both scenes uploads
  each buffer once, and copies only what the sibling rewrites for itself (a robot's
  vertex colours). `releaseGeometry` lets go of the shared attributes before
  disposing, so only what the sibling owns is freed. The source stays the owner and
  is disposed after its siblings. A GLB sibling restores the authored local transforms,
  bone transforms and morph weights captured at scene creation; the editor's current
  routine, explosion and selection overlays never become Preview's baseline.
- `createCadWebGlRenderer` (`common/webglRenderer.js`) takes the `canvas` it draws
  on (an `OffscreenCanvas`), so one renderer, and one upload of each resource, can
  serve several views; disposing it and losing its context are its caller's.

## 2. The demand boundary

- Raycast accelerators may be deferred until a ray reaches a component's
  local bounds. The first ray uses exact stock intersection; surface builds
  enter a single worker queue in idle time and are shared by occurrences.
- Admission covers private position/index copies, worker scratch, and the
  result before creating an isolate. Display arrays are never transferred.
  Each worker ends with its reservation; only serialized BVH nodes and the
  indirect triangle permutation return. Byte accounting includes both the
  packed BVH nodes and that indirect permutation.
- Failed or pending builds keep stock picking. A result must match the
  geometry's attributes, arrays, versions, groups, draw range and live
  ownership; the last geometry release cancels queued or active work.
- Deformation runs before the bounds test.

## 3. Reuse without changing geometry

### Recomposition

Recomposition may take its previous result when the descriptor and component
inputs are immutable. It shares unchanged occurrence rows and unchanged tree
metadata across progressive publishes; changed triangle ranges, bounds, placements and
appearance still produce the corresponding new records. Its private weak
ownership metadata never enters saved geometry or cache identity. Complete
same-file revisions can also seed from the prior composition.

Detached occurrence snapshots detect in-place descriptor or material edits;
only rows proven to belong to the current composition may skip scene work. A
static delta requires the same last-applied render context and no dynamic
pose, animation or clip. Changed components update their own records, while
unchanged occurrence geometry and selectors retain their owners. Arbitrary
mutable caller meshes keep normal reconciliation.

Imported STEP products without faces keep their occurrence identity. A product
that holds only wires has no triangles, so its mesh's box comes from its edges'
polylines. One with no faces or edges meshes to empty arrays, a zero-size box at
the origin and a positive minimum scale. Either way the same body validation
applies. That box is only the body's metadata: only triangles are
drawn, so composition gives an occurrence without them no bounds, and it
cannot change the assembly's framing or hide the real parts.

### Selector composition

An assembly's selector runtime is composed from one part per placed occurrence
(`buildSelectorCompositionPart`, `createSelectorRuntimeComposer` in
`lib/selectors/runtime.js`). A part keeps its rows, its references as last
placed and the bundle's own proxy buffers with the placement transform — never
a placed copy of the proxy or lookup maps. The composer re-places a part's
references only when its offsets move, and a composition that begins with the
previous one extends that result instead of rebuilding it. The result is value
for value the whole-runtime `composeSelectorRuntimes` result for the same
components in the same order (`runtimeComposer.test.js`).

### Instancing and culling

Repeated compatible opaque surfaces share instanced draws and retain
occurrence identity; mirrors, transparency and deformation use explicit
fallback paths.

Later publications of the same model retain compatible surface instance sets and
their original occurrence slots. Only changed membership or render passes replace those sets;
selected, hidden and deformed occurrences keep inactive slots until eligible
again. Transform passes reuse each mesh's matrix while observing mutable
source transforms and effect matrices on every update.

Surface instance groups use aggregate frustum bounds, invalidated by instance
matrix and slot changes. Transformed component boxes and conservative parent
affine padding keep boundary-crossing geometry eligible, including shear.
Culling changes draw submission only; occurrence slots and picking remain
intact. Screen-space edge instances retain their separate drawing policy.

### Material pass keys

Material pass keys reuse serialized strings only after comparing their current
scalar values, emission state, render order and clipping planes. Direct
material and plane mutations remain observable; custom values use ordinary
serialization. Reapplying material settings preserves unchanged shader programs
and owned emissive colors. Colour and PBR uniforms still update on every pass;
feature changes, vertex-colour mode and transparency invalidate the appropriate
program. Reflection intensity belongs to the shared pass key. A distinct
nonblack emissive channel, or emission over vertex colours, uses the ordinary
material so the instance colour cannot tint that channel.

Clients that apply pose, selection or material changes directly to display
records finish with `scene.syncSurfaceInstances()`; this uses the same
reconciliation as a source update. Clip-only viewer updates also synchronize
the shared surface material.

### Revision reuse

Canonical geometry trees contain no producer selection. Snapshot source scopes
remain isolated. Placement and appearance belong to each tree's occurrence
composition.

## 4. Decode workers

The GLB and STL decode workers are one each, and render sessions lease them. Releasing
one owner never cancels another owner's work; the final release retires the worker and
its pending work.
