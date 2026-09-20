
export interface CadPreferences {
  orbit?: { speed: number };
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

export const CAD_LEGACY_PREFERENCE_KEYS = Object.freeze({
  directory: 'cad-viewer:directory-session:v1'
});
