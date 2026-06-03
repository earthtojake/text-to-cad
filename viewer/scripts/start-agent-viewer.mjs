#!/usr/bin/env node
import { execFileSync, spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  DEFAULT_VIEWER_PORT,
  VIEWER_SERVER_API_VERSION,
  VIEWER_SERVER_APP_ID,
} from "../src/server/viewerServerInfo.mjs";
import {
  readViewerServerRegistry,
} from "../src/server/viewerServerRegistry.mjs";
import { parseServerLifetimeMs } from "../src/server/serverLifetime.mjs";

const scriptPath = fileURLToPath(import.meta.url);
const defaultPackageRoot = path.resolve(path.dirname(scriptPath), "..");
const startModeFlag = "--viewer-start-mode";
const startModes = new Set(["auto", "dev", "serve"]);
const defaultAgentHost = "127.0.0.1";
const defaultPortScanLimit = 64;
const probeTimeoutMs = 350;

function requiredValue(argv, index, flag) {
  const value = argv[index + 1];
  if (!value || value.startsWith("--")) {
    throw new Error(`${flag} requires a value`);
  }
  return value;
}

function normalizeStartMode(value, flag = startModeFlag) {
  const mode = String(value || "").trim();
  if (!startModes.has(mode)) {
    throw new Error(`${flag} must be one of: auto, dev, serve.`);
  }
  return mode;
}

function parseAgentPort(value, flag = "--port") {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  if (!Number.isInteger(parsed) || parsed <= 0 || parsed > 65535) {
    throw new Error(`${flag} must be a TCP port from 1 to 65535`);
  }
  return parsed;
}

function parsePositiveInteger(value, flag) {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    throw new Error(`${flag} must be a positive integer`);
  }
  return parsed;
}

export function parseAgentStartArgs(argv = []) {
  const options = {
    startMode: "auto",
    forwardedArgs: [],
    shutdownAfterMs: null,
    portScanLimit: defaultPortScanLimit,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg.startsWith(`${startModeFlag}=`)) {
      options.startMode = normalizeStartMode(arg.slice(startModeFlag.length + 1));
      continue;
    }
    if (arg === startModeFlag) {
      options.startMode = normalizeStartMode(requiredValue(argv, index, arg));
      index += 1;
      continue;
    }
    if (arg.startsWith("--port-scan-limit=")) {
      options.portScanLimit = parsePositiveInteger(arg.slice("--port-scan-limit=".length), "--port-scan-limit");
      continue;
    }
    if (arg === "--port-scan-limit") {
      options.portScanLimit = parsePositiveInteger(requiredValue(argv, index, arg), arg);
      index += 1;
      continue;
    }
    if (arg.startsWith("--shutdown-after=")) {
      options.shutdownAfterMs = parseServerLifetimeMs(arg.slice("--shutdown-after=".length), "--shutdown-after");
      options.forwardedArgs.push(arg);
      continue;
    }
    if (arg === "--shutdown-after") {
      const value = requiredValue(argv, index, arg);
      options.shutdownAfterMs = parseServerLifetimeMs(value, arg);
      options.forwardedArgs.push(arg, value);
      index += 1;
      continue;
    }
    options.forwardedArgs.push(arg);
  }

  return options;
}

export function stripShutdownAfterArgs(argv = []) {
  const stripped = [];
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg.startsWith("--shutdown-after=")) {
      continue;
    }
    if (arg === "--shutdown-after") {
      index += 1;
      continue;
    }
    stripped.push(arg);
  }
  return stripped;
}

export function forwardedServerTarget(argv = []) {
  const target = {
    host: defaultAgentHost,
    port: DEFAULT_VIEWER_PORT,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg.startsWith("--host=")) {
      target.host = arg.slice("--host=".length).trim() || defaultAgentHost;
      continue;
    }
    if (arg === "--host") {
      target.host = requiredValue(argv, index, arg).trim() || defaultAgentHost;
      index += 1;
      continue;
    }
    if (arg.startsWith("--port=")) {
      target.port = parseAgentPort(arg.slice("--port=".length), "--port");
      continue;
    }
    if (arg === "--port") {
      target.port = parseAgentPort(requiredValue(argv, index, arg), arg);
      index += 1;
    }
  }

  return target;
}

