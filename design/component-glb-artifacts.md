# Component-GLB assembly artifacts

**Status:** Proposed (design) · **Scope:** `packages/cadgen` (build) + `packages/cadjs`,
`viewer`, `skills/cad/scripts/{snapshot,inspect}` (consume) · **Date:** 2026-06

## 1. Summary

Replace the single monolithic `.{model}.step.glb` render artifact for an **assembly**
with a **package directory** of the same name containing:

- one **component GLB per unique part** (mesh + embedded local topology), and
- one **`assembly.json`** descriptor mapping occurrences → component + world transform.

The viewer/snapshot/inspect tools load each unique component once and **instance** it
per occurrence at render time (native glTF node instancing). The baked `.step` artifact
is unchanged.

This converts the dominant build cost — per-occurrence selector/topology extraction —
from *per-assembly, every build* to *per-component, once*, and makes warm assembly
rebuilds effectively free.

## 2. Motivation

Profiling the tom assembly build (`--force`, after the base-clamp swap) showed the
GLB/topology artifact stage is the bottleneck, and within it the **selector/topology
manifest extraction dominates**:

| Stage | Time |
|---|---|
| mesh (`BRepMesh`) | 2.2s |
| **selector/topology extraction** | **29.5s** |
| GLB pack + write | 1.7s |
| **monolithic GLB/topology total** | **33.5s, 80 MB** |

The cost scales with **occurrences × faces**: tom has 33 occurrences / 207 leaf solids,
of which 22 occurrences are repeats of an already-extracted part (e.g. 4× the same servo,
8× the same standoff), and one component (the Waveshare bus) is 57% of all faces. Every
build re-extracts all of it; nothing is shared across the three tom variants or across
rebuilds. The shape-only STEP export bakes geometry, so the existing in-GLB prototype
instancing is defeated (every baked solid is a distinct prototype).

A prototype (see §9) that extracts each **unique component once** and emits a descriptor
brought the warm assembly build's GLB stage to ~0s and shrank the per-model artifact ~2×.

## 3. Goals / non-goals

**Goals**
- Extract mesh + topology **once per unique component**, not once per occurrence.
- Make warm assembly rebuilds skip the GLB/topology stage entirely (cache hit).
- Preserve exact selector semantics for `inspect_refs` and viewer picking.
- Keep `assemblyMates` and occurrence colors working unchanged.

**Non-goals (explicitly out of scope)**
- The `.step` artifact and `gen_step` contract are **unchanged** (still a baked shape
  STEP; the bus is still baked into the STEP — that's a separate STEP-size concern).
- No cross-*model* component sharing in v1 — each model's package owns its component
  copies (see §7). Mesh-once-across-models is a future build-cache optimization,
  independent of this artifact format.

## 4. Architecture

```
gen_step() ─► build123d Compound (located children: unlocated TShape + world Location)
                 │
                 ├─► STEP export (baked)  ─►  tom.step                 [unchanged]
                 │
                 └─► component extraction ─►  .tom.step.glb/           [NEW package]
                          group children by unlocated-geometry hash → components
                          mesh + topology each unique component once
                          emit assembly.json (occurrence → component + transform)
```

Key enabler: a build123d `Compound` from `compound_from_instances` holds **located
children** — each child is `import_step(part).moved(world_transform)`, i.e. a shared
unlocated `TShape` plus a `TopLoc_Location`. The bake only happens at STEP export. So the
component build reads the **pre-export** structure: unlocated geometry → component,
location → occurrence transform. (Equivalently, the build can use the gen_step instance
list `{path, name, transform}` that `compound_from_instances` already constructs.)

## 5. Artifact format

### 5.1 Package layout

```
models/robots/tom/
  tom.step                       # primary CAD artifact (unchanged)
  .tom.step.glb/                 # was a file; now a package directory (same name)
    assembly.json                # the assembly descriptor
    components/
      <source-sha>.glb           # self-contained: mesh + embedded local topology
```

- `.{model}.step.glb/` is a **directory** named identically to the legacy file.
- `components/<source-sha>.glb` is content-addressed by the component's **unlocated
  geometry hash** (sha256 of its BREP). A component GLB is a normal `.step.glb`-style
  GLB **with embedded selector topology** (built via
  `export_assembly_glb_from_scene(include_selector_topology=True)`), expressed in the
  component's **local frame** (selectors `f1, f2, …`, `e1, e2, …`, and the component's
  own sub-occurrence tree `o1`, `o1.1`, …).
