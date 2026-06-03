import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { isViewerServerInfo } from "./viewerServerInfo.mjs";

export const VIEWER_SERVER_REGISTRY_VERSION = 1;
export const VIEWER_SERVER_REGISTRY_FILENAME = "cad-viewer-servers.json";

export function viewerServerRegistryPath(env = process.env) {
  const configuredPath = String(env.VIEWER_SERVER_REGISTRY || "").trim();
  return configuredPath
    ? path.resolve(configuredPath)
    : path.join(os.tmpdir(), VIEWER_SERVER_REGISTRY_FILENAME);
}

export function viewerServerProcessIsAlive(pid) {
  const numericPid = Number(pid);
  if (!Number.isInteger(numericPid) || numericPid <= 0) {
    return false;
  }
  try {
    process.kill(numericPid, 0);
    return true;
  } catch (error) {
    return error?.code === "EPERM";
  }
}

function normalizeRegistryServers(payload) {
  const sourceServers = Array.isArray(payload)
    ? payload
    : Array.isArray(payload?.servers)
      ? payload.servers
      : [];
  return sourceServers
    .map((server) => ({
      ...server,
      port: Number(server?.port),
      pid: Number(server?.pid)
    }))
    .filter((server) => isViewerServerInfo(server))
    .sort((a, b) => a.port - b.port);
}

export function readViewerServerRegistry({
  registryPath = viewerServerRegistryPath(),
  includeDead = false
} = {}) {
  try {
    const payload = JSON.parse(fs.readFileSync(registryPath, "utf8"));
    return normalizeRegistryServers(payload).filter((server) => (
      includeDead || viewerServerProcessIsAlive(server.pid)
    ));
  } catch {
    return [];
  }
}

function writeRegistryServers(servers, registryPath) {
  const payload = {
    version: VIEWER_SERVER_REGISTRY_VERSION,
    servers
  };
  fs.mkdirSync(path.dirname(registryPath), { recursive: true });
  const tempPath = `${registryPath}.${process.pid}.${Date.now()}.tmp`;
  fs.writeFileSync(tempPath, `${JSON.stringify(payload, null, 2)}\n`);
  fs.renameSync(tempPath, registryPath);
}

export function writeViewerServerRegistry(serverInfo, {
  registryPath = viewerServerRegistryPath()
} = {}) {
  if (!isViewerServerInfo(serverInfo)) {
    return false;
  }

  try {
    const currentServers = readViewerServerRegistry({ registryPath });
    const nextServers = currentServers
      .filter((server) => (
        server.port !== serverInfo.port &&
        server.pid !== serverInfo.pid
      ))
      .concat({
        ...serverInfo,
        registeredAt: new Date().toISOString()
      })
      .sort((a, b) => a.port - b.port);
    writeRegistryServers(nextServers, registryPath);
    return true;
  } catch {
    return false;
  }
}

export function removeViewerServerRegistryEntry(serverInfo, {
  registryPath = viewerServerRegistryPath()
} = {}) {
  if (!serverInfo || typeof serverInfo !== "object") {
    return false;
  }

  try {
    const currentServers = readViewerServerRegistry({ registryPath, includeDead: true });
    const nextServers = currentServers.filter((server) => !(
      server.port === serverInfo.port ||
      server.pid === serverInfo.pid
    ));
    writeRegistryServers(nextServers, registryPath);
    return true;
  } catch {
    return false;
  }
}
