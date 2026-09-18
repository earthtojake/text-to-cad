import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { createBrowserActions } from "../../../src/main/browser/actions";
import type { BrowserTarget } from "../../../src/shared/browser";
vi.mock("electron", () => ({ WebContentsView: vi.fn() }));
let directory: string;
beforeEach(async () => { directory = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), "browser-action-"))); });
afterEach(async () => { await fs.rm(directory, { recursive: true, force: true }); });
const session = { sessionId: "session-a", projectId: "project-a", cwd: "/untrusted/session/cwd" };
function fixture() {
  const target: BrowserTarget = { tabId: "page", projectId: session.projectId, root: directory, url: "https://example.com/", generation: 0, title: "Example", loading: false, canGoBack: false, canGoForward: false, visible: true, logs: [] };
  const service = { open: vi.fn().mockResolvedValue(target), invoke: vi.fn().mockResolvedValue(target), list: vi.fn().mockReturnValue([target]) };
  const commands = { request: vi.fn().mockResolvedValue({ tabId: target.tabId }) };
  const actions = createBrowserActions({ sessionRoot: () => ({ directory, root: null }) }, commands, service);
  return { target, service, commands, actions };
}
it("waits for native readiness after creating the visible tab in the authenticated root", async () => {
  const { target, service, commands, actions } = fixture();
  let ready!: (value: BrowserTarget) => void;
  service.open.mockImplementation(() => new Promise(resolve => { ready = resolve; }));
  let finished = false;
  const result = actions.open_url!(session, { url: target.url }).then(value => { finished = true; return value; });
  await vi.waitFor(() => expect(service.open).toHaveBeenCalled());
  expect(finished).toBe(false);
  expect(commands.request).toHaveBeenCalledWith(expect.objectContaining({ kind: "open-url", root: null, rootDirectory: directory, projectId: session.projectId }), undefined);
  expect(service.open).toHaveBeenCalledWith({ projectId: session.projectId, root: directory }, { tabId: target.tabId, url: target.url });
  ready(target);
  await expect(result).resolves.toMatchObject({ tabId: target.tabId, opened: target.url });
});
it("rejects cancellation before creating or mutating a page", async () => {
  const { service, commands, actions } = fixture();
  const controller = new AbortController(); controller.abort(new Error("cancelled"));
  await expect(actions.open_url!(session, { url: "https://example.com" }, controller.signal)).rejects.toThrow("cancelled");
  await expect(actions.browser_input!(session, { tabId: "page", action: { action: "type", text: "x" } }, controller.signal)).rejects.toThrow("cancelled");
  expect(commands.request).not.toHaveBeenCalled(); expect(service.open).not.toHaveBeenCalled(); expect(service.invoke).not.toHaveBeenCalled();
});
it("rejects raw protocol input and serializes page screenshots for MCP", async () => {
  const { service, actions } = fixture();
  await expect(actions.browser_input!(session, { tabId: "page", action: { action: "Browser.getVersion" } })).rejects.toThrow();
  expect(service.invoke).not.toHaveBeenCalled();
  service.invoke.mockResolvedValue({ tabId: "page", data: "png", mimeType: "image/png" });
  await expect(actions.browser_screenshot!(session, { tabId: "page" })).resolves.toEqual({ tabId: "page", mimeType: "image/png", base64: "png" });
});
