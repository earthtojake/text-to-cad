# The engine on the WebAssembly kernel: design

How cad's engine runs its kernel processes on the WebAssembly kernel (CPython and the CAD kernel's binding compiled
to WebAssembly, run by Node), what is in the way, and what each obstacle's answer is. "Done" below means in this
tree and held by a test or a measurement; "proposed" means not built. Paths are from the repository's root; line
numbers are this commit's.

## The seam

Every kernel process the engine starts runs "the kernel's Python", which one function answers:
`cad.engine.places.kernel()` (`packages/cad/src/cad/engine/places.py:736`), the server's
`cad_server._internal.base.kernel` behind it (`packages/cad/src/cad_server/_internal/base.py:344`). It returns
`{"python", "prefix", "path", "own"}`; the supervisor puts `python` where a service's command says `{python}`
(`packages/cad/src/cad_server/engine/supervisor.py:331`) and gives an `own` environment's process the engine's
folder on its import path (`supervisor.py:316`).

The WebAssembly kernel enters there and nowhere else. A **kernel folder** (`make.mjs` makes it: Pyodide's core, the
pinned packages unpacked with their bytecode, `kernel.json`, `bin/python`) has a launcher, `bin/python`, that takes
CPython's command line (`python.mjs`). Where a person's settings choose it, `base.kernel()` answers that launcher,
`own`, and one more word, `wasm`, which two places read: the pools (`serve._process_pool`,
`packages/cad/src/cad/engine/serve.py:500`) and the builds' leases (`Daemon.caller`,
`packages/cad/src/cad_server/engine/daemon.py:981`). The worker's protocol, its contract number and every request
are unchanged; the server, the client and the door stay on the native Python that runs them.

