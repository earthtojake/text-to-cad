import { ok, type Unsubscribe } from '@emdash/shared';
import { deferred } from '@emdash/shared/testing';
import { describe, expect, it, vi } from 'vitest';
import { z } from 'zod';
import type { LiveSnapshot } from '../../api/channel';
import { resyncRetry } from '../follower';
import { liveJobStateSchema } from '../protocol';
import { LiveJobCancelledError, LiveJobClient, LiveJobFailedError } from './client';
import { LIVE_JOB_TERMINAL_RETAIN_MS, LiveJobSource, type LiveJobContext } from './source';

const inputSchema = z.object({ name: z.string() });
const progressSchema = z.object({ step: z.number() });
const resultSchema = z.object({ ok: z.boolean() });
const errorSchema = z.object({ message: z.string() });
const stateSchema = liveJobStateSchema(progressSchema, resultSchema, errorSchema);

type Input = z.infer<typeof inputSchema>;
type Progress = z.infer<typeof progressSchema>;
type Result = z.infer<typeof resultSchema>;
type ErrorState = z.infer<typeof errorSchema>;

function toError(err: unknown): ErrorState {
  return { message: err instanceof Error ? err.message : String(err) };
}

async function attach(server: LiveJobSource<Input, Progress, Result, ErrorState>, jobId: string) {
  const source = server.source(jobId);
  if (!source) throw new Error(`Missing job ${jobId}`);

  const refetchSnapshot = vi.fn(
    async () => (await source.snapshot()) as LiveSnapshot<z.infer<typeof stateSchema>>
  );
  const onState = vi.fn<(state: z.infer<typeof stateSchema>) => void>();
  const onProgress = vi.fn<(progress: Progress) => void>();
  const client = new LiveJobClient<Progress, Result, ErrorState>(stateSchema, {
    refetchSnapshot,
    onResyncFailed: resyncRetry(),
    onState,
  });

  client.onProgress(onProgress);
  client.seed(server.snapshot(jobId)!);
  let unsubscribe: Unsubscribe = await source.subscribe((update) => client.applyUpdate(update));

  return {
    client,
    onProgress,
    refetchSnapshot,
    unsubscribe: () => unsubscribe(),
    resubscribe: async () => {
      unsubscribe = await source.subscribe((update) => client.applyUpdate(update));
    },
  };
}

