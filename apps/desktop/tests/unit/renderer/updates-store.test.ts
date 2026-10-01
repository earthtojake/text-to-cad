import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "sonner";

import { useUpdates } from "@renderer/state/updates";

vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn() } }));

type AppApi = Record<string, unknown>;
const app = () => window.textToCad.app as unknown as AppApi;

beforeEach(() => {
  useUpdates.setState({ status: { state: "idle" }, busy: false });
  vi.mocked(toast.error).mockClear();
});

afterEach(() => {
  delete app().checkForUpdates;
  delete app().updateStatus;
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
});
