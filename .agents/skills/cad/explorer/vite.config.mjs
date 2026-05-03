import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import {
  DEFAULT_EXPLORER_ROOT_DIR,
  EXPLORER_SKIPPED_DIRECTORIES,
  isCatalogRelevantPath,
  isServedCadAsset,
  normalizeExplorerRootDir,
  repoRelativePath,
  resolveExplorerRoot,
  scanCadDirectory,
} from "./lib/cadDirectoryScanner.mjs";
import {
  normalizeExplorerDefaultFile,
  normalizeExplorerGithubUrl,
} from "./lib/explorerConfig.mjs";
import {
  readOttoAuthLocalAgentCredential,
  writeOttoAuthLocalAgentCredential,
} from "./lib/ottoAuthLocalCredentials.mjs";

const DEFAULT_EXPLORER_PORT = 4178;
const resolvedPort = Number.parseInt(process.env.EXPLORER_PORT || "", 10);
const explorerPort = Number.isFinite(resolvedPort) ? resolvedPort : DEFAULT_EXPLORER_PORT;
const explorerAppRoot = path.dirname(fileURLToPath(import.meta.url));
const defaultWorkspaceRoot = path.resolve(explorerAppRoot, "../../../..");
const workspaceRoot = resolveWorkspaceRoot();
const repoRoot = workspaceRoot;
const buildExplorerRootDir = normalizeExplorerRootDir(process.env.EXPLORER_ROOT_DIR ?? DEFAULT_EXPLORER_ROOT_DIR);
const buildExplorerDefaultFile = normalizeExplorerDefaultFile(process.env.EXPLORER_DEFAULT_FILE ?? "");
const buildExplorerGithubUrl = normalizeExplorerGithubUrl(process.env.EXPLORER_GITHUB_URL ?? "");
const buildOttoAuthBaseUrl = normalizeOttoAuthBaseUrl(process.env.EXPLORER_OTTOAUTH_BASE_URL ?? "http://127.0.0.1:3000");

function resolveWorkspaceRoot() {
  if (process.env.EXPLORER_WORKSPACE_ROOT) {
    return path.resolve(process.env.EXPLORER_WORKSPACE_ROOT);
  }

  const resolvedExplorerAppRoot = path.resolve(explorerAppRoot);
  for (const candidate of [process.env.INIT_CWD, process.cwd()]) {
    if (!candidate) {
      continue;
    }
    const resolvedCandidate = path.resolve(candidate);
    if (resolvedCandidate !== resolvedExplorerAppRoot && !pathIsInside(resolvedCandidate, resolvedExplorerAppRoot)) {
      return resolvedCandidate;
    }
  }

  return defaultWorkspaceRoot;
}

function withExplorerConfig(catalog) {
  return {
    ...catalog,
    config: {
      ...(catalog?.config && typeof catalog.config === "object" ? catalog.config : {}),
      defaultFile: buildExplorerDefaultFile,
      githubUrl: buildExplorerGithubUrl,
    },
  };
}

function emptyCatalog(rootDir = DEFAULT_EXPLORER_ROOT_DIR) {
  const normalizedDir = normalizeExplorerRootDir(rootDir);
  return {
    schemaVersion: 3,
    root: {
      dir: normalizedDir,
      name: normalizedDir ? path.basename(normalizedDir) : path.basename(workspaceRoot),
      path: normalizedDir,
    },
    entries: [],
  };
}

function readCadCatalog(rootDir = buildExplorerRootDir) {
  try {
    return withExplorerConfig(scanCadDirectory({ repoRoot, rootDir }));
  } catch {
    return withExplorerConfig(emptyCatalog(rootDir));
  }
}

function pathIsInside(childPath, parentPath) {
  const relativePath = path.relative(path.resolve(parentPath), path.resolve(childPath));
  return Boolean(relativePath) && !relativePath.startsWith("..") && !path.isAbsolute(relativePath);
}

