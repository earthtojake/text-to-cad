# hosts/pyodide (prototype)

cad's build on a WebAssembly kernel: a model's script built by cad's own `cad.engine.build.build` (the function an
engine worker calls) inside Pyodide, CPython compiled to WebAssembly, with the CAD kernel's Python binding built for
it (OCP on OCCT 8.0.1, the release cad's native kernel is) and build123d. The `.xbf` it writes is handed on as bytes,
which the view core reads (`../web`, `../wasmtime`): building, reading, meshing and exporting a model then need no
native kernel, in Node or in a browser tab.

Nothing in cad, the viewer or the share service uses this. It is here to measure what such a build tier costs and
what cad's library needs changed to run on it.

## Files

| File | What |
|---|---|
| `pins.json` | The pinned set: Pyodide's core and one wheel per package, each with its URL and sha256 |
| `fetch.mjs` | Downloads the set into a folder and checks every file: `node fetch.mjs PACKAGES_DIR` |
| `kernel.mjs`, `kernel.py` | The kernel loaded (Node or a Worker) and the harness cad's build runs under: `build`, `withValues`, `preview` |
| `build.mjs` | A script built in Node: `node build.mjs PACKAGES_DIR SCRIPT.py [--out DIR]` |
| `make.mjs` | A kernel folder made of the set: every wheel unpacked with its bytecode, and a `bin/python` the engine can start: `node make.mjs PACKAGES_DIR KERNEL_DIR [--node PATH]` |
| `python.mjs`, `bootstrap.py` | That `python`: CPython's command line (`-m`, `-c`, a script) on the WebAssembly kernel, with the real filesystem, streams, environment and process id, so the engine's own kernel programs (`cad.engine.worker`, `cad.engine.kernel_pool`) run in it unchanged |
| `zip.mjs` | The little of the zip format this needs (a wheel's entries, cad's source as one archive) |
| `page/` | A page that builds a parametric model in the tab and draws it through the view core: `node page/serve.mjs PACKAGES_DIR`, with `dist/viewcore.wasm` built (`../../scripts/core.sh`) and the repository's `npm ci` done (three.js) |

The set is about 70 MB on disk. One wheel, a material library's, is 90 MB of texture images no build reads:
`fetch.mjs` checks it as downloaded and keeps it without them.

## The engine on this kernel

With `"kernel": {"kind": "wasm", "folder": KERNEL_DIR}` in a person's `settings.json`, cad's server starts its kernel
processes with `KERNEL_DIR/bin/python`: a build's worker, the standby, and the meshing and reading pools
(`cad.engine.kernel_pool`, which stands in for the spawn pools this Python cannot be part of). The script is run
natively as ever; its build, its `.xbf`, its meshes and its facts come from WebAssembly. Without the setting nothing
changes. `DESIGN.md` says what each kernel process needs to run here and what is not there yet.

Starting (measured on a loaded four-core machine, Node 24): ready to build in 9 to 10 s and 1.7 GB of the process's
memory, against 30 to 34 s and 4.3 GB for the first prototype (Node 22, wheels unzipped at each start, every import
done at once); the `.xbf` of each sample script is the same bytes either way. A start unzips nothing (the folder is
mounted as it stands), compiles no Python (bytecode is beside each module), and imports scikit-learn, scipy and
IPython only if the program uses them (`bootstrap.py`: a build imports them through build123d and calls none).
Node 24 or later is required: Node 22's engine holds over 4 GB for this kernel.

## What it stands in for

`kernel.py` names each thing it had to do for cad's library to run here (`SHIMS`); a real port settles them in the
library:

- **`OCP` imported before `cad`** (kernel.py, the in-page harness). This binding is one extension module, not a
  package of them, which cad's lazy import of the kernel did not expect; the library now imports such an `OCP` as
  ever (`cad/_internal/lazy_kernel.py`), so the engine's own programs need no stand-in.

And what the harness goes around rather than through:

- **A script run as a program** (`python model.py`, its `if __name__ == "__main__": model()`) asks cad's server to
  build it, over a socket (`cad/engine/client.py`). There is no server here: the harness calls the build the server's
  worker would.
- **The build closure** a document records names the release and the kernel's distribution, read from installed
  metadata (`cad/engine/previous.py`): the library's source is unpacked here, not installed, so the release reads
  `0+unknown`, and the kernel's wheel goes by another distribution name, so `libs.OCP` is absent. A document built
  here is therefore never taken as built by a native engine, nor the other way.

Not tried: declared exports written by the build's own writers, a model that reads a STEP, `@eng_drawing`, any
integration that is another program (KiCad, MuJoCo, the meshers), and a script that names its own packages.
