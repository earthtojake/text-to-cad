/** CAD viewer backend origin and warm-up IPC. */
import { z } from "zod";

import { invoke } from "./define";

/**
 * Why there is no origin. Each value is a different sentence in the UI, which
 * is the whole reason this is not a bare `null`.
 */
export const ViewerOriginReasonSchema = z.enum([
  /**
   * No interpreter can run cadgen: the bundled runtime is missing or broken
   * (`runtime.status` has the words). A failure, not a first-run state —
   * the runtime ships inside the app.
   */
  "runtime-not-ready",
  /** The runtime is there; the viewer process failed to come up. */
  "viewer-failed",
  /** Nothing to serve — the request named a project that no longer exists. */
  "no-project",
]);
export type ViewerOriginReason = z.infer<typeof ViewerOriginReasonSchema>;

export const ViewerOriginSchema = z.object({
  /**
   * The absolute origin of the `cadgen viewer` serving this project's root,
   * e.g. `"http://127.0.0.1:3250"`. Null when there is not one.
   */
  origin: z.string().nullable(),
  reason: ViewerOriginReasonSchema.optional(),
  /** What went wrong, in the interpreter's or the launcher's words; safe to show. */
  message: z.string().optional(),
  /** The runtime log's path, when there is one to point at. */
  log: z.string().optional(),
});
export type ViewerOrigin = z.infer<typeof ViewerOriginSchema>;

export const cadIpc = {
  cad: {
    /**
     * The viewer origin for a root — the project, or one of its worktrees,
     * each served by its own `cadgen viewer` — starting one if need be.
     * Idempotent: the launcher's reuse contract means asking twice gets the
     * same instance.
     */
    viewerOrigin: invoke(z.object({ projectId: z.string().min(1), root: z.string().optional() }), ViewerOriginSchema),
    /**
     * A project opened in the explorer: start what its first CAD file will
     * need — the runtime probe, the viewer for this root, the warm build
     * daemon — now, off the critical path, rather than on the first click.
     * Answers once the work is STARTED; never waits for the viewer, and a
     * failure here is not an error (the first `viewerOrigin` reports it).
     */
    warm: invoke(z.object({ projectId: z.string().min(1), root: z.string().optional() }), z.void()),
  },
} as const;
