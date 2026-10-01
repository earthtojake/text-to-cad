/**
 * `browser.*` scope resolution: a session whose worktree has gone is a
 * refusal in the app's words, not a raw ENOENT from `realpath`.
 */
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const fixture = vi.hoisted(() => ({ root: "", cwd: "" }));
const metadata = vi.hoisted(() => vi.fn());
const sweep = vi.hoisted(() => vi.fn().mockResolvedValue([]));
vi.mock("electron", () => ({ BrowserWindow: {} }));
vi.mock("@main/db/repositories", () => ({
  sessions: {
    get: (id: string) => id === "owner" ? { id, projectId: "project", cwd: fixture.cwd, archived: false } : undefined,
    list: () => [{ id: "owner" }, { id: "archived" }],
  },
}));
vi.mock("@main/ipc/explorer", () => ({ rootOf: () => fixture.root }));
vi.mock("@main/browser/service", () => ({ browserService: { metadata } }));
vi.mock("@main/browser/storage", () => ({ sweepBrowserStorage: sweep }));
import { browserHandlers } from "@main/ipc/browser";
import { IpcError } from "@main/ipc/register";

beforeEach(async () => {
  fixture.root = fixture.cwd = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), "browser-ipc-")));
  metadata.mockReset().mockReturnValue({ tabId: "tab" });
});
afterEach(async () => { await fs.rm(fixture.root, { recursive: true, force: true }); });

const request = { sessionId: "owner", projectId: "project", root: null, tabId: "tab" };

it("resolves the session's own workspace", () => {
  expect(browserHandlers.browser.metadata(request)).toEqual({ tabId: "tab" });
  expect(metadata).toHaveBeenCalledWith({ sessionId: "owner", projectId: "project", root: fixture.root }, "tab", true);
  expect(browserHandlers.browser.metadata({ ...request, logs: false })).toEqual({ tabId: "tab" });
  expect(metadata).toHaveBeenLastCalledWith(expect.anything(), "tab", false);
  // Orphaned partitions are swept once, against every session that still exists.
  expect(sweep).toHaveBeenCalledTimes(1);
  const liveSessions = sweep.mock.calls[0]![0] as () => { id: string }[];
  expect(liveSessions().map(session => session.id)).toEqual(["owner", "archived"]);
});

it("refuses a missing workspace with an IpcError instead of a raw ENOENT", async () => {
  await fs.rm(fixture.root, { recursive: true, force: true });
  let thrown: unknown;
  try { browserHandlers.browser.metadata(request); } catch (error) { thrown = error; }
  expect(thrown).toBeInstanceOf(IpcError);
  expect((thrown as Error).message).toBe("This session's workspace is missing.");
  expect(metadata).not.toHaveBeenCalled();
});

it("refuses a session whose recorded directory is gone even when the root resolves", async () => {
  fixture.cwd = path.join(fixture.root, "removed-worktree");
  expect(() => browserHandlers.browser.metadata(request)).toThrow(new IpcError("This session's workspace is missing."));
});
