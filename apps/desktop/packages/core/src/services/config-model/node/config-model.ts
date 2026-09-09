import { watch, type FSWatcher } from 'node:fs';
import { readFile } from 'node:fs/promises';
import path from 'node:path';

/**
 * The result of leniently reading a config file: a missing file yields the parser's
 * empty default with no error, a present-but-unparseable file yields the default
 * plus `parseError: true`. Lenient by design — a broken config must never block the
 * caller's flow; it degrades and surfaces the error as a flag.
 */
export type ConfigFileEntry<T> = {
  data: T;
  parseError: boolean;
};

/**
 * Reads one config file leniently. `parse` receives the raw content and reports
 * success plus the (defaulted) data — the shape `parseEmdashConfig` and friends
 * already produce.
 */
export async function readConfigFile<T>(
  filePath: string,
  parse: (content: string) => { success: boolean; data: T }
): Promise<ConfigFileEntry<T>> {
  let content: string;
  try {
    content = await readFile(filePath, 'utf8');
  } catch {
    const empty = parse('{}');
    return { data: empty.data, parseError: false };
  }
  const parsed = parse(content);
  return { data: parsed.data, parseError: !parsed.success };
}

export type ConfigModelOptions<T> = {
  /** Loads the entry for a key; `source` is caller context (typically a path). */
  read: (key: string, source: string) => Promise<T>;
  /**
   * Fired after a refresh lands an entry that differs (deep-equality via JSON) from
   * the cached one — including the first load. Never fired after dispose. `source`
   * is the refresh's caller context (typically the file's location).
   */
  onChanged?: (key: string, entry: T, previous: T | undefined, source: string) => void;
};

/**
 * A keyed live model of config entries (spec: activation-scripts-via-terminals,
 * shared config model): cached entries readable synchronously off any blocking
 * path, coalesced refreshes per key, and change callbacks for the host's side
 * effects. Hosts drive refreshes from boot walks and watcher events; this class
 * owns only the cache discipline.
 */
export class ConfigModel<T> {
  private readonly entries = new Map<string, T>();
  private readonly reads = new Map<string, Promise<T>>();
  private readonly revisions = new Map<string, number>();
  private readonly options: ConfigModelOptions<T>;
  private disposed = false;

  constructor(options: ConfigModelOptions<T>) {
    this.options = options;
  }

  get(key: string): T | undefined {
    return this.entries.get(key);
  }

  /** Seeds a known fallback without reading or firing change side effects. */
  seed(key: string, entry: T): void {
    if (!this.disposed && !this.entries.has(key)) this.entries.set(key, entry);
  }

  /** Coalesced: concurrent refreshes of one key share a single read. */
  refresh(key: string, source: string): Promise<T> {
    const inFlight = this.reads.get(key);
    if (inFlight) return inFlight;
    const revision = this.revisions.get(key) ?? 0;
    const read = (async () => {
      const entry = await this.options.read(key, source);
      // Reads are often fire-and-forget; a disposed model must never store or
      // fire callbacks into a torn-down host. A delete also invalidates any read
      // already in flight so removal cannot resurrect a stale model entry.
      if (this.disposed || (this.revisions.get(key) ?? 0) !== revision) return entry;
      const previous = this.entries.get(key);
      this.entries.set(key, entry);
      const changed = previous === undefined || JSON.stringify(previous) !== JSON.stringify(entry);
      if (changed) this.options.onChanged?.(key, entry, previous, source);
      return entry;
    })().finally(() => {
      if (this.reads.get(key) === read) this.reads.delete(key);
    });
    this.reads.set(key, read);
    return read;
  }

  delete(key: string): void {
    this.entries.delete(key);
    this.revisions.set(key, (this.revisions.get(key) ?? 0) + 1);
    this.reads.delete(key);
  }

  dispose(): void {
    this.disposed = true;
    this.entries.clear();
  }
}

export type ConfigFileWatcher = {
  dispose(): void;
};

/**
 * The watch-refresh half of the config-model pattern for a single standalone file
 * (e.g. a host settings file): watches the containing directory so create/delete of
 * the file itself is seen, debounces bursts, and calls `onChange` once per settle.
 * The directory must exist; the file need not.
 */
export function watchConfigFile(
  filePath: string,
  onChange: () => void,
  options?: { debounceMs?: number }
): ConfigFileWatcher {
  const debounceMs = options?.debounceMs ?? 100;
  const fileName = path.basename(filePath);
  let timer: NodeJS.Timeout | null = null;
  let disposed = false;
  const watcher: FSWatcher = watch(path.dirname(filePath), (_event, changed) => {
    if (disposed) return;
    if (changed !== null && changed !== fileName) return;
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      timer = null;
      if (!disposed) onChange();
    }, debounceMs);
  });
  return {
    dispose() {
      disposed = true;
      if (timer) clearTimeout(timer);
      watcher.close();
    },
  };
}
