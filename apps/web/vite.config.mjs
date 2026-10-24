import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { buildId } from "@text-to-cad/ui/build-id";
import { stampDebugId } from "@text-to-cad/core/chunk-ids";
import { packageSourceMaps } from "@text-to-cad/core/source-maps";

import { resolveDirectoryRoot as resolveViewerDirectoryRoot } from "./scripts/directoryRoot.mjs";
import { resolveServerFsAllow } from "./scripts/serverFsAllow.mjs";
import {
  normalizeServerLifetimeMs,
  scheduleProcessShutdown,
} from "./scripts/serverLifetime.mjs";

// Vite owns its development port; the engine chooses a separate HTTP port:
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

// Vite obtains the API endpoint of this installation's engine (its one page's), then
// proxies /__cad with its token. Closing Vite leaves the engine and its other clients alive.
// VIEWER_PYTHON names the editable installation's interpreter. An explicit
// VIEWER_BACKEND_URL (the launcher's apiUrl) also needs CAD_ENGINE_TOKEN: the token is
// named outside the client's envPrefix (VIEWER_), which Vite hands to the page.
const ENV_PREFIX = "VIEWER_";
const TOKEN_VARIABLE = "CAD_ENGINE_TOKEN";

// A secret the page would be handed: the engine's token under the client's prefix.
function refuseClientTokens(env = process.env) {
  const exposed = Object.keys(env).filter((name) => name.startsWith(ENV_PREFIX) && /TOKEN|SECRET|KEY/u.test(name));
  if (exposed.length) {
    throw new Error(`${exposed.join(", ")}: Vite hands every ${ENV_PREFIX} variable to the page. `
      + `Name the engine token ${TOKEN_VARIABLE} instead.`);
  }
}

async function startDevBackend() {
  const external = String(process.env.VIEWER_BACKEND_URL || "").trim();
  if (external) {
    const target = external.replace(/\/+$/u, "");
    console.info(`CAD Viewer backend: ${target} (VIEWER_BACKEND_URL)`);
    return { target, token: process.env[TOKEN_VARIABLE] };
  }

  const python = process.env.VIEWER_PYTHON || "python3";
  // The backend serves every file by absolute path. Where it starts is the launch
  // folder the home shows (`serverInfo.start`, replacing the last launch's): where
  // `npm run dev` was run (scripts/directoryRoot.mjs reads INIT_CWD, which npm
  // sets), handed over as the child's cwd.
  const child = spawn(
    python,
    [
      "-m",
      "cadgen.viewer",
      "--host",
      "127.0.0.1",
      "--api-only",
      "--json",
    ],
    { cwd: directoryRoot, stdio: ["ignore", "pipe", "inherit"] },
  );
  const announced = await readFirstJsonLine(child.stdout);
  const target = String(announced.apiUrl || "").replace(/\/+$/u, "");
  console.info(`CAD Viewer backend: ${target} (${python}, started in ${directoryRoot})`);
  return { target, token: announced.token };
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

export default defineConfig(async ({ command }) => (refuseClientTokens(), {
  root: viewerAppRoot,
  base: "./",
  envPrefix: ENV_PREFIX,
  // Which build this is, for the version the app menu shows (src/host/viewerLinks.js): none for
  // the release's own, this checkout's commit for any other (@text-to-cad/ui/build-id).
  define: { __TEXT_TO_CAD_BUILD__: JSON.stringify(buildId({ version: viewerVersion(), cwd: viewerAppRoot })) },
  plugins: [
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
    // No CORS: the client is this origin's own, and the /__cad proxy below adds the engine's
    // token to what it forwards, so no other origin (another localhost port among them) may
    // read what it answers. Vite's default lets every localhost origin.
    cors: false,
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
            const { target, token } = await startDevBackend();
            return {
              "/__cad": { target, changeOrigin: false, headers: token ? { Authorization: `Bearer ${token}` } : {} },
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
