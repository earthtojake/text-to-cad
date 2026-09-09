/**
 * `runtime.*`: the CAD runtime — the pinned Python with cadgen installed that
 * ships INSIDE the app (`resources/runtime/<os>-<arch>/`, built by
 * `scripts/bundle-runtime.mjs`), or the interpreter standing in for it in
 * development (plan §8, as revised: nothing downloads at first launch).
 *
 * Read by the status block in Settings › About & Updates and by the CAD file
 * tab when it has no viewer to show.
 */
import { z } from "zod";

import { invoke } from "./define";

/**
 * - `missing` — no interpreter at all: no bundle beside the app, no checkout
 *   venv, no override. `message` says where the app looked.
 * - `ready` — Python, cadgen and cadgen's viewer all import.
 * - `error` — an interpreter was found and cannot run cadgen; `message` has
 *   the interpreter's words and `log` the file with the rest.
 */
export const RuntimeStateSchema = z.enum(["missing", "ready", "error"]);
export type RuntimeState = z.infer<typeof RuntimeStateSchema>;

/** Where the interpreter came from, in resolution order. */
export const RuntimeSourceSchema = z.enum(["override", "bundled", "checkout"]);
export type RuntimeSource = z.infer<typeof RuntimeSourceSchema>;

export const RuntimeStatusSchema = z.object({
  state: RuntimeStateSchema,
  /** Absolute path of the interpreter in use. */
  python: z.string().nullable().default(null),
  source: RuntimeSourceSchema.nullable().default(null),
  /** Version reported by the installed cadgen, for comparison with the app's. */
  cadgenVersion: z.string().nullable().default(null),
  /** Whether `cadgen.viewer` — the backend the file tab talks to — imports. */
  viewerBuilt: z.boolean().default(false),
  /** The runtime log (`userData/cad-runtime.log`), once anything has been written to it. */
  log: z.string().nullable().default(null),
  /** Set on `missing` and `error`; safe to show. */
  message: z.string().optional(),
});
export type RuntimeStatus = z.infer<typeof RuntimeStatusSchema>;

export const runtimeContract = {
  runtime: {
    /** The current state, probing the interpreter once and remembering the answer. */
    status: invoke(z.void(), RuntimeStatusSchema),
    /** Forget the probe and look again; answers with the new state. */
    repair: invoke(z.void(), RuntimeStatusSchema),
  },
} as const;

export const runtimeEvents = {
  /** The state changed — a repair finished, or a probe answered. */
  "runtime.status": RuntimeStatusSchema,
} as const;
