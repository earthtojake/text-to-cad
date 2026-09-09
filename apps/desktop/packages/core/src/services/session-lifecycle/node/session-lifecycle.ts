import { systemClock, type Clock, type TimerHandle } from '@emdash/shared/scheduling';
import {
  noopConversationLifecycleReporter,
  type ConversationLifecycleReporter,
} from '#services/conversation-reports/node';
import {
  ACTIVITY_OUTPUT_THROTTLE_MS,
  SESSION_IDLE_MS,
  type ActivityFields,
  type ConversationOptions,
  type ConversationSessionLifecycle,
  type DeactivationCause,
  type EvictOptions,
  type IdlePolicyConfig,
  type SessionLifecycle,
  type SessionLifecycleOptions,
  type SessionSnapshotJudgment,
} from '#services/session-lifecycle/api';

type ReapDecision = { action: 'keep' } | { action: 'deactivate'; reason: string };

type IdlePolicy = (
  judgment: SessionSnapshotJudgment,
  activity: ActivityFields,
  now: number
) => ReapDecision;

type ActivityTracker = {
  recordInput(): void;
  recordOutput(): void;
  attach(): void;
  detach(): void;
  snapshot(): ActivityFields;
};

function compileIdlePolicy(config: IdlePolicyConfig): IdlePolicy {
  switch (config.kind) {
    case 'always':
    case 'until-complete':
      return () => ({ action: 'keep' });
    case 'while-attached':
      return (judgment, activity, now) => {
        if (judgment.busy || activity.attachedClients > 0 || activity.detachedAt === null) {
          return { action: 'keep' };
        }
        return now - activity.detachedAt > config.graceMs
          ? { action: 'deactivate', reason: 'detached' }
          : { action: 'keep' };
      };
    case 'idle-after':
      return (judgment, activity, now) => {
        if (judgment.busy) return { action: 'keep' };
        const inputMs = config.inputMs ?? config.outputMs;
        const inputIdle = activity.lastInputAt === null || now - activity.lastInputAt > inputMs;
        const outputIdle =
          activity.lastOutputAt === null || now - activity.lastOutputAt > config.outputMs;
        return inputIdle && outputIdle
          ? { action: 'deactivate', reason: 'idle' }
          : { action: 'keep' };
      };
  }
}

function createActivityTracker(now: () => number): ActivityTracker {
  let lastInputAt: number | null = null;
  let lastOutputAt: number | null = null;
  let attachedClients = 0;
  let detachedAt: number | null = now();

  return {
    recordInput() {
      lastInputAt = now();
    },
    recordOutput() {
      const timestamp = now();
      if (lastOutputAt === null || timestamp - lastOutputAt >= ACTIVITY_OUTPUT_THROTTLE_MS) {
        lastOutputAt = timestamp;
      }
    },
    attach() {
      attachedClients += 1;
      detachedAt = null;
    },
    detach() {
      attachedClients = Math.max(0, attachedClients - 1);
      if (attachedClients === 0) detachedAt = now();
    },
    snapshot() {
      return { attachedClients, detachedAt, lastInputAt, lastOutputAt };
    },
  };
}

