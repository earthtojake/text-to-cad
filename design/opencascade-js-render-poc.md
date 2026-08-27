# POC: opencascade.js as the viewer's render kernel

**Question.** Could WASM OCCT (opencascade.js) replace the Python/cadgen dependency on
the render side — the viewer rendering STEP models "from scratch" in the browser —
while keeping the generation-side performance wins (op memo, component store, closure
hashes)? CLIs (inspect/snapshot refs) would keep using cadgen's caches.

**Setup.** `opencascade.js@2.0.0-beta.b5ff984` (full build, OCCT ~7.6), Node 26,
Apple Silicon. Producer side: OCP/OCCT 7.9. Fixtures: the repo's own generated
packages and STEP exports. Harness: `tmp/ocjs-poc/` on this branch (gitignored,
one-off). All numbers measured, not estimated.

## Measured results

### Runtime footprint

| | value |
|---|---|
| wasm artifact | 48 MB |
| init (single instance) | 2.3 s |
| init (4 worker instances, parallel) | 3.5 s wall, ~2.3 GB RSS |

### STEP file parse (read + transfer)

| file | size | native OCP | WASM | ratio |
|---|---|---|---|---|
| cam_follower_roller.step | 22 KB | 0.00 s | 0.13 s | — |
| planetary_gear_assembly.step | 2.3 MB | 0.22 s | 3.81 s | **17×** |
| cutaway_turbofan_engine.step | 6.6 MB | 0.66 s | 8.39 s | **13×** |
| moonwatch.step | 114 MB | 12.9 s | 150.3 s (44.6 read + 105.7 transfer) | **12×** |

Face counts identical in every case (8 / 582 / 1572) — correctness is fine; speed is
the problem. The "2–4× slower than native" folklore for WASM OCCT is optimistic for
STEP translation: measured 12–17×. Moonwatch — a model that opens from its package
in about a second today — takes two and a half minutes per cold parse in WASM.

### BinTools `.brep` blob interop (the surprising positive)

WASM OCCT 7.6 reads the component blobs written by OCP 7.9 **perfectly**:

- All 9 planetary components: identical face/edge counts, surface areas identical to
  6 decimals, volumes match.
- **Face enumeration order is identical** across all components — per-face area
  sequences match element-for-element. Selector ids (`o1.fN`) derived in WASM would
  agree with cadgen's tables, at least across this version pair.
- Read cost: 4–19 ms per component.

Caveat: this worked 7.9→7.6 today, but BinTools carries a format version and a future
OCCT bump could break it. If anything ever ships on this path, the producer must pin
`BinTools_FormatVersion` on write.

### Tessellation (the same 9 planetary components)

| pipeline | time | triangles | µs/tri | parallel? |
|---|---|---|---|---|
| surf tessellator (ours, plain JS) | 285 ms | **24,777** | 11.5 | yes (worker pool, no per-worker cost) |
| WASM BRepMesh @ 0.1/0.5 (defaults) | 577 ms | 3,868 | 149 | one 2.3s+~500MB instance per worker |
| WASM BRepMesh @ 0.01/0.2 (tighter) | 689 ms | 6,720 | 103 | — |

The surf tessellator is **~10–13× faster per triangle**, produces 4–6× denser
(curvature-adaptive) output, and parallelizes for free. Matching surf's triangle
density in WASM would push well past 1 s for this small assembly, single-threaded;
extrapolated to f14d (1,127 components, surf pool: 18.4 s), WASM meshing is minutes.

## Conclusions

1. **"Viewer parses STEP directly" (Option A) is dead on arrival.** 13–17× parse
   penalty on every cache miss, plus meshing at 10× the cost and a fraction of the
   quality, plus 48 MB + 2.3 s before the first byte of geometry. It also *discards*
   the content-addressed caching rather than reusing it — a STEP file has no cids.

2. **"WASM consumes the existing `.brep` blobs" (Option B) is technically viable but
   strictly worse than what exists.** The interop and face-order parity results are
   genuinely encouraging — the blobs read perfectly and selector ids would line up.
   But the pipeline it would replace (`.surf` + client tessellation) is *already the
   pure-JS render flow*: exact surfaces evaluated with plain math, no kernel at all,
   faster than the kernel and finer-grained. Swapping it for WASM BRepMesh trades
   11.5 µs/tri JS for 103–149 µs/tri WASM, loses the classified-edge/appearance
   contract, and adds a 48 MB second kernel whose version must track the producer's.
   The premise of the question — "use OCCT for rendering" — turns out to be solved
   better by not having a kernel on the render side at all.

3. **Where WASM OCCT would earn its place: a no-cadgen import fallback.** Parse times
   of 3.8 s (planetary) / 8.4 s (turbofan) are unusable as the standing render path
   but acceptable as a one-time "quick look" at a foreign STEP when no cadgen is
   installed — mesh-only preview, nothing written, real import still owned by cadgen.
   That is the bounded version worth considering if drag-and-drop STEP viewing without
   Python ever becomes a product goal; a trimmed build (occt-import-js-style, ~10 MB)
   would fit better than the full 48 MB.

**Verdict:** keep the surf handoff. The render side already runs kernel-free JS with
content-addressed caching; opencascade.js can only re-introduce a kernel where one was
deliberately eliminated, at 10–17× the cost. The one open door is the import-preview
fallback, which touches no caches and no contracts.
