# Implicit CAD: SDF evaluation performance and per-vertex colour

Execution plan. Branch from the current work on
`claude/step-generation-status-tracking-1b7ff6` (based on `release/0.4.0`).

## 0. The governing constraint

**Preserve the full underlying functionality of the SDFs.** Every model in
`models/implicits/` must keep evaluating to exactly the values it does today, across every
GLSL construct the transpiler supports. This plan contains no approximation, no sampling
heuristic, and no reduction of what the SDF language can express. Steps 1 and 2 are
*mechanical* changes that must produce **bit-identical** output; Step 4 changes mesh
normals and is gated separately and explicitly.

This is not an aspiration — it is enforced by a harness built in Step 0, and **every
later step is blocked on that harness passing**. If a step cannot pass its equality gate,
stop and report rather than loosening the gate.

### 0.1 Execution status

Update this table as you go. It is the handoff record.

| Step | Title | Status | Notes |
|---|---|---|---|
| 0 | Equality harness | **DONE** `a7284ede` | 43 models, 2129 pts; falsified with an EPSILON perturbation |
| 1 | Transpiler control flow | **DONE** `08dfbee9` | bit-identical; median ~2.6x, up to 8.23x |
| 2 | sRGB linearization | **DONE** `263b08cd` | round-trip now exact; packages need rebuilding |
| 3 | Per-vertex `COLOR_0` | not started | writer + reader; see §6.3 for verified specifics |
| 4 | Post-sampling `sdf()` reduction | **superseded** | `design/implicit-glsl-compiler.md` makes per-call cost ~free, so these 5 calls/triangle stop mattering; revisit only if its C5 measurements say otherwise |

Measured for Step 1 (min of 3 runs, per `sdf()` call): planetary-gear 2152.16→261.57 µs
(8.23x), gosper-curve-tube 2916.70→1001.88 µs (2.91x), mobius-strip 19.26→7.45 µs (2.59x),
gyroid-unit-cell 19.44→8.01 µs (2.43x), boys-surface 23.87→12.00 µs (1.99x). The whole
43-model equality sweep went 134.5 s → 30.9 s (4.35x). **The earlier pass's 4.4–11.6x /
median 6.7x did not reproduce** — treat its other figures with the same suspicion.

Two process notes for whoever picks this up:

- **Never `git add -A` after `scripts/bundle/bundle.sh`.** The bundle converts the
  development symlinks into real directories, so `-A` stages the deletion of eight tracked
  symlinks and commits the entire built `viewer/dist` (732 files, 217k insertions — this
  happened, and had to be reset). Run `scripts/dev/setup-symlinks.sh` after bundling and
  `git add` explicit paths.
- Step 2's change made `implicitPackageRoundTrip.test.js` fail, correctly. That test had the
  wrong value pinned deliberately, with a comment naming the exact cause. Read a failing
  assertion's comment before assuming the change is at fault.

---

## 1. Background: what is actually wrong

Measured on this branch. Numbers marked *(reported)* came from a prior analysis pass and
should be **re-measured** by the implementer rather than trusted; numbers without that mark
were verified directly.

Per-`sdf()` cost varies ~150× across the corpus:

| model | grid | samples | near surface | µs per `sdf()` |
|---|---|---|---|---|
| `gosper-curve-tube` | 96×96×23 | 225,816 | 3.9% | 2986 |
| `planetary-gear` | 96×96×20 | 197,589 | 9.1% | 2187 |
| `boys-surface-sculpture` | 96³ | 912,673 | 5.2% | 24.6 |
| `gyroid-unit-cell` | 96³ | 912,673 | 7.2% | 19.9 |

The cause is not the SDF maths. It is that the GLSL→JS interpreter signals control flow by
**throwing `Error` subclasses**, and V8 captures a stack trace on every `Error`
construction:

- `packages/implicitjs/src/lib/implicitCad/sdfEvaluator.js:964` — `class ReturnValue extends Error`
- `:973` — `class BreakSignal extends Error`
- `:979` — `class ContinueSignal extends Error`
- `:1173` — `throw new ReturnValue(...)`, executed on **every GLSL function return**
- `:1269` — `if (error instanceof ReturnValue)` catch site

`gosper-curve-tube`'s `sdf()` runs a 60-iteration loop calling `gosperPoint()` twice per
iteration, so a single evaluation throws ~120+ stack-capturing exceptions. Stack capture was
measured at 50–64% of self time *(reported)*.

