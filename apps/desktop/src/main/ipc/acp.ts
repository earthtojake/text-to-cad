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
import { sessions } from "../db/repositories";

/**
 * `HARDCORE_FAKE_AGENT=<path to tests/fake-agent/index.mjs>` makes every
 * provider launch the scripted agent instead of its adapter. The Playwright
 * suite runs the built app this way; a packaged app ignores it.
 */
const fakeAgent = app.isPackaged ? undefined : process.env.HARDCORE_FAKE_AGENT;

export const sessionManager = new SessionManager({
  repo: sessions,
  detector,
  spawnTerminal: spawnPtyTerminal,
  broadcast,
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
    create: (input) => surfacing(() => sessionManager.create(input)),
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
    delete: ({ id }) => surfacing(() => sessionManager.delete(id)),
  },
} satisfies IpcHandlers<typeof acpContract, IpcContext>;

export function shutdownAcp() {
  sessionManager.closeAll();
}
