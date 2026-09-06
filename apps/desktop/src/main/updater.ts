/**
 * Auto-update against the GitHub Releases the repository already publishes
 * (`release-publish.yml`; plan §11). The feed is configured in
 * `electron-builder.yml` and baked into the build, so nothing is read from the
 * network before the app knows where to look.
 *
 * A no-op in development: `electron-updater` has no `app-update.yml` to read
 * there, and an unsigned dev build must never be told to replace itself.
 */
import { app } from "electron";
import electronUpdater from "electron-updater";

import { broadcast } from "./ipc";
import { settings } from "./db/repositories";

const { autoUpdater } = electronUpdater;

/**
 * Wire the updater and, unless the user turned it off, check once at launch.
 * P8 adds the manual "Check for updates" path and the restart-to-install
 * prompt; the events are already forwarded so About & Updates can render them.
 */
export function initUpdater() {
  if (!app.isPackaged) {
    return;
  }

  autoUpdater.autoDownload = true;
  // Installing an update during quit is the user's call, not ours.
  autoUpdater.autoInstallOnAppQuit = false;
  autoUpdater.logger = null;

  autoUpdater.on("checking-for-update", () => broadcast("updater.status", { state: "checking" }));
  autoUpdater.on("update-available", (info) =>
    broadcast("updater.status", { state: "available", version: info.version }),
  );
  autoUpdater.on("update-not-available", () => broadcast("updater.status", { state: "idle" }));
  autoUpdater.on("download-progress", (progress) =>
    broadcast("updater.status", { state: "downloading", percent: progress.percent }),
  );
  autoUpdater.on("update-downloaded", (info) =>
    broadcast("updater.status", { state: "ready", version: info.version }),
  );
  autoUpdater.on("error", (error) =>
    broadcast("updater.status", { state: "error", message: String(error?.message ?? error) }),
  );

  if (settings.get().checkUpdatesOnLaunch) {
    void checkForUpdates();
  }
}

/** Ask the feed. Safe to call when packaging or the network says no. */
export async function checkForUpdates() {
  if (!app.isPackaged) {
    return;
  }
  try {
    await autoUpdater.checkForUpdates();
  } catch (error) {
    broadcast("updater.status", { state: "error", message: String(error) });
  }
}
