import { describe, expect, it } from "vitest";

import { parseNameStatus, parseNumstat, parsePorcelainStatus } from "@main/projects/git";

/**
 * git's porcelain formats, parsed.
 *
 * These are the part of the review tab worth a unit test: the formats are
 * stable and fiddly, the failure mode is a silently wrong file list, and the
 * fixtures below are what `git` actually prints (NUL-separated, `-z`), not a
 * paraphrase of it.
 */

const NUL = "\0";

describe("porcelain status", () => {
  it("reads the branch header and its ahead/behind counts", () => {
    const parsed = parsePorcelainStatus(`## main...origin/main [ahead 2, behind 1]${NUL}`);
    expect(parsed).toMatchObject({ branch: "main", ahead: 2, behind: 1, unborn: false });
  });

  it("reads a branch with no upstream", () => {
    expect(parsePorcelainStatus(`## claude/desktop-app${NUL}`)).toMatchObject({
      branch: "claude/desktop-app",
      ahead: 0,
      behind: 0,
    });
  });

  it("recognises a repository with no commits yet", () => {
    const parsed = parsePorcelainStatus(`## No commits yet on main${NUL}`);
    expect(parsed.unborn).toBe(true);
    expect(parsed.branch).toBe("main");
  });

  it("reports a detached HEAD as no branch rather than as one called HEAD", () => {
    expect(parsePorcelainStatus(`## HEAD (no branch)${NUL}`).branch).toBeNull();
  });

  it("maps the status letters onto the badge's five", () => {
    const output = [
      " M src/main/index.ts",
      "A  src/new.ts",
      " D gone.ts",
      "?? untracked.ts",
      "",
    ].join(NUL);
    expect(parsePorcelainStatus(output).files).toEqual([
      { path: "src/main/index.ts", status: "modified" },
      { path: "src/new.ts", status: "added" },
      { path: "gone.ts", status: "deleted" },
      { path: "untracked.ts", status: "untracked" },
    ]);
  });

  it("pairs a rename with the path it came from", () => {
    // git writes the new path in the record and the old one in the next.
    const output = ["R  new/name.ts", "old/name.ts", ""].join(NUL);
    expect(parsePorcelainStatus(output).files).toEqual([
      { path: "new/name.ts", status: "renamed", oldPath: "old/name.ts" },
    ]);
  });

  it("does not lose the rest of the list to a path with a newline in it", () => {
    // The reason the parser is NUL-based. A line-oriented one stops here.
    const output = ["A  weird\nname.txt", " M after.ts", ""].join(NUL);
    const files = parsePorcelainStatus(output).files;
    expect(files).toHaveLength(2);
    expect(files[1]).toMatchObject({ path: "after.ts" });
  });

  it("prefers the index status over the worktree's when both are set", () => {
    expect(parsePorcelainStatus(`AM added-then-edited.ts${NUL}`).files[0]).toMatchObject({
      status: "added",
    });
  });
});

describe("numstat", () => {
  it("reads the counts per path", () => {
    const output = ["12\t3\tsrc/a.ts", "0\t40\tsrc/b.ts", ""].join(NUL);
    const counts = parseNumstat(output);
    expect(counts.get("src/a.ts")).toEqual({ insertions: 12, deletions: 3, binary: false });
    expect(counts.get("src/b.ts")).toEqual({ insertions: 0, deletions: 40, binary: false });
  });

  it("reads `-` as binary rather than as zero", () => {
    const counts = parseNumstat(`-\t-\tassets/logo.png${NUL}`);
    expect(counts.get("assets/logo.png")).toEqual({
      insertions: 0,
      deletions: 0,
      binary: true,
    });
  });

  it("reads a rename's three fields", () => {
    // `<ins>\t<del>\t\0<old>\0<new>` — the path field is empty.
    const output = ["4\t2\t", "old/name.ts", "new/name.ts", ""].join(NUL);
    const counts = parseNumstat(output);
    expect(counts.get("new/name.ts")).toEqual({
      insertions: 4,
      deletions: 2,
      binary: false,
      oldPath: "old/name.ts",
    });
    expect(counts.has("old/name.ts")).toBe(false);
  });

  it("answers with nothing for an empty diff", () => {
    expect(parseNumstat("").size).toBe(0);
  });
});

describe("name-status", () => {
  it("pairs each letter with its path", () => {
    const output = ["M", "src/a.ts", "A", "src/b.ts", "D", "src/c.ts", ""].join(NUL);
    const statuses = parseNameStatus(output);
    expect(statuses.get("src/a.ts")).toBe("modified");
    expect(statuses.get("src/b.ts")).toBe("added");
    expect(statuses.get("src/c.ts")).toBe("deleted");
  });

  it("takes the new path for a rename and its similarity score in stride", () => {
    const output = ["R096", "old.ts", "new.ts", "M", "after.ts", ""].join(NUL);
    const statuses = parseNameStatus(output);
    expect(statuses.get("new.ts")).toBe("renamed");
    expect(statuses.get("after.ts")).toBe("modified");
    expect(statuses.has("old.ts")).toBe(false);
  });
});
