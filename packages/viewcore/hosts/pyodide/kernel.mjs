// kernel.mjs: cad's build on a WebAssembly kernel (prototype). Pyodide (CPython compiled to WebAssembly) with the
// CAD kernel's Python binding built for it (OCP on OCCT 8.0.1), build123d, and cad's own library source: a model's
// script is built by cad's own build (`cad.engine.build.build`, what an engine worker calls) in this one process,
// and its `.xbf` handed back as bytes, which the view core reads (`../web`, `../wasmtime`). The same module in
// Node and in a browser Worker. What the library needs changed to run here is in kernel.py, each with its reason.
//
//   const kernel = await loadKernel({ base, pins, cad, kernelPy });
//   const { xbf, reports } = await kernel.build({ name: "bracket.py", text, files });
//
// `base`: where fetch.mjs put the packages (a URL ending in "/": file: in Node, http(s): in a page). `pins`:
// pins.json, parsed. `cad`: a zip of the library's source (`sourceZip` below, or one a server made), its packages at
// the top. `kernelPy`: kernel.py's text.

const NODE = typeof process !== "undefined" && !!process.versions?.node && typeof importScripts === "undefined";

async function local(url) {
  // Node's Pyodide loads a package from a path; a page's from a URL.
  if (!NODE || !url.startsWith("file:")) return url;
  const { fileURLToPath } = await import("node:url");
  return fileURLToPath(url);
}

/**
 * Start the kernel: Pyodide, the pinned packages, cad's source, and the harness. `timings` (seconds): start (the
 * interpreter), packages (unpacked), imports (the kernel, build123d and cad's build imported once).
 */
export async function loadKernel({ base, pins, cad, kernelPy, stdout = () => {}, stderr = () => {} }) {
  const now = () => performance.now() / 1000;
  const timings = {};
  let t = now();
  const { loadPyodide } = await import(/* @vite-ignore */ `${base}pyodide/pyodide.mjs`);
  const pyodide = await loadPyodide({ indexURL: await local(`${base}pyodide/`), stdout, stderr });
  timings.start = now() - t;
  t = now();
  const wheels = [];
  for (const entry of pins.packages) wheels.push(await local(`${base}wheels/${entry.file}`));
  await pyodide.loadPackage(wheels, { messageCallback: () => {}, errorCallback: stderr, checkIntegrity: false });
  pyodide.FS.mkdirTree("/cad/src");
  pyodide.unpackArchive(cad, "zip", { extractDir: "/cad/src" });
  timings.packages = now() - t;
  t = now();
  pyodide.FS.writeFile("/cad/kernel.py", kernelPy);
  pyodide.runPython("import sys; sys.path[:0] = ['/cad/src', '/cad']; import kernel");
  const harness = pyodide.pyimport("kernel");
  harness.warm();
  timings.imports = now() - t;
  const call = (name, request) => {
    const answer = harness[name](JSON.stringify(request));
    const [report, bytes] = answer.toJs();
    answer.destroy();
    return [JSON.parse(report), bytes];
  };
  return {
    pyodide,
    timings,
    shims: JSON.parse(harness.shims()),
    /** The WebAssembly memory in use, bytes. */
    heapBytes: () => pyodide._module.HEAPU8.length,
    /**
     * Build a script: `{ name, text, files?: { path: text }, functions?: string[] }` -> `{ reports, xbf, seconds }`.
     * `files` are written beside the script (its own modules, by relative path). `xbf`: the bytes of the first
     * model's `.xbf` the build wrote (every one, by name, in `written`).
     */
    build(request) {
      const [report, bytes] = call("build", request);
      return { ...report, xbf: bytes };
    },
    /**
     * The text of the script last built as `name` with its parameters set: `{ name, values }` -> `{ text, changed }`.
     * The rewrite is cad's own (`parameters.splice`), at the places that build reported.
     */
    withValues(request) {
      return call("with_values", request)[0];
    },
    /**
     * A model at other parameter values, nothing written (cad's `preview`): `{ name, model, values }` -> its
     * structure and its parts' shape bytes, of the script the last build of `name` left in the kernel.
     */
    preview(request) {
      const [report, bytes] = call("preview", request);
      return { ...report, shapes: bytes };
    },
    /** Read a file of the kernel's filesystem. */
    read: (path) => pyodide.FS.readFile(path),
  };
}

/** A zip of the library's source from a folder holding its packages (Node only): `cad/**.py` and its data files. */
export async function sourceZip(folder, packages = ["cad"]) {
  const fs = await import("node:fs");
  const path = await import("node:path");
  const { writeZip } = await import("./zip.mjs");
  const entries = [];
  const walk = (dir) => {
    for (const item of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => (a.name < b.name ? -1 : 1))) {
      const full = path.join(dir, item.name);
      if (item.isDirectory()) { if (item.name !== "__pycache__") walk(full); continue; }
      if (item.name.endsWith(".pyc")) continue;
      entries.push({ name: path.relative(folder, full).split(path.sep).join("/"), data: new Uint8Array(fs.readFileSync(full)) });
    }
  };
  for (const name of packages) walk(path.join(folder, name));
  return writeZip(entries);
}
