# Implicit CAD: compile GLSL to JS (kill the per-call interpreter)

Execution plan. Follow-up to `design/implicit-sdf-performance-and-colour.md` (Steps 0–2
shipped there; this plan supersedes its Step 4's urgency). Branch: continue on
`claude/step-generation-status-tracking-1b7ff6`.

## 0. The governing constraint (unchanged from the previous plan)

**Preserve the full underlying functionality of the SDFs, bit for bit.** The corpus
equality harness (`packages/implicitjs/src/lib/implicitCad/sdfEquality.test.js`, 43 models ×
2,129 points, sha256 over raw Float64 bytes) is the gate. It has been falsified once
already — a `Number.EPSILON` perturbation is caught on every model — so a green run means
something. Nothing in this plan may loosen it.

The compiler's failure mode must be **slowness, never wrong geometry**: any model the
compiler cannot handle falls back to the interpreter silently and correctly.

### 0.1 Execution status

Update as you go; this is the handoff record.

| Step | Title | Status | Notes |
|---|---|---|---|
| C1 | Export the codegen environment | **DONE** | `implicitSdfEvaluatorInternals.helpers` |
| C2 | The compiler (`sdfCompiler.js`) | **DONE** | ~420 lines; injected env, no import cycle |
| C3 | Wire in with fallback | **DONE** | zero call-site changes; `.compiled` flag |
| C4 | Gates | **DONE** | all 43 compile; differential + baseline both caught a deliberate `+`->`-` mis-emission per model; 10 semantic unit tests |
| C5 | Measure | **DONE — see below** | conservative tier lands 1.4–3.0x, NOT the predicted 10–100x |

### C5 measured results (min of 3, µs per `sdf()` call)

| model | interpreted | compiled | speedup |
|---|---|---|---|
| planetary-gear | 265.78 | 88.52 | 3.00x |
| gosper-curve-tube | 969.66 | 535.02 | 1.81x |
| mobius-strip | 7.38 | 4.22 | 1.75x |
| boys-surface-sculpture | 12.37 | 8.39 | 1.47x |
| gyroid-unit-cell | 8.12 | 5.78 | 1.40x |

End-to-end: gyroid-unit-cell `--force` rebuild 12 s -> 6 s. Corpus equality sweep
30.9 s -> 15.0 s.

**The 10–100x prediction was wrong for this tier.** Removing dispatch (AST walk, Scope
maps, thrown returns) bought 1.4–3x; the dominant remaining cost is the helper-side vec
machinery the conservative contract deliberately keeps -- every `H.add` on vecs runs
`mapBinary`'s `Array.from` with a fresh closure, so gosper still allocates thousands of
intermediate arrays per call. **This is precisely the evidence §6 required before phase 2:
typed emission** (GLSL is statically typed, so scalar-scalar ops can emit raw `+` and
known-width vec ops can emit array literals -- bit-identical per component, gated by the
same harness). Phase 2 is now justified and is the next step.

### Phase 2 SHIPPED — typed emission, measured (min of 3, µs per `sdf()` call)

| model | interpreted | phase 1 | phase 2 | total |
|---|---|---|---|---|
| planetary-gear | 265.78 | 88.52 | 56.95 | 4.67x |
| gosper-curve-tube | 969.66 | 535.02 | 332.48 | 2.92x |
| mobius-strip | 7.38 | 4.22 | 3.10 | 2.38x |
| boys-surface-sculpture | 12.37 | 8.39 | 6.16 | 2.01x |
| gyroid-unit-cell | 8.12 | 5.78 | 5.07 | 1.60x |

Shape inference from declared types; scalar ops inline to raw operators, known-width vec
ops to componentwise array literals; stores drop `cloneValue` when the value is scalar or
provably fresh. Anything type-uncertain stays on the helper path. Falsified with a
valid-JS-but-wrong-math perturbation (vec component pinned to [0]) — caught corpus-wide on
sdf and color digests. Cumulative from branch start: gosper 2916→332 µs (8.8x),
planetary-gear 2152→57 µs (37.8x). Remaining cost is builtin-call interiors (mapUnary
wrappers, vec constructors) and castValue boundaries — a possible phase 3, only on
evidence of need.

## 1. Why (measured this session)

`createImplicitCadSdfEvaluator` walks the GLSL AST **on every call** — scope `Map`s, a
thrown `ReturnValue` per GLSL function return, array allocation per vec op. Per-call cost
therefore scales with AST nodes executed, not with the math:

| model | µs/call (interpreted, post-Error-fix) |
|---|---|
| gosper-curve-tube | 1001.88 |
| planetary-gear | 261.57 |
| boys-surface-sculpture | 12.00 |
| gyroid-unit-cell | 8.01 |
| mobius-strip | 7.45 |

A build makes ~225k–913k grid samples plus ~5 calls/triangle in polygonize. So
`hilbert-curve-block` takes 18+ minutes and `gosper` 233 s, while the actual math is
milliseconds' worth of `sin/cos`. Compiling the same AST to a JS function once (~ms,
amortized over ~10⁶ calls) removes the interpretation tax. Alternatives (GPU, sparse
sampling, Python/numpy) were investigated and rejected with evidence — see the discussion
recorded in `design/implicit-sdf-performance-and-colour.md` §1.1 and this plan's §6.

