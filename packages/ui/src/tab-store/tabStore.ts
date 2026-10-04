import type { JsonValue } from '../file-viewer/types.js';
import { normalizeTabSettings, parseTabFileKey, readTabRecord, tabFileKey, writeTabFile, type TabRecord, type TabSettings } from './tabRecord.js';

/**
 * How a host keeps one tab's record: read whole and synchronously (so the first paint and every
 * restore are synchronous), written whole. The web hands over `sessionStorage`; the desktop its
 * per-tab store. What is read is `unknown` — the store normalizes it — and what is written is
 * the record, already normalized. A store that cannot read answers `undefined`; one that cannot
 * write throws or not as it likes: a blocked store never stops the viewer.
 */
export interface TabRecordStorage {
  read(): unknown;
  write(record: TabRecord): void;
}

/** A store of one kind of state: a snapshot to subscribe to, and a patch to apply. */
export interface SettingsSource<T> {
  getSnapshot(): T;
  subscribe(listener: () => void): () => void;
  update(patch: Partial<T>): void;
}

export interface TabStore {
  /** The whole record, immutable: a new object after every change. */
  getSnapshot(): TabRecord;
  subscribe(listener: () => void): () => void;
  /** The tab-wide settings; what renderers read as their `preferences`. */
  settings: SettingsSource<TabSettings>;
  /** The file views, by `[absolute file path, renderer id]` — `FileViewerState.renderers`' keys. */
  files: {
    read(path: string, rendererId: string): JsonValue | undefined;
    /** Writing puts the file last; the oldest goes once there are more than `TAB_FILE_LIMIT` (one). */
    write(path: string, rendererId: string, view: JsonValue): void;
    remove(path: string, rendererId: string): void;
    /**
     * Keep the view of the file on screen, whichever renderer wrote it, and drop every other;
     * `null` is no file on screen (the home), and drops them all. The settings stay.
     */
    retain(path: string | null): void;
    /** Every view, under `FileViewerState.renderers`' keys; stable per snapshot. */
    all(): Record<string, JsonValue>;
    /**
     * A view's `renderers` map came back changed: write what differs from `baseline` — never what a
     * stale view merely still holds — and drop what it dropped.
     */
    merge(baseline: Record<string, JsonValue>, next: Record<string, JsonValue>): void;
  };
}

/**
 * The tab's one store. Construction reads the storage once and nothing else; every change is
 * normalized, published to subscribers and written through, synchronously.
 */
export function createTabStore(storage: TabRecordStorage): TabStore {
  let record: TabRecord = readTabRecord(safeRead(storage));
  const listeners = new Set<() => void>();
  const commit = (next: TabRecord) => {
    if (JSON.stringify(next) === JSON.stringify(record)) return;
    record = next;
    try { storage.write(record); } catch { /* A blocked store does not prevent viewing. */ }
    for (const listener of listeners) listener();
  };
  const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };
  const write = (path: string, rendererId: string, view: JsonValue) =>
    commit({ ...record, files: writeTabFile(record.files, tabFileKey(path, rendererId), view) });
  const remove = (path: string, rendererId: string) => {
    const key = tabFileKey(path, rendererId);
    if (!(key in record.files)) return;
    const files = { ...record.files };
    delete files[key];
    commit({ ...record, files });
  };
  const retain = (path: string | null) => {
    const files: TabRecord['files'] = {};
    for (const [key, view] of Object.entries(record.files)) if (path !== null && parseTabFileKey(key)?.path === path) files[key] = view;
    if (Object.keys(files).length !== Object.keys(record.files).length) commit({ ...record, files });
  };
  return {
    getSnapshot: () => record,
    subscribe,
    settings: {
      getSnapshot: () => record.settings,
      subscribe,
      update(patch) { commit({ ...record, settings: normalizeTabSettings({ ...record.settings, ...patch }) }); },
    },
    files: {
      read: (path, rendererId) => record.files[tabFileKey(path, rendererId)],
      write, remove, retain,
      all: () => record.files,
      merge(baseline, next) {
        for (const key of new Set([...Object.keys(baseline), ...Object.keys(next)])) {
          if (JSON.stringify(baseline[key]) === JSON.stringify(next[key])) continue;
          const parsed = parseTabFileKey(key);
          if (!parsed) continue;
          if (key in next) write(parsed.path, parsed.rendererId, next[key]!); else remove(parsed.path, parsed.rendererId);
        }
      },
    },
  };
}

function safeRead(storage: TabRecordStorage): unknown {
  try { return storage.read(); } catch { return undefined; }
}

/** A store over nothing but memory, for a host with no storage of its own and for tests. */
export function memoryTabRecord(initial?: unknown): TabRecordStorage {
  let stored: unknown = initial;
  return { read: () => stored, write(record) { stored = JSON.parse(JSON.stringify(record)); } };
}
