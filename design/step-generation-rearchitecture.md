# STEP generation rearchitecture: GLB-default, STEP on-demand

Status: design / proposal. Clean break — **no backwards compatibility**; existing
`.step` files and committed GLB artifacts are regenerated/refactored under the new scheme.

## 1. Summary

Flip the default output of a `gen_step` generator from a **text STEP file** to the
**render artifacts** (a single-part GLB or a component-GLB package), and make the text
STEP an **opt-in export** like `--stl` / `--3mf` / `--glb`.

**The CLI has exactly two input kinds, each with one clean path to GLB:**

```
  before:  python  ──►  STEP (eager)  ──►  GLB        (3 steps, the STEP is a needless waypoint)
           STEP    ──────────────────►    GLB

  after:   python  ──►  GLB                           (no intermediate STEP)
           STEP    ──►  GLB                           (UNCHANGED — STEP files render exactly as today)
           python  ──►  STEP   only when --step is asked for (just another output format)
```

The whole point is to delete the messy `python → STEP → GLB` waypoint. The GLB path no
longer routes through a STEP at all; STEP becomes a sibling output of GLB/STL/3MF, not its
parent.

Four coupled changes:

1. **`gen_step` builds GLB by default, not STEP.** The eager `export_build123d_step_scene`
   write is removed from the default path (today's `--skip-step-write` behavior becomes the
   default; the flag is retired).
2. **The step CLI gains a `--step <output>` export option**, mirroring the existing
   `--stl/--3mf/--glb` sidecar options, that writes the text STEP from the in-memory scene
   the build already holds. STEP is produced on demand, when a human or external tool needs
   interchange/fabrication.
3. **The viewer indexes Python generators** (a `.step.py` naming convention) and serves their
   GLB render artifacts from `__cadgen__`, instead of pairing a committed `.step` file with
   a committed `.{model}.step.glb` beside it. **Direct STEP-file inputs are unchanged** —
   they still mesh to GLB for inspect/render and present in the viewer exactly as today.
4. **`__cadgen__` becomes a per-folder, content-addressed artifact store** (§4.6) so the
   inevitable duplication — a `.step.py` and the STEP you export from it produce *identical*
   GLBs — collapses to one cached entry, and parts shared between sibling models in a folder
   are meshed once.

**Design principle (load-bearing): the step CLI stays format-agnostic; the viewer and the CAD
skill are the opinionated layer.** The CLI takes a generator (any `.py` with a `gen_step`
marker) or a STEP file and produces *explicitly requested* outputs. It does not require a
`.step` file to exist, does not assume the `.step.py` suffix, and commits nothing. The
`.step.py` convention and the `__cadgen__` artifact store live entirely in the
viewer/skill layer on top of that agnostic CLI.

This repo is in beta: **hard migration is acceptable** and assumed throughout. GLB artifacts
are regenerated on the fly, so stale cached artifacts are harmless (they are overwritten or
left unreferenced) — none of this needs compatibility shims or careful cache eviction.

## 2. Motivation

Measured on tom (after the component-GLB flip):

| | time | size |
|---|---|---|
| eager text STEP write (`export_build123d_step_scene`) | **16.3s** | 149 MB |
| the *same geometry* as binary BREP (`BinTools`) | **0.27s** | 26 MB |

The text STEP is **~60× slower and ~6× larger** than the geometry it encodes — it's an ISO
interchange format, not a build artifact. After the component-GLB flip:

- **Render** uses the component package, never the STEP.
- **inspect** re-runs `gen_step` (~6s) for generated assemblies; it does not read `tom.step`.
- **URDF** composes top-down from per-part STEPs + committed 3MF visual meshes; it does not
  read the *composed* `tom.step`.

So the composed `tom.step` is now a pure interchange/fabrication-source artifact that only
some consumers need, only sometimes — yet every full build pays 16s to write it. A typical
part edit is **~31s today**; without the STEP write it is **~15s** (measured). The STEP cost
is now the single largest item on the hot path, and it buys nothing the default workflow
consumes.

## 3. Current architecture (grounded)

- **Catalog discovery is generator-first, not file-first.** `cadgen.catalog.iter_cad_sources`
  scans `*.py` files, keeps those whose bytes contain the `gen_step` marker
  (`_looks_like_generator_script`), and derives `step_path = script.with_suffix(".step")` and
  `cad_ref = cad_ref_from_step_path(step_path)`. **The `.step` file is never checked for
  existence during discovery** (`catalog.py:_read_python_source`). Existence is only required
  for *imported* (non-generated) STEP sources (`step_targets.py`). This is the key enabler.
