import { err, ok, type Result } from '@emdash/shared';
import { noopLogger, type Logger } from '@emdash/shared/logger';
import { createManualClock } from '@emdash/shared/testing';
import { describe, expect, it, vi } from 'vitest';
import { createRecordingConversationLifecycleReporter } from '#services/conversation-reports/node/testing';
import {
  createMemorySessionIntentStore,
  type SessionIntent,
  type SessionIntentError,
  type SessionIntentStore,
} from '#services/session-intents/api';
import {
  ACTIVITY_OUTPUT_THROTTLE_MS,
  type ActivityFields,
  type ConversationOptions,
  type EvictionStep,
  type SessionLifecycleOptions,
  type SessionSnapshotJudgment,
} from '#services/session-lifecycle/api';
import { createSessionLifecycle } from './session-lifecycle';
import { expectNoSessionResidue, mapContainer, recordContainer } from './testing';

type Harness = {
  keys: Set<string>;
  judgments: Map<string, SessionSnapshotJudgment | null>;
  deactivations: Array<{ key: string; cause: string }>;
  syncs: Array<{ key: string; activity: ActivityFields }>;
  warns: Array<{ message: string; context: unknown }>;
  logger: Logger;
};

function makeHarness(): Harness {
  const warns: Harness['warns'] = [];
  return {
    keys: new Set(),
    judgments: new Map(),
    deactivations: [],
    syncs: [],
    warns,
    logger: {
      ...noopLogger,
      warn: (message: string, context?: unknown) => {
        warns.push({ message, context });
      },
    },
  };
}

type BaseOptions = Omit<SessionLifecycleOptions<never, void>, 'conversation'>;

function baseOptions(harness: Harness, overrides: Partial<BaseOptions> = {}): BaseOptions {
  return {
    name: 'TestRuntime',
    logger: harness.logger,
    entries: () => harness.keys,
    snapshot: (key) => harness.judgments.get(key) ?? null,
    syncListEntry: (key, activity) => harness.syncs.push({ key, activity }),
    deactivate: (key, cause) => {
      harness.deactivations.push({ key, cause });
    },
    evictSteps: [],
    ...overrides,
  };
}

