import { beforeEach, describe, expect, it } from "vitest";
import { createStoredCadPreferences } from "@hardcore/ui/renderers/workspace";
import { desktopCadPreferences } from "@renderer/features/explorer/adapters/cadPersistence";

beforeEach(() => { localStorage.clear(); sessionStorage.clear(); });
describe("Desktop viewer preferences", () => {
  it("ignores retired CAD themes and tutorial state", () => {
    const retiredTheme = JSON.stringify({ version: 13, themeId: "cinematic", custom: { exposure: 1.2 } });
    localStorage.setItem("cad-viewer:theme", retiredTheme);
    localStorage.setItem("cad-viewer:tutorial-tips:v1", JSON.stringify({ version: 1, seen: ["copyReference", 5] }));
    expect(createStoredCadPreferences(localStorage).getSnapshot()).toEqual({ orbit: { speed: 1 }, toolStackWidth: 190 });
    expect(localStorage.getItem("cad-viewer:theme")).toBe(retiredTheme);
    localStorage.setItem("cad-viewer:tutorial-tips:v1", JSON.stringify({ version: 0, seen: ["copyReference"] }));
    expect(createStoredCadPreferences(localStorage).getSnapshot()).not.toHaveProperty("seenTips");
  });
  it("shares motion preferences across roots without reviving CAD themes or tutorial state", () => {
    const retiredTheme = JSON.stringify({ version: 13, themeId: "cinematic", custom: null });
    localStorage.setItem("cad-viewer:theme", retiredTheme);
    const firstRoot = desktopCadPreferences();
    const secondRoot = desktopCadPreferences();
    const orbit = { speed: 2 };
    firstRoot.update({ orbit });
    expect(secondRoot.getSnapshot().orbit).toEqual(orbit);
    expect(desktopCadPreferences().getSnapshot()).not.toHaveProperty("seenTips");
    expect(secondRoot.getSnapshot()).not.toHaveProperty("theme");
    expect(localStorage.getItem("cad-viewer:theme")).toBe(retiredTheme);
    expect(localStorage.getItem("cad-viewer:tutorial-tips:v1")).toBeNull();
    expect(localStorage.getItem("hardcore.cadPreferences.v1")).toBeNull();
    const beforeRetiredEvent = firstRoot.getSnapshot();
    localStorage.setItem("cad-viewer:theme", JSON.stringify({ version: 13, themeId: "system", custom: null }));
    window.dispatchEvent(new StorageEvent("storage", { key: "cad-viewer:theme" }));
    expect(firstRoot.getSnapshot()).toBe(beforeRetiredEvent);
    localStorage.setItem("cad-viewer:tutorial-tips:v1", JSON.stringify({ version: 1, seen: ["orbit"] }));
    window.dispatchEvent(new StorageEvent("storage", { key: "cad-viewer:tutorial-tips:v1" }));
    expect(firstRoot.getSnapshot()).toBe(beforeRetiredEvent);
    expect(firstRoot.getSnapshot()).not.toHaveProperty("theme");
  });
  it("preserves the orbit preference across roots and synchronizes another window without rewriting it", () => {
    const key = "cad-viewer:orbit:v1";
    localStorage.setItem(key, JSON.stringify({ speed: 2 }));
    expect(createStoredCadPreferences(localStorage).getSnapshot().orbit).toEqual({ speed: 2 });
    const firstRoot = desktopCadPreferences();
    window.dispatchEvent(new StorageEvent("storage", { key }));
    expect(firstRoot.getSnapshot().orbit).toEqual({ speed: 2 });
    firstRoot.update({ orbit: { speed: 4 } });
    expect(JSON.parse(localStorage.getItem(key)!)).toEqual({ speed: 4 });
    expect(desktopCadPreferences().getSnapshot().orbit).toEqual({ speed: 4 });

    localStorage.setItem(key, JSON.stringify({ speed: 99 }));
    window.dispatchEvent(new StorageEvent("storage", { key }));
    expect(firstRoot.getSnapshot().orbit).toEqual({ speed: 5 });
    expect(JSON.parse(localStorage.getItem(key)!)).toEqual({ speed: 99 });
  });
  it("ignores a stored pose transition preference: every pose write is a jump", () => {
    const key = "cad-viewer:pose-transition:v1";
    const retired = JSON.stringify({ animate: false, speed: 2 });
    localStorage.setItem(key, retired);
    expect(createStoredCadPreferences(localStorage).getSnapshot()).not.toHaveProperty("poseTransition");
    const preferences = desktopCadPreferences();
    const before = preferences.getSnapshot();
    window.dispatchEvent(new StorageEvent("storage", { key }));
    expect(preferences.getSnapshot()).toBe(before);
    expect(localStorage.getItem(key)).toBe(retired);
  });
  it("ignores retired tab arrangements on migration, updates and other-window events", () => {
    const preferences = desktopCadPreferences();
    const before = preferences.getSnapshot();
    for (const version of [5, 6, 7]) {
      const key = `cad-viewer:file-sheet-tab-layout:v${version}`;
      const legacy = JSON.stringify({ step: { split: true, top: ["render"], bottom: ["tree", "pose"], ratio: 0.2 } });
      localStorage.setItem(key, legacy);
      expect(createStoredCadPreferences(localStorage).getSnapshot()).not.toHaveProperty("fileSheetTabs");
      window.dispatchEvent(new StorageEvent("storage", { key }));
      expect(preferences.getSnapshot()).toBe(before);
      expect(localStorage.getItem(key)).toBe(legacy);
    }
    preferences.update({ orbit: { speed: 4 } });
    expect(preferences.getSnapshot()).not.toHaveProperty("fileSheetTabs");
    expect(JSON.parse(localStorage.getItem("cad-viewer:file-sheet-tab-layout:v7")!).step.split).toBe(true);
  });
});
