/**
 * `cad.*`. **A stub, on purpose** — P5 replaces the body, not the shape.
 *
 * The file tab needs an origin to point `<CadFileView>` at, and that origin
 * comes from a `cadgen viewer --api-only` that P5 spawns once the managed
 * Python runtime exists (plan §7, §8). Answering `{ origin: null, reason:
 * "runtime-not-ready" }` here is not a placeholder in the "fill this in later"
 * sense: it is the answer a fresh install genuinely gives, the renderer has to
 * handle it either way, and the CAD placeholder card the file tab shows for it
 * is a real surface with a real button.
 *
 * When P5 lands `src/main/cad/viewer.ts`, this handler calls it and the
 * renderer does not change.
 */
import { projects } from "../db/repositories";
import type { ViewerOrigin } from "../../shared";

export const cadHandlers = {
  cad: {
    viewerOrigin: ({ projectId }: { projectId: string }): ViewerOrigin => {
      const project = projects.list().find((candidate) => candidate.id === projectId);
      if (!project) {
        return { origin: null, reason: "no-project" };
      }
      return { origin: null, reason: "runtime-not-ready" };
    },
  },
};