Separately, colour is lost: `writeGlb.js:445` emits
`attributes: { POSITION, NORMAL }` only, so a model's `color(p, normal)` pattern is
flattened into one averaged `baseColorFactor`.

### 1.1 What is NOT in scope, and why

Do not attempt these. Each was investigated and rejected on evidence:

- **Sparse / octree / distance-bound cell skipping.** Unsafe for this corpus: 17 of ~30
  audited models drop geometry at safety factor 1, and a corpus-safe factor of ≥8 produces a
  net *slowdown* on three models *(reported)*. Non-exact SDFs (twist, scale, repeat)
  overestimate distance and would silently delete surface. This directly violates §0.
- **GPU field evaluation.** High ceiling but blocked: the skill ships as a ~179 KB esbuild
  bundle with no `node_modules` (Playwright cannot bundle), CI has no browser, and
  SwiftShader vs Metal disagree on near-surface corners while `bakeHash` covers only
  `{format, resolution, maxCells}` — so a GPU bake and a CPU bake would be mutually "fresh"
  while differing topologically.
- **Exporting the raymarched render to GLB.** Not possible: the raymarcher writes only
  `gl_FragColor` (GLSL ES 1.00, no `gl_FragDepth`, no MRT) into an 8-bit buffer and ends at
  `toDataURL`. Multi-view depth fusion loses 12.0% of `gyroid` and 57.7% of `klein-bottle`
  surface to self-occlusion *(reported)*, and would trade a watertight marching-tetrahedra
  mesh for reconstruction guesswork.
- **Raising the resolution cap.** See §6 — it is a real finding, but it is a separate
  decision with a size/perf tradeoff, not part of this plan.

---

## 2. Repo mechanics you must respect

Read `AGENTS.md` before starting. The parts that will bite you here:

- `packages/implicitjs` is the **source of truth** and is symlinked into both
  `viewer/packages/implicitjs` and `skills/implicit-cad/scripts/packages/implicitjs`.
  Editing it changes the viewer *and* the bundled skill runtime.
- After changing `implicitjs`, run `scripts/bundle/bundle.sh`, then
  `scripts/bundle/bundle.sh --check`. The pre-commit hook enforces this and **will block
  your commit** if the generated skill runtime is stale.
- `packages/cadjs/src/glb/writeGlb.js` is a five-line
  `export * from "implicitjs/glb/writeGlb.js"`. Do not add a second writer.
- `packages/implicitjs` must never import `packages/cadjs`. The dependency flows one way.
- Node 22 is required (`export PATH="$HOME/.nvm/versions/node/v22.22.0/bin:$PATH"`). Node 18
  fails with `bad option: --import`.
- Write any temporary scripts to `tmp/` or `/tmp`, never to `scripts/`.

### 2.1 Blast radius of the GLB writer

`writeGlb` has exactly three consumers:

- `packages/implicitjs/src/lib/implicitCad/renderGlb.js` (implicit package `model.glb`)
- `packages/implicitjs/src/lib/implicitCad/exporters.js` (implicit GLB/3MF/STL export)
- `packages/cadjs/src/lib/dxf/previewGlb.js` (DXF `preview.glb`)

**STEP component GLBs are NOT affected** — they are serialized in Python by
`export_assembly_glb_from_scene` (`packages/cadgen/src/cadgen/_internal/glb.py:82`, packing
`b"glTF"` itself at `:135`). Do not change Python for Steps 2 or 3.

Note there are **four independent `hexToRgb01` implementations**. Only one reaches a GLB
material. Do not "unify" them as a drive-by:

| location | used for |
|---|---|
| `implicitjs/src/lib/glb/bytes.js:114` | **GLB materials** (via `writeGlb.js:205`) — the one Step 2 touches |
| `implicitjs/src/lib/implicitCad/render.js:404` | raymarch shader uniforms |
| `implicitjs/src/lib/implicitCad/model.js:308` | param colour normalization |
| `implicitjs/src/lib/implicitCad/exporters.js:91` | 3MF/STL exporter colours |

---

## 3. Step 0 — Build the equality harness (do this first)

Nothing else may be merged until this exists and passes on an unmodified tree.

Create `packages/implicitjs/src/lib/implicitCad/sdfEquality.test.js`.

Placement matters and is easy to get wrong: `tests/` in this repo currently holds **Python
only** (`tests/python/…`). JS tests live beside the code they guard — see the existing
`mesh.test.js`, `meshWorkers.test.js`, `model.test.js` in that same directory. Follow that
convention; do not add a JS suite under `tests/`.