export function replaceForwardedPort(argv = [], port = DEFAULT_VIEWER_PORT) {
  const normalizedPort = parseAgentPort(port, "--port");
  const nextArgs = [];
  let replaced = false;

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg.startsWith("--port=")) {
      nextArgs.push(`--port=${normalizedPort}`);
      replaced = true;
      continue;
    }
    if (arg === "--port") {
      nextArgs.push(arg, String(normalizedPort));
      replaced = true;
      index += 1;
      continue;
    }
    nextArgs.push(arg);
  }

  if (!replaced) {
    nextArgs.push("--port", String(normalizedPort));
  }
  return nextArgs;
}

export function isSymlinkPath(filePath) {
  if (!filePath) {
    return false;
  }
  try {
    return fs.lstatSync(filePath).isSymbolicLink();
  } catch {
    return false;
  }
}

export function selectAgentStartMode({
  requestedMode = "auto",
  npmConfigPrefix = "",
  npmPackageJson = "",
} = {}) {
  const mode = normalizeStartMode(requestedMode);
  if (mode !== "auto") {
    return mode;
  }
  const packagePrefix = npmConfigPrefix
    || (npmPackageJson ? path.dirname(npmPackageJson) : "")
    || process.env.npm_config_prefix
    || (process.env.npm_package_json ? path.dirname(process.env.npm_package_json) : "");
  return isSymlinkPath(packagePrefix) ? "dev" : "serve";
}

function safeRealpath(filePath) {
  const resolvedPath = path.resolve(String(filePath || ""));
  try {
    return fs.realpathSync(resolvedPath);
  } catch {
    return resolvedPath;
  }
}

