/**
 * BrowserService against a fake Electron: the lifetime seams that do not need
 * Chromium — hiding pages when their app window reloads or crashes, what
 * counts as a new page for "Add to prompt", download refusal and Cmd+R.
 * Chromium's side is `tests/e2e/browser-service.spec.ts`.
 */
import { EventEmitter } from "node:events";
import { beforeEach, expect, it, vi } from "vitest";

const electron = await vi.hoisted(async () => {
  const { EventEmitter } = await import("node:events");
  const sessions = new Map<string, InstanceType<typeof EventEmitter>>();
  const partitionSession = (partition: string) => {
    const session = sessions.get(partition) ?? Object.assign(new EventEmitter(), { setPermissionRequestHandler: () => {}, setPermissionCheckHandler: () => {} });
    sessions.set(partition, session);
    return session;
  };
  class FakeContents extends EventEmitter {
    url = "about:blank"; focused = false; destroyed = false;
    reload = vi.fn(); focus = vi.fn();
    navigationHistory = { canGoBack: () => false, canGoForward: () => false };
    constructor(public session: InstanceType<typeof EventEmitter>) { super(); }
    setWindowOpenHandler() {}
    async loadURL(url: string) { this.url = url; }
    getURL() { return this.url; } getTitle() { return ""; } isLoading() { return false; }
    isDestroyed() { return this.destroyed; } isFocused() { return this.focused; }
    // Chromium reports `destroyed` after close() returns; a test can hold it back.
    close() { this.destroyed = true; if (!electron.state.deferDestroy) this.emit("destroyed"); }
    stop() {}
  }
  class WebContentsView {
    webContents: FakeContents;
    setBounds = vi.fn(); setVisible = vi.fn();
    constructor(options: { webPreferences: { partition: string } }) { this.webContents = new FakeContents(partitionSession(options.webPreferences.partition)); }
  }
  return { sessions, FakeContents, WebContentsView, state: { deferDestroy: false } };
});
vi.mock("electron", () => ({ WebContentsView: electron.WebContentsView, app: {}, session: {} }));
import { BrowserService } from "@main/browser/service";
import { browserSessionKey } from "@main/browser/storage";

type Contents = InstanceType<typeof electron.FakeContents>;
const scope = { sessionId: "session-a", projectId: "project", root: "/work" };
const bounds = { x: 10, y: 20, width: 300, height: 200 };
function owner() {
  const webContents = Object.assign(new EventEmitter(), { getZoomFactor: () => 1, focus: vi.fn(), sendInputEvent: vi.fn() });
  return Object.assign(new EventEmitter(), { webContents, focused: true, isFocused() { return this.focused; }, isDestroyed: () => false, contentView: { addChildView: vi.fn(), removeChildView: vi.fn() } }) as unknown as Electron.BrowserWindow & { webContents: EventEmitter };
}
let service: BrowserService;
beforeEach(() => { service = new BrowserService(); electron.sessions.clear(); electron.state.deferDestroy = false; });
const contents = (tabId: string) => service.contents(scope, tabId) as unknown as Contents;

it("hides every page an app window presented when that window reloads or its renderer dies", async () => {
  const window = owner();
  await service.open(scope, { tabId: "one", url: "https://example.com/" });
  await service.open(scope, { tabId: "two", url: "https://example.com/two" });
  service.present(scope, "one", window, "lease-1", bounds);
  expect(service.metadata(scope, "one").visible).toBe(true);
  // Loading starts before beforeunload: a reload cancelled over unsaved drafts leaves pages shown.
  window.webContents.emit("did-start-loading");
  expect(service.metadata(scope, "one").visible).toBe(true);
  window.webContents.emit("did-navigate", {}, "app://index.html");
  expect(service.metadata(scope, "one").visible).toBe(false);
  // The remounted tab presents again under a new lease.
  service.present(scope, "two", window, "lease-2", bounds);
  expect(service.metadata(scope, "two").visible).toBe(true);
  // A subframe failure or an aborted navigation leaves pages shown; a failed main-frame load hides them.
  window.webContents.emit("did-fail-load", {}, -102, "ERR_CONNECTION_REFUSED", "http://localhost:5173/", false);
  window.webContents.emit("did-fail-load", {}, -3, "ERR_ABORTED", "http://localhost:5173/", true);
  expect(service.metadata(scope, "two").visible).toBe(true);
  window.webContents.emit("did-fail-load", {}, -102, "ERR_CONNECTION_REFUSED", "http://localhost:5173/", true);
  expect(service.metadata(scope, "two").visible).toBe(false);
  service.present(scope, "two", window, "lease-2b", bounds);
  window.webContents.emit("render-process-gone", {}, { reason: "crashed" });
  expect(service.metadata(scope, "two").visible).toBe(false);
  // A stale lease's cleanup after the reload cannot hide a newer presentation.
  service.present(scope, "two", window, "lease-3", bounds);
  service.present(scope, "two", window, "lease-2", null);
  expect(service.metadata(scope, "two").visible).toBe(true);
});

