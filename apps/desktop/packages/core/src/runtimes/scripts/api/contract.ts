import { defineContract, fallible, liveLog, liveModel, liveState } from '@emdash/wire/rpc';
import { z } from 'zod';
import { scriptRunNotFoundErrorSchema, startScriptRunErrorSchema } from './errors';
import {
  scriptRunInputSchema,
  scriptRunKeySchema,
  scriptRunResizeInputSchema,
  scriptRunStateSchema,
  scriptRunsSchema,
  scriptsScopeInputSchema,
  startScriptRunInputSchema,
  stopScriptRunInputSchema,
  waitScriptRunInputSchema,
} from './schemas';

/**
 * The scripts runtime (spec: activation-scripts-via-terminals): the single script
 * execution plane. Every lifecycle script — activation-driven, manual, or retry —
 * runs here as a PTY-backed run with streamed output. Runs are detached from the
 * starting caller's lease: they die only on stop, self-exit, or host shutdown.
 * One in-flight run per (workspace, script); different scripts run concurrently;
 * a second start of a running script is rejected.
 */
export const scriptsContract = defineContract({
  /** Per-workspace run state: script → last run (running or settled). */
  runs: liveModel({
    key: scriptsScopeInputSchema,
    states: {
      current: liveState({ data: scriptRunsSchema }),
    },
  }),

  /** Streamed output per (workspace, script); scrollback retained until the next run. */
  output: liveLog({
    key: scriptRunKeySchema,
  }),

  /**
   * Starts a run and returns once it is spawned (status 'running'). The caller supplies
   * the canonically resolved command and shellSetup; this runtime only executes them.
   */
  start: fallible({
    input: startScriptRunInputSchema,
    data: scriptRunStateSchema,
    error: startScriptRunErrorSchema,
  }),

  /** Resolves with the settled run record once the current run finishes. */
  wait: fallible({
    input: waitScriptRunInputSchema,
    data: scriptRunStateSchema,
    error: scriptRunNotFoundErrorSchema,
  }),

  /**
   * Stops the in-flight run; it settles as 'cancelled'. Works for any caller —
   * deactivation, the drawer's stop button, and timeout enforcement all use it.
   */
  stop: fallible({
    input: stopScriptRunInputSchema,
    data: z.void(),
    error: scriptRunNotFoundErrorSchema,
  }),

  /** Keyboard input into an in-flight run — scripts run without CI=1 and may prompt. */
  sendInput: fallible({
    input: scriptRunInputSchema,
    data: z.void(),
    error: scriptRunNotFoundErrorSchema,
  }),

  resize: fallible({
    input: scriptRunResizeInputSchema,
    data: z.void(),
    error: scriptRunNotFoundErrorSchema,
  }),
});

export type ScriptsContract = typeof scriptsContract;
