import { describe, expect, it } from "vitest";

import { entryMenu, entryMenuActions, revealLabel } from "@renderer/features/explorer/entry-menu";

/**
 * The entry menu as data: what a file, a folder, a CAD file and the root
 * each get, and where the one destructive item sits.
 */

describe("entryMenu", () => {
  it("offers a file the open, copy, edit and trash items, in that order", () => {
    expect(entryMenuActions({ path: "src/index.ts", kind: "file" }, "darwin")).toEqual([
      "open",
      "open-new-tab",
      "open-default",
      "open-with",
      "reveal",
      "copy-path",
      "copy-relative-path",
      "rename",
      "duplicate",
      "trash",
    ]);
  });

  it("adds Copy reference for a CAD file only", () => {
    expect(entryMenuActions({ path: "models/bracket.step", kind: "file" }, "darwin")).toContain("copy-reference");
    expect(entryMenuActions({ path: "models/bracket.stl", kind: "file" }, "darwin")).toContain("copy-reference");
    expect(entryMenuActions({ path: "models/bracket.py", kind: "file" }, "darwin")).not.toContain("copy-reference");
    expect(entryMenuActions({ path: "models", kind: "directory" }, "darwin")).not.toContain("copy-reference");
  });

  it("offers a folder the new-entry, terminal, copy, rename and trash items", () => {
    expect(entryMenuActions({ path: "models", kind: "directory" }, "darwin")).toEqual([
      "new-file",
      "new-folder",
      "open-terminal",
      "reveal",
      "copy-path",
      "copy-relative-path",
      "rename",
      "trash",
    ]);
  });

  it("never offers to rename or trash the root", () => {
    const actions = entryMenuActions({ path: "", kind: "directory" }, "darwin");
    expect(actions).not.toContain("rename");
    expect(actions).not.toContain("trash");
    expect(actions).toContain("new-file");
    expect(actions).toContain("open-terminal");
  });

  it("keeps the destructive item alone in the last section", () => {
    for (const target of [
      { path: "a.txt", kind: "file" as const },
      { path: "a", kind: "directory" as const },
    ]) {
      const sections = entryMenu(target, "darwin");
      const last = sections[sections.length - 1]!;
      expect(last).toHaveLength(1);
      expect(last[0]).toMatchObject({ action: "trash", destructive: true });
      // And nothing else is.
      expect(sections.flat().filter((item) => item.destructive)).toHaveLength(1);
    }
  });

  it("names the platform's file browser and its trash chord", () => {
    expect(revealLabel("darwin")).toBe("Reveal in Finder");
    expect(revealLabel("win32")).toBe("Show in Explorer");
    expect(revealLabel("linux")).toBe("Show in file manager");
    const mac = entryMenu({ path: "a.txt", kind: "file" }, "darwin").flat();
    const win = entryMenu({ path: "a.txt", kind: "file" }, "win32").flat();
    expect(mac.find((item) => item.action === "reveal")?.label).toBe("Reveal in Finder");
    expect(mac.find((item) => item.action === "trash")?.shortcut).toBe("⌘⌫");
    expect(win.find((item) => item.action === "trash")?.shortcut).toBe("Ctrl+Del");
    expect(mac.find((item) => item.action === "rename")?.shortcut).toBe("F2");
  });
});
