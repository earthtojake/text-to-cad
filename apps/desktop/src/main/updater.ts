/**
 * Auto-update against the GitHub Releases the repository already publishes
 * (`release-publish.yml` attaches the installers to the release it tags; plan
 * §11). The feed is configured in `electron-builder.yml` and baked into the
 * build as `app-update.yml`, so nothing is read from the network before the app
 * knows where to look.
 *
 * Two decisions worth stating:
 *
 * - **`autoDownload` is off.** A hundred megabytes over someone's tether, on
 *   launch, without asking, is not a thing to do quietly. The app finds the
 *   update, says so, and downloads when the person presses Download.
 * - **`autoInstallOnAppQuit` is off.** Installing during quit means the next
 *   launch is a different build than the one they closed, with no moment where
 *   they agreed to it.
 *
 * A no-op in development: `electron-updater` has no `app-update.yml` to read
 * there, and an unsigned dev build must never be told to replace itself. The
 * status is `unsupported` then, so About shows why instead of a dead button.
 */
import { app } from "electron";
import electronUpdater from "electron-updater";

import { broadcast } from "./ipc";
import { settings } from "./db/repositories";
import type { UpdateStatus } from "../shared/ipc/app";

const { autoUpdater } = electronUpdater;

/** Long enough to be out of the launch path; short enough to matter today. */
const FIRST_CHECK_DELAY_MS = 10_000;
/** A long-running window still notices a release the same day. */
const CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000;

let status: UpdateStatus = { state: "unsupported" };
let timers: NodeJS.Timeout[] = [];

/** The last known status. Never asks the feed. */
export function updateStatus(): UpdateStatus {
  return status;
}

function setStatus(next: UpdateStatus): UpdateStatus {
  status = next;
  broadcast("app.updateStatus", next);
  return next;
}

/**
 * Wire the updater, then check on a delay and every six hours after that.
 *
 * Both automatic checks are gated on the user's `checkUpdatesOnLaunch` setting;
 * the manual ones below are not, because pressing a button that says "Check for
 * updates" is consent.
 */
export function initUpdater() {
  if (!app.isPackaged) {
    return;
  }

  status = { state: "idle" };
  autoUpdater.autoDownload = false;
  autoUpdater.autoInstallOnAppQuit = false;
  autoUpdater.logger = null;

  autoUpdater.on("checking-for-update", () => setStatus({ state: "checking" }));
  autoUpdater.on("update-available", (info) =>
    setStatus({ state: "available", version: info.version }),
  );
  autoUpdater.on("update-not-available", () => setStatus({ state: "idle" }));
  autoUpdater.on("download-progress", (progress) =>
    setStatus({
      state: "downloading",
      version: status.version,
      // electron-updater reports a float; the UI wants a percentage it can
      // print, and the schema refuses anything outside 0–100.
      percent: Math.min(100, Math.max(0, Math.round(progress.percent))),
    }),
  );
  autoUpdater.on("update-downloaded", (info) =>
    setStatus({ state: "downloaded", version: info.version }),
  );
  autoUpdater.on("error", (error) => setStatus({ state: "error", message: message(error) }));

  const automatic = () => {
    if (settings.get().checkUpdatesOnLaunch) {
      void checkForUpdates();
    }
  };

  // `unref` so a pending timer is never the reason the process is still alive.
  timers = [setTimeout(automatic, FIRST_CHECK_DELAY_MS), setInterval(automatic, CHECK_INTERVAL_MS)];
  for (const timer of timers) {
    timer.unref();
  }
}

/** Stop the scheduled checks. Called on quit; safe to call twice. */
export function stopUpdater() {
  for (const timer of timers) {
    clearTimeout(timer);
    clearInterval(timer);
  }
  timers = [];
}

/** Ask the feed. Safe to call when packaging or the network says no. */
export async function checkForUpdates(): Promise<UpdateStatus> {
  if (!app.isPackaged) {
    return status;
  }
  try {
    const result = await autoUpdater.checkForUpdates();
    // A check that finds nothing fires `update-not-available`, which has
    // already set the status; returning it rather than inventing one keeps the
    // event stream and the answer identical.
    if (!result) {
      return setStatus({ state: "idle" });
    }
    return status;
  } catch (error) {
    return setStatus({ state: "error", message: message(error) });
  }
}

/** Download the update that was found. A no-op unless one was. */
export async function downloadUpdate(): Promise<UpdateStatus> {
  if (status.state !== "available") {
    return status;
  }
  try {
    setStatus({ state: "downloading", version: status.version, percent: 0 });
    await autoUpdater.downloadUpdate();
    return status;
  } catch (error) {
    return setStatus({ state: "error", message: message(error) });
  }
}

/**
 * Restart into the new version. Only once something is staged — asking Electron
 * to quit and install nothing quits and installs nothing, loudly.
 */
export function installUpdate() {
  if (status.state !== "downloaded") {
    return;
  }
  stopUpdater();
  // `isSilent` false, `isForceRunAfter` true: show the installer on Windows,
  // and come back up afterwards on every platform.
  autoUpdater.quitAndInstall(false, true);
}

function message(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}
