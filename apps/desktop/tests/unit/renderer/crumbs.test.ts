import { describe, expect, it } from "vitest";

import { buildCrumbs, menuEntries, parentOf, stepToward, worktreeMark } from "@renderer/features/explorer/crumbs";
import type { DirEntry } from "@shared/ipc/explorer";

/**
 * The breadcrumb as data: which crumbs a path makes, what each one's menu
 * lists, and which entry that menu marks.
 *
 * The rule under test: a crumb is a segment BELOW the root, and its menu is
 * its PARENT's listing — its neighbours. So there is no crumb for the
 * project or the worktree, because a root's neighbours are outside the
 * project and the pane may not list them.
 */

const entry = (path: string, kind: "file" | "directory"): DirEntry => ({
  path,
  name: path.split("/").pop() ?? path,
  kind,
  size: 0,
  modifiedAt: 0,
  symlink: false,
});

describe("buildCrumbs", () => {
  it("makes a crumb per segment below the root, each listing its neighbours", () => {
    const crumbs = buildCrumbs({ path: "apps/viewer/src/main.jsx", narrow: false });
    expect(crumbs.map((crumb) => [crumb.kind, crumb.label, crumb.menu, crumb.current])).toEqual([
      // The first crumb's neighbours are the root's entries.
      ["directory", "apps", "", "apps"],
      ["directory", "viewer", "apps", "apps/viewer"],
      ["directory", "src", "apps/viewer", "apps/viewer/src"],
      // The file crumb lists its siblings — its folder — with itself marked.
      ["file", "main.jsx", "apps/viewer/src", "apps/viewer/src/main.jsx"],
    ]);
  });

  it("has no crumb for the root, whatever the root is", () => {
    // Jake's `STL/link_plate.stl` under `tom-cad`: two crumbs, not three.
    const crumbs = buildCrumbs({ path: "STL/link_plate.stl", narrow: false });
    expect(crumbs.map((crumb) => crumb.label)).toEqual(["STL", "link_plate.stl"]);
    // No crumb names the root, and no crumb's menu is above it: `""` is the
    // deepest a menu goes, and nothing is `null` except the ellipsis.
    expect(crumbs.every((crumb) => crumb.path !== "")).toBe(true);
    expect(crumbs.map((crumb) => crumb.menu)).toEqual(["", "STL"]);
  });

  it("lists the root for a file at the root", () => {
    const crumbs = buildCrumbs({ path: "README.md", narrow: false });
    expect(crumbs.map((crumb) => [crumb.kind, crumb.label, crumb.menu])).toEqual([["file", "README.md", ""]]);
  });

  it("is nothing at all for an empty tab", () => {
    expect(buildCrumbs({ path: null, narrow: false })).toEqual([]);
    expect(buildCrumbs({ path: "", narrow: false })).toEqual([]);
  });

  it("every crumb's menu is its parent, and marks the crumb itself", () => {
    // The redundancy is the point: `current` is the rule written down, and
    // it has to agree with what the component computes from the open file.
    const path = "a/b/c/d/e.step";
    for (const crumb of buildCrumbs({ path, narrow: false })) {
      expect(crumb.menu).toBe(parentOf(crumb.path));
      expect(crumb.current).toBe(crumb.path);
      expect(stepToward(crumb.menu!, path)).toBe(crumb.current);
    }
  });

  it("folds the folders into one ellipsis in a narrow pane, and keeps the file", () => {
    const crumbs = buildCrumbs({ path: "a/b/c/d.step", narrow: true });
    expect(crumbs.map((crumb) => crumb.kind)).toEqual(["ellipsis", "file"]);
    const ellipsis = crumbs[0]!;
    expect(ellipsis.menu).toBeNull();
    expect(ellipsis.hidden.map((folder) => folder.path)).toEqual(["a", "a/b", "a/b/c"]);
    expect(ellipsis.title).toBe("a/b/c");
    // The file keeps its own menu — its siblings — through the fold.
    expect(crumbs[1]!.menu).toBe("a/b/c");
    // One folder is not worth folding.
    expect(buildCrumbs({ path: "a/d.step", narrow: true }).map((c) => c.kind)).toEqual(["directory", "file"]);
    // Nor is none.
    expect(buildCrumbs({ path: "d.step", narrow: true }).map((c) => c.kind)).toEqual(["file"]);
  });

  it("is the same crumbs in a worktree: the root never appears", () => {
    // A worktree tab's paths are the worktree's, and the worktree is the
    // root — so it is not a crumb either, and the crumbs do not depend on
    // which copy of the tree they came from.
    expect(buildCrumbs({ path: "models/wrist.step", narrow: false })).toEqual(
      buildCrumbs({ path: "models/wrist.step", narrow: false }),
    );
    expect(buildCrumbs({ path: "models/wrist.step", narrow: false }).map((crumb) => crumb.label)).toEqual([
      "models",
      "wrist.step",
    ]);
  });
});

describe("worktreeMark", () => {
  it("names the worktree a file is in, and nothing for the project", () => {
    // A label rather than a crumb: it names the root, and a root has no menu
    // here. But which copy of the tree a file is in is the one thing its
    // name does not say, so it is still drawn.
    expect(worktreeMark("/home/me/.hardcore/worktrees/p/wrist")).toEqual({
      label: "wrist",
      title: "/home/me/.hardcore/worktrees/p/wrist",
    });
    expect(worktreeMark("C:\\Users\\me\\.hardcore\\worktrees\\p\\wrist")?.label).toBe("wrist");
    expect(worktreeMark(null)).toBeNull();
  });
});

describe("menuEntries", () => {
  it("puts directories first, in natural order, and marks the current one", () => {
    const listing = [entry("b.step", "file"), entry("zeta", "directory"), entry("a10.step", "file"), entry("a2.step", "file"), entry("Alpha", "directory")];
    const menu = menuEntries(listing, "a2.step");
    expect(menu.map((item) => item.path)).toEqual(["Alpha", "zeta", "a2.step", "a10.step", "b.step"]);
    expect(menu.filter((item) => item.current).map((item) => item.path)).toEqual(["a2.step"]);
  });
});

describe("stepToward", () => {
  it("names the entry of a directory that lies on the way to a path", () => {
    expect(stepToward("", "apps/viewer/main.jsx")).toBe("apps");
    expect(stepToward("apps", "apps/viewer/main.jsx")).toBe("apps/viewer");
    expect(stepToward("apps/viewer", "apps/viewer/main.jsx")).toBe("apps/viewer/main.jsx");
    // Not on the way at all: a sibling folder, or a prefix that is not a segment.
    expect(stepToward("packages", "apps/viewer/main.jsx")).toBeNull();
    expect(stepToward("app", "apps/viewer/main.jsx")).toBeNull();
    expect(stepToward("apps", null)).toBeNull();
  });
});

describe("parentOf", () => {
  it("is the root for a top-level entry", () => {
    expect(parentOf("README.md")).toBe("");
    expect(parentOf("a/b/c")).toBe("a/b");
  });
});
