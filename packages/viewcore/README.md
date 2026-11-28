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

The module needs WebAssembly's standard (exnref) exceptions and its 128-bit SIMD (the stills' rasterizer lights four
pixels at a time), with no fallback: Node 22 or later, and a browser or wasmtime with both; a host on an engine without
SIMD refuses in one line before compiling the module (SIMD alone: Node 16.4, Chrome 91, Firefox 89, Safari 16.4).

The rules are cad's: `packages/cad/src/cad/engine/mesh.py`, `mesh_format.py`, `document.py`, `mechanism.py` (read and
block), `kernel/bounds.py` and the writers in `export/` are the reference until the core replaces them. `include/viewcore.h` is the ABI.

## Layout

| Path | What |
|---|---|
| `include/viewcore.h` | The C ABI |
| `src/` | The core |
| `scripts/occt.sh` | OCCT's static libraries for WebAssembly, the subset the core links |
| `scripts/core.sh` | The core linked into `dist/viewcore.wasm` |
| `hosts/wasmtime/`, `hosts/web/` | Loading the module in Python (wasmtime) and in a page |
| `hosts/node/` | Loading it in Node, and a job server that answers the engine's pool jobs (meshing, tables, measures, a pick's facts, reading and exporting an `.xbf`, drawing a still) from it |
| `tools/` | The core built natively, and the checks that hold it to cad's own code: the pool jobs (`pool_parity.py`), the stills (`render_parity.py`) |
| `bench/` | Reference outputs from cad's engine, the comparison, the benchmarks |
| `licenses/` | OCCT's licence: the GNU LGPL 2.1 and the Open CASCADE exception, shipped beside the module |

## The kernel's own wheel (`scripts/ocp.sh`)

`hosts/pyodide` runs cad's build on OCP, the Python binding of OCCT, built for Pyodide. `scripts/ocp.sh` builds that
wheel from OCCT's source and OCP's generated binding sources, everything it fetches pinned in
`scripts/kernel-pins.json` (URL and sha256, or repository and commit): a bump of OCCT, OCP or Pyodide edits that file
only.

```bash
scripts/ocp.sh EMSDK_DIR OCCT_SRC XBUILDENV_DIR scripts/ocp-modules.txt WORK_DIR   # the wheel in WORK_DIR/dist/
```

`scripts/ocp-modules.txt` lists the OCP submodules to bind: those cad, build123d, ocpsvg and ocp_gordon import, and
what their bindings need to import. Importing one left out raises `ModuleNotFoundError` naming it and the list. `all`
builds every module, the same steps. OCCT is compiled as released but for one file: `PLib.cxx` gets
`scripts/patches/occt-plib-max-opt-dim.patch` (its polynomial evaluation stays on the fixed-size path up to dimension
48; results bit-identical) and is compiled with WebAssembly SIMD; `--plib-stock` leaves both out. The module therefore
needs an engine with WebAssembly SIMD (Chrome 91, Firefox 89, Safari 16.4, Node 16.4 and later). A cold build takes
about an hour on 4 cores and needs about 7 GB of memory. The wheel names no directory of the machine that built it
(each compile maps its directories to fixed names), but two builds are not the same bytes: the compiler nests a few
exception blocks differently from run to run, in code that does the same. The file to trust is the one whose sha256
the lock names. `ocp.sh --help` has the rest.

Text: OCCT reads fonts with FreeType, built in. Under Emscripten OCCT finds fonts only in `/usr/share/fonts`,
`/usr/local/share/fonts` and `/system/fonts` (no fontconfig), plus what build123d registers (its bundled single-line
font). Where the host mounts the machine's filesystem (the engine's kernel host) that is the machine's own fonts, as
natively; in a page there are none, and a font asked for by name falls back to build123d's single-line font.

The wheel contains OCCT (GNU LGPL 2.1 with the Open CASCADE exception 1.0), OCP's generated sources (Apache-2.0),
pybind11 (BSD-3-Clause), fmt and RapidJSON (MIT), and FreeType (the FreeType License; with its bundled zlib, zlib
licence); their texts are in its `.dist-info/licenses`. Whatever ships it offers OCCT's source at the pinned tag with
the patch and these scripts, and says in its documentation: "Portions of this software are copyright © 2024 The
FreeType Project (www.freetype.org). All rights reserved."

## Licence

The core's code is MIT, as the repository. The module links OCCT 8.0.1, which is under the GNU LGPL 2.1 with the
Open CASCADE exception 1.0: whatever ships the module also ships those two texts (`licenses/`, OCCT's own files at tag
`V8_0_1`) and a notice that it uses Open CASCADE Technology, and offers OCCT's source (tag `V8_0_1`, unchanged) with
the build scripts here, from where the module is offered. It also links zlib (Emscripten's port, for the 3MF's
deflate), under the zlib licence, which asks nothing of a binary. `scripts/occt.sh` changes no OCCT source. `scripts/core.sh`
puts the texts beside the module in `dist/`; the viewer's build ships them with the notice beside it in `viewcore/`
(`apps/web/scripts/viewcoreAssets.mjs`), and refuses to ship the module without them.
