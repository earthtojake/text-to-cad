import { describe, expect, it, vi } from 'vitest';
import { createStubLogger, deferred } from '../testing';
import { createScope, describeScope } from './scope';

describe('createScope', () => {
  it('runs cleanups in reverse registration order on dispose', async () => {
    const scope = createScope();
    const order: string[] = [];
    scope.add(() => {
      order.push('first');
    });
    scope.add(() => {
      order.push('second');
    });

    await scope.dispose();

    expect(order).toEqual(['second', 'first']);
    expect(scope.state).toBe('closed');
    expect(scope.disposed).toBe(true);
  });

  it('runs a cleanup immediately when added after close', async () => {
    const scope = createScope();
    await scope.dispose();

    const cleanup = vi.fn();
    scope.add(cleanup);

    await vi.waitFor(() => expect(cleanup).toHaveBeenCalledTimes(1));
  });

  it('disposes resources registered through use()', async () => {
    const scope = createScope();
    const resource = { dispose: vi.fn() };

    expect(scope.use(resource)).toBe(resource);
    await scope.dispose();

    expect(resource.dispose).toHaveBeenCalledTimes(1);
  });

  it('aborts its signal with the dispose reason', async () => {
    const scope = createScope();
    const reason = new Error('shutting down');

    await scope.dispose(reason);

    expect(scope.signal.aborted).toBe(true);
    expect(scope.signal.reason).toBe(reason);
  });

  it('reports cleanup failures through the injected logger by default', async () => {
    const { logger, calls } = createStubLogger();
    const scope = createScope({ logger, label: 'test-scope' });
    scope.add(() => {
      throw new Error('cleanup boom');
    });

    await scope.dispose();

    expect(calls).toHaveLength(1);
    expect(calls[0]?.level).toBe('warn');
    expect(calls[0]?.message).toBe('scope cleanup failed');
    expect(calls[0]?.message).not.toContain('wire');
  });

  it('routes cleanup failures to onCleanupError when provided', async () => {
    const { logger, calls } = createStubLogger();
    const onCleanupError = vi.fn();
    const scope = createScope({ logger, onCleanupError });
    const failure = new Error('cleanup boom');
    scope.add(() => {
      throw failure;
    });

    await scope.dispose();

    expect(onCleanupError).toHaveBeenCalledTimes(1);
    expect(onCleanupError.mock.calls[0]?.[0]).toBe(failure);
    expect(calls).toHaveLength(0);
  });

  it('disposes children before running its own cleanups', async () => {
    const scope = createScope();
    const order: string[] = [];
    scope.add(() => {
      order.push('parent');
    });
    const child = scope.child('child');
    child.add(() => {
      order.push('child');
    });

    await scope.dispose();

    expect(order).toEqual(['child', 'parent']);
    expect(child.disposed).toBe(true);
  });

  it('immediately disposes children created after close', async () => {
    const scope = createScope();
    await scope.dispose();

    const child = scope.child('late');

    await vi.waitFor(() => expect(child.state).toBe('closed'));
  });

  describe('run', () => {
    it('exposes success exits through exit and value()', async () => {
      const scope = createScope();
      const run = scope.run('work', async () => 42);

      await expect(run.value()).resolves.toBe(42);
      await expect(run.exit).resolves.toEqual({ kind: 'success', value: 42 });
      await scope.dispose();
    });

    it('reports failures through the scope logger', async () => {
      const { logger, calls } = createStubLogger();
      const scope = createScope({ logger });
      const failure = new Error('run boom');
      const run = scope.run('work', async () => {
        throw failure;
      });

      await expect(run.exit).resolves.toEqual({ kind: 'failure', error: failure });
      expect(calls).toHaveLength(1);
      expect(calls[0]?.message).toBe('scope run failed');
      expect(calls[0]?.message).not.toContain('wire');
      await scope.dispose();
    });

    it('closes the scope when onFailure is close-scope', async () => {
      const scope = createScope({ logger: createStubLogger().logger });
      const run = scope.run(
        'work',
        async () => {
          throw new Error('fatal');
        },
        { onFailure: 'close-scope' }
      );

      await run.exit;
      await vi.waitFor(() => expect(scope.disposed).toBe(true));
    });

    it('cancels in-flight runs on dispose', async () => {
      const scope = createScope();
      const gate = deferred<void>();
      const run = scope.run('work', async (signal) => {
        gate.resolve();
        await new Promise((_, reject) => {
          signal.addEventListener('abort', () => reject(signal.reason), { once: true });
        });
      });

      await gate.promise;
      await scope.dispose(new Error('scope torn down'));

      const exit = await run.exit;
      expect(exit.kind).toBe('cancelled');
    });

    it('returns a cancelled run when the scope is already closed', async () => {
      const scope = createScope();
      await scope.dispose();

      const run = scope.run('late', async () => 1);

      await expect(run.exit).resolves.toMatchObject({ kind: 'cancelled' });
      await expect(run.value()).rejects.toBeInstanceOf(Error);
    });
  });

  it('describeScope reports labels, runs, and children', async () => {
    const scope = createScope({ label: 'root' });
    const gate = deferred<void>();
    scope.child('child');
    scope.run('work', async () => {
      await gate.promise;
    });

    const description = describeScope(scope);
    expect(description.label).toBe('root');
    expect(description.children.map((child) => child.label)).toEqual(['child']);
    expect(description.runs.map((run) => run.label)).toEqual(['work']);

    gate.resolve();
    await scope.dispose();
  });
});
