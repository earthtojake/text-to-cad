import { createEmitter, type Unsubscribe } from '@emdash/shared';
import type { LiveLogSnapshotData, LiveSnapshot, LiveUpdate } from '../../api/channel';
import type { LiveLogDelta } from '../protocol';

/**
 * Shared retention cap for log sources and their client-side stores: keeping
 * one constant means source and client cannot drift apart.
 */
export const LIVE_LOG_DEFAULT_MAX_BUFFER_BYTES = 1024 * 1024;
const encoder = new TextEncoder();

type RetainedChunk = {
  text: string;
  bytes: number;
};

export type LiveLogSourceOptions = {
  maxBufferBytes?: number;
  generation?: number;
};

/**
 * Transport-agnostic append-only log source.
 *
 * The update envelope matches LiveStateSource, but the delta is log-specific:
 * `{ chunk: string }`. Snapshots return the retained tail plus the byte offset
 * of the first retained byte so clients can reset cheaply after gaps.
 */
export class LiveLogSource {
  private readonly emitter = createEmitter<LiveUpdate>();
  private readonly maxBufferBytes: number;
  private generation: number;
  private sequence = 0;
  private baseOffset = 0;
  private bufferedBytes = 0;
  private truncated = false;
  private chunks: RetainedChunk[] = [];

  constructor(options: LiveLogSourceOptions = {}) {
    this.maxBufferBytes = Math.max(0, options.maxBufferBytes ?? LIVE_LOG_DEFAULT_MAX_BUFFER_BYTES);
    this.generation = options.generation ?? Date.now();
  }

  append(chunk: string): void {
    if (chunk.length === 0) return;

    const retained = { text: chunk, bytes: byteLength(chunk) };
    this.chunks.push(retained);
    this.bufferedBytes += retained.bytes;
    this.evictOldChunks();

    const baseSequence = this.sequence;
    this.sequence += 1;
    const delta: LiveLogDelta = { chunk };
    this.emitter.emit({
      generation: this.generation,
      baseSequence,
      sequence: this.sequence,
      timestamp: Date.now(),
      delta,
    });
  }

  snapshot(): LiveSnapshot<LiveLogSnapshotData> {
    return {
      generation: this.generation,
      sequence: this.sequence,
      timestamp: Date.now(),
      data: {
        baseOffset: this.baseOffset,
        text: this.chunks.map((chunk) => chunk.text).join(''),
        truncated: this.truncated,
      },
    };
  }

  reseed(data?: LiveLogSnapshotData): void {
    this.generation = Date.now();
    this.sequence = 0;
    this.baseOffset = data?.baseOffset ?? 0;
    this.truncated = data?.truncated ?? false;
    this.chunks = data?.text ? [{ text: data.text, bytes: byteLength(data.text) }] : [];
    this.bufferedBytes = this.chunks.reduce((total, chunk) => total + chunk.bytes, 0);
    this.evictOldChunks();
  }

  subscribe(cb: (update: LiveUpdate) => void): Unsubscribe {
    return this.emitter.subscribe(cb);
  }

  private evictOldChunks(): void {
    while (this.chunks.length > 1 && this.bufferedBytes > this.maxBufferBytes) {
      const [removed] = this.chunks.splice(0, 1);
      if (!removed) return;
      this.baseOffset += removed.bytes;
      this.bufferedBytes -= removed.bytes;
      this.truncated = true;
    }
  }
}

function byteLength(text: string): number {
  return encoder.encode(text).byteLength;
}
