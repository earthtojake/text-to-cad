import type { Unsubscribe } from '@emdash/shared';
import type { LiveLogSnapshotData } from '../../api/channel';
import { LIVE_LOG_DEFAULT_MAX_BUFFER_BYTES } from './source';

/**
 * Guard against pathological single lines (e.g. progress bars rewriting one
 * line for hours): stored lines are hard-wrapped at this length so per-line
 * work downstream (rendering, width measurement) stays bounded.
 */
const DEFAULT_MAX_LINE_LENGTH = 4_096;

export type LineLogStoreOptions = {
  /** Byte cap mirrored from the source; defaults to the shared LiveLogSource cap. */
  maxBufferBytes?: number;
  /** Hard-wrap threshold for a single stored line, in UTF-16 units. */
  maxLineLength?: number;
  /**
   * Scheduler for coalesced flushes. Defaults to requestAnimationFrame when
   * available (renderer) and a 16 ms timeout otherwise. Injectable for tests.
   */
  scheduleFlush?: (flush: () => void) => void;
};

/**
 * Line-structured client log store with a mirrored byte cap and
 * frame-coalesced notifications.
 *
 * - `append` is O(chunk): only the new chunk is split; the partial last line
 *   is continued across chunk boundaries; completed `\r\n` line endings are
 *   normalized.
 * - Retention mirrors the source's byte cap by evicting whole oldest lines and
 *   raising a client truncation flag.
 * - Burst appends are batched: subscribers are notified at most once per
 *   scheduled flush (one animation frame by default).
 */
export type LineLogStore = {
  reset(data: LiveLogSnapshotData): void;
  append(chunk: string): void;
  /** Compat accessor: flushes pending appends and joins lines with `\n`. */
  text(): string;
  /** The retained lines. Live array reference — treat as immutable. */
  lines(): readonly string[];
  /** True when either the source snapshot or client eviction dropped output. */
  truncated(): boolean;
  /** Monotonic counter, bumped once per applied flush/reset. */
  version(): number;
  onFlush(listener: () => void): Unsubscribe;
};

const encoder = new TextEncoder();

export function createLineLogStore(options: LineLogStoreOptions = {}): LineLogStore {
  const maxBufferBytes = Math.max(0, options.maxBufferBytes ?? LIVE_LOG_DEFAULT_MAX_BUFFER_BYTES);
  const maxLineLength = Math.max(1, options.maxLineLength ?? DEFAULT_MAX_LINE_LENGTH);
  const scheduleFlush = options.scheduleFlush ?? defaultScheduleFlush;

  let lines: string[] = [''];
  let lineBytes: number[] = [0];
  let totalBytes = 0;
  let sourceTruncated = false;
  let clientEvicted = false;
  let storeVersion = 0;

  let pendingChunks: string[] = [];
  let flushScheduled = false;
  const listeners = new Set<() => void>();

  const setTail = (value: string): void => {
    const bytes = byteLength(value);
    totalBytes += bytes - lineBytes[lineBytes.length - 1]!;
    lines[lines.length - 1] = value;
    lineBytes[lineBytes.length - 1] = bytes;
  };

  const pushLine = (value: string): void => {
    lines.push('');
    lineBytes.push(0);
    if (value) setTail(value);
  };

  /** Append text (no newlines) to the tail line, hard-wrapping as needed. */
  const appendToTail = (segment: string): void => {
    if (!segment) return;
    let tail = lines[lines.length - 1]! + segment;
    while (tail.length > maxLineLength) {
      setTail(tail.slice(0, maxLineLength));
      tail = tail.slice(maxLineLength);
      pushLine('');
    }
    setTail(tail);
  };

  /** Terminate the tail line (strip one trailing `\r` from a CRLF ending). */
  const completeTailLine = (): void => {
    const tail = lines[lines.length - 1]!;
    if (tail.endsWith('\r')) setTail(tail.slice(0, -1));
    pushLine('');
  };

  const evict = (): void => {
    while (lines.length > 1 && totalBytes > maxBufferBytes) {
      lines.shift();
      totalBytes -= lineBytes.shift() ?? 0;
      clientEvicted = true;
    }
  };

  const applyChunk = (chunk: string): void => {
    const parts = chunk.split('\n');
    appendToTail(parts[0]!);
    for (let i = 1; i < parts.length; i += 1) {
      completeTailLine();
      appendToTail(parts[i]!);
    }
    evict();
  };

  const notify = (): void => {
    storeVersion += 1;
    for (const listener of listeners) listener();
  };

  const flushNow = (): void => {
    if (pendingChunks.length === 0) return;
    const chunks = pendingChunks;
    pendingChunks = [];
    for (const chunk of chunks) applyChunk(chunk);
    notify();
  };

  return {
    reset(data) {
      pendingChunks = [];
      lines = [''];
      lineBytes = [0];
      totalBytes = 0;
      sourceTruncated = data.truncated;
      clientEvicted = false;
      applyChunk(data.text);
      notify();
    },
    append(chunk) {
      if (!chunk) return;
      pendingChunks.push(chunk);
      if (flushScheduled) return;
      flushScheduled = true;
      scheduleFlush(() => {
        flushScheduled = false;
        flushNow();
      });
    },
    text() {
      flushNow();
      return lines.join('\n');
    },
    lines() {
      return lines;
    },
    truncated() {
      return sourceTruncated || clientEvicted;
    },
    version() {
      return storeVersion;
    },
    onFlush(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

function defaultScheduleFlush(flush: () => void): void {
  const raf = (globalThis as { requestAnimationFrame?: (cb: () => void) => unknown })
    .requestAnimationFrame;
  if (typeof raf === 'function') {
    raf(() => flush());
    return;
  }
  setTimeout(flush, 16);
}

function byteLength(text: string): number {
  return encoder.encode(text).byteLength;
}
