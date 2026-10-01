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
 * It is also `unsupported` for an install whose updater is inactive (an
 * AppImage run without `APPIMAGE`, a snap): its check answers with no result.
 *
 * The statuses are pushed (`app.updateStatus`), and two rules keep them true:
 *
 * - An offer survives a background check. `available` is left only by an
 *   answer (`update-available` refreshes it, `update-not-available` retires
 *   it to `idle`) or by Download; a check that fails while one is on offer
 *   leaves it on offer. A check never overwrites a busy state: while an update
 *   is downloading, downloaded or installing, `checkForUpdates` answers with
 *   the status and the feed's events are ignored.
 * - Restart is a pushed `installing` status, so the row says "Restarting…" for
 *   as long as it is true. It lasts at most `INSTALL_DEADLINE_MS`; past that
 *   the status is an `error` that keeps the staged version, the scheduled
 *   checks start again, and Restart is a retry.
 *
 * A failure is one sentence (`message`): "Could not reach GitHub to check for
 * updates." (or "…to download the update.") for a socket error, "No release is
 * published yet." for the provider's 404, "GitHub did not answer the update
 * check." for its other failures, and otherwise the error's first line. A
 * release that lacks this platform's feed file is not a failure: the status
 * goes back to `idle`.
 */
import { app, autoUpdater as nativeUpdater } from "electron";
import electronUpdater from "electron-updater";

import { broadcast } from "./ipc";
import { settings } from "./db/repositories";
import { markQuittingForUpdate } from "./quitting";
import type { UpdateStatus } from "../shared/ipc/app";

const { autoUpdater, CancellationToken } = electronUpdater;

/** Long enough to be out of the launch path; short enough to matter today. */
const FIRST_CHECK_DELAY_MS = 10_000;
/** A long-running window still notices a release the same day. */
const CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000;

let status: UpdateStatus = { state: "unsupported" };
let timers: NodeJS.Timeout[] = [];
/**
 * How long a Restart may take before it is called stuck. Squirrel can need
 * seconds on macOS; past a minute nothing is going to quit, and the row would
 * otherwise say "Restarting…" until the next launch.
 */
export const INSTALL_DEADLINE_MS = 60_000;
let installDeadline: NodeJS.Timeout | undefined;
/**
 * How long a download may go without a progress event before it is called stalled. A connection
 * that went quiet leaves "Downloading…" with no action and checks refused; past this the row
 * says so and offers Try again.
 */
export const DOWNLOAD_STALL_MS = 60_000;
export const DOWNLOAD_STALLED = "The download stalled; try again.";
let stallTimer: NodeJS.Timeout | undefined;
/**
 * The download in flight. `downloadUpdate` hands electron-updater a token and a stall cancels it:
 * `AppUpdater.downloadUpdate` returns the promise of a download already in flight, so without the
 * cancel a Try again would re-attach to the hung one. `downloadGeneration` is bumped when a
 * download is abandoned, so its late rejection is not reported as a failure of the next one.
 */
let downloadToken: InstanceType<typeof CancellationToken> | undefined;
let downloadGeneration = 0;

/** (Re)start the stall countdown: called when the download starts and on every progress event. */
function armStall() {
  clearTimeout(stallTimer);
  stallTimer = setTimeout(() => {
    stallTimer = undefined;
    if (status.state === "downloading") {
      // Cancelled, so the next download is a fresh one; no `version`, because on an error that
      // marks a staged download the row answers with Restart, and nothing is staged here.
      downloadGeneration += 1;
      downloadToken?.cancel();
      downloadToken = undefined;
      setStatus({ state: "error", message: DOWNLOAD_STALLED });
    }
  }, DOWNLOAD_STALL_MS);
  stallTimer.unref();
}
/** The version `update-downloaded` staged: what a retried Restart installs. */
let staged: string | undefined;

/** The last known status. Never asks the feed. */
export function updateStatus(): UpdateStatus {
  return status;
}

