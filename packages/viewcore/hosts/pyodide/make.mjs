#!/usr/bin/env node
// make.mjs: a kernel folder made of what fetch.mjs downloaded (prototype): the WebAssembly kernel laid out so a
// start reads it as it stands, and a `python` the engine can start.
// Usage: node make.mjs PACKAGES_DIR KERNEL_DIR [--node PATH]
//   KERNEL_DIR/pyodide/                           Pyodide's core
//   KERNEL_DIR/lib/pythonX.Y/site-packages/       every pinned wheel unpacked, each module's bytecode beside it
//   KERNEL_DIR/bin/python                         python.mjs under the Node named (default: the one running this)
//   KERNEL_DIR/kernel.json                        what it was made of: Pyodide's release, the pins' digest, the
//                                                 packages whose import is deferred to their first use
// A start then unzips nothing and compiles no Python (measured: half the time to ready). The folder is made beside
// its place and moved there whole, so one that exists is complete.
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import zlib from "node:zlib";

import { readEntries } from "./zip.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
// Packages a build imports and seldom calls (bootstrap.py: bound at import, imported for real at their first use).
// Each costs most of a second or more to import here; build123d imports them at the top of modules a build uses.
const DEFERRED = ["sklearn", "scipy", "IPython", "requests", "pygments", "prompt_toolkit", "fontTools"];

const args = process.argv.slice(2);
const option = (name) => { const at = args.indexOf(name); return at < 0 ? null : args.splice(at, 2)[1]; };
const node = option("--node") || process.execPath;
const [packages, target] = args;
if (!packages || !target) { console.error("usage: node make.mjs PACKAGES_DIR KERNEL_DIR [--node PATH]"); process.exit(2); }

const pinsText = fs.readFileSync(path.join(HERE, "pins.json"));
const pins = JSON.parse(pinsText);
const staged = `${path.resolve(target)}.making-${process.pid}`;
fs.rmSync(staged, { recursive: true, force: true });
fs.mkdirSync(path.join(staged, "pyodide"), { recursive: true });
for (const file of pins.core) fs.copyFileSync(path.join(packages, "pyodide", file.file), path.join(staged, "pyodide", file.file));

// The Python this Pyodide is, for the folder's name: asked of it once.
const { loadPyodide } = await import(pathToFileURL(path.join(staged, "pyodide", "pyodide.mjs")).href);
const pyodide = await loadPyodide({ indexURL: path.join(staged, "pyodide") + path.sep });
const python = pyodide.runPython("import sys; f'{sys.version_info.major}.{sys.version_info.minor}'");
const site = path.join(staged, "lib", `python${python}`, "site-packages");
fs.mkdirSync(site, { recursive: true });

let files = 0;
for (const entry of pins.packages) {
  const wheel = new Uint8Array(fs.readFileSync(path.join(packages, "wheels", entry.file)));
  for (const item of readEntries(wheel)) {
    if (item.name.endsWith("/")) continue;
    const to = path.join(site, ...item.name.split("/"));
    if (!to.startsWith(site + path.sep)) throw new Error(`${entry.file}: ${item.name} leaves the folder`);
    fs.mkdirSync(path.dirname(to), { recursive: true });
    fs.writeFileSync(to, item.method === 0 ? item.data : zlib.inflateRawSync(item.data));
    files += 1;
  }
}

// Each module's bytecode beside it, written by the Python that will read it.
const FS = pyodide.FS;
const mounted = pyodide.runPython("import site; site.getsitepackages()[0]");
FS.mount(FS.filesystems.NODEFS, { root: site }, mounted);
const compiled = pyodide.runPython(`
import compileall, io, contextlib
with contextlib.redirect_stdout(io.StringIO()):
    compileall.compile_dir(${JSON.stringify(mounted)}, quiet=2, workers=1)
import pathlib
sum(1 for _ in pathlib.Path(${JSON.stringify(mounted)}).rglob("*.pyc"))
`);

fs.mkdirSync(path.join(staged, "bin"));
const final = path.resolve(target);
const launcher = path.join(staged, "bin", "python");
// The launcher names its own folder as it will stand, the Node it runs and the host beside this file.
fs.writeFileSync(launcher, `#!/bin/sh\nCAD_KERNEL_HOME=${JSON.stringify(final)} exec ${JSON.stringify(node)} `
  + `${JSON.stringify(path.join(HERE, "python.mjs"))} "$@"\n`);
fs.chmodSync(launcher, 0o755);
fs.writeFileSync(path.join(staged, "kernel.json"), JSON.stringify({
  schema: "cad wasm kernel/1",
  pyodide: pins.pyodide,
  python,
  pins: createHash("sha256").update(pinsText).digest("hex"),
  node,
  deferred: DEFERRED,
}, null, 1) + "\n");
fs.rmSync(final, { recursive: true, force: true });
fs.renameSync(staged, final);
console.log(`${final}: ${pins.packages.length} packages, ${files} files, ${compiled} modules compiled, Python ${python}`);
