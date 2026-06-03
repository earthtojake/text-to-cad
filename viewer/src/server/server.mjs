#!/usr/bin/env node
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { createLocalAssetBackend } from "./localAssetBackend.mjs";
import {
  buildHostedViewerServerInfo,
} from "./vercelApi.mjs";
import { createVercelBlobAssetBackend } from "./vercelBlobAssetBackend.mjs";
import {
  createCadViewerApiMiddleware,
  createLocalAssetMiddleware,
  serveDistAsset,
} from "./httpHandlers.mjs";
import {
  DEFAULT_VIEWER_PORT,
  buildViewerServerInfo,
  normalizeViewerPort,
} from "./viewerServerInfo.mjs";
import {
  normalizeViewerDefaultFile,
  normalizeViewerGithubUrl,
} from "../shared/viewerConfig.mjs";
import { resolveDirectoryRoot } from "./directoryRoot.mjs";
import {
  normalizeViewerAssetBackend,
  assertNoDeprecatedLocalRootEnv,
  vercelBlobConfigFromEnv,
  VIEWER_ASSET_BACKENDS,
} from "./viewerEnv.mjs";
import {
  closeHttpServer,
  normalizeServerLifetimeMs,
  scheduleProcessShutdown,
} from "./serverLifetime.mjs";
import {
  applyServerArgsToEnv,
  serverHelpText,
} from "./serverArgs.mjs";

const serverModuleDir = path.dirname(fileURLToPath(import.meta.url));
const viewerAppRoot = path.basename(path.dirname(serverModuleDir)) === "src"
  ? path.resolve(serverModuleDir, "..", "..")
  : path.resolve(serverModuleDir, "..");
const defaultDirectoryRoot = path.resolve(viewerAppRoot, "..");

function readViewerPackageVersion(appRoot) {
  try {
    const packageJson = JSON.parse(fs.readFileSync(path.join(appRoot, "package.json"), "utf8"));
    return String(packageJson.version || "");
  } catch {
    return "";
  }
}

const viewerVersion = readViewerPackageVersion(viewerAppRoot);
const localServerFeatures = [
  "dynamic-root",
  "relative-dir-query",
  "default-dir",
  "directory-activation",
];
let runtime;
try {
  runtime = applyServerArgsToEnv({ argv: process.argv.slice(2), env: process.env, cwd: process.cwd() });
} catch (error) {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exit(1);
}
if (runtime.args.help) {
  process.stdout.write(serverHelpText());
  process.exit(0);
}
const runtimeEnv = runtime.env;
const viewerGit = String(runtimeEnv.VIEWER_GIT || "").trim();
try {
  assertNoDeprecatedLocalRootEnv(runtimeEnv);
} catch (error) {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exit(1);
}
const directoryRoot = resolveDirectoryRoot({
  env: runtimeEnv,
  cwd: process.cwd(),
  appRoot: viewerAppRoot,
  defaultDirectoryRoot,
});
const backendKind = normalizeViewerAssetBackend(runtimeEnv.VIEWER_ASSET_BACKEND);
const port = normalizeViewerPort(runtime.args.port, DEFAULT_VIEWER_PORT);
const host = runtime.args.host || "127.0.0.1";
const serverLifetimeMs = runtime.args.shutdownAfterMs ?? normalizeServerLifetimeMs(runtimeEnv.VIEWER_SERVER_LIFETIME_MS);
const distRoot = path.resolve(viewerAppRoot, "dist");
const backend = backendKind === VIEWER_ASSET_BACKENDS.VERCEL_BLOB
  ? createVercelBlobAssetBackend({
      ...vercelBlobConfigFromEnv(runtimeEnv),
      readOnly: true,
    })
  : createLocalAssetBackend({
      directoryRoot,
      rootDir: runtime.args.rootDir || "",
      defaultFile: normalizeViewerDefaultFile(runtimeEnv.VIEWER_DEFAULT_FILE || ""),
      githubUrl: normalizeViewerGithubUrl(runtimeEnv.VIEWER_GITHUB_URL || ""),
    });
const localAssetBackendEnabled = backend.kind === "local-fs";
const stepArtifactBackendEnabled = localAssetBackendEnabled && typeof backend.generateStepArtifact === "function";
const activeDirectories = new Map();

function trackActiveDirectory(resolvedRoot) {
  const dir = String(resolvedRoot?.dir || "").trim();
  const rootPath = String(resolvedRoot?.rootPath || "").trim();
  if (!dir || !rootPath) {
    return;
  }
  activeDirectories.set(rootPath, {
    dir,
    rootPath,
    rootName: String(resolvedRoot?.rootName || path.basename(rootPath) || dir),
  });
}

function activeDirectoryOptions({ rootDir = "" } = {}) {
  const options = [...activeDirectories.values()];
  const requestedRootDir = String(rootDir || "").trim();
  if (requestedRootDir && !options.some((option) => option.dir === requestedRootDir)) {
    options.push({ dir: requestedRootDir });
  }
  return options;
}

if (localAssetBackendEnabled) {
  try {
    trackActiveDirectory(backend.resolveRoot(""));
  } catch (error) {
    process.stderr.write(`Failed to activate default CAD Viewer directory: ${error instanceof Error ? error.message : String(error)}\n`);
  }
}

const middlewares = [
  createCadViewerApiMiddleware({
    backend,
    enableStepArtifactBackend: stepArtifactBackendEnabled,
    claimDisabledStepArtifactRoute: true,
    serverInfo: ({ rootDir = "" } = {}) => {
      if (!localAssetBackendEnabled) {
        return buildHostedViewerServerInfo({ backend, env: runtimeEnv, rootDir: "" });
      }
      const infoRootDir = rootDir || "";
      return buildViewerServerInfo({
        directoryRoot,
        rootDir: infoRootDir,
        port,
        pid: process.pid,
        backend: "local-fs",
        dynamicRoot: true,
        stepArtifactGenerationAvailable: stepArtifactBackendEnabled,
        viewerVersion,
        git: viewerGit,
        serverFeatures: localServerFeatures,
        activeDirectories: activeDirectoryOptions({ rootDir: infoRootDir }),
      });
    },
    onCatalogActivated: (resolvedRoot) => {
      trackActiveDirectory(resolvedRoot);
    },
    onDirectoryActivated: (resolvedRoot) => {
      trackActiveDirectory(resolvedRoot);
    },
  }),
  ...(localAssetBackendEnabled ? [createLocalAssetMiddleware({ backend })] : []),
  serveDistAsset({ distRoot }),
];

function runMiddleware(index, req, res) {
  const middleware = middlewares[index];
  if (!middleware) {
    res.statusCode = 404;
    res.end("Not found");
    return;
  }
  middleware(req, res, () => runMiddleware(index + 1, req, res));
}

const server = http.createServer((req, res) => runMiddleware(0, req, res));

server.listen(port, host, () => {
  console.log(`CAD Viewer backend listening on http://${host}:${port}/ (${backend.kind})`);
  if (serverLifetimeMs !== null) {
    scheduleProcessShutdown({
      lifetimeMs: serverLifetimeMs,
      label: "CAD Viewer backend",
      close: () => closeHttpServer(server),
    });
  }
});
