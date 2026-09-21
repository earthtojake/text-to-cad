# Resource ownership and reuse

How the shared render code owns, shares, reuses and releases the expensive
things: component geometry, GPU buffers, BVH accelerators, tessellation
workers and cache reservations.

The one-sentence laws are in [the package README](../README.md#the-laws-that-live-here);
this file is the mechanism each of them constrains. Nothing here may be traded
away for speed: **reuse is an optimization, never a change in exact geometry,
persistent cache identity or occurrence identity.**

| § | Covers |
|---|---|
| [1](#1-shared-ownership-and-disposal) | More than one scene owner, and who disposes |
| [2](#2-the-demand-boundary) | Selectors and raycast accelerators built only when asked for |
| [3](#3-reuse-without-changing-geometry) | Recomposition, instancing, culling, material pass keys |
| [4](#4-tessellation-workers) | One request per worker, pool growth, reclamation, charges |
| [5](#5-browser-mesh-cache-admission) | Probe, admit, verify, adopt — and strict reads |

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

## 2. The demand boundary

Render-only loads do not construct selector topology until it is requested,
and viewport refinement keeps that boundary.

- Unused components replace only display arrays. A component with active
  topology replaces its selectors at the same concrete tessellation before
  publishing new triangles.
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
metadata across detail swaps; changed triangle ranges, bounds, placements and
appearance still produce the corresponding new records. Its private weak
ownership metadata never enters saved geometry or cache identity. Complete
same-file revisions can also seed from the prior composition.

Detached occurrence snapshots detect in-place descriptor or material edits;
only rows proven to belong to the current composition may skip scene work. A
static delta requires the same last-applied render context and no dynamic
pose, animation or clip. Changed components update their own records, while
unchanged occurrence geometry and selectors retain their owners. Arbitrary
mutable caller meshes keep normal reconciliation.

### Instancing and culling

Repeated compatible opaque surfaces share instanced draws and retain
occurrence identity; mirrors, transparency and deformation use explicit
fallback paths.

Detail publications retain compatible surface instance sets and their original
occurrence slots. Only changed membership or render passes replace those sets;
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

Canonical geometry trees contain no surface-producer selection. A runtime view
binds each component's opaque surface input to a concrete immutable SURF
object, and render/selector reuse requires that exact binding plus the lossless
tolerance pair and payload version. Other snapshot source scopes remain
isolated. Placement and appearance belong to each tree's occurrence
composition. Viewport L0 is explicitly coarse; L1 preserves the canonical
default mesh options and key. **Changing viewport detail never changes export
defaults.**

## 4. Tessellation workers

Each tessellation worker runs one request at a time; excess requests wait on
the client.

- Aborting synchronous work replaces only its worker, preserving other
  callers. A failed worker request reports an error instead of retrying
  expensive tessellation on the UI thread. Inline execution is reserved for
  environments where workers cannot start.
- A pool starts with one isolate and grows only for ready concurrent requests.
  Sequential viewport refinement reuses that isolate until the drain becomes
  idle; it does not create a maximum-size pool for each component.
- Pressure reclamation may release idle worker slots while active and queued
  consumers keep their work. Each live slot retains its own highest completed
  request estimate, including handled failures; reclamation or replacement
  removes that slot's charge.
- Memory estimates stay on the client. They do not enter worker messages or
  cache keys, and RAM hits add no worker charge.

## 5. Browser mesh-cache admission

Browser mesh-cache reads start with a bounded metadata probe. The client
admits the encoded object and conservative decoded size before fetching a
body, binds that fetch to the probed object digest and byte limit, then
verifies the v4 header and content address before adoption.

A validated warm entry carries the full surface-object provenance, so
rendering does not need the SURF object or its derivation index to remain
present. `createHttpTessellationCacheProvider` takes an `origin` for hosts
whose cache is not on the page's own origin. TESB body groups remain bounded
at 32 MiB; the Node export provider uses the same immutable `objects/` and
`index/mesh/` layout as Python.

A caller admitted using a cache probe can request a strict read: a missing or
invalid body reports a typed cache miss before tessellation starts. The viewer
releases that reservation and probes another cached tier or resolves the exact
surface under fresh cold-work admission. **Cache loss never silently turns a
cheap decoded-mesh request into unbudgeted surface tessellation.**
