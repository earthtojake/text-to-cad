import type { EventEmitter } from "node:events";

import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  broadcast: vi.fn(),
  check: vi.fn(async (): Promise<unknown> => ({})),
  quitAndInstall: vi.fn(),
  downloadUpdate: vi.fn(async (_token?: { cancelled: boolean }): Promise<undefined> => undefined),
  settings: { checkUpdatesOnLaunch: true },
  native: null as unknown as EventEmitter,
}));

vi.mock("electron", async () => {
  const { EventEmitter: Emitter } = await import("node:events");
  mocks.native = new Emitter();
  return { app: { isPackaged: true }, autoUpdater: mocks.native };
});
type FakeUpdater = EventEmitter & { autoDownload: boolean; autoInstallOnAppQuit: boolean; logger: unknown };
let autoUpdater: FakeUpdater;
vi.mock("electron-updater", async () => {
  const { EventEmitter: Emitter } = await import("node:events");
  autoUpdater = Object.assign(new Emitter(), {
    autoDownload: true,
    autoInstallOnAppQuit: true,
    logger: undefined as unknown,
    checkForUpdates: () => mocks.check(),
    downloadUpdate: (token?: { cancelled: boolean }) => mocks.downloadUpdate(token),
    quitAndInstall: (...args: unknown[]) => mocks.quitAndInstall(...args),
  });
  // electron-updater re-exports builder-util-runtime's token: `cancel()` flips `cancelled`.
  class CancellationToken {
    cancelled = false;
    cancel() {
      this.cancelled = true;
    }
  }
  return { default: { autoUpdater, CancellationToken } };
});
vi.mock("@main/ipc", () => ({ broadcast: mocks.broadcast }));
vi.mock("@main/db/repositories", () => ({ settings: { get: () => mocks.settings } }));

const INSTALL_DEADLINE_MS = 60_000;

async function load() {
  // The fake updaters outlive `resetModules`: without this, an earlier test's
  // module would still be listening to them.
  autoUpdater?.removeAllListeners();
  mocks.native?.removeAllListeners();
  vi.resetModules();
  const updater = await import("@main/updater");
  updater.initUpdater();
  return updater;
}