Because `packages/implicitjs` is meant to stand alone and be vendored, the harness must
**skip gracefully** (not fail) when the repo's `models/implicits/` corpus is not present
next to it, and run fully when it is.

Requirements:

1. Enumerate **every** `models/implicits/*.implicit.js`. Do not hardcode a subset; a new
   model must be covered automatically.
2. For each model, load it the way the builder does — see
   `packages/cadjs/bin/implicit-artifact.mjs:107-110`:
   ```js
   const model = normalizeImplicitCadModel(await import(sourceUrl), { sourceUrl });
   const sdf = createImplicitCadSdfEvaluator(model);
   ```
3. Evaluate `sdf(x, y, z)` at a **deterministic** set of points spanning the model's bounds
   (a fixed lattice plus fixed pseudo-random points from a seeded generator — no
   `Math.random()`). Use at least 2,000 points per model.
4. Do the same for `color()` via `createImplicitCadColorEvaluator`
   (`sdfEvaluator.js:1289`) where the model defines one.
5. Serialize results to a baseline JSON under `tmp/` keyed by model name.
6. Provide two modes: `--write-baseline` and `--check`. `--check` must assert
   **`Δ === 0` exactly** — not a tolerance. A tolerance would let a subtle semantic change
   through, which is precisely what §0 forbids.
7. Compare with `Object.is` semantics for the sign of zero and for `NaN`: a model that
   returns `NaN` outside its domain today must still return `NaN`, and `-0` must not silently
   become `0`. Plain `===` treats `NaN !== NaN` and `-0 === 0`, so both cases would slip
   through a naive check.

Also record, per model, a full-mesh baseline for use in Steps 1 and 4:

- triangle count, vertex count, and a stable hash of the sorted triangle multiset
- reuse the existing mesher entry point rather than reimplementing it

**Gate:** run `--write-baseline` on a clean tree, then `--check` immediately. It must pass
trivially. Commit the harness on its own before touching any source.

---

## 4. Step 1 — Transpiler control flow (bit-identical, highest value)

**File:** `packages/implicitjs/src/lib/implicitCad/sdfEvaluator.js`

### The change

Stop the three control-flow signals from extending `Error`, which is what triggers V8 stack
capture:

- `:964` `class ReturnValue extends Error` → plain class holding `value`
- `:973` `class BreakSignal extends Error` → plain class
- `:979` `class ContinueSignal extends Error` → plain class

`BreakSignal` and `ContinueSignal` carry no payload, so make them **module-level frozen
singletons** and throw the singleton — this removes the allocation entirely. `ReturnValue`
carries a value, so keep allocating a fresh instance per throw (a shared mutable instance is
unsafe under recursion, and allocation is cheap once `Error` is out of the picture).

### Required audit before you finish

Removing `extends Error` changes what `catch` blocks see. Search the whole file (and any
other file that catches from the evaluator) for:

- `instanceof Error`
- `error.message`, `error.stack`, `error.name`
- bare `catch` blocks that rethrow or wrap

Any site that assumed these signals were `Error`s must be corrected. `instanceof ReturnValue`
(`:1269`) keeps working unchanged. **This audit is the main risk in Step 1 — do not skip it.**

### Do not, in this step

Do not restructure the interpreter to avoid `throw`/`catch` altogether. That is a much larger
refactor with real semantic risk. Land the minimal change, measure, and only then consider
more.

### Gate

- `node tests/implicit/sdf-equality.test.js --check` → **`Δ === 0` on every model**
- Mesh baselines unchanged: identical triangle multiset hash for every model
- `npm --prefix packages/implicitjs test` passes, including
  `meshWorkers.test.js:44` ("parallel meshing is byte-identical to the serial mesher") —
  **unmodified**. If you find yourself editing that test, you have broken something.
- Re-measure and record the speedup per model. Prior pass reported 4.4–11.6×, median 6.7×
  *(reported)*.

### Why this is safe to ship

Bit-identical output means `bakeHash` and `sourceClosureHash` stay valid, no cached package
is invalidated, and no model needs rebuilding. It is a pure speedup with no artifact change.

---

## 5. Step 2 — sRGB linearization in GLB materials

**File:** `packages/implicitjs/src/lib/glb/bytes.js:114-125` (`hexToRgb01`)

glTF `pbrMetallicRoughness.baseColorFactor` is defined in **linear** space. `hexToRgb01`
divides by 255 and stops, so authored sRGB hex values are written as if already linear,
brightening every affected GLB.

