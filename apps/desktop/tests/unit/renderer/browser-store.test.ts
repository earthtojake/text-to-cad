import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useBrowser } from "@renderer/state/browser";
import { useExplorer } from "@renderer/state/explorer";
import type { BrowserTarget } from "@shared/browser";

const binding = { sessionId: "browser-session", projectId: "browser-project", root: null, tabId: "browser-tab" };
const target: BrowserTarget = { ...binding, root: "/browser-project", generation: 0, title: "Form", url: "https://example.com/", loading: false, canGoBack: false, canGoForward: false, visible: false, logs: [] };
let element: HTMLDivElement;
let cleanups: (() => void)[];

beforeEach(() => {
  vi.useFakeTimers(); vi.clearAllMocks();
  useBrowser.setState({ targets: {}, errors: {}, consoles: {} });
  useExplorer.setState({ sessionId: "browser-session", projectId: binding.projectId, root: null, tabs: [{ sessionId: "browser-session", id: binding.tabId, projectId: binding.projectId, kind: "browser", root: null, url: target.url, order: 0 }], ready: true });
  vi.mocked(window.textToCad.browser.ensure).mockResolvedValue(target);
  vi.mocked(window.textToCad.browser.metadata).mockResolvedValue(target);
  element = document.createElement("div");
  element.getBoundingClientRect = () => ({ x: 700, y: 70, width: 600, height: 500, left: 700, top: 70, right: 1300, bottom: 570, toJSON() {} });
  document.body.append(element);
  cleanups = [];
});
afterEach(() => {
  cleanups.forEach(clean => clean());
  element.remove();
  vi.clearAllTimers(); vi.useRealTimers();
});
const mount = () => { const cleanup = useBrowser.getState().mount(binding, target.url, element); cleanups.push(cleanup); return cleanup; };

// These exercise the UI/native lifetime seam, not Chromium's implementation.
describe("browser presentation lifetime", () => {
  it("hides on unmount and reacquires the same page identity without a navigation or close", async () => {
    const release = mount();
    await vi.advanceTimersByTimeAsync(1);
    const first = vi.mocked(window.textToCad.browser.present).mock.calls[0]![0];
    expect(first).toMatchObject({ ...binding, bounds: { x: 700, y: 70, width: 600, height: 500 } });
    release();
    expect(window.textToCad.browser.present).toHaveBeenLastCalledWith({ ...binding, lease: first.lease, bounds: null });
    mount();
    await vi.advanceTimersByTimeAsync(1);
    const latest = vi.mocked(window.textToCad.browser.present).mock.calls.at(-1)![0];
    expect(latest.lease).not.toBe(first.lease);
    expect(latest.tabId).toBe(first.tabId);
    expect(window.textToCad.browser.navigate).not.toHaveBeenCalled();
    expect(window.textToCad.browser.close).not.toHaveBeenCalled();
  });
  it("never presents an old project after its asynchronous page creation finishes", async () => {
    let finish!: (target: BrowserTarget) => void;
    vi.mocked(window.textToCad.browser.ensure).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    const release = mount();
    release();
    useExplorer.setState({ sessionId: "browser-session", projectId: "another-project", tabs: [] });
    finish(target);
    await vi.advanceTimersByTimeAsync(1);
    expect(vi.mocked(window.textToCad.browser.present).mock.calls.every(([request]) => request.bounds === null)).toBe(true);
    expect(useExplorer.getState().tabs).toEqual([]);
  });
  it("hides native content while a dialog overlays it and restores afterward", async () => {
    mount(); await vi.advanceTimersByTimeAsync(1);
    const dialog = document.createElement("div"); dialog.setAttribute("role", "dialog"); document.body.append(dialog);
    await vi.advanceTimersByTimeAsync(20);
    expect(vi.mocked(window.textToCad.browser.present).mock.calls.at(-1)![0].bounds).toBeNull();
    dialog.remove(); await vi.advanceTimersByTimeAsync(20);
    expect(vi.mocked(window.textToCad.browser.present).mock.calls.at(-1)![0].bounds).not.toBeNull();
  });
  it("closing a browser strip tab destroys the owned native target", () => {
    useExplorer.getState().close(binding.tabId);
    expect(window.textToCad.browser.close).toHaveBeenCalledWith(binding);
  });
});