- **Build** (`generation.py`): `run_script_generator` runs `gen_step()` → a baked
  `Compound`, then `_write_shape_step_payload` eagerly writes the 149 MB STEP
  (`export_build123d_step_scene`), then `_generate_part_outputs` meshes the scene and emits
  the GLB/package + any `--stl/--3mf/--glb` sidecars. `--skip-step-write` already short-
  circuits the STEP write and builds the scene in memory (`build_build123d_step_scene`).
- **Artifact paths** live *beside* the `.step`: `.{model}.step.glb` (a file for parts, a
  directory for assembly packages), via `part_glb_path` / `explorer_artifact_path_for_step_path`.
- **`__cadgen__`** (`step_scene.py`) is a per-STEP, content-addressed cache of *parsed
  geometry* — `__cadgen__/<name>.step/v2-<stepHash>/{scene.json, prototype-N.bin}` (binary
  BREP). It accelerates `import_step` / `load_step_scene`. It is gitignored, keyed by STEP
  content, and not currently a render-artifact store.
- **Viewer** (`viewer/src/server/catalog/cadDirectoryScanner.mjs`) scans for `.step/.stp` (+
  stl/3mf/glb/dxf/urdf/…), reads each `.step` for a `gen_step()` call to find its same-stem
  `.py`, fetches `.{model}.step.glb`, and reads `entryKind` from the embedded topology to
  label part vs assembly.

## 4. Proposed architecture

### 4.1 `gen_step` → GLB by default

The default build for a generated target emits:

- the **render artifact** — single-part GLB (parts) or component-GLB package (assemblies);
- a **fast binary geometry cache** (binary BREP, ~0.27s) for non-hot-path scene reloads;
- a small **inertial-metadata JSON** sidecar (mass / COM / volume / bbox per part) for URDF;

and **does not write the text STEP**. `--skip-step-write` is removed; no-STEP is the default.
Freshness keys on `sourceClosureHash` (generator source + import closure — already recorded in
the package descriptor), not `step_file_hash` of a file that no longer exists by default.

### 4.2 STEP export as an opt-in CLI option

Add `--step <output>` mirroring `--stl/--3mf/--glb`:

- `StepImportOptions.step` (`catalog.py`) → `EntrySpec.step_export_path` →
  an `_ArtifactJob("STEP", …)` in `_generate_part_outputs` that calls
  `export_build123d_step_scene` **from the in-memory scene** the build already has.
- No new geometry work: the scene exists; the job only pays the 16s text serialization,
  and only when the user asks.

The CLI is symmetric: a generator produces whatever outputs are requested
(`--glb`, `--stl`, `--3mf`, `--step`, …); STEP is no longer privileged as "the" output.

### 4.3 The `.step.py` convention (viewer/skill only)

Top-level renderable generators are named `<model>.step.py` (e.g. `tom.step.py`). The
**viewer** indexes these by suffix — a renderable model is *a generator plus its cached GLB*,
with no `.step` file required. The CLI remains agnostic: it still discovers any `.py` with a
`gen_step` marker, so `.step.py` is a viewer/skill convention, not a CLI requirement. The
catalog's `script → step_path` derivation changes from `with_suffix(".step")` to "strip the
trailing `.py`" so `tom.step.py → tom.step` (a *logical* cad_ref/output path that need not
exist on disk).

### 4.4 `__cadgen__` as a per-folder, content-addressed artifact store

Today `__cadgen__` is per-STEP-file (`__cadgen__/<name>.step/v2-<stepHash>/…`) and caches
only parsed geometry, while render artifacts live as committed `.{model}.step.glb` blobs
beside the source. Both go away. Restructure `__cadgen__` into a **per-folder,
content-addressed** store that holds *all* derived artifacts, keyed by **geometry content
hash** (the unlocated-shape BREP hash already used for component cids), with a thin
per-model descriptor as the glue:

```
models/robots/tom/
  tom.step.py                       # generator (source of truth)
  tom_with_gripper.step.py          # sibling generator, shares most parts
  __cadgen__/                     # gitignored, per-folder, content-addressed
    components/<geomHash>.glb        # one GLB per unique part geometry — SHARED in folder
    geometry/<geomHash>.brep         # parsed binary BREP (fast scene reload; was prototype-N.bin)
    topology/<geomHash>.json         # full selector manifest for inspect (lazy)
    models/
      tom/assembly.json              # occurrences -> components[geomHash] + transform
      tom_with_gripper/assembly.json
```

**Why this kills the duplication.** Every input that yields the same geometry resolves to the
same content-addressed entries:

- `tom.step.py` builds the compound → each unique part hashes to `geomHash` → `components/<geomHash>.glb`.
- Exporting `tom.step` via `--step`, then meshing it, hashes to the **same** `geomHash` → cache hit, **no re-mesh, no duplicate GLB**.
- A hand-authored `tom.step` file loaded directly → same `geomHash` → same entry.
- `tom_with_gripper.step.py` reuses tom's servos/brackets → those `geomHash`es already cached → meshed once for the whole folder.

So the descriptor (`assembly.json`) is the only per-model artifact; the heavy GLBs are shared
by content within the folder. A single-part model is just a degenerate package: one occurrence
referencing one `components/<geomHash>.glb`.

**Per-folder, not global (deliberately).** Each folder owns its `__cadgen__`; dedup is
*within* a folder. No repo-global cache — that keeps invalidation, ownership, and gitignore
trivial, and avoids cross-folder coupling. Cross-folder reuse (the three tom variants live in
one folder, so they already share) is left as a future global-cache option, not built now.

**No eviction needed.** Artifacts are content-addressed and regenerated on the fly, so a stale
`components/<geomHash>.glb` is simply unreferenced by current descriptors — harmless, and
overwritten if its hash recurs. Optional opportunistic pruning of unreferenced entries, never
required for correctness.

**Keying summary:** generated and direct/exported STEP inputs both content-address their GLBs
by **geometry hash**, so they share. The model-level invalidation key (does this model need a
rebuild at all?) is `sourceClosureHash` for generators and the STEP content hash for imported
files — but the *artifacts themselves* are geometry-keyed, which is what makes the dedup work.

#### Components must be *clean* — no embedded provenance

Content-addressing only works if a component's bytes are a pure function of its geometry +
mesh tolerances. Today the embedded `STEP_topology` manifest also carries **source provenance**
(`sourceKind`, `sourcePath`, `sourceHash`, `sourceClosureHash/Files`, `stepPath`, `stepHash`,
`generatedAt`) — which is exactly what makes two byte-different GLBs for the *same* geometry
(a `.step.py` vs. the `.step` exported from it differ only in `sourcePath`/`stepHash`/
`generatedAt`). That is the sole reason the current package needs a *separate* geometry-BREP
hash instead of just hashing the GLB.

**Strip the provenance from components and move it to the descriptor.** A component then keeps
only what is deterministic from geometry, and hashing the file *is* content-addressing:

| keep in the component (deterministic) | move to the model descriptor (source-specific) |
|---|---|
| `schemaVersion`, `profile`, `entryKind=part`, `capabilities` | `sourceKind`, `sourcePath`, `sourceHash` |
| selector tables + `faces`/`edges`/`occurrences`/`shapes` | `sourceClosureHash`/`sourceClosureFiles` |
| `bbox`, `stats`, `mesh` tolerances, `edgeRendering` | `stepPath`, `stepHash`, `generatedAt` |
| (the geometry + its local topology) | `assemblyMates` (assembly-level semantics) |

Principle: **a component is the immutable "what" (geometry); the descriptor is the mutable
"where it came from / when / how it's placed."** Clean leaves + a provenance-carrying
descriptor is the content-addressed-store pattern, and it is what lets all input kinds dedup.

Note on the hash: the *file* hash of a clean GLB is the complete content address — and unlike a
bare geometry-BREP hash it also captures the mesh tolerance (the same shape meshed coarser is
correctly a different file). But to *skip the re-mesh* the cache must be probed *before*
meshing, so the pre-mesh key is the cheap one: **hash the source file** for file-backed parts
(literally the source-side version of "hash the whole file"), or the geometry BREP for
procedural parts. The clean GLB's own hash then addresses the produced result.

*Further option:* split the heavy selector tables into a separate content-addressed
`topology/<geomHash>.json` (inspect-only), leaving the component GLB as just *mesh + pick-ids*.
The render path never reads the selector tables, so rendered components get even smaller and
more shareable.

### 4.5 The agnostic-CLI / opinionated-viewer split

| layer | responsibility | opinions |
|---|---|---|
| **step CLI / cadgen** | given a source (generator or STEP) + explicit output requests, produce them | none: no `.step.py`, no required `.step`, no committing, no cache policy |
| **viewer + CAD skill** | discover `.step.py`, store/serve artifacts from `__cadgen__`, render-first iteration, trigger generation on cache-miss | all naming, caching, and workflow conventions |

This keeps cadgen reusable and unopinionated while letting the viewer be as opinionated as it
wants — the same principle behind keeping `packages/cadjs` non-React.

### 4.6 Direct STEP-file inputs — unchanged