- There is **no `refs.json`** — the topology is embedded in each component GLB exactly as
  it is in today's monolithic `.step.glb` (read back via
  `read_step_topology_manifest_from_glb`).

### 5.2 `assembly.json` schema

```jsonc
{
  "schemaVersion": 1,
  "kind": "assembly-package",
  "rootName": "tom",
  "units": "mm",
  "sourceHash": "<assembly source-closure hash>",   // for staleness checks
  "components": {
    "<componentId>": {
      "glb": "components/<source-sha>.glb",
      "sourceHash": "<source-sha>",
      "solidCount": 5, "faceCount": 490, "edgeCount": 1234
    }
  },
  "occurrences": [
    {
      "id": "o1.1",                                  // assembly occurrence selector root
      "name": "base_link__sts3250_3",
      "component": "<componentId>",
      "transform": [16 floats, row-major, mm],       // world placement of the component
      "color": [r, g, b, a]                          // optional occurrence color override
    }
  ],
  "assemblyMates": [ /* unchanged: normalized m{n} ids, fixed/moving part:frame */ ],
  "bbox": { "min": [x,y,z], "max": [x,y,z] }
}
```

Notes:
- `occurrences` is flat (one entry per top-level assembly child); a component may itself
  be multi-solid, but that structure lives inside the component GLB, not here.
- `transform` is the occurrence's world placement; the component geometry is local, so the
  renderer applies `transform` to the instanced component.
- `assemblyMates` is the same list already attached to `compound.assembly_mates` and
  harvested at export — it moves verbatim into the descriptor.

## 6. Selector composition contract (correctness-critical)

This is the part that must be exact, because `inspect_refs` and viewer picking depend on
it, and ~190 selector tests guard it.

**Resolution (selector → geometry):** an assembly selector is
`<occurrence-id>.<component-local-selector>`. To resolve `o1.1.f3`:
1. `descriptor.occurrences[id="o1.1"]` → `component` + `transform`.
2. The component's embedded topology resolves the local selector `f3` (a face in the
   component's local frame).
3. Apply `transform` to place it in the assembly frame.

For a multi-solid component the local selector carries the component's own path, e.g.
`o1.1.o1.2.f3` = occurrence `o1.1`, component sub-occurrence `o1.2`, local face `f3`.
**Composition rule:** assembly selector = assembly occurrence id `+ "." +` component-local
selector path, with the component's local root (`o1`) stripped.

**Picking (geometry → selector):** a viewer hit returns `(occurrence node, component,
component-local face/edge)`; recompose the assembly selector by prefixing the occurrence
id onto the component-local selector path.

**Mates:** `assemblyMates[].fixed/moving` are `part:frame` strings where `part` is an
occurrence `name` and `frame` is a named datum — unchanged. Resolution maps `part` →
occurrence → component, then `frame` → the component's named datum.

Invariant that makes this stable: a component's face/edge **ordinals are deterministic for
identical geometry**, so `f3` means the same geometric face in every occurrence and every
rebuild. (Ordinal is already the selector basis today; nothing new is assumed.)

### 6.1 The `STEP_TOPOLOGY` manifest is world-space — compose at read time

The embedded `STEP_TOPOLOGY` glTF extension schema (`entryKind`, `occurrences`, `assembly`,
faces/edges, bboxes, `assemblyMates`) is **unchanged**, but it moves:

- Today's monolithic assembly GLB stores **one** `STEP_TOPOLOGY` blob with
  `entryKind=assembly` — the full composed tree (all occurrences, **world-space** node
  transforms and face/edge bboxes, selectors `o1.X.fY`).
