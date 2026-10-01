import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "sonner";

import { useUpdates } from "@renderer/state/updates";

const dirty = vi.hoisted(() => ({ value: false }));
vi.mock("@renderer/state/live-documents", () => ({ hasAnyDirtyDocument: () => dirty.value }));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { error: vi.fn(), info: vi.fn() }) }));

type AppApi = Record<string, unknown>;
const app = () => window.textToCad.app as unknown as AppApi;

beforeEach(() => {
  useUpdates.setState({ status: { state: "idle" }, busy: false });
  vi.mocked(toast.error).mockClear();
  vi.mocked(toast).mockClear();
  dirty.value = false;
});

afterEach(() => {
  delete app().checkForUpdates;
  delete app().updateStatus;
  delete app().installUpdate;
});

describe("updates store", () => {
  it("a rejected check becomes an error status and a toast, not an unhandled rejection", async () => {
    app().checkForUpdates = vi.fn(async () => {
      throw new Error("ipc went away");
    });
    await expect(useUpdates.getState().check()).resolves.toBeUndefined();
    expect(useUpdates.getState().status).toEqual({ state: "error", message: "ipc went away" });
    expect(useUpdates.getState().busy).toBe(false);
    expect(toast.error).toHaveBeenCalledTimes(1);
  });

  it("shows the handler's sentence once, not Electron's invoke wrapper, on the row and not again in the toast", async () => {
    app().checkForUpdates = vi.fn(async () => {
      throw new Error("Error invoking remote method 'app.checkForUpdates': Error: GitHub did not answer the update check.");
    });
    await useUpdates.getState().check();
    expect(useUpdates.getState().status).toEqual({ state: "error", message: "GitHub did not answer the update check." });
    expect(toast.error).toHaveBeenCalledWith("Could not reach the updater");
  });

  it("a rejected first read lands as an error status too", async () => {
    app().updateStatus = vi.fn(async () => {
      throw new Error("no handler");
    });
    await expect(useUpdates.getState().load()).resolves.toBeUndefined();
    expect(useUpdates.getState().status).toEqual({ state: "error", message: "no handler" });
  });

  it("asks once before restarting over an unsaved document, and installs only when confirmed", async () => {
    dirty.value = true;
    useUpdates.setState({ status: { state: "downloaded", version: "1.2.3" } });
    const installUpdate = vi.fn(async () => undefined);
    app().installUpdate = installUpdate;

    await useUpdates.getState().install();
    expect(installUpdate).not.toHaveBeenCalled();
    expect(toast).toHaveBeenCalledWith("Restart now and discard unsaved changes?", expect.objectContaining({
      action: expect.objectContaining({ label: "Restart" }),
      cancel: expect.objectContaining({ label: "Not now" }),
    }));

    const options = vi.mocked(toast).mock.calls[0]![1] as unknown as { action: { onClick: () => void } };
    options.action.onClick();
    await vi.waitFor(() => expect(installUpdate).toHaveBeenCalledTimes(1));
  });

  it("restarts without asking when nothing is unsaved", async () => {
    useUpdates.setState({ status: { state: "downloaded", version: "1.2.3" } });
    const installUpdate = vi.fn(async () => undefined);
    app().installUpdate = installUpdate;
    await useUpdates.getState().install();
    expect(installUpdate).toHaveBeenCalledTimes(1);
    expect(toast).not.toHaveBeenCalled();
  });
});