| Process | Command | On the WebAssembly kernel |
|---|---|---|
| worker (a script's builds, exports, measures) | `{python} -X faulthandler -P -m cad.engine.worker` | runs (done) |
| standby worker | the same, kernel loaded ahead | runs (done) |
| checks process | the worker's program | starts; see DFM below |
| meshing and reading pools | `multiprocessing` spawn pool | `kernel_pool.KernelPool` (done) |
| render process (stills) | `{python} -P -m cad.engine.render.service` | cannot: OpenGL (below) |
| a script's own process (`python model.py`, `cad run`) | the caller's Python | native, hands the build over (below) |

## The setting

A person's setting, in `settings.json` beside the engine's other settings, read by `base.wasm_kernel()`
(`base.py:379`):

    "kernel": {"kind": "wasm", "folder": "/absolute/path/to/a/kernel/folder"}

No section, or `{"kind": "native"}`, is the base as before. A folder that is no kernel folder is refused in one
line; nothing falls back to the kernel the person did not choose. No environment variable selects it. Proposed:
`folder` becomes optional once the engine makes the kernel folder itself (below), and `cad setup`/the settings page
write the section.

## Obstacles

| # | Obstacle | Where | Answer | State |
|---|---|---|---|---|
| 1 | The binding's `OCP` is one extension module, which the lazy import of the kernel wrapped: `from OCP.BRep import ...` asked for a submodule before the body had made it | `packages/cad/src/cad/_internal/lazy_kernel.py:83` | A kernel that is one extension module and no package is imported as ever; packages (the native binding, `build123d`) stay lazy. Native behaviour identical | done, tested |
| 2 | No threads: the worker's reader thread, which answers `where` during a build and lets the loop wait for idleness | `packages/cad/src/cad/engine/worker.py:980` | `places.THREADS` (`places.py:48`). Without threads the loop reads each request when it comes for it: `where` is answered between requests, and the idle collection runs at once after a request | done, tested |
| 3 | No threads: the timer that says "loading the CAD kernel" during a slow load | `worker.py:435` | Said after the load, if it took that long | done |
| 4 | No threads: the timer that sends a held progress frame | `packages/cad/src/cad/engine/progress.py:157` | The held frame goes with the next one | done, tested |
| 5 | No `multiprocessing`: the meshing and reading pools are spawn pools | `serve.py:489`, `serve.py:1487`, `serve.py:1499` | `KernelPool` (`packages/cad/src/cad/engine/kernel_pool.py`): the part of `ProcessPoolExecutor` the pools use, over kernel processes started as programs and spoken to in length-prefixed pickles on their streams. Capped at 2 processes a pool (each holds the whole kernel); a process is kept across jobs (`max_tasks_per_child` not honoured: a start costs seconds); a process ends when its input closes, which replaces `exit_with_parent`'s thread (`serve.py:637`) | done, tested |
| 6 | A worker's own memory: no `resource`, no `ps` | `worker.py:110`, `worker.py:368` | Read from `/proc/self/status` (the host mounts `/proc`) | done (Linux); macOS proposed: the host answers `process.memoryUsage().rss` |
| 7 | The platform's file facts: every process is pid 42, a file's inode is invented, its times are rounded to the millisecond, a new file ignores the process's mask, and so `shutil.rmtree` took every folder for a link | `python.mjs`, `bootstrap.py` | The host answers the real ones: pid; inode and device wherever a file's facts are read; nanosecond times by path, open file and open folder; `umask` | done, measured (a staged write left its folder behind before) |
| 8 | Builds in the caller's own Python (a lease): the caller's Python is native | `daemon.py:981` | On this kernel every script is built in the kernel's worker, whatever Python ran it. A script that needs a package the kernel folder lacks fails as a missing import | done, tested |
| 9 | A script as `__main__`: `python model.py` runs the script natively until the engine takes the build (`packages/cad/src/cad/engine/client.py`), then the worker runs it again as `__main__` | `client.py:472`, `worker.py:1026` | Unchanged where a native Python with `cad` exists: the client never loads a kernel (the lazy import). Proposed for an install with no native kernel: `cad run` sends the build order (the script's path) to the engine and runs nothing itself; `import build123d` in a bare native `python model.py` stays an import error there | part done |
| 10 | Scripts that name their own packages (`# /// script`) | `packages/cad/src/cad_server/_internal/extras.py:165`, `packages/cad/src/cad_server/cli/run.py:525` | Not answered. `cad run` makes a native environment for them and the build asks for a lease in it, which obstacle 8 ignores. Proposed: pure-Python requirements installed into a per-script folder put on the worker's path; a requirement with native code refused in one line naming it | open |
| 11 | The STEP reader is a child process of the process that reads | `packages/cad/src/cad/engine/reader.py:399` | Where the Python starts no process the parse is the reading process's own (`reader.py:409`), answered and refused in the reader process's words; the parse's working memory stays in the worker, which the server's ceiling on a worker's memory answers | done, tested |
| 12 | Analyses that start processes or threads inside a build: interference (guard and worker processes, threads), convex hulls (an outside program), DFM measured in a child with a watcher thread | `packages/cad/src/cad/build123d/_interference.py:656,703,728,741`, `packages/cad/src/cad/engine/hulls.py:242,261`, `packages/cad/src/cad/_internal/manufacturing.py:642,703` | Proposed: each already has an in-process path or needs one (`manufacturing.py:616` measures in the process where there is no interpreter to start); limits by time and memory then belong to the worker's supervisor. Outside programs stay native: asked of the server | open |
| 13 | Stills: OCCT's viewer draws through OpenGL on an X display; the binding has no `OCP.OpenGl` | `packages/cad/src/cad/engine/render/context.py:262`, `service.py` | Cannot run on this kernel. Options: (a) the render process stays on a native base where one is installed (it draws triangulations, it models nothing); (b) stills drawn by the viewer's own renderer in a headless browser; (c) refused in one line. A person's decision | open |
| 14 | Integrations that are other programs (KiCad, CalculiX, MuJoCo, Netgen, CoACD, `fc-match`) | `packages/cad/src/cad/kicad/`, `calculix/`, `mujoco/`, `netgen/_mesher.py:59`, `engine/render/text.py:76` | Not kernel processes: they run from native Python and stay there. One called from inside a build would need the server to run it | open |
| 15 | The build closure's libraries: the release of what a body runs on | `packages/cad/src/cad/engine/previous.py:130` | The WebAssembly binding's distribution is named there, so a build's closure differs from a native build's by design and nothing built on one kernel is taken as built on the other | done |
| 16 | Signals | none in a kernel process (`_interference.py:635` only, in its guard) | Nothing to do: a worker is stopped by closing its input or by the supervisor's kill of the host process | done |
| 17 | Named pipes, the door, sockets | `packages/cad/src/cad/engine/door.py`, `client.py:97` | Server and client only; a kernel process speaks on its standard streams, which the host passes as bytes | done |
| 18 | Start-up cost: the binding's 104 MB module and build123d's imports of scipy, scikit-learn, IPython | `make.mjs`, `bootstrap.py` | Packages unpacked once with bytecode and mounted; imports of packages a build calls nothing of are deferred to first use by a finder that imports the real package then (never a stub) | done, measured |
| 19 | Node 22's V8 holds over 4 GB for this kernel | `python.mjs:27` | Refused in one line under Node 24 | done |
| 20 | Windows | `python.mjs` (mounts), `make.mjs` (launcher) | The launcher is a POSIX shell script and the host mounts POSIX paths. Proposed: a `.cmd` launcher and drive mounts | open |

## Memory and time

Each kernel process is a whole host with its own copy of the kernel: 1.6-1.9 GB resident (Node 24), against a
native worker's ~0.45 GB. A served model holds a worker and, once meshed and read, up to four pool processes.
Proposed, in order of yield: one process serves both pools; the view core (below) takes the reading and meshing
for viewing, which removes the pools from the common path.

## How the kernel folder is obtained

Today by hand: `node make.mjs PACKAGES_DIR KERNEL_DIR`, from a folder holding Pyodide's core and the pinned
wheels. Proposed, a person's decision because it adds to what cad installs:

- **The packages**: a lock file shipped in cad naming each file by URL and SHA-256 (Pyodide's core and wheels from
  its release, the binding's wheel from where it is published, build123d and its pure-Python requirements from the
  index). The server's one making (`base.MAKING`, which makes the native base today) downloads them into the cache
  and makes the kernel folder there, with the same lines said, the same failure memory, the same refusal offline.
- **Node**: Node 24 or later found on `PATH`, else from an extra (`cad[wasm]`) that depends on a Node wheel; the
  one on the index (`nodejs-wheel-binaries`, about 60 MB) is unofficial. Nothing is added to cad's default install.

## What the view core should serve

The view core (the kernel's reading side compiled alone, run by wasmtime or a browser) reads a model's `.xbf` and
answers structure, meshes, element lookups and measures in a few megabytes and milliseconds. On an engine whose
kernel is this one, those requests are the pools' whole work: proposed, the server asks the view core for them
(by wasmtime, as a library in the server's process) and keeps kernel processes for what needs the modelling kernel:
builds, exports the core does not write, analyses. That is the change that makes the memory above tolerable, and
it needs the core's interface to take a document's bytes and answer the engine's own shapes of result; it is not
built here.
