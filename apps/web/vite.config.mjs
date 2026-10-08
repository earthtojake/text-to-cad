import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { buildId } from "@text-to-cad/ui/build-id";
import { stampDebugId } from "@text-to-cad/core/chunk-ids";
import { packageSourceMaps } from "@text-to-cad/core/source-maps";
import { drawingAssetsPlugin } from "@text-to-cad/ui/drawing-assets";

import { resolveDirectoryRoot as resolveViewerDirectoryRoot } from "./scripts/directoryRoot.mjs";
import { resolveServerFsAllow } from "./scripts/serverFsAllow.mjs";
import {
  normalizeServerLifetimeMs,
  scheduleProcessShutdown,
} from "./scripts/serverLifetime.mjs";

// Dev deliberately lives on Vite's own canonical port, NOT the launcher's 3245:
// dev is a hand-managed foreground process that no launch reuses or replaces,
// so it must not look like (or collide with) a launched Viewer. Taken port →
// pick another with --port; nothing reuses here.
const DEFAULT_DEV_PORT = 5173;
function devPort() { const port=Number(process.env.PORT); return Number.isInteger(port) && port>0 ? port : DEFAULT_DEV_PORT; }

const viewerAppRoot = path.dirname(fileURLToPath(import.meta.url));
const viewerClientRoot = path.join(viewerAppRoot, "src", "client");
const repoRoot = path.resolve(viewerAppRoot, "../..");
const defaultDirectoryRoot = path.resolve(viewerAppRoot, "..");
const directoryRoot = resolveDirectoryRoot();
const viewerAllowedHosts = normalizeViewerAllowedHosts(process.env.VIEWER_ALLOWED_HOSTS ?? "");
const viewerServerLifetimeMs = normalizeServerLifetimeMs(process.env.VIEWER_SERVER_LIFETIME_MS);

function viewerVersion() {
  return JSON.parse(fs.readFileSync(path.join(viewerAppRoot, "package.json"), "utf8")).version;
}

function normalizeViewerAllowedHosts(value) {
  return String(value || "")
    .split(",")
    .map((host) => host.trim())
    .filter(Boolean);
}

function resolveDirectoryRoot() {
  return resolveViewerDirectoryRoot({
    env: process.env,
    cwd: process.cwd(),
    appRoot: viewerAppRoot,
    defaultDirectoryRoot,
  });
}

// Dev runs the SAME backend as production — `cadgen viewer`, spawned as
// `python -m cadgen.viewer` — but as a second process that Vite proxies to,
// because a Python server cannot be in-process Vite middleware. `npm run dev`
// stays ONE command: this plugin spawns the backend on an ephemeral port, reads
// the port off its {url,port,action} line, and hands it to the proxy in the
// server block.
//
// The backend runs --new --api-only. --new is a CORRECTNESS requirement, not
// tidiness: on the launcher's port, a later `cadgen viewer` launch would find
// this backend and reuse it (or replace it), handing an agent a URL served by
// Vite's proxy target instead of a real Viewer; --new binds a port of its own
// that no launch asks about. --api-only is what makes dev
// work on a checkout that has never been built: Vite serves the client here, so
// this backend needs no dist/ — and dist/ is gitignored, so without it
// `npm run dev` failed on every fresh clone with a complaint about a missing
// build.
//
// VIEWER_PYTHON names the interpreter that has cadgen installed, defaulting to
// python3 — usually WRONG in a checkout, where that interpreter is the repo
// venv. The resolved interpreter is logged at startup so an exit is
// attributable. See CONTRIBUTING.md for the checkout recipe.
//
// VIEWER_BACKEND_URL attaches to a backend you started yourself, which is also
// how you put a debugger on it.
// Resolved during CONFIG, not in configureServer: Vite builds the proxy
// middleware from `server.proxy` while creating the server, and http-proxy
// wants a plain string target — so the port has to be known before the config
// object exists. Vite supports an async config function, which is what makes
// that possible.
async function startDevBackend() {
  const external = String(process.env.VIEWER_BACKEND_URL || "").trim();
  if (external) {
    const target = external.replace(/\/+$/u, "");
    console.info(`CAD Viewer backend: ${target} (VIEWER_BACKEND_URL)`);
    return target;
  }

  const python = process.env.VIEWER_PYTHON || "python3";
  // The backend serves every file by absolute path. Where it starts is only where
  // a developer's relative ?file= resolves (`serverInfo.start`): where
  // `npm run dev` was run (scripts/directoryRoot.mjs reads INIT_CWD, which npm
  // sets), handed over as the child's cwd.
  const child = spawn(
    python,
    [
      "-m",
      "cadgen.viewer",
      "--host",
      "127.0.0.1",
      "--new",
      "--api-only",
      "--json",
    ],
    { cwd: directoryRoot, stdio: ["ignore", "pipe", "inherit"] },
  );
  // The backend's stderr is INHERITED, so whatever it printed is already above
  // this line. Say only what the exit code cannot: which interpreter ran, so a
  // version or import failure is attributable. Guessing at a cause here was
  // actively harmful — it used to blame a missing cadgen for every exit,
  // including the ones that had nothing to do with cadgen.
  child.once("exit", (code, signal) => {
    if (signal === "SIGTERM") {
      return; // our own teardown, below
    }
    console.error(
      `CAD Viewer backend (${python}) exited ${code === null ? `on ${signal}` : `with code ${code}`}. ` +
        "Its error is printed above; VIEWER_PYTHON selects the interpreter.",
    );
  });
  // Vite's own exit is the only teardown that always runs; a killed dev server
  // must not leave the backend holding a port.
  for (const signal of ["exit", "SIGINT", "SIGTERM"]) {
    process.once(signal, () => child.kill("SIGTERM"));
  }

  const announced = await readFirstJsonLine(child.stdout);
  const target = String(announced.url || "").replace(/\/+$/u, "");
  console.info(`CAD Viewer backend: ${target} (${python}, started in ${directoryRoot})`);
  return target;
}

