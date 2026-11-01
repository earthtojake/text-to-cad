import assert from "node:assert/strict";
import test from "node:test";

import { entryMenu, fileManagerName, openInMenu, revealLabel } from "./entry-menu.js";

test("a home card's file menu offers what the host can do, copy before reveal, named the platform's way", () => {
  const all = new Set(["copy-path", "reveal", "browser"]);
  assert.deepEqual(entryMenu("darwin", all), [{ action: "copy-path", label: "Copy path" }, { action: "reveal", label: "Reveal in Finder" }]);
  assert.deepEqual(entryMenu("win32", new Set(["reveal"])), [{ action: "reveal", label: "Show in Explorer" }]);
  assert.deepEqual(entryMenu("linux", new Set()), []);
  assert.equal(revealLabel("linux"), "Show in file manager");
});

test("the navbar's Open in is the browser, then the file manager by its plain name, each where the host can do it", () => {
  assert.deepEqual(openInMenu("darwin", new Set(["copy-path", "reveal", "browser"])),
    [{ action: "browser", label: "Browser" }, { action: "reveal", label: "Finder" }]);
  assert.deepEqual(openInMenu("win32", new Set(["reveal"])), [{ action: "reveal", label: "File Explorer" }]);
  assert.deepEqual(openInMenu("linux", new Set(["browser"])), [{ action: "browser", label: "Browser" }]);
  assert.deepEqual(openInMenu("linux", new Set(["copy-path"])), []);
  assert.equal(fileManagerName("linux"), "File manager");
  // Finder is a product's name, the same in every language; the others are said in the view's.
  const t = key => `<${key}>`;
  assert.deepEqual(["darwin", "win32", "linux"].map(platform => fileManagerName(platform, t)), ["Finder", "<file.fileExplorer>", "<file.fileManager>"]);
});