function serveStaticFile(root, req, res, next, { allow } = {}) {
  const requestPath = String(req.url || "").replace(/\?.*$/, "");
  let decodedRequestPath = "";
  try {
    decodedRequestPath = decodeURIComponent(requestPath);
  } catch {
    res.statusCode = 400;
    res.end("Bad request");
    return true;
  }
  const filePath = path.resolve(root, decodedRequestPath.replace(/^\/+/, ""));
  if (
    !(filePath === path.resolve(root) || pathIsInside(filePath, root))
    || (typeof allow === "function" && !allow(filePath))
  ) {
    res.statusCode = 403;
    res.end("Forbidden");
    return true;
  }
  fs.stat(filePath, (error, stats) => {
    if (res.destroyed) {
      return;
    }
    if (error || !stats.isFile()) {
      next();
      return;
    }
    if (path.extname(filePath).toLowerCase() === ".js" || path.extname(filePath).toLowerCase() === ".mjs") {
      res.setHeader("content-type", "text/javascript; charset=utf-8");
    }
    res.setHeader("content-length", String(stats.size));
    const stream = fs.createReadStream(filePath);
    res.on("close", () => {
      if (!res.writableEnded) {
        stream.destroy();
      }
    });
    stream.on("error", () => {
      if (!res.headersSent) {
        next();
      } else {
        res.destroy();
      }
    });
    stream.pipe(res);
  });
  return true;
}

function copyRecursiveFiltered(sourceRoot, destinationRoot, predicate) {
  if (!fs.existsSync(sourceRoot)) {
    return;
  }
  for (const entry of fs.readdirSync(sourceRoot, { withFileTypes: true })) {
    const sourcePath = path.join(sourceRoot, entry.name);
    const destinationPath = path.join(destinationRoot, entry.name);
    if (entry.isDirectory()) {
      if (EXPLORER_SKIPPED_DIRECTORIES.has(entry.name)) {
        continue;
      }
      copyRecursiveFiltered(sourcePath, destinationPath, predicate);
      continue;
    }
    if (!predicate(sourcePath)) {
      continue;
    }
    fs.mkdirSync(path.dirname(destinationPath), { recursive: true });
    fs.copyFileSync(sourcePath, destinationPath);
  }
}

function sendJson(res, statusCode, payload) {
  res.statusCode = statusCode;
  res.setHeader("content-type", "application/json; charset=utf-8");
  res.setHeader("cache-control", "no-store");
  res.end(JSON.stringify(payload));
}

function normalizeOttoAuthBaseUrl(value) {
  try {
    const url = new URL(String(value || "").trim() || "http://127.0.0.1:3000");
    url.pathname = url.pathname.replace(/\/+$/, "");
    url.search = "";
    url.hash = "";
    return url.toString().replace(/\/+$/, "");
  } catch {
    return "http://127.0.0.1:3000";
  }
}

function readRequestBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on("data", (chunk) => chunks.push(Buffer.from(chunk)));
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });
}

function forwardCookieHeader(req) {
  return req.headers.cookie ? { "cookie": req.headers.cookie } : {};
}

async function proxyOttoAuthJson(req, res, {
  path: upstreamPath,
  method = req.method,
  body = null,
  headers = {},
} = {}) {
  try {
    const upstreamResponse = await fetch(`${buildOttoAuthBaseUrl}${upstreamPath}`, {
      method,
      headers: {
        "accept": "application/json",
        ...forwardCookieHeader(req),
        ...headers,
      },
      ...(body == null ? {} : { body }),
      redirect: "manual",
    });
    const responseBody = await upstreamResponse.text();
    res.statusCode = upstreamResponse.status;
    res.setHeader(
      "content-type",
      upstreamResponse.headers.get("content-type") || "application/json; charset=utf-8"
    );
    res.setHeader("cache-control", "no-store");
    res.end(responseBody);
  } catch (error) {
    sendJson(res, 502, {
      error: `Could not reach OttoAuth at ${buildOttoAuthBaseUrl}.`,
      detail: error instanceof Error ? error.message : String(error),
    });
  }
}

