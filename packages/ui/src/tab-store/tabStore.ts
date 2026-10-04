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
  /** The file views, by `[root id, file path, renderer id]`. */
  files: {
    read(rootId: string, path: string, rendererId: string): JsonValue | undefined;
    /** Writing puts the file last; the oldest goes once there are more than `TAB_FILE_LIMIT` (one). */
    write(rootId: string, path: string, rendererId: string, view: JsonValue): void;
    remove(rootId: string, path: string, rendererId: string): void;
    /**
     * Keep the view of the file on screen — `path` under `rootId`, whichever renderer wrote it — and
     * drop every other; `null` is no file on screen (a home), and drops them all. The settings stay.
     */
    retain(rootId: string, path: string | null): void;
    /** One root's views under `FileViewerState.renderers`' keys, `[file path, renderer id]`; stable per snapshot. */
    forRoot(rootId: string): Record<string, JsonValue>;
    /**
     * A view's `renderers` map came back changed: write what differs from `baseline` — never what a
     * stale view merely still holds — and drop what it dropped.
     */
    merge(rootId: string, baseline: Record<string, JsonValue>, next: Record<string, JsonValue>): void;
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
  let rootViews: { record: TabRecord; rootId: string; views: Record<string, JsonValue> } | null = null;
  const forRoot = (rootId: string) => {
    if (rootViews?.record === record && rootViews.rootId === rootId) return rootViews.views;
    const views: Record<string, JsonValue> = {};
    for (const [key, view] of Object.entries(record.files)) {
      const parsed = parseTabFileKey(key);
      if (parsed?.rootId === rootId) views[JSON.stringify([parsed.path, parsed.rendererId])] = view;
    }
    rootViews = { record, rootId, views };
    return views;
  };
  const write = (rootId: string, path: string, rendererId: string, view: JsonValue) =>
    commit({ ...record, files: writeTabFile(record.files, tabFileKey(rootId, path, rendererId), view) });
  const remove = (rootId: string, path: string, rendererId: string) => {
    const key = tabFileKey(rootId, path, rendererId);
    if (!(key in record.files)) return;
    const files = { ...record.files };
    delete files[key];
    commit({ ...record, files });
  };
  const retain = (rootId: string, path: string | null) => {
    const files: TabRecord['files'] = {};
    for (const [key, view] of Object.entries(record.files)) {
      const parsed = parseTabFileKey(key);
      if (path !== null && parsed?.rootId === rootId && parsed.path === path) files[key] = view;
    }
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
      read: (rootId, path, rendererId) => record.files[tabFileKey(rootId, path, rendererId)],
      write, remove, retain, forRoot,
      merge(rootId, baseline, next) {
        for (const key of new Set([...Object.keys(baseline), ...Object.keys(next)])) {
          if (JSON.stringify(baseline[key]) === JSON.stringify(next[key])) continue;
          const parsed = parsePairKey(key);
          if (!parsed) continue;
          if (key in next) write(rootId, parsed.path, parsed.rendererId, next[key]!); else remove(rootId, parsed.path, parsed.rendererId);
        }
      },
    },
  };
}

function safeRead(storage: TabRecordStorage): unknown {
  try { return storage.read(); } catch { return undefined; }
}

function parsePairKey(key: string): { path: string; rendererId: string } | null {
  try {
    const parsed: unknown = JSON.parse(key);
    return Array.isArray(parsed) && parsed.length === 2 && parsed.every(part => typeof part === 'string') ? { path: parsed[0], rendererId: parsed[1] } : null;
  } catch { return null; }
}

/** A store over nothing but memory, for a host with no storage of its own and for tests. */
export function memoryTabRecord(initial?: unknown): TabRecordStorage {
  let stored: unknown = initial;
  return { read: () => stored, write(record) { stored = JSON.parse(JSON.stringify(record)); } };
}
