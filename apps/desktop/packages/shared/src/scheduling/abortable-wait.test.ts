import { describe, expect, it, vi } from 'vitest';
import { abortableWait } from './abortable-wait';

describe('abortableWait', () => {
  it('resolves with the settled value and runs cleanup exactly once', async () => {
    const cleanup = vi.fn();
    const wait = abortableWait<string>({}, (settle) => {
      queueMicrotask(() => settle.resolve('done'));
      return cleanup;
    });

    await expect(wait).resolves.toBe('done');
    expect(cleanup).toHaveBeenCalledTimes(1);
  });

  it('rejects with the settled error and runs cleanup', async () => {
    const cleanup = vi.fn();
    const failure = new Error('boom');
    const wait = abortableWait<string>({}, (settle) => {
      queueMicrotask(() => settle.reject(failure));
      return cleanup;
    });

    await expect(wait).rejects.toBe(failure);
    expect(cleanup).toHaveBeenCalledTimes(1);
  });

  it('guards against double settlement — the first settlement wins', async () => {
    const cleanup = vi.fn();
    const wait = abortableWait<string>({}, (settle) => {
      settle.resolve('first');
      settle.reject(new Error('second'));
      settle.resolve('third');
      return cleanup;
    });

    await expect(wait).resolves.toBe('first');
    expect(cleanup).toHaveBeenCalledTimes(1);
  });

  it('runs the cleanup returned after a synchronous settlement', async () => {
    const cleanup = vi.fn();
    const wait = abortableWait<string>({}, (settle) => {
      settle.resolve('sync');
      return cleanup;
    });

    await expect(wait).resolves.toBe('sync');
    expect(cleanup).toHaveBeenCalledTimes(1);
  });

  it('rejects without running the executor when the signal is already aborted', async () => {
    const controller = new AbortController();
    const reason = new Error('already aborted');
    controller.abort(reason);
    const executor = vi.fn();

    await expect(abortableWait({ signal: controller.signal }, executor)).rejects.toBe(reason);
    expect(executor).not.toHaveBeenCalled();
  });

  it('rejects and runs cleanup when the signal aborts while waiting', async () => {
    const controller = new AbortController();
    const cleanup = vi.fn();
    const reason = new Error('cancelled');
    const wait = abortableWait<string>({ signal: controller.signal }, () => cleanup);

    controller.abort(reason);

    await expect(wait).rejects.toBe(reason);
    expect(cleanup).toHaveBeenCalledTimes(1);
  });

  it('ignores a late abort after settlement', async () => {
    const controller = new AbortController();
    const cleanup = vi.fn();
    const wait = abortableWait<string>({ signal: controller.signal }, (settle) => {
      settle.resolve('done');
      return cleanup;
    });

    await expect(wait).resolves.toBe('done');
    controller.abort(new Error('too late'));
    expect(cleanup).toHaveBeenCalledTimes(1);
  });

  it('rejects with the executor error when the executor throws', async () => {
    const failure = new Error('executor boom');

    await expect(
      abortableWait({}, () => {
        throw failure;
      })
    ).rejects.toBe(failure);
  });

  describe('abort-reason mapping', () => {
    it('passes an Error reason through untouched', async () => {
      const controller = new AbortController();
      const reason = new Error('typed reason');
      const wait = abortableWait({ signal: controller.signal, fallback: 'fallback' }, () => {});

      controller.abort(reason);

      await expect(wait).rejects.toBe(reason);
    });

    it('maps a non-Error reason to the fallback message when provided', async () => {
      const controller = new AbortController();
      const wait = abortableWait({ signal: controller.signal, fallback: 'fell back' }, () => {});

      controller.abort('string reason');

      await expect(wait).rejects.toThrow('fell back');
    });

    it('rejects with the raw reason when non-Error and no fallback is provided', async () => {
      const controller = new AbortController();
      const wait = abortableWait({ signal: controller.signal }, () => {});

      controller.abort('raw reason');

      await expect(wait).rejects.toBe('raw reason');
    });

    it('passes the default DOMException reason through — DOMException is an Error', async () => {
      const controller = new AbortController();
      const wait = abortableWait(
        { signal: controller.signal, fallback: 'unused fallback' },
        () => {}
      );

      controller.abort();

      await expect(wait).rejects.toSatisfy(
        (error) => error instanceof DOMException && error.name === 'AbortError'
      );
    });

    it('rejects with the fallback when the reason is nullish and a fallback is provided', async () => {
      const controller = new AbortController();
      const wait = abortableWait(
        { signal: controller.signal, fallback: 'no reason given' },
        () => {}
      );

      controller.abort(null);

      await expect(wait).rejects.toThrow('no reason given');
    });

    it('rejects with a DOMException last, when the reason is nullish and no fallback exists', async () => {
      const controller = new AbortController();
      const wait = abortableWait({ signal: controller.signal }, () => {});

      controller.abort(null);

      await expect(wait).rejects.toSatisfy(
        (error) => error instanceof DOMException && error.name === 'AbortError'
      );
    });
  });
});
