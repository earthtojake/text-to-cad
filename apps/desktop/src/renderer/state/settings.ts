import { toast } from "sonner";
import { create } from "zustand";

import {
  SidebarSettingsSchema,
  type PaneLayout,
  type Settings,
  type SidebarSettings,
  type ThemePreference,
} from "@shared/types";

/**
 * Settings live in main's sqlite, not in the renderer. This store is a cache
 * of them plus the write path; every mutation goes out over IPC and comes back
 * as the whole object, so two windows and the app menu agree about what the
 * settings are once no write of this window is still in flight.
 *
 * While one is, this window's optimistic value for that key wins over anything
 * main reports (`pending`): an older reply or a `settings.changed` event must
 * not put back a key that a newer write already moved. A `layout`, `sidebar`
 * or `agentOverrides` write carries the whole object (the IPC patch is only
 * top-level partial), so `setLayout`/`setSidebar` build it from that same
 * optimistic state rather than from a copy an old reply just reverted.
 *
 * A write main refuses or fails comes back as no reply at all. The catch then
 * rolls back each key this write still owns to what main last reported (a key
 * a newer write owns keeps that write's value) and toasts "Could not save the
 * setting" with main's sentence.
 */
type Pending = { id: number; value: unknown; base: unknown };

/** The newest in-flight write per key, and the last value main reported for it. */
const pending = new Map<keyof Settings, Pending>();
let writeSeq = 0;

/** Forget every in-flight write: the module's maps outlive a test's store reset. */
export function resetForTests(): void {
  pending.clear();
  writeSeq = 0;
}

/** What main reported, with this window's in-flight writes laid over it. */
function overlay(reported: Settings): Settings {
  if (pending.size === 0) {
    return reported;
  }
  const out: Record<string, unknown> = { ...reported };
  for (const [key, entry] of pending) {
    entry.base = out[key];
    out[key] = entry.value;
  }
  return out as Settings;
}

type SettingsState = {
  settings: Settings | null;
  /** False until the first read lands; the shell renders from defaults. */
  ready: boolean;
  load: () => Promise<void>;
  patch: (patch: Partial<Settings>) => Promise<void>;
  setTheme: (theme: ThemePreference) => Promise<void>;
  setLayout: (layout: Partial<PaneLayout>) => Promise<void>;
  /** The sidebar's filter menu and its collapsed sections. */
  setSidebar: (sidebar: Partial<SidebarSettings>) => Promise<void>;
  /** Applied by the `settings.changed` subscription in `subscribeToMain`. */
  receive: (settings: Settings) => void;
};

export const useSettings = create<SettingsState>((set, get) => ({
  settings: null,
  ready: false,

  load: async () => {
    const settings = await window.textToCad.settings.get();
    set({ settings: overlay(settings), ready: true });
  },

  patch: async (patch) => {
    // Optimistic: a switch that waits for a round trip before it moves feels
    // broken. The reply is the correction — and for a write main refuses or
    // fails there is no reply, so the catch puts back what main last said.
    const id = ++writeSeq;
    const keys = Object.keys(patch) as (keyof Settings)[];
    const current = get().settings;
    if (current) {
      for (const key of keys) {
        pending.set(key, { id, value: patch[key], base: pending.get(key)?.base ?? current[key] });
      }
      set({ settings: { ...current, ...patch } });
    }
    try {
      const settings = await window.textToCad.settings.set(patch);
      for (const key of keys) {
        if (pending.get(key)?.id === id) {
          pending.delete(key);
        }
      }
      set({ settings: overlay(settings), ready: true });
    } catch (error) {
      // A key a newer write owns stays with that write.
      const reverted: Record<string, unknown> = {};
      for (const key of keys) {
        const entry = pending.get(key);
        if (entry?.id === id) {
          pending.delete(key);
          reverted[key] = entry.base;
        }
      }
      set((state) => ({ settings: state.settings ? { ...state.settings, ...reverted } : state.settings }));
      toast.error("Could not save the setting", { description: error instanceof Error ? error.message : String(error) });
    }
  },

  setTheme: (theme) => get().patch({ theme }),

  setLayout: (layout) => {
    const current = get().settings;
    if (!current) {
      return Promise.resolve();
    }
    return get().patch({ layout: { ...current.layout, ...layout } });
  },

  setSidebar: (sidebar) => {
    const current = get().settings;
    if (!current) {
      return Promise.resolve();
    }
    return get().patch({ sidebar: { ...current.sidebar, ...sidebar } });
  },

  receive: (settings) => set({ settings: overlay(settings), ready: true }),
}));

/**
 * The sidebar's settings, defaulted.
 *
 * The shell renders before the first read lands (`ready`), and the sidebar is
 * the first thing on screen — so the answer for "not loaded yet" is the same
 * all-defaults object the schema produces rather than a null the components
 * would each have to guard. Frozen once, because it is compared by identity:
 * a fresh object per call would re-render every row on every keystroke.
 */
const DEFAULT_SIDEBAR: SidebarSettings = SidebarSettingsSchema.parse({});

export function useSidebarSettings(): SidebarSettings {
  return useSettings((state) => state.settings?.sidebar ?? DEFAULT_SIDEBAR);
}
