/** The scoped CDP endpoint keeps download policy with the host, in both protocol spellings. */
import { EventEmitter } from "node:events";
import { afterEach, expect, it, vi } from "vitest";
import { WebSocket } from "ws";
vi.mock("electron", () => ({ WebContentsView: vi.fn(), app: {}, session: {} }));
import { ScopedBrowserCdp } from "@main/browser/cdp";
import type { BrowserService } from "@main/browser/service";

const scope = { sessionId: "session", projectId: "project", root: "/work" };
const sendCommand = vi.fn(async (method: string) => {
  if (method === "Target.getTargetInfo") return { targetInfo: { targetId: "native-target" } };
  if (method === "Target.attachToTarget") return { sessionId: "native-session" };
  return {};
});
const contents = { isDestroyed: () => false, debugger: Object.assign(new EventEmitter(), { isAttached: () => true, attach: vi.fn(), sendCommand }) };
/** The contents a tab id shows now; a test re-opens the tab over `reopened`. */
const reopened = { isDestroyed: () => false, debugger: Object.assign(new EventEmitter(), { isAttached: () => true, attach: vi.fn(), sendCommand: vi.fn(async (method: string) => {
  if (method === "Target.getTargetInfo") return { targetInfo: { targetId: "new-target" } };
  if (method === "Target.attachToTarget") return { sessionId: "new-native-session" };
  return {};
}) }) };
let showing: typeof contents = contents;
const service = {
  events: new EventEmitter(),
  metadata: () => ({ tabId: "tab", title: "Page", url: "https://example.com/" }),
  contents: () => showing,
  list: () => [{ tabId: "tab" }],
  noteAutomatedInput: vi.fn(),
} as unknown as BrowserService & { noteAutomatedInput: ReturnType<typeof vi.fn> };
const tabs = { open: vi.fn(), show: vi.fn(), close: vi.fn() };
let endpoint: ScopedBrowserCdp | undefined;
afterEach(async () => { showing = contents; await endpoint?.dispose(); });

it("refuses Page.setDownloadBehavior as well as Browser.setDownloadBehavior on an attached page", async () => {
  endpoint = new ScopedBrowserCdp(service, scope, tabs);
  const socket = new WebSocket(await endpoint.start());
  await new Promise(resolve => socket.once("open", resolve));
  let id = 0;
  const call = (method: string, params: Record<string, unknown> = {}, sessionId?: string) => new Promise<{ result?: Record<string, unknown>; error?: { message: string } }>(resolve => {
    const message = { id: ++id, method, params, ...(sessionId ? { sessionId } : {}) };
    const listener = (bytes: Buffer) => { const reply = JSON.parse(bytes.toString()); if (reply.id === message.id) { socket.off("message", listener); resolve(reply); } };
    socket.on("message", listener);
    socket.send(JSON.stringify(message));
  });
  await call("Target.getTargets");
  const attached = await call("Target.attachToTarget", { targetId: "native-target", flatten: true });
  const sessionId = String(attached.result?.sessionId);
  const page = await call("Page.setDownloadBehavior", { behavior: "allow", downloadPath: "/tmp/anywhere" }, sessionId);
  expect(page.error?.message).toContain("Download policy");
  const browser = await call("Browser.setDownloadBehavior", { behavior: "allow", downloadPath: "/tmp/anywhere" });
  expect(browser.error?.message).toContain("Download policy");
  expect(sendCommand.mock.calls.some(([method]) => String(method).endsWith("setDownloadBehavior"))).toBe(false);
  // Ordinary page commands still reach the owned page.
  expect((await call("Page.enable", {}, sessionId)).error).toBeUndefined();
  expect(sendCommand).toHaveBeenCalledWith("Page.enable", {}, "native-session");
  expect(service.noteAutomatedInput).not.toHaveBeenCalled();
  // Agent input marks the page, so a download it triggers is not the person's gesture.
  await call("Input.dispatchMouseEvent", { type: "mousePressed", x: 1, y: 1, button: "left", clickCount: 1 }, sessionId);
  expect(service.noteAutomatedInput).toHaveBeenCalledWith(scope, "tab");
  socket.close();
});

