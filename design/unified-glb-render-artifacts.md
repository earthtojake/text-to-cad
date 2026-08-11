# Design: Unified GLB Render Artifacts (Implicit, DXF) — Amended, partially executed

Status: **in progress** (reviewed + amended 2026-08-05; four scope changes applied; decisions settled in §0.1; execution started) · Branch `claude/step-generation-status-tracking-1b7ff6` (worktree `/Users/jakefitzgerald/robots/text-to-cad/.claude/worktrees/pr-180-review-test-dab541`) · Supersedes the original in full — you do not need to read it.

**G-code is out of scope for this batch** (§0.1). The title keeps Implicit + DXF only.

---

## 0.0 EXECUTION STATUS — COMPLETE

**All phases are done** (0, 2, 3a, 3, 4). G-code was deferred out of this batch by decision
(§0.1), so the renderable set is **GLB + 3MF + STL + G-code** and the render-path count went
**six → two**, not six → one. §13's meta-goal target is therefore not reached yet; that is
expected, not a shortfall.

Nothing is pushed. Branch `claude/step-generation-status-tracking-1b7ff6`.

### Rebase onto `release/0.4.0` (2026-08-08)

The branch was squash-merged onto upstream `66c08036` and the resulting conflicts resolved.
Upstream had meanwhile removed G-code from the viewer, so the renderable set is now **GLB +
3MF + STL** plus the two self-rendering kinds (implicit raymarch, URDF), and the deleted
G-code path took its client machinery with it.

Two classes of breakage survived the merge invisibly and are worth recording, because a clean
`vite build` plus green unit tests certified both:

* **Unbound identifiers.** `gcodeStatus`, `dxfStatus`, `gcodeMode`, `getCachedDxfState`,
  `loadDxfForEntry` and friends were referenced but never declared. A bundler treats those as
  globals; only a render throws. Found with a Babel scope pass over `viewer/src` — worth
  re-running after any large merge (`ReferencedIdentifier` + `scope.hasBinding`).
* **An orphaned JSX closer.** Deleting the DxfFileSheet branch left its `) : null}` behind,
  which esbuild downgraded to a warning and shipped as literal page text.

The DXF render path was also dead on arrival for a subtler reason: the mesh-load effect gated
on the SOURCE format, so a DXF entry whose `preview.glb` was built and published sat at 92%
forever because nothing ever asked for it. It now gates on `entryRenderAssetFormat`, with
implicit and robot entries excluded — they render their own geometry, and would otherwise
download a second copy of the model into a scene that already has one.

**Imported `.dxf` files with open or unsupported geometry no longer render at all.** This is a
consequence of dropping the 2D view, not a regression in the bake: every generated `.dxf.py`
drawing builds, but all seven raw fixtures under `models/drawings/dxf/` fail —
`arc1` (open contour), `ellipse` (ELLIPSE), `polylines` (POLYLINE), `splines` (SPLINE),
`multi_insert_with_attribs` (INSERT), plus two intentionally-invalid ones. The 3D flat-pattern
mesher needs closed cut contours and supports a narrower entity set than the parser. Closing
this means either teaching `buildPreviewMesh.js` those entities and an open-contour fallback,
or bringing back a 2D path for drawings that have no extrudable area.

### Outstanding follow-ups (none block the batch)

1. **ES-1.00 polyfills for nine GLSL builtins** — `sinh cosh tanh asinh acosh atanh trunc
   round roundEven` are ES 3.00, but model shaders are ES 1.00, so
   `catenoid-ring-bridge.implicit.js` **does not render on the GPU today** and now bakes an
   artifact from a field the GPU has never evaluated. Pinned by shrink-only lists in
   `sdfField.test.js` that fire on any new offender. Fix: polyfill them in
   `IMPLICIT_CAD_GLSL_LIBRARY`; the library sweep verifies each against its JS twin
   automatically.
2. **`stepArtifactStatus.js`** still gates on `sourceFormat === STEP` and its client-side
   buildable-code list omits the DXF/implicit codes. It reads `entry.artifact`, which the
   scanner no longer writes, so it is vestigial rather than wrong — but it is the last
   client-side place that believes only STEP is artifact-managed.
3. **`cadjs/implicit/{export,model}`** remain as importer-less re-export subpaths (dead
   before this work).
4. **`menger-sponge.implicit.js`** is a model defect, not a builder bug: its `sdf` is ≥ 2.77
   everywhere inside its own bounds, so it has no surface on the GPU either.

---

## 0.0.1 Original execution notes

Nothing is pushed. All work is local commits on the branch above. Every commit below left the
full suites green (`implicitjs` 65, `cadjs` 449, `viewer` 261 JS tests; Python 104 cadgen +
308 cad + skills + 80 viewer-server + 28 global), with `scripts/bundle/bundle.sh --check`
clean and the dev symlink layout restored.

### Done

| Phase | Commit | What landed |
|---|---|---|
| **3a** | `937efa03` | **DXF is 3D-only.** Deleted `viewer/src/client/components/DxfViewer.js` (752-line SVG renderer) + `DxfViewModeControl`, the 2D/3D toggle, `dxf3dAvailable`/`activeDxfViewMode`/`dxfMeshPreviewReady`, `dxfViewPlaneHeader`, the `dxfViewMode` state, and the `dxfMode` arm of `viewportHasRenderableContent`. −860/+37 lines. |
| **0 (part 1)** | `b69a1ad1` | **The shared JS GLB writer.** NEW `packages/implicitjs/src/lib/glb/{bytes,writeGlb,writeGlb.test}.js`; `meshoptimizer@1.2.0` added to `packages/cadjs` (runtime) and `packages/implicitjs` (devDependency, for the test). **Plus the phase-0 measurement gate — see §6.1.** |
| **0 (part 2a)** | `b2ee9036` | **One `--write` flag.** `cad gen --write-step` → `--write`; `dxf --dxf` → `--write`. No aliases. Tests + 4 SKILL.md/reference docs moved with them. **Also**: `scanner.py` now IMPORTS `CADGEN_DIRNAME` / `CADGEN_MODELS_DIRNAME` / `DRAWING_DESCRIPTOR_NAME` / `DRAWING_PACKAGE_KIND` from cadgen instead of hand-copying them (the loose end below — closed). Verified both source modules are stdlib-only. |
| **0 (part 2b)** | `3070915e` | **One closure digest.** The legacy byte-digest fallback in `closure_hash_matches` is deleted. The test that pinned the old behaviour now pins the new one. |
| **0 (part 2e)** | `b1447380` | **Freshness hardening + the Node bridge.** NEW stdlib-only `_internal/package_freshness.py` (canonical_bake_hash, both-direction bake_hash_matches, exact-int schema_version_matches, the one ASSEMBLY_PACKAGE_SCHEMA_VERSION). Three gates added to the viewer validator AND `_package_descriptor_matches_spec`/`drawing_package_current` **together**: strict `packageSchemaVersion`, `bakeHash`, and imported-digest **fail-closed** (the validator's last fail-OPEN path). Digest field named per-format in the spec table, not aliased. NEW `_internal/node_runtime.py` + `progressStream.js`: Python holds `artifact_build`, the Node child is inside it, NDJSON progress streams onto the BuildRun, and a `finally` couples child death to lock release. |
| **0 (part 2f)** | `77659687` | `ArtifactKind.labels` + `IMPLICIT_PACKAGE` (phases sample/polygonize/weld/write). Gates phase 2's bar. |
| **0 (part 2d)** | `f4fdffe2` | **The meshopt decoder is registered — the gate on phases 2 and 4 is CLOSED.** Registered inside `buildMeshDataFromGlbBuffer`, which is the ONLY `GLTFLoader` instantiation in the tree and the function the GLB worker also loads through — so the plan's "register in both `glbMeshData.js` and `glbMeshWorker.js`" is one place, not two. `cadjs/glb/writeGlb.js` re-export added (`./glb/*` in both exports maps). **`meshoptimizer` is now a VIEWER dependency**: as a cadjs-only dep the dev build passed and the PRODUCTION build failed, because rollup cannot resolve the dynamic import when `viewer/packages/cadjs` is a real copy with no `node_modules`, and an unresolvable dynamic import is a build-time error, not a runtime fallback. Only `bundle.sh --check` catches this class. 3 round-trip tests through the real encoder + real loader. |
| **0 (part 2c)** | `d8fc9f35` | **One GLB writer.** `meshToGlb` DELETED (65 lines); `meshToFormat`'s glb branch calls `writeGlb` with the `export` preset. Measured: sphere-boolean-cuts @48 → **541,712 B vs ~2,198,880 B**, 75% smaller, `extensionsRequired` empty, extras intact. Two fixes the tests forced: `IMPLICIT_CAD_SOURCE_KIND` now has one spelling, and `cadOccurrenceId` keys on the **source kind** not the model's display name (it was emitting `"export sphere:0"` where the convention is `"implicit-cad:0"`; an occurrence id must survive a rename). `writeGlb` gained `occurrenceIdPrefix`. |

| **3** | *(working tree)* | **The client deletions, and the viewer half of phase 2.** VIEWER WIRING: `owns_implicit_entry` + the `_IMPLICIT_PACKAGE` spec row + `validate_implicit_freshness` + the three implicit buildable codes (and `BUILDABLE_STEP_ARTIFACT_CODES` renamed to `BUILDABLE_ARTIFACT_CODES`); `_artifact_format` became an ordered predicate->record table that **raises** instead of falling through to STEP; `scanner` publishes each baked package GLB as the entry's `glb` **relation** (`render_package_asset_dir` keeps the URL derivation unresolved while the lock path stays realpath'd, §8). DELETIONS: `ImplicitCadViewer.js` (1140 lines, with its second OrbitControls), `ImplicitFileSheet.js`, `ImplicitGraphicsSection.js`, `implicitGraphicsSettings.js`, `DxfFileSheet.js`, `implicitExport.js`, the implicit params/animation machinery in `CadWorkspace.js`, the DXF loader/memo tier, `loadRenderDxf`/`peekRenderDxf`/`dxfCache`, `slices.dxf` + `slices.implicit`, `dxfThicknessMm` from the tab schema, `buildViewerDxfAlert`/`buildViewerImplicitAlert`, `entryHasImplicitCad`, and four dead `cadjs/implicit/*` subpaths. `entryRenderAssetFormat(entry)` landed in its FINAL one-argument form -- the `{ artifact }` phasing device was never written, so there was nothing to remove. EXPORT: `/__cad/implicit-export` and the browser-side mesh-and-upload are gone; `/__cad/step-export` became `/__cad/export` and NEW `cadgen.implicit_export` runs the shipped `implicitjs/scripts/export.mjs` in a Node child under `generator_busy`. **Six render paths -> two** (mesh + G-code, which is out of scope by §0.1). |
| **2** | *(working tree)* | **The implicit render package.** NEW `cadgen.implicit_artifact` + stdlib-only `_internal/implicit_package.py` (descriptor, bake block + `bakeHash`, `implicit_package_current`), NEW `packages/cadjs/bin/implicit-artifact.mjs` (+ closure-capture hooks), NEW `implicitjs` `meshWorkers.js` / `meshWorkerEntry.js` / `renderGlb.js`, NEW `skills/implicit-cad/scripts/gen` with `--write`. `mesh.js` split into exported `implicitCadGrid` / `sampleFieldPlanes` / `polygonizeCellPlanes` passes so serial and parallel run ONE implementation. **Measured** (10-core M1 Max, sphere-boolean-cuts, smooth normals): res 96 **36.7 s → 11.5 s (3.20x)**, res 48 6.51 s → 2.44 s (2.67x), byte-identical output pinned by test. Sample scales 3.9x, polygonize 2.9x. **The corpus does not scale with threads**: per-`sdf()` cost spans **29.6 µs → 9.06 ms (306x)** across the 43 models, so §7.2 optimization 0 (compile the transpiled SDF) is the lever the slow half needs, not more cores. Two evaluator gaps found and fixed (both pre-existing, both reproducible through the shipped `export.mjs`): the missing GLSL builtin set (`cosh` and 15 others — `catenoid-ring-bridge` could not mesh) and `break`/`continue` (`mandelbulb-distance-estimate` could not mesh). `menger-sponge.implicit.js` remains unbakeable and is a MODEL defect: its `sdf` is ≥ 2.77 everywhere inside its own bounds (the `cross` term never goes negative), so it has no surface on GPU either. |

**Two corrections to the plan that execution produced.** Both are already applied in the
document, but know that they came from running the code, not reading it:

- §7.4.1 said phase 3a needed **no test changes**. Wrong: `viewerAlerts.test.js` pinned two
  behaviours that had to change. With no 2D fallback, a failed DXF mesh build goes from a
  *warning* (whose text read "The flat pattern can still be shown") to an **error**, and the
  case that suppressed vertical-bend-line failures to `null` is removed — suppressing it now
  leaves an empty viewport with no explanation.
- §6.1's numbers replaced the estimates. The gyroid CPU mesh is **145 s, not 71 s**, and the
  geometry claims (220,202 segments, 5,429 groups, 972,816 triangles, 66.80 MB) are confirmed
  exactly.

### `writeGlb` — what exists, so you do not rebuild it

`writeGlb(mesh, options) -> bytes` is **pure and lock-free** (the `writeRenderPackage`
lock-asserting wrapper of §6 is **NOT written yet** — it is phase 2/4 work). Implemented and
covered by 9 tests that round-trip through a real three.js `GLTFLoader`:

- welding keyed on position **and** normal (creases survive), deterministic
- **pre-indexed passthrough** — pass `input.indices` and the weld is skipped
- `UNSIGNED_SHORT` indices under `UNSIGNED_SHORT_VERTEX_LIMIT` (65,535) vertices
- one node per primitive with `extras.cadOccurrenceId`; per-primitive materials
- `KHR_mesh_quantization` (positions SHORT over per-primitive bounds, with the node
  scale/translation that restores world placement; normals BYTE normalized)
- `EXT_meshopt_compression`, encoder **injected** (`options.encoder = MeshoptEncoder` after
  `await MeshoptEncoder.ready`) so the module stays dependency-free
- two presets: `render` (quantized + compressed) and `export` (welded + indexed but
  **unquantized, uncompressed, and declaring no required extensions** — a stock `GLTFLoader`
  with no decoder must be able to open it)

> **The bug worth not reintroducing.** The first draft wrote both the bufferView's own
> `buffer`/`byteOffset` **and** the `EXT_meshopt_compression` extension's. A decoder-aware
> loader reads that as garbage, because it allocates from the bufferView and fills from the
> extension. Per spec the bufferView describes the *decompressed* data
> (`byteLength === count * byteStride`) and carries no buffer/byteOffset of its own. See
> `pushCompressedView`.

### Remaining, in execution order

1. **Phase 0 (rest).** Still open, in rough order:
   - `bakeHash` (§5.3); per-format `source_digest_field` fail-closed (§5.3b);
     `packageSchemaVersion` strictly gated (§5.1). These three are one coherent change to
     the shared validator and are best done together.
   - `ArtifactKind.labels` (§4.7) — needed before phase 2, because the implicit builder's
     phases (`sample`/`polygonize`/`weld`/`write`) have no entries in the global
     `PHASE_LABELS` dict and would render as raw phase names.
   - Implicit `export` CLI **flag-surface** alignment (§4.7): adopt cad's flag-per-format
     (`--stl` / `--3mf` / `--glb`, several at once, sibling-default sentinel) over the
     current single `--format`, and produce all three from ONE mesh pass. The GLB *writer*
     half of this alignment is already done (`d8fc9f35`).
   - **Do NOT redo:** `meshToGlb` deletion, the `--write` renames, the legacy byte-digest,
     and the `scanner.py` constants import all landed — see the Done table above.
2. ~~**Phase 2.** `cadgen.implicit_artifact` + the implicit Node builder + `implicit-package` +
   `worker_threads` sampling **and** polygonizing + determinate progress +
   `skills/implicit-cad/scripts/gen` (with `--write` → sibling `.glb`).~~ **Landed** — see the
   Done table. Three things it did NOT do, each still open:
   - the **SDF field-agreement test**, which is **GATING** and a hard precondition on phase 3;
   - the VIEWER side (`owns_entry`, the `_IMPLICIT_PACKAGE` spec row, `_artifact_format`
     dispatch, the buildable codes) — `viewer/server_py` was owned by phase 4 concurrently, so
     nothing yet asks for an implicit package on open;
   - **packaging**: `skills/implicit-cad` now vendors `cadgen`, but the Node builder it spawns
     lives in `packages/cadjs` and pulls `meshoptimizer`, neither of which any skill bundle
     ships yet. Shared with phase 4, which has the same gap for `skills/dxf`.
3. **Phase 4.** DXF `preview.glb` — **required**, not optional (§7.4.2). `payload_refs` must
   return **both** `drawing.dxf` and `preview.glb` or a missing preview never marks the
   package stale. Widen `owns_dxf_entry` to imported `.dxf` (viewer-built on demand); the gen
   CLI stays `.dxf.py`-only (§0.1).
4. ~~**Phase 3.** Client deletions — **excluding all G-code plumbing** (§0.1).~~ **Landed** —
   see the Done table. Two follow-ups it deliberately did NOT do:
   - `stepArtifactStatus.js` still gates `stepArtifactCanGenerate` / `stepArtifactNeedsWarning`
     on `sourceFormat === STEP` and its `BUILDABLE_STEP_ARTIFACT_ERROR_CODES` still omits the
     DXF and implicit codes (§5.4). It reads `entry.artifact`, a per-entry field the scanner
     no longer writes, so it is vestigial rather than wrong — but it is the last client-side
     place that believes only STEP is artifact-managed.
   - `cadjs/implicit/{export,model}` remain as re-export subpaths with no importer. They were
     already dead before this phase, so they are not phase 3's to delete.

### Known loose ends

- `writeRenderPackage` and `assertWriteLock` (§4.4, §6) do not exist yet.
- `require_write_lock` is a Python thread-local check and does **not** cover a Node-written
  package. The structural answer is §4.3: the Python wrapper holds the lock, so the Node child
  is inside the critical section by construction.
- ~~`scanner.py:38-45` hand-copies four constants from cadgen with nothing cross-checking
  them.~~ **CLOSED** in `b2ee9036` — they are imported now.
- ~~The decoder is not registered yet.~~ **CLOSED** in `f4fdffe2`. Render-preset packages
  now load, so phases 2 and 4 are unblocked.
- **`NODE_PATH` does not work for a real `node` child — §4.5 is WRONG on this.** Node's ESM
  resolver ignores it (verified on v22.22.0: `import "implicitjs/glb/progressStream.js"` with
  `NODE_PATH` set throws `ERR_MODULE_NOT_FOUND`, while `require.resolve` of the same
  specifier under the same env succeeds). `bundle-cad.sh` never hit this because esbuild
  implements `NODE_PATH` itself. `node_runtime.py` corrects it with a resolve hook that tries
  `nextResolve` first and delegates only bare-specifier misses to the CJS resolver, which
  reads `NODE_PATH` and applies the exports map. Any future Node builder must spawn through
  `run_node_builder`, not bare `node`.
