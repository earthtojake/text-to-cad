import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

import { resolveDirectoryRoot as resolveViewerDirectoryRoot } from "./scripts/directoryRoot.mjs";
import { resolveServerFsAllow } from "./scripts/serverFsAllow.mjs";
import { assertNoDeprecatedLocalRootEnv } from "./scripts/viewerEnv.mjs";
import {
  normalizeServerLifetimeMs,
  scheduleProcessShutdown,
} from "./scripts/serverLifetime.mjs";

// Dev deliberately lives on Vite's own canonical port, NOT the bundled
// launcher's 3245: dev is a hand-managed foreground process that never enters
// the instance registry and never participates in launch reuse, so it must not
// look like (or collide with) a launched Viewer. Taken port → pick another
// with --port; nothing rolls or reuses here.
const DEFAULT_DEV_PORT = 5173;

const viewerAppRoot = path.dirname(fileURLToPath(import.meta.url));
const viewerClientRoot = path.join(viewerAppRoot, "src", "client");
const cadJsPackageRoot = resolveCadJsPackageRoot();
const viewerNodeModulesRoot = path.join(viewerAppRoot, "node_modules");
const defaultDirectoryRoot = path.resolve(viewerAppRoot, "..");
const directoryRoot = resolveDirectoryRoot();
const viewerAllowedHosts = normalizeViewerAllowedHosts(process.env.VIEWER_ALLOWED_HOSTS ?? "");
const viewerServerLifetimeMs = normalizeServerLifetimeMs(process.env.VIEWER_SERVER_LIFETIME_MS);
assertNoDeprecatedLocalRootEnv(process.env);

function normalizeViewerAllowedHosts(value) {
  return String(value || "")
    .split(",")
    .map((host) => host.trim())
    .filter(Boolean);
}

// cadgen-js is this repository's `packages/cadgen-js`, two levels up: the client is
// built from its SOURCE (the package is `private`, not installed from a registry),
// and package.json names the same path as a `file:` dependency so node_modules
// carries a link to it for tooling that resolves by name. An installed copy under
// node_modules is the fallback for a checkout laid out some other way.
function resolveCadJsPackageRoot() {
  const repoPackageSrc = path.resolve(viewerAppRoot, "..", "..", "packages", "cadgen-js", "src");
  if (fs.existsSync(repoPackageSrc)) {
    return repoPackageSrc;
  }
  const installedPackageSrc = path.join(viewerAppRoot, "node_modules", "cadgen-js", "src");
  if (fs.existsSync(installedPackageSrc)) {
    return installedPackageSrc;
  }
  // Nothing resolved: name the repo path so the failure points at the layout.
  return repoPackageSrc;
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
// The backend runs --ephemeral --no-registry --api-only. --no-registry is a
// CORRECTNESS requirement, not tidiness: a registered dev backend would be
// found by a later `cadgen viewer` launch from the same directory (reuse keys
// on the served realpath at the same version), handing an agent a URL served by
// Vite's proxy target instead of a real Viewer. --api-only is what makes dev
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
  // The backend has no directory flag: its cwd IS the directory it serves. Dev
  // still decides which directory that is (scripts/directoryRoot.mjs reads
  // INIT_CWD, which npm sets for `npm run dev`); the hand-off is the child's
  // cwd rather than an argument.
  const child = spawn(
    python,
    [
      "-m",
      "cadgen.viewer",
      "--host",
      "127.0.0.1",
      "--ephemeral",
      "--no-registry",
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
  console.info(`CAD Viewer backend: ${target} (${python}, serving ${directoryRoot})`);
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

export default defineConfig(async ({ command }) => ({
  root: viewerAppRoot,
  envPrefix: "VIEWER_",
  plugins: [
    react(),
    serverLifetimePlugin(),
  ],
  resolve: {
    alias: {
      "@": viewerClientRoot,
      "cadgen-js": cadJsPackageRoot,
      "clsx": path.join(viewerNodeModulesRoot, "clsx"),
      "gifenc": path.join(viewerNodeModulesRoot, "gifenc", "dist", "gifenc.esm.js"),
      "tailwind-merge": path.join(viewerNodeModulesRoot, "tailwind-merge"),
      "three": path.join(viewerNodeModulesRoot, "three"),
      "three/examples": path.join(viewerNodeModulesRoot, "three", "examples"),
    },
  },
  esbuild: {
    loader: "jsx",
    include: /.*\.[jt]sx?$/,
    exclude: [],
  },
  optimizeDeps: {
    esbuildOptions: {
      loader: {
        ".js": "jsx",
      },
    },
  },
  build: {
    chunkSizeWarningLimit: 800,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) {
            return undefined;
          }
          if (id.includes("/three/")) {
            return "vendor-three";
          }
          if (id.includes("/react/") || id.includes("/react-dom/")) {
            return "vendor-react";
          }
          if (id.includes("/radix-ui/") || id.includes("/@radix-ui/")) {
            return "vendor-ui";
          }
          if (id.includes("/lucide-react/")) {
            return "vendor-icons";
          }
          return undefined;
        },
      },
    },
  },
  worker: {
    format: "es",
  },
  server: {
    host: "127.0.0.1",
    port: DEFAULT_DEV_PORT,
    // Fail on a taken port instead of silently rolling: dev is hand-managed,
    // so the agent picks another port explicitly. (The bundled launcher is the
    // one that rolls/reuses; dev stays out of that machinery entirely.)
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
      // cadgen-js lives outside the app root, so it must be allowed explicitly;
      // real paths too, in case a checkout reaches it through a link. See
      // scripts/serverFsAllow.mjs.
      allow: resolveServerFsAllow([viewerAppRoot, cadJsPackageRoot], {
        realpath: fs.realpathSync,
      }),
    },
  },
  preview: {
    host: "127.0.0.1",
    allowedHosts: viewerAllowedHosts,
  },
}));
