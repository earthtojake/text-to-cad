import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import {
  isCatalogRelevantPath,
} from "./src/server/catalog/cadDirectoryScanner.mjs";
import {
  normalizeViewerDefaultFile,
  normalizeViewerGithubUrl,
} from "./src/shared/viewerConfig.mjs";
import {
  DEFAULT_VIEWER_PORT,
  buildViewerServerInfo,
} from "./src/server/viewerServerInfo.mjs";
import {
  removeViewerServerRegistryEntry,
  writeViewerServerRegistry,
} from "./src/server/viewerServerRegistry.mjs";
import {
  pathIsInside,
} from "cadjs/lib/pathUtils.mjs";
import { resolveDirectoryRoot as resolveViewerDirectoryRoot } from "./src/server/directoryRoot.mjs";
import { createLocalAssetBackend } from "./src/server/localAssetBackend.mjs";
import {
  createCadViewerApiMiddleware,
  createLocalAssetMiddleware,
} from "./src/server/httpHandlers.mjs";
import {
  assertNoDeprecatedLocalRootEnv,
  normalizeViewerAssetBackend,
} from "./src/server/viewerEnv.mjs";
import {
  normalizeServerLifetimeMs,
  scheduleProcessShutdown,
} from "./src/server/serverLifetime.mjs";

const viewerAppRoot = path.dirname(fileURLToPath(import.meta.url));
const viewerClientRoot = path.join(viewerAppRoot, "src", "client");
const cadJsPackageRoot = resolveCadJsPackageRoot();
const viewerNodeModulesRoot = path.join(viewerAppRoot, "node_modules");
const defaultDirectoryRoot = path.resolve(viewerAppRoot, "..");
const directoryRoot = resolveDirectoryRoot();
const repoRoot = directoryRoot;
normalizeViewerAssetBackend(process.env.VIEWER_ASSET_BACKEND);
const buildViewerDefaultFile = normalizeViewerDefaultFile(process.env.VIEWER_DEFAULT_FILE ?? "");
const buildViewerGithubUrl = normalizeViewerGithubUrl(process.env.VIEWER_GITHUB_URL ?? "");
const buildViewerDefaultDir = String(process.env.VIEWER_DEFAULT_DIR || "").trim();
const viewerAllowedHosts = normalizeViewerAllowedHosts(process.env.VIEWER_ALLOWED_HOSTS ?? "");
const viewerServerLifetimeMs = normalizeServerLifetimeMs(process.env.VIEWER_SERVER_LIFETIME_MS);
assertNoDeprecatedLocalRootEnv(process.env);
const viewerVersion = readViewerPackageVersion(viewerAppRoot);
const viewerGit = String(process.env.VIEWER_GIT || "").trim();
const localServerFeatures = [
  "dynamic-root",
  "relative-dir-query",
  "default-dir",
  "directory-activation",
];
const localAssetBackend = createLocalAssetBackend({
  directoryRoot,
  rootDir: buildViewerDefaultDir,
  defaultFile: buildViewerDefaultFile,
  githubUrl: buildViewerGithubUrl,
});

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
  const installedPackageSrc = path.join(viewerAppRoot, "node_modules", "cadjs", "src");
  if (fs.existsSync(installedPackageSrc)) {
    return installedPackageSrc;
  }
  const rootPackageSrc = findRootPackageSrc("cadjs");
  return rootPackageSrc || path.resolve(viewerAppRoot, "../packages/cadjs/src");
}

function resolveDirectoryRoot() {
  return resolveViewerDirectoryRoot({
    env: process.env,
    cwd: process.cwd(),
    appRoot: viewerAppRoot,
    defaultDirectoryRoot,
  });
}

function viteServerPort(server) {
  const address = server?.httpServer?.address?.();
  return address && typeof address === "object" && Number.isInteger(address.port)
    ? address.port
    : DEFAULT_VIEWER_PORT;
}

function isGenerationStatusFilePath(filePath) {
  const name = path.basename(String(filePath || ""));
  return name.startsWith(".") && name.endsWith(".generation.lock.json");
}

