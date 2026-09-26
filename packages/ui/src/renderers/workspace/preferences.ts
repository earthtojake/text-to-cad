import { ORBIT_STORAGE_KEY, readOrbit, writeOrbit } from '../kit/tools/fullscreen/orbitPreferences.js';
import { TOOL_STACK_WIDTH_STORAGE_KEY, readToolStackWidth, writeToolStackWidth } from '../kit/tools/toolStackWidth.js';


export interface CadPreferences {
  orbit?: { speed: number };
  /** The tool stack's width in CSS pixels: every panel under the strip, in every file (`kit/tools/toolStackWidth.js`). */
  toolStackWidth?: number;
}
export interface CadPreferenceSource {
  getSnapshot(): CadPreferences;
  subscribe(listener: () => void): () => void;
  update(patch: Partial<CadPreferences>): void;
}
/** Host storage is supplied explicitly; construction never discovers browser storage. */
export function createCadPreferences({ initial = {}, onChange }: {
  initial?: CadPreferences;
  onChange?: (preferences: CadPreferences) => void;
} = {}): CadPreferenceSource {
  let current = initial;
  const listeners = new Set<() => void>();
  return {
    getSnapshot: () => current,
    subscribe(listener) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    update(patch) {
      const next = { ...current, ...patch };
      if (JSON.stringify(next) === JSON.stringify(current)) return;
      current = next;
      onChange?.(next);
      for (const listener of listeners) listener();
    }
  };
}

/** Preferences kept in a host's `Storage`, which other windows of the same app may share. */
export interface StoredCadPreferences extends CadPreferenceSource {
  /**
   * Another window changed `key` in the same storage (a `storage` event's key; `null` is a clear):
   * the preferences stored under it are read again. Any other key is someone else's.
   */
  storageChanged(key: string | null): void;
}

/**
 * The viewer preferences as the host stores them: the one owner of their storage format. The app
 * hands over its `Storage` and forwards its `storage` events; what is written, and under which key,
 * is this module's. Construction reads the storage and nothing else.
 */
export function createStoredCadPreferences(storage: Storage): StoredCadPreferences {
  const read = (): CadPreferences => ({ orbit: readOrbit(storage), toolStackWidth: readToolStackWidth(storage) });
  let syncing = false;
  let baseline = read();
  const source = createCadPreferences({ initial: baseline, onChange(preferences) {
    // A preference read back from storage is not written again.
    if (!syncing && preferences.orbit && JSON.stringify(preferences.orbit) !== JSON.stringify(baseline.orbit)) writeOrbit(storage, preferences.orbit);
    if (!syncing && preferences.toolStackWidth !== undefined && preferences.toolStackWidth !== baseline.toolStackWidth) writeToolStackWidth(storage, preferences.toolStackWidth);
    baseline = preferences;
  } });
  return {
    ...source,
    storageChanged(key) {
      if (key !== null && key !== ORBIT_STORAGE_KEY && key !== TOOL_STACK_WIDTH_STORAGE_KEY) return;
      syncing = true;
      try { source.update(read()); } finally { syncing = false; }
    },
  };
}
