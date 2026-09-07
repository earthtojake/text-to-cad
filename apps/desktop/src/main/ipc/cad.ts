/**
 * `cad.*`: the viewer origin the file tab asks for, and the renderer's
 * answers to the MCP bridge's commands.
 *
 * `viewerOrigin` is P3's seam with P5's body: the tab's root — the project,
 * or one of its worktrees — goes to the
 * viewer manager, which spawns (or reuses) a `cadgen viewer --api-only` for it
 * and answers with its origin — or with the reason there is none, plus the
 * runtime's or the launcher's words, which the renderer shows as they are. `reply` is the other half of
 * `cad.command` (src/shared/ipc/cad.ts): the renderer did what an agent's
 * tool asked and this hands the result back to the waiting bridge call.
 */
import type { IpcHandlers } from "../../shared/ipc";
import type { cadIpc } from "../../shared/ipc/cad";
import type { ViewerOrigin } from "../../shared";
import { cadRuntime, rendererCommands, viewers, warmCad } from "../cad";
import { projects } from "../db/repositories";
import { rootOf } from "./explorer";
import type { IpcContext } from "./register";

export const cadHandlers = {
  cad: {
    viewerOrigin: async ({ projectId, root }): Promise<ViewerOrigin> => {
      const project = projects.list().find((candidate) => candidate.id === projectId);
      if (!project) {
        return { origin: null, reason: "no-project" };
      }
      // One viewer per root: a worktree is served by its own instance, so a
      // file the session wrote there is the file the viewer renders.
      const answer = await viewers().originFor(rootOf(projectId, root));
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

    warm: ({ projectId, root }) => {
      if (!projects.list().some((candidate) => candidate.id === projectId)) {
        return;
      }
      // The suite adds a project in nearly every spec; a viewer and a daemon
      // importing the kernel behind each of them is load the tests never see
      // a result from. Only the pre-warm spec asks for it.
      if (process.env.NODE_ENV === "test" && process.env.HARDCORE_PREWARM !== "1") {
        return;
      }
      // Started, not awaited: the renderer asked on the way into a project
      // and has nothing to show for it. The first `viewerOrigin` will find
      // the launch in progress (or done) and share it.
      warmCad(rootOf(projectId, root)).catch(() => {
        /* the first viewerOrigin reports the failure, with its words */
      });
    },

    reply: (reply) => {
      rendererCommands().reply(reply);
    },
  },
} satisfies IpcHandlers<typeof cadIpc, IpcContext>;
