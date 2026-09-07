import { describe, expect, it } from "vitest";

import { buildCrumbs, menuEntries, parentOf, stepToward } from "@renderer/features/explorer/crumbs";
import type { DirEntry } from "@shared/ipc/explorer";

/**
 * The breadcrumb as data: which crumbs a path makes, what each one's menu
 * lists, and which entry that menu marks.
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
  it("makes a crumb per segment, each listing what it names", () => {
    const crumbs = buildCrumbs({ projectName: "text-to-cad", root: null, path: "apps/viewer/src/main.jsx", narrow: false });
    expect(crumbs.map((crumb) => [crumb.kind, crumb.label, crumb.menu, crumb.current])).toEqual([
      ["project", "text-to-cad", "", "apps"],
      ["directory", "apps", "apps", "apps/viewer"],
      ["directory", "viewer", "apps/viewer", "apps/viewer/src"],
      ["directory", "src", "apps/viewer/src", "apps/viewer/src/main.jsx"],
      // The file crumb lists its siblings — its folder — with itself marked.
      ["file", "main.jsx", "apps/viewer/src", "apps/viewer/src/main.jsx"],
    ]);
  });

  it("lists the root for a file at the root", () => {
    const crumbs = buildCrumbs({ projectName: "p", root: null, path: "README.md", narrow: false });
    expect(crumbs.map((crumb) => [crumb.kind, crumb.menu])).toEqual([
      ["project", ""],
      ["file", ""],
    ]);
  });

  it("is just the project for an empty tab", () => {
    expect(buildCrumbs({ projectName: "p", root: null, path: null, narrow: false })).toEqual([
      expect.objectContaining({ kind: "project", label: "p", menu: "", current: null }),
    ]);
  });

  it("folds the folders into one ellipsis in a narrow pane, and keeps the file", () => {
    const crumbs = buildCrumbs({ projectName: "p", root: null, path: "a/b/c/d.step", narrow: true });
    expect(crumbs.map((crumb) => crumb.kind)).toEqual(["project", "ellipsis", "file"]);
    const ellipsis = crumbs[1]!;
    expect(ellipsis.menu).toBeNull();
    expect(ellipsis.hidden.map((folder) => folder.path)).toEqual(["a", "a/b", "a/b/c"]);
    expect(ellipsis.title).toBe("a/b/c");
    // One folder is not worth folding.
    expect(buildCrumbs({ projectName: "p", root: null, path: "a/d.step", narrow: true }).map((c) => c.kind)).toEqual([
      "project",
      "directory",
      "file",
    ]);
  });

  it("gives a worktree tab a worktree crumb that lists the worktree's root", () => {
    const crumbs = buildCrumbs({
      projectName: "p",
      root: "/home/me/.hardcore/worktrees/p/wrist",
      path: "models/wrist.step",
      narrow: true,
    });
    expect(crumbs.map((crumb) => [crumb.kind, crumb.label, crumb.menu])).toEqual([
      // The project's own listing is another tree's: no menu.
      ["project", "p", null],
      ["worktree", "wrist", ""],
      ["directory", "models", "models"],
      ["file", "wrist.step", "models"],
    ]);
    expect(crumbs[1]!.current).toBe("models");
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
