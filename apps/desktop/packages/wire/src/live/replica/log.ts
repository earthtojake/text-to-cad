import { createEmitter, type PendingLease, type Unsubscribe } from '@emdash/shared';
import { stableStringify } from '@emdash/shared/util';
import type { LiveLogSnapshotData, LiveSnapshot, LiveSource, LiveUpdate } from '../../api/channel';
import type { LiveLogClientHandle } from '../../api/client';
import type { LiveLogEndpointDef, LiveLogKey } from '../../api/define';
import type { WireInstrumentation } from '../../api/instrumentation';
import { resyncRetry, type LiveResyncFailurePolicy } from '../follower';
import { LiveLogSource, LiveLogClient, type LiveLogSourceOptions } from '../log';
import { createReplicaResourceCache } from './retention';
import { resourceCachedLiveSource } from './source';

export interface LogSink {
  reset(data: LiveLogSnapshotData): void;
  append(chunk: string): void;
}

export interface LogStore extends LogSink {
  text(): string;
}

export type ReplicaLogOptions = LiveLogSourceOptions & {
  instrumentation?: WireInstrumentation;
  /** Resync failure policy; production replicas retry until success or dispose. */
  onResyncFailed?: LiveResyncFailurePolicy;
  store?: LogSink;
};

export class ReplicaLog implements LiveSource {
  readonly ready: Promise<void>;

  private local: LiveLogSource | undefined;
  private readonly client: LiveLogClient;
  private readonly appendEmitter = createEmitter<string>();
  private readonly detachPromise: Promise<Unsubscribe>;
  private writtenOffset = 0;
  private disposed = false;

  constructor(
    private readonly handle: ReturnType<LiveLogClientHandle['handle']>,
    private readonly options: ReplicaLogOptions = {}
  ) {
    if (!options.store) this.local = new LiveLogSource(options);
    this.client = new LiveLogClient({
      refetchSnapshot: () => handle.snapshot(),
      onReset: (data) => this.reset(data),
      onAppend: (chunk) => this.append(chunk),
      onResyncFailed: options.onResyncFailed ?? resyncRetry(),
      instrumentation: options.instrumentation,
      topic: handle.topic,
    });
    this.ready = handle.snapshot().then((snapshot) => this.client.seed(snapshot));
    this.detachPromise = handle.attach((update) => this.client.applyUpdate(update), {
      onReattach: () => this.client.invalidate(),
    });
  }

  text(): string {
    const readable = asReadableLogStore(this.options.store);
    if (readable) return readable.text();
    if (this.local) return this.local.snapshot().data.text;
    throw new Error('ReplicaLog is backed by a write-only LogSink');
  }

  onAppend(cb: (chunk: string) => void): Unsubscribe {
    return this.appendEmitter.subscribe(cb);
  }

  async snapshot(): Promise<LiveSnapshot<LiveLogSnapshotData>> {
    await this.ready;
    return this.localSource().snapshot();
  }

  subscribe(cb: (update: LiveUpdate) => void): Unsubscribe {
    return this.localSource().subscribe(cb);
  }

  async dispose(): Promise<void> {
    if (this.disposed) return;
    this.disposed = true;
    this.client.dispose();
    this.appendEmitter.clear();
    (await this.detachPromise)();
  }

  private reset(data: LiveLogSnapshotData): void {
    this.options.store?.reset(data);
    this.local?.reseed(data);
    this.writtenOffset = data.baseOffset + byteLength(data.text);
  }

  private append(chunk: string): void {
    this.options.store?.append(chunk);
    this.local?.append(chunk);
    this.writtenOffset += byteLength(chunk);
    this.appendEmitter.emit(chunk);
  }

  private localSource(): LiveLogSource {
    if (!this.local) {
      const readable = asReadableLogStore(this.options.store);
      const text = readable?.text() ?? '';
      const bytes = byteLength(text);
      const baseOffset = this.writtenOffset >= bytes ? this.writtenOffset - bytes : 0;
      this.local = new LiveLogSource(this.options);
      this.local.reseed({
        baseOffset,
        text,
        truncated: true,
      });
    }
    return this.local;
  }
}

export type LiveLogReplicaCacheOptions = Omit<ReplicaLogOptions, 'store'> & {
  lingerMs?: number;
  store?: () => LogSink;
};

export type LiveLogReplicaCache<Def extends LiveLogEndpointDef = LiveLogEndpointDef> = {
  readonly kind: 'liveLogReplicaCache';
  readonly def: Def;
  acquire(key: LiveLogKey<Def>): PendingLease<ReplicaLog>;
  peek(key: LiveLogKey<Def>): ReplicaLog | undefined;
  resolve(key: LiveLogKey<Def>): LiveSource;
  dispose(): Promise<void>;
};

export function createLiveLogReplicaCache<Def extends LiveLogEndpointDef>(
  def: Def,
  log: LiveLogClientHandle<Def>,
  options: LiveLogReplicaCacheOptions = {}
): LiveLogReplicaCache<Def> {
  const source = createReplicaResourceCache<LiveLogKey<Def>, ReplicaLog>({
    key: stableStringify,
    lingerMs: options.lingerMs,
    async create(key, scope) {
      const { store, ...replicaOptions } = options;
      const replica = new ReplicaLog(log.handle(key), { ...replicaOptions, store: store?.() });
      scope.add(() => replica.dispose());
      await replica.ready;
      return replica;
    },
  });

  return {
    kind: 'liveLogReplicaCache',
    def,
    acquire(key) {
      return source.acquire(key);
    },
    peek(key) {
      return source.peek(key);
    },
    resolve(key) {
      return resourceCachedLiveSource(source, key, (replica) => replica);
    },
    dispose() {
      return source.dispose();
    },
  };
}

function asReadableLogStore(store: LogSink | undefined): LogStore | undefined {
  if (!store) return undefined;
  const candidate = store as Partial<LogStore>;
  return typeof candidate.text === 'function' ? (store as LogStore) : undefined;
}

const encoder = new TextEncoder();

function byteLength(text: string): number {
  return encoder.encode(text).byteLength;
}

export function isLiveLogReplicaCache(value: unknown): value is LiveLogReplicaCache {
  return (
    typeof value === 'object' &&
    value !== null &&
    (value as { kind?: unknown }).kind === 'liveLogReplicaCache'
  );
}
