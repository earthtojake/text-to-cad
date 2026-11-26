# viewcore bench

Reference outputs, the host runs and the comparison. All outputs share one folder layout (`reference.py`'s):
`<out>/<model>/{structure.json, timing.json, parts/<index>/{key, shape.bin, mesh.xbm, elements.json, groups.json, measure.json}}`.
Parts sharing a key are computed once and their files copied. Sample inputs: `.xbf` files; the module: `dist/viewcore.wasm`.

**reference.py** runs cad's own engine (native, one thread) and writes the reference outputs. With cad's environment:
`.venv/bin/python packages/viewcore/bench/reference.py OUT_DIR a.xbf b.xbf ...`

**dump_core.py** runs the core under wasmtime (`hosts/wasmtime/viewcore.py`) and writes the same layout, with the core's
bytes as they came, plus `timing.json`: compile, instantiate, open, structure, shape_bytes, mesh, elements, groups,
measure (seconds, summed over unique parts), and the median / p95 latency of ~100 seeded random `vc_fact` picks.
Needs a Python with `wasmtime`: `python dump_core.py OUT_DIR [--wasm PATH] [--picks N] [--cache FILE] a.xbf ...`.
Each file gets a fresh instance, so memory and timing are per model.

**compare.py** compares two such folders per model: `.venv/bin/python compare.py LEFT_DIR RIGHT_DIR [--json OUT] [--models a,b]`
(cad's Python, for numpy). It prints a table per aspect (structure, shape bytes and keys, mesh header / face and edge
tables / areas / points, elements, groups, measure, byte-identical counts) and writes `compare.json` (default beside
RIGHT_DIR's contents). Use it for reference vs core and for wasmtime vs browser. Comparing a folder with itself reports
everything identical.

**web_bench.mjs** drives headless Chromium (Playwright, no install step) with a local server: per model a fresh page and a
Worker running `hosts/web/viewcore.js`. It measures fetch, compile, instantiate, open, structure, first mesh (and the cold
total to it), all shape bytes / meshes / elements / groups / measures, per-pick `vc_fact` latency (core time and round
trip, median / p95) and the peak renderer-process RSS (sampled with `ps` every 50 ms), and POSTs the core's bytes back
to Node so the folder layout is written for compare.py. `node web_bench.mjs OUT_DIR [--wasm PATH] [--throttle 4]
[--picks N] [--files DIR] juno centrifugal_impeller ...` (names resolve to `--files`, default the package's
`tmp/files/`, or pass .xbf paths). `--throttle` sets CDP `Emulation.setCPUThrottlingRate` on the page. Measured: it does NOT slow the Worker (core
times in juno / centrifugal_impeller were unchanged at 4x), so it only throttles the page's main thread.

**sizes.mjs** prints `viewcore.wasm` raw, gzip -9 and brotli quality 11 sizes: `node sizes.mjs [PATH]`.

Hosts: `hosts/wasmtime/viewcore.py` (`Core`, `Doc`, `Pool`) and `hosts/web/viewcore.js` + `worker.js` (protocol documented in
the worker's header). The module uses standard (exnref) WebAssembly exceptions: wasmtime needs `Config.wasm_exceptions`.
