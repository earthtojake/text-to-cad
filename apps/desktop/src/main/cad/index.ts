/**
 * The CAD runtime this app is built around (plan §8), wired to Electron.
 *
 * Four pieces, each testable on its own without this file:
 *
 *   - `runtime.ts`   which Python runs cadgen — the bundled one, normally;
 *   - `viewer.ts`    one `cadgen viewer --api-only` per project root;
 *   - `plugin.ts`    the composed Hardcore plugin, installed into each agent;
 *   - `mcp-bridge.ts` + `actions.ts`  the stdio MCP server every session gets
 *     (`resources/hardcore-mcp/server.mjs`) and what its tools do here.
 *
 * `initCad` is called once from main after the database is open; `shutdownCad`
 * on quit. The IPC handlers in `src/main/ipc/{cad,runtime,plugins}.ts` reach
 * the singletons through the accessors below.
 */
import { randomUUID } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { app } from "electron";
import type { McpServer } from "@agentclientprotocol/sdk";

import type { CadCommand } from "../../shared/ipc/cad";
import type { Session } from "../../shared/types";
import { AGENT_PROVIDERS } from "../agents/registry";
import type { AgentDetector } from "../agents/detect";
import { projects, sessions, settings } from "../db/repositories";
import { rootBelongsToProject } from "../projects/workspace";
import * as git from "../projects/git";
import { createActions, RendererCommands } from "./actions";
import { McpBridge, type BridgeSession } from "./mcp-bridge";
import { PluginManager } from "./plugin";
import { CadRuntime, execCommand, nodeHost } from "./runtime";
import { ViewerManager } from "./viewer";

const dirname = path.dirname(fileURLToPath(import.meta.url));

export function appVersion(): string {
  return app.isPackaged ? app.getVersion() : __APP_VERSION__;
}

/** `apps/desktop` in a checkout; the asar's root when packaged. */
export function appRoot(): string {
  // out/main/index.js -> apps/desktop (or app.asar/out/main -> app.asar)
  return path.resolve(dirname, "..", "..");
}

/** `resources/` in a checkout, `Contents/Resources` (process.resourcesPath) packaged. */
export function resourcesDir(): string {
  return app.isPackaged ? process.resourcesPath : path.join(appRoot(), "resources");
}

/**
 * The MCP server script and how to run it. The command is this very Electron
 * binary told to be Node (`ELECTRON_RUN_AS_NODE`): the one interpreter a
 * packaged app is sure to have, on every platform. In a checkout the source
 * resolves the SDK from `apps/desktop/node_modules`; packaged, the bundle
 * `scripts/build-mcp.mjs` wrote is unpacked beside the asar so it can be run
 * by path (electron-builder.yml, `asarUnpack`).
 */
export function mcpServerScript(): { command: string; args: string[]; env: Record<string, string> } {
  const script = app.isPackaged
    ? path.join(appRoot().replace(/app\.asar$/, "app.asar.unpacked"), "out", "hardcore-mcp", "server.mjs")
    : path.join(appRoot(), "resources", "hardcore-mcp", "server.mjs");
  return { command: process.execPath, args: [script], env: { ELECTRON_RUN_AS_NODE: "1" } };
}

let runtimeInstance: CadRuntime | null = null;
let viewersInstance: ViewerManager | null = null;
let bridgeInstance: McpBridge | null = null;
let pluginsInstance: PluginManager | null = null;
let commandsInstance: RendererCommands | null = null;

export function cadRuntime(): CadRuntime {
  if (!runtimeInstance) {
    throw new Error("the CAD runtime is not initialised");
  }
  return runtimeInstance;
}

export function viewers(): ViewerManager {
  if (!viewersInstance) {
    throw new Error("the CAD runtime is not initialised");
  }
  return viewersInstance;
}

export function pluginManager(): PluginManager {
  if (!pluginsInstance) {
    throw new Error("the CAD runtime is not initialised");
  }
  return pluginsInstance;
}

