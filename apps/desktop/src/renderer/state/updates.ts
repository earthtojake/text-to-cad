import { toast } from "sonner";
import { create } from "zustand";

import type { UpdateStatus } from "@shared/ipc/app";

import { hasAnyDirtyDocument } from "./live-documents";

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
  /** `confirmed` skips the unsaved-changes ask (it is the ask's own Restart). */
  install: (confirmed?: boolean) => Promise<void>;
  /** Applied by the `app.updateStatus` subscription in `subscribeToMain`. */
  receive: (status: UpdateStatus) => void;
};

export const useUpdates = create<UpdatesState>((set, get) => {
  // A rejected IPC call is the updater being unreachable, not a state main
  // pushed: say so on the row the way a refused answer would, and in a toast.
  // Electron wraps a handler's error as "Error invoking remote method 'x': Error:
  // y"; only y is for the person. The sentence is on the row, which stays, and
  // the toast is just the headline, so it is not printed twice.
  const fail = (error: unknown) => {
    const raw = error instanceof Error ? error.message : String(error);
    const message = raw.match(/^Error invoking remote method '[^']*': (?:\w*Error: )?([^\n]*)/)?.[1]?.trim() || raw;
    set({ status: { state: "error", message } });
    toast.error("Could not reach the updater");
  };

  // `action` answers with the status, except Restart, which answers with
  // nothing: the app is about to quit, and a refused install arrives as a push.
  const run = async (action: () => Promise<UpdateStatus | void>) => {
    set({ busy: true });
    try {
      const status = await action();
      if (status) {
        set({ status });
      }
    } catch (error) {
      fail(error);
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
      try {
        set({ status: await window.textToCad.app.updateStatus() });
      } catch (error) {
        fail(error);
      }
    },

    check: () => run(() => window.textToCad.app.checkForUpdates()),

    // Resolves when the download finishes; the progress in between arrives as
    // pushes, which is why this store is not just a promise.
    download: () => run(() => window.textToCad.app.downloadUpdate()),

    // Through `run` like the others. `busy` only spans the round trip, and main
    // answers as soon as it has asked Electron to quit, so the row is held by
    // `installing` — pushed by main, and set here for the case where the answer
    // wins the race. A refusal that has already been pushed is not overwritten.
    //
    // An update's quit skips the unsaved-draft ask on purpose (a Cancel there would strand the
    // restart: `src/main/quitting.ts`), so the ask happens here, before the install is requested:
    // with an unsaved document open, Restart asks once and does nothing until it is confirmed.
    install: async (confirmed = false) => {
      if (!confirmed && hasAnyDirtyDocument()) {
        toast("Restart now and discard unsaved changes?", {
          id: "update-restart-discards",
          action: { label: "Restart", onClick: () => void get().install(true) },
          cancel: { label: "Not now", onClick: () => {} },
        });
        return;
      }
      await run(() => window.textToCad.app.installUpdate());
      const { status } = get();
      if (status.state === "downloaded" || (status.state === "error" && status.version !== undefined)) {
        set({ status: { state: "installing", version: status.version } });
      }
    },

    receive: (status) => set({ status }),
  };
});