- A component GLB stores its own `STEP_TOPOLOGY` with `entryKind=part`, in the component's
  **local** frame, **once** per unique part (the 4 servos' topology is stored once, not 4×).
- There is **no stored assembly-level blob.** The assembly manifest is **reconstructed at
  read time** by walking `assembly.json.occurrences`, pulling each component's local
  `STEP_TOPOLOGY`, prefixing the occurrence id onto its selectors, and **transforming its
  local bboxes/node data by the occurrence's world matrix**.

Because the manifest is world-space, composition is *not* pure id-prefixing — it applies the
occurrence transform to the component's local geometry data. That is **cheap matrix
arithmetic, not OCCT re-extraction**, which is precisely why the 29.5s selector cost
evaporates: the expensive per-face extraction happens once per component; the per-occurrence
step is just transforms. Composition is done **lazily at read** (and `inspect_refs` only
composes the selector(s) actually requested), so the descriptor stays tiny and the build
stays fast.

**Contract:** the composed manifest must be byte-equivalent to today's monolithic
`STEP_TOPOLOGY` for the same assembly (same occurrence ids, selectors, world bboxes,
`assemblyMates`) — this is what the ~190 selector tests assert.

> **Implementation note (revised after integration investigation).** Two findings narrow
> the scope of this section:
>
> 1. **`inspect_refs` does not read the GLB topology for selectors.** It re-extracts the
>    full manifest from the **STEP** via `cadgen.step_artifacts.ensure_step_topology_artifact`
>    (which calls `_generate_part_outputs` **without** the package flag). The GLB only carries
>    the lightweight *index* profile (occurrences, no faces/edges). Because the baked
>    `{model}.step` stays on disk, `inspect_refs` keeps working **unchanged** whether or not a
>    package exists — verified live on tom (full 352-occurrence / 18,340-face manifest resolved
>    with the package present). So a byte-equivalent composed manifest is a **performance
>    optimization** (skip the ~29.5 s STEP re-extraction on inspect), **not a correctness gate.**
> 2. **True byte-equivalence is borderline-infeasible** for the full artifact manifest: the
>    component manifests store *rounded* local geometry, and composing rounded values ≠ the
>    monolith's single round-of-product (`_round_transform(M·local)`), plus the buffer columns
>    (`triangleStart`, `segmentStart`, `faceEdgeRows`, …) are global row/buffer indices that
>    are inherently per-component-GLB. The geometric/selector columns compose cleanly; the
>    mesh-index columns do not.
>
> Net: the composition core is **deferred** as a perf lever. The build, `inspect_refs`, and the
> render consumers are all correct without it. When pursued, target the geometric/selector
> columns for the perf win and leave mesh-index resolution to the per-component GLBs.

## 7. Build-side design (`packages/cadgen`)

New path in the shape artifact generation for `kind == "assembly"`:

1. **Component extraction.** Walk the gen_step compound's located children (or the
   gen_step instance list). For each child, take its **unlocated geometry** and compute
   `source-sha = sha256(BinTools.Write_s(unlocated_shape))`. Group children by `source-sha`
   → unique components. Record each child as an occurrence `{id, name, component=source-sha,
   transform=location-matrix, color}`.
2. **Component build (cached by `source-sha`).** For each unique component not already
   present in `components/`, load/mesh the unlocated geometry and emit
   `components/<source-sha>.glb` with embedded local topology (reuse
   `mesh_step_scene` + `extract_selectors_from_scene` + `export_assembly_glb_from_scene`
   on a single-component scene). Skip if the file exists (content-addressed ⇒ a present
   file is valid).
3. **Descriptor emit.** Write `assembly.json` (occurrences + components + `assemblyMates`
   + bbox + `sourceHash`).
4. **Staleness.** The package is fresh when `assembly.json.sourceHash` matches the
   assembly's recomputed source-closure hash. Individual components are validated by the
   presence of their `source-sha`. A removed/changed part changes its `source-sha`
   (old component GLB becomes garbage; prune unreferenced `components/*.glb` on write).

`occurrence_colors` flow exactly as today (per-occurrence overrides land on the descriptor
occurrence, not baked into the mesh).

**Part vs assembly.** A `kind == "part"` model keeps emitting a single `.step.glb` file
(no package) — a part is a single component. Only assemblies get the package.

