import { describe, expect, it, vi } from 'vitest';
import { err, ok, type Result } from '../result';
import { deferred } from '../testing';
import { createLifecycleRegistry } from './lifecycle-registry';
import type { Scope } from './scope';

type Resource = { id: string; generation: number };
type TestError = { type: 'test-error'; message: string };

const testError = (message: string): TestError => ({ type: 'test-error', message });

describe('LifecycleRegistry', () => {
  it('shares one in-flight start for the same key', async () => {
    const resource = { id: 'task-1', generation: 1 };
    const startDeferred = deferred<Result<Resource, TestError>>();
    const start = vi.fn(async () => startDeferred.promise);
    const registry = createLifecycleRegistry<{ id: string }, Resource, TestError>({
      keyOf: (input) => input.id,
      start,
      stop: async () => ok(),
    });

    const first = registry.start({ id: 'task-1' });
    const second = registry.start({ id: 'task-1' });

    expect(registry.state('task-1').kind).toBe('starting');
    await Promise.resolve();
    expect(start).toHaveBeenCalledTimes(1);

    startDeferred.resolve(ok(resource));

    await expect(first).resolves.toEqual(ok(resource));
    await expect(second).resolves.toEqual(ok(resource));
    expect(registry.get('task-1')).toBe(resource);
  });

  it('serializes stop behind an in-flight start', async () => {
    const resource = { id: 'task-1', generation: 1 };
    const startDeferred = deferred<Result<Resource, TestError>>();
    const stop = vi.fn(async () => ok<void>());
    const registry = createLifecycleRegistry<{ id: string }, Resource, TestError>({
      keyOf: (input) => input.id,
      start: async () => startDeferred.promise,
      stop,
    });

    const startPromise = registry.start({ id: 'task-1' });
    const stopPromise = registry.stop('task-1');

    expect(stop).not.toHaveBeenCalled();

    startDeferred.resolve(ok(resource));

    await expect(startPromise).resolves.toEqual(ok(resource));
    await expect(stopPromise).resolves.toEqual(ok());
    expect(stop).toHaveBeenCalledTimes(1);
    expect(registry.has('task-1')).toBe(false);
  });

  it('serializes start behind an in-flight stop and creates a new generation', async () => {
    const stopDeferred = deferred<Result<void, TestError>>();
    const start = vi.fn(async (input: { id: string; generation: number }) =>
      ok({ id: input.id, generation: input.generation })
    );
    const registry = createLifecycleRegistry<
      { id: string; generation: number },
      Resource,
      TestError
    >({
      keyOf: (input) => input.id,
      start,
      stop: async () => stopDeferred.promise,
    });
    const initial = { id: 'task-1', generation: 1 };
    await registry.register('task-1', initial);

    const stopPromise = registry.stop('task-1');
    const startPromise = registry.start({ id: 'task-1', generation: 2 });

    expect(start).not.toHaveBeenCalled();
    expect(registry.state('task-1')).toEqual({ kind: 'stopping', value: initial });

    stopDeferred.resolve(ok());

    await expect(stopPromise).resolves.toEqual(ok());
    await expect(startPromise).resolves.toEqual(ok({ id: 'task-1', generation: 2 }));
    expect(registry.get('task-1')).toEqual({ id: 'task-1', generation: 2 });
  });

  it('disposes partial start scope on failure and clears the error on retry', async () => {
    const cleanup = vi.fn();
    let shouldFail = true;
    const registry = createLifecycleRegistry<{ id: string }, Resource, TestError>({
      keyOf: (input) => input.id,
      start: async (input, scope: Scope) => {
        scope.add(cleanup);
        if (shouldFail) return err(testError('start failed'));
        return ok({ id: input.id, generation: 1 });
      },
      stop: async () => ok(),
    });

    const failed = await registry.start({ id: 'task-1' });

    expect(failed).toEqual(err(testError('start failed')));
    expect(cleanup).toHaveBeenCalledTimes(1);
    expect(registry.state('task-1')).toEqual({
      kind: 'start-failed',
      error: testError('start failed'),
    });

    shouldFail = false;
    const retried = await registry.start({ id: 'task-1' });

    expect(retried).toEqual(ok({ id: 'task-1', generation: 1 }));
    expect(registry.state('task-1')).toEqual({
      kind: 'ready',
      value: { id: 'task-1', generation: 1 },
    });
  });

  it('transitions to start-failed before disposing the scope when start throws', async () => {
    const cleanup = vi.fn();
    const thrown = new Error('start threw');
    const observed: Array<{ current: string; cleanupCallsSoFar: number }> = [];
    const registry = createLifecycleRegistry<{ id: string }, Resource, unknown>({
      keyOf: (input) => input.id,
      start: async (_input, scope: Scope) => {
        scope.add(cleanup);
        throw thrown;
      },
      stop: async () => ok(),
      onStateChanged: (change) => {
        observed.push({
          current: change.current.kind,
          cleanupCallsSoFar: cleanup.mock.calls.length,
        });
      },
    });

    await expect(registry.start({ id: 'task-1' })).rejects.toBe(thrown);

    // Observers never see a permanent 'starting': the thrown failure is visible.
    expect(observed.map((entry) => entry.current)).toEqual(['starting', 'start-failed']);
    expect(registry.state('task-1')).toEqual({ kind: 'start-failed', error: thrown });

    // The transition happens before the scope dispose (and its cleanups) run.
    expect(observed[1]?.cleanupCallsSoFar).toBe(0);
    expect(cleanup).toHaveBeenCalledTimes(1);
  });

  it('retains ownership after failed stop until retry succeeds', async () => {
    let shouldFail = true;
    const resource = { id: 'task-1', generation: 1 };
    const registry = createLifecycleRegistry<{ id: string }, Resource, TestError>({
      keyOf: (input) => input.id,
      start: async (input) => ok({ id: input.id, generation: 1 }),
      stop: async () => (shouldFail ? err(testError('stop failed')) : ok()),
    });
    await registry.register('task-1', resource);

    const failed = await registry.stop('task-1');

    expect(failed).toEqual(err(testError('stop failed')));
    expect(registry.get('task-1')).toBe(resource);
    expect([...registry.keys()]).toEqual(['task-1']);
    expect(registry.state('task-1')).toEqual({
      kind: 'stop-failed',
      value: resource,
      error: testError('stop failed'),
    });

    shouldFail = false;
    await expect(registry.stop('task-1')).resolves.toEqual(ok());
    expect(registry.has('task-1')).toBe(false);
    expect(registry.state('task-1')).toEqual({ kind: 'idle' });
  });

  it('force-removes retained failed stop ownership', async () => {
    const resource = { id: 'task-1', generation: 1 };
    const registry = createLifecycleRegistry<{ id: string }, Resource, TestError>({
      keyOf: (input) => input.id,
      start: async (input) => ok({ id: input.id, generation: 1 }),
      stop: async () => err(testError('stop failed')),
    });
    await registry.register('task-1', resource);

    await registry.stop('task-1');
    await registry.forceRemove('task-1', 'delete continued after teardown failure');

    expect(registry.has('task-1')).toBe(false);
    expect(registry.state('task-1')).toEqual({ kind: 'idle' });
  });

  it('reports observer errors without changing lifecycle results', async () => {
    const observerErrors: unknown[] = [];
    const registry = createLifecycleRegistry<{ id: string }, Resource, TestError>({
      keyOf: (input) => input.id,
      start: async (input) => ok({ id: input.id, generation: 1 }),
      stop: async () => ok(),
      onStateChanged: () => {
        throw new Error('observer failed');
      },
      onObserverError: ({ error }) => observerErrors.push(error),
    });

    await expect(registry.start({ id: 'task-1' })).resolves.toEqual(
      ok({ id: 'task-1', generation: 1 })
    );

    expect(observerErrors).toHaveLength(2);
    expect(registry.state('task-1')).toEqual({
      kind: 'ready',
      value: { id: 'task-1', generation: 1 },
    });
  });
});
