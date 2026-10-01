/**
 * The `app.*` branch of the IPC contract: the auto-updater, as the renderer
 * sees it (P8).
 *
 * A separate module beside `src/shared/ipc.ts` rather than more lines inside
 * it. Phases land in parallel, and a contract that grows by one spread per
 * branch is a contract several people can extend at once — `../ipc.ts` names
 * this file twice, in the `app` branch and in `ipcEvents`, and that is the
 * whole seam.
 *
 * `invoke` comes from `./define`, not from `../ipc`: the contract imports this
 * module, so importing it back would be a cycle that fails at load time.
 */
import { z } from "zod";

import { invoke } from "./define";

/**
 * Where the updater is, in one object. One shape for the answer to "check now"
 * and for the pushes that follow, because About renders the same card either
 * way and a second shape would be a second thing to keep in step.
 *
 * - `unsupported` — a development build, or an install the updater is inactive
 *   for. There is nothing to check and the UI says so rather than offering a
 *   dead button; an optional `message` says why when it is not a checkout.
 * - `idle` — checked, and this is the newest build (or the release has no feed
 *   for this platform yet).
 * - `checking` — a check is in flight.
 * - `available` — a newer version exists and has NOT been downloaded
 *   (`autoDownload` is off; downloading is the user's decision).
 * - `downloading` — with `percent`.
 * - `downloaded` — staged; restarting installs it.
 * - `installing` — Restart was pressed and the quit has not happened yet.
 *   Ends in the quit, in an `error` from the installer, or in an `error` when
 *   a minute passes without either.
 * - `error` — with a `message` safe to show. An error that still carries the
 *   `version` of a staged download can be answered with Restart again.
 */
export const UpdateStatusSchema = z.object({
  state: z.enum([
    "unsupported",
    "idle",
    "checking",
    "available",
    "downloading",
    "downloaded",
    "installing",
    "error",
  ]),
  /** The version the state is about, when there is one. */
  version: z.string().optional(),
  /** 0–100, only while downloading. */
  percent: z.number().min(0).max(100).optional(),
  /** Set on `error`, and on `unsupported` when the reason is not a development build. */
  message: z.string().optional(),
});
export type UpdateStatus = z.infer<typeof UpdateStatusSchema>;

/**
 * Spread into the contract's `app` branch. Every call answers with the status
 * so the caller does not have to wait for the push to know what happened.
 */
export const appIpc = {
  /** The last known status, without asking the feed. */
  updateStatus: invoke(z.void(), UpdateStatusSchema),
  /** Ask GitHub Releases now. */
  checkForUpdates: invoke(z.void(), UpdateStatusSchema),
  /** Start the download of an already-found update. */
  downloadUpdate: invoke(z.void(), UpdateStatusSchema),
  /** Quit and install what was downloaded. Never answers: the app is gone. */
  installUpdate: invoke(z.void(), z.void()),
};

/** Spread into `ipcEvents`. */
export const appEvents = {
  /** Every updater transition, pushed as it happens. */
  "app.updateStatus": UpdateStatusSchema,
} as const;