## 2. Architecture: one frontend, two backends

```
GLSL source ──tokenize/Parser──► AST ──┬── interpreter (reference, stays forever)
                                       └── compiler → JS source → new Function (fast path)
```

The parser, the AST, the builtin library, and the value helpers are all shared. The
compiler is a **string-emitting mirror** of the interpreter's walker: where
`evalExpression` has a `case` that computes a value, the compiler has the same `case` that
emits the equivalent JS expression.

### 2.1 The entire language surface (verified against the interpreter)

The interpreter (`sdfEvaluator.js`) handles exactly this; the compiler handles exactly this
and nothing more:

- **Statements (9):** `empty`, `block`, `var`, `expr`, `return`, `if`, `break`,
  `continue`, `for` (`:1169–1195`)
- **Expressions (9):** `literal`, `identifier`, `member` (swizzles), `unary`, `update`
  (`++`/`--`), `binary`, `ternary`, `assign` (incl. swizzle assignment), `call`
  (`:1104–1154`)
- **Binary ops (12):** `+ - * /` via the `add/sub/mul/div` helpers; `< > <= >= == !=`;
  `&& ||` via `truthy()` (`:1060–1071`)

There is **no** `while`, no `switch`, no array indexing, no structs, no recursion (GLSL
forbids it). 18 node kinds total. Any AST node outside this set must throw a
`CompileUnsupported` error from the codegen, which triggers interpreter fallback for the
whole model.

### 2.2 The conservative contract: identical by construction

The generated code must call the **same function objects** the interpreter calls — not
reimplementations:

- arithmetic on possibly-vec values → the module's `add/sub/mul/div` (which route through
  `mapBinary` with its `?? 0` fills)
- builtins and user-visible constructors → the same `BUILTINS` entries
- swizzle read/write → the same `getSwizzle`/`setSwizzle`
- truthiness → the same `truthy` (vec truthiness is `some(truthy)`)
- type coercion at function boundaries → the same `castValue`/`defaultValueForType`

Same functions, same operation order ⇒ same IEEE 754 results, before any test runs. The
harness then verifies what construction implies. Only the *dispatch machinery* is compiled
away: AST walking, `Scope` map lookups, the throw/catch return path, per-call argument
arrays. The vec allocations inside helpers remain — that is deliberate; see §6 phase-2.

### 2.3 Semantic traps (verified in the interpreter — match them exactly)

CORRECTED during execution: an earlier draft claimed `&&`/`||` do not short-circuit, read
off `binaryValue` (`:1070`). That path is dead for those ops — the `binary` case
special-cases them first. Read the interpreter, not this doc, when in doubt.

1. **`&&`/`||` short-circuit through `truthy`** (`evalExpression` `:1128-1133`): the right
   operand is only evaluated when the left doesn't decide. Emit
   `H.truthy(<left>) && H.truthy(<right>)` — native JS laziness matches exactly.
2. **`==` is `===` on the raw values** (`:1068`). For two vecs that is *reference*
   equality. Quirky, but it is the shipped semantic — preserve it; do not "fix" it to
   componentwise comparison.