> **Implementation status (shipped behind `--component-package`).** Realized as
> `cadgen.component_package.build_package_from_compound` and wired into the build pipeline:
>
> - **Source = the compound, not an instance list.** The general path introspects the
>   `gen_step` compound's located children (`child.wrapped.Located(identity)` for local
>   geometry, `child.location` for the transform, `child.label` for the name,
>   `compound.assembly_mates` for mates). This recovers the pre-bake instance structure the
>   shape-only contract discards — no source-path tracking required, so it works for **any**
>   generated assembly.
> - **Geometry-only content hash.** `sha256(BinTools.Write_s(unlocated, withTriangles=False,
>   withNormals=False))`. Excluding mesh data is essential: building a component *meshes* the
>   shared `TShape`, and a triangulation-sensitive hash would change on re-hash and miss the
>   cache (regression-tested). Determinism note: a *cold* `__cadgen__` build can emit a
>   slightly less-deduped package (freshly-STEP-imported geometry serializes differently from
>   the cache-deserialized form — tom: 19 vs 11 components), but it is **correct and
>   self-healing** — the next warm rebuild re-hashes to the canonical set and the freshness
>   gate rebuilds once. The expensive bus is single-instance, so unaffected.
> - **Sibling path, behind a flag.** The package is emitted to `.{model}.step.glb.pkg/` next
>   to the monolithic `.{model}.step.glb` (not *at* it) so the two coexist for verification —
>   a directory at the exact monolith path would collide with the file and with
>   `_reset_step_artifact_dir`'s unlink. The final flip (§13) drops the `.pkg` suffix.
> - **Freshness.** `assembly_package_current(step_path)` = descriptor present + every
>   referenced component GLB on disk; it gates the existing monolith reuse checks, so a
>   missing/partial package forces the emit job while an unchanged source still fast-skips.
> - **Measured on tom (package step only, isolated from the monolith):** **23 s cold**
>   (build all 11 components) → **0.29 s warm** no-op (geometry-only re-hash of all children
>   — the `withTriangles=False` BREP is small, so even the 29 MB bus hashes in well under a
>   second — then every component GLB is reused). Editing one part re-meshes only that
>   component: **spacer 0.31 s · servo (sts3250) 1.19 s · bus 16.2 s** (each = ~0.29 s hash +
>   that component's mesh). See §9 for the full matrix.

## 8. Consumer-side design

All three consumers branch on **file vs directory** at `.{model}.step.glb`:

- **Path is a file** → legacy monolithic GLB (existing code path, unchanged).
- **Path is a directory** → read `assembly.json`, load each referenced
  `components/<sha>.glb` **once** (dedup by sha within the package), build one render node
  per occurrence referencing the shared component mesh, apply `transform` (glTF node
  instancing / `EXT_mesh_gpu_instancing` where available).

Specifics:
- **`packages/cadjs`** (`meshData`, asset loading): the composition layer — load N
  component GLBs, instance per occurrence, expose the composed topology to selection.
  **Done:** `buildComposedPackageMeshData(descriptor, componentMeshDataByCid)` in
  `assembly/meshData.js` — bakes each occurrence's 16-float transform into copied
  vertices/normals (component GLBs are *local*, unlike the world-baked monolith), reverses
  triangle winding for mirror occurrences (negative determinant), rebases indices, and emits
  parts carrying `occurrenceId` + `componentId` + `sourcePartRanges` (component-local id +
  primitiveIndex) for pick recomposition. Pure array math, no `three` import (per the cadjs
  non-React/three-optional rule); unit-tested (transform bake, mirror winding, missing
  component). `partTransformsBaked: true`, so it is drop-in for the monolith renderer path.
- **`viewer`** (`useCadAssets`, `CadViewer`, `referenceSelection`): **pending** — branch
  `useCadAssets` on file-vs-dir, fetch each unique component GLB once (cache by cid),
  `buildMeshDataFromGlbBuffer` per component, call `buildComposedPackageMeshData`, and
  recompose picks via the existing `remapOccurrencePrefix` machinery in
  `selectors/runtime.js` (occurrence id namespaces the component-local selector). Needs the
  running viewer + browser render to verify.
- **`skills/cad/scripts/snapshot`**: **pending** — same composition for headless renders
  (resolve N component GLB URLs, merge in the snapshot bundle).
- **`skills/cad/scripts/inspect` (`inspect_refs`)**: **no change needed** — it re-extracts
  the full manifest from the **STEP** (`ensure_step_topology_artifact`), not the GLB, so it
  is unaffected by the package (§6.1). A package-aware composed reader is only worth adding as
  the perf optimization in §6.1, not for correctness.

## 9. Measured results (tom)

Implemented as `cadgen.component_package.build_package_from_compound` (build side, the
compound-introspection path) and measured end-to-end. tom → **11 component GLBs cover 33
occurrences** (22 repeats deduped). Two regimes, because the package coexists with the
monolith behind the flag today and only fully pays off once the monolith is dropped (§13).

**Per-stage costs (tom, warm `__cadgen__`):** `gen_step` compound 5.3s · STEP write
~19s (142 MB) · mesh 2.2s · **monolithic GLB/topology 26s** (mesh 2.2 · selector extract
~24 · glb) · **package step 0.29s warm / 23s cold**.

### Regime A — render-iterate loop (package-only; what the §13 flip unlocks)

`build_package_from_compound` straight off the `gen_step` compound — no monolithic GLB, no
STEP write. Edits simulated by content-addressed invalidation of the changed component.

| scenario | package step | + `gen_step` (5.3s) = full loop |
|---|---|---|
| cold (build all 11 components) | 23.3s | 28.6s |
| **warm no-op** (re-hash all, reuse all) | **0.29s** | 5.5s |
| edit spacer (m2_spacer, 0.08 MB, 4×) | 0.31s | 5.6s |
| edit servo (sts3250, 2.6 MB, 4×) | 1.19s | 6.5s |
| edit bus (waveshare, 29 MB, 1×) | 16.2s | 21.5s |

The warm floor is **0.29s** — the geometry-only (`withTriangles=False`) BREP re-hash of all
11 children, which excludes the mesh, so even the 29 MB bus hashes in <1s. An edit re-meshes
**only the changed component** (1 built / 10 reused). If the compound is already in memory (a
long-lived dev/viewer process), the loop is just the package-step column: **0.29–16.2s** vs.
the old monolithic **~58s every render**.

### Regime B — current CLI (monolith + package coexist, `--component-package`)

| CLI scenario | total | wall | package job |
|---|---|---|---|
| full `--force`, monolith only (baseline) | 53.5s | 57s | — |
| full `--force`, monolith + package | 51.9s | 56s | 0.26s¹ |
| warm no-op, monolith + package | 52.7s | 57s | 0.28s |
| edit (bus) + package | 69.8s | 73s | 17.4s |

`--component-package` adds **~0.3s** to a normal build — the package is essentially free to
emit alongside the monolith. But the CLI is **dominated by the monolith** (gen 5 + STEP 19 +
mesh 2 + GLB/topology 26 ≈ **52s every run** — tom does not warm-skip the monolith), so an
edit through the CLI today still pays ~52s + the changed component (bus: 70s). The fast inner
loop (Regime A) is realized by the §13 flip: drop the monolith + STEP write for assemblies.

> ¹ Measured before `force` was threaded into the package job. The package cid hashes
> *geometry*, not the mesh/selector code version, so `--force` now also rebuilds every
> component (escape hatch for a meshing-code change) — making `--force --component-package`
> a true cold build (~52s monolith + 23s package). Normal (non-`--force`) builds are unchanged.

## 10. Caching strategy

- **v1 (this design):** per-model `components/` with its own copies — content-addressed by
  `source-sha` *within* the model. Warm rebuilds of a model hit cache (unchanged parts);
  the GLB stage is ~0. Separate copies keep the package self-contained and the build
  logic simple (chosen for clear separation of concerns).
- **Future, orthogonal:** a project-level content-addressed build cache (mesh once by
  `source-sha`, hardlink/copy into each model's `components/`) recovers mesh-once across
  the three tom variants on a clean rebuild **without changing the artifact format** —
  layout and build-cache are independent concerns.

## 11. Migration & compatibility

- The artifact at `.{model}.step.glb` changes from a file to a directory. Every consumer
  adds a one-line file-vs-dir branch; the file branch stays for parts + un-migrated
  assemblies, so the rollout is incremental.
- Existing tracked `.{model}.step.glb` files are deleted and replaced by directories on
  first regen; LFS/`.gitignore` rules that match the file name should match the directory.
- A directory literally named `*.glb` is mildly unusual; verify the bundler/snapshot/LFS
  tooling treats it as a directory (spot-checked during implementation).

## 12. Risks & open questions

- **Selector composition correctness** is the main risk (picking + `inspect_refs`); the
  ~190 selector tests must pass against composed selectors. Mitigate by porting the test
  fixtures to the package format and asserting selector round-trips.
- **glTF instancing in the viewer**: confirm the renderer/material path handles per-node
  transforms + per-occurrence color overrides with shared meshes.
- **Component identity hashing cost**: `sha256(BREP)` of each unique component (incl. the
  26 MB bus) is ~1–2s/build; acceptable vs the 29.5s saved, and only on the unique set.
- **Per-face color components**: if a component has per-face colors that differ per
  occurrence, the shared-mesh assumption needs an override channel (rare; today colors are
  per-occurrence-uniform). Decide whether to support per-occurrence face colors or forbid.
- **STEP side untouched**: this does not reduce `tom.step` (142 MB) or `gen_step`/STEP-write
  time. Pair with bus-stripping if the STEP path also matters.

## 13. Rollout plan — SHIPPED (the flip)

The package is now the **required** render artifact for generated assemblies, at the
canonical `.{model}.step.glb/` path (the `--component-package` flag is gone). Parts keep
emitting the single-file `.{model}.step.glb`. Consumers branch file-vs-dir, so a legacy
monolithic assembly file still renders (backwards compatible).

1. ✅ **Build emit (flipped).** `_generate_part_outputs` emits the package at the canonical
   path for `kind=="assembly"` generated targets and **drops the 29.5 s monolithic
   GLB/topology job**; parts + imported assemblies keep the single-file GLB. `assembly.json`
   carries the full provenance (schemaVersion 2, sourceKind, stepHash, sourceClosure, mesh,
   edgeRendering) so the freshness gates read it like the old embedded manifest.
   CLI-verified: tom full build ~80 s → **~55 s** (monolith eliminated); `.tom.step.glb` is now
   a directory of 11 components.
2. ✅ **Reader + freshness package-aware.** `read_step_topology_index_from_glb` returns the
   descriptor when the artifact is a package directory; `_reset_step_artifact_dir` preserves
   the component cache. 189 Python tests green.
3. ✅ **`inspect_refs`.** A package carries no whole-assembly topology, so
   `ensure_step_topology_artifact` extracts the full manifest on demand from the scene
   (cheap descriptor-only artifact when selectors aren't needed). Verified: full 18,340-face
   manifest + selector resolution with the package present.
4. ✅ **Snapshot render.** `resolve_render_job` emits an inline descriptor + pre-resolved
   per-component asset URLs; `loadSource` (cadjs) fetches each component GLB and composes via
   `buildComposedPackageMeshData`. Bundle rebuilt; **headless render of tom verified correct**
   (full arm, colors, mirror parts) against the monolith appearance.
5. ◐ **Viewer.** `useCadAssets` has a defensive package branch (probe `assembly.json`, fetch
   components, compose; fall back to the single-file path on any miss). Code complete +
   syntax-checked; **interactive render + pick recomposition still need the live viewer to
   verify** (same composition as the verified snapshot, so high confidence).

**Remaining:** viewer interactive verification; migrate the other tom variants (they flip on
next build — backwards-compat covers them meanwhile); confirm LFS treats the nested
`components/*.glb` under the `*.glb` filter; pick recomposition for package picking (the
`sourcePartRanges` + `remapOccurrencePrefix` machinery is in place but unwired).

## References
- Prototype + profiling: session notes; memory `tom-build-perf-levers`.
- Related: `gen-step-shape-only-contract` (why the STEP bakes), `assembly-mates-on-shape`
  (mates ride on the compound, harvested at export).
