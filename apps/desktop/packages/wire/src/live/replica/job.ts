import type { PendingLease, Unsubscribe } from '@emdash/shared';
import { stableStringify } from '@emdash/shared/util';
import type { z } from 'zod';
import type { LiveSnapshot, LiveSource, LiveUpdate } from '../../api/channel';
import type { LiveJobClientHandle } from '../../api/client';
import type {
  LiveJobEndpointDef,
  JobError,
  JobInput,
  JobProgress,
  JobResult,
} from '../../api/define';
import type { WireInstrumentation } from '../../api/instrumentation';
import { resyncRetry } from '../follower';
import { LiveJobCancelledError, LiveJobClient, LiveJobFailedError } from '../job';
import { liveJobStateSchema } from '../protocol';
import type { LiveJobState } from '../protocol';
import { LiveStateSource } from '../state';
import { createReplicaResourceCache } from './retention';
import { resourceCachedLiveSource } from './source';

export type ReplicaJobState<Def extends LiveJobEndpointDef> = LiveJobState<
  JobProgress<Def>,
  JobResult<Def>,
  JobError<Def>
>;

export interface JobStore<T> {
  reset(data: T): void;
  current(): T;
}

export type ReplicaJobOptions<Def extends LiveJobEndpointDef = LiveJobEndpointDef> = {
  instrumentation?: WireInstrumentation;
  store?: JobStore<ReplicaJobState<Def>>;
};

export class ReplicaJob<Def extends LiveJobEndpointDef = LiveJobEndpointDef> implements LiveSource {
  readonly jobId: string;
  readonly ready: Promise<void>;
  readonly result: Promise<JobResult<Def>>;

  private readonly client: LiveJobClient<JobProgress<Def>, JobResult<Def>, JobError<Def>>;
  private local:
    | LiveStateSource<LiveJobState<JobProgress<Def>, JobResult<Def>, JobError<Def>>>
    | undefined;
  private readonly store: JobStore<ReplicaJobState<Def>>;
  private readonly detachPromise: Promise<Unsubscribe>;
  private seeding = false;
  private detached = false;
  private disposed = false;

  constructor(
    private readonly job: LiveJobClientHandle<Def>,
    jobId: string,
    options: ReplicaJobOptions<Def> = {}
  ) {
    this.jobId = jobId;
    this.store = options.store ?? createPlainJobStore<ReplicaJobState<Def>>();
    const handle = this.job.handle(jobId);
    const stateSchema = liveJobStateSchema(
      this.job.def.progress,
      this.job.def.result,
      this.job.def.error
    ) as z.ZodType<LiveJobState<JobProgress<Def>, JobResult<Def>, JobError<Def>>>;
    const retryPolicy = resyncRetry();
    this.client = new LiveJobClient<JobProgress<Def>, JobResult<Def>, JobError<Def>>(stateSchema, {
      refetchSnapshot: () =>
        handle.snapshot() as Promise<
          LiveSnapshot<LiveJobState<JobProgress<Def>, JobResult<Def>, JobError<Def>>>
        >,
      // Retry like every production replica, but stop once the job reached a
      // terminal state — the replica detaches from upstream then anyway.
      onResyncFailed: (context) => (this.detached ? { kind: 'give-up' } : retryPolicy(context)),
      onState: (state) => this.handleState(state),
      instrumentation: options.instrumentation,
      topic: handle.topic,
    });
    this.result = this.client.result;
    this.ready = handle.snapshot().then((snapshot) => {
      const data = structuredClone(snapshot.data) as ReplicaJobState<Def>;
      this.store.reset(data);
      this.seeding = true;
      try {
        this.client.seed(
          snapshot as LiveSnapshot<LiveJobState<JobProgress<Def>, JobResult<Def>, JobError<Def>>>
        );
      } finally {
        this.seeding = false;
      }
    });
    this.detachPromise = handle.attach((update) => this.client.applyUpdate(update), {
      onReattach: () => this.client.invalidate(),
    });
    void this.result.catch(() => undefined);
  }

  getState(): LiveJobState<JobProgress<Def>, JobResult<Def>, JobError<Def>> | undefined {
    try {
      return this.store.current();
    } catch {
      return undefined;
    }
  }

  onProgress(cb: (progress: JobProgress<Def>) => void): Unsubscribe {
    return this.client.onProgress(cb);
  }