A `.step`/`.stp` file with no generator keeps today's workflow exactly: it *is* the source,
so it stays on disk, and the CLI meshes it to GLB for inspect/render. The only change is
*where the GLB lands* — the same per-folder content-addressed `__cadgen__` (§4.4) instead of
a `.{model}.step.glb` beside it — and that change is invisible to the user. The viewer
presents direct STEP files just as it does now (a `.step` entry that renders its GLB). Because
the GLB is geometry-keyed, a direct `tom.step` and a `tom.step.py` that produce the same shape
**share the cached GLB** — the dedup is automatic across input kinds, not special-cased.

The only asymmetry: a generator carries the *instance structure* (the compound's located
children) so it produces a proper component **package**; a flat baked STEP file has no
instancing, so it meshes to a single GLB (or a package whose components are content-addressed
per solid). Both still land in `__cadgen__` and dedup by geometry hash; the generator path
simply gets better part-level reuse for free.

### 4.7 One representation: `descriptor + components` (a part is a degenerate assembly)

**There is no longer a "part" type distinct from an "assembly" type.** Every model — part or
assembly, generated or imported — is *a descriptor plus content-addressed components*. A part
is simply the degenerate case: one occurrence referencing one component. This is the structural
keystone of the rearchitecture (it is what makes everything else collapse):

- **Delete `spec.kind` and every `kind == "assembly"` / `is_assembly_package` / file-vs-dir
  branch** across `generation.py` (the emit fork), `step_artifacts.py`, the catalog, `cadjs`,
  the snapshot, and the viewer. There is one emit path and one render-load path.
- **`part_glb_path` (file) vs the package directory** stops being a distinction — the model's
  artifact is always a descriptor + components in `__cadgen__`.
- **Likely deletes `assembly_spec.py`** and the part/assembly kind plumbing entirely.

Two consequences to design for (see §8):
- A single part no longer has a standalone `.glb` to hand to external tools — an explicit
  monolith/tarball export covers that.
- `build_package_from_compound` assumes a `Compound`; imported STEP files have none, so it must
  also accept a parsed `LoadedStepScene` (a one-component "package") for the STEP→GLB path.

> **⚠️ Design finding (S1 paused).** Implementing this surfaced that *fully* deleting `spec.kind`
> is not clean: the part/assembly distinction is **emit-time metadata, not derivable from the
> shape**. The package emit must know whether to introspect a compound's children as separate
> placed occurrences (assembly → dedup repeats) or treat the whole shape as one rigid component
> (part). A **multi-solid part** (a bracket authored as several solids in one `.step`) looks
> exactly like an assembly of instances, so inferring kind from "compound with >1 child"
> misclassifies it — splitting the part's faces across several components and breaking its
> unified selectors. `_shape_payload_entry_kind` already hits this; the kind ultimately comes
> from the generator's metadata.
>
> **Recommended resolution:** keep `spec.kind` **only at emit time** (from generator metadata)
> to choose introspect-children vs single-component, and unify everything *downstream*
> (freshness, readers, consumers, render) onto `descriptor + components` so the file-vs-dir and
> `kind=="assembly"` branches still collapse. This is "unify the representation, keep a minimal
> emit signal" rather than "delete `spec.kind` entirely." Needs the user's call before the
> ~40-reference sweep + the browser-verified consumer changes (parts become package directories).

## 5. Tradeoffs

The center of this proposal. Each axis is a real win paired with a real cost.

### 5.1 Build / edit speed — **strong win**
~16s off every full build; a typical part edit drops **~31s → ~15s**; render-first
iteration. The binary BREP cache (0.27s) replaces the STEP for internal scene reloads, so the
geometry is never lost — it's reproducible from source (`gen_step` ~6s) or the cache.

### 5.2 STEP becomes on-demand — **win + cost**
- **Win:** pay the 16s only when interchange/fabrication actually needs it.
- **Cost:** a STEP is not always present. External/fabrication workflows gain a required
  explicit step (`--step`); a user who *expects* a `.step` to exist must learn to ask for it.
  Discoverability matters — the failure mode is "where's my STEP?", which docs + a clear
  CLI/skill affordance must pre-empt.

### 5.3 `__cadgen__` as a per-folder, content-addressed store — **win + cost**
- **Win — duplication collapses.** Geometry-keyed artifacts mean a `.step.py` and the
  `.step` exported from it share one cached GLB (no re-mesh), and parts shared between sibling
  models in a folder mesh once. This directly answers the "the exported STEP has the same GLB"
  duplication: it's deduped by construction, not by a special case.
- **Win — nothing committed.** The repo sheds large per-model LFS GLB/STEP blobs; artifacts
  regenerate on the fly, so the committed-artifact-staleness problem disappears entirely. Stale
  cache entries are unreferenced and harmless — no eviction logic required.
