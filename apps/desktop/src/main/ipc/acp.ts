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
import { spawnPtyTerminal } from "../acp/pty-backend";
import { SessionManager } from "../acp/sessions";
import { projects, sessions, settings } from "../db/repositories";
import { head } from "../projects/git";
import { releaseWorkspace, resolveWorkspace } from "../projects/workspace";
import { pruneProjectWorktrees } from "./git";

export const sessionManager = new SessionManager({
  repo: sessions,
  detector,
  spawnTerminal: spawnPtyTerminal,
  broadcast,
  clientVersion: app.isPackaged ? app.getVersion() : __APP_VERSION__,
  newId: () => randomUUID(),

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
    close: ({ id }) => surfacing(() => sessionManager.close(id)),
    delete: ({ id }) => surfacing(() => sessionManager.delete(id)),
  },
} satisfies IpcHandlers<typeof acpContract, IpcContext>;

export function shutdownAcp() {
  sessionManager.closeAll();
}
