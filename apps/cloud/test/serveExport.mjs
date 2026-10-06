#!/usr/bin/env node
// A development stand-in for the cloud server, over one export: the built page from `dist/`,
// the build's viewer API through `handleViewerApi`, its objects at `/o/<sha256>`, and the build
// API the page's Code panel reads (`/v1/builds/<id>`, `/files`, `/files/<path>`) from the
// exported folder. For the browser test (`viewer.browser.test.ts`) and for looking at an export
// by hand:
//
//   node apps/cloud/test/serveExport.mjs --export OUT --root PROJECT [--id k7Qx2] [--port 4173]
//
// It stores nothing but a copied prompt's sketch, which it keeps beside the objects.

import { createHash } from "node:crypto";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { parseExportIndex, primaryView } from "../server/exportIndex.ts";
import { handleViewerApi } from "../server/viewerApi.ts";

const APP_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const STATIC_TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8", ".map": "application/json; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon",
  ".woff2": "font/woff2", ".ttf": "font/ttf", ".txt": "text/plain; charset=utf-8", ".wasm": "application/wasm" };

function readBody(request) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    request.on("data", chunk => chunks.push(chunk));
    request.on("end", () => resolve(new Uint8Array(Buffer.concat(chunks))));
    request.on("error", reject);
  });
}

/**
 * @param {{ exportDir: string, rootDir: string, distDir?: string, id?: string, port?: number, host?: string }} options
 * @returns {Promise<{ url: string, id: string, port: number, index: object, close(): Promise<void> }>}
 */