function setStatus(next: UpdateStatus): UpdateStatus {
  status = next;
  if (next.state !== "downloading") {
    clearTimeout(stallTimer);
    stallTimer = undefined;
  }
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

  // A check is never started while an update is downloading or staged
  // (`busyWithUpdate`), but the feed's events are guarded too: a staged
  // version that the feed announces again is still staged, and flipping it to
  // `available` would leave `installUpdate` with nothing it will install.
  // The quit an install starts closes every window BEFORE `before-quit`, so
  // the unsaved-draft ask would otherwise appear and its Cancel strand the
  // restart. Marked on Electron's own `before-quit-for-update` — emitted by the
  // native updater (macOS Squirrel) and re-emitted by electron-updater's
  // BaseUpdater (Windows, Linux) — only once the quit is really under way: a
  // `quitAndInstall` that returns without quitting (Squirrel still fetching,
  // a failed install) must leave the ask in place (`./quitting.ts`). The
  // same mark keeps the quit deadline off the installer it has just spawned.
  nativeUpdater.on("before-quit-for-update", markQuittingForUpdate);

  autoUpdater.on("checking-for-update", () => {
    // An offered update stays offered while the feed is asked again (the
    // scheduled check runs from `available`): the Download button is not
    // swapped for a spinner, and the answer — `update-available` refreshes it,
    // `update-not-available` retires it — is what moves the status.
    if (!busyWithUpdate() && status.state !== "available") {
      setStatus({ state: "checking" });
    }
  });
  autoUpdater.on("update-available", (info) => {
    if (status.state === "downloading") {
      return;
    }
    if ((status.state === "downloaded" || status.state === "installing") && status.version === info.version) {
      return;
    }
    setStatus({ state: "available", version: info.version });
  });
  autoUpdater.on("update-not-available", () => {
    // A check that overlaps a download (the six-hourly one, answering after
    // the Download press) finds nothing for the version already on its way.
    if (!busyWithUpdate()) {
      setStatus({ state: "idle" });
    }
  });
  autoUpdater.on("download-progress", (progress) => {
    // Progress from a download that was cancelled as stalled arrives after the row said so: it
    // must not turn the error back into "Downloading…" with no version.
    if (status.state !== "downloading") {
      return;
    }
    setStatus({
      state: "downloading",
      version: status.version,
      // electron-updater reports a float; the UI wants a percentage it can
      // print, and the schema refuses anything outside 0–100.
      percent: Math.min(100, Math.max(0, Math.round(progress.percent))),
    });
    armStall();
  });
  autoUpdater.on("update-downloaded", (info) => {
    staged = info.version;
    setStatus({ state: "downloaded", version: info.version });
  });
  autoUpdater.on("error", (error) => {
    const refusedInstall = status.state === "installing";
    failed(error);
    // An install that was refused (an unsigned or unverifiable update on
    // macOS, a failed installer spawn) did not quit, so the app carries on —
    // and so must its scheduled checks, which `installUpdate` stopped.
    if (refusedInstall) {
      scheduleChecks();
    }
  });

  scheduleChecks();
}

