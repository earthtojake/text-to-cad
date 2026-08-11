# Design: Unified Render-Artifact Pipeline

Status: historical (written against the retired Node viewer server) · Supersedes the
STEP-specific generation + "cache-state issues" machinery

> **Note:** this proposal predates the Python viewer server. The `viewer/src/server/*.mjs`
> files it links no longer exist; their behavior now lives in `viewer/server_py/`
> (`scanner.py`, `artifact.py`, `backend.py`). The resolve/freshness/build model described
> here shipped in that port; the doc is kept for design rationale.

## 1. Why

Today the viewer regenerates a STEP model's `__cadgen__` package through a STEP-named,
STEP-coupled path, and models the *cache states* (missing / stale / metadata-incomplete) as
user-facing **Issues**. That framing is wrong and the implementation has accreted hacks:

- Three parallel generation/status surfaces: `POST /__cad/step-artifact`,
  `GET /__cad/step-source-status`, and `POST /__cad/implicit-export`, each with its own backend
  method (`generateStepArtifact`, `readStepSourceStatusForFile`, `generateImplicitExport`).
- A client "issues" taxonomy ([`fileStatusItems.js`](../viewer/src/client/workbench/fileStatusItems.js)
  Track A/B/C, [`stepArtifactStatus.js`](../viewer/src/client/workbench/stepArtifactStatus.js)
  `BUILDABLE_STEP_ARTIFACT_ERROR_CODES` / `stepArtifactIssueShouldSuppress`) whose only purpose for
  cache states is to decide "should we regenerate" — i.e. it is a trigger dressed up as a warning.
- A coercion hack ([`CadWorkspace.js`](../viewer/src/client/components/CadWorkspace.js)
  `mergeStepSourceStatusIntoEntry`) that **strips an entry's mesh assets** when a buildable artifact
  error is present, purely so the unrelated `!entryHasMesh` gate fires the build effect.

