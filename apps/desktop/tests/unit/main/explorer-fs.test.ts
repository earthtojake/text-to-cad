import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterAll, beforeAll, describe, expect, it } from "vitest";

import {
  FsError,
  IgnoreRules,
  assertEntryName,
  createDirectory,
  createFile,
  detectType,
  duplicateEntry,
  extensionOf,
  isInside,
  listDirectory,
  listPaths,
  looksBinary,
  pathKinds,
  readTextFile,
  renameEntry,
  resolveInRoot,
  revisionOf,
  sortEntries,
  toRelative,
  uniqueName,
  writeTextFile,
} from "@main/explorer/fs";

/**
 * A real directory on a real disk. The thing being tested is what the tree
 * does with `.gitignore`, symlinks and file types, and a mocked `fs` would
 * only test the mock.
 */
let root: string;

beforeAll(async () => {
  root = await fs.mkdtemp(path.join(os.tmpdir(), "hardcore-fs-"));
  await fs.mkdir(path.join(root, "src", "deep"), { recursive: true });
  await fs.mkdir(path.join(root, "node_modules", "left-pad"), { recursive: true });
  await fs.mkdir(path.join(root, "dist"), { recursive: true });
  await fs.mkdir(path.join(root, ".git"), { recursive: true });

  await fs.writeFile(path.join(root, ".gitignore"), "dist/\n*.log\n\n# a comment\n");
  await fs.writeFile(path.join(root, "README.md"), "# Title\n");
  await fs.writeFile(path.join(root, "noise.log"), "ignored\n");
  await fs.writeFile(path.join(root, "src", "index.ts"), "export const a = 1;\n");
  await fs.writeFile(path.join(root, "src", "deep", "part.step"), "ISO-10303-21;\n");
  await fs.writeFile(path.join(root, "dist", "bundle.js"), "// built\n");
  await fs.writeFile(path.join(root, "node_modules", "left-pad", "index.js"), "module.exports\n");
  await fs.writeFile(path.join(root, ".git", "HEAD"), "ref: refs/heads/main\n");
  await fs.writeFile(path.join(root, "blob.bin"), Buffer.from([0x41, 0x00, 0x42]));
});

afterAll(async () => {
  await fs.rm(root, { recursive: true, force: true });
});

describe("ignore rules", () => {
  it("hides .git and node_modules whether or not the file says so", () => {
    const rules = IgnoreRules.none();
    expect(rules.ignores(".git", true)).toBe(true);
    expect(rules.ignores("node_modules", true)).toBe(true);
    expect(rules.ignores("src/node_modules/x.js", false)).toBe(true);
    expect(rules.ignores("src/index.ts", false)).toBe(false);
  });

  it("honours the root's .gitignore, directory patterns included", async () => {
    const rules = await IgnoreRules.read(root);
    expect(rules.ignores("dist", true)).toBe(true);
    expect(rules.ignores("noise.log", false)).toBe(true);
    expect(rules.ignores("README.md", false)).toBe(false);
  });

  it("does not treat a comment or a blank line as a pattern", () => {
    const rules = IgnoreRules.fromPatterns(["", "# a comment", "build"]);
    expect(rules.ignores("build", true)).toBe(true);
    expect(rules.ignores("a comment", false)).toBe(false);
  });

  it("never ignores the root itself", () => {
    expect(IgnoreRules.none().ignores("", true)).toBe(false);
  });
});

describe("listing a directory", () => {
  it("returns one level, ignored entries removed", async () => {
    const entries = await listDirectory(root, "");
    const names = entries.map((entry) => entry.name);
    expect(names).toContain("README.md");
    expect(names).toContain("src");
    expect(names).not.toContain("dist");
    expect(names).not.toContain("node_modules");
    expect(names).not.toContain(".git");
    expect(names).not.toContain("noise.log");
  });

  it("shows the ignored entries when asked", async () => {
    const entries = await listDirectory(root, "", { includeIgnored: true });
    expect(entries.map((entry) => entry.name)).toContain("dist");
  });

  it("puts directories first, then natural order", () => {
    const rows = sortEntries([
      row("b.txt", "file"),
      row("a.txt", "file"),
      row("z", "directory"),
      row("file10.txt", "file"),
      row("file2.txt", "file"),
    ]);
    expect(rows.map((entry) => entry.name)).toEqual([
      "z",
      "a.txt",
      "b.txt",
      "file2.txt",
      "file10.txt",
    ]);
  });

  it("reports paths relative to the root, POSIX-separated", async () => {
    const entries = await listDirectory(root, "src");
    expect(entries.map((entry) => entry.path)).toContain("src/index.ts");
  });
});