Add standard sRGB→linear conversion:

```
c <= 0.04045  ->  c / 12.92
c >  0.04045  ->  ((c + 0.055) / 1.055) ^ 2.4
```

Apply it **only** on the path feeding `materialFor` (`writeGlb.js:205`). Do not touch the
other three `hexToRgb01` copies listed in §2.1 — `render.js`'s feeds shader uniforms and is a
different concern.

### Gate

- Unit test: known hex → expected linear triple (include `#000000`, `#ffffff`, and a
  mid-tone where the two curves differ measurably).
- Confirm the change is visible in the three consumers of §2.1 and **absent** from STEP
  packages (Python path untouched).
- Renders will legitimately darken toward correct. That is the fix, not a regression — but
  screenshot one implicit model before and after and attach both to the PR.

### Consequence

This changes GLB bytes, so implicit and DXF packages must be rebuilt. Say so in the PR.

---

## 6. Step 3 — Per-vertex `COLOR_0`

This is the fix for "specified colour patterns are lost". It is independent of Steps 1 and 4
and can ship alone.

### 6.1 Writer

**File:** `packages/implicitjs/src/lib/glb/writeGlb.js`

`:445` currently emits `attributes: { POSITION: …, NORMAL: … }`. Add `COLOR_0`.

- Evaluate the model's `color(p, normal)` per vertex via the existing colour evaluator.
  Reported cost ~24 µs/vertex ≈ 4.9 s at 206k vertices *(reported)* — re-measure.
- Encode as **`VEC4` / `UNSIGNED_SHORT`, normalized**. Do **not** use `UNSIGNED_BYTE`: it was
  measured at 6.4 sRGB codes of error on dark models *(reported)*.
- Respect the existing quantization/stride machinery. This file already had a stride bug
  fixed once — read the `strideElements` helper and the `KHR_mesh_quantization` /
  `EXT_meshopt_compression` handling before adding an accessor, and follow the same padding
  rules (per-element stride, not tail padding).
- With per-vertex colour present, `baseColorFactor` must become white
  (`[1, 1, 1, 1]`) or the two multiply together and double-darken the result.
- Vertex colours are **linear** in glTF, same as Step 2 — apply the same conversion.

### 6.2 Reader

**File:** `packages/cadjs/src/lib/render/glbMeshData.js:462`

```js
const colors = new Float32Array(0);
```

This hardcodes empty colours, so the repo's reader discards `COLOR_0` even though three.js
parses it. Populate it from the parsed primitive.

Then confirm the viewer's material path actually renders vertex colours (`vertexColors` must
be enabled on the material). A correct writer plus a reader that drops the data looks
identical to doing nothing — verify end-to-end in the viewer, not just in a unit test.

### 6.3 Verified specifics (established while executing Steps 0–2 — do not re-derive)

The claim that this is "blocked by two lines" is right, but only because the rest of the
chain already exists. Confirmed by reading the code:

- **The viewer consumer chain is already built and in use** (robot meshes use it today).
  `cadScene.js:326` gates on `shouldUseDisplayVertexColors = has_source_colors &&
  isNumericArray(colors, 3)`; `cadScene.js:764` requires
  `meshData.colors.length === meshData.vertices.length` and builds the `color` BufferAttribute;
  `surfaceMaterials.js:55/183` and `cadScene.js:1035` toggle `vertexColors` on the material.
  **Nothing new is needed in the viewer.** (An early read of this suggested there was no
  consumer at all; that was wrong.)
- **Shape contract:** `colors` is flat **RGB (3 components), not RGBA**, one entry per
  DE-INDEXED vertex, exactly `vertices.length`. The reader de-indexes (see the vertexCount
  assertion in `implicitPackageRoundTrip.test.js`), so colours must be de-indexed with the
  positions. This is independent of the VEC4/USHORT choice for the file itself.
- **Colour space:** glTF `COLOR_0` is LINEAR, and three treats a `color` attribute as linear
  under `vertexColors`. Write linear, read linear, pass through — apply the same
  `srgbToLinear` Step 2 added, since a model's GLSL `color()` returns sRGB 0..1 (it mixes
  hex-derived params).
- **Where to evaluate:** post-weld, against `welded.positions`/`welded.normals` inside
  `writeGlb`. `color(p, normal)` is pure, and `weldMesh` merges on position AND normal
  (see "keeps creases" in `writeGlb.test.js`), so a welded vertex has one well-defined
  colour. Do NOT try to weld a colour array — pass a callback and evaluate after welding.
