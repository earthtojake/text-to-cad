import type { Result, Serializable } from '@emdash/shared';
import type { Scope } from '@emdash/shared/concurrency';
import type { Logger } from '@emdash/shared/logger';
import type { Clock } from '@emdash/shared/scheduling';
import { z } from 'zod';
import type {
  ReportProviderSessionIdInput,
  ReportSessionStartedInput,
} from '#services/conversation-reports/api';
import type { ConversationLifecycleReporter } from '#services/conversation-reports/node';
import type { SessionIntent, SessionIntentStore } from '#services/session-intents/api';

export const idlePolicyConfigSchema = z.discriminatedUnion('kind', [
  z.object({
    kind: z.literal('while-attached'),
    graceMs: z.number().int().positive(),
  }),
  z.object({
    kind: z.literal('idle-after'),
    outputMs: z.number().int().positive(),
    inputMs: z.number().int().positive().optional(),
  }),
  z.object({ kind: z.literal('until-complete') }),
  z.object({ kind: z.literal('always') }),
]);

export type IdlePolicyConfig = z.infer<typeof idlePolicyConfigSchema>;

/**
 * Shared idle window for the agent session runtimes (acp, tui-agents): a session
 * with no output for an hour is idle and can be deactivated; resuming
 * re-materializes it. Both worker spawn specs bake this into their `idle-after`
 * lifecycle policy so the invariant is stated once.
 */
export const SESSION_IDLE_MS = 60 * 60_000;

/**
 * The activity tracker keeps at most one output timestamp per throttle window.
 * Invariant (behavior contract 6): this must stay shorter than any busy window a
 * consumer's `snapshot` seam derives from `lastOutputAt`.
 */
export const ACTIVITY_OUTPUT_THROTTLE_MS = 30_000;

export interface ActivityFields {
  lastInputAt: number | null;
  lastOutputAt: number | null;
  attachedClients: number;
  detachedAt: number | null;
}

export interface EvictionStep {
  /** Appears in warn logs when the step fails. */
  name: string;
  run: (key: string) => void | Promise<void>;
}

/** 'idle' | 'user' | 'process-exit' | runtime-specific. */
export type DeactivationCause = string;

export interface SessionSnapshotJudgment {
  running: boolean;
  busy: boolean;
}

export interface ReconcileOptions<TResume, TCtx> {
  /** Run-vetoing pre-scan; a veto (or throw) aborts the whole reconcile. */
  precheck?: () => Promise<{ ctx: TCtx } | { veto: true; error?: unknown }>;
  parse: (intent: SessionIntent, ctx: TCtx) => { input: TResume } | { suspend: string };
  gate?: (input: TResume) => { ok: true } | { suspend: string };
  resume: (input: TResume) => Promise<Result<unknown, unknown>>;
}

export interface ConversationOptions<TResume, TCtx> {
  intents: SessionIntentStore;
  /** Builds the persistable active-intent payload; null = nothing to persist. */
  activePayload: (key: string) => { payload: Serializable; sessionId?: string | null } | null;
  /** Defaults to the noop reporter. */
  reports?: ConversationLifecycleReporter;
  reconcile?: ReconcileOptions<TResume, TCtx>;
}

export interface SessionLifecycleOptions<TResume, TCtx> {
  /** Log prefix, e.g. 'SessionManager'. */
  name: string;
  logger: Logger;
  /** The ONLY time source; defaults to systemClock. */
  clock?: Clock;
  scope?: Scope;
  /** Defaults to `{ kind: 'idle-after', outputMs: SESSION_IDLE_MS }`. */
  idlePolicy?: IdlePolicyConfig;
  /** Defaults to 60_000. */
  sweepIntervalMs?: number;
  beforeSweep?: () => void | Promise<void>;

  /** Authoritative session keys — never the published list. */
  entries: () => Iterable<string>;
  /** Per-runtime running/busy judgment; null = not sweepable. */
  snapshot: (key: string, activity: ActivityFields) => SessionSnapshotJudgment | null;
  /** MUST no-op when the list has no entry for the key. */
  syncListEntry?: (key: string, activity: ActivityFields) => void;
  /** What the sweeper invokes; the runtime's own verb (which calls back into end/evict). */
  deactivate: (key: string, cause: DeactivationCause) => void | Promise<void>;

  /** The COMPLETE per-key resource list, in teardown order. */
  evictSteps: EvictionStep[];

  /** Omit for terminals — absence IS the subset contract. */
  conversation?: ConversationOptions<TResume, TCtx>;
}

export interface EvictOptions {
  cause?: DeactivationCause;
  /** Persisted-intent disposition; ignored on instances without a conversation block. */
  intent?: 'suspend' | 'remove' | 'keep';
}

export interface SessionLifecycle {
  /**
   * tracker -> syncListEntry -> reporter.activity, in that order. `recordInput`
   * also revives an evicted key (it is the re-creation signal on the agent
   * runtimes' start paths, which record before their maps repopulate).
   */
  recordInput(key: string): void;
  /** Like recordInput, but dropped for evicted keys (behavior contract 7). */
  recordOutput(key: string): void;
  /** Dropped for evicted keys (behavior contract 7). */
  attach(key: string): void;
  /** Uniform post-detach list sync; dropped for evicted keys (behavior contract 7). */
  detach(key: string): void;
  /** For back-filling the first list write. */
  activity(key: string): ActivityFields;

  /**
   * Suspend-but-retain: sessionEnded + enqueue markSuspended; resources KEPT; the
   * runtime's snapshot seam (null for tombstoned keys) keeps the key sweep-inert.
   */
  end(key: string, cause: DeactivationCause): void;
  /**
   * Full teardown: [idle re-check when cause === 'idle'] -> run evictSteps (errors
   * isolated, logged per step name) -> drop tracker -> sessionEnded exactly once ->
   * enqueue intent write (default 'suspend'). Never rejects; concurrent evicts of one
   * key coalesce onto the in-flight promise.
   *
   * Post-evict record/attach/detach calls for the key are dropped, never lazily
   * recreated (behavior contract 7): a late PTY flush racing the evict would
   * otherwise leave an activity entry nothing ever cleans. The key is revived by a
   * fresh `recordInput` (agent start paths) or by re-appearing in `entries()`
   * (terminals re-registers the key before spawning on restart-replace).
   */
  evict(key: string, opts?: EvictOptions): Promise<void>;

  sweepNow(): Promise<void>;
  /** Stops the sweeper; does NOT evict (component scope owns process teardown). */
  dispose(): void;
}

export interface ConversationSessionLifecycle extends SessionLifecycle {
  /** sessionStarted (when a report is given) + saveActive. */
  started(key: string, report?: ReportSessionStartedInput): void;
  providerSessionId(key: string, input: ReportProviderSessionIdInput): void;
  /** Re-persist the active intent from activePayload. */
  saveIntent(key: string): void;
  reconcile(): Promise<void>;
}
