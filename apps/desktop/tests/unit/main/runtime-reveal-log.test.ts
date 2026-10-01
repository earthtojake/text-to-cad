/**
 * `runtime.revealLog` takes no path: main names `userData/cad-runtime.log`
 * and reveals it only when it exists.
 */
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterAll, beforeAll, beforeEach, expect, test, vi } from "vitest";

const fixture = vi.hoisted(() => ({ userData: "" }));
const showItemInFolder = vi.hoisted(() => vi.fn());
vi.mock("electron", () => ({
  app: { getPath: (name: string) => (name === "userData" ? fixture.userData : "") },
  BrowserWindow: {},
  ipcMain: {},
  shell: { showItemInFolder },
}));
vi.mock("@main/cad", () => ({ cadRuntime: () => { throw new Error("not in this test"); } }));
import { revealRuntimeLog } from "@main/ipc/runtime";

beforeAll(async () => {
  fixture.userData = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), "runtime-log-")));
});
afterAll(async () => { await fs.rm(fixture.userData, { recursive: true, force: true }); });
beforeEach(() => { showItemInFolder.mockClear(); });

test("a missing log is not revealed, and says so", async () => {
  await fs.rm(path.join(fixture.userData, "cad-runtime.log"), { force: true });
  expect(revealRuntimeLog()).toEqual({ revealed: false });
  expect(showItemInFolder).not.toHaveBeenCalled();
});

test("an existing log is revealed at main's own path", async () => {
  const log = path.join(fixture.userData, "cad-runtime.log");
  await fs.writeFile(log, "probe failed\n");
  expect(revealRuntimeLog()).toEqual({ revealed: true });
  expect(showItemInFolder).toHaveBeenCalledWith(log);
});
