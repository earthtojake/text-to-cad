import { create } from "zustand";

import type { RuntimeStatus } from "@shared/ipc/runtime";

/**
 * The CAD runtime's state, mirrored from main (plan §8).
 *
 * `progress` is the tail of the provisioning log rather than the whole of it:
 * the page shows what is happening now, and P5's installer writes the full log
 * to disk for the case where that is not enough.
 */
type RuntimeState = {
  status: RuntimeStatus;
  /** 0–100 while installing. */
  percent: number | null;
  /** The most recent progress line. */
  progress: string | null;
  busy: boolean;
  load: () => Promise<void>;
  repair: () => Promise<void>;
  receive: (status: RuntimeStatus, message?: string, percent?: number) => void;
};

/** What the page renders before main has answered. */
const UNKNOWN: RuntimeStatus = {
  state: "missing",
  python: null,
  cadgenVersion: null,
  viewerBuilt: false,
  overridden: false,
  log: null,
};

export const useRuntime = create<RuntimeState>((set) => ({
  status: UNKNOWN,
  percent: null,
  progress: null,
  busy: false,

  load: async () => {
    set({ status: await window.hardcore.runtime.status() });
  },

  repair: async () => {
    set({ busy: true, progress: null, percent: null });
    try {
      set({ status: await window.hardcore.runtime.repair() });
    } finally {
      set({ busy: false });
    }
  },

  receive: (status, message, percent) =>
    set({
      status,
      progress: message ?? null,
      percent: percent ?? null,
    }),
}));
