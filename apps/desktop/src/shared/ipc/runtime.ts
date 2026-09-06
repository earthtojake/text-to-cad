/**
 * `runtime.*`: the managed CAD runtime — a pinned Python under `userData/`
 * plus the bundled cadgen wheel, about a gigabyte on disk and therefore
 * installed on first launch rather than shipped in the installer (plan §8).
 *
 * Declared by P6 because the CAD Runtime settings page is `cad:check` as UI
 * and needs something to render; answered by stubs until P5 provisions the
 * runtime. The stub answers `missing`, which is true of every build that has
 * not run P5's provisioner.
 */
import { z } from "zod";

import { invoke } from "./define";

/**
 * - `missing` — no runtime yet; the page offers Install.
 * - `installing` — provisioning, with `runtime.progress` arriving.
 * - `ready` — Python, cadgen and the viewer client are all in place.
 * - `error` — provisioning failed; `message` says how and `log` has the tail.
 */
export const RuntimeStateSchema = z.enum(["missing", "installing", "ready", "error"]);
export type RuntimeState = z.infer<typeof RuntimeStateSchema>;

export const RuntimeStatusSchema = z.object({
  state: RuntimeStateSchema,
  /** Absolute path of the interpreter in use, managed or overridden. */
  python: z.string().nullable().default(null),
  /** Version reported by the installed cadgen, for comparison with the app's. */
  cadgenVersion: z.string().nullable().default(null),
  /** Whether the viewer client the wheel carries is present. */
  viewerBuilt: z.boolean().default(false),
  /** True when `cadPythonOverride` is what `python` points at. */
  overridden: z.boolean().default(false),
  /** Tail of the provisioning log, for the error state. */
  log: z.string().nullable().default(null),
  /** Set on `error`; safe to show. */
  message: z.string().optional(),
});
export type RuntimeStatus = z.infer<typeof RuntimeStatusSchema>;

export const runtimeContract = {
  runtime: {
    /** The current state, without provisioning anything. */
    status: invoke(z.void(), RuntimeStatusSchema),
    /** Install or reinstall from the bundled wheel; answers with the new state. */
    repair: invoke(z.void(), RuntimeStatusSchema),
  },
} as const;

export const runtimeEvents = {
  /**
   * One event for the whole install: the state as it now is, plus the line and
   * the percentage that moved it. One shape rather than a status event and a
   * log event, because the page renders them in one card.
   */
  "runtime.progress": z.object({
    status: RuntimeStatusSchema,
    /** The most recent line of output, when there is one. */
    message: z.string().optional(),
    percent: z.number().min(0).max(100).optional(),
  }),
} as const;