function gitOutput(args, cwd) {
  try {
    return execFileSync("git", args, {
      cwd,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
  } catch {
    return "";
  }
}

function resolveGitDir(rawGitDir, cwd) {
  if (!rawGitDir) {
    return "";
  }
  return safeRealpath(path.isAbsolute(rawGitDir)
    ? rawGitDir
    : path.resolve(cwd, rawGitDir));
}

function normalizeGitBranch(branch) {
  const normalizedBranch = String(branch || "").trim();
  return normalizedBranch && normalizedBranch !== "HEAD" ? normalizedBranch : "detached";
}

export function buildAgentViewerGit({
  env = process.env,
  cwd = process.cwd(),
} = {}) {
  const resolvedCwd = safeRealpath(env.INIT_CWD || cwd);
  const gitDir = resolveGitDir(gitOutput(["rev-parse", "--git-dir"], resolvedCwd), resolvedCwd);
  if (!gitDir) {
    return "";
  }
  const gitBranch = gitOutput(["symbolic-ref", "--quiet", "--short", "HEAD"], resolvedCwd)
    || gitOutput(["rev-parse", "--abbrev-ref", "HEAD"], resolvedCwd);
  return `${gitDir}#${normalizeGitBranch(gitBranch)}`;
}

function envWithGit(env, git) {
  return {
    ...env,
    VIEWER_GIT: String(git || ""),
  };
}

export function buildAgentStartCommand({
  mode,
  packageRoot = defaultPackageRoot,
  forwardedArgs = [],
  shutdownAfterMs = null,
  env = process.env,
  nodePath = process.execPath,
  git = buildAgentViewerGit({ env }),
} = {}) {
  const resolvedPackageRoot = path.resolve(packageRoot);
  if (mode === "dev") {
    const nextEnv = envWithGit(env, git);
    if (shutdownAfterMs !== null) {
      nextEnv.VIEWER_SERVER_LIFETIME_MS = String(shutdownAfterMs);
    }
    return {
      command: nodePath,
      args: [
        path.join(resolvedPackageRoot, "node_modules", "vite", "bin", "vite.js"),
        "dev",
        ...stripShutdownAfterArgs(forwardedArgs),
      ],
      cwd: resolvedPackageRoot,
      env: nextEnv,
      mode,
    };
  }

  return {
    command: nodePath,
    args: [
      path.join(resolvedPackageRoot, "src", "server", "server.mjs"),
      ...forwardedArgs,
    ],
    cwd: resolvedPackageRoot,
    env: envWithGit(env, git),
    mode,
  };
}

export function resolveAgentStartCommand({
  argv = process.argv.slice(2),
  env = process.env,
  packageRoot = defaultPackageRoot,
  nodePath = process.execPath,
  git = buildAgentViewerGit({ env }),
} = {}) {
  const parsed = parseAgentStartArgs(argv);
  const mode = selectAgentStartMode({
    requestedMode: parsed.startMode,
    npmConfigPrefix: env.npm_config_prefix,
    npmPackageJson: env.npm_package_json,
  });
  return buildAgentStartCommand({
    mode,
    packageRoot,
    forwardedArgs: parsed.forwardedArgs,
    shutdownAfterMs: parsed.shutdownAfterMs,
    env,
    nodePath,
    git,
  });
}

function normalizeBaseUrl(host, port) {
  return `http://${host}:${port}`;
}

function serverInfoGitAllowsReuse(serverInfo, git) {
  const currentGit = String(git || "");
  const serverGit = String(serverInfo?.git || "");
  return !currentGit || !serverGit || currentGit === serverGit;
}

export function isReusableAgentViewerServer(serverInfo, git) {
  return Boolean(
    serverInfo &&
    serverInfo.app === VIEWER_SERVER_APP_ID &&
    Number(serverInfo.serverApiVersion || 0) >= VIEWER_SERVER_API_VERSION &&
    serverInfo.dynamicRoot === true &&
    serverInfoGitAllowsReuse(serverInfo, git)
  );
}

async function fetchWithTimeout(fetchImpl, url, timeoutMs) {
  const controller = typeof AbortController === "function" ? new AbortController() : null;
  const timeout = controller
    ? setTimeout(() => controller.abort(), timeoutMs)
    : null;
  try {
    return await fetchImpl(url, controller ? { signal: controller.signal } : {});
  } finally {
    if (timeout) {
      clearTimeout(timeout);
    }
  }
}

function probeBlockedByPermissions(error) {
  const code = String(error?.cause?.code || error?.code || "");
  return code === "EPERM" || code === "EACCES";
}

export async function probeAgentViewerPort({
  host = defaultAgentHost,
  port = DEFAULT_VIEWER_PORT,
  fetchImpl = globalThis.fetch,
  timeoutMs = probeTimeoutMs,
} = {}) {
  if (typeof fetchImpl !== "function") {
    return { status: "unknown", port, error: "fetch is unavailable" };
  }
  const baseUrl = normalizeBaseUrl(host, port);
  try {
    const response = await fetchWithTimeout(fetchImpl, `${baseUrl}/__cad/server`, timeoutMs);
    if (!response?.ok) {
      return { status: "occupied", port, baseUrl };
    }
    try {
      const serverInfo = await response.json();
      if (serverInfo?.app === VIEWER_SERVER_APP_ID) {
        return { status: "viewer", port, baseUrl, serverInfo };
      }
    } catch {
      // Non-JSON responses mean another process is using this port.
    }
    return { status: "occupied", port, baseUrl };
  } catch (error) {
    if (error?.name === "AbortError") {
      return { status: "occupied", port, baseUrl, error };
    }
    if (probeBlockedByPermissions(error)) {
      return { status: "blocked", port, baseUrl, error };
    }
    return { status: "closed", port, baseUrl, error };
  }
}

function registryHost(serverInfo, fallbackHost) {
  try {
    const url = new URL(String(serverInfo?.url || ""));
    return url.hostname || fallbackHost;
  } catch {
    return fallbackHost;
  }
}

export async function resolveAgentViewerPort({
  forwardedArgs = [],
  git = "",
  registryServers = readViewerServerRegistry(),
  probePort = probeAgentViewerPort,
  portScanLimit = defaultPortScanLimit,
} = {}) {
  const target = forwardedServerTarget(forwardedArgs);
  const reusableRegistryServers = registryServers
    .filter((serverInfo) => isReusableAgentViewerServer(serverInfo, git))
    .sort((left, right) => Number(left.port) - Number(right.port));
  for (const serverInfo of reusableRegistryServers) {
    const host = registryHost(serverInfo, target.host);
    const probe = await probePort({ host, port: serverInfo.port });
    if (probe.status === "blocked") {
      throw new Error(`CAD Viewer port probe was blocked for ${probe.baseUrl}; rerun agent:start with local network permission.`);
    }
    if (probe.status === "viewer" && isReusableAgentViewerServer(probe.serverInfo, git)) {
      return {
        action: "reuse",
        host,
        port: Number(serverInfo.port),
        baseUrl: probe.baseUrl,
        serverInfo: probe.serverInfo,
      };
    }
  }

  for (let offset = 0; offset < portScanLimit; offset += 1) {
    const port = target.port + offset;
    if (port > 65535) {
      break;
    }
    const probe = await probePort({ host: target.host, port });
    if (probe.status === "blocked") {
      throw new Error(`CAD Viewer port probe was blocked for ${probe.baseUrl}; rerun agent:start with local network permission.`);
    }
    if (probe.status === "viewer" && isReusableAgentViewerServer(probe.serverInfo, git)) {
      return {
        action: "reuse",
        host: target.host,
        port,
        baseUrl: probe.baseUrl,
        serverInfo: probe.serverInfo,
      };
    }
    if (probe.status === "closed") {
      return {
        action: "start",
        host: target.host,
        port,
        baseUrl: probe.baseUrl,
      };
    }
  }

  throw new Error(`No reusable or free CAD Viewer port found from ${target.port} through ${Math.min(target.port + portScanLimit - 1, 65535)}.`);
}

export async function resolveAgentStartLaunch({
  argv = process.argv.slice(2),
  env = process.env,
  packageRoot = defaultPackageRoot,
  nodePath = process.execPath,
  probePort = probeAgentViewerPort,
  registryServers = readViewerServerRegistry(),
} = {}) {
  const parsed = parseAgentStartArgs(argv);
  const git = buildAgentViewerGit({ env });
  const portResolution = await resolveAgentViewerPort({
    forwardedArgs: parsed.forwardedArgs,
    git,
    registryServers,
    probePort,
    portScanLimit: parsed.portScanLimit,
  });
  if (portResolution.action === "reuse") {
    return { ...portResolution, git };
  }

  const mode = selectAgentStartMode({
    requestedMode: parsed.startMode,
    npmConfigPrefix: env.npm_config_prefix,
    npmPackageJson: env.npm_package_json,
  });
  return {
    action: "start",
    host: portResolution.host,
    port: portResolution.port,
    baseUrl: portResolution.baseUrl,
    git,
    command: buildAgentStartCommand({
      mode,
      packageRoot,
      forwardedArgs: replaceForwardedPort(parsed.forwardedArgs, portResolution.port),
      shutdownAfterMs: parsed.shutdownAfterMs,
      env,
      nodePath,
      git,
    }),
  };
}

export async function runAgentStart(options = {}) {
  const launch = await resolveAgentStartLaunch(options);
  if (launch.action === "reuse") {
    console.log(`CAD Viewer already running at ${launch.baseUrl}/`);
    console.log(`CAD Viewer git: ${launch.git || "none"}`);
    return null;
  }

  const command = launch.command;
  console.log(`Starting CAD Viewer ${command.mode} server at ${launch.baseUrl}/`);
  console.log(`CAD Viewer git: ${launch.git || "none"}`);
  const child = spawn(command.command, command.args, {
    cwd: command.cwd,
    env: command.env,
    stdio: "inherit",
  });

  child.on("exit", (code, signal) => {
    if (signal) {
      process.kill(process.pid, signal);
      return;
    }
    process.exit(code ?? 1);
  });

  child.on("error", (error) => {
    console.error(`Failed to start CAD Viewer ${command.mode} server: ${error.message}`);
    process.exit(1);
  });

  return child;
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === scriptPath;
if (isMain) {
  try {
    await runAgentStart();
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exit(1);
  }
}