/** A check whose feed announces `version` (electron-updater's event order). */
function feedAnnounces(version: string) {
  mocks.check.mockImplementation(async () => {
    autoUpdater.emit("checking-for-update");
    autoUpdater.emit("update-available", { version });
    return { updateInfo: { version } };
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  mocks.check.mockReset();
  mocks.quitAndInstall.mockReset();
  mocks.broadcast.mockReset();
});

describe("updater", () => {
  it("keeps a staged download staged through a manual check, so Restart still installs", async () => {
    const updater = await load();
    feedAnnounces("2.0.0");
    await updater.checkForUpdates();
    expect(updater.updateStatus()).toEqual({ state: "available", version: "2.0.0" });
    autoUpdater.emit("update-downloaded", { version: "2.0.0" });

    const answer = await updater.checkForUpdates();
    expect(answer).toEqual({ state: "downloaded", version: "2.0.0" });
    expect(mocks.check).toHaveBeenCalledTimes(1);
    const { isQuitting } = await import("@main/quitting");
    mocks.quitAndInstall.mockImplementation(() => {
      // What Electron does when the install really quits: announce it, then
      // close the windows before `before-quit`. The unload guard must already
      // know this is a quit.
      mocks.native.emit("before-quit-for-update");
      expect(isQuitting()).toBe(true);
    });
    updater.installUpdate();
    expect(mocks.quitAndInstall).toHaveBeenCalledWith(false, true);
    expect(isQuitting()).toBe(true);
    updater.stopUpdater();
  });

  it("an install that does not quit leaves the unsaved-draft ask in place", async () => {
    const updater = await load();
    const { isQuitting } = await import("@main/quitting");
    autoUpdater.emit("update-downloaded", { version: "2.0.0" });
    // MacUpdater with Squirrel still fetching, or BaseUpdater's failed
    // install(): quitAndInstall returns and nothing quits.
    mocks.quitAndInstall.mockImplementation(() => undefined);
    updater.installUpdate();
    expect(mocks.quitAndInstall).toHaveBeenCalled();
    expect(isQuitting()).toBe(false);
    updater.stopUpdater();
  });

  it("a second Restart while the first install is under way does not quit and install again", async () => {
    const updater = await load();
    autoUpdater.emit("update-downloaded", { version: "2.0.0" });
    // MacUpdater with Squirrel still fetching: quitAndInstall returns, nothing quits.
    mocks.quitAndInstall.mockImplementation(() => undefined);
    updater.installUpdate();
    updater.installUpdate();
    expect(mocks.quitAndInstall).toHaveBeenCalledTimes(1);
    updater.stopUpdater();
  });

  it("an install that is refused puts the scheduled checks back", async () => {
    const updater = await load();
    await vi.advanceTimersByTimeAsync(10_000);
    expect(mocks.check).toHaveBeenCalledTimes(1);
    autoUpdater.emit("update-downloaded", { version: "2.0.0" });
    // MacUpdater refusing an unsigned update: `error`, and no quit.
    mocks.quitAndInstall.mockImplementation(() => {
      autoUpdater.emit("error", new Error("Could not get code signature for running application"));
    });
    updater.installUpdate();
    expect(updater.updateStatus()).toEqual({ state: "error", message: "Could not get code signature for running application" });

    await vi.advanceTimersByTimeAsync(10_000);
    expect(mocks.check).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(6 * 60 * 60 * 1000);
    expect(mocks.check).toHaveBeenCalledTimes(3);
    updater.stopUpdater();
  });

  it("an install that neither quits nor errors is called stuck after a minute, and Restart can be pressed again", async () => {
    const updater = await load();
    autoUpdater.emit("update-downloaded", { version: "2.0.0" });
    mocks.quitAndInstall.mockImplementation(() => undefined);
    updater.installUpdate();
    expect(updater.updateStatus()).toEqual({ state: "installing", version: "2.0.0" });
    await vi.advanceTimersByTimeAsync(INSTALL_DEADLINE_MS - 1);
    expect(updater.updateStatus().state).toBe("installing");
    await vi.advanceTimersByTimeAsync(1);
    expect(updater.updateStatus()).toEqual({
      state: "error",
      message: "The update did not start; try Restart again.",
      version: "2.0.0",
    });

    updater.installUpdate();
    expect(mocks.quitAndInstall).toHaveBeenCalledTimes(2);
    expect(updater.updateStatus().state).toBe("installing");
    updater.stopUpdater();
  });

  it("shows one line of an error, never its stack", async () => {
    const updater = await load();
    autoUpdater.emit("error", new Error("x\n    at foo (file:1:1)"));
    const { message } = updater.updateStatus();
    expect(message).toBe("x");
    expect(message).not.toContain("at foo");
    updater.stopUpdater();
  });

  it("says a release is missing in a sentence, not in the provider's text and stack", async () => {
    const updater = await load();
    autoUpdater.emit(
      "error",
      new Error(
        "Unable to find latest version on GitHub (https://github.com/o/r/releases/latest), please ensure a production release exists: HttpError: 404\n    at createHttpError (x.js:1:1)",
      ),
    );
    expect(updater.updateStatus()).toEqual({ state: "error", message: "No release is published yet." });
    updater.stopUpdater();
  });

  it("does not call a GitHub 5xx 'no release is published yet'", async () => {
    const updater = await load();
    autoUpdater.emit(
      "error",
      new Error(
        "Unable to find latest version on GitHub (https://github.com/o/r/releases/latest), please ensure a production release exists: HttpError: 503 Service Unavailable\n    at x",
      ),
    );
    expect(updater.updateStatus()).toEqual({ state: "error", message: "GitHub did not answer the update check." });
    updater.stopUpdater();
  });

  it("words a failed download as a download, not a check", async () => {
    const updater = await load();
    autoUpdater.emit("update-available", { version: "2.0.0" });
    mocks.downloadUpdate.mockRejectedValue(new Error("net::ERR_CONNECTION_RESET"));
    expect(await updater.downloadUpdate()).toEqual({
      state: "error",
      message: "Could not reach GitHub to download the update.",
    });
    updater.stopUpdater();
  });

  it("reads the first line and the code for a dropped connection, not the whole text", async () => {
    const updater = await load();
    autoUpdater.emit("error", new Error("The feed was not valid\n    at parse (ECONNRESET.js:1:1)"));
    expect(updater.updateStatus()).toEqual({ state: "error", message: "The feed was not valid" });

    autoUpdater.emit("error", Object.assign(new Error("read failed"), { code: "ECONNRESET" }));
    expect(updater.updateStatus().message).toBe("Could not reach GitHub to check for updates.");
    updater.stopUpdater();
  });

  it("a check the updater answers with nothing is unsupported, not up to date", async () => {
    const updater = await load();
    mocks.check.mockResolvedValue(null);
    const answer = await updater.checkForUpdates();
    expect(answer.state).toBe("unsupported");
    expect(answer.message).toMatch(/no update channel/);
    updater.stopUpdater();
  });

  it("a background check that fails leaves the offered update on offer", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const updater = await load();
    autoUpdater.emit("update-available", { version: "2.0.0" });
    autoUpdater.emit("checking-for-update");
    expect(updater.updateStatus()).toEqual({ state: "available", version: "2.0.0" });
    autoUpdater.emit("error", new Error("net::ERR_INTERNET_DISCONNECTED"));
    expect(updater.updateStatus()).toEqual({ state: "available", version: "2.0.0" });

    autoUpdater.emit("checking-for-update");
    autoUpdater.emit("update-not-available", { version: "1.0.0" });
    expect(updater.updateStatus()).toEqual({ state: "idle" });
    warn.mockRestore();
    updater.stopUpdater();
  });

  /** An offered 2.0.0 whose download is under way, as a check that started earlier is still pending. */
  async function downloading() {
    const updater = await load();
    autoUpdater.emit("update-available", { version: "2.0.0" });
    mocks.downloadUpdate.mockImplementation(() => new Promise<undefined>(() => undefined));
    void updater.downloadUpdate();
    autoUpdater.emit("download-progress", { percent: 10 });
    return updater;
  }

  it("calls a download that stops reporting progress stalled, and Try again can check afresh", async () => {
    const updater = await downloading();
    vi.advanceTimersByTime(59_000);
    expect(updater.updateStatus().state).toBe("downloading");
    autoUpdater.emit("download-progress", { percent: 20 });
    vi.advanceTimersByTime(59_000);
    expect(updater.updateStatus().state, "progress restarted the countdown").toBe("downloading");

    vi.advanceTimersByTime(1_000);
    expect(updater.updateStatus()).toEqual({ state: "error", message: "The download stalled; try again." });

    feedAnnounces("2.0.0");
    expect((await updater.checkForUpdates()).state).toBe("available");
  });

  it("cancels the stalled download, so Try again starts a fresh one rather than re-attaching to the hung one", async () => {
    const updater = await downloading();
    const first = mocks.downloadUpdate.mock.calls[0]![0]!;
    expect(first.cancelled).toBe(false);

    vi.advanceTimersByTime(60_000);
    expect(first.cancelled, "the stalled download's token is cancelled").toBe(true);

    feedAnnounces("2.0.0");
    await updater.checkForUpdates();
    void updater.downloadUpdate();
    expect(mocks.downloadUpdate).toHaveBeenCalledTimes(2);
    const second = mocks.downloadUpdate.mock.calls[1]![0]!;
    expect(second, "a new token, not the cancelled one").not.toBe(first);
    expect(second.cancelled).toBe(false);
    expect(updater.updateStatus().state).toBe("downloading");
  });

  it("ignores progress and the rejection that a cancelled stalled download delivers late", async () => {
    mocks.downloadUpdate.mockReset();
    const updater = await load();
    autoUpdater.emit("update-available", { version: "2.0.0" });
    let reject!: (error: Error) => void;
    mocks.downloadUpdate.mockImplementation(() => new Promise<undefined>((_resolve, fail) => { reject = fail; }));
    const pending = updater.downloadUpdate();
    autoUpdater.emit("download-progress", { percent: 10 });
    vi.advanceTimersByTime(60_000);
    const stalled = { state: "error", message: "The download stalled; try again." };
    expect(updater.updateStatus()).toEqual(stalled);

    autoUpdater.emit("download-progress", { percent: 11 });
    expect(updater.updateStatus(), "late progress does not bring Downloading back").toEqual(stalled);

    reject(new Error("Cancelled"));
    await pending;
    expect(updater.updateStatus(), "the cancellation is not reported as a failure").toEqual(stalled);
  });

  it("a check that fails while a download runs leaves the download running", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const updater = await downloading();
    autoUpdater.emit("error", new Error("net::ERR_INTERNET_DISCONNECTED"));
    expect(updater.updateStatus()).toEqual({ state: "downloading", version: "2.0.0", percent: 10 });
    autoUpdater.emit("download-progress", { percent: 20 });
    expect(updater.updateStatus()).toEqual({ state: "downloading", version: "2.0.0", percent: 20 });
    warn.mockRestore();
    updater.stopUpdater();
  });

  it("a check that finds nothing while a download runs leaves the download running", async () => {
    const updater = await downloading();
    autoUpdater.emit("update-not-available", { version: "1.0.0" });
    expect(updater.updateStatus()).toEqual({ state: "downloading", version: "2.0.0", percent: 10 });
    autoUpdater.emit("download-progress", { percent: 20 });
    expect(updater.updateStatus()).toEqual({ state: "downloading", version: "2.0.0", percent: 20 });
    updater.stopUpdater();
  });

  it("skips the six-hourly check while downloaded or downloading", async () => {
    const staged = await load();
    autoUpdater.emit("update-downloaded", { version: "2.0.0" });
    await vi.advanceTimersByTimeAsync(6 * 60 * 60 * 1000 + 10_000);
    expect(mocks.check).not.toHaveBeenCalled();
    staged.stopUpdater();

    // (Progress only counts while a download is actually under way.)
    const updater = await downloading();
    // A download that is alive keeps reporting; one that goes quiet is a stalled one.
    for (let elapsed = 0; elapsed < 6 * 60 * 60 * 1000; elapsed += 30_000) {
      await vi.advanceTimersByTimeAsync(30_000);
      autoUpdater.emit("download-progress", { percent: 40 });
    }
    expect(mocks.check).not.toHaveBeenCalled();
    expect(updater.updateStatus().state).toBe("downloading");
    updater.stopUpdater();
  });

  it("ignores a re-announcement of the version already downloaded", async () => {
    const updater = await load();
    autoUpdater.emit("update-downloaded", { version: "2.0.0" });
    autoUpdater.emit("checking-for-update");
    autoUpdater.emit("update-available", { version: "2.0.0" });
    expect(updater.updateStatus()).toEqual({ state: "downloaded", version: "2.0.0" });
    updater.stopUpdater();
  });

  it("treats a release without latest-*.yml as idle, not an error", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const updater = await load();
    mocks.check.mockImplementation(async () => {
      const error = Object.assign(new Error("Cannot find latest-mac.yml in the latest release artifacts (https://…): 404"), {
        code: "ERR_UPDATER_CHANNEL_FILE_NOT_FOUND",
      });
      autoUpdater.emit("error", error);
      throw error;
    });
    expect(await updater.checkForUpdates()).toEqual({ state: "idle" });
    expect(warn).toHaveBeenCalled();

    mocks.check.mockRejectedValue(new Error("net::ERR_INTERNET_DISCONNECTED"));
    expect(await updater.checkForUpdates()).toEqual({ state: "error", message: "Could not reach GitHub to check for updates." });
    warn.mockRestore();
    updater.stopUpdater();
  });
});
