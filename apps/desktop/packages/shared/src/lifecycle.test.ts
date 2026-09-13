import { noopLogger, setRootLogger } from '@emdash/shared/logger';
import { afterEach, describe, expect, it } from 'vitest';
import { once, toPendingLease, type Lease } from './lifecycle';
import { createStubLogger } from './testing';

function leaseFor<T>(value: T, onRelease: () => void | Promise<void>): Lease<T> {
  return {
    value,
    release: async () => {
      await onRelease();
    },
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('once', () => {
  it('runs the producer exactly once across sequential calls', async () => {
    let calls = 0;
    const fn = once(async () => {
      calls += 1;
      return calls;
    });

    const r1 = await fn();
    const r2 = await fn();
    const r3 = await fn();

    expect(calls).toBe(1);
    expect(r1).toBe(1);
    expect(r2).toBe(1);
    expect(r3).toBe(1);
  });

  it('all concurrent callers await the same completion', async () => {
    const gate = deferred<number>();
    let calls = 0;
    const fn = once(async () => {
      calls += 1;
      return gate.promise;
    });

    const p1 = fn();
    const p2 = fn();
    const p3 = fn();

    let p1Settled = false;
    let p2Settled = false;
    p1.then(() => (p1Settled = true));
    p2.then(() => (p2Settled = true));

    await new Promise((resolve) => setImmediate(resolve));
    expect(calls).toBe(1);
    expect(p1Settled).toBe(false);
    expect(p2Settled).toBe(false);

    gate.resolve(42);
    const [r1, r2, r3] = await Promise.all([p1, p2, p3]);
    expect(r1).toBe(42);
    expect(r2).toBe(42);
    expect(r3).toBe(42);
    expect(calls).toBe(1);
  });

  it('memoizes rejection — failed run is not retried', async () => {
    let calls = 0;
    const fn = once(async () => {
      calls += 1;
      throw new Error('fail');
    });

    await expect(fn()).rejects.toThrow('fail');
    await expect(fn()).rejects.toThrow('fail');
    expect(calls).toBe(1);
  });
});

describe('toPendingLease', () => {
  it('supports releasing before the lease promise resolves', async () => {
    let resolve!: (lease: Lease<string>) => void;
    let released = false;
    const leasePromise = new Promise<Lease<string>>((res) => {
      resolve = res;
    });

    const lease = toPendingLease(leasePromise);
    const release = lease.release();

    resolve(
      leaseFor('value', () => {
        released = true;
      })
    );

    await release;
    expect(released).toBe(true);
  });

  it('exposes readiness separately from release', async () => {
    const lease = toPendingLease(Promise.resolve(leaseFor('value', () => {})));

    await expect(lease.ready()).resolves.toBe('value');
    await expect(lease.release()).resolves.toBeUndefined();
  });

  it('release is idempotent — underlying release called exactly once on repeated calls', async () => {
    let releaseCount = 0;
    const lease = toPendingLease(
      Promise.resolve(
        leaseFor('value', () => {
          releaseCount += 1;
        })
      )
    );

    await lease.release();
    await lease.release();
    await lease.release();

    expect(releaseCount).toBe(1);
  });

  it('release is safe to call before the backing lease resolves and is still idempotent', async () => {
    let releaseCount = 0;
    let resolve!: (lease: Lease<string>) => void;
    const leasePromise = new Promise<Lease<string>>((res) => {
      resolve = res;
    });

    const pending = toPendingLease(leasePromise);

    // Start two releases before the lease is ready.
    const r1 = pending.release();
    const r2 = pending.release();

    resolve(
      leaseFor('value', () => {
        releaseCount += 1;
      })
    );

    await r1;
    await r2;
    await pending.release(); // one more after resolution

    expect(releaseCount).toBe(1);
  });

  describe('release failures', () => {
    afterEach(() => {
      setRootLogger(noopLogger);
    });

    it('reports release failures through the root logger instead of swallowing them', async () => {
      const { logger, calls } = createStubLogger();
      setRootLogger(logger);

      const pending = toPendingLease(
        Promise.resolve(
          leaseFor('value', () => {
            throw new Error('release boom');
          })
        )
      );

      await expect(pending.release()).resolves.toBeUndefined();

      expect(calls).toHaveLength(1);
      expect(calls[0]?.level).toBe('warn');
      expect(calls[0]?.fields?.error).toBeInstanceOf(Error);
    });
  });
});
