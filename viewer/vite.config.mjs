import fs from "node:fs";
import http from "node:http";
import net from "node:net";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

import { cadPythonExecutable, cadPythonEnv } from "./scripts/cad-python.mjs";
import { resolveDirectoryRoot as resolveViewerDirectoryRoot } from "./scripts/directoryRoot.mjs";
import { resolveServerFsAllow } from "./scripts/serverFsAllow.mjs";
import { assertNoDeprecatedLocalRootEnv } from "./scripts/viewerEnv.mjs";
import {
  normalizeServerLifetimeMs,
  scheduleProcessShutdown,
} from "./scripts/serverLifetime.mjs";

const DEFAULT_VIEWER_PORT = 3245;

const viewerAppRoot = path.dirname(fileURLToPath(import.meta.url));
const viewerClientRoot = path.join(viewerAppRoot, "src", "client");
const cadJsPackageRoot = resolveCadJsPackageRoot();
const viewerNodeModulesRoot = path.join(viewerAppRoot, "node_modules");
const defaultDirectoryRoot = path.resolve(viewerAppRoot, "..");
const directoryRoot = resolveDirectoryRoot();
const repoRoot = directoryRoot;
const viewerAllowedHosts = normalizeViewerAllowedHosts(process.env.VIEWER_ALLOWED_HOSTS ?? "");
const viewerServerLifetimeMs = normalizeServerLifetimeMs(process.env.VIEWER_SERVER_LIFETIME_MS);
assertNoDeprecatedLocalRootEnv(process.env);

function normalizeViewerAllowedHosts(value) {
  return String(value || "")
    .split(",")
    .map((host) => host.trim())
    .filter(Boolean);
}

function readViewerPackageVersion(appRoot) {
  try {
    const packageJson = JSON.parse(fs.readFileSync(path.join(appRoot, "package.json"), "utf8"));
    return String(packageJson.version || "");
  } catch {
    return "";
  }
}

function findRootPackageSrc(packageDirName) {
  let current = viewerAppRoot;
  for (;;) {
    const candidate = path.join(current, "packages", packageDirName, "src");
    if (
      fs.existsSync(candidate) &&
      fs.existsSync(path.join(current, "packages", packageDirName, "package.json"))
    ) {
      return candidate;
    }
    const next = path.dirname(current);
    if (next === current) {
      return "";
    }
    current = next;
  }
}

function resolveCadJsPackageRoot() {
  const bundledPackageSrc = path.join(viewerAppRoot, "packages", "cadjs", "src");
  if (fs.existsSync(bundledPackageSrc)) {
    return bundledPackageSrc;
  }
  const rootPackageSrc = findRootPackageSrc("cadjs");
  if (rootPackageSrc) {
    return rootPackageSrc;
  }
  const installedPackageSrc = path.join(viewerAppRoot, "node_modules", "cadjs", "src");
  if (fs.existsSync(installedPackageSrc)) {
    return installedPackageSrc;
  }
  // Nothing resolved: name the in-app path so the failure points at this
  // checkout rather than escaping to a parent workbench that may not exist.
  return bundledPackageSrc;
}

function resolveDirectoryRoot() {
  return resolveViewerDirectoryRoot({
    env: process.env,
    cwd: process.cwd(),
    appRoot: viewerAppRoot,
    defaultDirectoryRoot,
  });
}

function findFreePort() {
  return new Promise((resolve, reject) => {
    const probe = net.createServer();
    probe.on("error", reject);
    probe.listen(0, "127.0.0.1", () => {
      const { port } = probe.address();
      probe.close(() => resolve(port));
    });
  });
}