**Key insight (the redesign's north star):** with a generation pipeline, *missing* and *stale* are
not problems to report — they are simply **triggers to (re)generate and show a loading state**. The
only thing the user ever needs to see is `ready` (render it), `generating` (loading), or `error` (a
real, fatal failure). Cache-state Issues should not exist.

### What actually needs a render artifact (grounded survey)

A 4-way code survey of every viewer file type found that **STEP is the only type that needs a
generated artifact to render**:

| Type | Renders from | Needs generated artifact? |
|---|---|---|
| **STEP generator** (`.step.py` / same-stem `gen_step` `.py`) | component-GLB package | **yes** — `__cadgen__/models/<name>.step/` |
| **STEP imported** (committed `.step`/`.stp`) | component-GLB package | **yes** — same package |
| implicit CAD (`.implicit.mjs`) | GPU raymarch **shader**, client-side | no (export is download-only) |
| urdf / srdf / sdf | committed file + referenced meshes (parsed in browser) | no |
| dxf / stl / 3mf / glb | committed file (parsed in browser) | no |

So a "render artifact" API has exactly **one producer to wrap today** (the STEP component-GLB
package). The value is therefore *not* a big plugin framework — it is (a) a clean, type-parametrized
seam so future producers (a baked implicit mesh, a decimated-mesh cache, a new format) drop in, and
(b) deleting the STEP-coupling + the entire cache-state Issues apparatus behind one small interface.

## 2. Goals / non-goals

**Goals**
- One shareable, server-side interface — `RenderArtifactProvider` — to check freshness and
  (re)build the render artifact for a source, reusing the existing `__cadgen__` package pipeline unchanged.
- A single client state machine `ready | generating | error` per entry. **No cache-state Issues.**
- Delete the mesh-stripping hack, the buildable-code suppression logic, and the duplicate endpoints.
- Optimize for simplicity: minimal interface, one concrete provider, trivial default for direct types.

**Non-goals**
- The Python build is **not** rewritten — `cadgen.step_artifact` / `component_package` /
  `generation.py` stay exactly as they are; the provider wraps them.
- Direct-render types are not touched (they have no artifact; they are always `ready`).
- Implicit *export/download* stays a separate concern (it is not a render artifact). The interface is
  shaped so it *could* adopt the same provider later, but we don't force it.
- Genuine, non-cache issues stay (a fatal build error; a truly-missing imported file; urdf
  parse warnings; the read-only urdf/dxf generator-provenance check). They are orthogonal and small.

## 3. The model

Every entry resolves to a **render source**, which is one of:

- **Direct** — the committed file *is* the render input (mesh / dxf / urdf / implicit shader).
  No artifact, no freshness; always `ready`.
- **Derived** — the render input is a generated artifact under `__cadgen__/` derived from a source
  (today: STEP → component-GLB package). Has a freshness check and a build.

```
resolveArtifact(entry):
  provider = providerFor(entry)            // null for direct types
  if !provider:            return { status: "ready",      ref: entryFileUrl(entry) }
  switch provider.freshness(entry).state:
    "fresh":               return { status: "ready",      ref: provider.artifactRef(entry) }
    "missing" | "stale":   build → { status: "generating" } … then "ready" | "error"
    "broken":              return { status: "error",      error }   // fatal, NOT a build trigger
```

The classifier "*is this state a build trigger or a fatal error?*" already exists as
[`canBuildStepArtifact`](../viewer/src/server/step/stepArtifactCompiler.mjs) (a fixed set of codes =
"regenerate", everything else = "hard failure"). We keep it; the code-set becomes per-provider.

## 4. The interface — `RenderArtifactProvider`

Server-side, one per derived-artifact `kind`. Generic shell around type-specific guts:

```ts
interface RenderArtifactProvider {
  kind: string;                                  // "step"
  owns(entry): boolean;                          // .step/.stp + same-stem gen_step .py
  artifactRef(source): string;                   // __cadgen__/<kind>/<basename>/  (artifact dir/url)
  freshness(source): Freshness;                  // present + up-to-date?  (no build)
  build(source, { force, signal }): BuildResult; // idempotent (re)build; settles freshness after
}

type Freshness  = { state: "fresh" | "stale" | "missing" | "broken"; reason?: string };
type BuildResult = { ok: boolean; ref?: string; error?: { message: string } };
```

The shell (the resolver) owns everything type-agnostic: dispatch by `kind`, the
validate→short-circuit-if-fresh→build→re-validate control flow (which is *already* generic in
`ensureStepTopologyArtifact`), the `generating` state, and `stale|missing → build` vs `broken → error`
mapping. The provider owns only the type-specific guts.

### The one concrete provider today: `StepArtifactProvider`

A thin wrapper — **no new build logic**:

| Member | Wraps (reused as-is) |
|---|---|
| `owns` | `sameStemPythonGeneratorPath` sniff + `.step/.stp` ([`stepArtifactCompiler.mjs:41`](../viewer/src/server/step/stepArtifactCompiler.mjs), [`localAssetBackend.mjs:124`](../viewer/src/server/localAssetBackend.mjs)) |
| `artifactRef` | `render_package_dir` ([`scanner.py`](../viewer/server_py/scanner.py)) |
| `freshness` | `validateStepTopologyArtifact` / `validateAssemblyPackageArtifact` ([`cadDirectoryScanner.mjs:636,780`](../viewer/src/server/catalog/cadDirectoryScanner.mjs)) → map its error codes to `fresh/stale/missing/broken` via `canBuildStepArtifact` |
| `build` | `ensureStepTopologyArtifact` → `compileStepTopologyArtifact` → `cadgen.step_artifact` CLI, + the descriptor-mtime bump that settles the mtime trigger ([`localAssetBackend.mjs:854-867`](../viewer/src/server/localAssetBackend.mjs)) |

Direct types need **no provider**: `providerFor` returns null → `resolveArtifact` returns `ready`
with the file URL immediately.

## 5. Server API (collapse 3 surfaces → 1)

One backend method + one route family replace `generateStepArtifact` + `readStepSourceStatusForFile`
(+ optionally `generateImplicitExport`):

```
backend.resolveArtifact({ fileRef, force, signal })
  → { status: "ready" | "generating" | "error", ref?, error? }     // builds if needed
backend.artifactStatus({ fileRef })
  → { status: "ready" | "stale" | "missing" | "error", ref? }      // freshness only, no build
```

HTTP:

- `POST /__cad/artifact?file=&force=` → `resolveArtifact` (build). Replaces `/__cad/step-artifact`.
- `GET  /__cad/artifact?file=`        → `artifactStatus` (freshness). Replaces `/__cad/step-source-status`.
- `/__cad/implicit-export` stays for now (download, not render) — or folds in later as a `kind`.

The catalog scanner keeps producing cheap per-entry freshness on open (it already does — the
component-presence + closure-mtime checks); the resolver consumes that and only escalates to a real
`build` on `stale|missing`. The request plumbing in the existing `/__cad/step-artifact` handler
(catalog read, `resolveRequestRoot`, `refreshCatalog`, `onCatalogChanged`) is already type-agnostic
and becomes the unified handler verbatim.

## 6. Client — `useArtifact(entry)` (delete the Issues machinery)

```
useArtifact(entry) → { status: "ready" | "generating" | "error", ref, error }
```

- On select: direct type → `ready` immediately. Derived type → `GET /__cad/artifact` (status); on
  `stale|missing` → `POST /__cad/artifact` (build) → `generating`; on completion → `ready` | `error`.
- The render layer switches on `status`: `ready` → render `ref`; `generating` → the existing loading
  UI; `error` → a single error message.

**Removed** (cache-state apparatus, all of it):
- `mergeStepSourceStatusIntoEntry` mesh-stripping ([`CadWorkspace.js:1081`](../viewer/src/client/components/CadWorkspace.js)).
- `selectedStepArtifactBuildFile`/`Key`, the `!entryHasMesh && stepArtifactCanGenerate` build effect.
- `stepArtifactIssueShouldSuppress`, `BUILDABLE_STEP_ARTIFACT_ERROR_CODES`, the failure-threshold-then-show logic.
- Track A "step-artifact" cache-state Issues items + Track B "STEP file missing" for generated models.

**Kept** (real problems, orthogonal — small surfaces, not a taxonomy):
- A fatal `error` from `build` (generator threw, OCP failure) — shown as the artifact's error state.
- A genuinely-missing **imported** `.step` (an imported model whose own source file is gone).
- urdf parse warnings; the read-only urdf/srdf/sdf/dxf generator-provenance check (Track C,
  rescoped to non-STEP text formats per the separate Issues-track audit).

This also fixes the current **stale-flash** (render stale → async status → strip → loading): because
render now gates on `useArtifact` status from the first frame, a stale model goes straight to
`generating` with no stale flash.

## 7. What gets reused (the simplicity payoff)

Nothing in the Python build changes. The redesign is mostly *deletion + rewiring* around stable cores:

- `cadgen.step_artifact` / `component_package.build_package_from_compound` / `generation.py` — unchanged.
- `ensureStepTopologyArtifact` control flow → the generic resolver shell.
- `validateStepTopologyArtifact` + `canBuildStepArtifact` → `freshness()` + the trigger classifier.
- `inlineStepGlbArtifactPathForSource` + the `__cadgen__/<kind>/<basename>/` convention → `artifactRef()`.
- `run_script_generator` (already dispatches `gen_step` **and** `gen_dxf`) + `source_hash.py` closure
  primitives → the shared Python-generator harness, ready if a future type generates via `.py`.

Type-specific bits stay behind `StepArtifactProvider`: the STEP CLI (scene loader, `_infer_entry_kind`,
topology embedding), the component-GLB layout, the imported-`stepHash` gate.

## 8. Freshness models (kept, owned by the provider)

The provider's `freshness()` consolidates today's distinct STEP models (no change in behavior):
generated source-closure hash + cheap descriptor-mtime trigger; imported on-disk `stepHash`; package
presence/completeness; embedded `STEP_TOPOLOGY` schema version; mesh-option/tolerance match. An
external generator-run lock (`.generation.lock`, an `fcntl.flock` sentinel surfaced via
`/__cad/generation-status`) maps directly to `status: "generating"`.

## 8a. Build progress (decoration on `generating`)

`generating` on its own says a build is running, not how far along it is — and a component-GLB build
of a large assembly runs for minutes. So the build writes its position to a sidecar beside the lock
(`.<entry>.generation.progress.json`, cadgen's `_internal/progress.py`), `GET /__cad/artifact`
attaches it as `progress` when the lock is held, and `useArtifact` polls that route while its build
POST is in flight (the POST is one long request and cannot report on itself).

Three properties are load-bearing:

- **The lock still decides the state; progress only decorates it.** A progress file is written data
  with no liveness guarantee. Inferring "a build is running" from one would reintroduce exactly the
  stale-heartbeat failure the `flock` replaced. A finished run's sidecar reads as *no* progress.
- **Only the component-mesh stage is measured.** Its work list (the components missing from the
  package's content-addressed cache) is resolved in full before the first mesh runs, so `done/total`
  there is a real count. `gen_step` running and a STEP parsing have no unit of work; they report a
  phase, and the reader interpolates them against the duration the model's *previous* build recorded
  in that same sidecar. Nothing invents a denominator the build does not have.
- **The build emits at work boundaries, never on a timer.** OCP meshing holds the GIL inside C for
  long stretches, so a heartbeat thread starves during exactly the work it would be reporting.
  Interpolation is the reader's job, which is why the payload carries `ratioFloor`/`ratioCeiling`/
  `phaseStartedAt`/`phaseExpectedMs` and not just a number.

Because the sidecar is keyed by package dir like the lock, any producer reports into any reader: a
`cad gen` in a terminal drives the progress bar in an already-open CAD Viewer.

## 9. Migration (incremental, each phase shippable)

1. **Introduce the seam, no behavior change.** Add `RenderArtifactProvider` + `StepArtifactProvider`
   wrapping the existing functions. Add `resolveArtifact`/`artifactStatus` backend methods that
   dispatch to providers. Keep the old routes/methods as thin shims.
2. **Unified route.** Add `POST/GET /__cad/artifact`; point a new `useArtifact` hook at it; keep
   `/__cad/step-source-status` + `/__cad/step-artifact` as shims that call through.
3. **Client cutover.** Replace the build effect + `mergeStepSourceStatusIntoEntry` + the Track-A/B
   cache Issues with `useArtifact`. Render gates on status (kills the stale-flash).
4. **Delete.** Remove the STEP-named routes/methods, the buildable-code suppression machinery, and the
   cache-state Issue items. Rescope Track B/C per the Issues-track audit.

## 10. Open questions

- **Is one provider worth an interface?** Yes — the payoff is the *deletion* (3 endpoints + the Issues
  apparatus + the mesh-strip hack → one state machine), not extensibility. Keep the interface minimal;
  do **not** build a registry framework for a single handler.
- **Implicit export.** Leave as a separate download concern initially; revisit folding it in as a
  `kind` whose `build` = export, if a "baked implicit mesh for render" need ever appears.
- **Freshness placement.** Keep both: the scanner's cheap eager check (catalog open) as the trigger,
  and `provider.freshness()` as the authoritative check on resolve. (Matches today.)