- **Skill bundles ship esbuild'd builders, and vendoring source would NOT have worked.**
  Measured: `dxf-artifact.mjs` pulls `three` transitively via
  `packages/cadjs/src/lib/dxf/buildPreviewMesh.js:1`, and both builders pull `meshoptimizer`.
  Vendoring `packages/{cadjs,implicitjs}` as source (the CAD Viewer's approach) leaves both
  npm packages unresolvable in a tree that ships no `node_modules`, so §4.5's option (b) is
  the only one that closes. `scripts/bundle/lib/node_builders.sh` bundles one
  `--platform=node` file per skill (+844 KB shipped total). Two extra files ship beside the
  implicit bundle because esbuild cannot inline a path computed at run time
  (`register("./implicitClosureHooks.mjs", import.meta.url)` and
  `new Worker(new URL("./meshWorkerEntry.js", import.meta.url))`), plus a
  `{"type":"module"}` package.json so a bare `.js` is not parsed as CommonJS.
- **Two builds differ.** `npm --prefix viewer run build` (dev, symlink layout) resolves
  imports that `scripts/bundle/bundle.sh --check` (production, real copies, no nested
  `node_modules`) cannot. Any new runtime dependency reachable from viewer client code must
  be a **viewer** dependency, not only a `packages/*` one. Always run the bundle check.

---

## 0.3 What changed since the original plan, and why

This document has **two layers of amendment** over the original. Read the layer-1 table if you are reconciling against the coordination refactor; read the layer-2 list if you already read the first amendment and want only the newly requested scope changes.

**Layer 1 — reconciliation with the coordination refactor** (the table below). The original was written against `56a119c0`; ten commits have landed since (`f1adbded` … `2c6d7882`) that rewrote the artifact coordination system this plan sits on. The original's §2 ("what already exists") is now partly wrong, and two of its architectural claims are no longer true.

**Layer 2 — four requested scope changes, applied afterwards.** These were applied *on top of* layer 1, so any conflict between the two is resolved in layer 2's favour, and each conflict is called out where it lands:

- **T1 — CLI `gen` parity + implicit `export`.** The new formats become buildable from the CLI, mirroring `skills/cad/scripts/gen`, with the sibling-write flag unified to a single `--write` across every gen CLI. **Two entrypoints, one producer** — and that forces the producer module out of `viewer/server_py` and into `packages/cadgen`, because no skill may import viewer code (**§4.3, §4.7**). Implicit `export` is scoped as **alignment**: `glb`/`stl`/`3mf` already ship (`exportModel.js:7`). G-code gets **no** export.
- **T2 — render-path convergence meta-goal.** After this lands the renderable set is **GLB + 3MF + STL**, and converging those three onto shared code becomes a standing goal with a starting inventory (**§13**). Explicitly **not a phase and not scoped now.**
- **T3 — DXF is 3D-only.** The 2D SVG view is deleted. That **reverses** the previous recommendation to drop phase 4: with 3D-only, `preview.glb` *replaces* the client-side DXF code instead of adding a sixth path, so phase 4 becomes **required** (**§7.4, §9**).
- **T4 — no backwards compatibility.** Remove and replace. No shims, no field aliases, no tolerant readers, no opt-in escape hatches. Stated once in **§0.2** so every later section can stop hedging, with the shim-vs-phasing-device distinction made explicit and every phasing device given the phase that deletes it.

> ### ⚠ One user-facing consequence of T4, surfaced here rather than buried
>
> T4 authorizes deleting the legacy byte-digest fallback in `closure_hash_matches` (`packages/cadgen/src/cadgen/_internal/source_hash.py:447-472`) — the last data-compatibility path in the freshness stack (**§5.6**). **Consequence: every existing `__cadgen__` package whose descriptor was written before semantic (AST) hashing landed reports stale once and rebuilds.** The rebuild is *lazy* — only for an entry the user actually opens — and `__cadgen__/` is a gitignored derived cache (`.gitignore:8-11`, "Rebuilt on demand; never committed"), so nothing is lost but time (~30 s for `tom`, ~71 s for a resolution-96 implicit). **Say this in the PR body.** It is the one T4 deletion whose price is a user-visible rebuild rather than deleted code.

| Original claim | Reality on this branch | Where it lands |
|---|---|---|
| "flock on a sentinel + a `.generation.progress.json` sidecar" | `cadgen.coordination` — a **Python API** (`artifact_build`, `generator_busy`, `snapshot`, `require_write_lock`) owned by ONE implementation imported by both cadgen and `viewer/server_py` | §3, §4 |
| "shells out to node … same subprocess isolation, **same flock, same progress sidecar**" | A subprocess inherits nothing. The lock and the record are taken *inside* the producer by `artifact_build`. Node has no `flock` (verified: `fs.flock`, `fs.promises.flock` undefined and `O_EXLOCK` absent on this repo's node v22.22.0) | §4 — rewritten, own section |
| "no OCP, **no cadgen import**" in the freshness path | Dead rule. `viewer/server_py/artifact.py:33` imports `cadgen._internal.source_hash`; `:185` imports `cadgen.coordination`. The live invariant is only "never import OCP/build123d/ezdxf in the server process", pinned by `tests/python/packages/cadgen/test_coordination_is_stdlib_only.py` | §3 |
| "Extend `tests/python/global/test_viewer_cadgen_mirror.py`" | Deleted in `140cb659`. It hid a real bug (it `.resolve()`d one side before comparing, masking a symlink divergence in lock sentinels) | §10 |
| "`bakeHash` … one optional comparison; both existing formats pass `None`" | There are **two** freshness authorities, not one. The viewer's validator decides the GET; a per-kind `is_current` callable re-evaluated under the lock decides whether the build is a no-op | §5.3 |
| "Node is unconditionally available … ships `node_modules/`" | The binary is available; the dependency graph is **not**. `git ls-tree -r origin/main \| grep -c node_modules` → **0**. `bundle-cad-viewer.sh` writes a dependency-free `package.json` (:322-339) and gitignores `node_modules` (:341-355). It *does* ship `packages/{cadjs,implicitjs}` source | §4.5 |
| Implicit "66.8 MB → 6–8 MB" post-weld-and-quantize | Arithmetic error. ~18.5 MiB, of which u32 indices are 11.7 MiB. `EXT_meshopt_compression` is doing the work, not welding — so it is **required**, not optional | §7.2 |
| "Phases 1 and 2 are additive … behind `entrySourceFormat`" | `entrySourceFormat` (`packages/cadjs/src/lib/fileFormats.js:59-89`) is a pure kind→format map with no flag and non-render call sites. Changing it is not additive | §9 |

Two things got **easier** and one got **worse** that the original could not have known:

- **Easier:** the client already attaches to a peer's build instead of POSTing a duplicate (`viewer/src/client/workbench/artifactResolution.js`, `useArtifact.js`), POST never blocks on a peer (`backend.py:397-424`), progress is runId-attributed so a corpse record can't be rendered as live (`record.py:162-173`), and a new format's progress bar is weighted over exactly its own phases (`ArtifactKind.phases`, `kinds.py:26-37`). All of that is free.
- **Worse:** `require_write_lock` (`component_package.py:462`, raising under `CADGEN_STRICT_LOCKS=1` which `scripts/test/test-python.sh:14` exports) is a **Python thread-local** check. A Node-written package trips nothing. The plan's central "the builders run in Node" decision now has to say who holds the lock, and the answer is not "the builder".

**One live bug found while verifying, unrelated to this plan but blocking §7.2's progress requirement** — see §4.6 (already fixed).

---

## 0.1 SETTLED DECISIONS (2026-08-05) — these override anything below them

Every open question §12 flagged as needing the user has been answered. Where this section
conflicts with a later section, **this section wins**; the later text is left as rationale.

### Scope: G-code is OUT of this batch

**Phase 1 (`toolpath-package`, the G-code Node builder, `skills/gcode/scripts/gen`, and
`scripts/bundle/skills/bundle-gcode.sh`) is DEFERRED to a separate effort** — "it needs a
slightly different treatment". Do not build it here. Delete nothing G-code-related: the
direct-parse path stays live and untouched.

Recorded for whoever picks it up: the decision was *not* driven by the numbers, both of which
were accepted (a slower first open is fine because the result is cached; 7.24 MB against a
6.0 MB source is fine). So the deferral is about approach, not viability.

**Consequences for the remaining phases.** The renderable set after this batch is GLB + 3MF +
STL **+ G-code**, so §13's meta-goal target is not reached yet and phase 3 must NOT delete the
G-code memo plumbing (`selectedGcodeMeshData`, `buildGcodePreviewMeshData` call sites,
`gcodeState`). "Six render paths → one" becomes **six → two**.

### Implicit

1. **Live parameters and animations are REMOVED.** The static-gallery trade is accepted for
   all 43 models. Bake at `params.*.default`; delete the slider UI and the animation
   machinery from the viewer, not just bypass them. This is what makes implicit actually
   leave the render-path count.
2. **Bake resolution stays 96** (`DEFAULT_RESOLUTION`, `mesh.js:4`), with 128 opt-in per
   model via a descriptor field. Decision delegated with the instruction "I want it to look
   good by default", and 96 is the resolution the models were authored against — dropping to
   64 would visibly coarsen 43 shipped models to save build time on an artifact that is built
   once and cached. The cost is real (**145 s measured**, §6.1, not the 71 s originally
   claimed) which is precisely why phase 2's `worker_threads` sampling is a hard requirement
   of that phase rather than an optimisation: ~8 cores should bring a first build to ~20-25 s.
   **Do not exit phase 2 on an estimated speedup — measure it.**
3. **The `export` CLI keeps its current live `--params` / `--animation` / `--resolution`
   behaviour.** Export is not the viewer and does not affect it, so there is no reason to
   force it to the baked defaults. Note the interaction with decision 1: once the slider UI
   is gone, these flags are reachable only from the CLI, which is fine — that is what a CLI
   is for.

### DXF: the CLI and the viewer own different inputs

This mirrors STEP exactly, and it is the model to copy:

| Input | Who builds it | How |
|---|---|---|
| `.dxf.py` generator | the `dxf` **gen CLI** | `dxf <target>` builds the drawing package; `--write` also writes the sibling `<name>.dxf` |
| imported `.dxf` | the **viewer**, on demand | opening it triggers a GLB artifact build into `__cadgen__`, exactly as an imported `.step` does today |

So `owns_dxf_entry` **is** widened to imported `.dxf` (the viewer owns and builds them), while
the gen CLI stays `.dxf.py`-only. An imported `.dxf` never appears as a gen target.

### `--write` is on BOTH implicit and DXF

Superseding §4.7, which concluded implicit takes no `--write`:

| CLI | Always builds | `--write` also writes |
|---|---|---|
| `cad gen` | STEP render package | sibling `<name>.step` (renamed from `--write-step`) |
| `dxf` | drawing package | sibling `<name>.dxf` (renamed from `--dxf`) |
| `implicit` gen (**NEW**) | implicit package | sibling `<name>.glb` |

Implicit's `--write` writes **GLB** — its native mesh output and the same geometry the render
package holds. `export` remains the command for choosing among glb/stl/3mf; `--write` is the
one-flag "also leave the native file beside the source" affordance the other two gen CLIs
have. G-code would have had no `--write` (the source *is* the deliverable), which is moot now
that it is out of scope.

### Legacy behaviour: remove it

Standing authorization. The legacy byte-digest fallback in `closure_hash_matches`
(`source_hash.py:447-472`) is deleted in phase 0. **Measured cost: 2 packages rebuild once**,
lazily, on next open — `models/step/assemblies/mars_rover_concept.step.py` and
`models/renders/raptor3/raptor3.step.py`. 22 other local packages already record semantic
digests and are unaffected. `__cadgen__/` is gitignored, so a fresh clone has nothing to
invalidate. The same posture applies to any other legacy path found while executing.

---

## 0.2 Compatibility posture (T4)

This plan **removes and replaces**. It ships **no** compatibility shims: no re-export stubs, no legacy field aliases, no tolerant readers, no opt-in escape hatches back to a deleted path, and no dual render path that outlives its own phasing.

This is the posture the three commits immediately preceding this plan already established. `7721f5e6` carries a section literally headed *"Also drops backwards compatibility, per request:"* — `_internal/generation_status.py` and `_internal/progress.py` were **deleted**, not left as re-export shims, and `record.progress_for_run` stopped tolerating the v1 schema, removing *"the fallback branch whose only purpose was letting a new reader show progress for an old producer."* `140cb659` deleted `viewer/server_py/source_hash.py` (133 lines) and the mirror test outright. `abb10521` ("coordination: cut speculative surface") deleted the EXPORT kind, `_REGISTRY`/`register()`/`lookup()`, `BuildRun.coordinated`, `BuildRun.reporter` and `Snapshot.idle` as *"API invented for a generality nobody asked for, which is the same kind of weight the shims were."* The live enforcement is `coordination/record.py:165` — `!= SCHEMA_VERSION` → reject, with **no tolerance branch**. New code matches that.

**What this does NOT mean.** T4 targets compatibility with *old code and old artifacts*. It does **not** target:

- error tolerance in a wire protocol (§4.4's unknown-`type` NDJSON lines, mirroring `cadgen_bridge.py:145-152`);
- environment degradation (`require_write_lock` warning unless `CADGEN_STRICT_LOCKS=1`, `coordination/__init__.py:316-346` — landed in `7721f5e6` with a stated reason: *a missing lock must never be the reason a user's build fails*; out of scope here). Note the deliberate asymmetry: the **new** JS `assertWriteLock` (§4.4) throws unconditionally. That is intentional — new code fails loud;
- tests that skip when a dependency is absent (§10.1's `node_modules` skip);
- deferral of features nobody has built yet (§12 Q2's eviction).

**Nor does it license deleting a *phasing device*** — a path that is dual only until a later phase *of this same effort* removes it, with a written exit criterion. Deleting the parity fallback before parity is verified is how you ship a regression. Every phasing device in this plan is named below, **with the phase that kills it**:

| Device | What it does | Deleted by |
|---|---|---|
| `entryRenderAssetFormat(entry, { artifact })` returning GLB only when a package exists (§8, §9) | Lets phases 1–2 ship before the deletions; parity verifiable side by side | **Phase 3**, which removes the `{ artifact }` argument entirely |
| Phase 2's gating SDF field-agreement test (§10.3) | Gates the phase-3 deletions | Nothing — it *is* the parity gate, and it is a hard precondition on phase 3 |
| DXF client mesh path surviving between phase 3a and phase 4 (§7.4) | 3D-only lands as a pure client deletion before the bake exists | **Phase 4**, after which phase 3 deletes the DXF loader/memo tier |

**On-disk artifacts are invalidated, not migrated.** `__cadgen__/` is gitignored under a comment that settles the question — *"Rebuilt on demand; never committed"* (`.gitignore:8-11`). It is a per-machine derived cache with zero data-compat obligation. Packages predating a new descriptor field get **invalidated**, and invalidation is lazy: `_validate_render_package` (`viewer/server_py/artifact.py:100-144`) only runs for an entry the user actually opens, and every stale/unsupported code is already in the buildable set (`artifact.py:42-49`), so the cost is one rebuild per entry reopened, not a mass event.

---

## 1. Verdict

**Still a good idea. Proceed, with the amendments below.** The coordination refactor made the destination *closer*, not further: package-path derivation, sentinel naming, run attribution, crash-safe idle state, per-kind phase weighting, non-blocking POST and the whole busy/blocked/attach client UX are now format-agnostic and cost this plan nothing. A new format supplies an `ArtifactKind` constant, a freshness predicate, and a builder.

What it did **not** give you, and what the original plan silently assumed it did:

1. Any JS-side implementation of anything. Coordination is stdlib-only Python by contract (`coordination/__init__.py:12-17`).
2. Any mutation-boundary guard a Node writer can trip.
3. Any cross-artifact concurrency bound (the warm worker's global lock is bypassed by a Node build).
4. Any eviction.

The single largest change to the plan is §4: **the Node builders do not own the lock, the run id, or the status record.** A thin Python process does, and the Node builder is its child. T1 adds a second consumer of that same process — the CLI — which is why its module home moves to `packages/cadgen`. Everything else is corrections and re-sequencing.

---

## 2. Goal and accepted losses

**Corrected path count.** The viewer has **six** file→geometry paths, of which only **two are separate renderers**:

| Path | Kind | Renderer |
|---|---|---|
| GLB / STL / 3MF | three loaders → one `meshData` (`meshLoaders.js:59-78`; `renderAssetClient.js:257`, `:282`, `:305`) | shared `CadViewer` |
| G-code | client parse + mesh (`CadWorkspace.js:2029-2035`) | shared `CadViewer` |
| DXF **3D** | client parse + mesh (`CadWorkspace.js:2980-2999`) | shared `CadViewer` |
| DXF **2D** (today's default) | `DxfViewer.js`, inline SVG | **its own renderer** |
| implicit | raymarch | **its own renderer** |

So G-code and DXF-3D are separate *mesh producers* feeding one renderer, not separate renderers. That is what makes the collapse cheap. Only STEP goes through the server-side artifact pipeline.

Collapse to **one runtime path**: every rendered entry resolves to a GLB (or a package of GLBs) produced by a server-owned build, loaded by `GLTFLoader`. DXF, G-code and implicit become build-time producers.

### Accepted losses (decided; do not relitigate)

| Lost | Format | Replacement |
|---|---|---|
| Adaptive detail slider (levels 1–7, segment budgets) | G-code | Always max detail (`detailMode: "full"`) |
| Runtime `extrusionWidthMm` / `travelWidthMm` / height tuning | G-code | Baked at defaults, recorded in the descriptor |
| Camera fit follows the *visible* layer slice (`buildPreviewMesh.js` computes bounds from visible segments only) | G-code | Bounds are whole-model; layer scrub no longer re-fits |
| Live parameter sliders | implicit | Baked at `params.*.default` |
| Custom animations (`animations.*.update`) | implicit | **Dropped.** §7.3 records the size arithmetic that keeps them dropped |
| Per-pixel `color(p, normal)` field, exact SDF normals | implicit | Per-vertex colors, tessellated normals |
| **Graphics panel** (resolution / ray-detail / normal-smoothing sliders, soft shadows, AO, rim light) | implicit | **None** — added here because it was missing from the original table and it is a visible feature |
| **Client-side parametric export** (`requestImplicitCadExport` meshes and serializes *in the browser*) | implicit | The browser export is **deleted**; the viewer's Export action runs the same node export CLI **server-side** under `generator_busy`, at caller-supplied params (§4.7, §12 decision 2) |
| **The 2D SVG drawing view** (`DxfViewer.js`, 752 lines) | DXF | **None — deleted (T3).** DXF renders in the shared 3D viewer only (§7.4) |
| Live thickness slider + per-bend fold angles | DXF | Baked at `defaultThicknessMm` with every bend angle at `DEFAULT_DXF_BEND_ANGLE_DEG = 0` (`buildPreviewMesh.js:6`). **"Flat" is the fold state, not the renderer** — the baked artifact is an extruded 3D solid (`DEFAULT_DXF_PREVIEW_THICKNESS_MM = 2`, `:3`) viewed in 3D |

State plainly in the PR: **43/43 shipped `models/implicits/*` lose live params and animation.** The implicit library becomes a static gallery. If that is not acceptable, the alternative is to keep the raymarch as the implicit *default* and use the baked GLB only for the unified asset/selection path — a different plan (§12 decision 1).

**Explicitly preserved:** G-code per-layer visibility and travel toggling (one GLB node per layer + one travel node, driven by `node.visible`); part/occurrence selection semantics via `extras.cadOccurrenceId` matching the STEP convention.

**Where this ends up:** the renderable set becomes exactly **GLB + 3MF + STL** — the same three formats `IMPLICIT_CAD_EXPORT_FORMATS` already lists (`exportModel.js:7`). Converging those three onto shared code is the standing meta-goal in **§13**.

---

## 3. What already exists (corrected to this branch)

### 3.1 Build transport
`GET`/`POST /__cad/artifact` (routes: `viewer/server_py/server.py:138`, `:159`; state machine: `Backend.artifact_status` `backend.py:297-334` and `Backend.resolve_artifact` `backend.py:397-424`). States: `ready | needs-build | generating | error`, plus `busy` / `blocked` / `runId` annotations.

**A POST never blocks on a peer.** `resolve_artifact` snapshots first and returns `{state:"generating", runId}` immediately when a peer holds the write lock (`backend.py:416-421`). The 180-second `await_generation_lock` wait was deleted in `46b0d84c`.

Dispatch is a per-format record table, `Backend._artifact_format` (`backend.py:274-284`), with `validate` / `resolve_source` / `build`. Adding a format is one record — **but the table has no `unsupported` fallthrough**: it returns the STEP record for anything not DXF. See §5.5.

### 3.2 Package layout
Entry-keyed `<folder>/__cadgen__/models/<entry-filename>/`. `viewer/server_py/scanner.render_package_dir` (`scanner.py:68-83`) **resolves symlinks** to match `cadgen.catalog.render_package_dir` — they previously diverged for a symlinked entry file, so the viewer and a CLI build silently failed to exclude each other. `__cadgen__/` is gitignored (`.gitignore:11`) and is in `VIEWER_SKIPPED_DIRECTORIES` (`scanner.py:33-37`), so a package directory literally named `<name>.implicit.js` cannot poison the catalog scan.

`scanner.py:38-45` still **hand-copies** `CADGEN_DIRNAME` / `CADGEN_MODELS_DIRNAME` / `DRAWING_DESCRIPTOR_NAME` / `DRAWING_PACKAGE_KIND` from `packages/cadgen/src/cadgen/catalog.py:16-17`, under a comment reading "mirrors cadgen.catalog". Nothing cross-checks them any more. That is a real, currently-unguarded boundary — see §10.

### 3.3 Freshness — **two authorities, not one**
1. **Viewer:** `_validate_render_package` (`viewer/server_py/artifact.py:100-144`), one algorithm over a per-format spec table (`_STEP_PACKAGE` :72-79, `_DRAWING_PACKAGE` :80-87). Decides the GET's `ready` / `needs-build`.
2. **Producer:** the `is_current` callable handed to `artifact_build`, **re-evaluated under the write lock** at `coordination/__init__.py:281-287` to set `run.skipped`. Today: `_current_artifact_for_spec` for STEP (`step_artifact.py:189`, wired at `:377`) and `drawing_package_current` for DXF (`_internal/drawing_package.py:188`, wired at `dxf_artifact.py:105`).

Freshness is a pure descriptor read — **no OCP, build123d or ezdxf in the server process**. It *does* import cadgen, but only stdlib-only modules (`cadgen._internal.source_hash` at `artifact.py:33`, `cadgen.coordination` at `:185`). That is the live invariant, and it is what lets the new formats' freshness predicate live in cadgen and be called from both processes (§5.3).

**STEP is the anti-pattern to avoid.** STEP has three entrypoints (`scripts/gen`, `scripts/artifact`, viewer POST) but its two coordinated wrappers use **different** currency expressions: gen uses `_assembly_is_current(spec) and _assembly_glb_package_current(spec)` (`generation.py:2202-2205`) while `build_step_artifact` uses `_current_artifact_for_spec(spec)` (`step_artifact.py:357`, `:377`). That is the same drift this section flags between validator and producer. **DXF is the precedent to copy** — `generate_dxf_targets` (`generation.py:2238-2332`) and `build_dxf_artifact` (`dxf_artifact.py:69-130`) wrap `artifact_build(DRAWING_PACKAGE, …)` with the *same* `is_current=drawing_package_current` (`:2289`, `:2312`, `:105`) and converge on the same inner producer.

**Known defect in the viewer half, which this plan must fix:** the imported branch is hardcoded to one key and **fails open**. `artifact.py:139` reads `descriptor.get("stepHash", "")`; the guard at `:142` is `if current and step_hash and step_hash != current`, so a descriptor with no digest falls through to `return (True, None)` at `:144` — fresh forever. cadgen's producer gate already fails closed on the same case (`_internal/generation.py:1222-1226`), so the two **already disagree**, contradicting the invariant asserted at `artifact.py:15-16`. (`missing_step_hash` is in `BUILDABLE_STEP_ARTIFACT_CODES` at `artifact.py:45` but is never returned by the validator — dead.)

### 3.4 Concurrency — `cadgen.coordination`
`packages/cadgen/src/cadgen/coordination/`, stdlib-only, imported by both sides.

- **`artifact_build(kind, output_dir, *, is_current, force, deadline_ms, sink)`** (`__init__.py:203-295`) — acquires `LOCK_EX` on the writer sentinel, mints a run id and stamps it into the sentinel, publishes a `starting` record *before* yielding, re-checks `is_current()` under the lock (`:281-287`), and publishes `done` (with `stageMs`) or `failed` (without).
- **`generator_busy(kind, output_dir)`** (`__init__.py:349-392`) — second sentinel `.generator.lock`, for a run that occupies a model's generator but writes no package (an export). Reads as `busy`, which does **not** hide the artifact. **The toolpath format has a builder but no exporter, so this lease applies to implicit only** (§4.7).
- **`snapshot(output_dir) -> Snapshot(state, run_id, progress, degraded)`** (`__init__.py:141-169`) — the reader. Probes `LOCK_SH` non-blocking, read-only, never creates files (`lock.py:76-105`).
- **`require_write_lock(output_dir)`** (`__init__.py:316-346`) — asserted at the package mutation boundary in `component_package.py:462`; raises under `CADGEN_STRICT_LOCKS=1`, warns otherwise. **Thread-local** (`lock.py:47`, `__init__.py:334-337`) — it cannot see a foreign process.
- **`ArtifactKind(name, phases)`** (`kinds.py:26-48`) — `STEP_PACKAGE` and `DRAWING_PACKAGE` are module constants. **There is no registry.** `phases` is load-bearing: the bar is weighted over exactly that tuple (`phases.py:190`, `_even_weights` :101-110).
- Paths (`paths.py`): `.<name>.generation.lock` (:28, **frozen**), `.<name>.generator.lock` (:34), `.<name>.generation.progress.json` (:40, deliberately not renamed). Hidden siblings of the package dir (`_sibling` :43-45).
- Record (`record.py`): schema v2, runId minted at acquire, `stageMs` **only** on `outcome=="done"` (:76-78), atomic temp + `os.replace` (:82-100). A reader renders a record **only** when `record.runId == the sentinel's runId` (:162-173) — a hand-written record with no matching sentinel is silently discarded.

### 3.5 Build execution
`Backend._run_artifact_build` (`backend.py:387-395`) → `cadgen_bridge.run_cadgen(module, args, repo_root)`. That prefers a **persistent warm worker** that imports OCP once (`cadgen_bridge.py:5-13`, `:121-131`) and falls back to a cold `python -m <module>` (`:134-158`). The worker's dispatch is a hardcoded three-entry map (`worker.py:55-65`) and an unknown module returns a normal result dict, not an exception (`worker.py:79-81`) — **so there is no cold fallback for an unrecognized module.** `run_cadgen_cold(module, args, repo_root)` (`cadgen_bridge.py:134-158`) is a **public function** that bypasses the worker entirely; §4.3 uses it, which is what makes that hazard a non-issue for the new formats. The server is a `ThreadingHTTPServer` (`server.py:388`), one thread per connection, and a POST already blocks for the whole build.

### 3.6 CLI shape (`cad gen`) — what "mirror the gen pipeline" means

`skills/cad/scripts/gen/cli.py` is argparse plus a one-line lazy delegate (`:14-17`, `:140-145`); all behaviour lives in `cadgen._internal.generation.generate_step_targets` (`generation.py:2147-2235`). Six things constitute the contract T1 mirrors:

1. **Argument surface** (`gen/cli.py:29-65`): positional `targets` (`nargs="+"`, explicit file paths only — no globs, no directory walk, no catalog scan; unresolvable → `FileNotFoundError` at `generation.py:1693-1697`, wrong suffix → `parser.error` at `gen/cli.py:76-84`); `--write-step [OUTPUT]` (`nargs="?"`, `const="__default_sibling_step__"` at `:11`; an explicit path requires exactly one target, `:104-108`); `--force`; `--mesh-tolerance` / `--mesh-angular-tolerance`; `--verbose`. There is **no** `--quiet` (the kwarg exists at `generation.py:1860` but no flag reaches it) and **no** `-o/--output`.
2. **`__main__.py` boilerplate** (`gen/__main__.py`): warm-daemon shim before the cli import (`:10-18`), sys.path insertion of `scripts/`, `scripts/packages/`, `scripts/packages/cadgen/src` so vendored cadgen beats a pip copy (`:25-31`), package-vs-directory dual import (`:33-39`).
3. **Two currency gates over ONE predicate**: a cheap pre-lock fast path logging `"{ref} is current; skipped recompose"` (`generation.py:2179-2196`, message at `:2191`), and the *same* predicate passed as `is_current=` to `artifact_build`, re-evaluated under the lock (`_built_by_a_peer` `:2202-2205` → `:2224`), yielding `run.skipped` → `"{ref} was built by a concurrent run; skipped"` (`:1888`). Success: `"generated {kind} GLB/topology artifact: {package_dir}"` (`:1745-1748`). Exit 0.
4. **Coordination is free.** `_run_with_spec_generation_status` (`generation.py:1805-1835`) is nothing but `artifact_build(KIND, render_package_dir(entry), is_current=…, sink=progress_sink)`, using the yielded `run` as the reporter.
5. **Multi-target = sequential**, one `artifact_build` lock per target (`:1877`, `:1827`). The only parallelism is stale-*child* rebuild in subprocesses (`:2070-2083`) — neither new format has composed children, so that machinery has no analogue.
6. **Reporting is *not* the status board.** `InlineStatusBoard` (`:125-166`) is reached only by logger-less callers (`:1893`); `generate_step_targets` always passes a `CliLogger`, so the live shape is `[scripts/gen] …` lines on **stderr** (`cli_logging.py:27-29`) plus one self-erasing `InlineProgressLine` per target (`:169-198`, `:201-228`), **suppressed under `--verbose`**. Determinate phases render `[bar] NN%  label 31/50` (`:1838-1850`) — a second reason §5.1's "make the dominant phase determinate" pays off.

**What cannot be reused.** `cadgen.catalog.source_from_path` returns `None` for anything that is not `.py`/`.step`/`.stp` (`catalog.py:161-172`); "gcode" and "implicit" appear nowhere in cadgen. Every piece of the `cad gen` driver — `EntrySpec`, `_selected_specs_for_targets` (`:1651`), `_validate_step_target` (`:1715`), `_spec_output_dir` (`:1771-1777`), the `gen_step`/`gen_dxf` kind switch (`:1826`) — is built on that model. **Mirror the contract, not the machinery**: reuse `CliLogger`, `_cli_progress_line`/`InlineProgressLine`, `_progress_status_text` and `artifact_build` — a ~60-line shared driver, not `_run_selected_specs` verbatim. Extending `source_from_path` would drag `.gcode`/`.implicit.js` into cad_ref, part-vs-assembly and `gen_step()`-metadata semantics they do not have.

### 3.7 What already exists on the JS side
- `packages/cadjs/src/lib/gcode/parseGcode.js` and `.../buildPreviewMesh.js` — **zero imports**, no external deps.
- `packages/cadjs/src/lib/dxf/parseDxf.js` (526 lines) and `.../buildPreviewMesh.js` (1,284 lines) — the client DXF tier that §7.4 deletes.
- `packages/implicitjs/src/lib/implicitCad/mesh.js` (`DEFAULT_RESOLUTION = 96` :4, `DEFAULT_MAX_CELLS = 2500000` :5, resolution clamped to [8,192] :35), `sdfEvaluator.js`, `model.js` — imports are all intra-package.
- `meshToGlb` (`exporters.js:193`) — single mesh, single primitive, **non-indexed**, f32 positions+normals. `meshToAnimatedGlb` (`exporters.js:259`). `meshToBinaryStl` (`:169-191`), `meshTo3mf` (`:508-559`), `meshToFormat` (`:561-585`).
- **Implicit export already ships all three requested formats**: `IMPLICIT_CAD_EXPORT_FORMATS = Object.freeze(["glb","stl","3mf"])` (`exportModel.js:7`), CLI at `packages/implicitjs/scripts/export.mjs`, skill shim at `skills/implicit-cad/scripts/export.mjs`, bundle guard at `scripts/bundle/skills/bundle-implicit-cad.sh:128`, docs at `skills/implicit-cad/SKILL.md:163-169`.
- **Mesh-once-write-three already exists in-repo**, just not in the CLI: `packages/implicitjs/scripts/verify-implicit-cad-exports.mjs:186-206` meshes once and loops all three formats through `meshToFormat`.
- `glbMeshData.js:479` constructs a bare `new GLTFLoader()` with **no plugins**; a separate `glbMeshWorker.js` exists.
- `packages/cadjs/bin/` and `packages/implicitjs/src/lib/glb/` do **not** exist yet.

---

## 4. Architecture decision: who owns the lock

The builders run in Node. That part is forced: an `.implicit.js` source is an executable ES module (`bounds` is an arrow function, `render` is a function of params), so there is no way to evaluate it without a JS runtime. Given Node is required for implicit, use it for G-code and DXF too and reuse `parseGcode` + `buildGcodePreviewMesh` + `parseDxf` + `buildDxfPreviewMeshData` + `sdfEvaluator` + `mesh` verbatim rather than writing ~3,400 LOC of second implementations.

**What is NOT forced, and what the original got wrong, is who holds the write lock.**

### 4.1 Rejected: Node holds the lock

Node cannot take a POSIX advisory lock. Verified on this repo's interpreter (v22.22.0): `fs.flock` and `fs.promises.flock` are `undefined`, and `O_EXLOCK` is not in `fs.constants`. A JS holder needs a native addon (which `scripts/github-workflows/check-builds.sh`'s no-symlink vendoring rule makes painful) or an `O_EXCL` lockfile — and a lockfile is invisible to `probe()`, which asks the kernel (`lock.py:94`). A reader would report `idle` over a live Node build, and `backend.py:416-421` would start a duplicate. That is verbatim defect #1 in `lock.py:8-11`.

It would also require re-deriving in JS: two sentinel suffixes (`paths.py:28,34`), hidden-sibling naming (`:43-45`), the 32-byte runId stamp (`lock.py:48,214-221`), schema-v2 field names and the `stageMs`-only-on-`done` rule (`record.py:76-78`), and temp+`os.replace` atomicity (`record.py:82-100`) — precisely the duplicated protocol the nine commits deleted (`coordination/__init__.py:3-10`).

### 4.2 Rejected: the server request thread holds the lock around a Node child

Tempting (no third process), but it **decouples lock lifetime from writer lifetime**. Kill or restart the viewer server mid-build and the lock dies with it while the orphaned Node child keeps writing — a half-written package with no lock over it. Every other holder in this system dies *with* its writer. Do not introduce the one that does not.

### 4.3 Chosen: a thin Python process holds the lock and owns the Node child's lifetime — **living in `packages/cadgen`**

```
                        ┌──────────────────────────────── two entrypoints ───┐
POST /__cad/artifact                                   python scripts/gen …
  ├─ *.step / *.step.py  → run_cadgen("cadgen.step_artifact")      (exists)  ← skills/cad/scripts/gen
  ├─ *.dxf / *.dxf.py    → run_cadgen("cadgen.dxf_artifact")       (exists)  ← skills/dxf/scripts/dxf
  ├─ *.gcode             → run_cadgen_cold("cadgen.toolpath_artifact")  NEW  ← skills/gcode/scripts/gen      NEW
  └─ *.implicit.js|.mjs  → run_cadgen_cold("cadgen.implicit_artifact")  NEW  ← skills/implicit-cad/scripts/gen NEW
                                │
                                │  ONE producer per format, in packages/cadgen
                                │  holds artifact_build(KIND, package_dir, …)
                                └─ child: node packages/cadjs/bin/<fmt>-artifact.mjs   (NEW)
```

**Division of labour — unchanged from the previous amendment.** Python owns the lock, the run id, the status record, the freshness re-check, the closure digest and the child's lifetime. Node owns geometry, GLB bytes, and the format-specific descriptor fields. Node never derives a lock path, never writes `.generation.progress.json`, and never outlives the lock.

**Amendment forced by T1: the module home moves out of `viewer/server_py`.** The previous draft put the wrapper at `viewer/server_py/node_artifact.py` and Node discovery at `viewer/server_py/node_bridge.py`. **No skill can import either.** AGENTS.md requires skills to be self-contained, and skill runtimes vendor `packages/` only — `skills/{cad,dxf}/scripts/packages/cadgen → packages/cadgen`, `skills/implicit-cad/scripts/packages/implicitjs → packages/implicitjs` (symlinks in dev, rsync copies in production; `scripts/bundle/skills/bundle-implicit-cad.sh:80-94`, `bundle-cad.sh`'s `vendor_python_package`). A viewer-resident producer makes the CLI path impossible without a **second implementation** — the exact duplication the coordination refactor just deleted.

New homes, each a byte-for-byte structural clone of `dxf_artifact.py`:

| Format | Producer module (**NEW**) | API |
|---|---|---|
| G-code | `packages/cadgen/src/cadgen/toolpath_artifact.py` | `build_toolpath_artifact(**kw) -> payload`, `run_cli_payload(argv)`, `main()` |
| Implicit | `packages/cadgen/src/cadgen/implicit_artifact.py` | `build_implicit_artifact(**kw) -> payload`, `run_cli_payload(argv)`, `main()` |
| DXF (phase 4) | `packages/cadgen/src/cadgen/dxf_artifact.py` (**exists**) | gains the Node mesh step as an inner stage of its existing lock |
| Node discovery | `packages/cadgen/src/cadgen/_internal/node_runtime.py` (**NEW**) | `cad_node_executable(repo_root)` |

**Why the previous section's four reasons for `viewer/server_py` no longer hold.** Three were about the warm worker, and the viewer can simply not use it — `run_cadgen_cold` is public (`cadgen_bridge.py:134-158`) and runs `python -m <module>` in a fresh subprocess, parsing the last stdout JSON line:

1. ~~"the warm worker exists solely to amortize the OCP import"~~ — irrelevant when the caller uses the cold path.
2. ~~"`worker_client` serializes through a per-worker `RLock` … a 71-second implicit build would freeze every STEP build"~~ — the cold path never touches `worker_client.py:55` or `:181`.
3. ~~"routing an unknown module through `run_cadgen` fails with no cold fallback"~~ — the hazard at `worker.py:79-81` only arises if the module is routed through `run_cadgen`. **Do not add these modules to the worker's dispatch map** (`worker.py:55-65`).
4. **Survives:** cadgen publishes to PyPI, so it must not *require* Node. It does not: Node stays a **soft, call-time** dependency discovered via `shutil.which("node")` at build time only. A PyPI install of cadgen that never builds a toolpath/implicit package never looks for Node. If that is still unacceptable, the AGENTS.md-sanctioned alternative is a new lightweight `packages/` package — at the cost of a third vendored dependency wired into three skills.

### 4.4 Concrete contracts

**NEW `cadgen.toolpath_artifact` / `cadgen.implicit_artifact`** — CLI:

```
python -m cadgen.toolpath_artifact \
  --repo-root <abs> --source-path <abs .gcode> [--force] [--threads N] [--verbose]
python -m cadgen.implicit_artifact \
  --repo-root <abs> --source-path <abs .implicit.js> [--force] [--resolution N] [--threads N] [--verbose]
```

Emits exactly one JSON object as its **last** stdout line — matching the contract `run_cadgen_cold` already parses (`cadgen_bridge.py:145-152`). Body:

```python
package_dir = render_package_dir(source_path)
try:
    with artifact_build(KIND, package_dir,
                        is_current=lambda: toolpath_package_current(source_path),
                        force=force, deadline_ms=2000) as run:
        if run.skipped:
            return {"ok": True, "skipped": True, ...}
        require_write_lock(package_dir)          # same thread; honest boundary assertion
        proc = subprocess.Popen([node, builder,
                                 "--package-dir", str(package_dir),
                                 "--source-path", source_path,
                                 "--run-id", run.run_id,
                                 "--threads", str(threads)],
                                stdout=subprocess.PIPE, stderr=None, text=True)
        try:
            for line in proc.stdout:     # NDJSON, below
                dispatch(line, run)
        finally:
            if proc.poll() is None:
                proc.kill(); proc.wait()  # lock release and child death are coupled
except Contended:
    return {"ok": True, "state": "generating"}
```

Two properties this buys, both currently untested in production code: `deadline_ms` / `Contended` (`lock.py:52-57`, `:192-211`) get their **first** production caller, so the wrapper refuses to queue behind a peer; and the `finally` couples child death to lock release.

**`is_current` is ONE module-level function, called from three places.** `toolpath_package_current` / `implicit_package_current` live in a stdlib-only cadgen module (beside `drawing_package_current` at `_internal/drawing_package.py:188`) and are used **verbatim** by:

1. the viewer's spec-table entry for that kind (`artifact.py:72-87`) — the GET's `ready`/`needs-build`;
2. the producer's `is_current=` under the lock;
3. the CLI's pre-lock fast path (§3.6 point 3).

That is what the DXF precedent does and what STEP fails to do (§3.3). Do not let a fourth expression appear.

**Child → parent progress: NDJSON on stdout**, one JSON object per line. Everything else the builder wants to say goes to stderr (inherited).

| Line | Parent action |
|---|---|
| `{"type":"phase","phase":"sample","total":96}` | `run.phase("sample", total=96)` |
| `{"type":"total","total":973214}` | `run.set_total(973214)` |
| `{"type":"advance","n":1,"detail":"slice 12/96"}` | `run.advance(1, detail=…)` |
| `{"type":"closure","files":["../lib/sdf.js"]}` | collect; Python computes the digest (§5.2) |
| `{"type":"result","ok":true,…}` | becomes the wrapper's payload |

Any line that is not a JSON object with a known `type` is ignored (same tolerance as `cadgen_bridge.py:145-152` — protocol robustness, not back-compat; see §0.2). If stdout pollution from a dependency ever becomes real, upgrade to a dedicated fd (`Popen(..., pass_fds=(w,))` + `fs.createWriteStream(null,{fd:3})`) — the Node analogue of `worker.py:41-45`'s dup/dup2 isolation.

**`require_write_lock`'s cross-process equivalent.** In the NEW shared JS render-package writer (§6), and only there:

```js
// NEW: packages/implicitjs/src/lib/glb/assertWriteLock.js
// suffix mirrors cadgen/coordination/paths.py:28 (declared FROZEN there for this reason)
export function assertWriteLock(packageDir, runId) {
  const sentinel = path.join(path.dirname(packageDir),
                             "." + path.basename(packageDir) + ".generation.lock");
  const stamped = fs.readFileSync(sentinel).subarray(0, 32).toString("ascii").trim();
  if (!runId || stamped !== runId) {
    throw new Error(`render package written without its generation lock: ${packageDir}`);
  }
}
```

This is sound because a run id only reaches the sentinel from **inside** `exclusive()`, after `LOCK_EX` is taken (`lock.py:167-170` then `_write_run_id` at `:179-180`, `:214-221`). A matching `--run-id` is unforgeable outside a held lock. A builder invoked directly, or with a stale id, throws — **unconditionally**, with no `CADGEN_STRICT_LOCKS` escape (§0.2: new code fails loud).

**Write ordering inside the package.** Node writes payload files first, then the descriptor **last** via temp + `fs.renameSync` — mirroring what `component_package.py` does. `_validate_render_package` requires the descriptor *and* every payload it names, so a reader sees the old descriptor or the new one, never a partial package.

**Node discovery — NEW `cadgen/_internal/node_runtime.py`:**
- `cad_node_executable(repo_root)` — env-first discovery mirroring `viewer/scripts/cad-python.mjs`'s shape: `VIEWER_CAD_NODE` → `CAD_NODE` → `shutil.which("node")`. `start-viewer.mjs` and `vite.config.mjs` both set `env.VIEWER_CAD_NODE = process.execPath`, so the launched path pins the interpreter that launched it. Imported lazily so a cadgen install that never builds these formats never looks for Node.
- **Startup probe, not first-build probe.** Extend `cadgen_bridge.probe_cadgen_runtime` / `require_cadgen_runtime` (`cadgen_bridge.py:70-118`, which already runs an isolated probe before serving) with a `[node, "-e", "process.exit(0)"]` + version-floor check, so a Node-less deployment fails at launch with a clear message rather than at the user's first `.gcode` open.

**Bounded concurrency.** A Node build bypasses the warm worker, which is the only concurrency bound in the system today. Add a module-level `threading.BoundedSemaphore(int(os.environ.get("VIEWER_NODE_BUILD_CONCURRENCY", "2")))` in `backend.py`, acquired around the wrapper subprocess, and pass `--threads max(1, os.cpu_count() // concurrency)` so §7.2's `worker_threads` pool cannot oversubscribe. **Do not** surface a queue-full state to the client — reusing `blocked` (`backend.py:331-335`) would drive `artifactActionFor` → ATTACH into a ~120 ms hot poll loop.

### 4.5 Packaging: Node the binary is available; the dependency graph is not

The published skill runtime ships `packages/cadjs` and `packages/implicitjs` **source** but no `node_modules` (verified against `origin/main`). Two consequences:

1. Builders resolve bare `implicitjs/...` / `cadjs/...` specifiers by spawning with `NODE_PATH=<viewer>/packages` — a `NODE_PATH` entry is treated as a `node_modules` dir, so `packages/implicitjs` resolves as the package `implicitjs` **through its exports map** (`packages/implicitjs/package.json:6-30`). This is the same mechanism `scripts/bundle/skills/bundle-cad.sh:166-167` already relies on (a directory `--alias` cannot do it — it bypasses the exports map).
2. **Any external npm dependency must be esbuild-bundled into a single self-contained `--platform=node` file**, exactly as `bundle-cad.sh:164-187` does for `snapshot-render.js`. This matters for `meshoptimizer` (§6). It does not matter today for the mesher/parser: `parseGcode.js`, `buildPreviewMesh.js` (gcode) and `parseDxf.js` have **zero** imports; `mesh.js` imports only siblings.

Phase-1 exit criterion: **the builder runs from a clean `bundle-cad-viewer.sh --check` output tree with `node_modules` deleted.**

#### RESOLVED — the skills bundle their builders (consequence 2 won; consequence 1 is dev-only)

Measured, not assumed: `dxf-artifact.mjs` imports `meshoptimizer` *and*, through
`buildPreviewMesh.js`, **`three`** (`Matrix4`, `ShapeUtils`, `Vector2`, `Vector3`) — so
consequence 1 alone never had a chance. Vendoring `packages/{cadjs,implicitjs}` as source
into each skill (the CAD Viewer's approach) would still leave both npm packages
unresolvable, and vendoring `node_modules` is exactly what the published tree must not do.

So **each skill esbuilds its own builders**, per consequence 2:

| Skill | `scripts/packages/cadjs/bin/…` | Bundled from |
|---|---|---|
| `dxf` | `dxf-artifact.mjs` | `packages/cadjs/bin/dxf-artifact.mjs` |
| `implicit-cad` | `implicit-artifact.mjs`, `implicitClosureHooks.mjs`, `meshWorkerEntry.js` | `packages/cadjs/bin/*`, `packages/implicitjs/src/lib/implicitCad/meshWorkerEntry.js` |

`scripts/bundle/lib/node_builders.sh` is the shared step; `three`/`meshoptimizer` versions are
read from `packages/cadjs/package-lock.json` so the committed bundles are reproducible.

**Two entries exist only because esbuild cannot inline a path computed at run time.**
`implicitClosure.mjs` does `register("./implicitClosureHooks.mjs", import.meta.url)` and
`meshWorkers.js` does `new Worker(new URL("./meshWorkerEntry.js", import.meta.url))` — both
resolve against the *bundle's* URL, so both files must be emitted beside it under those exact
basenames. `meshWorkerEntry.js` also forces a `{"type":"module"}` `package.json` into the
emitted directory: a bare `.js` with no `type` above it parses as CommonJS. Any future
`new URL(..., import.meta.url)` added to a builder graph is a new emitted entry.

**Nothing in Python changed.** `node_builder_script()` already derives
`node_package_root()/cadjs/bin/<name>`, which is the real `packages/cadjs/bin` in the dev
checkout (reached through the vendored-cadgen symlink) and the esbuilt directory in a
published skill. The `--import` resolve hook stays for the dev path; a bundled builder has no
bare specifier left for it to see.

Exit criterion met — from a real bundled tree (`rsync --exclude node_modules`, zero symlinks,
zero `node_modules`): `skills/dxf/scripts/dxf plate.dxf.py` wrote a `preview.glb`
(`EXT_meshopt_compression`), and `skills/implicit-cad/scripts/gen … --resolution 64` wrote a
388,536-triangle `model.glb` with `sourceClosureFiles` populated. Removing the emitted
`meshWorkerEntry.js` fails the build with `ERR_MODULE_NOT_FOUND`, which is what proves the
worker path was live rather than silently serial.
`tests/python/global/test_node_builder_bundles.py` guards all of it.

### 4.6 Prerequisite bug — ALREADY FIXED, do not redo

`artifact_build` published the `starting` record *before* reading the previous run's stage times. That record carries `stageMs: None` by construction (it is not a `done` outcome), so the read hit the record just written and returned nothing — every build silently fell back to `DEFAULT_PHASE_WEIGHTS` and the "weight the bar from this artifact's last build" feature was dead from the day it landed.

Measured before the fix: run 1 records `{'generate': 56, 'finalize': 26}`; run 2 learns `{}`.

**Fixed in `2c6d7882`** (read hoisted above the publish, plus a regression test in `tests/python/packages/cadgen/test_coordination.py`). It is called out here only because §7.2's progress requirement depends on it: a ~71 s indeterminate `sample` phase has no countable unit of work, so its ratio is interpolated against the *learned* duration. Nothing further to do.

### 4.7 CLI parity (T1): two entrypoints, one producer

The new formats must be buildable from the CLI, mirroring `skills/cad/scripts/gen` — not only via the viewer's POST.

**Copy the DXF shape exactly: two entrypoints, ONE producer** (§3.3). Do not add a second producer per format — a second producer that assembles the lock/record/currency-gate by hand is precisely how the D1 and D5 defects this branch just fixed came to exist (`coordination/__init__.py:3-10`).

| Source | CLI | Producer | Always builds | `--write` writes |
|---|---|---|---|---|
| `.step.py` | `cad gen` (exists) | `cadgen.step_artifact` | render package | sibling `<name>.step` |
| `.dxf.py` | `dxf` (exists) | `cadgen.dxf_artifact` | drawing package | sibling `<name>.dxf` |
| `.implicit.js` | **NEW** `skills/implicit-cad/scripts/gen` | **NEW** `cadgen.implicit_artifact` | implicit package | — (see below) |
| `.gcode` | **NEW** `skills/gcode/scripts/gen` | **NEW** `cadgen.toolpath_artifact` | toolpath package | — (see below) |

Each new CLI reproduces §3.6's six contract points: positional `targets` (`nargs="+"`), `--force`, `--verbose`, one format-specific bake knob (`--resolution` for implicit; none for toolpath), the two currency gates over the one predicate, sequential per-target locks, and CliLogger-on-stderr + one self-erasing progress line. **Omit the warm-daemon shim** from `__main__.py` — it exists to amortize the OCP import and neither format loads OCP.

**What each skill gains (the real cost of T1, and it belongs in the phase table):**

| Skill | Gains | Bundle work |
|---|---|---|
| `skills/implicit-cad` | `scripts/gen` package; a **vendored cadgen** (Python) beside the existing `packages/implicitjs` symlink; the **esbuilt cadjs implicit builder** | teach `bundle-implicit-cad.sh` `vendor_python_package` + `bundle_node_builders` |
| `skills/dxf` | the **esbuilt cadjs drawing-preview builder** beside its existing vendored cadgen | `bundle-dxf.sh` grew past the `vendor_python_skill` one-liner to add `bundle_node_builders` |
| `skills/gcode` | `scripts/gen` package; a **vendored cadgen**; the esbuilt cadjs toolpath builder. Today `skills/gcode/scripts/` is one file (`gcode_tool.py`) and vendors nothing | **NEW `scripts/bundle/skills/bundle-gcode.sh`** (none exists) — reuse `scripts/bundle/lib/node_builders.sh` |

Precedent that a Python skill CLI can ship and drive a JS runtime already exists: `skills/cad/scripts/snapshot/runtime/snapshot-render.js`, esbuild-bundled with `NODE_PATH=packages` (`bundle-cad.sh:165-187`).

Both phases' exit criteria gain **`scripts/bundle/bundle.sh --check` clean**.

#### The `--write` flag, unified

Each gen CLI is already format-specific, so the format does not need repeating in the flag name. **One spelling everywhere: `--write`.** Both existing flags are renamed; **no aliases are kept** (§0.2).

| Was | Becomes | Site |
|---|---|---|
| `cad gen --write-step` | `cad gen --write` | `skills/cad/scripts/gen/cli.py:35-37`, help at `:116`, and `DEFAULT_STEP_OUTPUT` at `:10-11` |
| `dxf --dxf` | `dxf --write` | `skills/dxf/scripts/dxf/cli.py:60-64`, and `write_dxf=bool(args.dxf)` at `:103` |

Update the corresponding `SKILL.md` / reference docs in the same change.

#### What `--write` means, precisely

Two different files are in play and **only one of them is opt-in**:

1. **The package payload** — `__cadgen__/models/<entry>/…` (`drawing.dxf`, `preview.glb`, `toolpath.glb`, `model.glb`, the STEP component GLBs). **Always written.** It *is* the artifact; the viewer renders it and the freshness validator checks it.
2. **The user-facing sibling** next to the source file. **Opt-in via `--write`.**

So "does gen export DXF by default?" has two answers and both matter: **yes** inside the package (`drawing.dxf`, `drawing_package.py:38`) because that is the artifact, and **no** as a sibling `<name>.dxf`. No behavioural change, only the flag rename.

**Neither new format takes `--write`:** `.implicit.js` has no single canonical sibling format (its outputs are GLB/STL/3MF, which is what `export` is for); `.gcode` **is** the deliverable.

#### Export: alignment, not creation — **the exporter already ships**

`packages/implicitjs/scripts/export.mjs` already exports **glb, stl and 3mf** — the exact three formats requested. Everything in this table exists today; **do not put "build an implicit export script" in any phase.**

| Thing | Where | State |
|---|---|---|
| Format list | `exportModel.js:7`, frozen | **exactly the three requested** |
| Dispatch | `exporters.js:561-585` `meshToFormat` | ships |
| GLB / STL / 3MF writers | `exporters.js:193-257` / `:169-191` / `:508-559` | ship |
| Animated GLB | `exportModel.js:191-268` | ships |
| CLI | `packages/implicitjs/scripts/export.mjs` | ships |
| Skill entry point | `skills/implicit-cad/scripts/export.mjs` (node shim, `spawnSync`, propagates status) | ships |
| Bundle guard / docs | `bundle-implicit-cad.sh:128` / `SKILL.md:163-169` | ship |
| Mesh-once-write-three | `verify-implicit-cad-exports.mjs:186-206` | **the pattern exists, just not in the CLI** |

**The contract gap, and the exact delta.** Scope the work as alignment with `skills/cad/scripts/export`:

| | `skills/cad/scripts/export` | `implicitjs/scripts/export.mjs` today |
|---|---|---|
| Target | positional (`cli.py:29-31`) | `--input`/`-i` or bare positional (`:66-68`) |
| Formats | `--stl`/`--3mf`/`--glb`, optional-valued, **several per run** (`:32-53`) | one `--format <fmt>` (`:74-77`) |
| Default output | sentinel → sibling `<name>.<ext>`; relative resolves **beside the model** (`step_export_target.py:269-283`) | sibling default matches (`export.js:25-32`); `--output` resolves against **CWD** (`export.js:75`) |
| None requested | `"at least one export format is required: --stl, --3mf, or --glb"` (`:103`) | silently defaults to glb |
| Geometry | built **once per run**, all formats from identical geometry (`:84-95`) | one format per process → 3 formats = 3 meshings |
| Exit codes | usage → 2, success → 0 | everything → 1 (`export.mjs:135-138`) |

Deltas, all inside `packages/implicitjs/scripts/export.mjs` (**the skill shim is argument-transparent and needs no change**):

1. **Positional target.** Delete `--input`/`-i`. No alias.
2. **Flag-per-format.** Add `--stl [OUT]` / `--3mf [OUT]` / `--glb [OUT]` with the sibling-default sentinel; delete `--format`/`-f`; reuse cad's error string verbatim.
3. **One mesh, N formats** — the `verify-implicit-cad-exports.mjs:188-199` shape. **Byte-safe:** the STL writer recomputes facet normals from positions (`exporters.js:178`) and the 3MF writer reads positions only (`:516`), so `smoothNormals` affects the GLB alone; STL/3MF bytes are unchanged. But note today's `exportImplicitCadModel` picks `smoothNormals: smoothNormals ?? outputFormat === "glb"` (`exportModel.js:174`), so build-once forces `smoothNormals` to become **one explicit shared choice** (recommend `true`).
4. **Model-relative output paths**, matching `_resolve_export_output` (`step_export_target.py:281-282`).
5. **Exit codes:** usage → 2, runtime failure → 1, success → 0. **Keep `--json`** — agents parse it; the alignment moves toward cad's grammar, not away from capability.
6. **`--animated` is GLB-only** — error if combined with `--stl`/`--3mf` rather than silently ignoring them. Resolve the split default (static 96 vs animated 64, `exportModel.js:198`): 96 static, 64 when `--animated` unless `--resolution` is explicit; document in `--help`.
7. **Keep** `--resolution`, `--max-cells`, `--params`, `--animation`, `--frames`, `--duration`, `--json`.

Resulting surface:

```
node scripts/export.mjs <model.implicit.js>
     [--stl [OUT]] [--3mf [OUT]] [--glb [OUT]]
     [--resolution N] [--max-cells N] [--params JSON] [--animation JSON]
     [--animated] [--frames N] [--duration S] [--json] [--verbose]
```

**Do not move the export CLI into a `scripts/export/` package "for symmetry with cad."** That was built (`55fa0f9f`) and deleted (`01dc8b0d`): an argparse wrapper that re-declared every flag in Python and then `subprocess.run`'d node — the flag surface maintained twice in two languages. `scripts/dev/skills/setup-implicit-cad-skill-symlink.sh:48-51` still guards against a tracked `scripts/export/runtime`. cad's package form exists for **Python-only** reasons (the warm-daemon shim; the vendored-cadgen `sys.path` precedence block in `skills/cad/scripts/export/__main__.py`); a node CLI has neither. The rule is **same CLI grammar, different host language, different file layout** — the asymmetry is deliberate.

**Measured export baseline** (this worktree, node v22.22.0, `models/implicits/sphere-boolean-cuts.implicit.js`) — record as the phase-0 baseline the aligned CLI must not regress:

| Format | B/triangle @ res 32 | @ res 48 | Extrapolated to `gyroid-window` @ res 96 (972,816 tris) |
|---|---|---|---|
| GLB | 72.07 | 72.03 | ~70.0 MB (confirms §7.2's 66.80 MiB) |
| STL | 50.01 | 50.00 | ~48.6 MB |
| **3MF** | **279.6** | **274.5** | **~267 MB** |

3MF is 4× GLB and 5.5× STL for two independent, cheap-to-fix reasons: `meshTo3mf` emits **one vertex per triangle corner** with no welding (`exporters.js:510-521`, ~3× duplication), and `zipStore` writes **compression method 0** (`:450-471`, method written at `:463`) so the ASCII XML is never deflated — the res-32 3MF is 3,841,928 B stored but **267,104 B under `gzip -9`, a 14.4× ratio thrown away.** Both fixes together take a res-96 3MF from ~267 MB to roughly 19 MB. Optional but recommended in phase 0; it is the largest byte win in the export path and needs no new architecture.

**Export stays live-valued** (this answers half of §12 decision 2). Render and export are different products: the render artifact must be reproducible from its descriptor and keyed by `bakeHash`, so a live parameter would poison §5.3's two-authority contract; the export is a user deliverable fed to slicers and CAM, and non-default resolution/params are the documented workflow (`SKILL.md:163-165`). The coordination system already has the right primitive:

> **Render** bakes at `params.*.default` under `artifact_build`.
> **Export** runs at caller-supplied values under `generator_busy` (`coordination/__init__.py:349-392`).
> An export is **not an artifact**: no descriptor, no `bakeHash`, no freshness, never inside `__cadgen__/`.

**The browser-side export is deleted, not kept.** `viewer/src/client/workbench/implicitExport.js` meshes and serializes **in the browser** (`:22-26`, `:49-54`) and POSTs the encoded bytes to `/__cad/implicit-export`, where `backend.generate_implicit_export` (`backend.py:524-548`) merely writes them to disk (`server.py:163-164`, `:339-346`). That is a second full implementation of the same export, and it re-declares the format list independently of `exportModel.js:7`. Replace it: the viewer's Export action asks the server to run **the same node export CLI** under `generator_busy`. One export implementation, and the browser stops needing the geometry runtime — the same argument this plan makes for the render path. **Lands in phase 3 with the §8 client deletions.**

**G-code gets no export command.** `skills/gcode/scripts/gcode_tool.py` exposes `discover`/`inspect`/`slice`/`validate` (`:752-776`); `slice` *writes* the `.gcode`, which **is** the deliverable, and its inputs are meshes — `.stl/.obj/.3mf` direct, `.ply/.glb/.gltf` converted (`:20-21`). The arrow points **into** g-code from the mesh formats. State it positively once: **implicit gets gen + export; g-code gets gen only, because its gen output is the export.**

Two corrections to fold into the same pass (T4's remove-and-replace mandate):

- `gcode_tool.py`'s `UNSUPPORTED_INPUT_REMEDIATION` tells agents to run `python scripts/step --kind part <input> --stl <output>.stl` in four places (`:27-29`, `:37`, `:50`, plus `SKILL.md:127-128`). **`scripts/step` no longer exists** — it was split into `scripts/gen` and `scripts/export`. Correct to `python scripts/export <target> --stl`.
- The remediation map (`:56-63`) has no `.implicit.js` / `.implicit.mjs` key, so an implicit model handed to g-code gets no routing at all. Add one pointing at the implicit-cad export CLI (`--stl`) — the real pipeline is **implicit export → STL → gcode slice**.
- **Guardrail:** the slicing input is the *exported* STL, never the baked render GLB. `CONVERT_TO_STL_EXTENSIONS` (`:21`) would happily accept a `.glb`, but the render bake is quantized, meshopt-compressed and possibly strided (§7.1.3).

#### Consequence for the drawing package

Under §7.4 the drawing package gains `preview.glb` alongside `drawing.dxf`, so it carries **two payloads with different jobs** (exchange artifact vs render artifact). `_DRAWING_PACKAGE`'s `payload_refs` currently returns only `[descriptor["dxf"]]` (`viewer/server_py/artifact.py:80-87`); it must return both, or a missing or half-written `preview.glb` will not mark the package stale and the viewer will render nothing with no `needs-build` to explain it.

---

## 5. Package shapes and freshness

### 5.1 Spec-table entries

| Format | Descriptor | `kind` | Payload refs |
|---|---|---|---|
| G-code | `toolpath.json` | `toolpath-package` | `toolpath.glb` |
| Implicit | `implicit.json` | `implicit-package` | `model.glb` |
| DXF (extend) | `drawing.json` | `drawing-package` | `<existing>.dxf` **+ `preview.glb`** |

```jsonc
// toolpath.json
{ "kind": "toolpath-package", "packageSchemaVersion": 1, "units": "mm",
  "sourceKind": "gcode", "sourceDigest": "<sha256 of the .gcode>",
  "glb": "toolpath.glb",
  "bake": { "detailMode": "full", "showTravel": true,
            "extrusionWidthMm": 0.42, "travelWidthMm": 0.08,
            "extrusionHeightMm": 0.18, "travelHeightMm": 0.04,
            "zBiasScale": 8 },
  "bakeHash": "<sha256 over the canonicalized bake block>",
  "layers": [{ "index": 0, "nodeName": "layer:0", "zMm": 0.2, "segmentCount": 4312 }],
  "stats": { "segmentCount": 220202, "layerCount": 51, "primitiveCount": 52 },
  "bbox": [...] }
```

Note `travel` is baked but hidden by default: `buildPreviewMesh.js:132` defaults `showTravel` to **false**, and travel is what produces the 5,429-group explosion. Bake it (the toggle is the point), but measure the size delta and record it.

**`packageSchemaVersion` must earn its place (T4).** Today it is **write-only dead surface**: written by `component_package.py:698` (from `PACKAGE_SCHEMA_VERSION = 2` at `:46`) and `drawing_package.py:142` (from `DRAWING_PACKAGE_SCHEMA_VERSION = 1` at `:36`), and read by **nobody** — no validator, no gate, no client. Adding it to two more descriptors would mint two more dead fields, exactly the surface `abb10521` cut. So gate on it:

- add `schema_version` to **all four** spec-table entries (`artifact.py:72-87`);
- add one line to `_validate_render_package`:

```python
if _as_int(descriptor.get("packageSchemaVersion")) != spec["schema_version"]:
    return (False, spec["unsupported"])
```

`unsupported_*` is already in `BUILDABLE_STEP_ARTIFACT_CODES` (`artifact.py:42-49`), so a version bump auto-rebuilds. **This is the plan's single invalidation channel**: bumping it invalidates every package of that kind and costs one lazy rebuild each. There will be **no per-field aliases** — this replaces every future per-field compat branch. It matches `record.py:165`'s posture (strict equality, no tolerance). If the plan declines this, drop `packageSchemaVersion` rather than ship it dead.

New `ArtifactKind` module constants in `coordination/kinds.py`, beside `STEP_PACKAGE` and `DRAWING_PACKAGE` (no registry — `register()`/`lookup()` were added then deleted as dead surface):

```python
TOOLPATH_PACKAGE = ArtifactKind(name="toolpath-package",
                                phases=(PHASE_PARSE, PHASE_MESH, PHASE_WRITE))
IMPLICIT_PACKAGE = ArtifactKind(name="implicit-package",
                                phases=(PHASE_SAMPLE, PHASE_POLYGONIZE, PHASE_WELD, PHASE_WRITE))
```

with the new `PHASE_*` constants and their `PHASE_LABELS` entries in `coordination/phases.py:36-52`. **One small cadgen change is required and only one:** add `labels: Mapping[str, str] = field(default_factory=dict)` to `ArtifactKind` (`kinds.py:26-37`) and a `labels` kwarg to `ProgressReporter.__init__` merged over `PHASE_LABELS` at the `phases.py:312` lookup, passed from `artifact_build` (`__init__.py:274-278`). Otherwise the viewer's phases render as raw lowercase tokens.

**Make the dominant phase determinate.** `run.phase(PHASE_SAMPLE, total=<z-slice count>)` + `run.advance()` per slice — the count is known before sampling starts, and a determinate phase reports a real count with no clock interpolation (`phases.py:271-272`, `:284-299`). Report the first phase **before** loading the model module so the client's ~120 ms first poll finds a bar. This also pays off in the CLI, where a determinate phase renders `[bar] NN%  label 31/50` (§3.6 point 6).

### 5.2 Provenance: Node knows which files, Python owns the digest

The builder emits `{"type":"closure","files":[…]}` (enumerable from a `--experimental-loader` resolve hook or `module.children`). The producer — which imports `cadgen._internal.source_hash` exactly as `artifact.py:33` does — calls `closure_for_files(script_path, files, base=model_folder)` and writes `sourceKind` / `sourceClosureFiles` / `sourceClosureHash` into the descriptor itself, after the child exits and while still holding the lock. Verified compatible: `_semantic_source_hash` byte-hashes non-`.py` inputs (`source_hash.py:109-110`), so a `.js` closure validates through the `closure_hash_matches` path at `artifact.py:134-138` — **and is unaffected by §5.6's deletion of that function's legacy byte pass.**

### 5.3 `bakeHash` — and the fail-closed source digest

This is **not** "one optional comparison". Two things change, both in phase 0.

**(a) `bakeHash`.** Add the field. Then, per format, name which authority owns the bake:

- **STEP** — passes `None`. Unchanged.
- **Toolpath / implicit** — the producer's `is_current` and the viewer's spec-table predicate are **the same module-level function** (§4.4), so one comparison genuinely suffices and the two agree by construction.
- **DXF (phase 4)** — must extend `drawing_package_current` (`_internal/drawing_package.py:188-205`) **itself**, not add a sibling. It compares only the `.dxf` payload's presence and `sourceClosureHash`, so a changed `defaultThicknessMm` leaves it returning `True` while the viewer reports `stale_dxf_artifact`. **Non-optional now that phase 4 is required (§7.4).**

**If the two ever disagree** (viewer stale, producer current), the failure is **silent**, not a visible loop: `run.skipped` → `OUTCOME_SKIPPED` → `backend.py:422-424` answers `ready` → `useArtifact.js:181` settles READY without re-checking, and the effect only re-runs on `activeRef`/`freshnessKey` (`CadWorkspace.js:1399` = entry hash + manifestRevision), neither of which a skipped build changes. The stale-bake package renders. That is exactly the failure `bakeHash` exists to prevent.

**(b) The imported digest must fail closed — per-format field names, no alias (T4).** Fix §3.3's defect:

1. The spec table (`artifact.py:72-87`) gains **`source_digest_field`** and `missing_digest`.
2. **Do not rename `stepHash`, and do not alias it.** Name the key per format in the spec table: `"stepHash"` for `_STEP_PACKAGE`, `"sourceDigest"` for `toolpath` / `implicit` / `drawing`. `stepHash` is load-bearing at ~14 cadgen sites well beyond the render descriptor — `step_targets.py:290,344`, `step_artifacts.py:360-365`, `step_artifact.py:141,172`, `_internal/component_package.py:65`, `_internal/generation.py:1216,1226,1421`, `_internal/glb.py:179,223`, `_internal/step_scene.py:1338,1429` — **including GLB manifests and the BREP scene cache**, which are different artifacts from the render package. Per-format naming is exactly what the spec table is for; an alias is a shim.
3. The imported branch returns `(False, spec["missing_digest"])` when the source file exists (`scanner._file_stats(source_path)` truthy) and the named digest is missing or blank — never today's `return (True, None)` at `:144`. Reuse `missing_step_hash` as `_STEP_PACKAGE`'s value: it is already in `BUILDABLE_STEP_ARTIFACT_CODES` (`artifact.py:45`), already in the client list (`stepArtifactStatus.js:13`) and already has copy in `fileStatusItems.js`. The fix makes a dead code live rather than minting a new one.
4. This is **alignment, not new policy**: cadgen's gate already fails closed (`generation.py:1222-1226`) and the *generated* branch of this same function already does (`artifact.py:132-133`). The imported branch is the lone fail-open path.

Phase 0's exit criterion is therefore "STEP/DXF freshness unchanged **except**: an imported descriptor with no digest now reports `needs-build` instead of `ready`, matching cadgen's producer gate."

### 5.4 Buildable codes
`BUILDABLE_STEP_ARTIFACT_CODES` gains `missing_toolpath_artifact` / `stale_toolpath_artifact` / `unsupported_toolpath_artifact` and the implicit equivalents. Rename to `BUILDABLE_ARTIFACT_CODES` in the same change — four call sites: `artifact.py:42`, `backend.py:329`, `viewer/server_py/tests/test_artifact.py:299` and `:416`.

Client side: `stepArtifactCanGenerate` / `stepArtifactNeedsWarning` gate on `sourceFormat === RENDER_FORMAT.STEP` (`viewer/src/client/workbench/stepArtifactStatus.js`); generalize to "is an artifact-managed entry". Note the client's `BUILDABLE_STEP_ARTIFACT_ERROR_CODES` (`stepArtifactStatus.js:6-16`) is **already missing** the three DXF codes — see §10 for the pin that catches this.

### 5.5 Ownership and dispatch must be made total
`artifact.owns_entry` (`artifact.py:65-66`) and `Backend._artifact_format` (`backend.py:274-284`) must be extended, or gcode/implicit entries report `ready` unconditionally and never build. While there: replace `_artifact_format`'s if/else with an ordered predicate→record table that **raises** (or returns an explicit `unsupported` error state) when nothing matches, so a half-wired format fails loudly instead of silently answering as STEP.

**T3 consequence — widen `owns_dxf_entry`.** `artifact.owns_dxf_entry` (`artifact.py:59-62`) today deliberately owns *"Generated `.dxf.py` drawings only; a raw imported `.dxf` renders directly from disk and never needs a build."* Once phase 3 deletes the client DXF tier (§7.4), that comment is false: an imported `.dxf` has no renderer left. **Widen `owns_dxf_entry` to imported `.dxf` and delete the comment.** Its freshness takes the *imported* branch with `source_digest_field = "sourceDigest"` (a plain sha256 of the `.dxf`), and its producer is the same `cadgen.dxf_artifact` wrapper with the ezdxf generation step skipped and only the Node mesh step run. Without this, DXF keeps a path forever and nobody's task list currently covers it.

### 5.6 NEW — delete the legacy closure digest (T4)

`closure_hash_matches` (`packages/cadgen/src/cadgen/_internal/source_hash.py:447-472`) tries **two** hashers in sequence — `_semantic_source_hash`, then `_sha256_file` — and its docstring states the purpose in T4's own vocabulary: *"Accepts EITHER the current semantic (AST) recompute OR the legacy byte recompute: descriptors written before comment-insensitive hashing recorded a byte-based digest, and must keep validating (no mass rebuild on upgrade) until their next genuine rebuild re-records the semantic digest."* That is shape-identical to the `record.progress_for_run` v1 branch removed in `7721f5e6`, and it is the last data-compat path in the freshness stack.

**Delete the second pass.** It is safe and it does not affect this plan's new `.js` closures: `_semantic_source_hash` already byte-hashes every non-`.py` input (`:109-110`) and already falls back to bytes on an unparseable or unreadable Python source (`:120-123`). The `_sha256_file` pass at `:468` is reachable **only** for descriptors recorded before semantic hashing landed. Removing it also collects a perf win the code documents itself (`:459-467`: the byte pass "re-reads every file's full contents each check").

Blast radius: the loop at `:468` collapses to one hasher; four production callers are signature-unaffected (`viewer/server_py/artifact.py:134`, `generation.py:1929`, `generation.py:2011`, `_internal/drawing_package.py:205`); one test inverts — `tests/python/skills/cad/cadgen/test_semantic_closure_hash.py:66` asserts a legacy byte digest still validates and becomes an `assertFalse` (the semantic case at `:74` and the missing-file cases at `:79`/`:108` stand).

**User-facing consequence, to be stated in the PR body, not discovered:** every existing `__cadgen__` package whose descriptor predates semantic hashing reports stale once and rebuilds. The rebuild is lazy (only on reopen) and `__cadgen__/` is a gitignored cache (`.gitignore:8-11`), but it is real time — ~30 s for `tom`, ~71 s for a resolution-96 implicit.

---

## 6. Shared GLB writer

Neither existing writer suffices: `meshToGlb` (`exporters.js:193`) is single-mesh, single-primitive, non-indexed f32 (72 B/triangle); cadgen's `_GlbBuilder` is Python.

Add **one** JS GLB writer, **NEW** `packages/implicitjs/src/lib/glb/writeGlb.js`, re-exported from cadjs as `cadjs/glb/writeGlb.js`. It lives in implicitjs per the repo dependency rule (shared primitives source in implicitjs, re-exported by cadjs, as with `common/camera.js`); it is a generic mesh serializer with no implicit-specific behaviour.

**Two corrections to the previous draft.**

1. **Split the writer from the package-writing boundary.** The previous text said `writeGlb` "is also the only supported way to write a render package, and it calls `assertWriteLock`", *and* that `meshToGlb` becomes a thin wrapper over it. Those are incompatible: every ordinary `export --glb` holds no generation lock and has no `runId`, so it would throw. Therefore:
   - **NEW `writeGlb(mesh, options) -> bytes`** — pure, lock-free, used by both render and export.
   - **NEW `writeRenderPackage(packageDir, runId, …)`** — calls `assertWriteLock` (§4.4) and then `writeGlb`. This is the only supported way to write a render package.
2. **`meshToGlb` is deleted** (T4), not kept as a thin wrapper — a delegating wrapper with no behaviour of its own is the shape `7721f5e6` refused for `_internal/progress.py`. Repoint `meshToFormat` (`exporters.js:561-585`) and `exportModel.js:179` at `writeGlb` directly. If it survives, it must survive with content `writeGlb` does not have — and the plan must say what that content is.

Required capabilities:
- indexed primitives with vertex welding
- **`UNSIGNED_SHORT` indices per primitive when the primitive has ≤ 65,535 vertices** (halves index bytes; assert in the budget test that no primitive exceeds the cap so a pathological file fails CI instead of silently shipping u32)
- multiple nodes / primitives with `extras.cadOccurrenceId` matching the STEP convention
- per-primitive materials
- `KHR_mesh_quantization` — positions `SHORT`, normals `BYTE` normalized (respect glTF 4-byte element alignment: `VEC3`/`SHORT` = 6 B padded to 8; `VEC3`/`BYTE` = 3 B padded to 4)
- **`EXT_meshopt_compression` — REQUIRED for render packages.** Every size budget below depends on it.

**Two option presets, one writer.** The **render** preset is indexed + welded + quantized + meshopt-compressed. The **export** preset is indexed + welded but **unquantized and uncompressed** — most slicers and stock glTF importers cannot read `EXT_meshopt_compression`, and a shared-writer-with-shared-defaults would silently ship an export nothing can open.

Record but do **not** silently fix here: the implicit export GLB is mm-scale in model space with `extras.cadUnits: "mm"` (`exporters.js:210-214`) and a single averaged `baseColorFactor` (`exportModel.js:40-72`, `:181`), while cad's native GLB export is documented as Y-up, meter-scaled, extension-free "for external tools" (`skills/cad/references/supported-exports.md:9`). That divergence predates this plan and is listed as an open sub-question in §13.

**STL and 3MF writers are deliberately not shared.** Two writers per format exist by necessity: JS (`exporters.js:169`, `:508`) for implicit, Python/OCP (`cadgen/_internal/stl.py:21-25`, `threemf.py:88`) for STEP, and the Python 3MF carries a material registry and assembly-component emission (`threemf.py:36`, `:305`) a single-solid implicit mesh has no use for. §13's reuse meta-goal is about the viewer's **loaders**, not the writers.

Loader wiring: `KHR_mesh_quantization` is core `GLTFLoader` support; `EXT_meshopt_compression` needs a decoder registered in **both** `glbMeshData.js:479` and `glbMeshWorker.js`. Add `meshoptimizer` to `packages/cadjs/package.json`; it is bundled by vite for the client and must be **esbuild-bundled into the builder** for the server side (§4.5). **Phase 0 must measure the encoder's real ratio on the flange fixture** — every downstream budget is set by that number, so do not commit phase-1/2 byte budgets before it.

---

## 6.1 MEASURED — meshopt's real ratio (phase-0 gate, recorded)

Every phase-1/2 byte budget is set from these numbers. Measured on this branch with
`writeGlb` + `meshoptimizer@1.2.0`, node v22.22.0, darwin. **Not estimates.**

| Fixture | `meshToGlb` (old, non-indexed f32) | export preset (welded+indexed) | **render preset** (+quantized+meshopt) | old → render |
|---|---|---|---|---|
| `gyroid-window.implicit.js` @ res 96 | 66.80 MB | 22.34 MB | **6.11 MB** | **10.94×** |
| `sphere-boolean-cuts.implicit.js` @ res 48 | 2.10 MB | 0.52 MB | **0.18 MB** | **11.73×** |
| `circular_flange_plate_sample.gcode`, 1 primitive, no colours | n/a | 25.20 MB | **7.24 MB** | — |

**meshopt+quantization ratio: 3.48× (toolpath) to 3.66× (gyroid) over an already
welded+indexed GLB**, and 4.87× over the raw attribute buffers. Welding alone accounts for
the rest: it is 3.0× on the gyroid and 4.0× on the sphere before meshopt runs.

Geometry figures the original plan claimed are CONFIRMED exactly: 220,202 segments, 51
layers, **5,429 groups** (the group explosion is real), 35.28 MB raw toolpath buffers,
972,816 gyroid triangles, 66.80 MB non-indexed.

**Two corrections to the plan's own figures.**

1. **The gyroid CPU mesh is 145.1 s, not 71 s** — roughly double. Phase 2's `worker_threads`
   sampling is therefore not an optimisation, it is the difference between a tolerable build
   and an intolerable one. Do not exit phase 2 on an estimated speedup.
2. **The toolpath lands at 7.24 MB, above the 6.0 MB source**, not in the "4–6 MB" zone the
   original estimated, and this is the *optimistic* single-primitive case — the required
   regroup into `layerCount + 1` primitives adds 52 sets of accessors/bufferViews/meshopt
   headers and compresses slightly worse per buffer. **Phase 1's exit criterion must be set
   from a regrouped measurement, not from this one.** "Target ≤ source size" is not met; the
   justification for phase 1 rests on deleting 626 ms of client work and the fifth render
   path, not on bytes.

---

## 7. Per-format builder specs

All raw figures are measured on `56a119c0`, and remain valid: `git diff --stat 56a119c0 HEAD -- packages/cadjs packages/implicitjs` is **empty**, and cadgen's GLB/mesh files are untouched.

### 7.1 G-code

`models/gcode/circular_flange_plate_sample.gcode` — 5.99 MiB source, **220,202 segments** (6,137 travel + 214,065 extrusion), **51 layers**, 880,808 vertices, 440,404 triangles, full detail with travel:

| Buffer | Raw | After |
|---|---|---|
| positions f32 12 B/v | 10.08 MiB | `SHORT`+pad 8 B → **6.72 MiB** |
| normals f32 12 B/v | 10.08 MiB | `BYTE`+pad 4 B → **3.36 MiB** |
| colors f32 12 B/v | 10.08 MiB | **0** (per-primitive material) |
| indices u32 | 5.04 MiB | `UNSIGNED_SHORT` → **2.52 MiB** |
| **total** | **35.28 MiB** | **12.60 MiB pre-meshopt** |

Parse costs 468 ms on the main thread; the full-detail mesh build adds 141–234 ms. Baking removes both.

**Corrections to the original's size path.** "4–6 MB" is *not* reachable without meshopt — 12.6 MiB is. With meshopt it is plausible (normals are the constant `(0,0,1)` for all 880,808 vertices — `buildPreviewMesh.js:45` `RIBBON_NORMAL` — and compress to essentially nothing; meshopt's index codec typically reaches ~1–2 bits/triangle). Commit **≤ 14 MiB without meshopt** as the hard budget and **4–6 MB with** as the goal, confirmed by phase 0's measurement.

**Three problems the builder must solve:**

1. **Group explosion.** `parts` are contiguous runs keyed by `segmentGroupKey` (`buildPreviewMesh.js:154-159`), so interleaved travel produces **5,429 groups** (51 without travel). The builder must **regroup by key** into buckets and emit vertices bucket-ordered. Regrouping is safe: `parts` are consumed as contiguous index-range slices (`packages/cadjs/src/common/cadScene.js:685-721`), nothing depends on interleaved run order, and there is no blending in this path. **Correction:** regroup by `(layerIndex, colorKey)`, not by `segmentGroupKey` — `segmentColor` returns `SUPPORT_COLOR` for `featureCategory === "support"` (`buildPreviewMesh.js:283-288`) regardless of the group key, so colour is **not** constant within a `layer:N` group when supports exist. Budget: **≤ 2×layerCount + 1** primitives (52 for this fixture, which has no supports; ≤ 103 in general). Re-measure the "29% saving" on a support-bearing fixture. Note `part.id` collapses from 5,429 ids of the form `gcode:layer:N:runIndex` (`buildPreviewMesh.js:465`) to ≤ 103 — fine for a new artifact format, but these are the selection handles, so say so in the descriptor.

2. **Quantization destroys the z-bias ladder.** `FEATURE_CATEGORY_Z_BIAS_MM` (`buildPreviewMesh.js:33-41`) spans **0.001 mm (support) → 0.006 mm (wall)**, with `TRAVEL_Z_BIAS_MM = 0.008` (`:42`) — a total span of 0.007 mm. Positions quantized to `SHORT` over a ~250 mm bed give a step of ~0.0076 mm, **larger than the whole ladder**. Every category collapses onto one plane and coplanar ribbons z-fight. Fix: scale the ladder so the smallest delta is ≥ 3 quantization steps (~0.023 mm — still an eighth of the 0.18 mm layer height), record `zBiasScale` in `bake` so `bakeHash` covers it. Alternative: per-primitive node translations for the category offsets. Either way, **add a G-code visual check to the phase-1 exit criteria** — size + draw-call budgets cannot detect this, and §10's visual regression is implicit-only.

3. **Large-file policy.** `detailMode: "full"` on a 50 MB `.gcode` is unbounded. Record the effective segment budget in `bake`, bake an adaptive stride above a threshold, and record `stats.stridedFrom` so the viewer can say the preview is decimated. Add a ≥ 50 MB fixture to phase-1 exit criteria. **The strided/quantized/compressed render GLB is never a slicing input** (§4.7).

Client-side layer scrubbing rebinds from "re-mesh with a new `layerRange`" to "set `node.visible`" — strictly cheaper.

### 7.2 Implicit

`models/implicits/gyroid-window.implicit.js` — 2.1 KB source, via `meshImplicitCadModel` + today's non-indexed GLB writer:

| resolution | CPU mesh | triangles | GLB (non-indexed) |
|---|---|---|---|
| 64 | 26 s | 389k | 26.7 MB |
| **96 (`DEFAULT_RESOLUTION`, mesh.js:4)** | **71 s** | **972,816** | **66.80 MiB** |
| 128 | 140 s | 1.7M | 118.4 MB |

`sphere-boolean-cuts.implicit.js`, the simplest fixture, is 4.4 s / 31k tris / 2.1 MB at resolution 48. Measured 2.015 triangles per unique vertex at res 96 → **482,738 unique vertices**.

**Bake at resolution 96**, with 128 opt-in per model via a descriptor field. Document the practical ceiling: `mesh.js:5` caps total cells at 2,500,000 and `mesh.js:35` clamps resolution to [8,192]; a cubic bound at 128 is 2,097,152 cells, just under the cap, so anything above 128 is silently downscaled by `normalizedGrid` (`mesh.js:38-54`).

**Corrected size arithmetic** (the original's "6–8 MB" was wrong):

| Buffer | Bytes |
|---|---|
| positions `SHORT`+pad, 482,738 v | 3.86 MB |
| normals `BYTE`+pad | 1.93 MB |
| vertex colors `UNSIGNED_BYTE` VEC4 (omitted from the original entirely) | 1.93 MB |
| indices u32, 2,918,448 | **11.67 MB** |
| **total welded + quantized** | **~19.4 MB (≈18.5 MiB)** |

Indices dominate. **Welding is not what closes the gap — meshopt's index codec is.** Set phase 2's byte budget from phase 0's measured ratio; do not commit to "≤ 10 MB" beforehand.

**Optimizations, re-prioritized:**

0. **Compile the transpiled SDF.** `sdfEvaluator.js` is a GLSL→JS transpiler; evaluate compiling its parsed AST to a JS closure via `new Function` before reaching for threads. *(Reported by the review's instrumentation; re-measure before committing.)*
1. **Index + weld.** `meshImplicitCadModel` already supports `smoothNormals: true` with a `normalCache` (`mesh.js:130-137`, `:249`). Welding on exact coordinates is sound: `interpolateVertex` (`mesh.js:140-150`) computes shared cube-edge intersections from identical inputs, so they are bit-identical across adjacent cells — which is what the `normalCache` key already assumes. Bucket numerically with `+0` normalization (`v === 0 ? 0 : v` before quantizing), **not** `toPrecision` string concatenation.
2. **Parallelize BOTH loops, not just sampling.** The polygonize loop (`mesh.js:251-274`) is also separable over `iz` — it reads `values` read-only at `cz ∈ {iz, iz+1}` and only appends to `mesh.positions`/`mesh.normals`. Use `worker_threads` over z-slabs with per-slab output buffers concatenated in slab order (which also preserves the byte-determinism §10 requires) and a per-worker `normalCache` (`estimateGradient` is pure, so duplicated boundary work yields identical values). Marshalling: send a pruned, data-only payload (`{glslSource, distanceSource, uniforms, bounds, size, normalEpsilon}`) — verified structuredClone-able and evaluator-equivalent — or pass the module URL and let each worker import independently. **Do not exit phase 2 on an unmeasured speedup claim.**
3. **Cut orientation cost.** `normalFacesOutward` (`mesh.js:124-128`, used at `:167` when `orientBySdf`) re-probes the field per triangle to decide winding — ~34% of all sdf calls — even though the eight corner values are already in `values[]` and, with `smoothNormals` on, the gradients are already cached. Derive winding from the cached gradients.
4. **Progress.** Report through `run.phase()` / `run.advance()` (§4.4), never by writing the record — a Node-written record has no matching sentinel runId and is silently discarded (`record.py:172-173`).

Bake vertex colors by evaluating `color(p, normal)` per welded vertex (482,738 additional evaluator calls) so the per-pixel field degrades to per-vertex rather than disappearing.

**Risk to state plainly:** the CPU `sdfEvaluator` is a transpile of the model's GLSL and has diverged from the shader before (the normalizer has mangled `1.0e-6` and `i == 0`). This plan promotes it from export-only to *the thing users see*. §10 gates on that — but with a **field-agreement** test, not an image diff.

### 7.3 Implicit animations — dropped

**Dropped, with no opt-in.** `meshToAnimatedGlb` (`exporters.js:259`) survives because the **export** path uses it (§4.7 delta item 6), not as a render escape hatch.

The sizing is recorded as the reason any future opt-in would need a hard build-time ceiling, not as an invitation: ~**14 MB/frame** at resolution 64 (not 7), with a default of **18 frames** — ~250 MB unbaked. Against the *welded* mesh, §7.2 optimization 1 roughly halves it (2.015 non-indexed verts per unique vertex). Not scope here.

### 7.4 DXF — **3D-only, and phase 4 is therefore REQUIRED** (T3)

#### 7.4.0 What "the 2D view" actually is

DXF is the only entry with **two renderers**, not one renderer with two presentations:

| View | Renderer | Data it consumes |
|---|---|---|
| **2D** (today's default) | `viewer/src/client/components/DxfViewer.js` — 752 lines of **inline SVG** with its own viewBox pan/zoom (`:493`), wheel zoom, ResizeObserver fit, and an SVG-serialize→canvas screenshot (`:448-472`) | `dxfData.paths` (`:695`), `dxfData.circles` (`:711`), `dxfData.bounds` (`:497-498`) — the raw `parseDxf` entity structure |
| **3D** | the ordinary three.js `CadViewer` | `selectedDxfMeshData` = `buildDxfPreviewMeshData(dxfData, thicknessMm, bendSettings)` (`CadWorkspace.js:2980-2999`, `dxf/buildPreviewMesh.js:1179`) |

The toggle is `dxfViewMode`, defaulting to `"2d"` (`CadWorkspace.js:1100`), rendered as a ToggleGroup in the view-plane header (`CadRenderPane.js:85-129`, `:426-432`), with the branch at `CadRenderPane.js:516-525` choosing `DxfViewer` whenever `dxfMode && !dxfMeshPreviewReady`.

#### 7.4.1 Decision: 3D-only

Drop the 2D view. Deletion set, exactly:

- **`viewer/src/client/components/DxfViewer.js`** — entire file (752 lines), including `DXF_2D_VIEW_PLANE_ORIENTATION` / `_FACES` / `_MESH` (`:28-39`) and its private `captureScreenshot` (`:575-600`).
- **`CadRenderPane.js`** — the `DxfViewer` import (`:3`), `DxfViewModeControl` (`:85-129`), `dxf3dAvailable` / `activeDxfViewMode` / `dxfMeshPreviewReady` (`:397-399`), `dxfViewPlaneHeader` (`:426-432`) and both `viewPlaneHeader={dxfViewPlaneHeader}` props (`:524`, `:547`), the `dxfMode && !dxfMeshPreviewReady` branch (`:516-525`), and the `dxfMode` arm of `viewportHasRenderableContent` (`:455-459`). `activeMeshData` (`:400`) collapses to `selectedMeshData`; `activeModelKey` (`:408`) to `selectedKey`.
- **`CadWorkspace.js`** — `dxfViewMode` state (`:1100`) and both props (`:8257-8258`). `selectedDxfMeshData` moves into `selectedMeshData` the way G-code already does (`:2029-2035`) — **interim only**, deleted again by phase 3.
- **Tests: none.** Nothing in the repo references `DxfViewer` or `dxf-2d` outside those two files. `parseDxf.test.js` (89 lines) and `dxf/buildPreviewMesh.test.js` (92 lines) test the libraries and are unaffected.

**One behaviour change that must be handled, not inherited.** `dxf3dAvailable = !!selectedDxfMeshData` (`CadRenderPane.js:397`) currently makes a failed mesh build fall back silently to 2D — `CadWorkspace.js:2980-2998` catches the throw into `selectedDxfPreviewError`. With 2D gone there is no fallback: that error must become a **blocking** viewer alert. The plumbing exists — `buildViewerDxfAlert` already receives `selectedDxfPreviewError` (`CadWorkspace.js:3098-3102`); what changes is that `viewportHasRenderableContent` no longer has a `selectedDxfData` arm keeping the alert non-blocking.

3D-only is a **pure client deletion**: no server work, because `buildDxfPreviewMeshData` already produces the mesh in the browser. It can land immediately, ahead of everything else (phase **3a**).

#### 7.4.2 `preview.glb` is now REQUIRED — this reverses the previous recommendation

The previous amendment recommended dropping phase 4. **That was correct only while 2D was the default.**

*Why it was correct before:* `DxfViewer` consumes `parseDxf` output directly, so `parseDxf`, `dxfState` and `loadDxfForEntry` had to remain client-side **no matter what the server baked**. A `preview.glb` would have been a *sixth* path bolted onto five, buying nothing at runtime (parse + extrude are sub-millisecond on the flat patterns in `models/robots/tom/parts/`).

*Why it is wrong now:* under 3D-only the DXF viewport is a `CadViewer` fed a `meshData` — structurally identical to GLB/STL/3MF. `preview.glb` therefore **replaces** the client-side DXF code instead of adding to it:

| Deleted once `preview.glb` exists | Size |
|---|---|
| `packages/cadjs/src/lib/dxf/parseDxf.js` | 526 lines |
| `packages/cadjs/src/lib/dxf/buildPreviewMesh.js` | 1,284 lines |
| `loadRenderDxf` / `peekRenderDxf` (`renderAssetClient.js:545-555`) + `dxfCache` | — |
| `dxfState`/`dxfStatus`/`dxfError`/`dxfLoadStage` (`useCadAssets.js:234-237`), `getCachedDxfState` (`:365`), `loadDxfForEntry`, `cancelDxfLoad` | — |
| the `selectedDxfPreview` / `…Key` / `effectiveDxfThicknessMm` / `normalizedSelectedDxfBendSettings` / `selectedDxfBendLines` memo block (`CadWorkspace.js:2954-3015`) | ~60 lines |

**1,810 LOC of library plus the whole loader-and-memo tier**, and it is the *only* way §2's "collapse to one runtime path" is ever true for DXF. With 2D kept, it never could be.

**The cross-runtime objection survives but shrinks to one call site.** `.dxf.py` freshness and build are Python (`drawing_package_current` at `_internal/drawing_package.py:188`, wired at `dxf_artifact.py:105`), so the Node mesh step runs inside the existing Python lock — which is **exactly** §4.3's architecture (Python parent holds `artifact_build`, Node child produces geometry). It is one additional caller of the same wrapper, not a new mechanism. Two requirements remain real:

1. One run id, one status record, phases spanning both runtimes (`DRAWING_PACKAGE`'s `phases` gains the mesh phases).
2. A Node-side failure marks the whole run `failed`. Never leave a `.dxf` with no `preview.glb` — `_validate_render_package` requires the descriptor *and* every payload it names, so the descriptor stays the last write (§4.4), and `payload_refs` must return both payloads (§4.7).

`bakeHash` for DXF lands in `drawing_package_current` itself (§5.3a) — non-optional now, since a changed `defaultThicknessMm` would otherwise render a stale bake **silently**.

**Imported `.dxf` comes along.** `owns_dxf_entry` widens (§5.5), or an imported `.dxf` has no renderer at all after phase 3.

**Recommendation, unambiguous: phase 4 is required, and it must land before phase 3's DXF deletions.**

#### 7.4.3 Bend and thickness UI

`dxfThicknessMm` / `dxfBendSettings` (`CadWorkspace.js:1098-1099`), the `DxfFileSheet` controls (270 lines), the `FILE_SHEET_SECTION_IDS.DXF` tab (`fileSheetSections.js:4`, `:36`, `:86`) and the per-file `slices.dxf` localStorage (`CadWorkspace.js:3743-3745`) exist solely to drive `buildDxfPreviewMeshData`. Today they steer a view the user is not looking at.

- **After 3a (3D-only, pre-bake):** the controls become *more* useful — they finally drive the visible view. Keep unchanged.
- **After phase 4 (baked):** they die exactly as §2's accepted-loss row states. Deletion set: `DxfFileSheet.js` collapses to status-only, the same shape as the `mesh` kind at `fileSheetSections.js:66-69`; `FILE_SHEET_SECTION_IDS.DXF` and its two switch arms go; `slices.dxf` persistence goes and `fileSessionState.test.js:70-160` is rewritten; `extractOrderedDxfBendLines` / `normalizeDxfBendSettings` / `normalizeDxfBendAngleDeg` / `normalizeDxfBendDirection` / `normalizeDxfPreviewThicknessMm` (`dxf/buildPreviewMesh.js:313-380`) become builder-internal.
- **Per §0.2:** delete the `slices.dxf` reader outright. No migration path for stale localStorage.

---

## 8. Client changes (the deletions)

Once the packages exist:

- `viewer/src/client/components/workbench/hooks/useCadAssets.js` — delete the `dxfState` / `gcodeState` / `implicitState` triplets and their effects. Everything routes through `loadRenderMeshForEntry`.
- `viewer/src/client/components/CadWorkspace.js` — delete `selectedGcodePreview`, `selectedDxfPreview`, `selectedDxfPreviewKey`, `normalizedSelectedDxfBendSettings`, `effectiveDxfThicknessMm` and the `buildDxfPreviewMeshData` / `buildGcodePreviewMeshData` call sites (~200 lines of memo plumbing), plus the interim `isDxfView` arm added by phase 3a.
- **`viewer/src/client/components/ImplicitCadViewer.js` (1140 lines) and its `CadRenderPane.js:4,499` branch are DELETED.** No descriptor field, no developer setting (T4). The reference raymarch render is **not** this component: `implicitjs` exports a complete headless path — `./render`, `./snapshot`, `./graphicsSettings`, `./headlessRenderEntry` (`packages/implicitjs/package.json:14,17,18,26`), driven by `packages/implicitjs/scripts/snapshot.mjs` — which `cad snapshot` already uses and this plan does not touch. §10.3's visual-regression job drives **that**, headlessly; CI has no browser for a React component regardless. The rollback is reverting phase 3.
- **`viewer/src/client/workbench/implicitExport.js` is DELETED**, along with the `/__cad/implicit-export` route (`server.py:163-164`, `:339-346`) and `backend.generate_implicit_export` (`backend.py:524-548`). The viewer's Export action runs the node export CLI server-side under `generator_busy` (§4.7).
- `packages/cadjs/src/lib/fileFormats.js` — **do not repurpose `entrySourceFormat`** (see §9). Add **NEW** `entryRenderAssetFormat(entry, { artifact })`, used only by `loadRenderMeshForEntry` / `meshAssetKeyForEntry`. **Phase 3 removes the `{ artifact }` argument**: it then returns GLB unconditionally for all three kinds, and a missing package surfaces as `needs-build` through the existing artifact state machine (`artifact.py:37-49`), never as a silent in-browser parse. `entryHasGcode` / `entryHasDxf` / `entryHasImplicitCad` stop gating the render path and **survive because they have live non-render callers** (`workbench/CadWorkspaceTopBar.js:107-115`, threaded from `CadWorkspace.js:96-97`, `:1480-1481`, `:8348-8349`); any that do not survive the phase-3 audit are deleted.
- `scanner.py` publishes a `glb` asset for these entries pointing into the package, so `entryMeshAssetUrl` (`packages/cadjs/src/lib/entryAssets.js:78`) resolves with no special-casing. **The asset URL must be derived from the entry path as the scanner walked it (unresolved), while the lock/package path stays realpath-resolved** — those are two different derivations (`scanner.py:68-83`), and conflating them breaks either mutual exclusion or the URL.

**Kept, now as builder inputs:** `parseGcode`, `buildGcodePreviewMeshData`, `parseDxf`, `buildDxfPreviewMeshData`, `meshImplicitCadModel` — unmodified, moved off the client and into the builders.

---

## 9. Phasing

Phases are listed in **execution order**. Numbering is preserved from the previous amendment; phase 3a is new (T3) and phase 4 has moved ahead of phase 3 (T3).

| # | Phase | Scope | Exit criteria |
|---|---|---|---|
| 1 | **0** | Shared JS writer split (`writeGlb` pure / `writeRenderPackage` locked) + `meshToGlb` **deleted** + `meshoptimizer` bundled + `EXT_meshopt_compression` decoder in `glbMeshData.js` **and** `glbMeshWorker.js` + `bakeHash` + per-format `source_digest_field` fail-closed (§5.3b) + `packageSchemaVersion` strictly gated (§5.1) + **legacy byte-digest deleted (§5.6)** + `ArtifactKind.labels` + implicit **export CLI alignment** (§4.7) | Existing implicit export **loads and is ≤ its previous size — no byte-compatibility required**; `export <model> --stl --3mf --glb` produces all three from **one** mesh pass, STL/3MF bytes unchanged, GLB loadable by a stock `GLTFLoader` with **no** meshopt decoder; usage error exits 2; per-flag relative paths resolve beside the model; `skills/implicit-cad/scripts/export.mjs` passes through unchanged; `verify-implicit-cad-exports.mjs` green across all 44 `models/implicits/*`; **meshopt's real ratio measured on the flange and gyroid fixtures and recorded** (phases 1/2 budgets are set from it); STEP/DXF freshness unchanged **except** a digest-less imported descriptor now reports `needs-build`; a pre-semantic descriptor reports stale once and self-corrects; run 2's reporter sees run 1's stage times |
| 2 | **3a** | **DXF 3D-only** (§7.4.1). Pure client deletion; **independent of everything else and may land first** | DXF opens in `CadViewer`; a mesh-build failure raises a **blocking** alert; `DxfViewer.js` deleted; no test changes needed |
| 3 | **1** | `cadgen.toolpath_artifact` + `cadgen/_internal/node_runtime` + G-code Node builder + `toolpath-package` + `owns_entry`/`_artifact_format` extension + `entryRenderAssetFormat` + bounded concurrency + startup Node probe + **`skills/gcode/scripts/gen`, vendored cadgen, and NEW `scripts/bundle/skills/bundle-gcode.sh`** | `circular_flange_plate_sample` renders from GLB; ≤ 14 MiB pre-meshopt / phase-0 target post; ≤ 2×layerCount+1 primitives; layer scrubbing via node visibility; **z-bias ladder visually intact after quantization**; builder runs from a clean `bundle-cad-viewer.sh --check` tree with `node_modules` deleted; `scripts/bundle/bundle.sh --check` clean; concurrent build reports `writing` with a non-null runId and live progress; a second concurrent build observes `run.skipped` — **from the CLI as well as the viewer**; a ≥ 50 MB fixture degrades per the size policy; **Q1's measurement taken (§12)** |
| 4 | **2** | `cadgen.implicit_artifact` + implicit Node builder + `implicit-package` + worker-thread sampling **and** polygonizing + determinate progress + **`skills/implicit-cad/scripts/gen` and vendored cadgen** | All 43 `models/implicits/*` build; **SDF field-agreement test green (GATING — hard precondition on phase 3)**; parallel result identical to single-threaded; resolution-96 packages within the phase-0 budget; measured speedup recorded (do not exit on an estimate); `scripts/bundle/bundle.sh --check` clean |
| 5 | **4** | **DXF `preview.glb` — REQUIRED** (§7.4.2). `dxf_artifact` gains the Node mesh step inside its existing lock; `bakeHash` inside `drawing_package_current`; `payload_refs` returns both payloads; `owns_dxf_entry` widened to imported `.dxf` | A generated `.dxf.py` **and** an imported `.dxf` both render from `preview.glb`; one run id and one record span both runtimes; a Node-side failure marks the run `failed` and leaves no descriptor; a changed `defaultThicknessMm` reports stale |
| 6 | **3** | Client deletions (§8), including the DXF loader/memo tier (**requires phase 4**) and the browser export | Six render paths → one; **`ImplicitCadViewer.js` deleted**; `implicitExport.js` + `/__cad/implicit-export` + `generate_implicit_export` deleted; **`entryRenderAssetFormat` loses its `{ artifact }` argument** and returns GLB unconditionally; DXF/G-code memo plumbing gone; the DXF file-sheet collapses to status-only and `slices.dxf` is deleted outright |

**Additivity, corrected — and time-boxed.** The original claimed phases 1–2 are additive "behind `entrySourceFormat`". They are not: `entrySourceFormat` (`fileFormats.js:59-89`) is a flagless kind→format map with icon/status/reset call sites. Additivity comes instead from **`entryRenderAssetFormat` returning GLB only when a built package exists for that entry** — so built entries take the new path while the old one is **not yet deleted**, per entry, and parity is verifiable side by side. **This is a phasing device with a named executioner, not a fallback** (§0.2): phase 3 removes the `{ artifact }` argument and the old call sites together. It exists so phases 1–2 are shippable before the deletions and so a regression is caught next to its reference. Fold any `entrySourceFormat` change into phase 3 and re-audit its call sites there.

---

## 10. Test plan

### 10.1 The split rule (state this at the top of the test section)

- **Python owns the package as a coordinated artifact:** descriptor kind, payload refs, freshness codes, ownership gates, buildable-code sets, lock/record/progress, scanner asset publication. Always against **hand-written synthetic packages** (the `_write_package` / `_write_generated_package` / `_write_drawing_package` pattern at `viewer/server_py/tests/test_artifact.py:26`, `:257`, `:360`), never by running a builder.
- **JS owns everything downstream of "here is geometry":** parse, mesh, regroup, weld, quantize, GLB bytes, node/primitive structure, budgets, decoder wiring, client resolution.
- Where the two must agree on a computed value, use the repo's existing cross-language pattern: `gen_golden.mjs` → checked-in `golden.json` → Python asserts with `SkipTest` when missing (`viewer/server_py/tests/test_parity.py`).
- **One exception:** exactly one integration test per format that actually spawns the producer, to pin the lock/record contract. It must skip cleanly when `node_modules` is absent. **Because the CLI and the viewer share one producer, this test covers both entrypoints** — add a CLI-level assertion that a second concurrent target observes `run.skipped` and prints the "built by a concurrent run" line.

### 10.2 The boundary pin (replacing the mirror test)

`tests/python/global/test_viewer_cadgen_mirror.py` is **deleted** (`140cb659`). **Do not recreate it** — it hid a real bug by `.resolve()`-ing the viewer's `render_package_dir` before comparing, masking a symlink divergence in lock sentinels. Its *actual* invariant is now pinned by `tests/python/packages/cadgen/test_coordination_is_stdlib_only.py`.

But the boundary is still half-live (§3.2), and it applies to every new kind. Put the pin in **`viewer/server_py/tests/test_artifact.py`** — it already imports both `artifact` and `scanner`, and runs in CI via `scripts/test/test-python.sh:38` with `packages/cadgen/src` on `PYTHONPATH` and `CADGEN_STRICT_LOCKS=1` (`:14`), so it can import `cadgen.catalog` and compare directly. Assert the descriptor name/kind and the derived package dir **without normalizing either side**.

### 10.3 Per phase

**Phase 0**
- NEW `packages/implicitjs/src/lib/glb/writeGlb.test.js` — indexed+welded output; multi-node/multi-primitive with `extras.cadOccurrenceId`; `UNSIGNED_SHORT` index selection and the 65,535 assertion; `KHR_mesh_quantization` round-trip within tolerance; **byte-identical across repeated runs on the same machine**; NaN rejection; **the export preset produces an unquantized, uncompressed GLB**.
- NEW: `writeRenderPackage` with no `runId`, or a stale one, throws from `assertWriteLock`; `writeGlb` alone never touches a lock.
- EXTEND `packages/implicitjs/src/lib/implicitCad/export.test.js` — `meshToFormat` reaches `writeGlb` directly (`meshToGlb` gone); output loadable and ≤ previous size; **`--stl --3mf --glb` in one run meshes once and STL/3MF bytes match the pre-change writer**.
- EXTEND `packages/cadjs/src/lib/render/glbMeshData.test.js` **and** the GLB-worker suite — meshopt decoder registered in **both**; quantized GLB decodes to the same vertex count/bbox.
- EXTEND `viewer/server_py/tests/test_artifact.py` — `bakeHash` mismatched → `stale_*`, absent → stale; **`source_digest_field` missing → `missing_digest`, per format** (the fail-open path at `artifact.py:144` is currently untested: `_write_package` always writes a digest and the only negative case is a wrong one at `:72-74`); **a descriptor whose `packageSchemaVersion` does not match returns `unsupported_*` for every format, and that code is in `BUILDABLE_ARTIFACT_CODES`**; STEP/DXF pass `bakeHash=None` and all existing cases unchanged.
- EXTEND `tests/python/skills/cad/cadgen/test_semantic_closure_hash.py` — the legacy-byte-digest case at `:66` **inverts to `assertFalse`**; `:74`, `:79`, `:108` stand.
- EXTEND `tests/python/packages/cadgen/test_coordination.py` — iterate every `ArtifactKind` exported from `kinds.py`, assert every phase has a `PHASE_LABELS` (or kind-`labels`) entry and that `_even_weights` over that set sums to 1.0. Plus the `stageMs` learning regression (§4.6).

**Phase 3a**
- No new tests. Assert only that `DxfViewer` and `dxf-2d` have zero remaining references (an `importPolicy.test.mjs`-style grep assertion), and that a DXF whose mesh build throws produces a blocking alert.

**Phase 1**
- NEW `packages/cadjs/src/lib/gcode/buildPreviewMesh.test.js` — **must land first.** The 505-line mesher is currently untested; pin segment→quad counts, layer assignment, travel toggling, and `detailMode: "full"` == no decimation *before* its output becomes a frozen artifact.
- NEW `packages/cadjs/bin/gcodeArtifact.test.mjs` — regroup by `(layerIndex, colorKey)`: interleaved travel across 3 layers, plus a support-bearing case, → correct primitive count, layer membership preserved, `layer:<i>` node names, stable `cadOccurrenceId`. **Rate-based budgets on a synthetic `.gcode` generated in the test** (bytes/segment, attribute set — no `COLOR_0`, primitive count) — `.gcode` is LFS (`.gitattributes:11`) and CI's checkout has no `lfs:` input, so **no test may hard-require an LFS-backed fixture**.
- EXTEND `viewer/server_py/tests/test_artifact.py` — `_write_toolpath_package` helper; ready / missing payload / wrong `kind` / mutated `sourceDigest` / mutated `bakeHash`; `owns_entry` for imported `.gcode`; codes in `BUILDABLE_ARTIFACT_CODES`; the §10.2 boundary pin; **the one integration test** (spawn the producer on a tiny synthetic input under `CADGEN_STRICT_LOCKS=1`, assert `snapshot()` reports `writing` with a non-null runId and non-None progress during the run, and that two concurrent builds serialize with the second observing `run.skipped`).
- NEW CLI test: `python scripts/gen <a.gcode> <b.gcode>` takes two sequential locks, prints the "is current; skipped recompose" line on a second run, and exits 0.
- EXTEND `viewer/src/client/workbench/stepArtifactStatus.test.js` — a stale toolpath entry offers Generate (the `sourceFormat === STEP` gate).
- The 6 MB whole-file number for `circular_flange_plate_sample` goes in an **opt-in** job doing a targeted `git lfs pull --include=...` behind the same `git lfs version` guard `scripts/test/test-docs.sh` uses, skipping when the pointer is unhydrated.

**Phase 2 — the gating test**
CI has no browser (nothing runs `playwright install`), so a perceptual diff cannot gate. Split it:

- **GATING, browser-free:** NEW `packages/implicitjs/src/lib/implicitCad/sdfField.test.js`. Walk all **43** `models/implicits/*.implicit.js` — **not LFS** (verified: `git check-attr filter` → `unspecified`), 216 KB of plain JS, available in an unhydrated worktree. For each: transpile via `sdfEvaluator`, assert no unresolved tokens, `sdf()` finite and non-NaN over a fixed coarse point set, the field changes sign, and a committed per-model field digest still matches. **This catches the `1.0e-6` / `i == 0` normalizer-mangling class** at millisecond cost, and re-blessing a digest is a deliberate reviewable diff. Better where feasible: evaluate the GLSL on the GPU over a fixed point set and assert agreement in absolute distance at a float32-scaled tolerance; for hash/noise models either add `Math.fround` emulation or keep an explicit allowlist **recorded in the descriptor**, not buried in a test file.
- **NON-GATING:** NEW `.github/workflows/visual-regression.yml` on `workflow_dispatch` + nightly, explicitly running `npx playwright install --with-deps chromium`, driving **`implicitjs/snapshot` headlessly** (not a React component), rendering 5–8 representative models with **identical flat unlit shading, AO/shadows/rim off, `resolutionScale: 1` on both sides**, uploading a contact sheet.
- NEW `packages/cadjs/bin/implicitArtifact.test.mjs` — weld correctness at resolution 12–16 (vertex ≈ tri/2.015, no duplicate positions within ε, unit normals); per-vertex colour bake; **worker_threads slicing produces the same mesh as single-threaded**.
- EXTEND `viewer/server_py/tests/test_artifact.py` — implicit-package freshness, same five cases, plus a `GeneratedPackageParity`-style case (`test_artifact.py:467`) so all four formats answer identically-shaped questions identically.
- EXTEND `packages/implicitjs/src/lib/implicitCad/mesh.test.js` — pin `DEFAULT_RESOLUTION` and the clamp, so a bake-setting change is visible.

**Phase 4**
- EXTEND `viewer/server_py/tests/test_artifact.py` — `_write_drawing_package` gains `preview.glb`; a package missing it is stale; a mutated `bakeHash` is stale; `owns_dxf_entry` now true for an imported `.dxf`.
- NEW integration test: a Node-side failure inside `dxf_artifact` marks the run `failed` and leaves the previous descriptor intact.

**Phase 3**
- EXTEND `packages/cadjs/src/lib/fileFormats.test.js` and `entryAssets.test.js` — `entryRenderAssetFormat` takes **one** argument and returns GLB for all three kinds; `entryMeshAssetUrl` resolves into the package.
- EXTEND `viewer/src/client/workbench/fileSheetSections.test.js` — the surviving tabs still render (the id must stay in `renderedFileSheetSectionIds`); rewrite `fileSessionState.test.js:70-160` for the deleted `slices.dxf`.
- NEW assertions in the style of `viewer/src/importPolicy.test.mjs` — `useCadAssets.js` no longer references `dxfState`/`gcodeState`/`implicitState`; `ImplicitCadViewer` and `implicitExport` have zero references; `/__cad/implicit-export` is gone from the route table.
- NEW in `viewer/server_py/tests/test_artifact.py` — **buildable-code parity**: parse the exported array out of `viewer/src/client/workbench/stepArtifactStatus.js:6-16` and assert set equality with `artifact.BUILDABLE_ARTIFACT_CODES`. It needs no Node, **it fails today** (the JS list is missing the three DXF codes), and it is the one pin genuinely worth inheriting from the mirror test's job.

### 10.4 Determinism — narrowed
"Byte-identical GLB" is achievable and cheap at the **writer** layer (fixed in-memory mesh, repeated N times) and at the **stability** layer (same fixture built twice on the same machine — which is what catches `Math.random` and Map/Set iteration-order leaks). Across machines, assert **content equivalence** instead: a canonical hash over sorted positions/indices/normals within a stated tolerance, plus identical vertex/index/primitive counts and bbox. If content-addressed caching genuinely needs bytes, say which layer supplies the cid — as the STEP path does (geometry hash, not bytes).

### 10.5 Housekeeping
Fix the dangling docstring at `viewer/server_py/tests/test_artifact.py:228-235` (it references the deleted `server_py.source_hash` and the deleted mirror test) and promote `_reference_closure_hash` (`:228`) as the surviving independent digest check. Fix `viewer/src/client/workbench/artifactProgress.js:1-3`, which still credits `cadgen/_internal/progress.py` (now `coordination/phases.py`) and `read_generation_progress` (now `generation_snapshot`). Fix the four stale `python scripts/step …` strings in `skills/gcode` (§4.7).

---

## 11. Risks

| Risk | Mitigation |
|---|---|
| Implicit CPU evaluator diverges from the GLSL users saw | Gating **field-agreement** test over all 43 models (§10.3), not an image diff; phases 2 and 3 ship separately, so the rollback is reverting phase 3. **The raymarch runtime survives in `implicitjs` regardless** — `cad snapshot` uses it — so deleting the viewer component costs no reference render |
| 71 s implicit builds feel broken | The Python parent holds the write lock for the Node child's whole lifetime, so a peer POST reports `generating` and the client attaches to the live bar rather than starting a duplicate. Remaining work: emit slice-level `advance()` often enough that the bar moves during `sample`, and the §4.6 `stageMs` fix (already landed) weights it by the previous build |
| A Node-written package races a CLI build | Never happens by construction: Node is a child of the lock holder, and **the CLI and the viewer share one producer** (§4.7). Enforced by `assertWriteLock(packageDir, runId)` in `writeRenderPackage` (§4.4, §6), unforgeable outside a held lock, plus `require_write_lock` on the Python side |
| Server restart orphans a Node build | The producer is a separate process, so lock and writer die together; its `finally` kills the child before releasing (§4.4) |
| Node builds bypass the warm worker's serialization | Bounded semaphore + per-build `--threads` budget in phase 1 (§4.4) — the *only* concurrency bound once the worker is out of the path |
| Node dependency graph unavailable in the packaged runtime | Builders take no external deps (verified: parser/meshers have none); anything that does (`meshoptimizer`) is esbuild-bundled per `bundle-cad.sh:164-187`. Phase-1 exit criterion runs the builder from a clean `--check` tree with `node_modules` deleted. Node the binary is probed at **startup** (`cadgen_bridge.py:70-118`) |
| `bake` drift silently invalidates nothing | `bakeHash` is phase 0 **on whichever freshness authority owns each format** (§5.3). For toolpath/implicit the two authorities are the same function object; for DXF, `drawing_package_current` itself must change — now non-optional, since phase 4 is required. A one-sided landing renders stale **silently**, not as a visible loop |
| Quantization flattens the G-code z-bias ladder | Scaled ladder recorded in `bake`; visual check in phase-1 exit criteria (§7.1) |
| G-code group explosion ships as 5,429 draw calls | Explicit `≤ 2×layerCount + 1` budget in phase-1 exit criteria |
| **T4's byte-digest deletion forces rebuilds users did not ask for** | Lazy (per reopened entry), on a gitignored cache, and **stated in the PR body** (§0, §5.6) rather than discovered |
| **New skill vendoring (cadgen into `skills/{gcode,implicit-cad}`, first `bundle-gcode.sh`) drifts from source** | `scripts/bundle/bundle.sh --check` is an exit criterion on phases 1 and 2; `check-builds.sh`'s no-symlink assert is not relaxed |
| Artifacts inflate the disk | `__cadgen__/` is gitignored (`.gitignore:11`), so this is disk hygiene, not repo hygiene. See §12 Q2 |

---

## 12. Open questions

**Answered — implement as stated unless the user objects.**

**Q1 — Imported `.gcode` first-build UX.** Do **not** pre-build on scan; that builds every file in a directory the user merely browsed. Build on first open. Measure the true end-to-end cost including Node startup in phase 1 — but **the outcome is binary, not a third path.** Either G-code goes through the artifact pipeline **and** `parseGcode` / `buildGcodePreviewMesh` leave the client render path, or the **G-code phase is dropped from this plan entirely** and the format is left untouched until someone addresses it (untouched is not a shim; a permanent dual path is). If it is the second, the unification argument reduces to implicit — and to DXF under T3. **That changes the value calculation for the whole plan, so measure before deleting anything.**

**Q2 — Package eviction.** No LRU. It needs access tracking, global size accounting, and an eviction policy that can race a live build. Instead: one entry-keyed sweep applied to every kind — on catalog scan, delete `__cadgen__/models/<name>/` when `<name>` no longer resolves to a file in that folder. If any sweep is ever added, it must acquire each candidate's write lock via `artifact_build`/`exclusive` before deleting, must delete only the package directory, and must leave the two sentinels and the status record in place (`lock.py:20-22`: sentinels are never unlinked).

**Q3 — Resolution 128 opt-in.** Per-model descriptor field, not a global setting. `bakeHash` must invalidate on it, and a global would invalidate every package at once; a global is also user state, reintroducing exactly the live-UI-state-in-the-render-path coupling this plan deletes; and the cost is wildly uneven per model (4.4 s vs 71 s). Document the 128 ceiling from `mesh.js:5`.

**Q4 — `.gcode.py` generators.** Imported-only. Zero `.gcode.py` files exist and no skill produces one (`skills/gcode` slices from mesh input). A generated path adds a second provenance branch with no consumer to exercise it, which is how the untested edge cases at `artifact.py:131-133` accumulate. `.dxf.py` earns its generated path because generators actually exist. Corollary phase-0 check: `cad gen` / `cad inspect` over a directory containing `.gcode` / `.implicit.js` entries must ignore them rather than report them as unbuildable.

**Genuinely needs the user's decision — do not proceed without it.**

1. **Implicit becomes a static gallery.** 43/43 shipped models lose live parameter sliders and animation, plus the whole graphics panel (§2). Accept, or keep the raymarch as the implicit default and use the baked GLB only for the unified asset/selection path?
2. **Implicit export params.** **Recommended answer (§4.7): export stays live-valued** — `--params` / `--animation` / `--resolution` / `--max-cells` are kept on the node export CLI, run under `generator_busy`, while the *render* bakes at `params.*.default` under `artifact_build`. The browser-side export is deleted and the viewer's Export action runs the same CLI server-side. Confirm.
3. ~~**Phase 4 (DXF `preview.glb`).** Recommend dropping it.~~ **Withdrawn — settled by T3.** 3D-only makes phase 4 **required** and moves it ahead of phase 3's DXF deletions (§7.4.2, §9).

---

## 13. META-GOAL — converge the three surviving render paths

> **Not a phase. Not scoped now. Not designed here.** This section states a direction that every phase of this plan should be judged against, and records the inventory that a future effort would start from. It deliberately proposes no API.

Once DXF, G-code and implicit become build-time producers, the viewer renders exactly **three** file formats: **GLB, 3MF, STL** — the same three `IMPLICIT_CAD_EXPORT_FORMATS` already lists (`packages/implicitjs/src/lib/implicitCad/exportModel.js:7`), so the renderable set and the implicit export set coincide. All three already produce one `meshData` record consumed by one `CadViewer`. **The renderer is already converged; the loader tier below it is not.** The standing goal is that the loader tier become one implementation with three thin front ends.

### 13.1 Starting inventory — concrete duplication found while writing this plan

| # | Duplication | Evidence |
|---|---|---|
| 1 | **The workers are copy-paste.** `stlMeshWorker.js` and `glbMeshWorker.js` are 61-line files differing in **exactly three lines** (import, message-type string, builder call). `stlMeshWorkerClient.js` and `glbMeshWorkerClient.js` are 94-line files differing only in identifier names and two message strings. **3MF has no worker at all**, despite being the most expensive parse | `diff packages/cadjs/src/lib/render/{stl,glb}MeshWorker.js`; `diff …/{stl,glb}MeshWorkerClient.js`; `threeMfMeshData.js` (597 lines, no worker file) |
| 2 | **Worker policy is three different policies.** GLB uses a worker only when the caller passes `preferWorker`, gated on a ≥32 MB heuristic; STL *always* attempts one, no size gate; 3MF never | `renderAssetClient.js:257` vs `:283` vs `:305-313`; `meshCost.js:10`, `:37`; `useCadAssets.js:207` |
| 3 | **`boundsFromVertices` exists six times.** Three shared copies plus one per loader — and `renderMeshScene.js` imports the shared one aliased at `:49` then **shadows it with a local redefinition at `:131`** | `common/renderOptions.js:148`, `common/cadScene.js:118`, `common/renderMeshScene.js:49,131`, `threeMfMeshData.js:8`, `stlMeshData.js:1-15`, `glbMeshData.js:13-44` |
| 4 | **The `meshData` record is an undeclared contract the loaders already violate.** Only STL sets `sourceFormat` — and `renderMeshScene.js:678` *reads* it to decide whether STEP display settings apply, so GLB and 3MF silently take the fallback branch. GLB emits `surfaceEdgeBarycentric`/`surfaceEdgeClass` as empty typed arrays; STL and 3MF omit the keys | `stlMeshData.js:66`; `glbMeshData.js:462-475`; `threeMfMeshData.js:368-378`; `renderMeshScene.js:678` |
| 5 | **Part/occurrence identity is three conventions.** GLB walks ancestors for `extras.cadOccurrenceId`, falling back to `glb:<n>`; 3MF synthesizes `3mf:<n>` with `occurrenceId === id`; STL returns `parts: []` — an STL model has no selectable parts at all | `glbMeshData.js:149-168`, `:264-266`, `:403`; `threeMfMeshData.js:321-337`; `stlMeshData.js:63` |
| 6 | **Unit handling is per-loader, and it is a correctness gap.** GLB multiplies every position by `GLB_CAD_UNIT_SCALE = 1000`; STL and 3MF apply nothing, and `threeMfMeshData.js` never reads the 3MF `unit` attribute at all | `glbMeshData.js:1`, `:174-176`; no `unit`/`scale` match anywhere in `threeMfMeshData.js` |
| 7 | **Color and normal handling are three implementations.** GLB reads `material.extras.cadSourceColor` against a generated-STEP default sentinel; 3MF resolves its own material/colorgroup chain to per-vertex colors; STL emits none and instead hardcodes a `Math.PI/4` crease-angle normal regeneration neither other loader does | `glbMeshData.js:10`, `:60`; `threeMfMeshData.js:311`, `:364-372`; `stlMeshData.js:17-31`, `:63` |

**Already converged — the model to copy, not work to do:** fetch-and-cache. All three loaders wrap identical `loadCached` / `peekCached` / `finalizeCached` helpers over per-format Maps (`renderAssetClient.js:71-111`, used at `:258`, `:283`, `:306`). That is the existing proof the rest is tractable.

**Explicitly out of scope for this goal: the writers.** Two writers per format exist by necessity — JS (`exporters.js:169`, `:508`) for implicit, Python/OCP (`cadgen/_internal/stl.py:21-25`, `threemf.py:88`) for STEP, and the Python 3MF carries a material registry and assembly-component emission (`threemf.py:36`, `:305`) an implicit single-solid mesh has no use for. **"Reuse render code" means the viewer's loaders, not a mandate to unify an OCP tessellator with a marching-tetrahedra exporter.**

### 13.2 A stated lean on 3MF/STL packages (a lean, not a decision)

3MF and STL are **imported** formats with no generator and no server-side package: `artifact.owns_entry` (`artifact.py:65-66`) covers STEP entries and generated `.dxf.py` drawings only (widened to imported `.dxf` by §5.5). GLB is the built artifact.

**Lean: keep 3MF and STL direct-load.** Three grounds, all already argued elsewhere in this plan: there is no producer and no provenance beyond the file's own bytes, so a package buys a cache and nothing else (§12 Q4's reasoning); extending `owns_entry` to imported mesh formats makes every browsed `.stl` a build candidate (§12 Q1's reasoning); and the win is a parse (§7.4's original reasoning). **The one case that could flip it:** 3MF's 597-line main-thread zip+XML parse is the worst of the three and has no worker — but the cheaper fix (inventory item 1) is available first and should be tried first.

### 13.3 Open sub-questions — deliberately not answered

1. Does `meshData` get a declared schema, a version field, and one `normalizeMeshData()` at the loader boundary? Under §0.2 the record may change shape outright — no optional-field shims for old producers.
2. Does STL gain parts, or does the record formally sanction part-less meshes?
3. Does GLB's `extras.cadOccurrenceId` convention become the record's only identity scheme? (This plan's new toolpath/implicit builders already emit it — §5.1, §7.1 — so it is the de-facto winner.)
4. Does unit normalization move out of the loaders into one place, and does 3MF start honouring its `unit` attribute? Related: the mm/model-space vs Y-up/meter-scale divergence between the implicit GLB export and cad's native GLB export (§6).
5. One worker for all three, with one size policy — or worker-always? Note the current heuristic is *entry*-shaped (`shouldUseGlbMeshWorkerForEntry`) while the loaders are *URL*-shaped, which is why the policy leaked into three places.
6. Does `entryRenderAssetFormat` (§8) also select the loader, replacing `resolveMeshFormatFromUrl`'s URL sniffing (`meshLoaders.js:44-57`)?

### 13.4 How to use this goal now

Every phase of this plan touches the GLB loader. When it does, **prefer the shared shape over the format-specific one** — the new toolpath/implicit/drawing packages should consume the *converged* loader path they help justify, not add a fourth variant. Items 3 (one `boundsFromVertices`) and 1 (one worker) are zero-risk, independent of the rest of this plan, and may be done at any time. Everything else waits until the renderable set is actually three.