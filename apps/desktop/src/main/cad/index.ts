/**
 * The CAD runtime this app is built around (plan §8), wired to Electron.
 *
 * Three pieces, each testable on its own without this file:
 *
 *   - `runtime.ts`   which Python runs cadgen — the bundled one, normally;
 *   - `viewer.ts`    one `cadgen viewer --api-only` per project root;
 *   - `mcp-bridge.ts` + `actions.ts`  the stdio MCP server every session gets
 *     (`resources/hardcore-mcp/server.mjs`) and what its tools do here.
 *
 * Skills are the fourth thing this file owns, but they are a directory rather
 * than a module: `materialiseSkills` below composes `resources/skills` into
 * the user's data directory, and a session is handed that path. Nothing is
 * installed into an agent's own configuration.
 *
 * `initCad` is called once from main after the database is open; `shutdownCad`
 * on quit. The IPC handlers in `src/main/ipc/{cad,runtime,skills}.ts` reach
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
import { projects, sessions, settings } from "../db/repositories";
import { rootBelongsToProject } from "../projects/workspace";
import * as git from "../projects/git";
import { createActions, RendererCommands } from "./actions";
import { DaemonWarmer } from "./daemon";
import { McpBridge, type BridgeSession } from "./mcp-bridge";
import {
  EMPTY_SKILLS,
  materialiseSkillsRoot,
  skillsPreamble,
  SKILLS_ROOT_ENV,
  type SkillSummary,
  type SkillsRoot,
} from "./skills";
import { CadRuntime, nodeHost, runtimeLogPath } from "./runtime";
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
  // The skills root travels in the environment: `list_skills` and
  // `read_skill` read it directly, without a round trip through main.
  const env: Record<string, string> = { ELECTRON_RUN_AS_NODE: "1" };
  if (skillsInstance.root) {
    env[SKILLS_ROOT_ENV] = skillsInstance.root;
  }
  return { command: process.execPath, args: [script], env };
}

let runtimeInstance: CadRuntime | null = null;
let viewersInstance: ViewerManager | null = null;
let bridgeInstance: McpBridge | null = null;
let skillsInstance: SkillsRoot = EMPTY_SKILLS;
let commandsInstance: RendererCommands | null = null;
let daemonInstance: DaemonWarmer | null = null;

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

/**
 * What goes in front of a session's `PATH`: the resolved runtime's `cadgen`
 * and `python` (`CadRuntime.sessionPath`). Empty rather than a throw when the
 * runtime is not up yet — a session that starts early gets the person's own
 * PATH, not an error.
 */
export function sessionRuntimePath(): string[] {
  return runtimeInstance?.sessionPath() ?? [];
}

export function rendererCommands(): RendererCommands {
  if (!commandsInstance) {
    throw new Error("the CAD runtime is not initialised");
  }
  return commandsInstance;
}

export function daemonWarmer(): DaemonWarmer {
  if (!daemonInstance) {
    throw new Error("the CAD runtime is not initialised");
  }
  return daemonInstance;
}

/**
 * A project opened at `root`: start what its first CAD file will need. The
 * viewer's launch probes the runtime first (`import cadgen.viewer`, which
 * primes the interpreter's caches for every cadgen process after it), and
 * the daemon follows once the probe has said which interpreter runs. Nothing
 * here is awaited by the caller; `cad.viewerOrigin` shares the launch.
 *
 * Measured on the reference machine (scripts/perf-cad.mjs): the first STEP
 * open after launch paid 0.9 s for the probe and the viewer and 3.5 s for
 * the daemon's own start inside its compile; warmed at project open, both
 * are done before the click.
 */
export async function warmCad(root: string): Promise<void> {
  const viewer = viewers().originFor(root);
  const resolved = await cadRuntime().ready();
  if (resolved) {
    daemonWarmer().warm(resolved, root);
  }
  await viewer;
}

export type CadDeps = {
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

  // The skills every session is handed, laid out for both native loaders
  // under one versioned directory (`./skills.ts`). Before the bridge, whose
  // MCP server reads the root out of its environment, and before the first
  // session can ask for it.
  skillsInstance = materialiseSkills(userData);

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

  daemonInstance = new DaemonWarmer({
    env: (resolved) => runtimeInstance!.processEnv(resolved),
    logFile: () => runtimeLogPath(userData),
    log: (line) => {
      console.info(`[daemon] ${line}`);
      void runtimeInstance!.log(`[daemon] ${line}`);
    },
  });

  commandsInstance = new RendererCommands({
    sessionRoot,
    send: deps.sendCommand,
    newId: () => randomUUID(),
  });

  bridgeInstance = new McpBridge(createActions({ sessionRoot, send: deps.sendCommand, newId: () => randomUUID() }, commandsInstance), mcpServerScript);
  await bridgeInstance.start();
}

/**
 * The skills root for this app version, rebuilt when the version (or the
 * composed set) has changed and left alone otherwise. A failure here is not
 * fatal: sessions then get no additional directory and no preamble, and the
 * reason goes to the runtime log.
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
    void runtimeInstance?.log(`[skills] ${message}`);
    return EMPTY_SKILLS;
  }
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
export function mcpServersFor(session: Pick<Session, "id" | "projectId" | "cwd">): McpServer[] {
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
