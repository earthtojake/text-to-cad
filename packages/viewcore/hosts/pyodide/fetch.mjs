#!/usr/bin/env node
// fetch.mjs: the pinned WebAssembly kernel downloaded into a folder (prototype): Pyodide's core, the CAD kernel's
// Python binding built for it (OCP on OCCT 8.0.1), build123d and what it imports, each file checked against the
// sha256 lock.json names. Usage: node fetch.mjs PACKAGES_DIR
//   PACKAGES_DIR/pyodide/   Pyodide's core (its loader, its module, the standard library)
//   PACKAGES_DIR/wheels/    one wheel per package
// A wheel lock.json marks `slim` is kept without its texture images but its colour maps (a material library's maps:
// 86 MB, of which the colour maps are the 21 MB a build reads, to average a material's colour): the wheel as
// downloaded is checked, then written again without them.
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { readEntries, writeZip } from "./zip.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
// The kernel's host as cad ships it: its Python's stand-in, what that runs first, and the lock of what a kernel
// folder is made of.
const HOST = path.join(HERE, "..", "..", "..", "cad", "src", "cad_server", "_internal", "kernel_host");
// A texture image left out of a slim wheel: any but a colour map (``color.png``), which a material's colour is read off.
const TEXTURES = /(^|\/)(?!color\.)[^/]*\.(png|jpe?g|webp|exr|hdr|ktx2?|tiff?)$/i;

async function fetched(url, sha256) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url} answered ${response.status}`);
  const bytes = new Uint8Array(await response.arrayBuffer());
  const digest = createHash("sha256").update(bytes).digest("hex");
  if (digest !== sha256) throw new Error(`${url}: sha256 ${digest}, pinned ${sha256}`);
  return bytes;
}

const target = process.argv[2];
if (!target) { console.error("usage: node fetch.mjs PACKAGES_DIR"); process.exit(2); }
const pins = JSON.parse(fs.readFileSync(path.join(HOST, "lock.json"), "utf8"));
fs.mkdirSync(path.join(target, "pyodide"), { recursive: true });
fs.mkdirSync(path.join(target, "wheels"), { recursive: true });
let total = 0;
for (const file of [...pins.core.map(f => ({ ...f, to: path.join(target, "pyodide", f.file) })),
                    ...pins.packages.map(f => ({ ...f, to: path.join(target, "wheels", f.file) }))]) {
  if (fs.existsSync(file.to)) { total += fs.statSync(file.to).size; continue; }
  let bytes = await fetched(file.url, file.sha256);
  if (file.slim) bytes = writeZip(readEntries(bytes).filter(entry => !TEXTURES.test(entry.name)));
  fs.writeFileSync(file.to, bytes);
  total += bytes.length;
  console.log(`${file.file}  ${(bytes.length / 1048576).toFixed(2)} MB`);
}
console.log(`${pins.core.length + pins.packages.length} files, ${(total / 1048576).toFixed(1)} MB in ${target}`);
