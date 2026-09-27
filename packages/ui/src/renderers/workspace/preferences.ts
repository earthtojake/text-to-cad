import { normalizeTabSettings, type TabSettings } from '../../tab-store/tabRecord.js';
import type { SettingsSource } from '../../tab-store/tabStore.js';

/**
 * What the viewer renderers read as their preferences: the tab's settings (`@hardcore/ui/tab-store`).
 * A host hands every renderer its tab store's `settings`; a renderer built without one gets an
 * in-memory source with the defaults, which is what a test or a headless host wants.
 */
export type CadPreferences = TabSettings;
export type CadPreferenceSource = SettingsSource<TabSettings>;
export type { ToolStackLayout } from '../../tab-store/tabRecord.js';

/** An in-memory source: the defaults, or `initial` normalized, and an optional change callback. */
export function createCadPreferences({ initial = {}, onChange }: {
  initial?: Partial<CadPreferences>;
  onChange?: (preferences: CadPreferences) => void;
} = {}): CadPreferenceSource {
  let current = normalizeTabSettings(initial);
  const listeners = new Set<() => void>();
  return {
    getSnapshot: () => current,
    subscribe(listener) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    update(patch) {
      const next = normalizeTabSettings({ ...current, ...patch });
      if (JSON.stringify(next) === JSON.stringify(current)) return;
      current = next;
      onChange?.(next);
      for (const listener of listeners) listener();
    }
  };
}