it("counts a new document, not a pushState or fragment change, as a page change", async () => {
  await service.open(scope, { tabId: "spa", url: "https://example.com/" });
  const start = service.metadata(scope, "spa").generation;
  contents("spa").emit("did-start-navigation", { isMainFrame: true, isSameDocument: true });
  contents("spa").emit("did-start-navigation", { isMainFrame: false, isSameDocument: false });
  expect(service.metadata(scope, "spa").generation).toBe(start);
  contents("spa").emit("did-start-navigation", { isMainFrame: true, isSameDocument: false });
  expect(service.metadata(scope, "spa").generation).toBe(start + 1);
});

it("cancels background downloads with an error line, and lets the person's own foreground download through", async () => {
  const window = owner();
  await service.open(scope, { tabId: "dl", url: "https://example.com/" });
  const partition = contents("dl").session;
  expect(partition.listenerCount("will-download")).toBe(1);
  await service.open(scope, { tabId: "dl-2", url: "https://example.com/" });
  expect(partition.listenerCount("will-download")).toBe(1);
  const item = { getFilename: () => "report.zip", getURL: () => "https://example.com/report.zip" };
  const download = () => { const event = { preventDefault: vi.fn() }; partition.emit("will-download", event, item, contents("dl")); return event.preventDefault.mock.calls.length > 0; };
  // Hidden (a background session, or an agent's page nobody is looking at).
  expect(download()).toBe(true);
  expect(service.metadata(scope, "dl").logs.at(-1)).toMatchObject({ level: "error", message: expect.stringContaining("report.zip") });
  expect(service.metadata(scope, "dl", false)).toMatchObject({ logs: [], errors: 1 });
  // Shown but not focused: still not the person's gesture.
  service.present(scope, "dl", window, "lease", bounds);
  expect(download()).toBe(true);
  // Shown and focused in the focused window, but no recent press: an agent
  // driving the page the person last clicked into.
  contents("dl").focused = true;
  expect(download()).toBe(true);
  // The person's own click, just now: the native dialog is theirs.
  let now = 1_000_000;
  const clock = vi.spyOn(Date, "now").mockImplementation(() => now);
  contents("dl").emit("before-mouse-event", {}, { type: "mouseMove" });
  expect(download()).toBe(true);
  contents("dl").emit("before-mouse-event", {}, { type: "mouseDown" });
  now += 500;
  expect(download()).toBe(false);
  // Stale after two seconds.
  now += 2_000;
  expect(download()).toBe(true);
  // A key press counts too, unless an agent sent input to the page around it.
  contents("dl").emit("before-input-event", {}, { type: "keyDown" });
  expect(download()).toBe(false);
  service.noteAutomatedInput(scope, "dl");
  contents("dl").emit("before-input-event", {}, { type: "keyDown" });
  expect(download()).toBe(true);
  now += 2_500;
  contents("dl").emit("before-input-event", {}, { type: "keyDown" });
  expect(download()).toBe(false);
  (window as unknown as { focused: boolean }).focused = false;
  expect(download()).toBe(true);
  clock.mockRestore();
});

it("names each partition after its session so a deleted session's storage can be found", async () => {
  await service.open(scope, { tabId: "p1", url: "https://example.com/" });
  await service.open({ ...scope, sessionId: "session-b" }, { tabId: "p2", url: "https://example.com/" });
  const [first, second] = [...electron.sessions.keys()];
  expect(first).toMatch(new RegExp(`^persist:browser-${browserSessionKey("session-a")}-[0-9a-f]{32}$`));
  expect(second).toMatch(new RegExp(`^persist:browser-${browserSessionKey("session-b")}-[0-9a-f]{32}$`));
});

