import { create } from "zustand";

import type { PaneLayout, Settings, ThemePreference } from "@shared/types";

/**
 * Settings live in main's sqlite, not in the renderer. This store is a cache
 * of them plus the write path; every mutation goes out over IPC and comes back
 * as the whole object, so two windows and the app menu cannot disagree about
 * what the current settings are.
 */
type SettingsState = {
  settings: Settings | null;
  /** False until the first read lands; the shell renders from defaults. */
  ready: boolean;
  load: () => Promise<void>;
  patch: (patch: Partial<Settings>) => Promise<void>;
  setTheme: (theme: ThemePreference) => Promise<void>;
  setLayout: (layout: Partial<PaneLayout>) => Promise<void>;
  /** Applied by the `settings.changed` subscription in `subscribeToMain`. */
  receive: (settings: Settings) => void;
};

export const useSettings = create<SettingsState>((set, get) => ({
  settings: null,
  ready: false,

  load: async () => {
    const settings = await window.hardcore.settings.get();
    set({ settings, ready: true });
  },

  patch: async (patch) => {
    // Optimistic: a switch that waits for a round trip before it moves feels
    // broken. The event that follows the write is the correction.
    const current = get().settings;
    if (current) {
      set({ settings: { ...current, ...patch } });
    }
    const settings = await window.hardcore.settings.set(patch);
    set({ settings, ready: true });
  },

  setTheme: (theme) => get().patch({ theme }),

  setLayout: (layout) => {
    const current = get().settings;
    if (!current) {
      return Promise.resolve();
    }
    return get().patch({ layout: { ...current.layout, ...layout } });
  },

  receive: (settings) => set({ settings, ready: true }),
}));
