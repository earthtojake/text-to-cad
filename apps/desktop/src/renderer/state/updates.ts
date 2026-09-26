import { create } from "zustand";

import type { UpdateStatus } from "@shared/ipc/app";

/**
 * The updater's state, mirrored from main (P8).
 *
 * Main is the authority: it holds the electron-updater instance, checks on a
 * timer, and pushes `app.updateStatus` on every transition. This store is the
 * cache the About page renders, plus the three verbs. `busy` covers the gap
 * between pressing a button and the first push, which is otherwise a button
 * that looks like it did nothing.
 */
type UpdatesState = {
  status: UpdateStatus;
  busy: boolean;
  load: () => Promise<void>;
  check: () => Promise<void>;
  download: () => Promise<void>;
  install: () => Promise<void>;
  /** Applied by the `app.updateStatus` subscription in `subscribeToMain`. */
  receive: (status: UpdateStatus) => void;
};

export const useUpdates = create<UpdatesState>((set) => {
  const run = async (action: () => Promise<UpdateStatus>) => {
    set({ busy: true });
    try {
      set({ status: await action() });
    } finally {
      set({ busy: false });
    }
  };

  return {
    // Development builds never leave this state, which is the honest answer
    // there: there is no feed to ask.
    status: { state: "unsupported" },
    busy: false,

    load: async () => {
      set({ status: await window.hardcore.app.updateStatus() });
    },

    check: () => run(() => window.hardcore.app.checkForUpdates()),

    // Resolves when the download finishes; the progress in between arrives as
    // pushes, which is why this store is not just a promise.
    download: () => run(() => window.hardcore.app.downloadUpdate()),

    install: () => window.hardcore.app.installUpdate(),

    receive: (status) => set({ status }),
  };
});
