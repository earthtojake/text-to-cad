import assert from "node:assert/strict";
import test from "node:test";

import {
  buildCrumbs,
  menuEntries,
  parentOf,
  stepToward
} from "./crumbs.js";

/**
 * The breadcrumb as data: which crumbs a path makes, what each one's menu
 * lists, and which entry that menu marks.
 *
 * The rule under test: a crumb is a segment BELOW the root, and its menu is
 * its PARENT's listing — its neighbours. So there is no crumb for the served
 * directory (whichever copy of a tree it is), because a root's neighbours are outside what the
 * pane may list.
 */

const entry = (path, kind) => ({
  path,
  name: path.split("/").pop() ?? path,
  kind
});

test("buildCrumbs makes a crumb per segment below the root, each listing its neighbours", () => {
  const crumbs = buildCrumbs({ path: "apps/web/src/main.jsx" });
  assert.deepEqual(
    crumbs.map((crumb) => [crumb.kind, crumb.label, crumb.menu, crumb.current]),
    [
      // The first crumb's neighbours are the root's entries.
      ["directory", "apps", "", "apps"],
      ["directory", "web", "apps", "apps/web"],
      ["directory", "src", "apps/web", "apps/web/src"],
      // The file crumb lists its siblings — its folder — with itself marked.
      ["file", "main.jsx", "apps/web/src", "apps/web/src/main.jsx"]
    ]
  );
});

test("buildCrumbs has no crumb for the root, whatever the root is", () => {
  // `STL/link_plate.stl` under a served project: two crumbs, not three.
  const crumbs = buildCrumbs({ path: "STL/link_plate.stl" });
  assert.deepEqual(crumbs.map((crumb) => crumb.label), ["STL", "link_plate.stl"]);
  // No crumb names the root, and no crumb's menu is above it: `""` is the
  // deepest a menu goes.
  assert.equal(crumbs.every((crumb) => crumb.path !== ""), true);
  assert.deepEqual(crumbs.map((crumb) => crumb.menu), ["", "STL"]);
});

test("buildCrumbs lists the root for a file at the root", () => {
  const crumbs = buildCrumbs({ path: "README.md" });
  assert.deepEqual(
    crumbs.map((crumb) => [crumb.kind, crumb.label, crumb.menu]),
    [["file", "README.md", ""]]
  );
});

test("buildCrumbs is nothing at all for an empty tab", () => {
  assert.deepEqual(buildCrumbs({ path: null }), []);
  assert.deepEqual(buildCrumbs({ path: "" }), []);
});

test("every crumb's menu is its parent, and marks the crumb itself", () => {
  // The redundancy is the point: `current` is the rule written down, and it
  // has to agree with what the component computes from the open file.
  const path = "a/b/c/d/e.step";
  for (const crumb of buildCrumbs({ path })) {
    assert.equal(crumb.menu, parentOf(crumb.path));
    assert.equal(crumb.current, crumb.path);
    assert.equal(stepToward(crumb.menu, path), crumb.current);
  }
});

test("menuEntries puts directories first, in natural order, and marks the current one", () => {
  const listing = [
    entry("b.step", "file"),
    entry("zeta", "directory"),
    entry("a10.step", "file"),
    entry("a2.step", "file"),
    entry("Alpha", "directory")
  ];
  const menu = menuEntries(listing, "a2.step");
  assert.deepEqual(menu.map((item) => item.path), [
    "Alpha",
    "zeta",
    "a2.step",
    "a10.step",
    "b.step"
  ]);
  assert.deepEqual(menu.filter((item) => item.current).map((item) => item.path), ["a2.step"]);
});

test("menuEntries carries the source's own payload through", () => {
  // The catalog source hangs its entry on `value`; the menu hands it back to
  // `onOpen`, so a host never has to look a picked file up again by path.
  const menu = menuEntries([{ path: "a.step", name: "a.step", kind: "file", value: { id: 7 } }], null);
  assert.deepEqual(menu[0].value, { id: 7 });
});

test("stepToward names the entry of a directory that lies on the way to a path", () => {
  assert.equal(stepToward("", "apps/web/main.jsx"), "apps");
  assert.equal(stepToward("apps", "apps/web/main.jsx"), "apps/web");
  assert.equal(stepToward("apps/web", "apps/web/main.jsx"), "apps/web/main.jsx");
  // Not on the way at all: a sibling folder, or a prefix that is not a segment.
  assert.equal(stepToward("packages", "apps/web/main.jsx"), null);
  assert.equal(stepToward("app", "apps/web/main.jsx"), null);
  assert.equal(stepToward("apps", null), null);
});

test("parentOf is the root for a top-level entry", () => {
  assert.equal(parentOf("README.md"), "");
  assert.equal(parentOf("a/b/c"), "a/b");
});