- **Cost — cold start.** A fresh clone / CI has an empty cache → **you must build before you
  can view** (~15–20s for tom on first open). The viewer must trigger generation on
  cache-miss (progress UI), and CI/release should pre-warm. "Clone and view instantly" is
  traded for "clone, build once, view."
- **Cost — per-folder, not global.** Deliberately simple: dedup is within a folder only, so
  the same part used in two *different* folders is meshed twice. Acceptable now (the three tom
  variants share a folder); a global content-addressed cache is a clean later upgrade since
  the keying is already geometry-hash.
- **Cost — two keying notions to keep straight.** Artifacts are geometry-keyed (for dedup);
  model freshness is `sourceClosureHash`-keyed (generators) or STEP-content-keyed (imported).
  Conflating them is the easy bug — the descriptor is the bridge between the two.

### 5.4 The `.step.py` naming convention — **win + cost**
- **Win:** self-documenting (a `.step.py` clearly declares "STEP-class renderable model"); the
  viewer can index by suffix without reading file contents (faster scan); cleanly decouples
  "renderable model" from "has a `.step` file."
- **Cost / gotcha — dotted module names.** A file `tom.step.py` has module name `tom.step`,
  which contains a dot, so it is **not importable as a normal module** (`import tom.step`
  resolves to a submodule, not this file). The CLI loads generators **by path**
  (`importlib.util.spec_from_file_location` in `_load_generator_module`), so `.step.py`
  generators execute fine. But a generator that **imports another generator** by module name
  breaks. Resolution: reserve `.step.py` for **top-level renderables**; keep shared/sub-
  assembly modules as ordinary importable `.py` (e.g. `robot_common/…`, `assemblies/base_link.py`).
  A module that must be *both* independently renderable *and* imported by another generator
  needs a path-load or a thin wrapper — a real but narrow wrinkle to call out.
- **Cost:** it's a new convention to adopt + migrate, and the double suffix is mildly unusual
  to tooling (test discovery, linters) that assumes one extension.

### 5.5 Freshness / provenance — **rework**
`step_file_hash` (hash of the on-disk STEP) is gone from the default path. Freshness moves to
`sourceClosureHash` (generator source + import closure), which is the *correct* invalidation
key for generated models anyway — the STEP hash was only ever a derived proxy. Imported
(non-generated) STEP sources keep `step_file_hash` (the file *is* the source). The package
descriptor already carries `sourceClosureHash`, so this is incremental.

### 5.6 URDF / fabrication consumers — **mostly fine + small rework**
- URDF visual meshes (committed 3MF) and assembly composition (per-part STEPs) **don't read
  the composed `tom.step`** — unaffected.
- URDF inertials (mass / volume × density) re-import per-part STEPs today; cache
  `{mass, com, volume, bbox}` in the build-time metadata sidecar so URDF reads cached numbers
  — strictly better than today (drops a redundant STEP re-import).
- Assembly STL/3MF export derive from the in-memory scene (the export jobs already take a
  `LoadedStepScene`), so they work without an on-disk STEP.

### 5.7 inspect — **neutral / win**
Already re-runs `gen_step` for generated assemblies and reads the GLB for parts. No STEP
needed; unaffected by the flip.

### 5.8 Interoperability with non-Python / imported geometry — **unchanged**
Imported `.step/.stp` files (authored elsewhere, no generator) keep their current path: the
file *is* the source, it must exist, and the CLI meshes it to GLB as today. The rearchitecture
only changes the *generated* path.

## 6. Approved simplifications (Tier A + B)

These ride on the rearchitecture and are **approved as part of the plan**. IDs match the
simplification sweep. Sequence is fixed by dependency: **S2 + S3 (enabling primitives) → S1
(keystone) → S4 → B-tier deletions**, which then fall out mostly automatically.