export async function startExportServer({ exportDir, rootDir, distDir = path.join(APP_ROOT, "dist"), id = "k7Qx2", port = 0, host = "127.0.0.1" }) {
  const index = parseExportIndex(fs.readFileSync(path.join(exportDir, "export.json"), "utf8"));
  const objectsDir = path.join(exportDir, "objects");
  const objectTypes = new Map();
  for (const route of ["/__cad/asset", "/__cad/store"]) for (const entry of Object.values(index.routes[route])) objectTypes.set(entry.object, entry.type);
  if (!fs.existsSync(path.join(distDir, "index.html"))) throw new Error(`no built page at ${distDir}: run \`npm --prefix apps/cloud run build\` first`);
  const page = fs.readFileSync(path.join(distDir, "index.html"));
  let origin = "";
  const ctx = {
    objectUrl: sha256 => `${origin}/o/${sha256}`,
    async saveSketch(png, name) {
      const digest = createHash("sha256").update(png).digest("hex");
      fs.writeFileSync(path.join(objectsDir, digest), png);
      objectTypes.set(digest, "image/png");
      return `${origin}/o/${digest}?name=${encodeURIComponent(name)}`;
    },
  };
  const sendJson = (response, status, value, headers = {}) => {
    const body = Buffer.from(JSON.stringify(value));
    response.writeHead(status, { "content-type": "application/json; charset=utf-8", "content-length": body.length, ...headers });
    response.end(body);
  };
  const server = http.createServer(async (request, response) => {
    try {
      const url = new URL(request.url || "/", origin);
      const method = (request.method || "GET").toUpperCase();
      const build = /^\/b\/([^/]+)(\/.*)?$/.exec(url.pathname);
      if (build && decodeURIComponent(build[1]) === id) {
        const rest = build[2] || "";
        if (/^\/__(?:cad|tess_cache)\//.test(rest)) {
          const body = method === "POST" ? await readBody(request) : undefined;
          const headers = Object.fromEntries(Object.entries(request.headers).map(([name, value]) => [name.toLowerCase(), Array.isArray(value) ? value.join(", ") : value]));
          const answer = await handleViewerApi(index, { method, path: rest, query: url.searchParams, body, headers }, ctx);
          if (answer.redirect) { response.writeHead(answer.status, { ...answer.headers, location: answer.redirect }); response.end(); return; }
          if (answer.json !== undefined) { sendJson(response, answer.status, answer.json, answer.headers); return; }
          const bytes = answer.body ? Buffer.from(answer.body) : Buffer.alloc(0);
          response.writeHead(answer.status, { ...answer.headers, ...(answer.body ? { "content-length": bytes.length } : {}) });
          response.end(method === "HEAD" ? undefined : bytes);
          return;
        }
        if (!rest || rest === "/") { response.writeHead(302, { location: `/b/${encodeURIComponent(id)}${primaryView(index)}` }); response.end(); return; }
        response.writeHead(200, { "content-type": "text/html; charset=utf-8", "content-length": page.length, "cache-control": "no-store" });
        response.end(method === "HEAD" ? undefined : page);
        return;
      }
      const object = /^\/o\/([0-9a-f]{64})$/.exec(url.pathname);
      if (object) {
        const file = path.join(objectsDir, object[1]);
        if (!fs.existsSync(file)) { sendJson(response, 404, { error: "Not found" }); return; }
        const stat = fs.statSync(file);
        response.writeHead(200, { "content-type": objectTypes.get(object[1]) || "application/octet-stream", "content-length": stat.size, "cache-control": "public, max-age=31536000, immutable" });
        if (method === "HEAD") { response.end(); return; }
        fs.createReadStream(file).pipe(response);
        return;
      }
      const api = /^\/v1\/builds\/([^/]+)(?:\/files(\/.*)?)?$/.exec(url.pathname);
      if (api && decodeURIComponent(api[1]) === id) {
        if (api[0].endsWith(`/builds/${api[1]}`)) { sendJson(response, 200, { id, title: `Build ${id}`, status: "succeeded", primaryFile: primaryView(index), outputs: index.views }); return; }
        if (!api[2]) { sendJson(response, 200, { files: index.files }); return; }
        const virtual = decodeURIComponent(api[2]);
        const entry = index.files.find(file => file.path === virtual);
        if (!entry) { sendJson(response, 404, { error: "Not found" }); return; }
        const bytes = fs.readFileSync(path.join(rootDir, ...virtual.split("/").filter(Boolean)));
        response.writeHead(200, { "content-type": "text/plain; charset=utf-8", "content-length": bytes.length });
        response.end(method === "HEAD" ? undefined : bytes);
        return;
      }
      // The page's own assets: `dist/` at the root.
      const file = path.join(distDir, ...url.pathname.split("/").filter(part => part && part !== ".."));
      if (url.pathname !== "/" && fs.existsSync(file) && fs.statSync(file).isFile()) {
        const stat = fs.statSync(file);
        response.writeHead(200, { "content-type": STATIC_TYPES[path.extname(file)] || "application/octet-stream", "content-length": stat.size });
        if (method === "HEAD") { response.end(); return; }
        fs.createReadStream(file).pipe(response);
        return;
      }
      sendJson(response, 404, { error: "Not found" });
    } catch (error) {
      sendJson(response, 500, { error: String(error?.message || error) });
    }
  });
  await new Promise((resolve, reject) => { server.once("error", reject); server.listen(port, host, () => resolve()); });
  const bound = server.address();
  origin = `http://${host}:${bound.port}`;
  return { url: origin, id, port: bound.port, index, close: () => new Promise(resolve => server.close(() => resolve())) };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = {};
  for (let at = 2; at < process.argv.length; at += 1) {
    const flag = process.argv[at];
    if (!flag.startsWith("--")) throw new Error(`unknown argument ${flag}`);
    args[flag.slice(2)] = process.argv[++at];
  }
  if (!args.export || !args.root) { console.error("usage: serveExport.mjs --export OUT --root PROJECT [--id ID] [--port N]"); process.exit(2); }
  const started = await startExportServer({ exportDir: path.resolve(args.export), rootDir: path.resolve(args.root), id: args.id || "k7Qx2", port: Number(args.port || 4173) });
  console.log(`${started.url}/b/${started.id}${primaryView(started.index)}`);
}