function readFirstJsonLine(stream) {
  return new Promise((resolve, reject) => {
    let buffered = "";
    const onData = (chunk) => {
      buffered += chunk;
      for (const line of buffered.split("\n")) {
        if (!line.startsWith("{")) {
          continue;
        }
        try {
          const parsed = JSON.parse(line);
          stream.off("data", onData);
          resolve(parsed);
          return;
        } catch {
          // a partial line; keep buffering
        }
      }
    };
    stream.on("data", onData);
    stream.once("error", reject);
    stream.once("end", () =>
      reject(new Error(`CAD Viewer backend exited before announcing a port: ${buffered}`)),
    );
  });
}

function serverLifetimePlugin() {
  return {
    name: "cad-viewer-server-lifetime",
    configureServer(server) {
      if (viewerServerLifetimeMs === null) {
        return;
      }
      let shutdownTimer = null;
      const scheduleShutdown = () => {
        shutdownTimer = scheduleProcessShutdown({
          lifetimeMs: viewerServerLifetimeMs,
          label: "CAD Viewer dev server",
          close: () => server.close(),
        });
      };
      if (server.httpServer?.listening) {
        scheduleShutdown();
      } else {
        server.httpServer?.once("listening", scheduleShutdown);
      }
      server.httpServer?.once("close", () => {
        if (shutdownTimer) {
          clearTimeout(shutdownTimer);
        }
      });
    },
  };
}

// Each chunk's debug id, by file name, in the page before anything runs (`__cadChunkIds`): a crash
// report names the chunk each of its frames ran in by it (@text-to-cad/core's crash reporter), and
// the release uploads every chunk with its source map (scripts/release/sourcemaps.py) for PostHog to
// show the source -- the shared packages' own source, whose maps the build chains
// (@text-to-cad/core/source-maps), not their compiled dist. Each chunk goes by an id its text and its
// map decide (@text-to-cad/core/chunk-ids), never rolldown's, which names the code alone. The maps stay
// in dist, which the wheel leaves out (scripts/bundle).
function chunkIdsPlugin() {
  return {
    name: "cad-viewer-chunk-ids",
    apply: "build",
    enforce: "post",
    generateBundle: { order: "post", handler(_, bundle) {
      const ids = {};
      for (const chunk of Object.values(bundle)) {
        if (chunk.type !== "chunk" || !chunk.sourcemapFileName) continue;
        const map = bundle[chunk.sourcemapFileName];
        if (map?.type !== "asset") throw new Error(`The CAD Viewer chunk ${chunk.fileName} has no source map.`);
        const stamped = stampDebugId(chunk.code, String(map.source), chunk.fileName);
        chunk.code = stamped.code;
        map.source = stamped.map;
        ids[chunk.fileName.split("/").pop()] = stamped.debugId;
      }
      const html = bundle["index.html"];
      if (!html || html.type !== "asset") throw new Error("The CAD Viewer build needs index.html.");
      const script = `<script>globalThis.__cadChunkIds=${JSON.stringify(ids)}</script>`;
      const document = String(html.source);
      if (!document.includes("<head>")) throw new Error("The CAD Viewer's index.html has no <head>.");
      html.source = document.replace("<head>", () => `<head>${script}`);
    } },
  };
}