it("reloads only the focused, presented page", async () => {
  const window = owner();
  await service.open(scope, { tabId: "r", url: "https://example.com/" });
  expect(service.reloadFocused(window)).toBe(false);
  service.present(scope, "r", window, "lease", bounds);
  expect(service.reloadFocused(window)).toBe(false);
  contents("r").focused = true;
  expect(service.reloadFocused(window)).toBe(true);
  expect(contents("r").reload).toHaveBeenCalledTimes(1);
});

it("hands a key from the focused page to its own app window, and only from there", async () => {
  const window = owner();
  const other = owner();
  const key = { keyCode: "W", modifiers: ["meta" as const] };
  await service.open(scope, { tabId: "w", url: "https://example.com/" });
  service.present(scope, "w", window, "lease", bounds);
  expect(service.forwardFromFocused(window, key)).toBe(false);
  contents("w").focused = true;
  expect(service.forwardFromFocused(other, key)).toBe(false);
  expect(service.forwardFromFocused(window, key)).toBe(true);
  const app = window.webContents as unknown as { focus: ReturnType<typeof vi.fn>; sendInputEvent: ReturnType<typeof vi.fn> };
  expect(app.focus).toHaveBeenCalledTimes(1);
  expect(app.sendInputEvent.mock.calls.map(([event]) => event)).toEqual([
    { type: "keyDown", ...key },
    { type: "keyUp", ...key },
  ]);
});

it("disposeSession keeps the pages of the scope it is told to keep, and closes the session's others", async () => {
  const other = { ...scope, root: "/elsewhere" };
  await service.open(scope, { tabId: "kept", url: "https://example.com/" });
  await service.open(other, { tabId: "gone", url: "https://example.com/" });
  await service.open({ ...scope, sessionId: "session-b" }, { tabId: "foreign", url: "https://example.com/" });
  service.disposeSession(scope.sessionId, scope);
  expect(service.list(scope).map(tab => tab.tabId)).toEqual(["kept"]);
  expect(service.list(other)).toEqual([]);
  expect(service.list({ ...scope, sessionId: "session-b" })).toHaveLength(1);
  service.disposeSession(scope.sessionId);
  expect(service.list(scope)).toEqual([]);
});

it("does not evict a page re-opened under the same id when the old one reports destroyed late", async () => {
  electron.state.deferDestroy = true;
  await service.open(scope, { tabId: "x", url: "https://example.com/" });
  const old = contents("x");
  service.close(scope, "x");
  await service.open(scope, { tabId: "x", url: "https://example.com/again" });
  old.emit("destroyed");
  expect(service.list(scope).map(tab => tab.tabId)).toEqual(["x"]);
});

it("reads console messages from the details event, and still from the deprecated positional form", async () => {
  await service.open(scope, { tabId: "log", url: "https://example.com/" });
  contents("log").emit("console-message", { level: "warning", message: "from details" });
  contents("log").emit("console-message", { level: "error", message: "boom" });
  contents("log").emit("console-message", {}, 3, "positional");
  expect(service.metadata(scope, "log").logs).toEqual([
    { level: "warn", message: "from details" }, { level: "error", message: "boom" }, { level: "error", message: "positional" },
  ]);
});

it("drops its app-window `closed` listener when the page closes", async () => {
  const window = owner();
  await service.open(scope, { tabId: "w", url: "https://example.com/" });
  service.present(scope, "w", window, "lease", bounds);
  expect(window.listenerCount("closed")).toBe(1);
  service.close(scope, "w");
  expect(window.listenerCount("closed")).toBe(0);
});

it("lets more than ten CDP connections listen on its events without a MaxListeners warning", async () => {
  const warn = vi.fn();
  process.on("warning", warn);
  try {
    // Each scoped CDP connection adds one `opened` and one `closed` listener.
    for (let connection = 0; connection < 12; connection += 1) { service.events.on("opened", () => {}); service.events.on("closed", () => {}); }
    await new Promise(resolve => setImmediate(resolve));
  } finally { process.off("warning", warn); }
  expect(warn).not.toHaveBeenCalled();
});

it("still warns about a listener leak, past a finite cap", async () => {
  const warn = vi.fn();
  process.on("warning", warn);
  try {
    for (let listener = 0; listener < 101; listener += 1) service.events.on("opened", () => {});
    await new Promise(resolve => setImmediate(resolve));
  } finally { process.off("warning", warn); service.events.removeAllListeners("opened"); }
  expect(warn).toHaveBeenCalledWith(expect.objectContaining({ name: "MaxListenersExceededWarning" }));
});
