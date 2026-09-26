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
  useBrowser.setState({ targets: {}, errors: {} });
  useExplorer.setState({ sessionId: "browser-session", projectId: binding.projectId, root: null, tabs: [{ sessionId: "browser-session", id: binding.tabId, projectId: binding.projectId, kind: "browser", root: null, url: target.url, order: 0 }], ready: true });
  vi.mocked(window.hardcore.browser.ensure).mockResolvedValue(target);
  vi.mocked(window.hardcore.browser.metadata).mockResolvedValue(target);
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
    const first = vi.mocked(window.hardcore.browser.present).mock.calls[0]![0];
    expect(first).toMatchObject({ ...binding, bounds: { x: 700, y: 70, width: 600, height: 500 } });
    release();
    expect(window.hardcore.browser.present).toHaveBeenLastCalledWith({ ...binding, lease: first.lease, bounds: null });
    mount();
    await vi.advanceTimersByTimeAsync(1);
    const latest = vi.mocked(window.hardcore.browser.present).mock.calls.at(-1)![0];
    expect(latest.lease).not.toBe(first.lease);
    expect(latest.tabId).toBe(first.tabId);
    expect(window.hardcore.browser.navigate).not.toHaveBeenCalled();
    expect(window.hardcore.browser.close).not.toHaveBeenCalled();
  });
  it("never presents an old project after its asynchronous page creation finishes", async () => {
    let finish!: (target: BrowserTarget) => void;
    vi.mocked(window.hardcore.browser.ensure).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    const release = mount();
    release();
    useExplorer.setState({ sessionId: "browser-session", projectId: "another-project", tabs: [] });
    finish(target);
    await vi.advanceTimersByTimeAsync(1);
    expect(vi.mocked(window.hardcore.browser.present).mock.calls.every(([request]) => request.bounds === null)).toBe(true);
    expect(useExplorer.getState().tabs).toEqual([]);
  });
  it("hides native content while a dialog overlays it and restores afterward", async () => {
    mount(); await vi.advanceTimersByTimeAsync(1);
    const dialog = document.createElement("div"); dialog.setAttribute("role", "dialog"); document.body.append(dialog);
    await vi.advanceTimersByTimeAsync(1);
    expect(vi.mocked(window.hardcore.browser.present).mock.calls.at(-1)![0].bounds).toBeNull();
    dialog.remove(); await vi.advanceTimersByTimeAsync(1);
    expect(vi.mocked(window.hardcore.browser.present).mock.calls.at(-1)![0].bounds).not.toBeNull();
  });
  it("closing a browser strip tab destroys the owned native target", () => {
    useExplorer.getState().close(binding.tabId);
    expect(window.hardcore.browser.close).toHaveBeenCalledWith(binding);
  });
});
