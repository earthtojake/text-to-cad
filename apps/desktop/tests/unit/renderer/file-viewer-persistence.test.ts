import { beforeEach, describe, expect, it } from "vitest";
import { desktopCadPreferences, migrateCadFileStates, migrateCadPreferences } from "@renderer/features/explorer/adapters/cadPersistence";

beforeEach(() => { localStorage.clear(); sessionStorage.clear(); });
describe("FileViewer persisted CAD state migration", () => {
  it("ignores retired CAD themes and tutorial state", () => {
    const retiredTheme = JSON.stringify({ version: 13, themeId: "cinematic", custom: { exposure: 1.2 } });
    localStorage.setItem("cad-viewer:theme", retiredTheme);
    localStorage.setItem("cad-viewer:tutorial-tips:v1", JSON.stringify({ version: 1, seen: ["copyReference", 5] }));
    expect(migrateCadPreferences(localStorage)).toEqual({ poseTransition: { animate: true, speed: 1 } });
    expect(localStorage.getItem("cad-viewer:theme")).toBe(retiredTheme);
    localStorage.setItem("cad-viewer:tutorial-tips:v1", JSON.stringify({ version: 0, seen: ["copyReference"] }));
    expect(migrateCadPreferences(localStorage)).not.toHaveProperty("seenTips");
  });
  it("maps file state only from the exact root namespace and leaves other records intact", () => {
    const key = (root: string, file: string) => `cad-viewer:file-session:v1:${encodeURIComponent(root)}:${encodeURIComponent(file)}`;
    const old = { version: 1, fileKey: "part.step", signatures: {}, slices: { tab: { fileSheetTab: "tree" } } };
    sessionStorage.setItem(key("/projects/a", "part.step"), JSON.stringify(old));
    sessionStorage.setItem(key("http://localhost:8765", "part.step"), JSON.stringify(old));
    sessionStorage.setItem(key("/projects/b", "part.step"), JSON.stringify(old));
    sessionStorage.setItem("cad-viewer:directory-session:v1", JSON.stringify({ version: 1, theme: { themeId: "cinematic" } }));
    const result = migrateCadFileStates("root-a", "/projects/a", localStorage, sessionStorage);
    expect(result).toEqual({ '["part.step","cad"]': { version: 1, fileSession: old } });
    expect(sessionStorage.length).toBe(4);
    expect(migrateCadFileStates("root-a", "/projects/a", localStorage, sessionStorage)).toEqual({});
    expect(JSON.parse(localStorage.getItem("hardcore.fileViewer.v1")!)["root-a"]).toEqual(result);
  });
  it("preserves a newer root record and refuses paths outside the root", () => {
    localStorage.setItem("hardcore.fileViewer.v1", JSON.stringify({ "root-a": { '["part.step","cad"]': { version: 1, drawing: "new" } } }));
    sessionStorage.setItem(`cad-viewer:file-session:v1:${encodeURIComponent("/projects/a")}:${encodeURIComponent("../other.step")}`, JSON.stringify({ version: 1, fileKey: "../other.step" }));
    migrateCadFileStates("root-a", "/projects/a", localStorage, sessionStorage);
    expect(JSON.parse(localStorage.getItem("hardcore.fileViewer.v1")!)["root-a"]).toEqual({ '["part.step","cad"]': { version: 1, drawing: "new" } });
  });
  it("shares motion preferences across roots without reviving CAD themes or tutorial state", () => {
    const retiredTheme = JSON.stringify({ version: 13, themeId: "cinematic", custom: null });
    localStorage.setItem("cad-viewer:theme", retiredTheme);
    const firstRoot = desktopCadPreferences();
    const secondRoot = desktopCadPreferences();
    const poseTransition = { animate: false, speed: 2 };
    firstRoot.update({ poseTransition });
    expect(secondRoot.getSnapshot().poseTransition).toEqual(poseTransition);
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
  it("preserves pose transition preferences across roots and synchronizes another window without rewriting it", () => {
    const key = "cad-viewer:pose-transition:v1";
    localStorage.setItem(key, JSON.stringify({ animate: false, speed: 2 }));
    expect(migrateCadPreferences(localStorage).poseTransition).toEqual({ animate: false, speed: 2 });
    const firstRoot = desktopCadPreferences();
    window.dispatchEvent(new StorageEvent("storage", { key }));
    expect(firstRoot.getSnapshot().poseTransition).toEqual({ animate: false, speed: 2 });
    firstRoot.update({ poseTransition: { animate: true, speed: 4 } });
    expect(JSON.parse(localStorage.getItem(key)!)).toEqual({ animate: true, speed: 4 });
    expect(desktopCadPreferences().getSnapshot().poseTransition).toEqual({ animate: true, speed: 4 });

    localStorage.setItem(key, JSON.stringify({ animate: false, speed: 0.001 }));
    window.dispatchEvent(new StorageEvent("storage", { key }));
    expect(firstRoot.getSnapshot().poseTransition).toEqual({ animate: false, speed: 1 });
    expect(JSON.parse(localStorage.getItem(key)!)).toEqual({ animate: false, speed: 0.001 });
  });
  it("ignores retired tab arrangements on migration, updates and other-window events", () => {
    const preferences = desktopCadPreferences();
    const before = preferences.getSnapshot();
    for (const version of [5, 6, 7]) {
      const key = `cad-viewer:file-sheet-tab-layout:v${version}`;
      const legacy = JSON.stringify({ step: { split: true, top: ["render"], bottom: ["tree", "pose"], ratio: 0.2 } });
      localStorage.setItem(key, legacy);
      expect(migrateCadPreferences(localStorage)).not.toHaveProperty("fileSheetTabs");
      window.dispatchEvent(new StorageEvent("storage", { key }));
      expect(preferences.getSnapshot()).toBe(before);
      expect(localStorage.getItem(key)).toBe(legacy);
    }
    preferences.update({ poseTransition: { animate: true, speed: 4 } });
    expect(preferences.getSnapshot()).not.toHaveProperty("fileSheetTabs");
    expect(JSON.parse(localStorage.getItem("cad-viewer:file-sheet-tab-layout:v7")!).step.split).toBe(true);
  });
});