function cadCatalogPlugin({ enableStepArtifactBackend = false } = {}) {
  const activeDirectories = new Map();
  const refreshTimers = new Map();
  const pendingRefreshes = new Map();

  function activateDirectory(server, resolvedRoot) {
    const resolved = resolvedRoot && typeof resolvedRoot === "object"
      ? resolvedRoot
      : localAssetBackend.resolveRoot(resolvedRoot);
    const wasActive = activeDirectories.has(resolved.rootPath);
    activeDirectories.set(resolved.rootPath, {
      dir: resolved.dir || "",
    });
    if (!wasActive) {
      server.watcher.add(resolved.rootPath);
    }
    return resolved;
  }

  function activeDirectoryOptions({ rootDir = "" } = {}) {
    const options = [];
    const addOption = (option = {}) => {
      const dir = String(option.dir || "").trim();
      if (!dir) {
        return;
      }
      const rootPath = String(option.rootPath || "").trim();
      if (options.some((current) => current.dir === dir || (rootPath && current.rootPath === rootPath))) {
        return;
      }
      options.push({
        dir,
        rootPath,
        rootName: String(option.rootName || (rootPath ? path.basename(rootPath) : "") || dir),
      });
    };
    for (const [rootPath, activeRoot] of activeDirectories.entries()) {
      addOption({
        dir: activeRoot.dir,
        rootPath,
        rootName: path.basename(rootPath),
      });
    }
    addOption({ dir: rootDir });
    return options;
  }

  function scheduleCatalogRefresh(server, rootPath, activeRoot = {}, changedPath = "") {
    const rootState = typeof activeRoot === "string"
      ? { dir: activeRoot }
      : {
          dir: String(activeRoot?.dir || ""),
        };
    if (refreshTimers.has(rootPath)) {
      clearTimeout(refreshTimers.get(rootPath));
    }
    const pending = pendingRefreshes.get(rootPath) || {
      dir: rootState.dir,
      paths: new Set(),
      full: false,
    };
    pending.dir = rootState.dir;
    if (changedPath) {
      pending.paths.add(path.resolve(changedPath));
    } else {
      pending.full = true;
    }
    pendingRefreshes.set(rootPath, pending);
    refreshTimers.set(rootPath, setTimeout(() => {
      refreshTimers.delete(rootPath);
      const nextRefresh = pendingRefreshes.get(rootPath) || {
        dir: rootState.dir,
        paths: new Set(),
        full: true,
      };
      pendingRefreshes.delete(rootPath);
      try {
        if (nextRefresh.full || typeof localAssetBackend.refreshCatalogForPath !== "function") {
          localAssetBackend.refreshCatalog({ rootDir: nextRefresh.dir });
        } else {
          for (const filePath of nextRefresh.paths) {
            localAssetBackend.refreshCatalogForPath({
              rootDir: nextRefresh.dir,
              filePath,
            });
          }
        }
      } catch (error) {
        console.warn("Failed to refresh CAD catalog", error);
      }
      server.ws.send({
        type: "custom",
        event: "cad-catalog:changed",
        data: { dir: nextRefresh.dir },
      });
    }, 150));
  }

  function notifyChangedPath(server, changedPath) {
    const resolvedChangedPath = path.resolve(changedPath);
    for (const [rootPath, activeRoot] of activeDirectories.entries()) {
      if (resolvedChangedPath === rootPath || pathIsInside(resolvedChangedPath, rootPath)) {
        if (isGenerationStatusFilePath(resolvedChangedPath)) {
          server.ws.send({
            type: "custom",
            event: "cad-generation-status:changed",
            data: { dir: activeRoot.dir },
          });
          continue;
        }
        if (isCatalogRelevantPath(resolvedChangedPath)) {
          scheduleCatalogRefresh(server, rootPath, activeRoot, resolvedChangedPath);
        }
      }
    }
  }

  return {
    name: "cad-catalog",
    configureServer(server) {
      let activeServerInfo = null;
      try {
        activateDirectory(server, localAssetBackend.resolveRoot(""));
      } catch (error) {
        console.warn("Failed to activate default CAD Viewer directory", error);
      }
      const currentServerInfo = ({ rootDir = "" } = {}) => {
        const infoRootDir = rootDir || "";
        activeServerInfo = buildViewerServerInfo({
          directoryRoot: repoRoot,
          rootDir: infoRootDir,
          port: viteServerPort(server),
          pid: process.pid,
          backend: "local-fs",
          dynamicRoot: true,
          stepArtifactGenerationAvailable: enableStepArtifactBackend,
          viewerVersion,
          git: viewerGit,
          serverFeatures: localServerFeatures,
          activeDirectories: activeDirectoryOptions({ rootDir: infoRootDir }),
        });
        return activeServerInfo;
      };
      const registerServer = () => {
        writeViewerServerRegistry(currentServerInfo());
      };
      if (server.httpServer?.listening) {
        registerServer();
      } else {
        server.httpServer?.once("listening", registerServer);
      }
      server.httpServer?.once("close", () => {
        removeViewerServerRegistryEntry(activeServerInfo || currentServerInfo());
      });
      server.middlewares.use(createCadViewerApiMiddleware({
        backend: localAssetBackend,
        enableStepArtifactBackend,
        serverInfo: currentServerInfo,
        onCatalogActivated: (resolvedRoot) => {
          activateDirectory(server, resolvedRoot);
        },
        onDirectoryActivated: (resolvedRoot) => {
          activateDirectory(server, resolvedRoot);
        },
        onCatalogChanged: (resolvedRoot) => {
          scheduleCatalogRefresh(server, resolvedRoot.rootPath, { dir: resolvedRoot.dir });
        },
      }));
      server.middlewares.use(createLocalAssetMiddleware({
        backend: localAssetBackend,
      }));
      for (const eventName of ["add", "change", "unlink"]) {
        server.watcher.on(eventName, (changedPath) => notifyChangedPath(server, changedPath));
      }
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
    cadCatalogPlugin({ enableStepArtifactBackend: command === "serve" }),
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
    allowedHosts: viewerAllowedHosts,
  },
  preview: {
    host: "127.0.0.1",
    allowedHosts: viewerAllowedHosts,
  },
}));