- `renderGlb.js`'s header comment states per-vertex colour "would not help" because the
  reader drops it. That reasoning is what this step invalidates — **update that comment**.

### Gate

- Round-trip test: write a GLB with known per-vertex colours, read it back, assert the values
  survive. Model it on the Step 2 test "an authored colour round-trips through GLB as the
  same sRGB hex" in `writeGlb.test.js`, which proved its own fix by failing without it.
- Visual: open an implicit model with a strong pattern (`gosper-curve-tube` mixes
  `#24e6c2` → `#fff45a` via a `hexBand` gradient) and confirm the gradient appears instead of
  a flat average.
- File-size delta recorded per model.

---

## 7. Step 4 — Post-sampling `sdf()` reduction (OPTIONAL, gated)

Attempt only after Steps 0–1 are merged and stable. **This one changes output**, so it is
governed by §0 more strictly than the others.

Polygonization makes more `sdf()` calls than sampling does — reported at exactly 5.00 per
triangle, 40–69% of total *(reported)*. Two sites in
`packages/implicitjs/src/lib/implicitCad/mesh.js`:

- `:115-122` `estimateGradient` — **6 calls per unique vertex**, used for smooth normals
- `:132-136` `normalFacesOutward` — **2 calls per triangle**, used for winding

The proposal is to derive both from data already sampled:

- **Winding** from the marching-tetrahedra sign pattern (`TETRAHEDRA`, `mesh.js:6-13`, and
  the polygonizer around `:193-221`). This is a purely combinatorial derivation and should be
  exactly equivalent — gate on an identical triangle multiset hash.
- **Normals** from the sampled lattice gradient instead of six fresh probes. **This is NOT
  equivalent** and was never verified. It trades gradient accuracy for speed and will change
  shading.

Therefore split the step:

- **4a (winding).** Gate: triangle multiset hash identical for every model. If it is not
  identical, abandon — do not accept "close".
- **4b (normals).** Gate: report max and mean angular deviation per model against the current
  gradient normals, and render before/after screenshots for at least five models spanning the
  corpus. **Do not merge 4b on your own judgement — surface the numbers and images and let a
  human decide.** Under §0, a silent shading change is exactly the kind of thing that must be
  escalated rather than assumed acceptable.

Reported combined effect with Step 1: `gyroid-unit-cell` 79.3 s → 3.27 s (24.3×) *(reported)*.

---

## 8. Known finding, deliberately deferred: the resolution ceiling

Not part of this plan, recorded so it is not lost.

The lumpy/patchy appearance of thin-feature models is **not** a speed problem and none of the
steps above fix it:

- `mesh.js:4` `DEFAULT_RESOLUTION = 96`
- `mesh.js:5` `DEFAULT_MAX_CELLS = 2500000`
- `mesh.js:35` `normalizeResolution` clamps to `[8, 192]`
- `mesh.js:46-62` `implicitCadGrid` rescales the grid down when `nx·ny·nz > maxCells`

Consequence, verified arithmetically: for a cubic model, 144³ = 2,985,984 and 192³ =
7,077,888 both rescale to **exactly 135³**. Requesting resolution 144 or 192 produces an
identical grid to each other, and only ~1.4× the linear resolution of the default.

`gosper-curve-tube` has `tubeRadius` 1.12 mm inside a ~72.6 mm box, so at the effective grid
its tube is roughly 3 voxels across — which is why it looks lumpy. It needs roughly resolution
300 to be smooth.

Raising both caps is the fix, but it is a product decision with a GLB size and build-time
cost, and Step 1's speedup is what makes it affordable. Revisit after Step 1 lands with real
numbers.

---

## 9. Suggested sequencing

1. Step 0 (harness) — commit alone.
2. Step 1 (transpiler) — commit alone. Bit-identical, so it can ship independently and
   de-risks everything else.
3. Step 2 (sRGB) — small, independent.
4. Step 3 (`COLOR_0`) — writer and reader together; useless if split.
5. Step 4a, then pause at 4b for human review.

Run `scripts/bundle/bundle.sh` then `scripts/bundle/bundle.sh --check` before **each**
commit that touches `packages/implicitjs`, and keep the development symlink layout intact
(`scripts/dev/setup-symlinks.sh --check`).

Checks to run before handoff:

```bash
npm --prefix packages/implicitjs test
npm --prefix packages/cadjs test
npm --prefix viewer run test
npm --prefix viewer run build
scripts/bundle/bundle.sh --check
```
