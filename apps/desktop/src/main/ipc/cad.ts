/**
 * `cad.*`: the viewer origin the file tab asks for, and the renderer's
 * answers to the MCP bridge's commands.
 *
 * `viewerOrigin` is P3's seam with P5's body: the project's root goes to the
 * viewer manager, which spawns (or reuses) a `cadgen viewer --api-only` for it
 * and answers with its origin — or with the reason there is none, which the
 * renderer already turns into the right card. `reply` is the other half of
 * `cad.command` (src/shared/ipc/cad.ts): the renderer did what an agent's
 * tool asked and this hands the result back to the waiting bridge call.
 */
import type { IpcHandlers } from "../../shared/ipc";
import type { cadIpc } from "../../shared/ipc/cad";
import type { ViewerOrigin } from "../../shared";
import { rendererCommands, viewers } from "../cad";
import { projects } from "../db/repositories";
import type { IpcContext } from "./register";

export const cadHandlers = {
  cad: {
    viewerOrigin: async ({ projectId }): Promise<ViewerOrigin> => {
      const project = projects.list().find((candidate) => candidate.id === projectId);
      if (!project) {
        return { origin: null, reason: "no-project" };
      }
      return viewers().originFor(project.path);
    },

    reply: (reply) => {
      rendererCommands().reply(reply);
    },
  },
} satisfies IpcHandlers<typeof cadIpc, IpcContext>;
