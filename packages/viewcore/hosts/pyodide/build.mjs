#!/usr/bin/env node
// build.mjs: a model's script built by cad's own build on the WebAssembly kernel, in Node (prototype).
// Usage: node build.mjs PACKAGES_DIR SCRIPT.py [--out DIR] [--cad SRC_DIR] [--json]
//   PACKAGES_DIR  what fetch.mjs downloaded
//   SCRIPT.py     a model's script; the Python files of its folder go with it (its own modules)
//   --out DIR     where each `.xbf` the build wrote is put (default: beside nothing, the sizes are printed)
//   --cad DIR     the folder holding the library's source (default: this repository's packages/cad/src)
// Prints seconds for the start, the packages, the imports and the build, and the memory in use.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { loadKernel, sourceZip } from "./kernel.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const option = (name) => { const at = args.indexOf(name); return at < 0 ? null : args.splice(at, 2)[1]; };
const out = option("--out");
const source = option("--cad") || path.resolve(HERE, "../../../cad/src");
const asJson = args.includes("--json") && args.splice(args.indexOf("--json"), 1);
const [packages, ...scripts] = args;
if (!packages || !scripts.length) { console.error("usage: node build.mjs PACKAGES_DIR SCRIPT.py [...] [--out DIR] [--cad SRC_DIR] [--json]"); process.exit(2); }

/** The text files of a script's folder a model may import or read, by relative path (no built or hidden ones). */
export function folderFiles(folder) {
  const files = {};
  const walk = (dir) => {
    for (const item of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, item.name);
      if (item.name.startsWith(".") || item.name === "__pycache__") continue;
      if (item.isDirectory()) walk(full);
      else if (/\.(py|json|toml|txt|csv)$/.test(item.name)) files[path.relative(folder, full).split(path.sep).join("/")] = fs.readFileSync(full, "utf8");
    }
  };
  walk(folder);
  return files;
}

const kernel = await loadKernel({
  base: pathToFileURL(path.resolve(packages) + path.sep).href,
  pins: JSON.parse(fs.readFileSync(path.join(HERE, "pins.json"), "utf8")),
  cad: await sourceZip(source),
  kernelPy: fs.readFileSync(path.join(HERE, "kernel.py"), "utf8"),
  stdout: (line) => console.error(line), stderr: (line) => console.error(line),
});
const results = [];
for (const script of scripts) {
  const folder = path.dirname(path.resolve(script));
  const files = folderFiles(folder);
  const name = path.basename(script);
  const text = files[name]; delete files[name];
  const built = kernel.build({ name, text, files });
  const ok = built.reports.every((report) => report.ok !== false);
  if (out) {
    fs.mkdirSync(out, { recursive: true });
    for (const file of built.written) fs.writeFileSync(path.join(out, path.basename(file)), kernel.read(file));
  }
  results.push({ script: name, ok, seconds: +built.seconds.toFixed(3), written: built.written.map((file) => [path.basename(file), kernel.read(file).length]),
    error: ok ? undefined : built.reports.find((report) => report.ok === false)?.error, log: built.log });
}
const summary = { timings: kernel.timings, heapMB: +(kernel.heapBytes() / 1048576).toFixed(1), rssMB: +(process.memoryUsage().rss / 1048576).toFixed(1), shims: kernel.shims, results };
if (asJson) console.log(JSON.stringify(summary));
else {
  console.log(`start ${summary.timings.start.toFixed(2)} s, packages ${summary.timings.packages.toFixed(2)} s, imports ${summary.timings.imports.toFixed(2)} s; heap ${summary.heapMB} MB, process ${summary.rssMB} MB`);
  for (const result of results) console.log(`${result.script}: ${result.ok ? "built" : "FAILED"} in ${result.seconds} s ${JSON.stringify(result.written)}${result.error ? "\n" + result.error : ""}`);
}
