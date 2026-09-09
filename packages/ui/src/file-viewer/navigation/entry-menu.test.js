import assert from "node:assert/strict";
import test from "node:test";

import {
  ALL_ENTRY_CAPABILITIES,
  WEB_ENTRY_CAPABILITIES,
  entryMenu,
  entryMenuActions,
  revealLabel
} from "./entry-menu.js";

/**
 * The entry menu as data: what a file, a folder, a CAD file and the root each
 * get, where the one destructive item sits, and what a host that cannot touch
 * a filesystem is left with.
 */

test("a file gets the open, copy, edit and trash items, in that order", () => {
  assert.deepEqual(entryMenuActions({ path: "src/index.ts", kind: "file" }, "darwin"), [
    "open",
    "open-default",
    "open-with",
    "reveal",
    "copy-path",
    "copy-relative-path",
    "rename",
    "duplicate",
    "trash"
  ]);
});

test("a breadcrumb gets the same menu without Open — the crumb is the open file", () => {
  const fromCrumb = entryMenuActions({ path: "src/index.ts", kind: "file", surface: "crumb" }, "darwin");
  const fromTree = entryMenuActions({ path: "src/index.ts", kind: "file", surface: "tree" }, "darwin");
  assert.ok(!fromCrumb.includes("open"));
  assert.deepEqual(fromCrumb, fromTree.filter((action) => action !== "open"));
  assert.deepEqual(
    entryMenuActions({ path: "src", kind: "directory", surface: "crumb" }, "darwin"),
    entryMenuActions({ path: "src", kind: "directory" }, "darwin")
  );
});

test("Copy reference is offered for a CAD file and nothing else", () => {
  assert.ok(entryMenuActions({ path: "models/bracket.step", kind: "file" }, "darwin").includes("copy-reference"));
  assert.ok(entryMenuActions({ path: "models/bracket.stl", kind: "file" }, "darwin").includes("copy-reference"));
  assert.ok(!entryMenuActions({ path: "models/bracket.py", kind: "file" }, "darwin").includes("copy-reference"));
  assert.ok(!entryMenuActions({ path: "models", kind: "directory" }, "darwin").includes("copy-reference"));
});

test("a folder gets the new-entry, terminal, copy, rename and trash items", () => {
  assert.deepEqual(entryMenuActions({ path: "models", kind: "directory" }, "darwin"), [
    "new-file",
    "new-folder",
    "open-terminal",
    "reveal",
    "copy-path",
    "copy-relative-path",
    "rename",
    "trash"
  ]);
});

test("the root is never renamed or trashed", () => {
  const actions = entryMenuActions({ path: "", kind: "directory" }, "darwin");
  assert.ok(!actions.includes("rename"));
  assert.ok(!actions.includes("trash"));
  assert.ok(actions.includes("new-file"));
  assert.ok(actions.includes("open-terminal"));
});

test("the destructive item is alone in the last section", () => {
  for (const target of [
    { path: "a.txt", kind: "file" },
    { path: "a", kind: "directory" }
  ]) {
    const sections = entryMenu(target, "darwin");
    const last = sections[sections.length - 1];
    assert.equal(last.length, 1);
    assert.equal(last[0].action, "trash");
    assert.equal(last[0].destructive, true);
    // And nothing else is.
    assert.equal(sections.flat().filter((item) => item.destructive).length, 1);
  }
});

test("the platform's file browser and its trash chord are named", () => {
  assert.equal(revealLabel("darwin"), "Reveal in Finder");
  assert.equal(revealLabel("win32"), "Show in Explorer");
  assert.equal(revealLabel("linux"), "Show in file manager");
  const mac = entryMenu({ path: "a.txt", kind: "file" }, "darwin").flat();
  const win = entryMenu({ path: "a.txt", kind: "file" }, "win32").flat();
  assert.equal(mac.find((item) => item.action === "reveal").label, "Reveal in Finder");
  assert.equal(mac.find((item) => item.action === "trash").shortcut, "⌘⌫");
  assert.equal(win.find((item) => item.action === "trash").shortcut, "Ctrl+Del");
  assert.equal(mac.find((item) => item.action === "rename").shortcut, "F2");
});

/**
 * The capability filter is the whole difference between the two apps' menus:
 * one table, filtered, rather than a table each.
 */
test("a browser tab is left with opening a file and naming it", () => {
  assert.deepEqual(
    entryMenuActions({ path: "models/bracket.step", kind: "file" }, "darwin", WEB_ENTRY_CAPABILITIES),
    ["open", "copy-path", "copy-relative-path", "copy-reference"]
  );
  // A folder in a browser tab can be copied and nothing else — no new file,
  // no terminal, no reveal, no rename, no trash.
  assert.deepEqual(
    entryMenuActions({ path: "models", kind: "directory" }, "darwin", WEB_ENTRY_CAPABILITIES),
    ["copy-path", "copy-relative-path"]
  );
});

test("an item's place never depends on which host is asking", () => {
  // Every action a filtered menu still has appears in the same order it does
  // in the full one, so a person moving between the apps finds the same item
  // under the same neighbours.
  const full = entryMenuActions({ path: "a.step", kind: "file" }, "darwin");
  const web = entryMenuActions({ path: "a.step", kind: "file" }, "darwin", WEB_ENTRY_CAPABILITIES);
  assert.deepEqual(web, full.filter((action) => WEB_ENTRY_CAPABILITIES.has(action)));
});

test("a section the filter empties takes its separator with it", () => {
  const sections = entryMenu({ path: "a.step", kind: "file" }, "darwin", WEB_ENTRY_CAPABILITIES);
  assert.ok(sections.every((section) => section.length > 0));
  // Open, then the copies: two sections, not five with three blanks.
  assert.equal(sections.length, 2);
});

test("a host with no capabilities at all gets no menu rather than an empty one", () => {
  assert.deepEqual(entryMenu({ path: "a.step", kind: "file" }, "darwin", new Set()), []);
});

test("the default capability set is everything", () => {
  assert.deepEqual(
    entryMenuActions({ path: "a.step", kind: "file" }, "darwin"),
    entryMenuActions({ path: "a.step", kind: "file" }, "darwin", ALL_ENTRY_CAPABILITIES)
  );
});
