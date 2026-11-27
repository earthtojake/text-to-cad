#!/usr/bin/env node
// serve.mjs: the demo page served from this checkout (prototype). Usage: node serve.mjs PACKAGES_DIR [PORT]
//   /                 this folder (index.html, main.js, kernel-worker.js, model.py)
//   /host/            ../ (kernel.mjs, kernel.py, pins.json, zip.mjs)
//   /web/             the view core's web host (viewcore.js, worker.js)
//   /viewcore.wasm    the view core's module (packages/viewcore/dist, built by scripts/core.sh)
//   /packages/        PACKAGES_DIR, what ../fetch.mjs downloaded
//   /cad.zip          the library's source (packages/cad/src/cad), zipped here
//   /three/           three.js from the repository's node_modules, which draws the meshes
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { sourceZip } from "../kernel.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "../../../../..");
const [packages, port = "8787"] = process.argv.slice(2);
if (!packages) { console.error("usage: node serve.mjs PACKAGES_DIR [PORT]"); process.exit(2); }
const ROUTES = [
  ["/host/", path.resolve(HERE, "..")],
  ["/web/", path.resolve(HERE, "../../web")],
  ["/packages/", path.resolve(packages)],
  ["/three/", path.join(REPO, "node_modules/three")],
  ["/", HERE],
];
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
  ".json": "application/json", ".wasm": "application/wasm", ".py": "text/plain; charset=utf-8", ".zip": "application/zip" };
const cad = Buffer.from(await sourceZip(path.join(REPO, "packages/cad/src")));

http.createServer((request, response) => {
  const at = decodeURIComponent(new URL(request.url, "http://localhost").pathname);
  const send = (body, type) => { response.writeHead(200, { "content-type": type, "content-length": body.length, "cache-control": "no-store" }); response.end(body); };
  if (at === "/cad.zip") return send(cad, TYPES[".zip"]);
  if (at === "/viewcore.wasm") return send(fs.readFileSync(path.join(REPO, "packages/viewcore/dist/viewcore.wasm")), TYPES[".wasm"]);
  for (const [prefix, folder] of ROUTES) {
    if (!at.startsWith(prefix)) continue;
    const file = path.join(folder, at.slice(prefix.length) || "index.html");
    if (!file.startsWith(folder) || !fs.existsSync(file) || !fs.statSync(file).isFile()) break;
    return send(fs.readFileSync(file), TYPES[path.extname(file)] || "application/octet-stream");
  }
  response.writeHead(404); response.end("not found");
}).listen(Number(port), "127.0.0.1", () => console.log(`http://127.0.0.1:${port}/`));