describe("browser chrome cost", () => {
  it("coalesces a burst of DOM mutations into one measurement per animation frame", async () => {
    mount(); await vi.advanceTimersByTimeAsync(1);
    const measure = vi.spyOn(element, "getBoundingClientRect");
    const query = vi.spyOn(document, "querySelector");
    // A streamed transcript: many mutations, each delivered in its own
    // microtask, all inside one frame.
    for (let token = 0; token < 50; token += 1) { document.body.append(document.createElement("span")); await Promise.resolve(); }
    await vi.advanceTimersByTimeAsync(20);
    expect(measure.mock.calls.length).toBeLessThanOrEqual(1);
    expect(query.mock.calls.length).toBeLessThanOrEqual(1);
  });
  it("polls without console lines unless the console is open", async () => {
    mount(); await vi.advanceTimersByTimeAsync(501);
    expect(window.textToCad.browser.metadata).toHaveBeenLastCalledWith({ ...binding, logs: false });
    useBrowser.getState().setConsoleOpen(binding.tabId, true);
    await vi.advanceTimersByTimeAsync(1);
    expect(window.textToCad.browser.metadata).toHaveBeenLastCalledWith({ ...binding, logs: true });
  });
  it("keeps the console lines it has when a poll carries none", async () => {
    vi.mocked(window.textToCad.browser.ensure).mockResolvedValue({ ...target, logs: [{ level: "error", message: "boom" }], errors: 1 });
    vi.mocked(window.textToCad.browser.metadata).mockResolvedValue({ ...target, logs: [], errors: 1 });
    mount(); await vi.advanceTimersByTimeAsync(501);
    expect(useBrowser.getState().targets[binding.tabId]).toMatchObject({ logs: [{ level: "error", message: "boom" }], errors: 1 });
  });
  it("does not publish a new state when a poll changed nothing", async () => {
    mount(); await vi.advanceTimersByTimeAsync(1);
    const changes = vi.fn();
    const unsubscribe = useBrowser.subscribe(changes);
    await vi.advanceTimersByTimeAsync(2_000);
    unsubscribe();
    expect(window.textToCad.browser.metadata).toHaveBeenCalled();
    expect(changes).not.toHaveBeenCalled();
  });
  it("stops polling once the workspace refuses the tab, and resumes after a navigation or wake", async () => {
    vi.mocked(window.textToCad.browser.metadata).mockRejectedValue(new Error("Error invoking remote method 'text-to-cad:browser.metadata': IpcError: This session's workspace is missing."));
    mount(); await vi.advanceTimersByTimeAsync(3_000);
    expect(window.textToCad.browser.metadata).toHaveBeenCalledTimes(1);
    expect(useBrowser.getState().errors[binding.tabId]).toContain("This session's workspace is missing.");
    vi.mocked(window.textToCad.browser.metadata).mockResolvedValue(target);
    vi.mocked(window.textToCad.browser.navigate).mockResolvedValue(target);
    await useBrowser.getState().navigate(binding, { direction: "reload" });
    await vi.advanceTimersByTimeAsync(1_000);
    expect(vi.mocked(window.textToCad.browser.metadata).mock.calls.length).toBeGreaterThan(2);
    expect(useBrowser.getState().errors[binding.tabId]).toBeUndefined();
  });
  it.each(["This browser tab is not available in this session's workspace.", "that project is no longer open"])("stops polling a tab main refuses with %s", async (refusal) => {
    vi.mocked(window.textToCad.browser.metadata).mockRejectedValue(new Error(`Error invoking remote method 'text-to-cad:browser.metadata': IpcError: ${refusal}`));
    mount(); await vi.advanceTimersByTimeAsync(3_000);
    expect(window.textToCad.browser.metadata).toHaveBeenCalledTimes(1);
  });
  it("does not publish a new state when the same failure repeats", async () => {
    vi.mocked(window.textToCad.browser.metadata).mockRejectedValue(new Error("transient"));
    mount(); await vi.advanceTimersByTimeAsync(501);
    const changes = vi.fn();
    const unsubscribe = useBrowser.subscribe(changes);
    await vi.advanceTimersByTimeAsync(2_000);
    unsubscribe();
    expect(vi.mocked(window.textToCad.browser.metadata).mock.calls.length).toBeGreaterThan(2);
    expect(changes).not.toHaveBeenCalled();
  });
  it("keeps polling through a failure that is not a refusal", async () => {
    vi.mocked(window.textToCad.browser.metadata).mockRejectedValueOnce(new Error("transient")).mockResolvedValue(target);
    mount(); await vi.advanceTimersByTimeAsync(1_600);
    expect(vi.mocked(window.textToCad.browser.metadata).mock.calls.length).toBeGreaterThan(1);
    expect(useBrowser.getState().errors[binding.tabId]).toBeUndefined();
  });
  it("opening the console wakes a refused tab's poll", async () => {
    vi.mocked(window.textToCad.browser.metadata).mockRejectedValueOnce(new Error("This session is no longer active.")).mockResolvedValue(target);
    mount(); await vi.advanceTimersByTimeAsync(2_000);
    expect(window.textToCad.browser.metadata).toHaveBeenCalledTimes(1);
    useBrowser.getState().setConsoleOpen(binding.tabId, true);
    await vi.advanceTimersByTimeAsync(1);
    expect(window.textToCad.browser.metadata).toHaveBeenLastCalledWith({ ...binding, logs: true });
  });
});