> **Implementation status — SHIPPED.** S1–S6 + the per-folder cache + the schema bump all
> landed and are verified (232 Python, 375 cadjs, 386 viewer tests; tom + generated part/assembly
> render end-to-end; inspect works on packages).
> - **S1 ✅** — part & assembly unified onto `descriptor + components`. `spec.kind` survives only
>   as the *emit-time* signal (single-component vs introspect-children), resolved from generator
>   metadata / STEP inference; the durable, consumer-facing kind is `entryKind` on the descriptor
>   (the §4.7 design finding). Freshness gates, inspect (cheap descriptor summary + on-demand
>   selector extraction), render, and `--step` all run off the unified package.
> - **S2 ✅** clean byte-deterministic components. **S3 ✅** STEP-on-demand default + `--step`.
> - **S4 ✅** — `assembly_composition.py` (707 lines) + `_AssemblyArtifactContext` +
>   `_assembly_composition_for_spec` + `_report_selector_manifest_change` deleted (occurrence
>   colors ride on the child compounds, harvested by the exporters — no mediator needed).
> - **S5 ✅** — the monolith `export_glb`/`export_glb_with_topology` job + the whole-model
>   `SelectorBundle` return path are gone. ⚠️ `export_assembly_glb_from_scene` and
>   `build_step_topology_index_manifest` are **repurposed, not deleted** — the component builder
>   reuses the former and the descriptor *is* the index manifest, so the original "delete them"
>   wording is superseded.
> - **S6 ✅** — the cadjs/viewer self-contained (monolith) mesh paths
>   (`buildSelfContainedAssemblyMeshData`, `assemblyUsesSelfContainedMesh`, the
>   `buildSelfContainedAssemblyMeshState` viewer hook + tests) are deleted.
> - **Per-folder `__cadgen__`** live + gitignored + skipped by the viewer scanner.
>   **`packageSchemaVersion = 2`** stamped on the descriptor (independent of
>   `STEP_TOPOLOGY_SCHEMA_VERSION`).
> - **P6 viewer/catalog ✅** — `validateStepTopologyArtifact`, `readStepCatalogMetadata`,
>   `assetForPath`, and `collectCadSourceFiles` are all package-directory-aware; the scanner
>   treats `.{model}.step.glb/` as the artifact anchor and skips `__cadgen__`.
>
> **S7 ✅** — the legacy path helpers (`legacy_part_glb_path` / `existing_part_glb_path` /
> `native_component_glb_dir`, the explorer-dir helpers in `catalog.py`, and
> `_reset_step_artifact_dir`'s stale-dir cleanup) are deleted; `part_glb_path` resolves the
> `__cadgen__` package directly and the viewer ignores dot-prefixed (hidden) files and
> directories generically instead of pattern-matching legacy artifact names.
>
> **Superseded:** **S8** (delete the `index`
> `STEP_TOPOLOGY` profile / `build_step_topology_index_manifest`) is **superseded** — the
> rearchitecture made the index profile the canonical package descriptor, so it is load-bearing,
> not dead. `--skip-step-write` (and the unused `--write-step-after-artifact`) are fully
> retired: `--source-path` alone selects generator mode in `cadgen.step_artifact`.

### Tier A — structural (change the model)

- **S1 — Unify part & assembly into `descriptor + components`** (§4.7). ⚠️ **Paused** — survey
  found the part/assembly distinction is *emit-time metadata*, not cleanly inferable (a
  multi-solid part looks like an assembly of instances). Fully deleting `spec.kind` loses the
  signal the emit needs. Open question in §4.7 / §8 before the 40-reference sweep + the
  browser-verified consumer changes. `L · high`
- **S2 — Clean components** (§4.4): ✅ **shipped**. Provenance stripped from embedded
  `STEP_TOPOLOGY` (+ `stats.timingMs`) → components are byte-deterministic and content-addressable.
- **S3 — STEP-on-demand default** (§4.1/§4.2): ✅ **shipped**. `skip_step_write` plumbing +
  `--skip-step-write` flag deleted; `--step` / `--output` write STEP on demand from the
  in-memory compound.
- **S4 — Delete `assembly_composition.py`** (~707 lines) + `_assembly_composition_for_spec` +
  the `_AssemblyArtifactContext` mediator. Entangled with S1 (still used by the monolith path
  that S1 removes). Follows S1. `L · high`

### Tier B — dead-code deletions (mostly automatic once Tier A lands)

- **S5 — Delete the monolithic assembly GLB export + redundant whole-scene mesh:**
  `export_assembly_glb_from_scene`, the package-path `mesh_step_scene` call, the
  `export_glb_with_topology` fallback, and the `SelectorBundle` return path. `S · low`
- **S6 — Delete the cadjs/viewer self-contained (monolithic) mesh paths:**
  `buildSelfContainedAssemblyMeshData` + tests, `assemblyUsesSelfContainedMesh` branches in
  `source.js`, `buildSelfContainedAssemblyMeshState` in `useCadAssets`. `S · low–med`
- **S7 — Delete legacy GLB path helpers/fallbacks:** ✅ **shipped**. `legacy_part_glb_path`,
  `existing_part_glb_path`, `native_component_glb_dir`, the `catalog.py` explorer-dir helpers,
  and `_reset_step_artifact_dir` are deleted; the viewer skips dot-prefixed files/dirs
  generically. `S · low`
- **S8 — Delete the `index` `STEP_TOPOLOGY` profile; one canonical manifest schema:** remove
  `build_step_topology_index_manifest` and the index-vs-selector branching in the reader.
  *(depends S2.)* `M · med`

Tier C/D items (freshness-gate collapse, descriptor writer merge, path-helper consolidation,
inspect/URDF/mates cleanups) are tracked separately and land after Tier A/B.

## 7. Migration (hard break — acceptable in beta)

No compatibility shims, no dual-format readers, no graceful fallbacks. The repo is in beta;
delete the old scheme and regenerate. Because GLB artifacts regenerate on the fly, leftover
old artifacts are harmless (overwritten or ignored), so migration is "delete + rebuild," not a
careful data migration. In dependency order:

1. **CLI/cadgen:** make no-STEP the default; add `--step <output>`; retire `--skip-step-write`;
   emit the binary BREP cache + inertial metadata; move freshness to `sourceClosureHash`;
   route all derived artifacts into the per-folder content-addressed `__cadgen__` (§4.4).
2. **Viewer/skill:** index `.step.py` (and direct `.step` files, unchanged); serve GLBs from
   `__cadgen__`; trigger generation on cache-miss; delete the committed-`.{model}.step.glb`
   code path outright.
3. **Repo:** rename top-level generators `<model>.py → <model>.step.py`; **stop committing**
   `.{model}.step.glb` and generated `.step` files; gitignore `__cadgen__`. Old committed
   `.step`/GLB artifacts are simply removed — they regenerate on demand. Hand-authored
   (imported) `.step` files stay committed (they are source). The user refactors/regenerates
   the generated ones as prompted.
4. **CI/release:** pre-warm `__cadgen__` and produce on-demand `--step` exports for the
   release bundle, so published viewers and external CAD consumers still get artifacts.

## 8. Risks & open questions

**Standing caveats (not decisions, just keep in view):**
- **Binary BREP is internal-only** — a fast cache, not an interchange format; never let it leak
  to anything expecting portable STEP.
- **External consumers lose committed artifacts** — anyone who did `git lfs pull` and opened a
  `.step`/`.glb` now needs `--step` / a cache-warm; document the on-demand workflow prominently.
- **Cross-machine hash determinism** — `sourceClosureHash` and the geometry hash must be stable
  across clones/CI for cache hits; verify neither folds in absolute paths or mtimes.

### 8.1 Implementation questions to resolve

The decisions below fork the implementation. **⛔ marks the ones that block starting**; each
carries a suggested default.

#### Cache & hashing
- ⛔ **Where does `__cadgen__` live / at what level is geometry shared?** A) per-model-root
  folder (all generators in the dir share); B) per-input-file sibling; C) today's per-STEP
  `<step>.step/v2-<hash>/`. **Default A** — deepest common ancestor maximizes sibling-model dedup.