export default defineConfig(async ({ command }) => ({
  root: viewerAppRoot,
  envPrefix: "VIEWER_",
  // Which build this is, for the version the app menu shows (src/host/viewerLinks.js): none for
  // the release's own, this checkout's commit for any other (@text-to-cad/ui/build-id).
  define: { __TEXT_TO_CAD_BUILD__: JSON.stringify(buildId({ version: viewerVersion(), cwd: viewerAppRoot })) },
  plugins: [
    // Excalidraw's fonts, served in dev and emitted into dist/excalidraw, with
    // the SDK's CDN fallback pointed back at this origin: the Viewer ships in a
    // wheel and never fetches a font from the network. The 12 MB Xiaolai CJK
    // family is left out of the wheel on purpose; a CJK glyph is then a local
    // miss and a system font, not a request.
    drawingAssetsPlugin({ exclude: [/\/fonts\/Xiaolai\//] }),
    react(),
    serverLifetimePlugin(),
    packageSourceMaps(["@text-to-cad/core", "@text-to-cad/ui"]),
    chunkIdsPlugin(),
  ],
  resolve: { alias: { "@": viewerClientRoot }, dedupe: ["react", "react-dom", "three", "lucide-react"] },
  build: {
    chunkSizeWarningLimit: 800,
    // Maps beside the chunks, named by no chunk (`hidden`), each chunk's debug id in it and in its map.
    sourcemap: "hidden",
    rolldownOptions: { output: { sourcemapDebugIds: true, codeSplitting: { groups: [
      { name: "vendor-three", test: /[\\/]node_modules[\\/]three[\\/]/ },
      { name: "vendor-react", test: /[\\/]node_modules[\\/]react(?:-dom)?[\\/]/ },
      { name: "vendor-ui", test: /[\\/]node_modules[\\/]@?radix-ui[\\/]/ },
      { name: "vendor-icons", test: /[\\/]node_modules[\\/]lucide-react[\\/]/ },
    ] } } },
  },
  worker: {
    format: "es",
  },
  server: {
    host: "127.0.0.1",
    port: devPort(),
    // Fail on a taken port instead of silently rolling: dev is hand-managed,
    // so the agent picks another port explicitly. (The launcher is the one that
    // reuses or replaces; dev stays out of that.)
    strictPort: true,
    allowedHosts: viewerAllowedHosts,
    // The two API prefixes go to the Python backend; everything else is the
    // client, served by Vite with HMR. Neither prefix collides with Vite's own
    // reserved /@vite/, /@fs/ or /@id/.
    //
    // changeOrigin: false is MANDATORY. The backend keeps its DNS-rebinding
    // Host check, which is active whenever the bound host is loopback. With
    // false the browser's own `Host: 127.0.0.1:5173` is forwarded and passes
    // (the check compares the NAME, never the port) — the same header the
    // in-process middleware used to see. With true, Vite would rewrite Host to
    // the target's, which would launder a VIEWER_ALLOWED_HOSTS entry served
    // over a non-local name into an accepted request.
    proxy:
      command === "serve"
        ? await (async () => {
            const target = await startDevBackend();
            return {
              "/__cad": { target, changeOrigin: false },
              "/__tess_cache": { target, changeOrigin: false },
            };
          })()
        : undefined,
    fs: {
      // @text-to-cad/core lives outside the app root, so it must be allowed explicitly;
      // real paths too, in case a checkout reaches it through a link. See
      // scripts/serverFsAllow.mjs.
      allow: resolveServerFsAllow([repoRoot], {
        realpath: fs.realpathSync,
      }),
    },
  },
  preview: {
    host: "127.0.0.1",
    allowedHosts: viewerAllowedHosts,
  },
}));
