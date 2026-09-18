import type { ActionDeps, RendererCommands } from "../actions";
import { resolveForSession } from "../actions";
import type { BridgeActions, BridgeSession } from "../mcp-bridge";
import type { Terminals } from "../../explorer/terminal";
import type { ExplorerTab } from "../../../shared/types";
import fs from "node:fs/promises";

export function createTerminalActions(deps: ActionDeps, commands: RendererCommands, terminals: () => Terminals): BridgeActions {
  async function resolve(session: BridgeSession, params: Record<string, unknown>, signal?: AbortSignal) {
    const scope = deps.sessionRoot(session);
    if (!scope) throw new Error("workspace no longer exists");
    const tab = await commands.request({ kind: "tab-resource", projectId: session.projectId, root: scope.root,
      rootDirectory: await fs.realpath(scope.directory), tabId: String(params.tabId) }, signal) as ExplorerTab;
    if (tab.kind !== "terminal" || !tab.ptyId || !terminals().owns(tab.ptyId, session.projectId)) throw new Error("this tab has no app-owned terminal in the workspace");
    return tab.ptyId;
  }
  return {
    create_terminal: async (session, params, signal) => {
      signal?.throwIfAborted();
      const location = await resolveForSession(deps, session, typeof params.cwd === "string" ? params.cwd : ".");
      if (!(await fs.stat(location.absolute)).isDirectory()) throw new Error("terminal cwd must be a directory");
      signal?.throwIfAborted();
      const info = await terminals().create({ projectId: session.projectId, cwd: location.absolute });
      try {
        return await commands.request({ kind: "terminal-open", projectId: session.projectId, root: location.root,
          rootDirectory: location.directory, params: { cwd: info.cwd, ptyId: info.id } }, signal);
      } catch (error) { terminals().kill(info.id); throw error; }
    },
    read_terminal: async (session, params, signal) => terminals().read(await resolve(session, params, signal), params.after as number | undefined, params.limit as number | undefined),
    write_terminal: async (session, params, signal) => {
      const id = await resolve(session, params, signal);
      terminals().writeGuarded(id, params.data as string, params.expectedSequence as number, params.expectedInputRevision as number);
      return terminals().read(id);
    },
    stop_terminal: async (session, params, signal) => {
      const id = await resolve(session, params, signal); terminals().stop(id); return { stopped: true, id };
    },
  };
}
