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
| `zip.mjs` | The little of the zip format this needs (a wheel's entries, cad's source as one archive) |
| `page/` | A page that builds a parametric model in the tab and draws it through the view core: `node page/serve.mjs PACKAGES_DIR`, with `dist/viewcore.wasm` built (`../../scripts/core.sh`) and the repository's `npm ci` done (three.js) |

The set is about 70 MB on disk. One wheel, a material library's, is 90 MB of texture images no build reads:
`fetch.mjs` checks it as downloaded and keeps it without them.

## What it stands in for

`kernel.py` names each thing it had to do for cad's library to run here (`SHIMS`); a real port settles them in the
library:

- **`OCP` imported before `cad`.** This binding is one extension module, not a package of them. cad's lazy import of
  the kernel (`cad/_internal/lazy_kernel.py`) wraps `OCP`'s loader, and `from OCP.BRep import ...` then fails on a
  parent that is no package and has registered no submodule yet. Imported first, it is an ordinary loaded module.

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
