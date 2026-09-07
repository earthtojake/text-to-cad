import { create } from "zustand";

import type { PluginStatus } from "@shared/ipc/plugins";

/**
 * The bundled plugin's state per agent (plan §8). Two pages read it — the
 * Agents drawer's Plugins block and the CAD Runtime page's per-agent rows — so
 * it is a store rather than a fetch inside a component, and both show the same
 * answer after an install.
 *
 * Main answers `not-installed` for everything until P5 lands; the shape is
 * final, so nothing here changes when it does.
 */
type PluginsState = {
  /** Keyed by agent id. */
  statuses: Record<string, PluginStatus>;
  /** The agent whose install is in flight, if any. */
  installing: string | null;
  load: () => Promise<void>;
  install: (agentId: string) => Promise<void>;
  receive: (statuses: PluginStatus[]) => void;
};

const byAgent = (statuses: PluginStatus[]) =>
  Object.fromEntries(statuses.map((status) => [status.agentId, status]));

export const usePlugins = create<PluginsState>((set) => ({
  statuses: {},
  installing: null,

  load: async () => {
    set({ statuses: byAgent(await window.hardcore.plugins.statusAll()) });
  },

  install: async (agentId) => {
    set({ installing: agentId });
    try {
      const status = await window.hardcore.plugins.install({ agentId });
      set((state) => ({ statuses: { ...state.statuses, [agentId]: status } }));
    } finally {
      set({ installing: null });
    }
  },

  receive: (statuses) => set({ statuses: byAgent(statuses) }),
}));
