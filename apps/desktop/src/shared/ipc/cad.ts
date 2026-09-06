/**
 * The CAD runtime's half of the contract.
 *
 * One channel so far, and it is a seam rather than a feature: the file tab
 * renders `.step`, `.glb`, `.dxf` and the rest through the CAD Viewer's
 * `<CadFileView>`, which talks to a `cadgen viewer --api-only` over HTTP and
 * therefore needs that instance's origin (plan §7).
 *
 * P3 declares the channel and answers it with `origin: null`, so the file tab
 * is written against the real shape and shows its "not set up yet" card. P5
 * provisions the managed Python, spawns the viewer per project root and
 * returns a real origin — with no change on the renderer's side, because the
 * renderer already handles both answers.
 */
import { z } from "zod";

import { invoke } from "./invoke";

/**
 * Why there is no origin. Each value is a different sentence in the UI, which
 * is the whole reason this is not a bare `null`.
 */
export const ViewerOriginReasonSchema = z.enum([
  /** The managed Python and cadgen are not installed yet (P5's setup flow). */
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
});
export type ViewerOrigin = z.infer<typeof ViewerOriginSchema>;

export const cadIpc = {
  cad: {
    /**
     * The viewer origin for a project root, starting one if need be.
     * Idempotent: the launcher's reuse contract means asking twice gets the
     * same instance.
     */
    viewerOrigin: invoke(z.object({ projectId: z.string().min(1) }), ViewerOriginSchema),
  },
} as const;
