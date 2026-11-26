// The view core beside the viewer's page (prototype): `viewcore/` in the build -- the module
// (packages/viewcore/dist/viewcore.wasm, built by packages/viewcore/scripts/core.sh, never committed), the
// web host and its Worker (packages/viewcore/hosts/web), the engine's look as static files where a copy of it
// is kept (tmp/viewcore/look.json and tmp/viewcore/look/environment.hdr), and a manifest naming them, which
// the page reads under `?viewcore=N` (src/host/viewcore.js). Where no module is built, nothing is added and the
// page reads every document from the engine. CAD_VIEWCORE=0 leaves it out of a build that has one.
import fs from "node:fs";
import path from "node:path";

const NOTICE = `viewcore.wasm uses Open CASCADE Technology (OCCT) 8.0.1, under the GNU LGPL 2.1 with the
Open CASCADE exception 1.0 (https://dev.opencascade.org/resources/licensing). Its source, tag V8_0_1,
unchanged, is at https://github.com/Open-Cascade-SAS/OCCT; the scripts that build the module are in
packages/viewcore/scripts. (Prototype: not a release.)
`;

/** What the build adds under `viewcore/`, by its path there: each a file's bytes, or null where there is no core. */
export function viewCoreAssets(repoRoot, env = process.env) {
  if (env.CAD_VIEWCORE === "0") return null;
  const wasm = path.join(repoRoot, "packages/viewcore/dist/viewcore.wasm");
  if (!fs.existsSync(wasm)) return null;
  const host = path.join(repoRoot, "packages/viewcore/hosts/web");
  const lookJson = path.join(repoRoot, "tmp/viewcore/look.json");
  const lookEnvironment = path.join(repoRoot, "tmp/viewcore/look/environment.hdr");
  const look = fs.existsSync(lookJson) && fs.existsSync(lookEnvironment);
  const files = {
    "viewcore.wasm": fs.readFileSync(wasm),
    "viewcore.js": fs.readFileSync(path.join(host, "viewcore.js")),
    "worker.js": fs.readFileSync(path.join(host, "worker.js")),
    "NOTICE.txt": Buffer.from(NOTICE),
  };
  if (look) {
    files["look.json"] = fs.readFileSync(lookJson);
    files["look/environment.hdr"] = fs.readFileSync(lookEnvironment);
  }
  files["manifest.json"] = Buffer.from(JSON.stringify({
    wasm: "/viewcore/viewcore.wasm", worker: "/viewcore/worker.js", wasmBytes: files["viewcore.wasm"].byteLength,
    look: look ? { json: "/viewcore/look.json", environment: "/viewcore/look/environment.hdr" } : null,
  }));
  return files;
}

const TYPES = { ".wasm": "application/wasm", ".js": "text/javascript; charset=utf-8", ".json": "application/json",
  ".hdr": "image/vnd.radiance", ".txt": "text/plain; charset=utf-8" };

/** The vite plugin: the files emitted into the build, and served under `/viewcore/` by the dev server. */
export function viewCoreAssetsPlugin(repoRoot) {
  return {
    name: "cad-viewer-viewcore",
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        const at = String(request.url || "").split("?")[0];
        if (!at.startsWith("/viewcore/")) return next();
        const files = viewCoreAssets(repoRoot);
        const file = files?.[at.slice("/viewcore/".length)];
        if (!file) { response.statusCode = 404; response.end("no view core here"); return; }
        response.setHeader("content-type", TYPES[path.extname(at)] || "application/octet-stream");
        response.end(file);
      });
    },
    generateBundle() {
      const files = viewCoreAssets(repoRoot);
      if (!files) return;
      for (const [name, source] of Object.entries(files)) this.emitFile({ type: "asset", fileName: `viewcore/${name}`, source });
    },
  };
}
