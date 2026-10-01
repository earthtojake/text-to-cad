import { beforeEach, describe, expect, it, vi } from "vitest";

const invoke = vi.fn();
let exposed: { explorer: { stat: (request: unknown) => Promise<unknown> } };

vi.mock("electron", () => ({
  contextBridge: { exposeInMainWorld: (_name: string, api: unknown) => { exposed = api as typeof exposed; } },
  ipcRenderer: { invoke: (...args: unknown[]) => invoke(...args), on: vi.fn(), off: vi.fn() },
}));

describe("the preload bridge", () => {
  beforeEach(async () => {
    vi.resetModules();
    invoke.mockReset();
    await import("@preload/index");
  });

  it("hands the renderer the handler's own sentence, not Electron's wrapper", async () => {
    invoke.mockRejectedValue(new Error("Error invoking remote method 'text-to-cad:explorer.stat': IpcError: that file is gone"));
    await expect(exposed.explorer.stat({ path: "a.txt" })).rejects.toThrow(/^that file is gone$/);
  });

  it("passes a resolved value through untouched", async () => {
    invoke.mockResolvedValue({ kind: "file" });
    await expect(exposed.explorer.stat({ path: "a.txt" })).resolves.toEqual({ kind: "file" });
  });
});
