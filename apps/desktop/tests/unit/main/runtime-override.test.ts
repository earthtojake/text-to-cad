/**
 * Changing the CAD interpreter override re-probes and broadcasts the new
 * status, so About and a CAD tab's build-failure note stop quoting the old
 * interpreter's kernel.
 */
import { expect, test, vi } from "vitest";

const calls = vi.hoisted(() => ({ repair: vi.fn(), broadcast: vi.fn() }));
vi.mock("electron", () => ({ app: { getPath: () => "" }, BrowserWindow: {}, ipcMain: {}, shell: {} }));
vi.mock("@main/cad", () => ({ cadRuntime: () => ({ repair: calls.repair }) }));
vi.mock("@main/ipc/register", () => ({ broadcast: calls.broadcast }));
import { refreshRuntimeAfterOverride } from "@main/ipc/runtime";

test("probes afresh and tells every window the new interpreter's status", async () => {
  const fresh = { state: "ready", python: "/new/python", source: "override", cadgenVersion: "9.9.9", viewerBuilt: true, log: null };
  calls.repair.mockResolvedValue(fresh);
  expect(await refreshRuntimeAfterOverride()).toBe(fresh);
  expect(calls.repair).toHaveBeenCalledOnce();
  expect(calls.broadcast).toHaveBeenCalledWith("runtime.status", fresh);
});

test("override A then B: only B's answer is broadcast, even when A's arrives last", async () => {
  calls.repair.mockReset();
  calls.broadcast.mockReset();
  let answerA: (status: unknown) => void = () => {};
  const a = { state: "ready", python: "/a/python", source: "override", cadgenVersion: "9.9.9", viewerBuilt: true, log: null };
  const b = { ...a, python: "/b/python" };
  calls.repair.mockImplementationOnce(() => new Promise((resolve) => { answerA = resolve; }));
  calls.repair.mockResolvedValueOnce(b);
  const first = refreshRuntimeAfterOverride();
  const second = refreshRuntimeAfterOverride();
  await second;
  answerA(a);
  await first;
  expect(calls.broadcast).toHaveBeenCalledOnce();
  expect(calls.broadcast).toHaveBeenCalledWith("runtime.status", b);
});
