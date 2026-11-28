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
| render process (stills) | `{python} -P -m cad.engine.render.service` | cannot draw: see Stills |

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
| 7 | 32-bit index type: numpy takes no 64-bit array for repeat counts or `reduceat` indices | `cad/engine/ranges.py:392-399,467` | Those counts are `np.intp`. The other sites are not audited: see What is open | part done |
| 8 | Builds in the caller's own Python (a lease) | `daemon.py:989` | Every script is built in the kernel's worker | done, tested |
| 9 | A program's own run: `cad run model.py` runs the program, which decides what it calls (law 11) | `cad_server/cli/run.py:447,464` | The program runs on the kernel's Python; that Python has no pipes to dial the door with, so its `cad run` holds a relay it connects to (`cad/engine/relay.py`, `cad/engine/client.py:96`) | done, tested, measured (4.7 s a warm run) |
| 10 | A script's own packages (`# /// script`, `--with`) | `cad_server/_internal/kernel_packages.py` | uv resolves them; what the kernel folder does not carry is installed, pure Python alone, in a folder of the cache on the program's path; one with native code is refused in one line naming it | done, tested |
| 11 | Stills: OCCT's viewer draws through OpenGL; the binding has no `OCP.OpenGl` | `cad/engine/render/context.py:69` | A kernel process refuses a picture at once (`KernelDrawsNothing`); see Stills | refusal done; drawing open |
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

**What draws today.** `cad/engine/render/` is 6,660 lines. A render process holds a document as the engine serves
it: the structure (JSON), each part's XBM2 mesh buffer (positions, normals, triangles by face, feature-edge
polylines), its paints (`faceColors`, `faceMaterials`), and draws a `snapshot.Still` to PNG bytes and a report.
Nothing in it models: `shapes.py` makes triangulation-only OCCT shapes of the buffers so that OCCT's viewer has
something to present.

| Part | Lines | Files | For a new renderer |
|---|---|---|---|
| OCCT drawing | 2,688 | `occt.py` (`Scene`, 1,494), `context.py` (the OpenGL canvas, 454), `finish.py` (materials as OCCT aspects, 275), `shapes.py` (252), `clip.py` (clip planes and capping, 213) | replaced |
| Partly OCCT | 1,455 | `service.py` (what a renderer holds, the frames, the camera's fitting: 2 imports of OCCT), `grid.py` (7), `drawing.py` (a DXF drawn: 4) | kept, their OCCT calls moved behind the seam |
| Plain Python | 2,517 | `board.py`, `schematic.py`, `text.py` (text by Pillow), `overlay.py` (ink over pixels), `explode.py`, `look.py` (the lights and the environment image), `board_refs.py`, `meshes.py` | kept as they are |

**The seam a renderer fills** is `occt.Scene`'s: made of `(structure, {key: XBM2 buffer}, size)`, then
`show(display, preview)` (the display modes: shaded, with or without edges, hidden parts, transparency),
`_clip(clip)` (a plane, its cut capped), `explode(amount)`, `grid(on)`, `frame(camera, projection, focal_length)`
(a preset, `az:el`, or a view's own camera: position, target, up; orthographic or perspective) answering the camera
used, `project(points)`, `placed_points()`, `box_corners()` and `rest_bounds()` (what `service.frame_camera` fits a
camera with, and what `overlay.py` places ink by), `annotate(annotation)` and `measure(marks)` (ribbons, polylines
and text quads in the scene), `backdrop(colour)` (or none: a picture on nothing, its alpha kept),
`preview_look()` (the Preview look: image-based lighting from `studio.hdr`, a floor, a contact shadow, tone
mapping) and `path_trace(out, samples)`, `painter()`/`save(out)` (the frame as RGBA pixels, `width` x `height`,
supersampled where the still asks), `close()`. It answers pixels and a report (size, camera, timings, unmeshed
faces, warnings).

**Three ways to fill it**, by cost:

1. *A software rasterizer in the view core.* It already holds the meshes and the structure. A z-buffered triangle
   rasterizer with per-face colour, feature edges as lines, one clip plane with capping, alpha, supersampling and a
   projected grid covers the display modes; the Preview look (image lighting, contact shadow, tone mapping) is a
   second step, and path tracing is not on offer. No new dependency, the same pictures on every computer, about the
   2,700 lines above to write again in C++ behind a `still` job, and every picture the tests pin drawn anew.
2. *The viewer's own renderer in a headless browser.* The page already draws the same structure and buffers with
   every mode, clip, explode, grid and annotation. A still is then a page loaded with the still as its state and its
   canvas read. Nothing to write in the renderer, and stills match what a person sees; it needs a browser on the
   computer (Chromium is 150-300 MB, or the person's own by the DevTools protocol) and software WebGL where there
   is no GPU.
3. *A native render process as a drawing-only dependency.* In a mixed install this works today
   (`places.drawing`, `base.py:418`: the render process runs in the native kernel the installation has beside it,
   and a worker's own picture is redrawn there from an exported `.xbf`: `snapshot.elsewhere`). It is not a
   destination: one kernel everywhere excludes it.

**An installation with no native kernel** refuses a still in one line (`base.NO_DRAWING`): "a still is drawn by
the native CAD kernel's OpenGL viewer, which this installation does not have: its kernel is the WebAssembly one.
See the model on its page instead (cad show), or choose the native kernel ... and ask again".

## How the kernel folder is obtained

By hand today: `node fetch.mjs PACKAGES_DIR` (every file checked against the sha256 `pins.json` names), then
`node make.mjs PACKAGES_DIR KERNEL_DIR`. Node 24 or later is found on `PATH` and refused in one line otherwise;
shipping one is a person's decision. Open: the engine making the folder itself on first need, as it makes the
native base, from a lock shipped with cad.

## What is open

1. Stills on an installation with no native kernel (above).
2. The engine making the kernel folder itself; `folder` optional in the setting.
3. 32-bit integers: numpy's default integer is 32 bits here. The sites that failed loudly in the suites are fixed;
   code that relied on a 64-bit default silently is not audited (the manufacturing checks and `ranges.py` use
   explicit 64-bit keys where they multiply cell indexes).
4. A model's body cannot listen on a socket, start a thread or a process: a script that does fails there.
5. Memory: a worker is 1.6-1.9 GB against a native worker's 0.45 GB, and the engine's caps are sized for the
   native one.
6. Windows, and a macOS worker's own memory reading.
7. This host has no test a CI job runs: the kernel folder is made by hand.
