/**
 * Handlers for the `app.*` branch's updater channels (P8).
 *
 * The counterpart to `src/shared/ipc/app.ts`: one file, spread into the handler
 * tree in `./index.ts`, so the phase that owns the updater owns its IPC too and
 * `index.ts` gains a line rather than a section.
 */
import { checkForUpdates, downloadUpdate, installUpdate, updateStatus } from "../updater";

export const appHandlers = {
  updateStatus: () => updateStatus(),
  checkForUpdates: () => checkForUpdates(),
  downloadUpdate: () => downloadUpdate(),
  // Returns before the app is gone: `quitAndInstall` unwinds asynchronously,
  // and the renderer's promise resolving is what tells it the request landed.
  installUpdate: () => installUpdate(),
};