function waitForPythonBackend(port, { timeoutMs = 20000, child = null } = {}) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve) => {
    let settled = false;
    let retryTimer = null;
    const finish = (ready) => {
      if (settled) {
        return;
      }
      settled = true;
      if (retryTimer) {
        clearTimeout(retryTimer);
      }
      child?.off("exit", handleChildExit);
      resolve(ready);
    };
    const handleChildExit = () => finish(false);
    child?.once("exit", handleChildExit);
    const retry = () => {
      if (settled) {
        return;
      }
      if (Date.now() >= deadline) {
        finish(false);
        return;
      }
      retryTimer = setTimeout(attempt, 250);
    };
    const attempt = () => {
      if (settled) {
        return;
      }
      const req = http.get({ host: "127.0.0.1", port, path: "/__cad/server", timeout: 500 }, (res) => {
        res.resume();
        if (res.statusCode === 200) {
          finish(true);
        } else {
          retry();
        }
      });
      req.on("error", retry);
      req.on("timeout", () => {
        req.destroy();
      });
    };
    if (child && child.exitCode !== null) {
      finish(false);
      return;
    }
    attempt();
  });
}

// Dev mode runs the SAME Python backend as production: Vite serves the client
// (with HMR) and proxies /__cad/* to a Python server it spawns. The Python
// backend owns all CAD logic; Vite is purely the frontend dev tool.
function cadViewerBackendProxyPlugin() {
  let child = null;
  let backendPort = 0;
  return {
    name: "cad-viewer-python-backend",
    async configureServer(server) {
      backendPort = await findFreePort();
      const env = cadPythonEnv();
      env.PYTHONPATH = [viewerAppRoot, env.PYTHONPATH].filter(Boolean).join(path.delimiter);
      env.VIEWER_AGENT_START_MODE = env.VIEWER_AGENT_START_MODE || "dev";
      // No --dir: a URL path IS the directory. cwd is the backend's only fallback,
      // used when a request names no directory at all (the bare origin).
      child = spawn(
        cadPythonExecutable(repoRoot),
        ["-m", "server_py.server", "--host", "127.0.0.1", "--port", String(backendPort)],
        { cwd: directoryRoot, env, stdio: "inherit" },
      );
      child.on("error", (error) => {
        console.error(`Failed to start Python CAD Viewer backend: ${error.message}`);
      });
      const ready = await waitForPythonBackend(backendPort, { child });
      if (!ready) {
        if (child && child.exitCode === null) {
          child.kill();
        }
        child = null;
        throw new Error("Python CAD Viewer backend failed startup validation or did not become ready.");
      }
      // Forward every /__cad/* request (method + headers + body + streamed response) to Python.
      server.middlewares.use((req, res, next) => {
        if (!req.url || !req.url.startsWith("/__cad/")) {
          next();
          return;
        }
        const proxyReq = http.request(
          { host: "127.0.0.1", port: backendPort, path: req.url, method: req.method, headers: req.headers },
          (proxyRes) => {
            res.writeHead(proxyRes.statusCode || 502, proxyRes.headers);
            proxyRes.pipe(res);
          },
        );
        proxyReq.on("error", () => {
          if (!res.headersSent) {
            res.statusCode = 502;
          }
          res.end("CAD Viewer backend proxy error");
        });
        req.pipe(proxyReq);
      });
      const stop = () => {
        if (child) {
          child.kill();
          child = null;
        }
      };
      server.httpServer?.once("close", stop);
      process.once("exit", stop);
    },
  };
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

export default defineConfig(({ command }) => ({
  root: viewerAppRoot,
  envPrefix: "VIEWER_",
  plugins: [
    react(),
    cadViewerBackendProxyPlugin(),
    serverLifetimePlugin(),
  ],
  resolve: {
    alias: {
      "@": viewerClientRoot,
      "cadjs": cadJsPackageRoot,
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
    port: DEFAULT_VIEWER_PORT,
    // Fail on a taken port instead of silently rolling to the next one, so dev
    // matches `npm run start`: a Viewer is always on the port you asked for.
    strictPort: true,
    allowedHosts: viewerAllowedHosts,
    fs: {
      // Real paths too: Vite checks ids after resolution, and the develop layout
      // reaches cadjs through a symlink. See scripts/serverFsAllow.mjs.
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