function settle(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

describe('createSessionLifecycle', () => {
  describe('record ordering (contract 1)', () => {
    it('runs tracker write, then syncListEntry, then reporter.activity', () => {
      const clock = createManualClock(1_000);
      const harness = makeHarness();
      const reports = createRecordingConversationLifecycleReporter();
      const order: string[] = [];
      const lifecycle = createSessionLifecycle({
        ...baseOptions(harness, {
          syncListEntry: (key, activity) => {
            order.push('sync');
            harness.syncs.push({ key, activity });
          },
        }),
        clock,
        conversation: {
          intents: createMemorySessionIntentStore(),
          activePayload: () => null,
          reports: {
            ...reports,
            activity: (conversationId) => {
              order.push('report');
              reports.activity(conversationId);
            },
          },
        },
      });

      lifecycle.recordInput('s1');

      expect(order).toEqual(['sync', 'report']);
      // The sync already sees the tracker write: the record happened first.
      expect(harness.syncs[0]).toMatchObject({ key: 's1', activity: { lastInputAt: 1_000 } });
      expect(reports.activities).toEqual(['s1']);
    });

    it('records legally before any list entry exists and back-fills via activity()', () => {
      const clock = createManualClock(500);
      const harness = makeHarness();
      const lifecycle = createSessionLifecycle({ ...baseOptions(harness), clock });

      lifecycle.recordInput('unlisted');

      expect(lifecycle.activity('unlisted')).toMatchObject({
        lastInputAt: 500,
        lastOutputAt: null,
      });
    });

    it('syncs the list uniformly after detach', () => {
      const clock = createManualClock(0);
      const harness = makeHarness();
      const lifecycle = createSessionLifecycle({ ...baseOptions(harness), clock });

      lifecycle.attach('s1');
      expect(lifecycle.activity('s1').attachedClients).toBe(1);
      expect(lifecycle.activity('s1').detachedAt).toBeNull();

      lifecycle.detach('s1');

      expect(harness.syncs.at(-1)).toMatchObject({
        key: 's1',
        activity: { attachedClients: 0, detachedAt: 0 },
      });
    });
  });

  describe('sweeper (contract 2)', () => {
    it('deactivates idle entries via the runtime deactivate seam', async () => {
      const clock = createManualClock(0);
      const harness = makeHarness();
      const lifecycle = createSessionLifecycle({
        ...baseOptions(harness),
        clock,
        idlePolicy: { kind: 'idle-after', outputMs: 1_000 },
        sweepIntervalMs: 500,
      });
      harness.keys.add('s1');
      harness.judgments.set('s1', { running: true, busy: false });
      lifecycle.recordOutput('s1');

      await clock.advanceBy(500);
      expect(harness.deactivations).toEqual([]);

      await clock.advanceBy(1_000);
      expect(harness.deactivations).toEqual([{ key: 's1', cause: 'idle' }]);
    });

    it('skips entries whose snapshot is null (not sweepable)', async () => {
      const clock = createManualClock(0);
      const harness = makeHarness();
      const lifecycle = createSessionLifecycle({
        ...baseOptions(harness),
        clock,
        idlePolicy: { kind: 'idle-after', outputMs: 1 },
        sweepIntervalMs: 100,
      });
      harness.keys.add('tombstoned');
      harness.judgments.set('tombstoned', null);

      await clock.advanceBy(500);

      expect(harness.deactivations).toEqual([]);
      lifecycle.dispose();
    });

    it('schedules the next tick only after the current sweep settles', async () => {
      const clock = createManualClock(0);
      const harness = makeHarness();
      let releaseDeactivate!: () => void;
      const blocked = new Promise<void>((resolve) => {
        releaseDeactivate = resolve;
      });
      let sweepEntries = 0;
      createSessionLifecycle({
        ...baseOptions(harness, {
          entries: () => {
            sweepEntries += 1;
            return harness.keys;
          },
          deactivate: () => blocked,
        }),
        clock,
        idlePolicy: { kind: 'idle-after', outputMs: 1 },
        sweepIntervalMs: 100,
      });
      harness.keys.add('s1');
      harness.judgments.set('s1', { running: true, busy: false });

      await clock.advanceBy(100);
      expect(sweepEntries).toBe(1);

      // The sweep is stuck in deactivate; no overlapping sweep starts.
      await clock.advanceBy(1_000);
      expect(sweepEntries).toBe(1);

      releaseDeactivate();
      await settle();
      await clock.advanceBy(100);
      expect(sweepEntries).toBe(2);
    });

    it('coalesces sweepNow onto an in-flight sweep', async () => {
      const clock = createManualClock(0);
      const harness = makeHarness();
      let releaseDeactivate!: () => void;
      const blocked = new Promise<void>((resolve) => {
        releaseDeactivate = resolve;
      });
      let sweepEntries = 0;
      const lifecycle = createSessionLifecycle({
        ...baseOptions(harness, {
          entries: () => {
            sweepEntries += 1;
            return harness.keys;
          },
          deactivate: () => blocked,
        }),
        clock,
        idlePolicy: { kind: 'idle-after', outputMs: 1 },
        sweepIntervalMs: 60_000,
      });
      harness.keys.add('s1');
      harness.judgments.set('s1', { running: true, busy: false });

      const first = lifecycle.sweepNow();
      const second = lifecycle.sweepNow();
      releaseDeactivate();
      await Promise.all([first, second]);

      expect(sweepEntries).toBe(1);
    });

    it('isolates beforeSweep errors and keeps sweeping entries', async () => {
      const clock = createManualClock(0);
      const harness = makeHarness();
      const lifecycle = createSessionLifecycle({
        ...baseOptions(harness),
        clock,
        idlePolicy: { kind: 'idle-after', outputMs: 1 },
        beforeSweep: () => {
          throw new Error('tmux listing failed');
        },
      });
      harness.keys.add('s1');
      harness.judgments.set('s1', { running: true, busy: false });
      lifecycle.recordOutput('s1');
      await clock.advanceBy(10);

      await lifecycle.sweepNow();

      expect(harness.warns).toContainEqual(
        expect.objectContaining({ message: 'TestRuntime: sweep failed' })
      );
      expect(harness.deactivations).toEqual([{ key: 's1', cause: 'idle' }]);
    });

    it('isolates per-entry errors and continues with later entries', async () => {
      const clock = createManualClock(0);
      const harness = makeHarness();
      const lifecycle = createSessionLifecycle({
        ...baseOptions(harness, {
          snapshot: (key) => {
            if (key === 'broken') throw new Error('boom');
            return harness.judgments.get(key) ?? null;
          },
        }),
        clock,
        idlePolicy: { kind: 'idle-after', outputMs: 1 },
      });
      harness.keys.add('broken');
      harness.keys.add('healthy');
      harness.judgments.set('healthy', { running: true, busy: false });
      lifecycle.recordOutput('healthy');
      await clock.advanceBy(10);

      await lifecycle.sweepNow();

      expect(harness.warns).toContainEqual(
        expect.objectContaining({
          message: 'TestRuntime: sweep failed',
          context: expect.objectContaining({ key: 'broken' }),
        })
      );
      expect(harness.deactivations).toEqual([{ key: 'healthy', cause: 'idle' }]);
    });

    it('stops sweeping after dispose without evicting anything', async () => {
      const clock = createManualClock(0);
      const harness = makeHarness();
      const steps: string[] = [];
      const lifecycle = createSessionLifecycle({
        ...baseOptions(harness, {
          evictSteps: [{ name: 'record', run: (key) => void steps.push(key) }],
        }),
        clock,
        idlePolicy: { kind: 'idle-after', outputMs: 1 },
        sweepIntervalMs: 100,
      });
      harness.keys.add('s1');
      harness.judgments.set('s1', { running: true, busy: false });

      lifecycle.dispose();
      await clock.advanceBy(1_000);

      expect(harness.deactivations).toEqual([]);
      expect(steps).toEqual([]);
    });
  });

  describe('idle-policy math', () => {
    it('keeps busy sessions under idle-after regardless of timestamps', async () => {
      const clock = createManualClock(0);
      const harness = makeHarness();
      const lifecycle = createSessionLifecycle({
        ...baseOptions(harness),
        clock,
        idlePolicy: { kind: 'idle-after', outputMs: 1_000 },
      });
      harness.keys.add('s1');
      harness.judgments.set('s1', { running: true, busy: true });
      await clock.advanceBy(10_000);

      await lifecycle.sweepNow();

      expect(harness.deactivations).toEqual([]);
    });

    it('requires both input and output idleness under idle-after', async () => {
      const clock = createManualClock(0);
      const harness = makeHarness();
      const lifecycle = createSessionLifecycle({
        ...baseOptions(harness),
        clock,
        idlePolicy: { kind: 'idle-after', outputMs: 1_000 },
      });
      harness.keys.add('s1');
      harness.judgments.set('s1', { running: true, busy: false });
      lifecycle.recordOutput('s1');
      await clock.advanceBy(1_500);
      lifecycle.recordInput('s1');

      await lifecycle.sweepNow();
      expect(harness.deactivations).toEqual([]);

      await clock.advanceBy(1_100);
      await lifecycle.sweepNow();
      expect(harness.deactivations).toEqual([{ key: 's1', cause: 'idle' }]);
    });

    it('deactivates detached sessions after the while-attached grace period', async () => {
      const clock = createManualClock(0);
      const harness = makeHarness();
      const lifecycle = createSessionLifecycle({
        ...baseOptions(harness),
        clock,
        idlePolicy: { kind: 'while-attached', graceMs: 1_000 },
      });
      harness.keys.add('s1');
      harness.judgments.set('s1', { running: true, busy: false });
      lifecycle.attach('s1');

      await clock.advanceBy(5_000);
      await lifecycle.sweepNow();
      expect(harness.deactivations).toEqual([]);

      lifecycle.detach('s1');
      await clock.advanceBy(1_100);
      await lifecycle.sweepNow();
      expect(harness.deactivations).toEqual([{ key: 's1', cause: 'detached' }]);
    });

    it("never deactivates under the 'always' policy", async () => {
      const clock = createManualClock(0);
      const harness = makeHarness();
      const lifecycle = createSessionLifecycle({
        ...baseOptions(harness),
        clock,
        idlePolicy: { kind: 'always' },
      });
      harness.keys.add('s1');
      harness.judgments.set('s1', { running: true, busy: false });
      await clock.advanceBy(100 * 60 * 60_000);

      await lifecycle.sweepNow();

      expect(harness.deactivations).toEqual([]);
    });
  });

  describe('idle re-check on eviction (contract 3)', () => {
    it('aborts an idle-cause evict when the session became busy again', async () => {
      const clock = createManualClock(0);
      const harness = makeHarness();
      const reports = createRecordingConversationLifecycleReporter();
      const intents = createMemorySessionIntentStore();
      const steps: string[] = [];
      const lifecycle = createSessionLifecycle({
        ...baseOptions(harness, {
          evictSteps: [{ name: 'record', run: (key) => void steps.push(key) }],
        }),
        clock,
        idlePolicy: { kind: 'idle-after', outputMs: 1_000 },
        conversation: {
          intents,
          activePayload: () => null,
          reports,
        },
      });
      await intents.saveActive({ conversationId: 's1', payload: {} });
      harness.judgments.set('s1', { running: true, busy: true });

      await lifecycle.evict('s1', { cause: 'idle' });

      expect(steps).toEqual([]);
      expect(reports.ended).toEqual([]);
      await settle();
      expect(intents.snapshot()[0]).toMatchObject({ conversationId: 's1', status: 'active' });
    });

    it('aborts an idle-cause evict when the key is no longer sweepable', async () => {
      const clock = createManualClock(0);
      const harness = makeHarness();
      const steps: string[] = [];
      const lifecycle = createSessionLifecycle({
        ...baseOptions(harness, {
          evictSteps: [{ name: 'record', run: (key) => void steps.push(key) }],
        }),
        clock,
        idlePolicy: { kind: 'idle-after', outputMs: 1_000 },
      });
      harness.judgments.set('s1', null);

      await lifecycle.evict('s1', { cause: 'idle' });

      expect(steps).toEqual([]);
    });

    it('proceeds with an idle-cause evict when the session is still idle', async () => {
      const clock = createManualClock(0);
      const harness = makeHarness();
      const steps: string[] = [];
      const lifecycle = createSessionLifecycle({
        ...baseOptions(harness, {
          evictSteps: [{ name: 'record', run: (key) => void steps.push(key) }],
        }),
        clock,
        idlePolicy: { kind: 'idle-after', outputMs: 1_000 },
      });
      harness.judgments.set('s1', { running: true, busy: false });
      lifecycle.recordOutput('s1');
      await clock.advanceBy(2_000);

      await lifecycle.evict('s1', { cause: 'idle' });

      expect(steps).toEqual(['s1']);
    });
  });

  describe('FIFO intent writes (contract 4)', () => {
    it('serializes suspend-then-remove so a slow markSuspended cannot resurrect the intent', async () => {
      const clock = createManualClock(0);
      const harness = makeHarness();
      const stored = new Map<string, SessionIntent>();
      stored.set('s1', {
        conversationId: 's1',
        status: 'active',
        payload: {},
        updatedAt: 0,
      });
      let releaseSuspend!: () => void;
      const suspendGate = new Promise<void>((resolve) => {
        releaseSuspend = resolve;
      });
      const removeCalls: string[] = [];
      const intents: SessionIntentStore = {
        async list() {
          return ok([...stored.values()]);
        },
        async saveActive() {
          return ok();
        },
        async markSuspended(conversationId, cause) {
          // Read-modify-write with a hole in the middle, like the KV store.
          const existing = stored.get(conversationId);
          await suspendGate;
          if (existing) {
            stored.set(conversationId, {
              ...existing,
              status: 'suspended',
              suspendedCause: cause,
              updatedAt: 1,
            });
          }
          return ok();
        },
        async remove(conversationId) {
          removeCalls.push(conversationId);
          stored.delete(conversationId);
          return ok();
        },
      };
      const lifecycle = createSessionLifecycle({
        ...baseOptions(harness),
        clock,
        conversation: { intents, activePayload: () => null },
      });

      lifecycle.end('s1', 'user');
      await lifecycle.evict('s1', { intent: 'remove' });

      // Without FIFO ordering the remove would land inside markSuspended's
      // read-modify-write window and the suspended write would resurrect it.
      expect(removeCalls).toEqual([]);
      releaseSuspend();
      await vi.waitFor(() => expect(removeCalls).toEqual(['s1']));
      expect(stored.has('s1')).toBe(false);
    });

    it('logs and swallows intent-write failures', async () => {
      const clock = createManualClock(0);
      const harness = makeHarness();
      const failure: Result<void, SessionIntentError> = err({ type: 'io', message: 'disk full' });
      const intents: SessionIntentStore = {
        async list() {
          return ok([]);
        },
        async saveActive() {
          return failure;
        },
        async markSuspended() {
          return failure;
        },
        async remove() {
          return failure;
        },
      };
      const lifecycle = createSessionLifecycle({
        ...baseOptions(harness),
        clock,
        conversation: {
          intents,
          activePayload: () => ({ payload: { a: 1 }, sessionId: null }),
        },
      });

      lifecycle.saveIntent('s1');
      lifecycle.end('s1', 'user');
      await lifecycle.evict('s1', { intent: 'remove' });
      await settle();

      const messages = harness.warns.map((warn) => warn.message);
      expect(messages).toContain('TestRuntime: failed to persist active session intent');
      expect(messages).toContain('TestRuntime: failed to mark session intent suspended');
      expect(messages).toContain('TestRuntime: failed to remove session intent');
    });
  });

  describe('eviction (contract 5)', () => {
    it('runs every named step in order, isolates failures, and reports sessionEnded exactly once, after the steps', async () => {
      const clock = createManualClock(0);
      const harness = makeHarness();
      const reports = createRecordingConversationLifecycleReporter();
      const order: string[] = [];
      const steps: EvictionStep[] = [
        { name: 'first', run: () => void order.push('first') },
        {
          name: 'exploding',
          run: () => {
            throw new Error('teardown failed');
          },
        },
        { name: 'last', run: () => void order.push('last') },
      ];
      const lifecycle = createSessionLifecycle({
        ...baseOptions(harness, { evictSteps: steps }),
        clock,
        conversation: {
          intents: createMemorySessionIntentStore(),
          activePayload: () => null,
          reports: {
            ...reports,
            sessionEnded: (conversationId) => {
              order.push('ended');
              reports.sessionEnded(conversationId);
            },
          },
        },
      });

      await lifecycle.evict('s1');

      expect(order).toEqual(['first', 'last', 'ended']);
      expect(reports.ended).toEqual(['s1']);
      expect(harness.warns).toContainEqual(
        expect.objectContaining({
          message: "TestRuntime: evict step 'exploding' failed",
          context: expect.objectContaining({ key: 's1' }),
        })
      );
    });

    it('coalesces concurrent evicts of one key onto the in-flight promise', async () => {
      const clock = createManualClock(0);
      const harness = makeHarness();
      let runs = 0;
      let release!: () => void;
      const gate = new Promise<void>((resolve) => {
        release = resolve;
      });
      const lifecycle = createSessionLifecycle({
        ...baseOptions(harness, {
          evictSteps: [
            {
              name: 'slow',
              run: async () => {
                runs += 1;
                await gate;
              },
            },
          ],
        }),
        clock,
      });

      const first = lifecycle.evict('s1');
      const second = lifecycle.evict('s1');
      expect(second).toBe(first);
      release();
      await Promise.all([first, second]);

      expect(runs).toBe(1);
    });

    it('enqueues the requested intent disposition', async () => {
      const clock = createManualClock(0);
      const harness = makeHarness();
      const intents = createMemorySessionIntentStore();
      const lifecycle = createSessionLifecycle({
        ...baseOptions(harness),
        clock,
        conversation: { intents, activePayload: () => null },
      });
      await intents.saveActive({ conversationId: 'suspend-me', payload: {} });
      await intents.saveActive({ conversationId: 'remove-me', payload: {} });
      await intents.saveActive({ conversationId: 'keep-me', payload: {} });

      await lifecycle.evict('suspend-me', { cause: 'process-exit' });
      await lifecycle.evict('remove-me', { intent: 'remove' });
      await lifecycle.evict('keep-me', { intent: 'keep' });
      await settle();

      const byId = new Map(intents.snapshot().map((intent) => [intent.conversationId, intent]));
      expect(byId.get('suspend-me')).toMatchObject({
        status: 'suspended',
        suspendedCause: 'process-exit',
      });
      expect(byId.has('remove-me')).toBe(false);
      expect(byId.get('keep-me')).toMatchObject({ status: 'active' });
    });
  });

  describe('end vs evict', () => {
    it('end reports sessionEnded and suspends the intent without running evict steps', async () => {
      const clock = createManualClock(0);
      const harness = makeHarness();
      const reports = createRecordingConversationLifecycleReporter();
      const intents = createMemorySessionIntentStore();
      const steps: string[] = [];
      const lifecycle = createSessionLifecycle({
        ...baseOptions(harness, {
          evictSteps: [{ name: 'record', run: (key) => void steps.push(key) }],
        }),
        clock,
        conversation: { intents, activePayload: () => null, reports },
      });
      await intents.saveActive({ conversationId: 's1', payload: {} });
      lifecycle.recordInput('s1');

      lifecycle.end('s1', 'user');
      await settle();

      expect(steps).toEqual([]);
      expect(reports.ended).toEqual(['s1']);
      expect(intents.snapshot()[0]).toMatchObject({ status: 'suspended', suspendedCause: 'user' });
      // Resources (here: the tracker) are kept.
      expect(lifecycle.activity('s1').lastInputAt).toBe(0);
    });
  });

  describe('output throttle (contract 6)', () => {
    it('keeps at most one output timestamp per throttle window', async () => {
      const clock = createManualClock(0);
      const harness = makeHarness();
      const lifecycle = createSessionLifecycle({ ...baseOptions(harness), clock });

      lifecycle.recordOutput('s1');
      await clock.advanceBy(ACTIVITY_OUTPUT_THROTTLE_MS - 1);
      lifecycle.recordOutput('s1');
      expect(lifecycle.activity('s1').lastOutputAt).toBe(0);

      await clock.advanceBy(1);
      lifecycle.recordOutput('s1');
      expect(lifecycle.activity('s1').lastOutputAt).toBe(ACTIVITY_OUTPUT_THROTTLE_MS);
    });

    it('stays shorter than the busy windows consumers derive from lastOutputAt', () => {
      // tui-agents judges busy over a 60s output recency window; the tracker's
      // throttle must be shorter or a steadily-chatty session would look idle.
      const TUI_BUSY_OUTPUT_WINDOW_MS = 60_000;
      expect(ACTIVITY_OUTPUT_THROTTLE_MS).toBeLessThan(TUI_BUSY_OUTPUT_WINDOW_MS);
    });
  });

  describe('post-evict records (contract 7)', () => {
    /** An instance whose evictSteps remove the key from the runtime map, like real consumers. */
    function evictionHarness() {
      const clock = createManualClock(0);
      const harness = makeHarness();
      const reports = createRecordingConversationLifecycleReporter();
      const lifecycle = createSessionLifecycle({
        ...baseOptions(harness, {
          evictSteps: [{ name: 'drop-key', run: (key) => void harness.keys.delete(key) }],
        }),
        clock,
        conversation: {
          intents: createMemorySessionIntentStore(),
          activePayload: () => null,
          reports,
        },
      });
      return { clock, harness, reports, lifecycle };
    }

    it('drops records for evicted keys instead of recreating an activity entry', async () => {
      const { clock, harness, reports, lifecycle } = evictionHarness();
      harness.keys.add('s1');
      lifecycle.recordOutput('s1');

      await clock.advanceBy(5_000);
      await lifecycle.evict('s1');
      const syncsBefore = harness.syncs.length;
      const activitiesBefore = reports.activities.length;

      // A late PTY flush racing the evict: the key is gone from the runtime's
      // maps, so nothing would ever clean a lazily recreated tracker.
      lifecycle.recordOutput('s1');

      expect(harness.syncs.length).toBe(syncsBefore);
      expect(reports.activities.length).toBe(activitiesBefore);
      expect(lifecycle.activity('s1')).toEqual({
        lastInputAt: null,
        lastOutputAt: null,
        attachedClients: 0,
        detachedAt: 5_000,
      });
    });

    it('drops attach/detach for evicted keys; activity() reads do not resurrect tracking', async () => {
      const { harness, lifecycle } = evictionHarness();
      harness.keys.add('s1');
      lifecycle.recordOutput('s1');
      await lifecycle.evict('s1');
      const syncsBefore = harness.syncs.length;

      lifecycle.attach('s1');
      expect(lifecycle.activity('s1').attachedClients).toBe(0);

      // Neither the attach nor the activity() read may have revived the key.
      lifecycle.recordOutput('s1');
      expect(lifecycle.activity('s1').lastOutputAt).toBeNull();

      lifecycle.detach('s1');
      expect(harness.syncs.length).toBe(syncsBefore);
    });

    it('revives with a fresh idle baseline when a genuine restart records input (agent start paths)', async () => {
      const { clock, harness, lifecycle } = evictionHarness();
      harness.keys.add('s1');
      lifecycle.recordInput('s1');
      lifecycle.recordOutput('s1');

      await clock.advanceBy(5_000);
      await lifecycle.evict('s1');
      // acp/tui restart: the start path leads with recordInput, in some paths
      // before the runtime's own maps are repopulated (contract 1).
      lifecycle.recordInput('s1');

      expect(lifecycle.activity('s1')).toEqual({
        lastInputAt: 5_000,
        lastOutputAt: null,
        attachedClients: 0,
        detachedAt: 5_000,
      });
      lifecycle.recordOutput('s1');
      expect(lifecycle.activity('s1').lastOutputAt).toBe(5_000);
    });

    it('revives when the runtime re-registers the key before the first record (terminals restart)', async () => {
      const { clock, harness, lifecycle } = evictionHarness();
      harness.keys.add('s1');
      lifecycle.recordOutput('s1');

      await clock.advanceBy(5_000);
      await lifecycle.evict('s1');
      // Terminals restart-replace: evict-then-create re-registers the key in the
      // authoritative map before spawning; the first record is output-driven.
      harness.keys.add('s1');
      const syncsBefore = harness.syncs.length;
      lifecycle.recordOutput('s1');

      expect(lifecycle.activity('s1').lastOutputAt).toBe(5_000);
      expect(harness.syncs.length).toBe(syncsBefore + 1);
    });
  });

  describe('conversation verbs', () => {
    it('started reports sessionStarted and persists the active payload', async () => {
      const clock = createManualClock(0);
      const harness = makeHarness();
      const reports = createRecordingConversationLifecycleReporter();
      const intents = createMemorySessionIntentStore();
      const lifecycle = createSessionLifecycle({
        ...baseOptions(harness),
        clock,
        conversation: {
          intents,
          activePayload: (key) => ({ payload: { key, kept: true }, sessionId: 'provider-1' }),
          reports,
        },
      });

      lifecycle.started('s1', {
        conversationId: 's1',
        providerSessionId: 'provider-1',
        resumeOutcome: null,
      });
      await settle();

      expect(reports.started).toEqual([
        { conversationId: 's1', providerSessionId: 'provider-1', resumeOutcome: null },
      ]);
      expect(intents.snapshot()[0]).toMatchObject({
        conversationId: 's1',
        status: 'active',
        sessionId: 'provider-1',
        payload: { key: 's1', kept: true },
      });
    });

    it('started without a report only persists the intent', async () => {
      const clock = createManualClock(0);
      const harness = makeHarness();
      const reports = createRecordingConversationLifecycleReporter();
      const intents = createMemorySessionIntentStore();
      const lifecycle = createSessionLifecycle({
        ...baseOptions(harness),
        clock,
        conversation: {
          intents,
          activePayload: () => ({ payload: {}, sessionId: null }),
          reports,
        },
      });

      lifecycle.started('s1');
      await settle();

      expect(reports.started).toEqual([]);
      expect(intents.snapshot()).toHaveLength(1);
    });

    it('saveIntent skips persistence when activePayload returns null', async () => {
      const clock = createManualClock(0);
      const harness = makeHarness();
      const intents = createMemorySessionIntentStore();
      const lifecycle = createSessionLifecycle({
        ...baseOptions(harness),
        clock,
        conversation: { intents, activePayload: () => null },
      });

      lifecycle.saveIntent('s1');
      await settle();

      expect(intents.snapshot()).toEqual([]);
    });

    it('providerSessionId forwards to the reporter', () => {
      const clock = createManualClock(0);
      const harness = makeHarness();
      const reports = createRecordingConversationLifecycleReporter();
      const lifecycle = createSessionLifecycle({
        ...baseOptions(harness),
        clock,
        conversation: {
          intents: createMemorySessionIntentStore(),
          activePayload: () => null,
          reports,
        },
      });

      lifecycle.providerSessionId('s1', { conversationId: 's1', providerSessionId: 'rebound' });

      expect(reports.providerIds).toEqual([{ conversationId: 's1', providerSessionId: 'rebound' }]);
    });
  });

  describe('reconcile skeleton', () => {
    type ResumeInput = { conversationId: string; live: boolean };

    function reconcileHarness(options: {
      intents: SessionIntentStore;
      precheck?: () => Promise<{ ctx: void } | { veto: true; error?: unknown }>;
      gate?: (input: ResumeInput) => { ok: true } | { suspend: string };
      resume?: (input: ResumeInput) => Promise<Result<unknown, unknown>>;
    }) {
      const harness = makeHarness();
      const resumed: ResumeInput[] = [];
      const lifecycle = createSessionLifecycle<ResumeInput, void>({
        ...baseOptions(harness),
        clock: createManualClock(0),
        conversation: {
          intents: options.intents,
          activePayload: () => null,
          reconcile: {
            precheck: options.precheck,
            parse: (intent) => {
              const payload = intent.payload as { live?: boolean; malformed?: boolean };
              if (payload.malformed) return { suspend: 'reconcile-failed' };
              return {
                input: { conversationId: intent.conversationId, live: payload.live ?? true },
              };
            },
            gate: options.gate,
            resume:
              options.resume ??
              (async (input) => {
                resumed.push(input);
                return ok();
              }),
          },
        },
      });
      return { harness, lifecycle, resumed };
    }

    it('aborts the whole run when precheck vetoes, without suspending intents', async () => {
      const intents = createMemorySessionIntentStore();
      await intents.saveActive({ conversationId: 's1', payload: {} });
      const { harness, lifecycle, resumed } = reconcileHarness({
        intents,
        precheck: async () => ({ veto: true, error: new Error('tmux unavailable') }),
      });

      await lifecycle.reconcile();
      await settle();

      expect(resumed).toEqual([]);
      expect(intents.snapshot()[0]).toMatchObject({ conversationId: 's1', status: 'active' });
      expect(harness.warns).toContainEqual(
        expect.objectContaining({ message: 'TestRuntime: reconcile precheck failed' })
      );
    });

    it('treats a throwing precheck as a veto', async () => {
      const intents = createMemorySessionIntentStore();
      await intents.saveActive({ conversationId: 's1', payload: {} });
      const { harness, lifecycle, resumed } = reconcileHarness({
        intents,
        precheck: async () => {
          throw new Error('listing exploded');
        },
      });

      await lifecycle.reconcile();
      await settle();

      expect(resumed).toEqual([]);
      expect(intents.snapshot()[0]).toMatchObject({ status: 'active' });
      expect(harness.warns).toContainEqual(
        expect.objectContaining({ message: 'TestRuntime: reconcile precheck failed' })
      );
    });

    it('suspends with the parse-provided cause and continues with other intents', async () => {
      const intents = createMemorySessionIntentStore();
      await intents.saveActive({ conversationId: 'bad', payload: { malformed: true } });
      await intents.saveActive({ conversationId: 'good', payload: {} });
      const { lifecycle, resumed } = reconcileHarness({ intents });

      await lifecycle.reconcile();
      await settle();

      const byId = new Map(intents.snapshot().map((intent) => [intent.conversationId, intent]));
      expect(byId.get('bad')).toMatchObject({
        status: 'suspended',
        suspendedCause: 'reconcile-failed',
      });
      expect(resumed).toEqual([{ conversationId: 'good', live: true }]);
    });

    it('suspends with the gate-provided cause without resuming', async () => {
      const intents = createMemorySessionIntentStore();
      await intents.saveActive({ conversationId: 'dead', payload: { live: false } });
      const { lifecycle, resumed } = reconcileHarness({
        intents,
        gate: (input) => (input.live ? { ok: true } : { suspend: 'process-lost' }),
      });

      await lifecycle.reconcile();
      await settle();

      expect(resumed).toEqual([]);
      expect(intents.snapshot()[0]).toMatchObject({
        status: 'suspended',
        suspendedCause: 'process-lost',
      });
    });

    it("warns and suspends 'reconcile-failed' when resume fails", async () => {
      const intents = createMemorySessionIntentStore();
      await intents.saveActive({ conversationId: 's1', payload: {} });
      const { harness, lifecycle } = reconcileHarness({
        intents,
        resume: async () => err({ type: 'spawn-failed' }),
      });

      await lifecycle.reconcile();
      await settle();

      expect(harness.warns).toContainEqual(
        expect.objectContaining({
          message: 'TestRuntime: failed to reconcile session intent',
          context: expect.objectContaining({ conversationId: 's1' }),
        })
      );
      expect(intents.snapshot()[0]).toMatchObject({
        status: 'suspended',
        suspendedCause: 'reconcile-failed',
      });
    });

    it('skips suspended intents entirely', async () => {
      const intents = createMemorySessionIntentStore();
      await intents.saveActive({ conversationId: 's1', payload: {} });
      await intents.markSuspended('s1', 'user');
      const { lifecycle, resumed } = reconcileHarness({ intents });

      await lifecycle.reconcile();

      expect(resumed).toEqual([]);
    });

    it('warns and returns when listing intents fails', async () => {
      const intents: SessionIntentStore = {
        async list() {
          return err({ type: 'io', message: 'kv unavailable' });
        },
        async saveActive() {
          return ok();
        },
        async markSuspended() {
          return ok();
        },
        async remove() {
          return ok();
        },
      };
      const { harness, lifecycle, resumed } = reconcileHarness({ intents });

      await lifecycle.reconcile();

      expect(resumed).toEqual([]);
      expect(harness.warns).toContainEqual(
        expect.objectContaining({ message: 'TestRuntime: failed to load session intents' })
      );
    });
  });

  describe('overload typing', () => {
    it('exposes conversation verbs only when the conversation block is present', () => {
      const harness = makeHarness();
      const subset = createSessionLifecycle({ ...baseOptions(harness) });

      // @ts-expect-error started is a compile error on a subset instance
      subset.started('s1');
      // @ts-expect-error providerSessionId is a compile error on a subset instance
      subset.providerSessionId('s1', { conversationId: 's1', providerSessionId: 'x' });
      // @ts-expect-error saveIntent is a compile error on a subset instance
      subset.saveIntent('s1');
      type SubsetHasReconcile = 'reconcile' extends keyof typeof subset ? true : false;
      const hasReconcile: SubsetHasReconcile = false;
      expect(hasReconcile).toBe(false);

      const conversationOptions: ConversationOptions<never, void> = {
        intents: createMemorySessionIntentStore(),
        activePayload: () => null,
      };
      const full = createSessionLifecycle({
        ...baseOptions(makeHarness()),
        conversation: conversationOptions,
      });
      full.saveIntent('s1');
      subset.dispose();
      full.dispose();
    });
  });
});

describe('leak-check helper', () => {
  it('passes when no container holds the key and names the leaking containers otherwise', () => {
    const logs = new Map<string, string>();
    const startCounts = new Map<string, number>();
    const list: Record<string, unknown> = {};

    expect(() =>
      expectNoSessionResidue('s1', [
        mapContainer('logs', logs),
        mapContainer('startCounts', startCounts),
        recordContainer('sessionsList', () => list),
      ])
    ).not.toThrow();

    logs.set('s1', 'scrollback');
    list['s1'] = { status: 'exited' };
    expect(() =>
      expectNoSessionResidue('s1', [
        mapContainer('logs', logs),
        mapContainer('startCounts', startCounts),
        recordContainer('sessionsList', () => list),
      ])
    ).toThrow(/logs, sessionsList/);
  });
});
