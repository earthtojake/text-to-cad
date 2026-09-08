# Handoff: PR #370 viewer memory/perf work — state and what is left

Rewritten 2026-09-08 by the second review session, replacing the first session's
step list (steps 4 and 6 of that list turned out to be already implemented, and
its measurement table predates every change since). Delete this file in the last
commit before merge.

Background documents (read-only, outside the repo):
- Design: `~/robots/text-to-cad-notes/design/viewer-memory.md`
- Bug-log verdicts: `~/robots/text-to-cad-notes/tendon-hand-bugs.md`

## 0. Facts you must not guess

- Repo: `/Users/jakefitzgerald/robots/text-to-cad` (MAIN). MAIN is on branch
  `codex/anthropomorphic-tendon-hand` at an OLD commit and holds the warm CAD
  cache (`~/.cache/cadgen`) and the hand's built STEP files under
  `MAIN/models/assemblies/STEP/anthropomorphic_hand/`. Do not switch its branch.
  Its `.git/index.lock` has been stale since 2026-09-07 12:40 with no git
  process holding it; anything needing MAIN's index will fail until it is
  removed.
- Node deps in a worktree: `packages/cadgen-js/node_modules` may be a whole-dir
  symlink to MAIN's, but `apps/viewer/node_modules` must be a REAL directory of
  per-entry symlinks with `cadgen-js -> <worktree>/packages/cadgen-js`. Check
  with `readlink -f <worktree>/apps/viewer/node_modules/cadgen-js`; if it prints
  MAIN's path the viewer tests are testing the wrong code.
- Suites: `npm --prefix packages/cadgen-js test` (829), `npm --prefix apps/viewer
  run test` (346), `PYTHON_BIN=MAIN/.venv/bin/python scripts/test/test-python.sh`,
  `scripts/bundle/bundle.sh` then `--check` whenever `packages/cadgen-js/src`
  changed (commit the regenerated `_runtime/browser/snapshot-render.js`).
- Fixtures: the hand is
  `assemblies/STEP/anthropomorphic_hand/hand_mechanical_candidate_r13.step`
  (866 components, 3,259 occurrences). A smaller one that loads in ~32 s:
  `assemblies/STEP/anthropomorphic_hand/routing_layout_review.step` (303
  components, 1,216 occurrences).
- User constraints, binding: every feature preserved (per-occurrence highlight,
  dim, hide, focus, opacity, exploded view, hover/selection picking, tube
  deformation, per-class edge colour/opacity/thickness, animation, kinematics).
  Pausing hover/selection raycasts while the camera moves is allowed. Hiding
  edges or any geometry during camera motion is NOT. No backwards-compat shims;
  hard cutovers. cadgen-js stays non-React.

## 1. How to measure

Harness at `scripts/bench/viewer-memory/`: `measure.mjs` (memory/timing, now
also reporting the largest SINGLE renderer process and an after-GC reading),
`profile.mjs` / `cpu-profile.mjs`, `publish-timing.mjs`.

```bash
cd <worktree>/apps/viewer && npm run build
cd MAIN/models && MAIN/.venv/bin/python -m cadgen.viewer --host 127.0.0.1 \
  --port 3450 --new --dist <worktree>/apps/viewer/dist --json &
cd <worktree>/scripts/bench/viewer-memory && node measure.mjs --url http://127.0.0.1:3450 \
  --file assemblies/STEP/anthropomorphic_hand/hand_mechanical_candidate_r13.step \
  --label r13 --runs 2 --timeout-ms 900000 --sample-ms 250 --out /tmp/r13.json
lsof -ti :3450 | xargs kill   # stop ONLY your own instance
```

`measure.mjs` reports the SUM of renderer-process RSS beside the largest single
one. The gate is about the largest single process — a tab dies on its own
footprint — and Chromium runs more than one renderer here.

## 2. Where it stands, measured on r13

| metric | baseline (old client) | at `fb1632c5b` | now |
|---|---|---|---|
| first geometry on screen | ~86 s | 4.7 s | **4.9–5.9 s** |
| time to fully loaded | 86–90 s | 186 s | **147 s** |
| renderer RSS peak | 4.5 GB | 3.4–3.6 GB | **2.65 GB** (largest single 2.58 GB) |
| renderer RSS after a forced GC | — | — | **2.22 GB** (heap 1.18 GB) |
| JS heap peak | 3.3 GB | 2.2–2.4 GB | **1.72 GB** |
| GPU buffer bytes | 2418 MiB | 524 MiB | **507 MiB** |
| publishes | 1 | 28 | **8** |
| draw calls over the load | — | 368k | **98k** |

The hand also loads in a real (in-app) browser without crashing: 144 s, 3,259
occurrences, JS heap 1.22 GB settled.

## 3. What landed in this session

- `6b7621a99` — the tube braid shader never compiled. `bbc48ff9c` moved the
  shared varying's declaration to the same `#include <common>` anchor the braid
  block uses, so the fragment stage read `vCadTubeMaterial` above the line
  declaring it and every braided tube lost its program. The hook now inserts the
  declaration last; `tubeMaterialShader.test.js` pins declaration-before-use.