  cancel(): Promise<void> {
    return this.job.cancel(this.jobId);
  }

  async snapshot(): Promise<
    LiveSnapshot<LiveJobState<JobProgress<Def>, JobResult<Def>, JobError<Def>>>
  > {
    await this.ready;
    return this.localSource().snapshot();
  }

  subscribe(cb: (update: LiveUpdate) => void): Unsubscribe {
    return this.localSource().subscribe(cb);
  }

  async dispose(): Promise<void> {
    if (this.disposed) return;
    this.disposed = true;
    await this.detachUpstream();
    this.client.dispose();
  }

  private handleState(state: LiveJobState<JobProgress<Def>, JobResult<Def>, JobError<Def>>): void {
    if (this.seeding) {
      if (state.status !== 'running') void this.detachUpstream();
      return;
    }

    const local = this.local;
    if (local) {
      local.produce((draft) => replaceDraft(draft, state));
    }
    this.store.reset(state as ReplicaJobState<Def>);
    if (state.status !== 'running') void this.detachUpstream();
  }

  private async detachUpstream(): Promise<void> {
    if (this.detached) return;
    this.detached = true;
    (await this.detachPromise)();
  }

  private localSource(): LiveStateSource<
    LiveJobState<JobProgress<Def>, JobResult<Def>, JobError<Def>>
  > {
    if (!this.local) {
      this.local = new LiveStateSource(structuredClone(this.store.current()));
    }
    return this.local;
  }
}

export type LiveJobReplicaCacheOptions<Def extends LiveJobEndpointDef = LiveJobEndpointDef> = Omit<
  ReplicaJobOptions<Def>,
  'store'
> & {
  lingerMs?: number;
  store?: () => JobStore<ReplicaJobState<Def>>;
};

export type LiveJobReplicaCache<Def extends LiveJobEndpointDef = LiveJobEndpointDef> = {
  readonly kind: 'liveJobReplicaCache';
  readonly def: Def;
  start(input: JobInput<Def>): Promise<PendingLease<ReplicaJob<Def>>>;
  acquire(jobId: string): PendingLease<ReplicaJob<Def>>;
  peek(jobId: string): ReplicaJob<Def> | undefined;
  resolve(jobId: string): LiveSource;
  cancel(jobId: string): Promise<void>;
  dispose(): Promise<void>;
};

export function createLiveJobReplicaCache<Def extends LiveJobEndpointDef>(
  def: Def,
  job: LiveJobClientHandle<Def>,
  options: LiveJobReplicaCacheOptions<Def> = {}
): LiveJobReplicaCache<Def> {
  const source = createReplicaResourceCache<string, ReplicaJob<Def>>({
    key: stableStringify,
    lingerMs: options.lingerMs,
    async create(jobId, scope) {
      const { store, ...replicaOptions } = options;
      const replica = new ReplicaJob(job, jobId, { ...replicaOptions, store: store?.() });
      scope.add(() => replica.dispose());
      await replica.ready;
      return replica;
    },
  });

  return {
    kind: 'liveJobReplicaCache',
    def,
    async start(input) {
      const { jobId } = await job.start(input);
      return source.acquire(jobId);
    },
    acquire(jobId) {
      return source.acquire(jobId);
    },
    peek(jobId) {
      return source.peek(jobId);
    },
    resolve(jobId) {
      return resourceCachedLiveSource(source, jobId, (replica) => replica);
    },
    cancel(jobId) {
      return job.cancel(jobId);
    },
    dispose() {
      return source.dispose();
    },
  };
}

export function isLiveJobReplicaCache(value: unknown): value is LiveJobReplicaCache {
  return (
    typeof value === 'object' &&
    value !== null &&
    (value as { kind?: unknown }).kind === 'liveJobReplicaCache'
  );
}

export { LiveJobCancelledError, LiveJobFailedError };

export function createPlainJobStore<T>(): JobStore<T> {
  let ready = false;
  let value: T | undefined;

  return {
    reset(data) {
      ready = true;
      value = structuredClone(data);
    },
    current() {
      if (!ready) throw new Error('JobStore has not been seeded');
      return value as T;
    },
  };
}

function replaceDraft<T>(draft: T, next: T): void {
  for (const key of Object.keys(draft as object)) {
    delete (draft as Record<string, unknown>)[key];
  }
  Object.assign(draft as object, structuredClone(next));
}
