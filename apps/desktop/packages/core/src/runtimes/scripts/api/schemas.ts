import { z } from 'zod';

/** The four lifecycle scripts a workspace's `.emdash.json` can define. */
export const scriptKindSchema = z.enum(['prepare', 'setup', 'run', 'teardown']);

export type ScriptKind = z.infer<typeof scriptKindSchema>;

/**
 * Who started a run — attribution only, no behavioral difference (spec:
 * activation-scripts-via-terminals, run identity).
 */
export const scriptProvenanceSchema = z.enum(['activation', 'manual', 'retry']);

export type ScriptProvenance = z.infer<typeof scriptProvenanceSchema>;

/** Terminal outcomes are distinct: timed-out is not failed, cancelled is not failed. */
export const scriptRunStatusSchema = z.enum([
  'running',
  'succeeded',
  'failed',
  'timed-out',
  'cancelled',
]);

export type ScriptRunStatus = z.infer<typeof scriptRunStatusSchema>;

/**
 * Workspace facts the env builder derives `EMDASH_*` variables from. Callers pass
 * what they know (the registry passes record facts; the desktop passes mirror
 * facts); everything but the record id is optional and degrades to path-derived
 * values.
 */
export const scriptWorkspaceFactsSchema = z.object({
  /** The workspace record id — becomes EMDASH_TASK_ID. */
  workspaceId: z.string().min(1),
  /** The repository root path — becomes EMDASH_ROOT_PATH (falls back to the workspace path). */
  repositoryPath: z.string().min(1).optional(),
  /** The checked-out branch — EMDASH_TASK_NAME derives from it (falls back to the directory name). */
  branch: z.string().min(1).optional(),
  /** The base/default branch — becomes EMDASH_DEFAULT_BRANCH (omitted when unknown). */
  defaultBranch: z.string().min(1).optional(),
});

export type ScriptWorkspaceFacts = z.infer<typeof scriptWorkspaceFactsSchema>;

/**
 * Runs are keyed by host-absolute workspace path plus script — no host-ref
 * component, so registry-initiated and desktop-initiated runs land in the same
 * scope on local and remote hosts alike (spec: keying).
 */
export const scriptRunKeySchema = z.object({
  workspacePath: z.string().min(1),
  script: scriptKindSchema,
});

export type ScriptRunKey = z.infer<typeof scriptRunKeySchema>;

export const startScriptRunInputSchema = z.object({
  workspacePath: z.string().min(1),
  script: scriptKindSchema,
  provenance: scriptProvenanceSchema,
  facts: scriptWorkspaceFactsSchema,
  /** Canonically resolved command; the scripts runtime executes it verbatim. */
  command: z.string().min(1),
  /** Canonically resolved shell setup; the empty string means no setup. */
  shellSetup: z.string(),
  /** A timed-out run settles as 'timed-out'; absent means no timeout. */
  timeoutMs: z.number().int().positive().optional(),
  cols: z.number().int().positive().optional(),
  rows: z.number().int().positive().optional(),
});

export type StartScriptRunInput = z.infer<typeof startScriptRunInputSchema>;

/**
 * One run's record — the last run per (workspace, script) is retained in memory
 * with a capped output tail that survives the exit. Nothing survives a worker
 * restart.
 */
export const scriptRunStateSchema = z.object({
  runId: z.string().min(1),
  script: scriptKindSchema,
  provenance: scriptProvenanceSchema,
  status: scriptRunStatusSchema,
  startedAt: z.number(),
  finishedAt: z.number().optional(),
  exitCode: z.number().int().nullable().optional(),
  signal: z.string().nullable().optional(),
  pid: z.number().optional(),
  /** Control-stripped, capped (~16KiB) output tail; retained after exit. */
  outputTail: z.string(),
  /** Human context for non-success settlements (timeout, stop reason). */
  message: z.string().optional(),
});

export type ScriptRunState = z.infer<typeof scriptRunStateSchema>;

/** Per-workspace view: script name → last run. */
export const scriptRunsSchema = z.record(z.string(), scriptRunStateSchema);

export type ScriptRuns = z.infer<typeof scriptRunsSchema>;

export const scriptsScopeInputSchema = z.object({
  workspacePath: z.string().min(1),
});

export const waitScriptRunInputSchema = z.object({
  workspacePath: z.string().min(1),
  script: scriptKindSchema,
  /** When set, waits for that specific run; a different current run resolves immediately. */
  runId: z.string().min(1).optional(),
});

export type WaitScriptRunInput = z.infer<typeof waitScriptRunInputSchema>;

export const stopScriptRunInputSchema = z.object({
  workspacePath: z.string().min(1),
  script: scriptKindSchema,
});

export type StopScriptRunInput = z.infer<typeof stopScriptRunInputSchema>;

/** Keyboard input into an in-flight run's PTY (interactive prompts). */
export const scriptRunInputSchema = scriptRunKeySchema.extend({
  data: z.string(),
});

export type ScriptRunInput = z.infer<typeof scriptRunInputSchema>;

export const scriptRunResizeInputSchema = scriptRunKeySchema.extend({
  cols: z.number().int().positive(),
  rows: z.number().int().positive(),
});

export type ScriptRunResizeInput = z.infer<typeof scriptRunResizeInputSchema>;
