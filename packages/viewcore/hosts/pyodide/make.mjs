#!/usr/bin/env node
// make.mjs: a kernel folder made of what fetch.mjs downloaded (prototype): the WebAssembly kernel laid out so a
// start reads it as it stands, and a `python` the engine can start.
// Usage: node make.mjs PACKAGES_DIR KERNEL_DIR [--node PATH] [--core VIEWCORE_DIR] [--live]
//   KERNEL_DIR/pyodide/                           Pyodide's core
//   KERNEL_DIR/lib/pythonX.Y/site-packages/       every pinned wheel unpacked, each module's bytecode beside it
//   KERNEL_DIR/host/                              python.mjs and bootstrap.py, as they stood when it was made
//   KERNEL_DIR/bin/python                         that python.mjs under the Node named (default: the one running
//                                                 this); with --live, cad's own python.mjs as it stands instead
//   KERNEL_DIR/core/, KERNEL_DIR/bin/viewcore     the view core and its job server (hosts/node/serve.mjs) under
//                                                 that Node, where VIEWCORE_DIR (default: this package) has a
//                                                 built module (dist/viewcore.wasm); the engine's pools use it
//   KERNEL_DIR/kernel.json                        what it was made of: Pyodide's release, the pins' digest, the
//                                                 packages whose import is deferred to their first use
// The folder names nothing outside itself but the Node it runs: it can be moved by making it again, never copied.
// A start then unzips nothing and compiles no Python (measured: half the time to ready). The folder is made beside
// its place and moved there whole, so one that exists is complete.
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import zlib from "node:zlib";

import { readEntries } from "./zip.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
// The kernel's host as cad ships it: its Python's stand-in, what that runs first, and the lock of what a kernel
// folder is made of.
const HOST = path.join(HERE, "..", "..", "..", "cad", "src", "cad_server", "_internal", "kernel_host");
const args = process.argv.slice(2);
const option = (name) => { const at = args.indexOf(name); return at < 0 ? null : args.splice(at, 2)[1]; };
const node = option("--node") || process.execPath;
const viewcore = path.resolve(option("--core") || path.join(HERE, "..", ".."));
const live = args.includes("--live") && args.splice(args.indexOf("--live"), 1).length > 0;
const [packages, target] = args;
if (!packages || !target) { console.error("usage: node make.mjs PACKAGES_DIR KERNEL_DIR [--node PATH]"); process.exit(2); }

const pinsText = fs.readFileSync(path.join(HOST, "lock.json"));
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
fs.mkdirSync(path.join(staged, "host"));
for (const name of ["python.mjs", "bootstrap.py"]) fs.copyFileSync(path.join(HOST, name), path.join(staged, "host", name));
fs.writeFileSync(launcher, `#!/bin/sh\nCAD_KERNEL_HOME=${JSON.stringify(final)} exec ${JSON.stringify(node)} `
  + `${JSON.stringify(path.join(live ? HOST : path.join(final, "host"), "python.mjs"))} "$@"\n`);
fs.chmodSync(launcher, 0o755);
// The view core, laid out as its hosts find each other (hosts/node beside hosts/web, the module in dist).
const CORE = ["hosts/node/serve.mjs", "hosts/node/viewcore.mjs", "hosts/web/viewcore.js", "dist/viewcore.wasm"];
const core = CORE.every((name) => fs.existsSync(path.join(viewcore, name)));
if (core) {
  const texts = fs.readdirSync(path.join(viewcore, "dist")).filter((name) => /LICENSE|EXCEPTION/.test(name)).map((name) => `dist/${name}`);
  for (const name of [...CORE, ...texts]) {
    fs.mkdirSync(path.dirname(path.join(staged, "core", name)), { recursive: true });
    fs.copyFileSync(path.join(viewcore, name), path.join(staged, "core", name));
  }
  fs.writeFileSync(path.join(staged, "core", "package.json"), '{"type": "module"}\n');  // its .js files are modules
  const serve = path.join(staged, "bin", "viewcore");
  fs.writeFileSync(serve, `#!/bin/sh\nexec ${JSON.stringify(node)} ${JSON.stringify(path.join(final, "core", CORE[0]))} "$@"\n`);
  fs.chmodSync(serve, 0o755);
}
fs.writeFileSync(path.join(staged, "kernel.json"), JSON.stringify({
  schema: "cad wasm kernel/1",
  pyodide: pins.pyodide,
  python,
  pins: createHash("sha256").update(pinsText).digest("hex"),
  node,
  // Packages a build imports and seldom calls (bootstrap.py: bound at import, imported for real at first use).
  deferred: pins.deferred ?? [],
  core: core ? createHash("sha256").update(fs.readFileSync(path.join(viewcore, "dist", "viewcore.wasm"))).digest("hex") : null,
}, null, 1) + "\n");
fs.rmSync(final, { recursive: true, force: true });
fs.renameSync(staged, final);
console.log(`${final}: ${pins.packages.length} packages, ${files} files, ${compiled} modules compiled, Python ${python}`
  + (core ? ", the view core" : ", no view core (none built)"));
