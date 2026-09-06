/**
 * `cad.*`: the viewer origin the file tab asks for, and the renderer's
 * answers to the MCP bridge's commands.
 *
 * `viewerOrigin` is P3's seam with P5's body: the project's root goes to the
 * viewer manager, which spawns (or reuses) a `cadgen viewer --api-only` for it
 * and answers with its origin — or with the reason there is none, plus the
 * runtime's or the launcher's words, which the renderer shows as they are. `reply` is the other half of
 * `cad.command` (src/shared/ipc/cad.ts): the renderer did what an agent's
 * tool asked and this hands the result back to the waiting bridge call.
 */
import type { IpcHandlers } from "../../shared/ipc";
import type { cadIpc } from "../../shared/ipc/cad";
import type { ViewerOrigin } from "../../shared";
import { cadRuntime, rendererCommands, viewers } from "../cad";
import { projects } from "../db/repositories";
import type { IpcContext } from "./register";

export const cadHandlers = {
  cad: {
    viewerOrigin: async ({ projectId }): Promise<ViewerOrigin> => {
      const project = projects.list().find((candidate) => candidate.id === projectId);
      if (!project) {
        return { origin: null, reason: "no-project" };
      }
      const answer = await viewers().originFor(project.path);
      if (answer.origin || answer.reason !== "runtime-not-ready") {
        return answer;
      }
      // No interpreter could run cadgen. The card in the tab shows the
      // runtime's own words and the log, not a sentence about installing.
      const status = await cadRuntime().status();
      return {
        ...answer,
        ...(status.message ? { message: status.message } : {}),
        ...(status.log ? { log: status.log } : {}),
      };
    },

    reply: (reply) => {
      rendererCommands().reply(reply);
    },
  },
} satisfies IpcHandlers<typeof cadIpc, IpcContext>;