describe("listing every path", () => {
  it("walks the tree, skipping what the rules hide", async () => {
    const { paths, truncated } = await listPaths(root);
    expect(paths).toContain("README.md");
    expect(paths).toContain("src/deep/part.step");
    expect(paths.some((entry) => entry.startsWith("node_modules/"))).toBe(false);
    expect(paths.some((entry) => entry.startsWith("dist/"))).toBe(false);
    expect(truncated).toBe(false);
  });

  it("says so when it hits the cap instead of returning silently short", async () => {
    const { paths, truncated } = await listPaths(root, "", { limit: 1 });
    expect(paths).toHaveLength(1);
    expect(truncated).toBe(true);
  });
});

describe("containment", () => {
  it("resolves a relative path inside the root", async () => {
    expect(await resolveInRoot(root, "src/index.ts")).toBe(
      path.join(await fs.realpath(root), "src", "index.ts"),
    );
  });

  it("refuses a path that climbs out", async () => {
    await expect(resolveInRoot(root, "../../etc/passwd")).rejects.toBeInstanceOf(FsError);
  });

  it("refuses an absolute path outside the root", async () => {
    await expect(resolveInRoot(root, "/etc/hosts")).rejects.toBeInstanceOf(FsError);
  });

  it("refuses a symlink that points out of the root", async () => {
    const link = path.join(root, "escape");
    await fs.symlink(os.tmpdir(), link).catch(() => {});
    await expect(resolveInRoot(root, "escape")).rejects.toBeInstanceOf(FsError);
    await fs.rm(link, { force: true });
  });

  it("knows what is inside", () => {
    expect(isInside("/a", "/a/b")).toBe(true);
    expect(isInside("/a", "/a")).toBe(true);
    expect(isInside("/a", "/ab")).toBe(false);
    expect(isInside("/a", "/b")).toBe(false);
  });

  it("makes a relative path POSIX-separated", () => {
    expect(toRelative(path.join("/a", "b"), path.join("/a", "b", "c", "d"))).toBe("c/d");
  });
});

describe("type detection", () => {
  it("routes the nine CAD extensions to the CAD surface", () => {
    for (const extension of ["step", "stp", "glb", "stl", "3mf", "dxf", "urdf", "srdf", "sdf"]) {
      expect(detectType(`a/b.${extension}`).kind).toBe("cad");
    }
  });

  it("separates images, PDFs, text and the rest", () => {
    expect(detectType("logo.png")).toMatchObject({ kind: "image", mime: "image/png" });
    expect(detectType("spec.pdf")).toMatchObject({ kind: "pdf" });
    expect(detectType("main.ts").kind).toBe("text");
    expect(detectType("archive.zip").kind).toBe("binary");
  });

  it("treats dotfiles and the extensionless build files as text", () => {
    expect(detectType(".gitignore").kind).toBe("text");
    expect(detectType("Makefile").kind).toBe("text");
    expect(detectType("LICENSE").kind).toBe("text");
  });

  it("reads an extension off a path", () => {
    expect(extensionOf("a/b/c.Step")).toBe("step");
    expect(extensionOf("Makefile")).toBe("");
  });

  it("calls a buffer with a NUL byte binary", () => {
    expect(looksBinary(Buffer.from("plain text"))).toBe(false);
    expect(looksBinary(Buffer.from([0x41, 0x00, 0x42]))).toBe(true);
  });
});

describe("reading and writing", () => {
  it("reads text with a revision", async () => {
    const file = await readTextFile(root, "README.md");
    expect(file.content).toBe("# Title\n");
    expect(file.revision).toBe(revisionOf("# Title\n"));
    expect(file.truncated).toBe(false);
  });

  it("refuses to hand a binary to the editor", async () => {
    await expect(readTextFile(root, "blob.bin")).rejects.toBeInstanceOf(FsError);
  });

  it("writes and reports the new revision", async () => {
    const before = await readTextFile(root, "src/index.ts");
    const after = await writeTextFile(root, "src/index.ts", "export const a = 2;\n", before.revision);
    expect(after.content).toBe("export const a = 2;\n");
    expect(after.revision).not.toBe(before.revision);
  });

  it("refuses a write whose revision is stale", async () => {
    await expect(
      writeTextFile(root, "src/index.ts", "clobbered\n", "not-the-revision"),
    ).rejects.toBeInstanceOf(FsError);
  });
});

function row(name: string, kind: "file" | "directory") {
  return { path: name, name, kind, size: 0, modifiedAt: 0, symlink: false };
}