async function proxyOttoAuthRaw(req, res, {
  path: upstreamPath,
  method = req.method,
  body = null,
  headers = {},
} = {}) {
  try {
    const upstreamResponse = await fetch(`${buildOttoAuthBaseUrl}${upstreamPath}`, {
      method,
      headers: {
        "accept": "application/json",
        ...forwardCookieHeader(req),
        ...headers,
      },
      ...(body == null ? {} : { body }),
      redirect: "manual",
    });
    const responseBody = await upstreamResponse.text();
    res.statusCode = upstreamResponse.status;
    res.setHeader(
      "content-type",
      upstreamResponse.headers.get("content-type") || "application/json; charset=utf-8"
    );
    res.setHeader("cache-control", "no-store");
    res.end(responseBody);
  } catch (error) {
    sendJson(res, 502, {
      error: `Could not reach OttoAuth at ${buildOttoAuthBaseUrl}.`,
      detail: error instanceof Error ? error.message : String(error),
    });
  }
}

async function provisionLocalOttoAuthAgent(req, res, body = null) {
  try {
    const upstreamResponse = await fetch(`${buildOttoAuthBaseUrl}/api/sdk/local-agent`, {
      method: "POST",
      headers: {
        "accept": "application/json",
        "content-type": "application/json",
        ...forwardCookieHeader(req),
      },
      body: body && body.length
        ? body
        : JSON.stringify({
            tool_name: "cad-explorer",
            app_id: "cad-explorer",
            app_name: "CAD Explorer",
            agent_name: "CAD Explorer local coding agent",
          }),
      redirect: "manual",
    });
    const responseText = await upstreamResponse.text();
    let payload = null;
    try {
      payload = responseText ? JSON.parse(responseText) : null;
    } catch {
      payload = { error: responseText };
    }

    if (!upstreamResponse.ok) {
      sendJson(res, upstreamResponse.status, payload || {
        error: `OttoAuth request failed with status ${upstreamResponse.status}.`,
      });
      return;
    }

    const stored = writeOttoAuthLocalAgentCredential({
      workspaceRoot,
      payload,
      baseUrl: buildOttoAuthBaseUrl,
    });
    sendJson(res, 200, stored);
  } catch (error) {
    sendJson(res, 502, {
      error: `Could not provision local OttoAuth agent credentials from ${buildOttoAuthBaseUrl}.`,
      detail: error instanceof Error ? error.message : String(error),
    });
  }
}

async function submitOttoAuthAgentTask(res, body) {
  const credential = readOttoAuthLocalAgentCredential({ workspaceRoot });
  if (!credential) {
    sendJson(res, 409, {
      error:
        "No local OttoAuth linked agent credentials are available. Sign in with Google through OttoAuth, then reopen Buy Parts Now.",
    });
    return;
  }

  let payload = null;
  try {
    payload = body && body.length ? JSON.parse(body.toString("utf8")) : {};
  } catch {
    sendJson(res, 400, { error: "Invalid JSON body." });
    return;
  }

  try {
    const upstreamResponse = await fetch(`${buildOttoAuthBaseUrl}/api/sdk/checkout`, {
      method: "POST",
      headers: {
        "accept": "application/json",
        "content-type": "application/json",
      },
      body: JSON.stringify({
        ...payload,
        username: credential.username,
        private_key: credential.privateKey,
      }),
    });
    const responseBody = await upstreamResponse.text();
    res.statusCode = upstreamResponse.status;
    res.setHeader(
      "content-type",
      upstreamResponse.headers.get("content-type") || "application/json; charset=utf-8"
    );
    res.setHeader("cache-control", "no-store");
    res.end(responseBody);
  } catch (error) {
    sendJson(res, 502, {
      error: `Could not submit OttoAuth agent task to ${buildOttoAuthBaseUrl}.`,
      detail: error instanceof Error ? error.message : String(error),
    });
  }
}

