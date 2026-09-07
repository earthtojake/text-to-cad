/**
 * `plugins.*` handlers: the bundled Hardcore plugin's state per agent, and
 * installing it (src/main/cad/plugin.ts).
 *
 * An install answers with the agent's state as it now is and broadcasts every
 * agent's, so the drawer that asked and the CAD Runtime page that did not
 * agree afterwards.
 */
import type { IpcHandlers } from "../../shared/ipc";
import type { pluginsContract } from "../../shared/ipc/plugins";
import { pluginManager } from "../cad";
import { broadcast, IpcError, type IpcContext } from "./register";

export const pluginsHandlers = {
  plugins: {
    status: ({ agentId }) => surfacing(() => pluginManager().status(agentId)),

    statusAll: () => pluginManager().statusAll(),

    install: async ({ agentId }) => {
      const status = await surfacing(() => pluginManager().install(agentId));
      broadcast("plugins.status", await pluginManager().statusAll());
      return status;
    },
  },
} satisfies IpcHandlers<typeof pluginsContract, IpcContext>;

/** "unknown agent" is the one throw here, and it is a message worth showing. */
async function surfacing<T>(work: () => Promise<T>): Promise<T> {
  try {
    return await work();
  } catch (error) {
    throw new IpcError(error instanceof Error ? error.message : String(error));
  }
}
