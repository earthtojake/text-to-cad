import type { ActionDeps, RendererCommands } from "../actions";
import { resolveForSession, workspaceDirectory } from "../actions";
import type { BridgeActions, BridgeSession } from "../mcp-bridge";
import type { Terminals } from "../../explorer/terminal";
import type { ExplorerTab } from "../../../shared/types";
import fs from "node:fs/promises";

/** Terminals one session may hold: each keeps up to 512 KB of scrollback until its tab is closed. */
export const MAX_TERMINALS_PER_SESSION = 16;
/** How long `stop_terminal` waits for the shell to exit before saying it has not. */
const STOP_WAIT_MS = 2_000;

/**
 * `runtimePath` is the session's runtime launchers (`sessionRuntimePath`), put
 * in front of a created terminal's PATH as they are in front of the agent's:
 * the cad-viewer skill promises `cadgen` on PATH, and a terminal the agent
 * opens is one more place it runs it.
 */
export function createTerminalActions(deps: ActionDeps, commands: RendererCommands, terminals: () => Terminals,
  runtimePath: () => string[] = () => []): BridgeActions {
  async function resolve(session: BridgeSession, params: Record<string, unknown>, signal?: AbortSignal) {
    const scope = deps.sessionRoot(session);
    if (!scope) throw new Error("workspace no longer exists");
    const tab = await commands.request({ kind: "tab-resource", sessionId: session.sessionId, projectId: session.projectId, root: scope.root,
      ...(await workspaceDirectory(scope.directory)), tabId: String(params.tabId) }, signal) as ExplorerTab;
    if (tab.kind !== "terminal" || !tab.ptyId || !terminals().owns(tab.ptyId, session.sessionId)) throw new Error("this tab has no app-owned terminal in the workspace");
    return tab.ptyId;
  }
  return {
    create_terminal: async (session, params, signal) => {
      signal?.throwIfAborted();
      const location = await resolveForSession(deps, session, typeof params.cwd === "string" ? params.cwd : ".");
      if (!(await fs.stat(location.absolute)).isDirectory()) throw new Error("terminal cwd must be a directory");
      signal?.throwIfAborted();
      const info = await terminals().create({ sessionId: session.sessionId, projectId: session.projectId, cwd: location.absolute,
        pathPrefix: runtimePath(), maxPerSession: MAX_TERMINALS_PER_SESSION });
      try {
        signal?.throwIfAborted();
        if (!deps.sessionRoot(session)) throw new Error("This session is no longer active.");
        return await commands.request({ kind: "terminal-open", sessionId: session.sessionId, projectId: session.projectId, root: location.root,
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
      const id = await resolve(session, params, signal);
      terminals().stop(id);
      // `stop` only signals; report the exit if it comes, not before it has.
      const exitCode = await terminals().exited(id, STOP_WAIT_MS);
      return exitCode === null ? { stopped: true, id, exited: false } : { stopped: true, id, exited: true, exitCode };
    },
  };
}
