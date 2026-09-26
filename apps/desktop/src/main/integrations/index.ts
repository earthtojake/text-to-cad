/** App-owned domain integrations: registry, per-session MCP credentials, skills and renderer relay. */
import { randomUUID } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { app } from "electron";
import type { McpServer } from "@agentclientprotocol/sdk";
import type { IntegrationCommand } from "../../shared/ipc/integrations";
import type { Session } from "../../shared/types";
import { appVersion, appRoot, resourcesDir } from "../app-paths";
import { projects, sessions } from "../db/repositories";
import * as git from "../projects/git";
import { createActions, RendererCommands } from "./actions";
import { integrationServers } from "./manager";
import { createTerminalActions } from "./terminals/actions";
import { explorerTerminals } from "../ipc/explorer";
import { BrowserConnections } from "../browser/connections";
import { McpBridge, type BridgeSession } from "./mcp-bridge";
import { EMPTY_SKILLS, materialiseSkillsRoot, skillsPreamble, SKILLS_ROOT_ENV, type SkillSummary, type SkillsRoot } from "./skills";
let bridgeInstance: McpBridge | null = null;
let skillsInstance: SkillsRoot = EMPTY_SKILLS;
let commandsInstance: RendererCommands | null = null;
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
  // The skills root travels in the environment: `list_skills` and
  // `read_skill` read it directly, without a round trip through main.
  const env: Record<string, string> = { ELECTRON_RUN_AS_NODE: "1" };
  if (skillsInstance.root) {
    env[SKILLS_ROOT_ENV] = skillsInstance.root;
  }
  return { command: process.execPath, args: [script], env };
}

/** The materialised skills root, or null when no skills were composed into the app. */
export function skillsRoot(): string | null {
  return skillsInstance.root;
}

/** What that root holds — the Settings page's list, and the preamble's. */
export function skillSummaries(): SkillSummary[] {
  return skillsInstance.skills;
}

/**
 * The text block in front of the first prompt of a session with an agent that
 * ignores additional directories (`skillRoots: "preamble"`).
 */
export function sessionPreamble(): string | null {
  return skillsInstance.root ? skillsPreamble(skillsInstance.root, skillsInstance.skills) : null;
}

export function rendererCommands(): RendererCommands {
  if (!commandsInstance) {
    throw new Error("app integrations are not initialised");
  }
  return commandsInstance;
}

export async function initIntegrations(deps: { sendCommand: (command: IntegrationCommand) => void; cancelCommand: (requestId: string) => void }): Promise<void> {
  skillsInstance = materialiseSkills(app.getPath("userData"));
  commandsInstance = new RendererCommands({
    sessionRoot,
    send: deps.sendCommand,
    cancel: deps.cancelCommand,
    newId: () => randomUUID(),
  });

  const actionDeps = { sessionRoot, send: deps.sendCommand, cancel: deps.cancelCommand, newId: () => randomUUID() };
  const browsers = new BrowserConnections(actionDeps, commandsInstance, path.join(app.getPath("userData"), "browser-artifacts"));
  const actions = { ...createActions(actionDeps, commandsInstance),
    ...createTerminalActions(actionDeps, commandsInstance, explorerTerminals),
    browser_connection: (session: BridgeSession, _params: Record<string, unknown>, signal?: AbortSignal) => browsers.connect(session, signal) };
  bridgeInstance = new McpBridge(actions, mcpServerScript, browsers);
  await bridgeInstance.start();
}

/**
 * The skills root for this app version, rebuilt when the version (or the
 * composed set) has changed and left alone otherwise. A failure here is not
 * fatal: sessions then get no additional directory and no preamble, and the
 * reason goes to the application log.
 */
function materialiseSkills(userData: string): SkillsRoot {
  // A leftover from the version of this app that installed a plugin into each
  // agent's global configuration. There is no such thing now (README, "Skills
  // and tools in a session"), so the record it kept is deleted on sight.
  fs.rmSync(path.join(userData, "plugin-installs.json"), { force: true });
  try {
    const composed = materialiseSkillsRoot({
      source: path.join(resourcesDir(), "skills"),
      base: path.join(userData, "skills"),
      version: appVersion(),
    });
    if (!composed.root) {
      console.info("[skills] nothing composed into resources/skills; run npm run build");
    }
    return composed;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`[skills] could not materialise the skills root: ${message}`);
    return EMPTY_SKILLS;
  }
}

/** Resolve only the session's recorded workspace; a missing worktree never grants checkout access. */
function sessionRoot(session: BridgeSession): { directory: string; root: string | null } | null {
  const owner = sessions.get(session.sessionId);
  if (!owner || owner.archived || owner.projectId !== session.projectId || owner.cwd !== session.cwd) return null;
  const project = projects.get(session.projectId);
  const cwd = path.resolve(owner.cwd);
  if (!project || !fs.existsSync(cwd)) return null;
  return { directory: cwd, root: git.samePath(cwd, project.path) ? null : cwd };
}

/** The MCP servers every session gets: Hardcore's own. */
export function mcpServersFor(session: Pick<Session, "id" | "projectId" | "cwd">): McpServer[] {
  if (!bridgeInstance?.address()) {
    return [];
  }
  return integrationServers(bridgeInstance, { sessionId: session.id, projectId: session.projectId, cwd: session.cwd });
}

export function forgetSession(sessionId: string): void { bridgeInstance?.revoke(sessionId); }
export async function shutdownIntegrations(): Promise<void> { commandsInstance?.dispose(); await bridgeInstance?.stop(); }
