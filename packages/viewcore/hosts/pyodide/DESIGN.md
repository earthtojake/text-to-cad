# The engine on the WebAssembly kernel: design

How cad's engine runs on one kernel compiled to WebAssembly, what was in the way, and what each obstacle's answer
is. "Done" means in this tree and held by a test or a measurement; "open" means not built. Paths are from the
repository's root (`cad/` is `packages/cad/src/cad/`, `cad_server/` is `packages/cad/src/cad_server/`); line
numbers are this commit's. The target is an installation with no native kernel; a mixed one (a native kernel
beside it) keeps working, and is what the tests run in.

## Two programs

| Program | What it is | Ready | Memory | What the engine asks of it |
|---|---|---|---|---|
| The kernel's Python (`KERNEL/bin/python`: `python.mjs`) | CPython and the kernel's whole binding under Node 24+ | 9-10 s with the kernel loaded | 1.6-1.9 GB | Builds, exports, checks, a program's own run, a foreign file's read |
| The view core's job server (`KERNEL/bin/viewcore`: `../node/serve.mjs`) | The kernel's reading side alone under Node 22+ | 0.2 s | 0.1-0.25 GB | A part's mesh, table, measures and facts; an `.xbf` read |

Both live in a **kernel folder** (`make.mjs` makes it: Pyodide's core, the pinned packages unpacked with their
bytecode, the host's own files, the view core where one is built, `kernel.json`). It names nothing outside itself
but the Node it runs.

## The seam

Every kernel process the engine starts runs "the kernel's Python", which one function answers:
`cad.engine.places.kernel()` (`cad/engine/places.py:759`), the server's `base.kernel` behind it
(`cad_server/_internal/base.py:344`). Where a person's settings choose the WebAssembly kernel, it answers the
kernel folder's launcher and two more words:

- `wasm`, read by the supervisor, which gives its processes the engine's folder as it gives an `own` environment's
  (`cad_server/engine/supervisor.py:313`); by the builds' leases (`cad_server/engine/daemon.py:989`); and by the
  pools (`cad/engine/serve.py:489`). It is never `own`: its libraries are not the server's, so what measures a
  manufacturing check there is what its processes say (`cad_server/engine/checks.py:394`).
- `core`, the view core's launcher, where the folder carries one: the pools are then a `CorePool`
  (`cad/engine/core_pool.py`, `serve.py:510`).

The worker's protocol, its contract number and every request are unchanged.

| Process | Command | On the WebAssembly kernel |
|---|---|---|
| worker, standby, checks process | `{python} -X faulthandler -P -m cad.engine.worker` | the kernel's Python (done) |
| meshing and reading pools | a `multiprocessing` spawn pool | the view core's job server; a kernel process for what it does not answer (done) |
| a program (`cad run model.py`) | the environment's Python | the kernel's Python, asking the engine through a relay (done) |
| render process (stills) | `{python} -P -m cad.engine.render.service` | the installation's own Python, drawing with the view core (`--core`): see Stills (done) |

## The setting

In `settings.json` beside the engine's other settings, read by `base.wasm_kernel()` (`base.py:379`):

    "kernel": {"kind": "wasm", "folder": "/absolute/path/to/a/kernel/folder"}

No section, or `{"kind": "native"}`, is the native base as before. A folder that is no kernel folder is refused in
one line; nothing falls back to the kernel the person did not choose. The suites run on it by
`scripts/test/test-python.sh --kernel FOLDER`, which gives each test's state folder that setting.

## Obstacles

| # | Obstacle | Where | Answer | State |
|---|---|---|---|---|
| 1 | The binding's `OCP` is one extension module, which the lazy import of the kernel wrapped | `cad/_internal/lazy_kernel.py:83` | One extension module and no package is imported as ever; native behaviour identical | done, tested |
| 2 | No threads: the worker's reader thread, the kernel-load notice, the progress timer | `cad/engine/worker.py:435,949,980`, `cad/engine/progress.py:158` | `places.THREADS` (`places.py:48`): the loop reads each request in turn, `where` is answered between requests, no progress frame is held | done, tested |
| 3 | No `multiprocessing`: the pools | `serve.py:489` | `CorePool` for the jobs the view core answers; `KernelPool` (`cad/engine/kernel_pool.py`, capped at 2) for the rest | done, tested, measured |
| 4 | Threads and processes inside a build or a check: the mesher's inline thread, interference's crew and guard, a check's watched child, the STEP reader process | `serve.py:749,759`, `cad/build123d/_interference.py:702`, `cad/_internal/manufacturing.py:620`, `cad/engine/reader.py:409` | Each runs in the one thread where `places.THREADS` is false; a check's time is kept between pairs, and the limits on a whole process are its supervisor's | done, tested |
| 5 | CoACD (convex hulls) is native code with no WebAssembly wheel | `cad/engine/hulls.py:302` | Refused in one line naming the platform; nothing is started | done, tested |
| 6 | The platform's own answers where the system's are wanted: pid 42, invented inodes, times to the millisecond, no umask, `os.chdir` moving the program and not the process, no `.pth`/`sitecustomize`, no sockets | `python.mjs`, `bootstrap.py` | The host answers as CPython on the computer does; sockets that connect are the host's (a thread of its own does the I/O) | done, measured |
| 7 | 32-bit index type: numpy takes no 64-bit array for `repeat` counts, `reduceat` indices, `choose` or `put` (it does for indexing, `take` and `bincount`), and `astype(int)` is 32 bits | `cad/engine/ranges.py`, `cad/engine/render/shapes.py`, `cad/build123d/_dfm_brep.py`, `_dfm_cnc_model.py`, `_dfm_printing.py` | Those counts are `np.intp`; packed part owners (`part << 20`) are `np.int64`. Audited: every `repeat`/`reduceat`/`choose`/`put` site of `cad/`, and the library's numpy-heavy tests run inside the kernel's own Python | done, tested |
| 8 | Builds in the caller's own Python (a lease) | `daemon.py:989` | Every script is built in the kernel's worker | done, tested |
| 9 | A program's own run: `cad run model.py` runs the program, which decides what it calls (law 11) | `cad_server/cli/run.py:447,464` | The program runs on the kernel's Python; that Python has no pipes to dial the door with, so its `cad run` holds a relay it connects to (`cad/engine/relay.py`, `cad/engine/client.py:96`) | done, tested, measured (4.7 s a warm run) |
| 10 | A script's own packages (`# /// script`, `--with`) | `cad_server/_internal/kernel_packages.py` | uv resolves them; what the kernel folder does not carry is installed, pure Python alone, in a folder of the cache on the program's path; one with native code is refused in one line naming it | done, tested |
| 11 | Stills: OCCT's viewer draws through OpenGL; the binding has no `OCP.OpenGl` | `cad/engine/render/context.py:69` | A kernel process refuses a picture at once (`KernelDrawsNothing`); the render process draws it with the view core's software renderer (`cad/engine/render/core.py`); see Stills | done, tested, measured |
| 12 | Integrations that are other programs (KiCad, CalculiX, MuJoCo, Netgen, Blender) | `cad/kicad/`, `calculix/`, `mujoco/`, `netgen/` | Not kernel processes: `cad run` gives a program that uses one its own native environment, as before | unchanged |
| 13 | The build closure's libraries | `cad/engine/previous.py:130` | The WebAssembly binding's distribution is named: nothing built on one kernel is taken as built on the other | done |
| 14 | Start-up: the binding's 104 MB module, build123d's imports of scipy, scikit-learn, IPython; Node 22 holding over 4 GB | `make.mjs`, `bootstrap.py`, `python.mjs:27` | Packages unpacked once with bytecode; imports a build calls nothing of deferred to first use by a finder that imports the real package then; Node 24 required, refused in one line under it | done, measured |
| 15 | Windows | `python.mjs` (mounts), `make.mjs` (launchers) | The launchers are POSIX shell scripts and the host mounts POSIX paths | open |

## The pools' job seam

`serve.py`'s pool jobs, as `CorePool` asks them of the view core's job server (`core_pool.request`), and what each
answers. A frame, both ways: 8 bytes, the length of the rest; 4 bytes, the header's length; the header, one JSON
object; the payloads end to end, their lengths the header's `payloads`.

| The engine's job | Arguments | The core's job | Answer (the engine's own shape) |
|---|---|---|---|
| `_timed(data, parallel)` | a part's shape bytes | `mesh`, the bytes | `(XBM2 buffer, {ordinal: why unmeshed}, seconds)` |
| `_table(key, data, unmeshed, measure)` | geometry key, shape bytes, unmeshed ordinals | `table {key, unmeshed, measure}`, the bytes | `(table JSON bytes, measures or None)` |
| `_measured(batch)` | `[(key, shape bytes)]` | `measured {keys}`, each part's bytes | `[(key, measures)]` |
| `_topology_fact(key, data, method, args)` | `face`, `edge`, `vertex`, `groups`, `elements`, `measured` | `fact {key, method, args}`, the bytes | the JSON value |
| `_read_document(path)` for an `.xbf` | the file's path | `read_xbf {path}` | `(structure, (mtime_ns, size), {key: shape bytes}, {key: name})`: the core's structure with `path` (resolved), `version` and tuples for colours put in, `tessellation` and `closure` taken out |
| `_ready()`, `int` (a pool's warm-up) | | `about` | `True`, `0` |
| `_pose_structure`, `_read_foreign` (STEP, DXF, a robot), a live shape | | none | a kernel process's (`KernelPool`), started for the first of them |

What the core refuses is the job's `ValueError` in the core's words; a process that dies fails its job alone
(`BrokenProcessPool`) and the next job starts another. Exports stay the worker's: the engine's export path has
decorators, tolerance options and motion rules the core's `export` job does not take.

Measured, a 249-part model served (`first mesh` is a page's first part): 13.1 s to serve and 12.3 s to the first
mesh with three kernel processes holding 5,155 MB, against 1.1 s and 1.0 s with five job servers holding 802 MB.

## Stills

A still is the render process's, as on the native kernel: a kernel process refuses one at once
(`render.context.KernelDrawsNothing`) and the client has the render process draw an `.xbf` the engine exports
(`snapshot.elsewhere`). Where the kernel is the WebAssembly one, `base.drawing` (`cad_server/_internal/base.py`)
answers the installation's own Python -- numpy and Pillow, no kernel: a render process models nothing -- and the
kernel folder's view core, which the supervisor hands the process as `--core` (`cad_server/engine/supervisor.py`).
Its `Held` then draws with `render.core.CoreScene`: `occt.Scene` with the OCCT calls taken out, so both renderers
take one set of decisions -- what is shown and how (`Scene.plan`, `finish.finish`), the camera (`Scene.frame`,
`service.frame_camera`, kept by `Scene.aim`), the clip (`clip.cut`, `clip.cap_colour`), the grid (`grid.drawn`), the
ink's ribbons, lines and text quads (`Scene._ink`, `_line`, `_quad`) -- and the core's are written as the `render`
job's scene (`../node/README.md`, "The scene") each time a frame is asked, each part's mesh crossing the pipe once
by its key. The painter (text marks laid as three lays them, Measure's marks) is the same Python, a text mark's bare
pixels a frame drawn without the marks. Preview is `Scene._studio`, `_studio_backdrop` and the painter's tone
mapping with the core under them: the studio's floor and shadow are `Scene._stage`'s triangles, the shadow baked
from the core's `"depth"` pictures squeezed by the view's aspect as OCCT squeezes them (`CoreScene._depth`), the
backdrop the one row of its picture OCCT shows down the frame, the key light casting its shadow map. A GLB's base
colour texture is the faces' `texels` and `texture`; a DXF's drawing is `drawing.Sheet`'s fills and lines.

Not drawn by the core yet, each refused in one line (`core.NOT_YET`): the path tracer, Preview of a textured part,
Preview seen from under its floor. A foreign file whose reader needs the kernel (a GLB, a robot's primitives, a
DXF's splines) is refused where the installation has none. A kernel folder with no view core refuses every still
(`base.NO_DRAWING`).

Measured (juno, 249 parts and 363 instances, 1600 x 1200, solid, through `cad snapshot` on this kernel): 6.7 s for
the first picture (serving and meshing included; 16.4 s natively with its Xvfb and kernel load), 0.66 s warm against
0.53-0.59 s natively, the core's frame 0.40 s at 8 samples a pixel against OpenGL's 0.40 s (llvmpipe, 4); the two
pictures differ by a mean 0.3 levels, 0.26% of the pixels by over 32 levels and 0.035% once a line a pixel aside is
allowed for. Preview of the material fixture at 800 x 600, the core against OpenGL in one process: a mean 0.33-0.45
levels, under 0.03% of pixels over 32 levels. `tests/python/packages/cad/engine/test_render.py` draws its goldens with the core where the suite runs
on this kernel (`scripts/test/test-python.sh --kernel`); `test_render_core.py` holds the scene and the job's
traffic against a stand-in server wherever the suite runs.

## How the kernel folder is obtained

With no `folder` in the setting the engine makes it on first need (`cad_server/_internal/kernel_folder.py`): every
file the lock shipped with cad names (`kernel_host/lock.json`) downloaded into the cache and checked against its
sha256, the wheels unpacked, cad's host put beside them, a launcher written for the Node 24+ on `PATH`. It is made
by the engine's one making, as the native base is (`base.KERNEL_MAKING`, a `Making`): one making for every asker,
its lines said to each request that waits on it, a failure remembered and told at once until it can have cleared;
`cad run` asks the server for it over the door (`{"op": "base", "key"}`) as it asks for the base. Where the lock
names the view core (`viewcore`: one archive of `core/` as `make.mjs` lays it out) it is unpacked into the folder
with `bin/viewcore`; the lock names none yet -- publishing that archive with a release is the view core's owners'
step -- so an engine-made folder's pools are kernel processes and its stills are refused (`base.NO_DRAWING`).
By hand: `node fetch.mjs PACKAGES_DIR`, then `node make.mjs PACKAGES_DIR KERNEL_DIR` (with the view core where one
is built), named in the setting's `folder`.

## What is open

1. Stills on the view core: the path tracer, Preview of a textured part, Preview from under its floor (above).
2. The view core's archive in the lock (above): until a release publishes one, an engine-made folder draws no still.
3. Defects of the binding itself, found running the library's tests inside the kernel's Python: OCCT's glTF reader
   traps ("memory access out of bounds": a GLB read, `formats/glb.py`), and one sheet-metal fixture's division traps
   ("unreachable"). Both end the process; neither is cad's code.
4. A model's body cannot listen on a socket, start a thread or a process: a script that does fails there.
5. Memory: a worker is 1.6-1.9 GB against a native worker's 0.45 GB, and the engine's caps are sized for the
   native one.
6. Windows, and a macOS worker's own memory reading.
7. This host has no test a CI job runs: the kernel folder is made by hand.