describe('LiveJobSource and LiveJobClient', () => {
  it('streams progress and resolves the result', async () => {
    const begin = deferred<void>();
    const server = new LiveJobSource<Input, Progress, Result, ErrorState>(
      async (_input, ctx) => {
        await begin.promise;
        ctx.progress({ step: 1 });
        ctx.progress({ step: 2 });
        return ok({ ok: true });
      },
      { toError }
    );
    const { jobId } = server.start({ name: 'success' });
    const { client, onProgress } = await attach(server, jobId);

    begin.resolve();

    await expect(client.result).resolves.toEqual({ ok: true });
    expect(onProgress).toHaveBeenNthCalledWith(1, { step: 1 });
    expect(onProgress).toHaveBeenNthCalledWith(2, { step: 2 });
    expect(client.getState()).toMatchObject({
      status: 'succeeded',
      progress: [{ step: 1 }, { step: 2 }],
      result: { ok: true },
    });
  });

  it('passes the run jobId to the handler context', async () => {
    const server = new LiveJobSource<Input, Progress, Result, ErrorState>(
      async (_input, ctx) => ok({ ok: ctx.jobId === 'job-context' }),
      {
        toError,
        idFactory: () => 'job-context',
      }
    );
    const { jobId } = server.start({ name: 'context' });
    const { client } = await attach(server, jobId);

    await expect(client.result).resolves.toEqual({ ok: true });
  });

  it('maps handler failures into failed state', async () => {
    const begin = deferred<void>();
    const server = new LiveJobSource<Input, Progress, Result, ErrorState>(
      async () => {
        await begin.promise;
        throw new Error('boom');
      },
      { toError }
    );
    const { jobId } = server.start({ name: 'failure' });
    const { client } = await attach(server, jobId);
    const result = client.result.catch((err: unknown) => err);

    begin.resolve();
    const err = await result;

    expect(err).toBeInstanceOf(LiveJobFailedError);
    expect((err as LiveJobFailedError<ErrorState>).error).toEqual({ message: 'boom' });
  });

  it('cancels cooperatively through the job signal', async () => {
    let signal: AbortSignal | undefined;
    const server = new LiveJobSource<Input, Progress, Result, ErrorState>(
      async (_input, ctx) => {
        signal = ctx.signal;
        await new Promise<never>((_resolve, reject) => {
          ctx.signal.addEventListener('abort', () => reject(new Error('aborted')), { once: true });
        });
        return ok({ ok: true });
      },
      { toError }
    );
    const { jobId } = server.start({ name: 'cancel' });
    const { client } = await attach(server, jobId);
    const result = client.result.catch((err: unknown) => err);

    server.cancel(jobId);
    const err = await result;

    expect(signal?.aborted).toBe(true);
    expect(err).toBeInstanceOf(LiveJobCancelledError);
  });

  it('awaits cooperative handlers when disposed', async () => {
    const started = deferred<void>();
    const released = deferred<void>();
    const events: string[] = [];
    const server = new LiveJobSource<Input, Progress, Result, ErrorState>(
      async (_input, ctx) => {
        started.resolve();
        ctx.signal.addEventListener('abort', () => events.push('aborted'), { once: true });
        await released.promise;
        events.push('handler settled');
        return ok({ ok: true });
      },
      { toError }
    );
    const { jobId } = server.start({ name: 'dispose' });
    const { client } = await attach(server, jobId);
    const result = client.result.catch((err: unknown) => err);

    await started.promise;
    const dispose = server.dispose();
    await Promise.resolve();
    expect(events).toEqual(['aborted']);

    released.resolve();
    await dispose;
    const err = await result;

    expect(events).toEqual(['aborted', 'handler settled']);
    expect(err).toBeInstanceOf(LiveJobCancelledError);
    expect(server.source(jobId)).toBeUndefined();
  });

  it('resyncs on sequence gaps without re-emitting already seen progress', async () => {
    let ctx: LiveJobContext<Progress> | undefined;
    const finish = deferred<Result>();
    const server = new LiveJobSource<Input, Progress, Result, ErrorState>(
      async (_input, jobCtx) => {
        ctx = jobCtx;
        return finish.promise.then((result) => ok(result));
      },
      { toError }
    );
    const { jobId } = server.start({ name: 'resync' });
    const { client, onProgress, refetchSnapshot, unsubscribe, resubscribe } = await attach(
      server,
      jobId
    );

    await vi.waitFor(() => expect(ctx).toBeDefined());
    ctx?.progress({ step: 1 });
    expect(onProgress).toHaveBeenCalledTimes(1);

    unsubscribe();
    ctx?.progress({ step: 2 });
    ctx?.progress({ step: 3 });
    await resubscribe();
    ctx?.progress({ step: 4 });

    await vi.waitFor(() => expect(refetchSnapshot).toHaveBeenCalledTimes(1));
    await vi.waitFor(() => expect(onProgress).toHaveBeenCalledTimes(4));

    finish.resolve({ ok: true });
    await expect(client.result).resolves.toEqual({ ok: true });
  });

  it('evicts terminal jobs after the fixed grace period', async () => {
    vi.useFakeTimers({ now: 1000 });
    try {
      const server = new LiveJobSource<Input, Progress, Result, ErrorState>(
        async () => ok({ ok: true }),
        { toError }
      );
      const { jobId } = server.start({ name: 'evict' });

      await vi.waitFor(() =>
        expect(server.getState(jobId)).toMatchObject({
          status: 'succeeded',
          result: { ok: true },
        })
      );
      expect(server.getState(jobId)).toMatchObject({
        status: 'succeeded',
        result: { ok: true },
      });

      vi.advanceTimersByTime(LIVE_JOB_TERMINAL_RETAIN_MS);

      expect(server.source(jobId)).toBeUndefined();
    } finally {
      vi.useRealTimers();
    }
  });

  it('uses configured id, clock, and terminal retention', async () => {
    vi.useFakeTimers();
    try {
      let now = 100;
      const server = new LiveJobSource<Input, Progress, Result, ErrorState>(
        async (_input, ctx) => {
          now = 150;
          ctx.progress({ step: 1 });
          now = 200;
          return ok({ ok: true });
        },
        {
          toError,
          idFactory: () => 'job-1',
          clock: () => now,
          terminalRetainMs: 10,
        }
      );

      const { jobId } = server.start({ name: 'options' });
      expect(jobId).toBe('job-1');

      await Promise.resolve();
      await Promise.resolve();
      expect(server.getState(jobId)).toEqual({
        status: 'succeeded',
        startedAt: 100,
        finishedAt: 200,
        progress: [{ step: 1 }],
        result: { ok: true },
      });

      vi.advanceTimersByTime(10);
      expect(server.source(jobId)).toBeUndefined();
    } finally {
      vi.useRealTimers();
    }
  });

  it('reports run lifecycle hooks for optional listing', async () => {
    const events: unknown[] = [];
    const server = new LiveJobSource<Input, Progress, Result, ErrorState>(
      async () => ok({ ok: true }),
      {
        toError,
        idFactory: () => 'listed-job',
        clock: () => 100,
        terminalRetainMs: 0,
        onRunStarted: (entry) => events.push({ kind: 'started', entry }),
        onRunChanged: (entry) => events.push({ kind: 'changed', entry }),
        onRunEvicted: (jobId) => events.push({ kind: 'evicted', jobId }),
      }
    );

    const { jobId } = server.start({ name: 'listed' });
    await vi.waitFor(() =>
      expect(events).toContainEqual({
        kind: 'changed',
        entry: { jobId, status: 'succeeded', startedAt: 100, finishedAt: 100 },
      })
    );
    await vi.waitFor(() => expect(events).toContainEqual({ kind: 'evicted', jobId }));

    expect(events).toEqual([
      {
        kind: 'started',
        entry: { jobId, status: 'running', startedAt: 100, finishedAt: undefined },
      },
      {
        kind: 'changed',
        entry: { jobId, status: 'succeeded', startedAt: 100, finishedAt: 100 },
      },
      { kind: 'evicted', jobId },
    ]);
  });

  it('exposes cursor and wait helpers on the client', async () => {
    let ctx: LiveJobContext<Progress> | undefined;
    const finish = deferred<Result>();
    const server = new LiveJobSource<Input, Progress, Result, ErrorState>(
      async (_input, jobCtx) => {
        ctx = jobCtx;
        return finish.promise.then((result) => ok(result));
      },
      { toError }
    );
    const { jobId } = server.start({ name: 'client' });
    const { client } = await attach(server, jobId);

    expect(client.cursor).toBeDefined();
    await vi.waitFor(() => expect(ctx).toBeDefined());
    const progressReady = client.waitForProgressCount(1);
    ctx?.progress({ step: 1 });
    await progressReady;

    const terminalReady = client.waitForTerminal();
    finish.resolve({ ok: true });
    await terminalReady;
    await expect(client.result).resolves.toEqual({ ok: true });
  });
});
