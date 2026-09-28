/**
 * `telemetry.*`: what Settings › General and the first-launch notice need
 * from `src/main/telemetry.ts` that is not a setting — whether this build and
 * this environment can send at all, and the list of what went out this run.
 */
import { z } from "zod";

import { invoke } from "./define";

export const TelemetryStatusSchema = z.object({
  /** A key is compiled in and the environment did not say no. */
  available: z.boolean(),
  reason: z.enum(["no-key", "environment"]).nullable(),
  /** The environment variable that said no, when one did. */
  variable: z.string().nullable(),
});
export type TelemetryStatus = z.infer<typeof TelemetryStatusSchema>;

export const SentEventSchema = z.object({
  name: z.string(),
  props: z.record(z.string(), z.string()),
  /** Unix milliseconds. */
  at: z.number(),
});
export type SentEvent = z.infer<typeof SentEventSchema>;

export const telemetryContract = {
  telemetry: {
    status: invoke(z.void(), TelemetryStatusSchema),
    /** Every event sent this run, oldest first. */
    log: invoke(z.void(), z.object({ events: z.array(SentEventSchema) })),
    /**
     * A file was opened in the explorer. Main keeps the extension and drops the
     * rest (`file_opened`); the path never leaves the machine.
     */
    fileOpened: invoke(z.object({ path: z.string() }), z.void()),
  },
} as const;