export function rendererCommands(): RendererCommands {
  if (!commandsInstance) {
    throw new Error("the CAD runtime is not initialised");
  }
  return commandsInstance;
}

export type CadDeps = {
  detector: AgentDetector;
  sendCommand: (command: CadCommand) => void;
};

export async function initCad(deps: CadDeps): Promise<void> {
  const userData = app.getPath("userData");

  runtimeInstance = new CadRuntime(
    nodeHost({
      userData,
      appVersion: appVersion(),
      resourcesDir: resourcesDir(),
      appRoot: appRoot(),
      overrideSetting: () => settings.get().cadPythonOverride,
    }),
  );

  viewersInstance = new ViewerManager({
    runtime: () => runtimeInstance!.ready(),
    env: (resolved) => runtimeInstance!.processEnv(resolved),
    // The viewer's stderr and its launch failures go to the runtime log
    // beside the probe's, so one file answers "why is there no viewer".
    log: (line) => {
      console.info(`[viewer] ${line}`);
      void runtimeInstance!.log(`[viewer] ${line}`);
    },
  });

  commandsInstance = new RendererCommands({
    sessionRoot,
    send: deps.sendCommand,
    newId: () => randomUUID(),
  });

  bridgeInstance = new McpBridge(createActions({ sessionRoot, send: deps.sendCommand, newId: () => randomUUID() }, commandsInstance), mcpServerScript);
  await bridgeInstance.start();

  pluginsInstance = new PluginManager({
    appVersion: appVersion(),
    pluginDir: path.join(resourcesDir(), "plugin"),
    homeDir: app.getPath("home"),
    stateFile: path.join(userData, "plugin-installs.json"),
    providers: AGENT_PROVIDERS,
    agent: async (agentId) => {
      const status = deps.detector.list().find((candidate) => candidate.id === agentId);
      return { installed: status?.installed ?? false, binaryPath: status?.binaryPath ?? null };
    },
    env: () => deps.detector.environment(),
    exec: (file, args, env) => execCommand(file, args, { env, timeoutMs: 120_000 }),
  });
}

/**
 * Where a session's paths resolve (plan §9): its worktree when its cwd is one
 * of the project's worktrees, else the project directory. A cwd that is
 * neither — a row from before worktrees, or one edited by hand — falls back
 * to the project, which is what every session could reach before.
 */
function sessionRoot(session: BridgeSession): { directory: string; root: string | null } | null {
  const project = projects.list().find((candidate) => candidate.id === session.projectId);
  if (!project || !fs.existsSync(project.path)) {
    return null;
  }
  const cwd = path.resolve(session.cwd);
  if (
    !git.samePath(cwd, project.path) &&
    rootBelongsToProject(settings.get(), project, cwd) &&
    fs.existsSync(cwd)
  ) {
    return { directory: cwd, root: cwd };
  }
  return { directory: project.path, root: null };
}

/** The MCP servers every session gets: Hardcore's own. */
export function mcpServersFor(session: Session): McpServer[] {
  if (!bridgeInstance?.address()) {
    return [];
  }
  return [bridgeInstance.serverFor({ sessionId: session.id, projectId: session.projectId, cwd: session.cwd })];
}

/**
 * A session is gone. Its bridge token is revoked, and the viewer that served
 * its worktree — one instance per root — is stopped when no other session
 * still runs there; the project's own viewer is never touched here.
 */
export function forgetSession(sessionId: string, worktreePath?: string | null): void {
  bridgeInstance?.revoke(sessionId);
  if (worktreePath && !sessions.list().some((other) => other.id !== sessionId && git.samePath(other.cwd, worktreePath))) {
    viewersInstance?.stop(path.resolve(worktreePath));
  }
}

export async function shutdownCad(): Promise<void> {
  viewersInstance?.stopAll();
  commandsInstance?.dispose();
  await bridgeInstance?.stop();
}