function cadCatalogPlugin() {
  const virtualId = "virtual:cad-catalog";
  const resolvedVirtualId = `\0${virtualId}`;
  let resolvedConfig = null;
  const activeDirectories = new Map();
  const refreshTimers = new Map();

  function activateDirectory(server, rootDir) {
    const resolved = resolveExplorerRoot(repoRoot, rootDir);
    const wasActive = activeDirectories.has(resolved.rootPath);
    activeDirectories.set(resolved.rootPath, resolved.dir);
    if (!wasActive) {
      server.watcher.add(resolved.rootPath);
    }
    return resolved;
  }

  function scheduleCatalogRefresh(server, rootPath, dir) {
    if (refreshTimers.has(rootPath)) {
      clearTimeout(refreshTimers.get(rootPath));
    }
    refreshTimers.set(rootPath, setTimeout(() => {
      refreshTimers.delete(rootPath);
      const virtualCatalogModule = server.moduleGraph.getModuleById(resolvedVirtualId);
      if (virtualCatalogModule) {
        server.moduleGraph.invalidateModule(virtualCatalogModule);
      }
      server.ws.send({
        type: "custom",
        event: "cad-catalog:changed",
        data: { dir },
      });
    }, 150));
  }

  function notifyChangedPath(server, changedPath) {
    const resolvedChangedPath = path.resolve(changedPath);
    if (!isCatalogRelevantPath(resolvedChangedPath)) {
      return;
    }
    for (const [rootPath, dir] of activeDirectories.entries()) {
      if (resolvedChangedPath === rootPath || pathIsInside(resolvedChangedPath, rootPath)) {
        scheduleCatalogRefresh(server, rootPath, dir);
      }
    }
  }

  return {
    name: "cad-catalog",
    configResolved(config) {
      resolvedConfig = config;
    },
    resolveId(id) {
      if (id === virtualId) {
        return resolvedVirtualId;
      }
      return null;
    },
    load(id) {
      if (id !== resolvedVirtualId) {
        return null;
      }
      const catalog = readCadCatalog(buildExplorerRootDir);
      return `export default ${JSON.stringify(catalog)};`;
    },
    configureServer(server) {
      const servedExplorerRoot = activateDirectory(server, buildExplorerRootDir);
      server.middlewares.use(async (req, res, next) => {
        const requestUrl = new URL(req.url || "/", "http://localhost");
        if (requestUrl.pathname !== "/__ottoauth/me") {
          next();
          return;
        }
        if (req.method !== "GET") {
          res.setHeader("allow", "GET");
          sendJson(res, 405, { error: "Method not allowed." });
          return;
        }
        await proxyOttoAuthJson(req, res, {
          path: "/api/sdk/me?app_id=cad-explorer&app_name=CAD%20Explorer",
          method: "GET",
        });
      });
      server.middlewares.use(async (req, res, next) => {
        const requestUrl = new URL(req.url || "/", "http://localhost");
        if (requestUrl.pathname !== "/__ottoauth/local-agent") {
          next();
          return;
        }
        if (req.method !== "POST" && req.method !== "GET") {
          res.setHeader("allow", "GET, POST");
          sendJson(res, 405, { error: "Method not allowed." });
          return;
        }

        let body = null;
        if (req.method === "POST") {
          try {
            body = await readRequestBody(req);
          } catch (error) {
            sendJson(res, 400, {
              error: error instanceof Error ? error.message : "Could not read request body.",
            });
            return;
          }
        }

        await provisionLocalOttoAuthAgent(req, res, body);
      });
      server.middlewares.use(async (req, res, next) => {
        const requestUrl = new URL(req.url || "/", "http://localhost");
        if (requestUrl.pathname !== "/__ottoauth/files") {
          next();
          return;
        }
        if (req.method !== "POST") {
          res.setHeader("allow", "POST");
          sendJson(res, 405, { error: "Method not allowed." });
          return;
        }

        let body;
        try {
          body = await readRequestBody(req);
        } catch (error) {
          sendJson(res, 400, {
            error: error instanceof Error ? error.message : "Could not read request body.",
          });
          return;
        }

        await proxyOttoAuthRaw(req, res, {
          path: "/api/sdk/files",
          method: "POST",
          body,
          headers: {
            "content-type": req.headers["content-type"] || "application/octet-stream",
          },
        });
      });
      server.middlewares.use(async (req, res, next) => {
        const requestUrl = new URL(req.url || "/", "http://localhost");
        if (requestUrl.pathname !== "/__ottoauth/human-task") {
          next();
          return;
        }
        if (req.method !== "POST") {
          res.setHeader("allow", "POST");
          sendJson(res, 405, { error: "Method not allowed." });
          return;
        }

        let body;
        try {
          body = await readRequestBody(req);
        } catch (error) {
          sendJson(res, 400, {
            error: error instanceof Error ? error.message : "Could not read request body.",
          });
          return;
        }

        await proxyOttoAuthJson(req, res, {
          path: "/api/sdk/checkout",
          method: "POST",
          body,
          headers: {
            "content-type": req.headers["content-type"] || "application/json",
          },
        });
      });
      server.middlewares.use(async (req, res, next) => {
        const requestUrl = new URL(req.url || "/", "http://localhost");
        if (requestUrl.pathname !== "/__ottoauth/agent-task") {
          next();
          return;
        }
        if (req.method !== "POST") {
          res.setHeader("allow", "POST");
          sendJson(res, 405, { error: "Method not allowed." });
          return;
        }

        let body;
        try {
          body = await readRequestBody(req);
        } catch (error) {
          sendJson(res, 400, {
            error: error instanceof Error ? error.message : "Could not read request body.",
          });
          return;
        }

        await submitOttoAuthAgentTask(res, body);
      });
      server.middlewares.use((req, res, next) => {
        const requestUrl = new URL(req.url || "/", "http://localhost");
        if (requestUrl.pathname !== "/__cad/catalog") {
          next();
          return;
        }
        let catalog;
        try {
          const resolved = activateDirectory(server, buildExplorerRootDir);
          catalog = withExplorerConfig(scanCadDirectory({ repoRoot, rootDir: resolved.dir }));
        } catch (error) {
          sendJson(res, 400, {
            error: error instanceof Error ? error.message : String(error),
          });
          return;
        }
        sendJson(res, 200, catalog);
      });
      server.middlewares.use((req, res, next) => {
        const requestPath = String(req.url || "").replace(/\?.*$/, "");
        let decodedRequestPath = "";
        try {
          decodedRequestPath = decodeURIComponent(requestPath);
        } catch {
          next();
          return;
        }
        const candidatePath = path.resolve(repoRoot, decodedRequestPath.replace(/^\/+/, ""));
        if (!isServedCadAsset(candidatePath)) {
          next();
          return;
        }
        if (!(candidatePath === servedExplorerRoot.rootPath || pathIsInside(candidatePath, servedExplorerRoot.rootPath))) {
          res.statusCode = 403;
          res.end("Forbidden");
          return;
        }
        serveStaticFile(repoRoot, req, res, next, {
          allow: (filePath) => (
            isServedCadAsset(filePath) &&
            (filePath === servedExplorerRoot.rootPath || pathIsInside(filePath, servedExplorerRoot.rootPath))
          ),
        });
      });
      for (const eventName of ["add", "change", "unlink"]) {
        server.watcher.on(eventName, (changedPath) => notifyChangedPath(server, changedPath));
      }
    },
    writeBundle() {
      const outDir = resolvedConfig?.build?.outDir || "dist";
      const resolved = resolveExplorerRoot(repoRoot, buildExplorerRootDir);
      const cadDestinationRoot = path.resolve(explorerAppRoot, outDir, repoRelativePath(repoRoot, resolved.rootPath));
      copyRecursiveFiltered(resolved.rootPath, cadDestinationRoot, (filePath) => {
        return isServedCadAsset(filePath);
      });
    },
  };
}

export default defineConfig({
  root: explorerAppRoot,
  envPrefix: "EXPLORER_",
  plugins: [react(), cadCatalogPlugin()],
  resolve: {
    alias: {
      "@": explorerAppRoot,
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
  server: {
    host: "127.0.0.1",
    port: explorerPort,
    strictPort: true,
  },
  preview: {
    host: "127.0.0.1",
    port: explorerPort,
    strictPort: true,
  },
});