function scheduleChecks() {
  stopUpdater();
  const automatic = () => {
    if (busyWithUpdate()) {
      return;
    }
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

/** Stop the scheduled checks and the install deadline. Called on quit; safe to call twice. */
export function stopUpdater() {
  clearTimeout(installDeadline);
  installDeadline = undefined;
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
  // Downloading or staged: there is nothing a check could add, and its events
  // would knock the state off `downloaded`. The answer is the current status —
  // which About prints as "Version … is ready. Restarting installs it."
  if (busyWithUpdate()) {
    return status;
  }
  try {
    const result = await autoUpdater.checkForUpdates();
    // A check that finds nothing fires `update-not-available`, which has
    // already set the status; returning it rather than inventing one keeps the
    // event stream and the answer identical. No result at all is the updater
    // being inactive for this install (an AppImage run without APPIMAGE, a
    // snap): that is not "up to date", it is "cannot be updated from here".
    if (!result) {
      return setStatus({ state: "unsupported", message: "This install has no update channel, so updates are not available." });
    }
    return status;
  } catch (error) {
    return failed(error);
  }
}

/** True while an update is downloading, downloaded and waiting for Restart, or being installed. */
function busyWithUpdate() {
  return status.state === "downloading" || status.state === "downloaded" || status.state === "installing";
}

/**
 * A release published without the feed file for this platform (the GitHub
 * provider's "Cannot find latest-mac.yml …", e.g. while a release's assets are
 * still uploading) is "no update for this build yet", not a failure to keep on
 * screen until the next check: logged, and the status goes back to `idle`.
 */
export function isMissingFeedFile(error: unknown): boolean {
  const code = (error as { code?: unknown } | null)?.code;
  return code === "ERR_UPDATER_CHANNEL_FILE_NOT_FOUND" || /cannot find latest[^\s]*\.yml/i.test(message(error));
}

function failed(error: unknown): UpdateStatus {
  // A check that fails while a download runs must not replace it: the
  // download's own rejection sets its error (`downloadUpdate`), and the next
  // progress event would otherwise restore `downloading` with no version. An
  // install the updater refuses is the one error that does belong here.
  if (busyWithUpdate() && status.state !== "installing") {
    console.warn("[updater] ignoring an error while an update is in progress:", message(error));
    return status;
  }
  // `available` is only ever left by an answer or by `downloadUpdate`, which
  // moves to `downloading` first: an error here is a background check that
  // failed, and the update it found earlier is still there to download.
  if (status.state === "available") {
    console.warn("[updater] check failed while an update is on offer:", message(error));
    return status;
  }
  if (isMissingFeedFile(error)) {
    console.warn("[updater] release has no update feed for this platform yet:", message(error));
    return status.state === "idle" ? status : setStatus({ state: "idle" });
  }
  return setStatus({ state: "error", message: message(error) });
}

/** Download the update that was found. A no-op unless one was. */
export async function downloadUpdate(): Promise<UpdateStatus> {
  if (status.state !== "available") {
    return status;
  }
  const token = new CancellationToken();
  downloadToken = token;
  const generation = downloadGeneration;
  try {
    setStatus({ state: "downloading", version: status.version, percent: 0 });
    armStall();
    await autoUpdater.downloadUpdate(token);
    return status;
  } catch (error) {
    // A download abandoned as stalled rejects with its cancellation: the row already says why.
    if (generation !== downloadGeneration) {
      return status;
    }
    return setStatus({ state: "error", message: message(error, "download") });
  }
}

/**
 * Restart into the new version. Only once something is staged — asking Electron
 * to quit and install nothing quits and installs nothing, loudly.
 */
export function installUpdate() {
  // A second press while the first is under way: MacUpdater would add a second
  // `update-downloaded` listener and a second install while Squirrel is still
  // fetching, and BaseUpdater's second `install` resets its own guard. Once the
  // deadline has called the first one stuck, the same press is a retry: the
  // error carries the staged version.
  const retry = status.state === "error" && staged !== undefined && status.version === staged;
  if (status.state !== "downloaded" && !retry) {
    return;
  }
  stopUpdater();
  // Pushed, so the row says "Restarting…" for as long as it is true instead of
  // for the length of the IPC round trip.
  setStatus({ state: "installing", version: staged });
  installDeadline = setTimeout(() => {
    installDeadline = undefined;
    setStatus({ state: "error", message: INSTALL_STUCK, version: staged });
    scheduleChecks();
  }, INSTALL_DEADLINE_MS);
  installDeadline.unref();
  // `isSilent` false: show the installer on Windows. BaseUpdater passes
  // `isSilent ? isForceRunAfter : autoRunAppAfterInstall` on to the installer,
  // so here the second argument does nothing and coming back up afterwards is
  // the wizard's "run after finish" box (`oneClick: false`); macOS relaunches
  // through Squirrel.
  autoUpdater.quitAndInstall(false, true);
}

const INSTALL_STUCK = "The update did not start; try Restart again.";

/** What a socket says when GitHub could not be reached at all. */
const UNREACHABLE = /net::ERR_|ENOTFOUND|EAI_AGAIN|ECONNREFUSED|ECONNRESET|ETIMEDOUT|ENETUNREACH|EHOSTUNREACH/;

/**
 * The line About prints (the schema promises a `message` safe to show). The
 * library's text is for a log: the GitHub provider appends the failure's whole
 * stack to "Unable to find latest version on GitHub (url), please ensure a
 * production release exists", so the known cases get a sentence of their own
 * and anything else keeps its first line and nothing after it.
 */
function message(error: unknown, doing: "check" | "download" = "check"): string {
  const raw = error instanceof Error ? error.message : String(error);
  const firstLine = raw.split(/\r?\n/, 1)[0]!.trim();
  // The first line and the error's own code, not the whole text: a feed that
  // merely mentions ECONNRESET further down is not a dropped connection.
  const code = (error as { code?: unknown } | null)?.code;
  if (UNREACHABLE.test(firstLine) || (typeof code === "string" && UNREACHABLE.test(code))) {
    return doing === "download"
      ? "Could not reach GitHub to download the update."
      : "Could not reach GitHub to check for updates.";
  }
  if (/unable to find latest version on github/i.test(raw)) {
    // The provider wraps every failure in that sentence; only a 404 is "there
    // is no release". A 5xx or a 429 is GitHub having a bad minute.
    return /HttpError: 404\b/.test(raw) ? "No release is published yet." : "GitHub did not answer the update check.";
  }
  return firstLine;
}
