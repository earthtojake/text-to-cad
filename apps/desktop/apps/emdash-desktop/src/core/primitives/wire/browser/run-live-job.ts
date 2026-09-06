import { err, ok, type Result } from '@emdash/shared';
import { createLiveJobReplicaCache, LiveJobFailedError } from '@emdash/wire/live';
import {
  type JobError,
  type JobInput,
  type JobProgress,
  type JobResult,
  type LiveJobClientHandle,
  type LiveJobEndpointDef,
} from '@emdash/wire/rpc';

export async function runDesktopLiveJob<Def extends LiveJobEndpointDef>(
  definition: Def,
  handle: LiveJobClientHandle<Def>,
  input: JobInput<Def>,
  onProgress?: (progress: JobProgress<Def>) => void,
  options: { signal?: AbortSignal } = {}
): Promise<Result<JobResult<Def>, JobError<Def>>> {
  const jobs = createLiveJobReplicaCache(definition, handle);
  const lease = await jobs.start(input);
  try {
    const job = await lease.ready();
    const cancel = () => void job.cancel().catch(() => undefined);
    // Deliberately hand-rolled instead of `abortableWait`: abort here means
    // "request job.cancel() and keep awaiting the job's own settled result",
    // while abortableWait rejects the wait on abort and never runs its
    // executor for a pre-aborted signal (renderer-shared-adoption ticket 05).
    if (options.signal?.aborted) cancel();
    options.signal?.addEventListener('abort', cancel, { once: true });
    const unsubscribe = onProgress ? job.onProgress(onProgress) : undefined;
    try {
      return ok(await job.result);
    } catch (error) {
      if (error instanceof LiveJobFailedError) return err(error.error as JobError<Def>);
      throw error;
    } finally {
      options.signal?.removeEventListener('abort', cancel);
      unsubscribe?.();
    }
  } finally {
    await lease.release();
    await jobs.dispose();
  }
}