export function createSessionLifecycle(
  options: SessionLifecycleOptions<never, void> & { conversation?: undefined }
): SessionLifecycle;
export function createSessionLifecycle<TResume, TCtx = void>(
  options: SessionLifecycleOptions<TResume, TCtx> & {
    conversation: ConversationOptions<TResume, TCtx>;
  }
): ConversationSessionLifecycle;
export function createSessionLifecycle<TResume, TCtx>(
  options: SessionLifecycleOptions<TResume, TCtx>
): ConversationSessionLifecycle {
  const { name, logger, entries, snapshot, syncListEntry, deactivate, evictSteps, conversation } =
    options;
  const clock: Clock = options.clock ?? systemClock;
  const policy = compileIdlePolicy(
    options.idlePolicy ?? { kind: 'idle-after', outputMs: SESSION_IDLE_MS }
  );
  const intervalMs = options.sweepIntervalMs ?? 60_000;
  const reports: ConversationLifecycleReporter =
    conversation?.reports ?? noopConversationLifecycleReporter;

  const trackers = new Map<string, ActivityTracker>();
  const tombstones = new Set<string>();
  const intentQueues = new Map<string, Promise<void>>();
  const evicting = new Map<string, Promise<void>>();

  function trackerFor(key: string): ActivityTracker {
    let tracker = trackers.get(key);
    if (!tracker) {
      tracker = createActivityTracker(() => clock.now());
      trackers.set(key, tracker);
    }
    return tracker;
  }

  /**
   * Post-evict calls must not lazily recreate a tracker (behavior contract 7): a
   * late PTY flush racing an evict would leave an activity entry nothing ever
   * cleans, because the key is gone from the runtime's maps and no future evict
   * will run for it. A tombstoned key is revived only by a re-creation signal:
   * an explicit `recordInput` (every consumer's start/restart path leads with
   * one — record-before-list-entry stays legal per contract 1 — and every other
   * recordInput call site is guarded by the runtime's own maps), or the key
   * re-appearing in `entries()` (terminals restart-replace re-registers the key
   * before spawning; its first record is output-driven). Everything else on a
   * tombstoned key is a straggler from the torn-down session and is dropped.
   */
  function reviveTombstoned(key: string, signal: 'record-input' | 'passive'): boolean {
    if (!tombstones.has(key)) return true;
    if (signal === 'passive' && !entriesInclude(key)) return false;
    tombstones.delete(key);
    return true;
  }

  function entriesInclude(target: string): boolean {
    for (const key of entries()) {
      if (key === target) return true;
    }
    return false;
  }

  function activity(key: string): ActivityFields {
    if (!reviveTombstoned(key, 'passive')) {
      // Transient snapshot matching a fresh tracker; nothing is stored.
      return { lastInputAt: null, lastOutputAt: null, attachedClients: 0, detachedAt: clock.now() };
    }
    return trackerFor(key).snapshot();
  }

  function afterRecord(key: string): void {
    syncListEntry?.(key, activity(key));
    reports.activity(key);
  }

  // --- per-key FIFO intent writes (contract 4) ---------------------------------

  function enqueueIntentWrite(key: string, write: () => Promise<void>): void {
    const tail = intentQueues.get(key) ?? Promise.resolve();
    const next = tail.then(write);
    intentQueues.set(key, next);
    void next.finally(() => {
      if (intentQueues.get(key) === next) intentQueues.delete(key);
    });
  }

  function writeActiveIntent(key: string): void {
    if (!conversation) return;
    const active = conversation.activePayload(key);
    if (!active) return;
    enqueueIntentWrite(key, async () => {
      try {
        const result = await conversation.intents.saveActive({
          conversationId: key,
          payload: active.payload,
          sessionId: active.sessionId,
        });
        if (!result.success) {
          logger.warn(`${name}: failed to persist active session intent`, {
            conversationId: key,
            error: result.error,
          });
        }
      } catch (error) {
        logger.warn(`${name}: failed to persist active session intent`, {
          conversationId: key,
          error: String(error),
        });
      }
    });
  }

  function writeSuspendedIntent(key: string, cause: string): void {
    if (!conversation) return;
    enqueueIntentWrite(key, async () => {
      try {
        const result = await conversation.intents.markSuspended(key, cause);
        if (!result.success) {
          logger.warn(`${name}: failed to mark session intent suspended`, {
            conversationId: key,
            error: result.error,
          });
        }
      } catch (error) {
        logger.warn(`${name}: failed to mark session intent suspended`, {
          conversationId: key,
          error: String(error),
        });
      }
    });
  }

  function writeRemovedIntent(key: string): void {
    if (!conversation) return;
    enqueueIntentWrite(key, async () => {
      try {
        const result = await conversation.intents.remove(key);
        if (!result.success) {
          logger.warn(`${name}: failed to remove session intent`, {
            conversationId: key,
            error: result.error,
          });
        }
      } catch (error) {
        logger.warn(`${name}: failed to remove session intent`, {
          conversationId: key,
          error: String(error),
        });
      }
    });
  }

  // --- eviction (contract 5) ---------------------------------------------------

  function judgeIdle(key: string, now: number): boolean {
    const fields = activity(key);
    const judgment = snapshot(key, fields);
    if (!judgment) return false;
    return policy(judgment, fields, now).action === 'deactivate';
  }

  function evict(key: string, opts: EvictOptions = {}): Promise<void> {
    const inFlight = evicting.get(key);
    if (inFlight) return inFlight;

    const run = (async () => {
      try {
        // Sweeper-driven eviction re-snapshots and re-judges before releasing
        // (contract 3); activity may have arrived between the sweep snapshot and now.
        if (opts.cause === 'idle' && !judgeIdle(key, clock.now())) return;

        for (const step of evictSteps) {
          try {
            await step.run(key);
          } catch (error) {
            logger.warn(`${name}: evict step '${step.name}' failed`, {
              key,
              error: String(error),
            });
          }
        }
        trackers.delete(key);
        tombstones.add(key);
        reports.sessionEnded(key);

        const intent = opts.intent ?? 'suspend';
        if (intent === 'suspend') writeSuspendedIntent(key, opts.cause ?? 'user');
        else if (intent === 'remove') writeRemovedIntent(key);
      } catch (error) {
        // `evict` never rejects; anything escaping the per-step isolation is logged.
        logger.warn(`${name}: evict failed`, { key, error: String(error) });
      } finally {
        evicting.delete(key);
      }
    })();
    evicting.set(key, run);
    return run;
  }

  function end(key: string, cause: DeactivationCause): void {
    reports.sessionEnded(key);
    writeSuspendedIntent(key, cause);
  }

  // --- sweeper (contract 2) ------------------------------------------------------

  let disposed = false;
  let timer: TimerHandle | undefined;
  let sweeping: Promise<void> | null = null;

  const scheduleNext = () => {
    if (disposed) return;
    timer = clock.schedule(
      intervalMs,
      () => {
        void runSweep().finally(scheduleNext);
      },
      { unref: true }
    );
  };

  const runSweep = async (): Promise<void> => {
    if (sweeping) return sweeping;
    sweeping = (async () => {
      try {
        try {
          await options.beforeSweep?.();
        } catch (error) {
          logger.warn(`${name}: sweep failed`, { error: String(error) });
        }

        for (const key of entries()) {
          try {
            const fields = activity(key);
            const judgment = snapshot(key, fields);
            if (!judgment) continue;
            const decision = policy(judgment, fields, clock.now());
            if (decision.action === 'deactivate') {
              await deactivate(key, decision.reason);
            }
          } catch (error) {
            logger.warn(`${name}: sweep failed`, { key, error: String(error) });
          }
        }
      } finally {
        sweeping = null;
      }
    })();
    return sweeping;
  };

  scheduleNext();
  options.scope?.add(() => {
    disposed = true;
    timer?.dispose();
  });

  // --- reconcile skeleton --------------------------------------------------------

  async function reconcile(): Promise<void> {
    const reconcileOptions = conversation?.reconcile;
    if (!conversation || !reconcileOptions) return;

    const listed = await conversation.intents.list();
    if (!listed.success) {
      logger.warn(`${name}: failed to load session intents`, { error: listed.error });
      return;
    }

    let ctx: TCtx = undefined as TCtx;
    if (reconcileOptions.precheck) {
      let prechecked;
      try {
        prechecked = await reconcileOptions.precheck();
      } catch (error) {
        logger.warn(`${name}: reconcile precheck failed`, { error: String(error) });
        return;
      }
      if ('veto' in prechecked) {
        logger.warn(`${name}: reconcile precheck failed`, {
          error: prechecked.error === undefined ? undefined : String(prechecked.error),
        });
        return;
      }
      ctx = prechecked.ctx;
    }

    for (const intent of listed.data) {
      if (intent.status !== 'active') continue;

      const parsed = reconcileOptions.parse(intent, ctx);
      if ('suspend' in parsed) {
        writeSuspendedIntent(intent.conversationId, parsed.suspend);
        continue;
      }

      if (reconcileOptions.gate) {
        const gated = reconcileOptions.gate(parsed.input);
        if ('suspend' in gated) {
          writeSuspendedIntent(intent.conversationId, gated.suspend);
          continue;
        }
      }

      try {
        const result = await reconcileOptions.resume(parsed.input);
        if (!result.success) {
          logger.warn(`${name}: failed to reconcile session intent`, {
            conversationId: intent.conversationId,
            error: result.error,
          });
          writeSuspendedIntent(intent.conversationId, 'reconcile-failed');
        }
      } catch (error) {
        logger.warn(`${name}: failed to reconcile session intent`, {
          conversationId: intent.conversationId,
          error: String(error),
        });
        writeSuspendedIntent(intent.conversationId, 'reconcile-failed');
      }
    }
  }

  return {
    recordInput(key) {
      reviveTombstoned(key, 'record-input');
      trackerFor(key).recordInput();
      afterRecord(key);
    },
    recordOutput(key) {
      if (!reviveTombstoned(key, 'passive')) return;
      trackerFor(key).recordOutput();
      afterRecord(key);
    },
    attach(key) {
      if (!reviveTombstoned(key, 'passive')) return;
      trackerFor(key).attach();
    },
    detach(key) {
      if (!reviveTombstoned(key, 'passive')) return;
      trackerFor(key).detach();
      syncListEntry?.(key, activity(key));
    },
    activity,
    end,
    evict,
    sweepNow: runSweep,
    dispose() {
      disposed = true;
      timer?.dispose();
    },
    started(key, report) {
      if (report) reports.sessionStarted(report);
      writeActiveIntent(key);
    },
    providerSessionId(_key, input) {
      reports.providerSessionId(input);
    },
    saveIntent(key) {
      writeActiveIntent(key);
    },
    reconcile,
  };
}
