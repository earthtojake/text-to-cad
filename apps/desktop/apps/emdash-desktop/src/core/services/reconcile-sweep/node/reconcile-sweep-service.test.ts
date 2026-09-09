import { hostRef, LOCAL_HOST_REF, type HostRef } from '@emdash/core/primitives/host/api';
import { createScope, type Scope } from '@emdash/shared/concurrency';
import { ManualClock } from '@emdash/shared/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ReconcileSweepService,
  type ReconcileSweepKind,
  type ReconcileTombstone,
  type RemovalAttemptOutcome,
} from './reconcile-sweep-service';

const REMOTE_HOST = hostRef('remote', 'ssh-1');

/**
 * The sweep seam (ADR 0006, spec §2): the entity-generic primitive driven against a
 * fake kind — an in-memory tombstone store plus a scripted removal function. The
 * tests pin the lifecycle the spec decided: per-tombstone single-flight, per-item
 * exponential backoff riding the backstop, purge gated on the store confirming the
 * record gone (never on the RPC return), the durable epoch-based terminal-failure
 * stop with its Retry and Untrack-anyway affordances, and rows vanishing mid-sweep
 * staying benign. No wall clock decides stop/retry.
 */
describe('ReconcileSweepService', () => {
  let scope: Scope;
  let clock: ManualClock;

  beforeEach(() => {
    scope = createScope({ label: 'reconcile-sweep-test' });
    clock = new ManualClock(1_000_000);
  });

  afterEach(async () => {
    await scope.dispose();
  });

  function createService(options: { onError?: (context: string, error: unknown) => void } = {}) {
    return new ReconcileSweepService({
      scope,
      clock,
      onError: options.onError ?? (() => {}),
    });
  }

  function failure(kind: 'transient' | 'terminal'): RemovalAttemptOutcome {
    return { failed: { class: kind, stage: 'remove', message: `${kind} failure` } };
  }

  type FakeItem = ReconcileTombstone & { gone?: boolean };

  /** In-memory stand-in for the mirror: live tombstoned rows plus a gone flag. */
  function createFakeKind(
    options: {
      kind?: string;
      outcome?: RemovalAttemptOutcome | (() => RemovalAttemptOutcome);
      onRemoval?: (host: HostRef, id: string) => void | Promise<void>;
    } = {}
  ) {
    const items = new Map<string, FakeItem>();
    const executeRemoval = vi.fn(async (host: HostRef, id: string) => {
      await options.onRemoval?.(host, id);
      return typeof options.outcome === 'function' ? options.outcome() : (options.outcome ?? 'ok');
    });
    const recordTerminalStop = vi.fn(
      async (_host: HostRef, id: string, stop: { epoch: number }) => {
        const item = items.get(id);
        if (!item) return;
        // The epoch guard mirrored from the durable registry write: a Retry that
        // already advanced the epoch discards the stale stop.
        if (stop.epoch !== item.attemptEpoch) return;
        item.terminalStopEpoch = stop.epoch;
      }
    );
    const kind: ReconcileSweepKind = {
      kind: options.kind ?? 'widgets',
      readTombstones: async () =>
        [...items.values()]
          .filter((item) => item.gone !== true)
          .map(({ gone: _gone, ...item }) => item),
      executeRemoval,
      confirmGone: async (_host, id) => items.get(id)?.gone !== false,
      recordTerminalStop,
    };
    return {
      kind,
      executeRemoval,
      recordTerminalStop,
      seed(id: string, overrides: Partial<FakeItem> = {}) {
        items.set(id, {
          id,
          attemptEpoch: 0,
          terminalStopEpoch: null,
          gone: false,
          ...overrides,
        });
      },
      markGone(id: string) {
        const item = items.get(id);
        if (item) item.gone = true;
      },
      /** The durable half of Retry: the owning operation bumps the attempt epoch. */
      bumpEpoch(id: string) {
        const item = items.get(id);
        if (item) item.attemptEpoch += 1;
      },
      get(id: string) {
        return items.get(id);
      },
      forgetAll() {
        items.clear();
      },
    };
  }

  it('sweeps a host and calls the removal function once per tombstone', async () => {
    const fake = createFakeKind();
    fake.seed('a');
    fake.seed('b');
    const service = createService();
    service.registerKind(fake.kind);

    await service.sweepHost(LOCAL_HOST_REF);

    expect(fake.executeRemoval).toHaveBeenCalledTimes(2);
    expect(fake.executeRemoval).toHaveBeenCalledWith(LOCAL_HOST_REF, 'a');
    expect(fake.executeRemoval).toHaveBeenCalledWith(LOCAL_HOST_REF, 'b');
  });

  it('attachHost marks the host reachable and triggers an immediate sweep', async () => {
    const fake = createFakeKind();
    fake.seed('a');
    const service = createService();
    service.registerKind(fake.kind);

    service.attachHost(REMOTE_HOST);
    await vi.waitFor(() => expect(fake.executeRemoval).toHaveBeenCalledTimes(1));
    expect(fake.executeRemoval).toHaveBeenCalledWith(REMOTE_HOST, 'a');
  });

  it('single-flight: two overlapping triggers issue one RPC per tombstone', async () => {
    let release: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const fake = createFakeKind({ onRemoval: () => gate });
    fake.seed('a');
    const service = createService();
    service.registerKind(fake.kind);

    const first = service.sweepHost(LOCAL_HOST_REF);
    const second = service.sweepHost(LOCAL_HOST_REF);
    release?.();
    await Promise.all([first, second]);

    expect(fake.executeRemoval).toHaveBeenCalledTimes(1);
  });

  it('failed attempts back off exponentially, capped at one hour', async () => {
    const fake = createFakeKind({ outcome: failure('transient') });
    fake.seed('a');
    const service = createService();
    service.registerKind(fake.kind);

    await service.sweepHost(LOCAL_HOST_REF);
    expect(fake.executeRemoval).toHaveBeenCalledTimes(1);

    // Inside the first backoff window (1 minute): skipped.
    await clock.advanceBy(30_000);
    await service.sweepHost(LOCAL_HOST_REF);
    expect(fake.executeRemoval).toHaveBeenCalledTimes(1);

    // Past the window: retried, doubling the next window to 2 minutes.
    await clock.advanceBy(31_000);
    await service.sweepHost(LOCAL_HOST_REF);
    expect(fake.executeRemoval).toHaveBeenCalledTimes(2);

    await clock.advanceBy(60_000);
    await service.sweepHost(LOCAL_HOST_REF);
    expect(fake.executeRemoval).toHaveBeenCalledTimes(2);
    await clock.advanceBy(61_000);
    await service.sweepHost(LOCAL_HOST_REF);
    expect(fake.executeRemoval).toHaveBeenCalledTimes(3);

    // After many failures the window never exceeds the one-hour cap.
    for (let i = 0; i < 10; i += 1) {
      await clock.advanceBy(60 * 60_000 + 1_000);
      await service.sweepHost(LOCAL_HOST_REF);
    }
    const calls = fake.executeRemoval.mock.calls.length;
    await clock.advanceBy(60 * 60_000 + 1_000);
    await service.sweepHost(LOCAL_HOST_REF);
    expect(fake.executeRemoval.mock.calls.length).toBe(calls + 1);
  });

  it('an unreachable host is not an attempt: no backoff is scheduled', async () => {
    const fake = createFakeKind({ outcome: 'unreachable' });
    fake.seed('a');
    const service = createService();
    service.registerKind(fake.kind);

    await service.sweepHost(LOCAL_HOST_REF);
    await service.sweepHost(LOCAL_HOST_REF);

    expect(fake.executeRemoval).toHaveBeenCalledTimes(2);
  });

  it('a successful RPC purges nothing: the item re-sweeps until the store confirms gone', async () => {
    const fake = createFakeKind({ outcome: 'ok' });
    fake.seed('a');
    const service = createService();
    service.registerKind(fake.kind);

    await service.sweepHost(LOCAL_HOST_REF);
    expect(fake.executeRemoval).toHaveBeenCalledTimes(1);

    // Still tombstoned in the store — the RPC return asserted nothing; re-issue.
    await service.sweepHost(LOCAL_HOST_REF);
    expect(fake.executeRemoval).toHaveBeenCalledTimes(2);

    // The store confirms the record gone (sync-delivered): no further RPCs.
    fake.markGone('a');
    await service.sweepHost(LOCAL_HOST_REF);
    expect(fake.executeRemoval).toHaveBeenCalledTimes(2);
  });

  it('skips the RPC when the record is confirmed gone between read and execute', async () => {
    const fake = createFakeKind();
    fake.seed('a');
    const service = createService();
    service.registerKind(fake.kind);
    // Simulate sync landing between readTombstones and the removal call.
    const original = fake.kind.confirmGone;
    fake.kind.confirmGone = async (host, id) => {
      fake.markGone('a');
      return original(host, id);
    };

    await service.sweepHost(LOCAL_HOST_REF);

    expect(fake.executeRemoval).not.toHaveBeenCalled();
  });

  it('a durable terminal stop in the current epoch halts auto-retry for that item only', async () => {
    const fake = createFakeKind();
    fake.seed('stuck', { terminalStopEpoch: 0 });
    fake.seed('fine');
    const service = createService();
    service.registerKind(fake.kind);

    await service.sweepHost(LOCAL_HOST_REF);

    expect(fake.executeRemoval).toHaveBeenCalledTimes(1);
    expect(fake.executeRemoval).toHaveBeenCalledWith(LOCAL_HOST_REF, 'fine');
  });

  it('a terminal failure records the durable stop, tagged with the attempt epoch', async () => {
    const fake = createFakeKind({ outcome: failure('terminal') });
    fake.seed('a');
    const service = createService();
    service.registerKind(fake.kind);

    await service.sweepHost(LOCAL_HOST_REF);

    expect(fake.executeRemoval).toHaveBeenCalledTimes(1);
    expect(fake.recordTerminalStop).toHaveBeenCalledWith(LOCAL_HOST_REF, 'a', {
      epoch: 0,
      stage: 'remove',
      message: 'terminal failure',
      at: clock.now(),
    });
    // Stopped durably: later sweeps (past any backoff) never re-issue.
    await clock.advanceBy(60 * 60_000);
    await service.sweepHost(LOCAL_HOST_REF);
    expect(fake.executeRemoval).toHaveBeenCalledTimes(1);
  });

  it('a transient failure never records a stop and keeps riding the backstop', async () => {
    const fake = createFakeKind({ outcome: failure('transient') });
    fake.seed('a');
    const service = createService();
    service.registerKind(fake.kind);

    await service.sweepHost(LOCAL_HOST_REF);
    await clock.advanceBy(61_000);
    await service.sweepHost(LOCAL_HOST_REF);

    expect(fake.executeRemoval).toHaveBeenCalledTimes(2);
    expect(fake.recordTerminalStop).not.toHaveBeenCalled();
  });

  it('a stop from an older epoch never halts the sweep: retry is durable across restarts', async () => {
    // Retry bumped the epoch durably; then the app restarted (fresh in-memory state).
    const fake = createFakeKind();
    fake.seed('a', { attemptEpoch: 1, terminalStopEpoch: 0 });
    const service = createService();
    service.registerKind(fake.kind);

    await service.sweepHost(LOCAL_HOST_REF);

    expect(fake.executeRemoval).toHaveBeenCalledTimes(1);
  });

  it('retry (durable epoch bump + backoff reset) runs exactly one fresh attempt', async () => {
    const fake = createFakeKind({ outcome: failure('transient') });
    fake.seed('a', { terminalStopEpoch: 0 });
    const service = createService();
    service.registerKind(fake.kind);

    await service.sweepHost(LOCAL_HOST_REF);
    expect(fake.executeRemoval).not.toHaveBeenCalled();

    // The owning operation bumps the epoch durably, then pokes the service.
    fake.bumpEpoch('a');
    service.retry('widgets', LOCAL_HOST_REF, 'a');
    await vi.waitFor(() => expect(fake.executeRemoval).toHaveBeenCalledTimes(1));

    // The fresh attempt failed transiently: the next sweep sits inside the backoff.
    await service.sweepHost(LOCAL_HOST_REF);
    expect(fake.executeRemoval).toHaveBeenCalledTimes(1);
  });

  it('a new terminal failure after a retry stops the item again, at the new epoch', async () => {
    const fake = createFakeKind({ outcome: failure('terminal') });
    fake.seed('a', { terminalStopEpoch: 0 });
    const service = createService();
    service.registerKind(fake.kind);

    fake.bumpEpoch('a');
    service.retry('widgets', LOCAL_HOST_REF, 'a');
    await vi.waitFor(() => expect(fake.executeRemoval).toHaveBeenCalledTimes(1));
    expect(fake.recordTerminalStop).toHaveBeenCalledWith(
      LOCAL_HOST_REF,
      'a',
      expect.objectContaining({ epoch: 1 })
    );

    await clock.advanceBy(60 * 60_000);
    await service.sweepHost(LOCAL_HOST_REF);
    expect(fake.executeRemoval).toHaveBeenCalledTimes(1);
  });

  it('a retry landing mid-attempt invalidates the stale stop: the item stays live', async () => {
    let release: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const fake = createFakeKind({ outcome: failure('terminal'), onRemoval: () => gate });
    fake.seed('a');
    const service = createService();
    service.registerKind(fake.kind);

    const sweep = service.sweepHost(LOCAL_HOST_REF);
    // Retry lands while the attempt is in flight: the durable epoch moves ahead.
    fake.bumpEpoch('a');
    release?.();
    await sweep;

    // The stop was tagged with the stale epoch 0 and discarded by the epoch guard.
    expect(fake.get('a')?.terminalStopEpoch).toBeNull();
    await clock.advanceBy(60 * 60_000);
    await service.sweepHost(LOCAL_HOST_REF);
    expect(fake.executeRemoval).toHaveBeenCalledTimes(2);
  });

  it('drop forgets the in-memory state for an untracked-anyway item', async () => {
    const fake = createFakeKind({ outcome: failure('transient') });
    fake.seed('a');
    const service = createService();
    service.registerKind(fake.kind);
    await service.sweepHost(LOCAL_HOST_REF);

    // Untrack-anyway purges the row client-side; the store stops serving it.
    fake.markGone('a');
    service.drop('widgets', 'a');
    await service.sweepHost(LOCAL_HOST_REF);

    expect(fake.executeRemoval).toHaveBeenCalledTimes(1);
  });

  it('forget-host mid-sweep is benign: rows vanish under an in-flight removal', async () => {
    let release: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const fake = createFakeKind({ onRemoval: () => gate, outcome: failure('transient') });
    fake.seed('a');
    fake.seed('b');
    const onError = vi.fn();
    const service = createService({ onError });
    service.registerKind(fake.kind);

    const sweep = service.sweepHost(LOCAL_HOST_REF);
    fake.forgetAll();
    release?.();
    await sweep;

    expect(onError).not.toHaveBeenCalled();
    // The vanished items never resurrect: nothing left to sweep.
    fake.executeRemoval.mockClear();
    await service.sweepHost(LOCAL_HOST_REF);
    expect(fake.executeRemoval).not.toHaveBeenCalled();
  });

  it('a kind that throws reports the error and never breaks the sweep', async () => {
    const broken: ReconcileSweepKind = {
      kind: 'broken',
      readTombstones: async () => {
        throw new Error('store exploded');
      },
      executeRemoval: async () => 'ok',
      confirmGone: async () => false,
      recordTerminalStop: async () => {},
    };
    const fake = createFakeKind();
    fake.seed('a');
    const onError = vi.fn();
    const service = createService({ onError });
    service.registerKind(broken);
    service.registerKind(fake.kind);

    await service.sweepHost(LOCAL_HOST_REF);

    expect(onError).toHaveBeenCalled();
    expect(fake.executeRemoval).toHaveBeenCalledTimes(1);
  });

  it('kinds sweep in registration order — the fixed-order churn heuristic', async () => {
    const order: string[] = [];
    const first = createFakeKind({
      kind: 'worktrees',
      onRemoval: () => void order.push('worktrees'),
    });
    const second = createFakeKind({
      kind: 'conversations',
      onRemoval: () => void order.push('conversations'),
    });
    first.seed('a');
    second.seed('b');
    const service = createService();
    service.registerKind(first.kind);
    service.registerKind(second.kind);

    await service.sweepHost(LOCAL_HOST_REF);

    expect(order).toEqual(['worktrees', 'conversations']);
  });

  it('the backstop sweeps attached hosts only', async () => {
    const fake = createFakeKind();
    fake.seed('a');
    const service = createService();
    service.registerKind(fake.kind);

    await service.sweepAll();
    expect(fake.executeRemoval).not.toHaveBeenCalled();

    service.attachHost(LOCAL_HOST_REF);
    await vi.waitFor(() => expect(fake.executeRemoval).toHaveBeenCalledTimes(1));
    service.detachHost(LOCAL_HOST_REF);
    await service.sweepAll();
    expect(fake.executeRemoval).toHaveBeenCalledTimes(1);
  });
});