/** A connected client: `call` for commands, `events` for what the endpoint pushes. */
async function client() {
  endpoint = new ScopedBrowserCdp(service, scope, tabs);
  const socket = new WebSocket(await endpoint.start());
  await new Promise(resolve => socket.once("open", resolve));
  let id = 0;
  const events: { method: string; params: Record<string, unknown>; sessionId?: string }[] = [];
  const call = (method: string, params: Record<string, unknown> = {}, sessionId?: string) => new Promise<{ result?: Record<string, unknown>; error?: { message: string } }>(resolve => {
    const message = { id: ++id, method, params, ...(sessionId ? { sessionId } : {}) };
    const listener = (bytes: Buffer) => { const reply = JSON.parse(bytes.toString()); if (reply.id === message.id) { socket.off("message", listener); resolve(reply); } };
    socket.on("message", listener);
    socket.send(JSON.stringify(message));
  });
  socket.on("message", bytes => { const value = JSON.parse(bytes.toString()); if (value.method) events.push(value); });
  return { socket, call, events };
}

it("tells the client its page sessions are gone when Electron's debugger detaches", async () => {
  const { socket, call, events } = await client();
  await call("Target.getTargets");
  const attached = await call("Target.attachToTarget", { targetId: "native-target", flatten: true });
  const sessionId = String(attached.result?.sessionId);
  // A renderer crash, or DevTools taking the page over.
  contents.debugger.emit("detach", {}, "target closed");
  await vi.waitFor(() => expect(events.find(item => item.method === "Target.detachedFromTarget")?.params).toEqual({ sessionId, targetId: "native-target" }));
  expect((await call("Page.enable", {}, sessionId)).error?.message).toBe("Unknown browser session");
  socket.close();
});

it("forgets a closed page's target id, and takes its listeners off the service's events with the connection", async () => {
  // The previous test's socket is still closing.
  await vi.waitFor(() => expect(service.events.listenerCount("closed")).toBe(0));
  const { socket, call } = await client();
  await call("Target.getTargets");
  expect((await call("Target.attachToTarget", { targetId: "native-target", flatten: true })).error).toBeUndefined();
  service.events.emit("closed", { ...scope, tabId: "tab" });
  // The id no longer names a target of this connection (the fake service would still hand out the page).
  expect((await call("Target.attachToTarget", { targetId: "native-target", flatten: true })).error?.message).toBe("Unknown browser target");
  expect(service.events.listenerCount("opened")).toBe(1);
  await new Promise(resolve => { socket.once("close", resolve); socket.close(); });
  await vi.waitFor(() => expect(service.events.listenerCount("closed")).toBe(0));
  expect(service.events.listenerCount("opened")).toBe(0);
});

it("a tab id re-opened over new contents gets its own session and target id, and the old contents' detach does not touch them", async () => {
  await vi.waitFor(() => expect(service.events.listenerCount("closed")).toBe(0));
  const { socket, call, events } = await client();
  await call("Target.getTargets");
  const first = String((await call("Target.attachToTarget", { targetId: "native-target", flatten: true })).result?.sessionId);
  // Archive, then a quick unarchive on the same tab id: the old contents never reports `closed`.
  showing = reopened as unknown as typeof contents;
  await call("Target.getTargets");
  const second = String((await call("Target.attachToTarget", { targetId: "new-target", flatten: true })).result?.sessionId);
  expect(second).not.toBe(first);
  contents.debugger.emit("detach", {}, "target closed");
  await vi.waitFor(() => expect(events.find(item => item.method === "Target.detachedFromTarget")?.params).toEqual({ sessionId: first, targetId: "native-target" }));
  expect((await call("Page.enable", {}, second)).error).toBeUndefined();
  service.events.emit("closed", { ...scope, tabId: "tab" });
  await vi.waitFor(() => expect(events.find(item => item.method === "Target.targetDestroyed")?.params).toEqual({ targetId: "new-target" }));
  await new Promise(resolve => { socket.once("close", resolve); socket.close(); });
});
