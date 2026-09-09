import { createManualClock } from '@emdash/shared/testing';
import { describe, expect, it, vi } from 'vitest';
import { AcpStartupCoordinator, type AcpStartupPhase } from './acp-startup-coordinator';

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

describe('AcpStartupCoordinator', () => {
  it('bounds concurrent starts while allowing the next conversation to proceed', async () => {
    const coordinator = new AcpStartupCoordinator({ maxConcurrent: 2 });
    const gates = [deferred<string>(), deferred<string>(), deferred<string>()];
    let active = 0;
    let peak = 0;
    const operation = (index: number) => async () => {
      active += 1;
      peak = Math.max(peak, active);
      const value = await gates[index]!.promise;
      active -= 1;
      return value;
    };

    const first = coordinator.run('one', operation(0));
    const second = coordinator.run('two', operation(1));
    const third = coordinator.run('three', operation(2));

    await vi.waitFor(() => expect(active).toBe(2));
    expect(peak).toBe(2);
    gates[0]!.resolve('one');
    await expect(first).resolves.toBe('one');
    await vi.waitFor(() => expect(active).toBe(2));
    gates[1]!.resolve('two');
    gates[2]!.resolve('three');
    await expect(Promise.all([second, third])).resolves.toEqual(['two', 'three']);
    expect(peak).toBe(2);
  });

  it('single-flights repeated starts for one conversation', async () => {
    const coordinator = new AcpStartupCoordinator();
    const gate = deferred<string>();
    const operation = vi.fn(() => gate.promise);

    const first = coordinator.run('same', operation);
    const second = coordinator.run('same', operation);

    expect(second).toBe(first);
    expect(operation).toHaveBeenCalledTimes(1);
    gate.resolve('ready');
    await expect(Promise.all([first, second])).resolves.toEqual(['ready', 'ready']);
  });

  it('multicasts startup phase changes to callers that join a flight', async () => {
    const clock = createManualClock();
    const coordinator = new AcpStartupCoordinator({ clock, retryDelaysMs: [50] });
    const gate = deferred<string>();
    const firstPhases: AcpStartupPhase[] = [];
    const joinedPhases: AcpStartupPhase[] = [];
    const operation = vi
      .fn<() => Promise<string>>()
      .mockRejectedValueOnce(new Error('temporary'))
      .mockImplementationOnce(() => gate.promise);
    const shouldRetry = (outcome: { kind: string }) => outcome.kind === 'error';

    const first = coordinator.run('same-phases', operation, {
      onPhase: (phase) => firstPhases.push(phase),
      shouldRetry,
    });
    await vi.waitFor(() => expect(operation).toHaveBeenCalledTimes(1));
    const joined = coordinator.run('same-phases', operation, {
      onPhase: (phase) => joinedPhases.push(phase),
      shouldRetry,
    });
    await clock.advanceBy(50);
    await vi.waitFor(() => expect(operation).toHaveBeenCalledTimes(2));
    gate.resolve('ready');

    await expect(Promise.all([first, joined])).resolves.toEqual(['ready', 'ready']);
    expect(firstPhases).toContain('retrying');
    expect(joinedPhases).toContain('retrying');
    expect(joinedPhases[0]).toBe('retrying');
  });

  it('rejects a changed provider or model instead of merging browser startups', async () => {
    const coordinator = new AcpStartupCoordinator();
    const gate = deferred<string>();
    const operation = vi.fn(() => gate.promise);

    const first = coordinator.run('changed-agent', operation, {
      compatibilityKey: JSON.stringify({ providerId: 'claude', model: 'sonnet' }),
    });
    const changed = coordinator.run('changed-agent', operation, {
      compatibilityKey: JSON.stringify({ providerId: 'codex', model: 'gpt-5' }),
    });

    await expect(changed).rejects.toThrow('different agent startup');
    expect(operation).toHaveBeenCalledTimes(1);
    gate.resolve('ready');
    await expect(first).resolves.toBe('ready');
  });

  it('retries a transient failure with bounded backoff and reports the phase', async () => {
    const clock = createManualClock();
    const coordinator = new AcpStartupCoordinator({
      clock,
      retryDelaysMs: [300, 900],
    });
    const phases: AcpStartupPhase[] = [];
    const operation = vi
      .fn<() => Promise<string>>()
      .mockRejectedValueOnce(new Error('timed out'))
      .mockResolvedValueOnce('ready');

    const started = coordinator.run('retry', operation, {
      onPhase: (phase) => phases.push(phase),
      shouldRetry: (outcome) =>
        outcome.kind === 'error' && String(outcome.error).includes('timed out'),
    });
    await vi.waitFor(() => expect(operation).toHaveBeenCalledTimes(1));
    await clock.advanceBy(300);

    await expect(started).resolves.toBe('ready');
    expect(operation).toHaveBeenCalledTimes(2);
    expect(phases).toContain('retrying');
  });
});
