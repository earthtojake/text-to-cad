import { create } from "zustand";

import type { RuntimeStatus } from "@shared/ipc/runtime";

/**
 * The CAD runtime's state, mirrored from main (plan §8, as revised: the
 * runtime ships inside the app, so this is a status, never a progress bar).
 * Read by the block in Settings › About & Updates and by a CAD tab that has
 * no viewer to show.
 */
type RuntimeState = {
  status: RuntimeStatus | null;
  busy: boolean;
  load: () => Promise<void>;
  /** Forget the probe and look again. */
  repair: () => Promise<void>;
  receive: (status: RuntimeStatus) => void;
};

export const useRuntime = create<RuntimeState>((set) => ({
  status: null,
  busy: false,

  load: async () => {
    set({ status: await window.hardcore.runtime.status() });
  },

  repair: async () => {
    set({ busy: true });
    try {
      set({ status: await window.hardcore.runtime.repair() });
    } finally {
      set({ busy: false });
    }
  },

  receive: (status) => set({ status }),
}));
