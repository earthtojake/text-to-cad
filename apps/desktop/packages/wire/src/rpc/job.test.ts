import { ok } from '@emdash/shared';
import { deferred } from '@emdash/shared/testing';
import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import { defineContract, liveJob } from '../api/define';
import { LiveJobCancelledError, type LiveJobContext } from '../live/job';
import { createLiveJobReplicaCache } from '../live/replica';
import { createTestWire } from '../testing';

const jobContract = defineContract({
  build: liveJob({
    input: z.object({ name: z.string() }),
    progress: z.object({ step: z.string() }),
    result: z.object({ artifact: z.string() }),
    error: z.object({ message: z.string() }),
  }),
});

type BuildInput = { name: string };
type BuildProgress = { step: string };
type BuildResult = { artifact: string };

describe('contract jobs', () => {
  it('starts a job, streams progress, and resolves the result', async () => {
    const gate = deferred<void>();
    const { client } = setup(async (input, ctx) => {
      await gate.promise;
      ctx.progress({ step: 'build' });
      return { artifact: `${input.name}.zip` };
    });

    const jobs = createLiveJobReplicaCache(jobContract.build, client.build);
    const lease = await jobs.start({ name: 'demo' });
    const handle = await lease.ready();
    const progress: Array<{ step: string }> = [];
    handle.onProgress((entry) => progress.push(entry));
    gate.resolve();

    await expect(handle.result).resolves.toEqual({ artifact: 'demo.zip' });
    expect(progress).toEqual([{ step: 'build' }]);
    await lease.release();
    await jobs.dispose();
  });

  it('passes the server job id through controller job context', async () => {
    const { client } = setup(async (_input, ctx) => ({ artifact: ctx.jobId }));

    const jobs = createLiveJobReplicaCache(jobContract.build, client.build);
    const lease = await jobs.start({ name: 'context' });
    const handle = await lease.ready();

    await expect(handle.result).resolves.toEqual({ artifact: handle.jobId });
    await lease.release();
    await jobs.dispose();
  });

  it('cancels a running job', async () => {
    const { client } = setup(
      async (_input, ctx) =>
        new Promise<BuildResult>((_resolve, reject) => {
          ctx.signal.addEventListener('abort', () => reject(new Error('aborted')));
        })
    );

    const jobs = createLiveJobReplicaCache(jobContract.build, client.build);
    const lease = await jobs.start({ name: 'cancel' });
    const handle = await lease.ready();
    await handle.cancel();

    await expect(handle.result).rejects.toBeInstanceOf(LiveJobCancelledError);
    await lease.release();
    await jobs.dispose();
  });

  it('reattaches to a terminal job state by id', async () => {
    const gate = deferred<void>();
    const { client } = setup(async (input) => {
      await gate.promise;
      return { artifact: `${input.name}.zip` };
    });

    const jobs = createLiveJobReplicaCache(jobContract.build, client.build, { lingerMs: 100 });
    const lease = await jobs.start({ name: 'reattach' });
    const handle = await lease.ready();
    gate.resolve();
    await expect(handle.result).resolves.toEqual({ artifact: 'reattach.zip' });
    await lease.release();

    const reattachedLease = jobs.acquire(handle.jobId);
    const reattached = await reattachedLease.ready();

    await expect(reattached.result).resolves.toEqual({ artifact: 'reattach.zip' });
    await reattachedLease.release();
    await jobs.dispose();
  });

  it('cancels running jobs when the controller is disposed', async () => {
    const { client, controller } = setup(
      async (_input, ctx) =>
        new Promise<BuildResult>((_resolve, reject) => {
          ctx.signal.addEventListener('abort', () => reject(new Error('aborted')));
        })
    );

    const jobs = createLiveJobReplicaCache(jobContract.build, client.build);
    const lease = await jobs.start({ name: 'dispose' });
    const handle = await lease.ready();
    await controller.dispose?.();

    await expect(handle.result).rejects.toBeInstanceOf(LiveJobCancelledError);
    await lease.release();
    await jobs.dispose();
  });

  it('validates job start input in full validation mode', async () => {
    const { client } = setup(async (input) => ({ artifact: `${input.name}.zip` }), {
      validate: 'full',
    });

    await expect(client.build.start({ name: 1 } as never)).rejects.toMatchObject({
      code: 'HANDLER_ERROR',
    });
  });
});

function setup(
  run: (
    input: BuildInput,
    ctx: LiveJobContext<BuildProgress>
  ) => Promise<BuildResult> | BuildResult,
  options: { validate?: 'none' | 'inputs' | 'full' } = {}
) {
  const wire = createTestWire(
    jobContract,
    {
      build: {
        run: async (input, ctx) => ok(await run(input as BuildInput, ctx)),
        toError: (error) => ({
          message: error instanceof Error ? error.message : String(error),
        }),
      },
    },
    { validate: options.validate }
  );
  return { client: wire.client, controller: wire.controller };
}
