import { beforeEach, describe, expect, it } from "vitest";
import { createTabStore, TAB_RECORD_VERSION } from "@text-to-cad/ui/tab-store";
import type { JsonValue } from "@text-to-cad/ui/file-viewer";
import { desktopTabRecord, desktopTabStore, forgetTabStore } from "@renderer/features/explorer/adapters/tabStore";

const KEY = "text-to-cad.tabs.v1";
const view = (camera: JsonValue): JsonValue => ({ version: 2, camera, display: null, renderer: {} });

beforeEach(() => { localStorage.clear(); sessionStorage.clear(); for (const id of ["tab-a", "tab-b"]) forgetTabStore(id); });

describe("Desktop tab store", () => {
  it("keeps one record per tab, whole, under one localStorage entry, and reads it back for a reloaded window", () => {
    const a = desktopTabStore("tab-a");
    expect(desktopTabStore("tab-a")).toBe(a);
    expect(localStorage.getItem(KEY)).toBeNull();
    a.settings.update({ toolStack: { panels: { tree: { width: 240 } }, collapsed: {} }, appearance: "dark" });
    a.files.write("root", "a.step", "step", view({ position: [1, 2, 3] }));
    const stored = JSON.parse(localStorage.getItem(KEY)!);
    expect(Object.keys(stored)).toEqual(["tab-a"]);
    expect(stored["tab-a"].version).toBe(TAB_RECORD_VERSION);
    expect(stored["tab-a"].settings.toolStack).toEqual({ panels: { tree: { width: 240 } }, collapsed: {} });
    expect(Object.keys(stored["tab-a"].files)).toEqual([JSON.stringify(["root", "a.step", "step"])]);
    // The window reloads: a fresh store over the same tab reads the same record.
    const reloaded = createTabStore(desktopTabRecord("tab-a"));
    expect(reloaded.getSnapshot()).toEqual(a.getSnapshot());
  });

  it("gives every tab its own settings and file views: nothing is global", () => {
    const a = desktopTabStore("tab-a");
    const b = desktopTabStore("tab-b");
    a.settings.update({ toolStack: { panels: { tree: { width: 300 } }, collapsed: {} }, appearance: "dark" });
    a.files.write("root", "a.step", "step", view("a"));
    expect(b.settings.getSnapshot().toolStack).toEqual({ panels: {}, collapsed: {} });
    expect(b.settings.getSnapshot().appearance).toBe("system");
    expect(b.files.forRoot("root")).toEqual({});
    b.files.write("root", "a.step", "step", view("b"));
    expect(a.files.forRoot("root")).toEqual({ [JSON.stringify(["a.step", "step"])]: view("a") });
    expect(Object.keys(JSON.parse(localStorage.getItem(KEY)!))).toEqual(["tab-a", "tab-b"]);
  });

  it("drops a tab's record with the tab, and leaves the other tabs' as they are", () => {
    const a = desktopTabStore("tab-a");
    const b = desktopTabStore("tab-b");
    a.settings.update({ appearance: "dark" });
    b.settings.update({ appearance: "light" });
    forgetTabStore("tab-a");
    expect(Object.keys(JSON.parse(localStorage.getItem(KEY)!))).toEqual(["tab-b"]);
    expect(desktopTabStore("tab-a")).not.toBe(a);
    expect(desktopTabStore("tab-a").settings.getSnapshot().appearance).toBe("system");
    expect(desktopTabStore("tab-b")).toBe(b);
    expect(() => forgetTabStore("never-opened")).not.toThrow();
  });

  it("neither reads nor removes what older versions stored", () => {
    const retired: [string, string][] = [["cad-viewer:orbit:v1", JSON.stringify({ speed: 2 })], ["cad-viewer:animation:v1", JSON.stringify({ autoplay: true })],
      ["cad-viewer:tool-stack:v2", JSON.stringify({ panels: { tree: { width: 300 } }, collapsed: {} })], ["text-to-cad.fileViewer.v1", JSON.stringify({ x: 1 })]];
    for (const [key, value] of retired) localStorage.setItem(key, value);
    const a = desktopTabStore("tab-a");
    expect(a.settings.getSnapshot().toolStack).toEqual({ panels: {}, collapsed: {} });
    expect("orbit" in a.settings.getSnapshot()).toBe(false);
    a.settings.update({ appearance: "dark" });
    forgetTabStore("tab-a");
    for (const key of ["cad-viewer:orbit:v1", "cad-viewer:animation:v1", "cad-viewer:tool-stack:v2", "text-to-cad.fileViewer.v1"]) expect(localStorage.getItem(key)).not.toBeNull();
  });
});