3. **Blocks do not create scopes** (`case "block"` `:1171` reuses the caller's scope), so
   every declaration is FUNCTION-scoped, `var`-style: a redeclaration overwrites, a
   `for`-init counter leaks past its loop, and a branch-local declaration is readable
   after the `if`. Emitting JS `let` inside `{}` blocks would silently diverge. The
   compiler must HOIST every declared name (plus loop guards and temps) to the top of the
   generated function and turn declarations into assignments.
4. **Assignment clones vectors** (`Scope.set`/`define` route through `cloneValue`,
   `:1015-1029`): `a = b` stores a copy, while the assignment *expression* evaluates to
   the un-cloned right-hand value (`evalLValue` `:1081-1084`). Swizzle writes mutate the
   live array via `setSwizzle`, then re-store a clone. The compiler must reproduce these
   clone points — plain `l_a = l_b` in generated code would alias where the interpreter
   copies.
5. **Uniforms are captured at runtime creation**, `castValue`d once
   (`createImplicitCadProgramRuntime`, `:1263`), alongside globals `PI`/`TWO_PI` and any
   top-level GLSL statements executed once into the global scope. The compiled factory
   must do the same: capture/cast once, not re-read per call, and run `program.globals`
   once into a mutable globals object (function bodies may assign to globals; that state
   persists across calls in the interpreter and must in compiled code too).
6. **The `for` guard is semantic**: loops abort with "GLSL for-loop exceeded exporter
   safety limit" after 10,000 iterations (`:1197-1217`), and `continue` still runs the
   update expression. Emit the update in the JS `for` header's update slot alongside the
   guard increment so native `continue` matches.

## 3. Implementation steps

### C1 — Export the codegen environment

`implicitSdfEvaluatorInternals` (`sdfEvaluator.js:1308`) currently exports
`{ BUILTINS, tokenize, Parser }`. Extend it with what the compiler needs — the helper
functions themselves, as one object:

```js
export const implicitSdfEvaluatorInternals = {
  BUILTINS, tokenize, Parser,
  helpers: {
    add, sub, mul, div, truthy, castValue, defaultValueForType,
    getSwizzle, setSwizzle, finiteNumber, vec2, vec3, vec4,
  },
  normalizedDistanceSource, normalizedColorSource,
};
```

No behavioral change; commit alone or with C2.

### C2 — The compiler: `packages/implicitjs/src/lib/implicitCad/sdfCompiler.js`

One exported function, mirroring the interpreter runtime's interface exactly:

```js
// Returns { call(name, args) } like createImplicitCadProgramRuntime, or null if any
// construct is unsupported. Must never throw out of compileImplicitProgramRuntime itself.
export function compileImplicitProgramRuntime(model, source) → runtime | null
```

Internals:

- Parse with the shared `Parser`/`tokenize` (same normalized source as the interpreter —
  the normalizer is NOT touched; both backends consume its output, so its known quirks
  cancel out).
- Walk each `program.functions` entry and emit a JS function:

  ```js
  function f_sdf(l_p) {
    l_p = H.castValue(l_p, "vec3");
    // ...body, native control flow...
    return H.defaultValueForType("float");   // implicit-return path
  }
  ```

  - `return expr;` → `return H.castValue(<expr>, "<returnType>");` — native `return`,
    no `ReturnValue` object.
  - `break`/`continue` → native keywords (loops are real `for` loops).
  - `var` declarations → `let`; every GLSL identifier is name-mangled (`l_` locals/params,
    `u_` uniforms/globals, `f_` functions) so no identifier can collide with a JS reserved
    word or the environment names.
  - Swizzle assignment (`v.xy = ...`) → `H.setSwizzle(l_v, "xy", <expr>)`; compound
    assignment and `update` mirror the interpreter's `assign`/`update` cases.
  - Calls: user function → `f_<name>(...)`; builtin → a pre-resolved `const B_<name>`
    hoisted at factory top (avoids per-call map lookups but is the same function object).
- Assemble one source string: hoisted builtin consts, uniform/global consts (captured
  per §2.3), the compiled functions, then `return { <entries> }`.
- Materialize with `new Function("H", "U", src)` where `H` = the helpers object, `U` = the
  cast uniform values. Wrap the *entire* compile in try/catch → return `null` on anything.
- Attach `runtime.compiled = true` for the gates.

Size expectation: ~400–600 lines including comments. The emitters should visually mirror
the interpreter's `case` blocks; a reviewer must be able to diff them side by side.

### C3 — Wire in with fallback (zero call-site changes)

In `createImplicitCadSdfEvaluator` / `createImplicitCadColorEvaluator` only:

```js
const runtime =
  (process.env.IMPLICIT_SDF_FORCE_INTERPRET !== "1" &&
    compileImplicitProgramRuntime(model, source)) ||
  createImplicitCadProgramRuntime(model, source, entryName);
```

The entry wrappers (`finiteNumber(..., 1e6)` for sdf, the clamp for color) stay byte-for-
byte identical. **No changes** to `mesh.js`, `meshWorkers.js`, `meshWorkerEntry.js`,
`exportModel.js`, or any builder — workers call `createImplicitCadSdfEvaluator` and get
compilation automatically. Expose the compiled flag on the returned evaluator function
(e.g. `evaluator.compiled = runtime.compiled === true`) for C4.

`IMPLICIT_SDF_FORCE_INTERPRET=1` is the A/B lever, the benchmark baseline, and the
emergency exit.

### C4 — Gates (all three are mandatory)

1. **Differential, on every harness run.** Extend `sdfEquality.test.js`: for each model,
   build BOTH runtimes and digest both; assert compiled ≡ interpreted ≡ the frozen
   baseline, with the existing byte-digest (`Object.is`) semantics. The interpreter is now
   an executable oracle, not just a frozen file.
2. **Coverage must be loud.** Assert that **all 43 models compile** (`evaluator.compiled
   === true`). Without this, a codegen regression silently falls back everywhere, every
   test stays green, and the speedup quietly vanishes. If a model legitimately cannot
   compile, it goes in an explicit, commented allowlist in the test — never silent.
3. **Falsification, once, recorded.** Temporarily mis-emit one node (e.g. swap `add` for
   `sub` in the binary emitter), confirm the harness fails naming models, revert. Record
   in the commit message, as Step 0 did with its `Number.EPSILON` check.

Existing suites must pass unmodified — in particular `meshWorkers.test.js:44`
("parallel meshing is byte-identical to the serial mesher") now exercises the compiled
path on both sides, and `mesh.test.js`'s edge-refinement tests exercise compiled `sdf`
inside `interpolateVertex`. If any of them needs editing, something is wrong with the
compiler, not the test.

### C5 — Measure, bundle, commit

- Per-call: min-of-3 probe (the `/tmp/q.mjs` pattern: stride-sample the model's own grid,
  report µs/call) for gosper-curve-tube, planetary-gear, mobius-strip, gyroid-unit-cell,
  boys-surface-sculpture — interpreted (`IMPLICIT_SDF_FORCE_INTERPRET=1`) vs compiled,
  same machine, same run.
- End-to-end: `cadgen.implicit_artifact --force` wall time for gosper-curve-tube,
  dragon-curve-ribbon, hilbert-curve-block.
- Record BOTH tables in the commit message. Predictions are ranges (10–100× per-call on
  interpreter-heavy models); the previous plan's predictions missed once (6.7× claimed,
  2.6× measured) — report what is, not what was hoped.
