import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { BrowserService } from "../../../src/main/browser/service";
import type { BrowserTabLifecycle } from "../../../src/main/browser/cdp";
import { BrowserConnections } from "../../../src/main/browser/connections";
const endpoints = vi.hoisted(() => [] as { scope: unknown; tabs: BrowserTabLifecycle; dispose: ReturnType<typeof vi.fn> }[]);
vi.mock("electron", () => ({ WebContentsView: vi.fn() }));
vi.mock("../../../src/main/browser/cdp", () => ({ ScopedBrowserCdp: class {
  dispose = vi.fn().mockResolvedValue(undefined);
  constructor(_service: unknown, public scope: unknown, public tabs: BrowserTabLifecycle) { endpoints.push(this); }
  async start() { return "ws://127.0.0.1:1234/scoped"; }
} }));
let directory: string;
beforeEach(async () => { endpoints.length = 0; directory = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), "browser-connections-"))); });
afterEach(async () => { await fs.rm(directory, { recursive: true, force: true }); });
const session = { sessionId: "session", projectId: "project", cwd: "/untrusted" };
function fixture() {
  const commands = { request: vi.fn().mockResolvedValue({ tabId: "new-tab" }) };
  const service = { open: vi.fn().mockResolvedValue({ tabId: "new-tab" }), invoke: vi.fn().mockResolvedValue({}), disposeSession: vi.fn() };
  const connections = new BrowserConnections({ sessionRoot: () => ({ directory, root: null }) }, commands, path.join(directory, "artifacts"), service as unknown as BrowserService);
  return { commands, service, connections };
}
it("binds native tabs and artifact output to the authenticated workspace", async () => {
  const { connections, commands, service } = fixture();
  const connection = await connections.connect(session);
  expect(connection.root).toBe(directory);
  expect(connection.outputDir.startsWith(path.join(directory, "artifacts"))).toBe(true);
  expect(endpoints[0]!.scope).toEqual({ sessionId: "session", projectId: "project", root: directory });
  const signal = new AbortController().signal;
  await expect(endpoints[0]!.tabs.open("https://example.com", signal)).resolves.toBe("new-tab");
  expect(commands.request).toHaveBeenCalledWith(expect.objectContaining({ kind: "open-url", rootDirectory: directory, projectId: "project", root: null }), signal);
  expect(service.open).toHaveBeenCalledWith({ sessionId: "session", projectId: "project", root: directory }, { tabId: "new-tab", url: "https://example.com" });
  await connections.connect(session); expect(endpoints).toHaveLength(1);
  connections.revoke(session.sessionId);
  await vi.waitFor(() => expect(endpoints[0]!.dispose).toHaveBeenCalled());
  await connections.connect(session); expect(endpoints).toHaveLength(2);
  await connections.dispose(); expect(endpoints[1]!.dispose).toHaveBeenCalled();
});
it("cancellation prevents resource creation, including after renderer admission", async () => {
  const { connections, commands, service } = fixture();
  const controller = new AbortController(); controller.abort(new Error("cancelled"));
  await expect(connections.connect(session, controller.signal)).rejects.toThrow("cancelled");
  expect(endpoints).toHaveLength(0);
  await connections.connect(session);
  commands.request.mockImplementation(async () => { throw new Error("renderer command cancelled"); });
  await expect(endpoints[0]!.tabs.open("https://example.com", controller.signal)).rejects.toThrow("cancelled");
  expect(service.open).not.toHaveBeenCalled();
  await connections.dispose();
});
it("disposePages closes every page when the workspace is gone", async () => {
  const { service } = fixture();
  const connections = new BrowserConnections({ sessionRoot: () => null }, { request: vi.fn() }, path.join(directory, "artifacts"), service as unknown as BrowserService);
  await connections.disposePages(session);
  expect(service.disposeSession).toHaveBeenCalledWith("session", undefined);
});
it("disposePages closes the session's native pages but keeps its endpoint", async () => {
  const { connections, service } = fixture();
  await connections.connect(session);
  await connections.disposePages(session);
  expect(service.disposeSession).toHaveBeenCalledWith("session", { sessionId: "session", projectId: "project", root: directory });
  expect(endpoints[0]!.dispose).not.toHaveBeenCalled();
  await connections.dispose();
});
it("disposePages from a superseded workspace change cannot close the pages of the newer one", async () => {
  const { service } = fixture();
  const dirs = ["/work-b", "/work-c"];
  const connections = new BrowserConnections({ sessionRoot: () => ({ directory: dirs.shift()!, root: null }) }, { request: vi.fn() }, path.join(directory, "artifacts"), service as unknown as BrowserService);
  let resolveB!: (value: string) => void;
  const realpath = vi.spyOn(fs, "realpath").mockImplementation((async (target: string) => target === "/work-b" ? new Promise<string>(resolve => { resolveB = resolve; }) : target) as typeof fs.realpath);
  try {
    const first = connections.disposePages(session);
    await connections.disposePages(session);
    resolveB("/work-b");
    await first;
  } finally { realpath.mockRestore(); }
  // B's late completion would keep B and close C's pages.
  expect(service.disposeSession.mock.calls).toEqual([["session", { sessionId: "session", projectId: "project", root: "/work-c" }]]);
});
it("the newest disposePages still wins when each call follows a revoke, as the bridge's tokenFor does", async () => {
  const { service } = fixture();
  const dirs = ["/work-b", "/work-c"];
  const connections = new BrowserConnections({ sessionRoot: () => ({ directory: dirs.shift()!, root: null }) }, { request: vi.fn() }, path.join(directory, "artifacts"), service as unknown as BrowserService);
  let resolveB!: (value: string) => void;
  const realpath = vi.spyOn(fs, "realpath").mockImplementation((async (target: string) => target === "/work-b" ? new Promise<string>(resolve => { resolveB = resolve; }) : target) as typeof fs.realpath);
  try {
    connections.revoke(session.sessionId);
    const first = connections.disposePages(session);
    connections.revoke(session.sessionId);
    await connections.disposePages(session);
    resolveB("/work-b");
    await first;
  } finally { realpath.mockRestore(); }
  expect(service.disposeSession.mock.calls).toEqual([["session", { sessionId: "session", projectId: "project", root: "/work-c" }]]);
});
