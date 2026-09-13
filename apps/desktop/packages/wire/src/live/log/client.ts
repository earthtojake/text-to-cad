import type { Logger } from '@emdash/shared/logger';
import type { Clock } from '@emdash/shared/scheduling';
import type { LiveLogSnapshotData, LiveSnapshot, LiveUpdate } from '../../api/channel';
import type { WireInstrumentation } from '../../api/instrumentation';
import {
  LiveFollower,
  type LiveFollowerApplyResult,
  type LiveMaterializer,
  type LiveResyncFailurePolicy,
} from '../follower';
import type { LiveLogDelta } from '../protocol';

export type LiveLogClientDeps = {
  refetchSnapshot: () => Promise<LiveSnapshot<LiveLogSnapshotData>>;
  onReset: (data: LiveLogSnapshotData) => void;
  onAppend: (chunk: string) => void;
  /** Required policy deciding what happens when a resync refetch fails. */
  onResyncFailed: LiveResyncFailurePolicy;
  instrumentation?: WireInstrumentation;
  logger?: Logger;
  clock?: Clock;
  topic?: string;
};

export class LiveLogClient {
  private readonly follower: LiveFollower<LiveLogSnapshotData>;
  private readonly materializer: LiveLogMaterializer;

  constructor(private readonly deps: LiveLogClientDeps) {
    this.materializer = new LiveLogMaterializer(deps);
    this.follower = new LiveFollower(deps.refetchSnapshot, this.materializer, {
      ...deps,
      label: 'live log',
    });
  }

  get writtenOffset(): number {
    return this.materializer.writtenOffset;
  }

  isReady(): boolean {
    return this.follower.isReady();
  }

  /** True while a resync is needed or in flight, including after a give-up. */
  get stale(): boolean {
    return this.follower.stale;
  }

  seed(snapshot: LiveSnapshot<LiveLogSnapshotData>): void {
    this.follower.seed(snapshot);
  }

  applyUpdate(update: LiveUpdate): void {
    this.follower.applyUpdate(update);
  }

  /** Resolves only once the follower is fresh; see `LiveFollower.refresh`. */
  refresh(): Promise<void> {
    return this.follower.refresh();
  }

  /** Triggers a resync without exposing a promise; failures follow the policy. */
  invalidate(): void {
    this.follower.invalidate();
  }

  /** Stops any resync retry loop and rejects pending refresh promises. */
  dispose(): void {
    this.follower.dispose();
  }
}

class LiveLogMaterializer implements LiveMaterializer<LiveLogSnapshotData> {
  private generation: number | undefined;
  writtenOffset = 0;

  constructor(private readonly deps: LiveLogClientDeps) {}

  seed(snapshot: LiveSnapshot<LiveLogSnapshotData>): void {
    const data = snapshot.data;
    const endOffset = data.baseOffset + byteLength(data.text);
    if (
      this.generation === snapshot.generation &&
      this.writtenOffset >= data.baseOffset &&
      this.writtenOffset <= endOffset
    ) {
      const missing = suffixFromByteOffset(data.text, this.writtenOffset - data.baseOffset);
      if (missing.length > 0) this.deps.onAppend(missing);
    } else {
      this.deps.onReset(data);
    }
    this.generation = snapshot.generation;
    this.writtenOffset = endOffset;
  }

  apply(update: LiveUpdate): LiveFollowerApplyResult {
    if (!isLiveLogDelta(update.delta)) {
      return { ok: false, reason: 'patch-failed', details: { reason: 'invalid-delta' } };
    }

    this.deps.onAppend(update.delta.chunk);
    this.writtenOffset += byteLength(update.delta.chunk);
    return { ok: true };
  }
}

function isLiveLogDelta(value: unknown): value is LiveLogDelta {
  return (
    typeof value === 'object' &&
    value !== null &&
    'chunk' in value &&
    typeof (value as { chunk: unknown }).chunk === 'string'
  );
}

const encoder = new TextEncoder();
const decoder = new TextDecoder();

function byteLength(text: string): number {
  return encoder.encode(text).byteLength;
}

function suffixFromByteOffset(text: string, offset: number): string {
  if (offset <= 0) return text;
  const bytes = encoder.encode(text);
  if (offset >= bytes.byteLength) return '';
  return decoder.decode(bytes.slice(offset));
}