describe("pathKinds", () => {
  it("answers file, directory or null per path, and null for anything outside", async () => {
    const answers = await pathKinds(root, ["README.md", "src", "nope.txt", "../outside", "/etc/passwd", "src/../README.md"]);
    expect(answers["README.md"]).toBe("file");
    expect(answers["src"]).toBe("directory");
    expect(answers["nope.txt"]).toBeNull();
    expect(answers["../outside"]).toBeNull();
    expect(answers["/etc/passwd"]).toBeNull();
    // Answered under the key it was asked by, however it was spelled.
    expect(answers["src/../README.md"]).toBe("file");
  });
});

/**
 * The tree's edits — the context menu's New file, New folder, Rename and
 * Duplicate. Each one stays inside the root: a directory outside it is
 * refused before anything is written, and a name is one segment, so
 * `../` cannot arrive through the field either.
 */
describe("creating, renaming and duplicating", () => {
  let edits: string;

  beforeAll(async () => {
    edits = path.join(root, "edits");
    await fs.mkdir(path.join(edits, "nested"), { recursive: true });
    await fs.writeFile(path.join(edits, "part.step"), "ISO-10303-21;\n");
    await fs.writeFile(path.join(edits, "nested", "note.md"), "# note\n");
    // A door out of the root: a symlink to the machine's temp directory.
    await fs.symlink(os.tmpdir(), path.join(edits, "escape"));
  });

  it("creates a file and a folder, answering root-relative paths", async () => {
    expect(await createFile(root, "edits", "new.txt")).toEqual({ path: "edits/new.txt" });
    expect(await fs.readFile(path.join(edits, "new.txt"), "utf8")).toBe("");
    expect(await createDirectory(root, "edits/nested", "deeper")).toEqual({ path: "edits/nested/deeper" });
    expect((await fs.stat(path.join(edits, "nested", "deeper"))).isDirectory()).toBe(true);
    // At the root itself, the directory is "".
    expect(await createFile(root, "", "top.txt")).toEqual({ path: "top.txt" });
  });

  it("refuses to create over something that is there", async () => {
    await expect(createFile(root, "edits", "part.step")).rejects.toBeInstanceOf(FsError);
    await expect(createDirectory(root, "edits", "nested")).rejects.toBeInstanceOf(FsError);
    expect(await fs.readFile(path.join(edits, "part.step"), "utf8")).toBe("ISO-10303-21;\n");
  });

  it("refuses a directory outside the root, a symlink out of it included", async () => {
    await expect(createFile(root, "../", "x.txt")).rejects.toBeInstanceOf(FsError);
    await expect(createFile(root, os.tmpdir(), "x.txt")).rejects.toBeInstanceOf(FsError);
    await expect(createDirectory(root, "edits/escape", "x")).rejects.toBeInstanceOf(FsError);
    await expect(renameEntry(root, "../something", "y")).rejects.toBeInstanceOf(FsError);
    await expect(duplicateEntry(root, "/etc/hosts")).rejects.toBeInstanceOf(FsError);
  });

  it("refuses a name that is not one segment", async () => {
    for (const name of ["", ".", "..", "a/b", "..\\x", "../escape.txt"]) {
      await expect(createFile(root, "edits", name)).rejects.toBeInstanceOf(FsError);
      await expect(renameEntry(root, "edits/part.step", name)).rejects.toBeInstanceOf(FsError);
    }
    expect(() => assertEntryName("fine name.txt")).not.toThrow();
  });

  it("renames in place and refuses to replace a neighbour", async () => {
    expect(await renameEntry(root, "edits/nested/note.md", "notes.md")).toEqual({ path: "edits/nested/notes.md" });
    expect(await fs.readFile(path.join(edits, "nested", "notes.md"), "utf8")).toBe("# note\n");
    await expect(renameEntry(root, "edits/nested/notes.md", "deeper")).rejects.toBeInstanceOf(FsError);
    // The root cannot be renamed from inside itself.
    await expect(renameEntry(root, "", "other")).rejects.toBeInstanceOf(FsError);
  });

  it("duplicates beside the original, Finder's way", async () => {
    expect(await duplicateEntry(root, "edits/part.step")).toEqual({ path: "edits/part copy.step" });
    expect(await duplicateEntry(root, "edits/part.step")).toEqual({ path: "edits/part copy 2.step" });
    expect(await fs.readFile(path.join(edits, "part copy 2.step"), "utf8")).toBe("ISO-10303-21;\n");
    expect(await duplicateEntry(root, "edits/nested")).toEqual({ path: "edits/nested copy" });
    expect(await fs.readFile(path.join(edits, "nested copy", "notes.md"), "utf8")).toBe("# note\n");
  });

  it("picks the first free name", async () => {
    expect(await uniqueName(edits, "brand-new.txt", false)).toBe("brand-new.txt");
    expect(await uniqueName(edits, "part.step", false)).toBe("part copy 3.step");
    expect(await uniqueName(edits, "nested", true)).toBe("nested copy 2");
  });
});