- `e184fc941` — publish batches DOUBLE (8 components/8 MB up to 256/128 MB), so
  the publish count is logarithmic in the model and the first batch is smaller
  than the old fixed 32; the surf worker pool is released when a load ends or
  aborts; a deformed tube's private edges are one screen-space fat line per
  drawn class at that class's width instead of one 1-px vertex-coloured
  GL_LINES; a released component's queued BVH is no longer built after the fact.
  Also verified and carried in the previous session's uncommitted work (departed
  components free their GPU buffers, BVHs and edge draws) and dropped two
  duplicated test blocks.
- `034077528` — the camera frames again once every component has arrived, unless
  the user has already moved it.
- `221f6c48a` — the hand's render module articulates (see §5).

## 4. What is left

**Memory.** 2.65 GB peak (largest single renderer 2.58 GB) against the previous
session's "well under 2 GB" gate. That is 25% below the 3.6 GB that crashed the
user's Chrome twice, and the model loads in a real browser now, but the gate is
not met. After a forced GC the renderer still holds 2.22 GB (largest 2.15 GB)
with a 1.18 GB JS heap, while the probe accounts for 712 MB (surface 530 MB, BVH
158 MB, edges 23 MB).

PICKING IS NOT THE GAP, and the probe now proves it rather than leaving it a
suspect: `faceIdBytes` and `pickBytes` are both ZERO after a full load of the
hand. Selector topology is lazy — nothing loads it until something is picked —
so `buildGlbFaceIdsForPart`'s per-occurrence triangle -> face-row map (98.5 M
occurrence-triangles, ~394 MB if it ever covered the model) and the merged pick
proxies cost nothing on a plain load. Do not go looking there again; go looking
at picking only if you make selector topology eager.

What is left points at the PER-OCCURRENCE OBJECT GRAPH: 3,259 meshes, 5,061
materials and 1,839 geometries, each with its own three.js WebGLProperties entry
and uniform list, none of which the byte accounting can see because none of it
is a typed array. That is the same thing the remaining draw calls are — one
surface draw per occurrence — so instancing surface meshes per component is one
change against both. Confirm it with a heap snapshot before building it.

**Load time.** 147 s against an 86 s baseline. It is NOT transport: the viewer's
`/__tess_cache/` route serves 315 MiB/s to one reader and 681 MiB/s across
eight, while the load only draws ~15 MiB/s because the workers are busy. And the
cache is worth having — blocking it takes the routing fixture from 32 s to 63 s.
So the cost is per-component CPU in the surf worker: entry decode,
`buildMeshDataFromSurf` and `buildSelectorBundleFromSurf`. Profile those three
before choosing a lever; deferring the selector bundle until picking needs it is
the obvious candidate and would change when topology is available.

**Instanced edges.** Implemented, unit-tested and confirmed to render on a GPU
(no shader errors, `edgeInstanceSets` 829 for 866 components, edge bytes 4.4% of
surface bytes). Not measured: orbit median/p90 frame time before and after, and
the per-frame cost of `instanceTexture.needsUpdate = true` on every `setMatrix`,
which re-uploads a component's whole instance texture on every animated frame.
Surface meshes are still one draw per occurrence (~6.5k of the ~7.5k draw calls);
instancing them per component is the remaining draw-call lever.

**Smaller, all real, none blocking:**
- `CadEdgeInstances.syncCounts` is quadratic on a mass release
  (`freeSlots.includes` inside a loop over `slotCount`).
- A record that leaves the instanced set for a tube deformation never rejoins
  it. Deliberate — a publish resets the pose, so rejoining there would rebuild
  every tube's line geometry on every publish — but it costs one draw per tube
  that has ever bent. Written up at `attachCadEdgeInstance`.
- A component's edge segment texture is cached on the component across scenes,
  but disposal only checks the sets in ONE runtime.
- `node_resolve_register.mjs` uses deprecated `module.register` (Node DEP0205);
  `registerHooks` needs Node ≥ 22.15 and the wheel's floor is 20.
- Per-component bounds in `assembly.json` would let the FIRST progressive
  publish frame the exact model, and the completion re-frame could go.

## 5. The hand's render module

`STEP/anthropomorphic_hand/hand_mechanical_candidate_r13.step.js` is generated by
`models/assemblies/validation/anthropomorphic_hand/write_showcase_presentation.py`
— edit the generator, never the module. It carries the build's authored joint
datums and evaluates `lib.layout.assembled_transforms` in JavaScript, so the
choreography is exact forward kinematics rather than eyeballed rotations.

The tendons do NOT bend: a posed route is a routing solve, and moving each route
group rigidly with its own frame tears the centerline apart by up to 100 mm,
which `deformTube` rightly refuses. They are shown at rest and faded through
motion instead. Making them bend means re-solving all 48 routes per keyframe in
Python and embedding the samples — the one real follow-up on the animation.

## 6. Before merging

Run every suite in §0, `scripts/bundle/bundle.sh --check`, re-measure r13 per
§1 and paste the table into the PR, delete this file, push.