- ⛔ **Do file-backed and procedural parts share one content-address scheme** (so a `.step.py`
  dedups against the `.step` it exports)? A) separate keys, never collide; B) hash the loaded
  STEP geometry, not the file; C) two-level: geometry hash for dedup + source hash in descriptor
  for freshness. **Default C.**
- **Cold-vs-warm BREP instability (19 vs 11 components)** — accept self-healing, canonicalize, or
  version it? A) accept current `_content_hash_shape` (cold emits extras, warm reconciles);
  B) canonicalize BREP so 19==11; C) canonicalization-version in the key. **Default A** (already
  approved as self-healing in §4.4).
- **Is mesh tolerance in the component key or only descriptor metadata?** A) metadata only;
  B) `sha256(geom+linear+angular)`; C) a freshness predicate. **Default A** (component = geometry+mesh).
- **Do the parsed-BREP cache and the component-GLB store unify?** **Default: separate subfolders**
  (`components/<h>.glb` render vs `geometry/<h>.brep` internal), keyed independently; unify later.
- **Eviction policy?** A) none; B) per-model pruning (today's `component_package.py`); C) folder
  orphan scan; D) TTL/LRU. **Default B** + a future `cadgen cache clean` sweep.

#### Descriptor & schema
- ⛔ **`assembly.json` schema + how components are referenced** — A) colocated relative
  `components/<cid>.glb`; B) descriptor at `__cadgen__/models/<m>/assembly.json` → `../components/<cid>.glb`;
  C) absolute/URL. **Default B** (enables per-folder dedup; relative keeps the folder relocatable).
- **`PACKAGE_SCHEMA_VERSION`** (undefined ref at `component_package.py:297`) — define `=1`,
  independent of `STEP_TOPOLOGY_SCHEMA_VERSION`. **Default: A**, and fix the latent crash now (S16).
