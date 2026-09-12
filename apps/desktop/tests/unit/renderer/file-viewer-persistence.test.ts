import { beforeEach, describe, expect, it } from "vitest";
import { desktopCadPreferences, migrateCadFileStates, migrateCadPreferences } from "@renderer/features/explorer/adapters/cadPersistence";

beforeEach(() => { localStorage.clear(); sessionStorage.clear(); });
describe("FileViewer persisted CAD state migration", () => {
  it("keeps the old theme and tutorial seen state without reinterpreting versioned records", () => {
    localStorage.setItem("cad-viewer:theme", JSON.stringify({ version: 13, themeId: "cinematic", custom: { exposure: 1.2 } }));
    localStorage.setItem("cad-viewer:tutorial-tips:v1", JSON.stringify({ version: 1, seen: ["copyReference", 5] }));
    expect(migrateCadPreferences(localStorage)).toEqual({ theme: { themeId: "cinematic", custom: { exposure: 1.2 } }, seenTips: ["copyReference"], fileSheetTabs: {} });
    localStorage.setItem("cad-viewer:theme", JSON.stringify({ version: 12, themeId: "cinematic" }));
    expect(migrateCadPreferences(localStorage).theme).toBeUndefined();
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
  it("keeps one global theme/tips preference shared by active and newly opened roots", () => {
    const firstRoot = desktopCadPreferences();
    const secondRoot = desktopCadPreferences();
    firstRoot.update({ theme: { themeId: "cinematic", custom: null }, seenTips: ["copyReference"] });
    expect(secondRoot.getSnapshot().theme?.themeId).toBe("cinematic");
    expect(desktopCadPreferences().getSnapshot().seenTips).toEqual(["copyReference"]);
    expect(JSON.parse(localStorage.getItem("cad-viewer:theme")!)).toEqual({ version: 13, themeId: "cinematic", custom: null });
    expect(localStorage.getItem("hardcore.cadPreferences.v1")).toBeNull();
    localStorage.setItem("cad-viewer:theme", JSON.stringify({ version: 13, themeId: "system", custom: null }));
    window.dispatchEvent(new StorageEvent("storage", { key: "cad-viewer:theme" }));
    expect(firstRoot.getSnapshot().theme?.themeId).toBe("system");
  });
});