- `scripts/bundle/bundle.sh` then `scripts/bundle/bundle.sh --check`, then
  `scripts/dev/setup-symlinks.sh` — and **never `git add -A` after bundling** (see the
  previous plan's §0.1 process notes for how that once committed 732 files). Stage
  explicit paths; the regenerated skill runtimes
  (`skills/implicit-cad/scripts/packages/cadjs/bin/*.mjs`,
  `skills/cad/scripts/snapshot/runtime/snapshot-render.js`) belong in the commit.

Because compiled output is bit-identical, `bakeHash`/`sourceClosureHash` stay valid and
**no package rebuilds** — this ships as a pure speedup, like the Error-subclass fix.

## 4. Rules and pitfalls

- Do not modify the interpreter's semantics, the parser, or the normalizer in this plan.
  (The normalizer has known sharp edges — it has mangled `1.0e-6` and `i == 0` patterns
  historically — but both backends read its output, so they cancel; touching it breaks
  the cancellation.)
- Do not "improve" GLSL semantics in codegen (short-circuiting, componentwise `==`,
  swizzle inlining). Every such improvement is a digest mismatch.
- `new Function` runs in Node (builders, workers, skill runtime) — no CSP concern. If some
  future browser context forbids eval, the try/catch fallback already handles it.
- The compiled runtime must be self-contained after creation: no imports inside generated
  source; everything arrives via the `H`/`U` factory arguments.
- Keep `implicitSdfEvaluatorInternals.helpers` the single source of the helper set; the
  compiler must not re-declare or copy any helper.

## 5. Expected results

Per-call: interpreter-heavy models (gosper ~1000 µs, planetary-gear ~260 µs) should drop
by 10–100×; already-cheap models (gyroid ~8 µs) by perhaps 3–10× (helper allocations
remain). End-to-end floor per model ≈ samples×cost + weld (85 ms–1.3 s) + write
(60–250 ms) + spawn ≈ **seconds, not minutes**: gosper 233 s → single digits expected,
hilbert-curve-block 18 min → tens of seconds. These are estimates to be replaced by C5's
measured tables.

## 6. Non-goals, and what this unlocks

Explicitly OUT of scope:

- **Scalarization / inlining** (emitting `[a[0]+b[0], ...]` instead of `H.add`): breaks
  identical-by-construction, relies on the harness alone, and is only worth doing if C5's
  numbers say helper allocation dominates. Phase 2, separate plan, only on evidence.
- **GPU field evaluation** — still blocked (bundling, CI, backend nondeterminism).
- **Sparse/adaptive sampling** — rejected on measured geometry loss; do not revisit.
- **Polygonize call-thinning** (winding from tetra signs) — likely unnecessary once calls
  are ~1 µs; only on evidence.
- Any grid, model, or GLB-writer change.

Unlocked after C5 (separate follow-ups, in order):

1. Raise `MIN_THIN_AXIS_CELLS` back toward 24+ (`mesh.js`) — the staircase quality that
   was dialed back for cost.
2. Feature-driven resolution: lift a model's lattice until its thinnest wall spans ~2
   cells — the real fix for the chmutov/tanglecube/koch debris (walls measured at
   0.109–0.475 mm against ~1 mm cells). Affordable once sampling is compiled.
