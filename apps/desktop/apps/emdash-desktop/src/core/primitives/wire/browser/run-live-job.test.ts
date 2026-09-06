import { LiveJobFailedError } from '@emdash/wire/live';
import type { JobInput, LiveJobClientHandle, LiveJobEndpointDef } from '@emdash/wire/rpc';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { runDesktopLiveJob } from './run-live-job';

const mocks = vi.hoisted(() => ({
  createLiveJobReplicaCache: vi.fn(),
}));

vi.mock('@emdash/wire/live', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  createLiveJobReplicaCache: mocks.createLiveJobReplicaCache,
}));

const definition = {} as unknown as LiveJobEndpointDef;
const handle = {} as unknown as LiveJobClientHandle<LiveJobEndpointDef>;
const input = {} as JobInput<LiveJobEndpointDef>;

function deferred<T>(): {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason?: unknown) => void;
} {
  let resolve: (value: T) => void = () => {};
  let reject: (reason?: unknown) => void = () => {};
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function makeHarness(result: Promise<unknown>) {
  const job = {
    cancel: vi.fn().mockResolvedValue(undefined),
    onProgress: vi.fn(() => () => {}),
    result,
  };
  const lease = {
    ready: vi.fn().mockResolvedValue(job),
    release: vi.fn().mockResolvedValue(undefined),
  };
  const cache = {
    start: vi.fn().mockResolvedValue(lease),
    dispose: vi.fn().mockResolvedValue(undefined),
  };
  mocks.createLiveJobReplicaCache.mockReturnValue(cache);
  return { job, lease, cache };
}

beforeEach(() => {
  mocks.createLiveJobReplicaCache.mockReset();
});

describe('runDesktopLiveJob abort plumbing', () => {
  it('returns the job result without cancelling when the signal never aborts', async () => {
    const { job } = makeHarness(Promise.resolve('done'));
    const controller = new AbortController();
    const addSpy = vi.spyOn(controller.signal, 'addEventListener');
    const removeSpy = vi.spyOn(controller.signal, 'removeEventListener');

    const outcome = await runDesktopLiveJob(definition, handle, input, undefined, {
      signal: controller.signal,
    });

    expect(outcome.success).toBe(true);
    if (outcome.success) expect(outcome.data).toBe('done');
    expect(job.cancel).not.toHaveBeenCalled();
    expect(addSpy).toHaveBeenCalledWith('abort', expect.any(Function), { once: true });
    expect(removeSpy).toHaveBeenCalledWith('abort', addSpy.mock.calls[0]?.[1]);
  });

  it('cancels immediately on a pre-aborted signal and still awaits the settled result', async () => {
    const result = deferred<string>();
    const { job } = makeHarness(result.promise);
    const controller = new AbortController();
    controller.abort();

    const onProgress = vi.fn();
    const runPromise = runDesktopLiveJob(definition, handle, input, onProgress, {
      signal: controller.signal,
    });
    await vi.waitFor(() => expect(job.onProgress).toHaveBeenCalled());

    expect(job.cancel).toHaveBeenCalledTimes(1);

    result.resolve('settled-after-cancel');
    const outcome = await runPromise;
    expect(outcome.success).toBe(true);
    if (outcome.success) expect(outcome.data).toBe('settled-after-cancel');
    expect(job.cancel).toHaveBeenCalledTimes(1);
  });

  it('cancels exactly once on mid-run abort and keeps awaiting the job result', async () => {
    const result = deferred<string>();
    const { job } = makeHarness(result.promise);
    const controller = new AbortController();

    const onProgress = vi.fn();
    const runPromise = runDesktopLiveJob(definition, handle, input, onProgress, {
      signal: controller.signal,
    });
    await vi.waitFor(() => expect(job.onProgress).toHaveBeenCalled());
    expect(job.cancel).not.toHaveBeenCalled();

    controller.abort();
    expect(job.cancel).toHaveBeenCalledTimes(1);

    result.resolve('settled-after-abort');
    const outcome = await runPromise;
    expect(outcome.success).toBe(true);
    if (outcome.success) expect(outcome.data).toBe('settled-after-abort');
    expect(job.cancel).toHaveBeenCalledTimes(1);
  });

  it('maps LiveJobFailedError to a Result error', async () => {
    const failure = { code: 'boom' };
    makeHarness(Promise.reject(new LiveJobFailedError(failure)));

    const outcome = await runDesktopLiveJob(definition, handle, input);

    expect(outcome.success).toBe(false);
    if (!outcome.success) expect(outcome.error).toBe(failure);
  });
});
