import { z } from 'zod';

/** The same script is already running for this workspace — stop it first. */
export const runInFlightErrorSchema = z.object({
  type: z.literal('run-in-flight'),
  message: z.string().min(1),
});

/** Canonical project configuration has no command for the requested script. */
export const scriptNotConfiguredErrorSchema = z.object({
  type: z.literal('script-not-configured'),
  message: z.string().min(1),
});

/** The PTY could not be spawned. */
export const spawnFailedErrorSchema = z.object({
  type: z.literal('spawn-failed'),
  message: z.string().min(1),
});

export const startScriptRunErrorSchema = z.discriminatedUnion('type', [
  runInFlightErrorSchema,
  spawnFailedErrorSchema,
]);

export type StartScriptRunError = z.infer<typeof startScriptRunErrorSchema>;

/** No run — running or retained — exists for the (workspace, script) key. */
export const scriptRunNotFoundErrorSchema = z.object({
  type: z.literal('not-found'),
  message: z.string().min(1),
});

export type ScriptRunNotFoundError = z.infer<typeof scriptRunNotFoundErrorSchema>;
