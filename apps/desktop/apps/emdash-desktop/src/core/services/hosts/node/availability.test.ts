import { LOCAL_HOST_REF, hostRef } from '@emdash/core/primitives/host/api';
import { runtimeHostUnavailable } from '@emdash/core/primitives/runtime-resolution/api';
import { err, ok } from '@emdash/shared';
import { createScope } from '@emdash/shared/concurrency';
import { retrySchedules } from '@emdash/shared/scheduling';
import { createManualClock, deferred } from '@emdash/shared/testing';
import { describe, expect, it, vi } from 'vitest';
import { createHostAvailability, type HostReadinessAdapter } from './availability';

describe('HostAvailability', () => {
  it('runs one keyed recovery for every automatic Project demand on a Host', async () => {
    const scope = createScope({ label: 'host-availability-test' });
    const firstProject = createScope({ label: 'first-project' });
    const secondProject = createScope({ label: 'second-project' });
    const host = hostRef('remote', 'ssh-1');
    const completion = deferred<ReturnType<typeof ok<void>>>();
    const prepare = vi.fn(() => completion.promise);
    const availability = createHostAvailability({
      scope,
      readiness: { prepare },
    });

    availability.demand(host, 'automatic', firstProject);
    availability.demand(host, 'automatic', secondProject);

    await vi.waitFor(() => expect(prepare).toHaveBeenCalledOnce());
    completion.resolve(ok());
    await vi.waitFor(() => expect(availability.stateFor(host).kind).toBe('ready'));

    expect(prepare).toHaveBeenCalledOnce();
    await firstProject.dispose();
    await secondProject.dispose();
    await scope.dispose();
  });

  it('keeps passive demand dormant across browser wakeups until it becomes automatic', async () => {
    const scope = createScope({ label: 'host-availability-test' });
    const project = createScope({ label: 'project' });
    const host = hostRef('remote', 'ssh-1');
    const prepare = vi.fn(async () => ok<void>());
    const availability = createHostAvailability({
      scope,
      readiness: { prepare },
    });

    const demand = availability.demand(host, 'passive', project);
    availability.wakeDemanded('online');

    await Promise.resolve();
    expect(prepare).not.toHaveBeenCalled();

    demand.setMode('automatic');
    await vi.waitFor(() => expect(prepare).toHaveBeenCalledOnce());
    expect(demand.mode).toBe('automatic');

    await project.dispose();
    await scope.dispose();
  });

  it('cancels automatic preparation when its final Scope-owned demand releases', async () => {
    const scope = createScope({ label: 'host-availability-test' });
    const project = createScope({ label: 'project' });
    const host = hostRef('remote', 'ssh-1');
    const started = deferred<AbortSignal>();
    const completion = deferred<ReturnType<typeof ok<void>>>();
    const availability = createHostAvailability({
      scope,
      readiness: {
        prepare: async (_host, context) => {
          started.resolve(context.signal);
          return await completion.promise;
        },
      },
    });

    availability.demand(host, 'automatic', project);
    const signal = await started.promise;
    await project.dispose();

    expect(signal.aborted).toBe(true);
    expect(availability.stateFor(host)).toEqual({
      kind: 'unavailable',
      recovery: 'eligible',
    });

    completion.resolve(ok());
    await Promise.resolve();
    expect(availability.stateFor(host)).toEqual({
      kind: 'unavailable',
      recovery: 'eligible',
    });
    await scope.dispose();
  });

  it('starts fresh automatic recovery when a demanded ready Host is invalidated', async () => {
    const scope = createScope({ label: 'host-availability-test' });
    const project = createScope({ label: 'project' });
    const host = hostRef('remote', 'ssh-1');
    const prepare = vi.fn(async () => ok<void>());
    const availability = createHostAvailability({
      scope,
      readiness: { prepare },
    });
    availability.demand(host, 'automatic', project);
    await vi.waitFor(() => expect(availability.stateFor(host).kind).toBe('ready'));

    availability.invalidate(host);

    await vi.waitFor(() => expect(prepare).toHaveBeenCalledTimes(2));
    await vi.waitFor(() =>
      expect(availability.stateFor(host)).toEqual({ kind: 'ready', generation: 2 })
    );

    await project.dispose();
    await scope.dispose();
  });

  it('starts automatic recovery for a demanded transient typed invalidation', async () => {
    const scope = createScope({ label: 'host-availability-test' });
    const project = createScope({ label: 'project' });
    const host = hostRef('remote', 'ssh-1');
    const recovery = deferred<ReturnType<typeof ok<void>>>();
    const prepare = vi
      .fn<HostReadinessAdapter['prepare']>()
      .mockResolvedValueOnce(ok())
      .mockImplementationOnce(() => recovery.promise);
    const availability = createHostAvailability({
      scope,
      readiness: { prepare },
    });
    availability.demand(host, 'automatic', project);
    await vi.waitFor(() => expect(availability.stateFor(host).kind).toBe('ready'));
    const failure = runtimeHostUnavailable(
      host,
      'runtime-unavailable',
      'Host runtime is unavailable'
    );

    availability.invalidate(host, failure);

    await vi.waitFor(() => expect(prepare).toHaveBeenCalledTimes(2));
    expect(availability.stateFor(host)).toMatchObject({
      kind: 'preparing',
      attempt: 1,
    });
    recovery.resolve(ok());
    await vi.waitFor(() =>
      expect(availability.stateFor(host)).toEqual({ kind: 'ready', generation: 2 })
    );

    await project.dispose();
    await scope.dispose();
  });

  it('keeps repeated invalidations within the active bounded recovery run', async () => {
    const scope = createScope({ label: 'host-availability-test' });
    const project = createScope({ label: 'project' });
    const clock = createManualClock();
    const host = hostRef('remote', 'ssh-1');
    const failure = runtimeHostUnavailable(host, 'connection-failed', 'Host is offline');
    const prepare = vi.fn<HostReadinessAdapter['prepare']>(async () => err(failure));
    const availability = createHostAvailability({
      scope,
      clock,
      readiness: { prepare },
    });

    availability.demand(host, 'automatic', project);
    await vi.waitFor(() => expect(prepare).toHaveBeenCalledOnce());
    await vi.waitFor(() =>
      expect(availability.stateFor(host)).toEqual({
        kind: 'unavailable',
        issue: failure,
        recovery: 'waiting',
        nextAttemptAt: 1_000,
      })
    );

    availability.invalidate(host);
    availability.invalidate(host, failure);

    expect(prepare).toHaveBeenCalledOnce();
    expect(availability.stateFor(host)).toEqual({
      kind: 'unavailable',
      issue: failure,
      recovery: 'waiting',
      nextAttemptAt: 1_000,
    });

    await clock.advanceBy(1_000);
    await vi.waitFor(() => expect(prepare).toHaveBeenCalledTimes(2));

    await project.dispose();
    await scope.dispose();
  });

  it('throttles browser focus wakeups once per demanded Host for 30 seconds', async () => {
    const scope = createScope({ label: 'host-availability-test' });
    const project = createScope({ label: 'project' });
    const clock = createManualClock();
    const host = hostRef('remote', 'ssh-1');
    const availability = createHostAvailability({
      scope,
      clock,
      readiness: { prepare: async () => ok() },
    });
    availability.demand(host, 'automatic', project);
    await vi.waitFor(() => expect(availability.stateFor(host).kind).toBe('ready'));
    const ensureReady = vi.spyOn(availability, 'ensureReady');
    ensureReady.mockClear();

    availability.wakeDemanded('focus');
    availability.wakeDemanded('focus');
    await clock.advanceBy(29_999);
    availability.wakeDemanded('focus');

    expect(ensureReady).toHaveBeenCalledTimes(1);
    expect(ensureReady).toHaveBeenLastCalledWith(host, 'focus');

    await clock.advanceBy(1);
    availability.wakeDemanded('focus');
    expect(ensureReady).toHaveBeenCalledTimes(2);

    await project.dispose();
    await scope.dispose();
  });

  it('suppresses SSH, online, and focus wakeups while explicitly suspended', async () => {
    const scope = createScope({ label: 'host-availability-test' });
    const project = createScope({ label: 'project' });
    const host = hostRef('remote', 'ssh-1');
    const availability = createHostAvailability({
      scope,
      readiness: { prepare: async () => ok() },
    });
    availability.suspend(host);
    availability.demand(host, 'automatic', project);
    const ensureReady = vi.spyOn(availability, 'ensureReady');
    ensureReady.mockClear();

    availability.wake(host, 'ssh-edge');
    availability.wakeDemanded('online');
    availability.wakeDemanded('focus');

    expect(ensureReady).not.toHaveBeenCalled();
    expect(availability.stateFor(host)).toEqual({
      kind: 'suspended',
      reason: 'user-disconnected',
    });
    await project.dispose();
    await scope.dispose();
  });

  it('lets an SSH edge restart exhausted cold-boot recovery with passive demand', async () => {
    const scope = createScope({ label: 'host-availability-test' });
    const project = createScope({ label: 'project' });
    const host = hostRef('remote', 'ssh-1');
    const failure = runtimeHostUnavailable(host, 'connection-failed', 'Host is offline');
    const prepare = vi.fn().mockResolvedValueOnce(err(failure)).mockResolvedValueOnce(ok());
    const availability = createHostAvailability({
      scope,
      retrySchedule: retrySchedules.sequence([]),
      readiness: { prepare },
    });
    const demand = availability.demand(host, 'automatic', project);
    await vi.waitFor(() =>
      expect(availability.stateFor(host)).toEqual({
        kind: 'unavailable',
        issue: failure,
        recovery: 'manual',
      })
    );
    demand.setMode('passive');

    availability.wake(host, 'ssh-edge');
    await vi.waitFor(() => expect(prepare).toHaveBeenCalledTimes(2));
    await vi.waitFor(() =>
      expect(availability.stateFor(host)).toEqual({ kind: 'ready', generation: 1 })
    );

    await project.dispose();
    await scope.dispose();
  });

  it('keeps online and focus dormant for passive demand after automatic exhaustion', async () => {
    const scope = createScope({ label: 'host-availability-test' });
    const project = createScope({ label: 'project' });
    const host = hostRef('remote', 'ssh-1');
    const failure = runtimeHostUnavailable(host, 'connection-failed', 'Host is offline');
    const prepare = vi.fn().mockResolvedValueOnce(err(failure)).mockResolvedValueOnce(ok());
    const availability = createHostAvailability({
      scope,
      retrySchedule: retrySchedules.sequence([]),
      readiness: { prepare },
    });
    const demand = availability.demand(host, 'automatic', project);
    await vi.waitFor(() =>
      expect(availability.stateFor(host)).toEqual({
        kind: 'unavailable',
        issue: failure,
        recovery: 'manual',
      })
    );
    demand.setMode('passive');

    availability.wakeDemanded('online');
    availability.wakeDemanded('focus');
    await Promise.resolve();

    expect(prepare).toHaveBeenCalledOnce();
    expect(availability.stateFor(host)).toEqual({
      kind: 'unavailable',
      issue: failure,
      recovery: 'manual',
    });

    await project.dispose();
    await scope.dispose();
  });

  it('attempts automatic recovery immediately, then after the exact bounded schedule', async () => {
    const scope = createScope({ label: 'host-availability-test' });
    const project = createScope({ label: 'project' });
    const clock = createManualClock(100);
    const host = hostRef('remote', 'ssh-1');
    const failure = runtimeHostUnavailable(host, 'connection-failed', 'Host is offline');
    const prepare = vi.fn<HostReadinessAdapter['prepare']>(async () => err(failure));
    const availability = createHostAvailability({
      scope,
      clock,
      retrySchedule: retrySchedules.sequence([1_000, 2_000, 5_000, 10_000, 30_000]),
      readiness: { prepare },
    });
    availability.demand(host, 'passive', project);

    const recovery = availability.ensureReady(host, 'demand');
    await vi.waitFor(() => expect(prepare).toHaveBeenCalledTimes(1));
    expect(availability.stateFor(host)).toEqual({
      kind: 'unavailable',
      issue: failure,
      recovery: 'waiting',
      nextAttemptAt: 1_100,
    });

    for (const [delayMs, attempt] of [
      [1_000, 2],
      [2_000, 3],
      [5_000, 4],
      [10_000, 5],
      [30_000, 6],
    ] as const) {
      await clock.advanceBy(delayMs);
      await vi.waitFor(() => expect(prepare).toHaveBeenCalledTimes(attempt));
    }

    await expect(recovery).resolves.toEqual(err(failure));
    expect(availability.stateFor(host)).toEqual({
      kind: 'unavailable',
      issue: failure,
      recovery: 'manual',
    });
    expect(prepare).toHaveBeenCalledTimes(6);

    availability.wakeDemanded('online');
    availability.wakeDemanded('focus');
    await Promise.resolve();
    expect(prepare).toHaveBeenCalledTimes(6);

    prepare.mockResolvedValueOnce(ok<void>());
    await expect(availability.ensureReady(host, 'retry')).resolves.toMatchObject({
      success: true,
      data: { generation: 1 },
    });
    expect(prepare).toHaveBeenCalledTimes(7);

    await project.dispose();
    await scope.dispose();
  });

  it('does not report an SSH Host ready before its runtime handshake completes', async () => {
    const scope = createScope({ label: 'host-availability-test' });
    const handshake = deferred<void>();
    const preparing = deferred<void>();
    const availability = createHostAvailability({
      scope,
      readiness: {
        async prepare(_host, context) {
          context.setPhase('provisioning');
          preparing.resolve();
          await handshake.promise;
          context.setPhase('handshaking');
          return ok();
        },
      },
    });
    const host = hostRef('remote', 'ssh-1');

    const pending = availability.ensureReady(host, 'demand');
    await preparing.promise;

    expect(availability.stateFor(host)).toEqual({
      kind: 'preparing',
      phase: 'provisioning',
      attempt: 1,
    });
    expect(availability.requireReady(host)).toMatchObject({
      success: false,
      error: { type: 'host-unavailable', reason: 'runtime-unavailable' },
    });

    handshake.resolve();

    await expect(pending).resolves.toEqual({
      success: true,
      data: { host, generation: 1 },
    });
    expect(availability.stateFor(host)).toEqual({ kind: 'ready', generation: 1 });

    await scope.dispose();
  });

  it('rejects a stale success after suspension and a newer readiness cycle', async () => {
    const scope = createScope({ label: 'host-availability-test' });
    const first = deferred<ReturnType<typeof ok<void>>>();
    const second = deferred<ReturnType<typeof ok<void>>>();
    const prepare = vi
      .fn()
      .mockImplementationOnce(() => first.promise)
      .mockImplementationOnce(() => second.promise);
    const availability = createHostAvailability({
      scope,
      readiness: { prepare },
    });
    const host = hostRef('remote', 'ssh-1');

    const stale = availability.ensureReady(host, 'demand');
    await vi.waitFor(() => expect(prepare).toHaveBeenCalledTimes(1));
    availability.suspend(host);
    const current = availability.ensureReady(host, 'retry');
    await vi.waitFor(() => expect(prepare).toHaveBeenCalledTimes(2));
    second.resolve(ok());
    await expect(current).resolves.toEqual({
      success: true,
      data: { host, generation: 1 },
    });

    first.resolve(ok());

    await expect(stale).resolves.toMatchObject({
      success: false,
      error: { type: 'host-unavailable', reason: 'offline' },
    });
    expect(availability.stateFor(host)).toEqual({ kind: 'ready', generation: 1 });

    await scope.dispose();
  });

  it('coalesces concurrent readiness requests into one Host attempt', async () => {
    const scope = createScope({ label: 'host-availability-test' });
    const completion = deferred<ReturnType<typeof ok<void>>>();
    const prepare = vi.fn(() => completion.promise);
    const availability = createHostAvailability({
      scope,
      readiness: { prepare },
    });
    const host = hostRef('remote', 'ssh-1');

    const first = availability.ensureReady(host, 'demand');
    const second = availability.ensureReady(host, 'demand');

    expect(second).toBe(first);
    await vi.waitFor(() => expect(prepare).toHaveBeenCalledTimes(1));
    completion.resolve(ok());
    await expect(first).resolves.toMatchObject({ success: true });

    await scope.dispose();
  });

  it('keeps requireReady read-only and preserves a recorded semantic failure', async () => {
    const scope = createScope({ label: 'host-availability-test' });
    const host = hostRef('remote', 'ssh-1');
    const failure = runtimeHostUnavailable(
      host,
      'install-failed',
      'Host runtime installation failed'
    );
    const prepare = vi.fn(async () => err(failure));
    const availability = createHostAvailability({
      scope,
      readiness: { prepare },
    });

    expect(availability.requireReady(host)).toEqual(
      err(runtimeHostUnavailable(host, 'offline', 'Host is offline'))
    );
    expect(prepare).not.toHaveBeenCalled();

    await expect(availability.ensureReady(host, 'demand')).resolves.toEqual(err(failure));
    expect(availability.requireReady(host)).toEqual(err(failure));
    expect(prepare).toHaveBeenCalledOnce();

    await scope.dispose();
  });

  it('cancels in-flight preparation when the Host is suspended', async () => {
    const scope = createScope({ label: 'host-availability-test' });
    const started = deferred<void>();
    const prepare = vi.fn(
      async (
        _host: unknown,
        { signal }: { signal: AbortSignal }
      ): Promise<ReturnType<typeof ok<void>>> => {
        started.resolve();
        return await new Promise<ReturnType<typeof ok<void>>>((_resolve, reject) => {
          signal.addEventListener('abort', () => reject(signal.reason), { once: true });
        });
      }
    );
    const availability = createHostAvailability({
      scope,
      readiness: { prepare },
    });
    const host = hostRef('remote', 'ssh-1');

    const pending = availability.ensureReady(host, 'demand');
    await started.promise;
    availability.suspend(host);

    await expect(pending).resolves.toMatchObject({
      success: false,
      error: { type: 'host-unavailable', reason: 'offline' },
    });
    expect(availability.stateFor(host)).toEqual({
      kind: 'suspended',
      reason: 'user-disconnected',
    });

    await scope.dispose();
  });

  it('keeps suspension through transport changes until explicit Connect requests readiness', async () => {
    const scope = createScope({ label: 'host-availability-test' });
    const host = hostRef('remote', 'ssh-1');
    const explicit = deferred<ReturnType<typeof ok<void>>>();
    const causes: string[] = [];
    const availability = createHostAvailability({
      scope,
      readiness: {
        prepare: async (_host, context) => {
          causes.push(context.cause);
          return await explicit.promise;
        },
      },
    });

    availability.suspend(host);
    availability.invalidate(host);
    await expect(availability.ensureReady(host, 'ssh-edge')).resolves.toMatchObject({
      success: false,
      error: { type: 'host-unavailable', reason: 'offline' },
    });

    expect(availability.stateFor(host)).toEqual({
      kind: 'suspended',
      reason: 'user-disconnected',
    });
    expect(causes).toEqual([]);

    availability.requestReady(host, 'connect');
    await vi.waitFor(() => expect(causes).toEqual(['connect']));
    expect(availability.stateFor(host)).toMatchObject({
      kind: 'preparing',
      phase: 'connecting',
    });

    explicit.resolve(ok());
    await vi.waitFor(() => expect(availability.stateFor(host).kind).toBe('ready'));
    await scope.dispose();
  });

  it('supports local runtime readiness and advances the generation after a fresh cycle', async () => {
    const scope = createScope({ label: 'host-availability-test' });
    const handshake = deferred<void>();
    const availability = createHostAvailability({
      scope,
      readiness: {
        async prepare() {
          await handshake.promise;
          return ok();
        },
      },
    });

    const first = availability.ensureReady(LOCAL_HOST_REF, 'demand');
    expect(availability.stateFor(LOCAL_HOST_REF)).toEqual({
      kind: 'preparing',
      phase: 'handshaking',
      attempt: 1,
    });
    handshake.resolve();
    await expect(first).resolves.toMatchObject({ success: true, data: { generation: 1 } });

    availability.suspend(LOCAL_HOST_REF);
    await expect(availability.ensureReady(LOCAL_HOST_REF, 'retry')).resolves.toMatchObject({
      success: true,
      data: { generation: 2 },
    });

    await scope.dispose();
  });

  it('lets one explicit request supersede automatic preparation and then single-flights clicks', async () => {
    const scope = createScope({ label: 'host-availability-test' });
    const automatic = deferred<ReturnType<typeof ok<void>>>();
    const explicit = deferred<ReturnType<typeof ok<void>>>();
    const prepare = vi
      .fn()
      .mockImplementationOnce(() => automatic.promise)
      .mockImplementationOnce(() => explicit.promise);
    const availability = createHostAvailability({
      scope,
      readiness: { prepare },
    });
    const host = hostRef('remote', 'ssh-1');

    const superseded = availability.ensureReady(host, 'demand');
    await vi.waitFor(() => expect(prepare).toHaveBeenCalledTimes(1));
    const current = availability.ensureReady(host, 'retry');
    const repeated = availability.ensureReady(host, 'retry');

    expect(current).not.toBe(superseded);
    expect(repeated).toBe(current);
    await vi.waitFor(() => expect(prepare).toHaveBeenCalledTimes(2));
    explicit.resolve(ok());
    await expect(current).resolves.toMatchObject({ success: true });
    automatic.resolve(ok());
    await expect(superseded).resolves.toMatchObject({
      success: false,
      error: { type: 'host-unavailable', reason: 'runtime-unavailable' },
    });

    await scope.dispose();
  });

  it.each([
    ['connection-failed', 'waiting'],
    ['install-failed', 'manual'],
    ['unsupported-platform', 'blocked'],
  ] as const)('classifies %s readiness failures as %s recovery', async (reason, recovery) => {
    const scope = createScope({ label: 'host-availability-test' });
    const host = hostRef('remote', 'ssh-1');
    const issue = runtimeHostUnavailable(host, reason, `semantic:${reason}`);
    const availability = createHostAvailability({
      scope,
      readiness: { prepare: async () => err(issue) },
    });

    const pending = availability.ensureReady(host, 'demand');
    if (recovery === 'waiting') {
      await vi.waitFor(() =>
        expect(availability.stateFor(host)).toMatchObject({ recovery: 'waiting' })
      );
    } else {
      await pending;
    }

    expect(availability.stateFor(host)).toMatchObject({
      kind: 'unavailable',
      issue,
      recovery,
    });

    if (recovery === 'waiting') {
      availability.suspend(host);
      await pending;
    }
    await scope.dispose();
  });

  it('keeps manual and blocked failures dormant until an explicit request', async () => {
    const scope = createScope({ label: 'host-availability-test' });
    const host = hostRef('remote', 'ssh-1');
    const blocked = runtimeHostUnavailable(
      host,
      'unsupported-platform',
      'Host platform is not supported'
    );
    const prepare = vi.fn().mockResolvedValueOnce(err(blocked)).mockResolvedValueOnce(ok());
    const availability = createHostAvailability({
      scope,
      readiness: { prepare },
    });

    await availability.ensureReady(host, 'demand');
    await expect(availability.ensureReady(host, 'online')).resolves.toEqual(err(blocked));
    expect(prepare).toHaveBeenCalledOnce();

    await expect(availability.ensureReady(host, 'retry')).resolves.toMatchObject({
      success: true,
    });
    expect(prepare).toHaveBeenCalledTimes(2);

    await scope.dispose();
  });
});
