import {
  scriptKindSchema,
  scriptRunNotFoundErrorSchema,
  scriptRunsSchema,
} from '@emdash/core/runtimes/scripts/api';
import { runScriptErrorSchema } from '@emdash/core/runtimes/workspace-registry/api';
import { runtimeResolveErrorSchema } from '@emdash/core/services/runtime-broker/api';
import { defineContract, fallible, liveLog, liveModel, liveState } from '@emdash/wire/rpc';
import { z } from 'zod';

const scriptKeyInput = z.object({
  workspaceId: z.string().min(1),
  script: scriptKindSchema,
});

export const lifecycleScriptsDomain = 'lifecycleScripts' as const;

/**
 * The renderer's window onto the host scripts runtime (spec:
 * activation-scripts-via-terminals): the bottom drawer and the Activity popover
 * both read and act through this surface. Reads (run state, output) forward to
 * the scripts runtime keyed by the workspace's host path; `start` goes through
 * the host registry's runScript so the request — command, env, shellSetup,
 * timeout — is built host-side from the record. The desktop resolves ids to
 * hosts and forwards; it never assembles script requests.
 */
export const lifecycleScriptsWireContract = defineContract({
  /** Per-workspace run state: script → last run (running or settled). */
  runs: liveModel({
    key: z.object({ workspaceId: z.string().min(1) }),
    states: {
      current: liveState({ data: scriptRunsSchema }),
    },
  }),

  /** Streamed PTY output per (workspace, script); scrollback until the next run. */
  output: liveLog({
    key: scriptKeyInput,
  }),

  /**
   * Starts a manual or retry run, brokered by the host registry. Returns once
   * the run spawned; progress arrives through `runs` and the timeline through
   * the registry's observation. A same-script start while one runs is rejected.
   */
  start: fallible({
    input: scriptKeyInput.extend({ provenance: z.enum(['manual', 'retry']) }),
    data: z.void(),
    error: z.union([runScriptErrorSchema, runtimeResolveErrorSchema]),
  }),

  /** Stops the in-flight run; it settles as cancelled. */
  stop: fallible({
    input: scriptKeyInput,
    data: z.void(),
    error: z.union([scriptRunNotFoundErrorSchema, runtimeResolveErrorSchema]),
  }),

  /** Keyboard input into an in-flight run — scripts run without CI and may prompt. */
  sendInput: fallible({
    input: scriptKeyInput.extend({ data: z.string() }),
    data: z.void(),
    error: z.union([scriptRunNotFoundErrorSchema, runtimeResolveErrorSchema]),
  }),

  resize: fallible({
    input: scriptKeyInput.extend({
      cols: z.number().int().positive(),
      rows: z.number().int().positive(),
    }),
    data: z.void(),
    error: z.union([scriptRunNotFoundErrorSchema, runtimeResolveErrorSchema]),
  }),
});

export type LifecycleScriptsWireContract = typeof lifecycleScriptsWireContract;