- **`assemblyMates` inlined or sidecar?** **Default: inlined** (small; needed by viewer picks + URDF joints; keeps the package self-contained).
- **Inertial metadata (`mass/com/volume/bbox`) cached where?** A) in descriptor; B) `inertials/<cid>.json`;
  C) glTF extension; D) keep re-importing per-part STEP. **Default D for now**, add `--inertial-metadata` export later.

#### STEP-on-demand & freshness
- ⛔ **Retire `--skip-step-write` as a hard delete or a deprecation path?** A) delete flag + all
  callers at once; B) silent no-op; C) flip default + add `--step`, warn on `--skip-step-write`,
  delete in follow-up. **Default C** (lets tests/CI drop the flag at their pace).
- **Standalone `--step`: re-run `gen_step` or load cached BREP?** A) always re-run (~15–20s);
  B) always cache (~0.27s); C) fresh-cache-else-rebuild. **Default C.**
- **Which freshness predicate survives?** **Default: `sourceClosureHash` (generated) /
  `step_file_hash` (imported), read descriptor-only** — delete the embedded-manifest fallback chain (`generation.py:1999–2014`).
- **Binary-BREP cache keyed by geometry hash or `sourceClosureHash`?** **Default: geometry hash** (model freshness checked separately).
- **`--step` baked or XCAF-instanced?** **Default: baked** (reuses `export_build123d_step_scene`; instancing is a later optimization, optionally `--step=baked|xcaf`).

#### `.step.py` & catalog
- **Discovery marker — the `.step.py` suffix or the `gen_step` byte marker?** **Default: the
  `gen_step` marker** (CLI stays agnostic; the suffix is a viewer/skill optimization, not a discovery gate).
- **Which generators get renamed?** **Default: only top-level renderables** (`tom.py → tom.step.py`);
  sub-assemblies / `robot_common` stay importable `.py`; generators load by path only.
- **Migration without breaking imports** — audit-grep for importers of `tom.py` (expected zero —
  variants are entry points), then rename, stop committing `tom.step`/`.glb`, gitignore `__cadgen__`.
- **Catalog changes for imported flat `.step`?** **Default: none** — catalog stays agnostic; dedup/freshness live downstream.

#### Part/assembly unification (S1)
- ⛔ **Delete `spec.kind` now or phase it?** **Default: keep the part/assembly distinction until
  S1's two blockers ship** (external single-GLB export; imported-STEP packaging), then flip atomically.
- **External single-GLB export mechanism** — A) `--glb-monolith <out>` merged single GLB;
  B) `--tarball-package`; C) both. **Default A** (mirrors `--stl/--3mf/--step`; what external CAM/fab consume).
- **Imported flat STEP → one-component package or per-solid?** **Default: one component, single occurrence** (decomposition is a generator-side concern).
- **How does the viewer tell single-part from assembly once `kind` is gone?** A) explicit
  `presentationHint`; B) infer from occurrence count (`==1` → part); C) always assembly UI.
  **Default B** (no new field; pure function of the descriptor).

#### Consumers & build-on-demand
- **Inspect topology — descriptor-truth or re-extract?** A) re-run `gen_step` / re-extract (simple,
  slow first inspect); B) content-addressed `topology/<geomHash>.json` sidecar; C) lazy `topology.glb`.
  **Default A** now (composition is the §6.1 future perf lever).
- **On viewer cache-miss, who builds + how is progress shown?** **Default: viewer spawns the CLI**
  and streams stdout (mirrors snapshot); CI pre-warm for published builds.
- **Simultaneous builds of the same model?** A) filesystem `.lock`; B) in-memory viewer lock;
  C) optimistic with atomic descriptor `mv`. **Default C** (redundant builds are rare and cheap once cached).

## 9. Recommendation

Adopt it. The agnostic-CLI / opinionated-viewer split is the right shape, and the catalog is
**already** generator-first, so the heavy lifting (discovery without a `.step` file) is done.

Sequence: (1) CLI default-no-STEP + `--step` export + binary BREP/metadata + `sourceClosureHash`
freshness — all verifiable in cadgen with the existing test suites; (2) viewer `.step.py` +
`__cadgen__` artifacts + build-on-demand — needs the live viewer to verify; (3) repo migration
(rename generators, drop committed artifacts). It is the same philosophy as the component-GLB
flip — stop paying a heavy serialization on the hot path for an artifact only some consumers
need, and make it on-demand — applied one level up, to the STEP itself.

## References
- `design/component-glb-artifacts.md` (the flip this builds on).
- Measured STEP-vs-binary-BREP cost; STEP-consumer audit (session notes).
- Memory: `gen-step-shape-only-contract`, `tom-build-perf-levers`, `venv-cadgen-points-to-main-checkout`.
