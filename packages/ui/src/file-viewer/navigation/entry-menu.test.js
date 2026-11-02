import assert from "node:assert/strict";
import test from "node:test";

import { entryMenu, fileManagerName, openInMenu, revealLabel } from "./entry-menu.js";

test("a home card's file menu offers what the host can do, copy before reveal, named the platform's way", () => {
  const all = new Set(["copy-path", "reveal", "browser"]);
  assert.deepEqual(entryMenu("darwin", all), [{ action: "copy-path", label: "Copy path" }, { action: "reveal", label: "Reveal in Finder" }]);
  // Copy link after Copy path, where the host can make a link.
  assert.deepEqual(entryMenu("darwin", new Set(["reveal", "copy-link", "copy-path"])).map(item => item.label), ["Copy path", "Copy link", "Reveal in Finder"]);
  assert.deepEqual(entryMenu("win32", new Set(["reveal"])), [{ action: "reveal", label: "Show in Explorer" }]);
  assert.deepEqual(entryMenu("linux", new Set()), []);
  assert.equal(revealLabel("linux"), "Show in file manager");
});

test("the navbar's Open in is the browser, then the file manager by its plain name, each where the host can do it", () => {
  assert.deepEqual(openInMenu("darwin", new Set(["copy-path", "reveal", "browser"])),
    [{ action: "browser", label: "Browser", enabled: true, group: "places" }, { action: "reveal", label: "Finder", enabled: true, group: "places" }]);
  assert.deepEqual(openInMenu("win32", new Set(["reveal"])), [{ action: "reveal", label: "File Explorer", enabled: true, group: "places" }]);
  assert.deepEqual(openInMenu("linux", new Set(["browser"])), [{ action: "browser", label: "Browser", enabled: true, group: "places" }]);
  // A source moved or deleted: what opens it is disabled, saying why; the browser needs none.
  assert.deepEqual(openInMenu("darwin", new Set(["reveal", "browser"]), undefined, { sourceMissing: true }), [
    { action: "browser", label: "Browser", enabled: true, group: "places" },
    { action: "reveal", label: "Finder", enabled: false, reason: "The source was moved or deleted.", group: "places" }]);
  assert.deepEqual(openInMenu("linux", new Set(["copy-path"])), []);
  assert.equal(fileManagerName("linux"), "File manager");
  // Finder is a product's name, the same in every language; the others are said in the view's.
  const t = key => `<${key}>`;
  assert.deepEqual(["darwin", "win32", "linux"].map(platform => fileManagerName(platform, t)), ["Finder", "<file.fileExplorer>", "<file.fileManager>"]);
});

test("Open in's apps come in groups after the places: the source's, each present export's as \"App (file)\", then Default app", () => {
  const files = { targets: [
    { target: "source", kind: "script", name: "bracket.py", present: true, apps: [{ id: "vscode", name: "Visual Studio Code" }] },
    { target: "export:step", kind: "step", name: "bracket.step", present: true, apps: [{ id: "freecad", name: "FreeCAD" }] },
    { target: "export:stl", kind: "stl", name: "bracket.stl", present: false, apps: [{ id: "bambu", name: "Bambu Studio" }] },
  ] };
  const rows = (state) => openInMenu("darwin", new Set(["reveal", "browser"]), undefined, state)
    .map(({ group, label, enabled, target, app }) => [group, label, enabled, target, app]);
  assert.deepEqual(rows({ files }), [
    ["places", "Browser", true, undefined, undefined], ["places", "Finder", true, undefined, undefined],
    ["source", "Visual Studio Code", true, "source", "vscode"],
    ["exports", "FreeCAD (bracket.step)", true, "export:step", "freecad"],
    ["default", "Default app", true, "source", "default"]]);
  // A source gone: what opens it is disabled; the browser and the export on disk are not.
  const gone = { targets: [{ ...files.targets[0], present: false }, files.targets[1]] };
  assert.deepEqual(rows({ files: gone }).map(([group, , enabled]) => [group, enabled]),
    [["places", true], ["places", false], ["source", false], ["exports", true], ["default", false]]);
  // No answer (yet, or ever): the places alone.
  assert.deepEqual(rows({ files: null }).map(([, label]) => label), ["Browser", "Finder"]);
});
