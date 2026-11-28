# viewcore (prototype)

The view core: one WebAssembly module, C++ on Open CASCADE Technology (OCCT), that reads a model's `.xbf` and
answers what the viewer reads of it: its structure, each part's mesh, an element's facts, a part's groups and
measures. The same file is meant to run in a page (a Worker) and in the engine (wasmtime), so both answer alike.

Status: a prototype on a branch, to measure size, start, speed, memory and parity with the engine. The local viewer
reads a model through it behind `?viewcore=N` (`packages/core/src/client/viewcore.js`); nothing else in cad, the
viewer or cad.fun uses it.

## What it does, and what stays in Python

In the core: reading an `.xbf` into the structure the engine serves (parts, their geometry keys, element names and
colours, materials, frames and declarations, placements, the tree, the mechanism as `kinematics`, animations,
parameters, the build closure), meshing a part by cad's rule into the XBM2 buffer, one element's facts and a
part's groups (what a pick asks), a part's whole table (what a view bundle holds), a part's measures, and the whole
document exported as `cad export` writes it: STEP (OCCT's STEP writer, then cad's settling of its bytes), STL, 3MF and
GLB (`src/exports.cpp`, `src/step.cpp`, `src/glb.cpp`). A part's canonical shape bytes can be opened by themselves
(`vc_open_shape`), as the engine's pool jobs hand a part over, and meshed to an export's own tolerance (`vc_mesh_at`). The viewer's Export asks the core for them behind
`?viewcore=N`; a DXF is still the engine's. It also draws a still in software (`vc_render`, `src/render.cpp`): the
picture cad's OpenGL renderer draws, from the same meshes, placements, materials, lights and camera, said as a scene
of plain numbers (`hosts/node/README.md`, "Stills"). No OCCT is called for it; `tools/render_parity.py` measures its
pictures against the OpenGL renderer's.

In cad's Python, as now: building and rebuilding models (build123d), writing the `.xbf`, the server and its
caches, sharing, the command line, and every integration (KiCad, MuJoCo, FEA, DFM, renders).

The rules are cad's: `packages/cad/src/cad/engine/mesh.py`, `mesh_format.py`, `document.py`, `mechanism.py` (read and
block), `kernel/bounds.py` and the writers in `export/` are the reference until the core replaces them. `include/viewcore.h` is the ABI.

## Layout

| Path | What |
|---|---|
| `include/viewcore.h` | The C ABI |
| `src/` | The core |
| `scripts/occt.sh` | OCCT's static libraries for WebAssembly, the subset the core links |
| `scripts/core.sh` | The core linked into `dist/viewcore.wasm` (the stills' rasterizer in WebAssembly's 128-bit SIMD, which Node, current browsers and wasmtime run) |
| `hosts/wasmtime/`, `hosts/web/` | Loading the module in Python (wasmtime) and in a page |
| `hosts/node/` | Loading it in Node, and a job server that answers the engine's pool jobs (meshing, tables, measures, a pick's facts, reading and exporting an `.xbf`, drawing a still) from it |
| `tools/` | The core built natively, and the checks that hold it to cad's own code: the pool jobs (`pool_parity.py`), the stills (`render_parity.py`) |
| `bench/` | Reference outputs from cad's engine, the comparison, the benchmarks |
| `licenses/` | OCCT's licence: the GNU LGPL 2.1 and the Open CASCADE exception, shipped beside the module |

## Licence

The core's code is MIT, as the repository. The module links OCCT 8.0.1, which is under the GNU LGPL 2.1 with the
Open CASCADE exception 1.0: whatever ships the module also ships those two texts (`licenses/`, OCCT's own files at tag
`V8_0_1`) and a notice that it uses Open CASCADE Technology, and offers OCCT's source (tag `V8_0_1`, unchanged) with
the build scripts here, from where the module is offered. It also links zlib (Emscripten's port, for the 3MF's
deflate), under the zlib licence, which asks nothing of a binary. `scripts/occt.sh` changes no OCCT source. `scripts/core.sh`
puts the texts beside the module in `dist/`; the viewer's build ships them with the notice beside it in `viewcore/`
(`apps/web/scripts/viewcoreAssets.mjs`), and refuses to ship the module without them.
