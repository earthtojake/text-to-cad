import assert from "node:assert/strict";
import test from "node:test";

import { entryMenu, revealLabel } from "./entry-menu.js";

test("the file menu offers what the host can do, copy before reveal, named the platform's way", () => {
  const all = new Set(["copy-path", "reveal"]);
  assert.deepEqual(entryMenu("darwin", all), [{ action: "copy-path", label: "Copy path" }, { action: "reveal", label: "Reveal in Finder" }]);
  assert.deepEqual(entryMenu("win32", new Set(["reveal"])), [{ action: "reveal", label: "Show in Explorer" }]);
  assert.deepEqual(entryMenu("linux", new Set()), []);
  assert.equal(revealLabel("linux"), "Show in file manager");
});
