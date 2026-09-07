/**
 * `sessions.*` handlers: the index plus the live ACP connection behind each
 * row, through one `SessionManager`. `ipc/index.ts` spreads `acpHandlers`
 * into the contract; main calls `shutdownAcp` on quit.
 */
import { randomUUID } from "node:crypto";

import { app } from "electron";

import { IpcError, broadcast, type IpcContext } from "./register";
import { detector } from "./agents";
import type { IpcHandlers } from "../../shared/ipc";
import type { acpContract } from "../../shared/ipc/acp";
import type { ConfigOption } from "../../shared/acp/types";
import { spawnPtyTerminal } from "../acp/pty-backend";
import { AgentOptionStore } from "../acp/agent-options";
import { SessionManager } from "../acp/sessions";
import { forgetSession, mcpServersFor } from "../cad";
import { agentOptions as agentOptionsRepo, projects, sessions, settings } from "../db/repositories";
import { head } from "../projects/git";
import { releaseWorkspace, resolveWorkspace } from "../projects/workspace";
import { pruneProjectWorktrees } from "./git";

/**
 * `HARDCORE_FAKE_AGENT=<path to tests/fake-agent/index.mjs>` makes every
 * provider launch the scripted agent instead of its adapter. The Playwright
 * suite runs the built app this way; a packaged app ignores it.
 */
const fakeAgent = app.isPackaged ? undefined : process.env.HARDCORE_FAKE_AGENT;

/**
 * What each agent's sessions can be configured with, between sessions
 * (`src/main/acp/agent-options.ts`): the snapshot the new-session screen's
 * model and effort chips are drawn from, the defaults `create` applies, and
 * the probe that takes a first snapshot from an agent nobody has run yet.
 *
 * Declared before the manager it calls into and closing over it lazily, so
 * the two can refer to each other without a module cycle.
 */
export const agentOptions: AgentOptionStore = new AgentOptionStore({
  read: () => agentOptionsRepo.list(),
  get: (agentId) => agentOptionsRepo.get(agentId),
  writeOptions: (agentId, options) => agentOptionsRepo.setOptions(agentId, options),
  writeDefaults: (agentId, defaults) => agentOptionsRepo.setDefaults(agentId, defaults),
  probe: async (agentId, projectId): Promise<ConfigOption[]> => {
    const project = projectId
      ? (projects.list().find((candidate) => candidate.id === projectId) ?? null)
      : (projects.list()[0] ?? null);
    if (!project) {
      throw new Error("no project to probe in");
    }
    return sessionManager.probeOptions({ agentId, cwd: project.path, projectId: project.id });
  },
  onChange: (all) => broadcast("agentOptions.changed", all),
  onProbeFailed: (agentId, error) => {
    // Not installed, not signed in, no adapter: the new-session screen shows
    // that provider nothing, which is the whole of what the person needs.
    console.info(`[acp] ${agentId} answered no config options: ${String(error)}`);
  },
});

export const sessionManager: SessionManager = new SessionManager({
  repo: sessions,
  detector,
  spawnTerminal: spawnPtyTerminal,
  broadcast,
  // Every session gets the Hardcore MCP server, with a token that names it.
  mcpServers: mcpServersFor,
  forgetProbe: (probeId) => forgetSession(probeId, null),
  agentOptions: {
    defaults: (agentId) => agentOptions.defaults(agentId),
    remember: (agentId, options) => agentOptions.remember(agentId, options),
    rememberChoice: (agentId, configId, value, options) =>
      agentOptions.rememberChoice(agentId, configId, value, options),
  },
  clientVersion: app.isPackaged ? app.getVersion() : __APP_VERSION__,
  newId: () => randomUUID(),
  launchOverride: fakeAgent
    ? () => ({
        // Electron's own binary, told to be plain Node.
        command: process.execPath,
        args: [fakeAgent, ...(process.env.HARDCORE_FAKE_AGENT_ARGS?.split(" ").filter(Boolean) ?? [])],
        env: { ELECTRON_RUN_AS_NODE: "1" },
      })
    : undefined,

  /** P7: the git mode as a directory, and a worktree when the mode asks (plan §9). */
  workspace: async ({ projectId, gitMode, name, cwd }) => {
    const project = projects.list().find((candidate) => candidate.id === projectId);
    if (!project) {
      throw new Error("that project is no longer open");
    }
    const workspace = await resolveWorkspace({
      project,
      gitMode,
      settings: settings.get(),
      name,
      cwd,
    });
    if (workspace.worktreePath) {
      // One more worktree exists, so this is the moment the keep limit can be
      // exceeded. The sweep never touches a worktree with an open session, and
      // this one has just become one.
      await pruneProjectWorktrees(project);
    }
    return workspace;
  },

  head: (cwd) => head(cwd),

  releaseWorkspace: async (session) => {
    await releaseWorkspace(session, settings.get());
  },
});

/** Re-raise as an IpcError so the renderer sees the agent's words, not "failed". */
async function surfacing<T>(work: () => Promise<T> | T): Promise<T> {
  try {
    return await work();
  } catch (error) {
    throw new IpcError(error instanceof Error ? error.message : String(error));
  }
}

export const acpHandlers = {
  sessions: {
    list: ({ projectId }) => sessionManager.list(projectId),
    get: ({ id }) => sessionManager.get(id),
    // The mode falls back to the setting here rather than in the composer:
    // Settings › Git & Worktrees' `Default git mode` has to hold for every
    // caller, including the menu's New Session and Settings' `New chat in
    // this worktree`, not only the one chip that happens to read it.
    create: (input) =>
      surfacing(() =>
        sessionManager.create({
          ...input,
          gitMode: input.gitMode ?? settings.get().defaultGitMode,
        }),
      ),
    load: ({ id }) => surfacing(() => sessionManager.load(id)),
    state: ({ id }) => sessionManager.state(id),
    prompt: ({ id, content }) => surfacing(() => sessionManager.prompt(id, content)),
    cancel: ({ id }) => surfacing(() => sessionManager.cancel(id)),
    setMode: ({ id, modeId }) => surfacing(() => sessionManager.setMode(id, modeId)),
    setConfigOption: ({ id, configId, value }) =>
      surfacing(() => sessionManager.setConfigOption(id, configId, value)),
    respondPermission: ({ id, requestId, optionId }) =>
      surfacing(() => sessionManager.respondPermission(id, requestId, optionId)),
    setApprovalMode: ({ id, mode }) => surfacing(() => sessionManager.setApprovalMode(id, mode)),
    rename: ({ id, title }) => surfacing(() => sessionManager.rename(id, title)),
    archive: ({ id, archived }) => surfacing(() => sessionManager.archive(id, archived)),
    close: ({ id }) => surfacing(() => sessionManager.close(id)),
    delete: ({ id }) =>
      surfacing(async () => {
        const row = sessions.get(id);
        await sessionManager.delete(id);
        forgetSession(id, row?.worktreePath ?? null);
      }),
  },
} satisfies IpcHandlers<typeof acpContract, IpcContext>;

export function shutdownAcp() {
  sessionManager.closeAll();
}
