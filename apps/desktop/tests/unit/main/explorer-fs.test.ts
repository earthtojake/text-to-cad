import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";

import {
  FsError,
  FsConflictError,
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
  await fs.mkdir(path.join(root, ".git", "info"), { recursive: true });
  await fs.mkdir(path.join(root, "STEP", "imported"), { recursive: true });

  await fs.writeFile(path.join(root, ".gitignore"), "dist/\n*.log\n/STEP/**\n!/STEP/**/\n!/STEP/imported/**\n");
  await fs.writeFile(path.join(root, ".git", "info", "exclude"), "*.unsupported\n");
  await fs.writeFile(path.join(root, "README.md"), "# Title\n");
  await fs.writeFile(path.join(root, ".DS_Store"), "test-owned metadata\n");
  await fs.writeFile(path.join(root, "STEP", "tom.step"), "ISO-10303-21;\n");
  await fs.writeFile(path.join(root, "STEP", "imported", "part.step"), "ISO-10303-21;\n");
  await fs.writeFile(path.join(root, "dist", "output.unsupported"), Buffer.from([0, 1, 2]));
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

describe("listing a directory", () => {
  it("returns every entry at one level, including Git-ignored and hidden files", async () => {
    const entries = await listDirectory(root, "");
    const names = entries.map((entry) => entry.name);
    expect(names).toContain("README.md");
    expect(names).toContain("src");
    expect(names).toEqual(expect.arrayContaining(["dist", "node_modules", ".git", ".DS_Store", "noise.log", "blob.bin"]));
    expect(names).not.toContain("tom.step");
  });

  it("lists generated STEP outputs despite the project's output-ignore pattern", async () => {
    const entries = await listDirectory(root, "STEP");
    expect(entries.map((entry) => entry.name)).toEqual(["imported", "tom.step"]);
    expect(entries.find((entry) => entry.name === "tom.step")).toMatchObject({ path: "STEP/tom.step", kind: "file" });
  });

  it("lists unsupported files even inside an ignored directory", async () => {
    const entries = await listDirectory(root, "dist");
    expect(entries.map((entry) => entry.name)).toEqual(["bundle.js", "output.unsupported"]);
    expect(detectType("dist/output.unsupported").kind).toBe("binary");
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
  it("searches ignored, unsupported and dependency files as well as source files", async () => {
    const { paths, truncated } = await listPaths(root);
    expect(paths).toContain("README.md");
    expect(paths).toContain("src/deep/part.step");
    expect(paths).toEqual(expect.arrayContaining(["STEP/tom.step", "dist/output.unsupported", "node_modules/left-pad/index.js", ".git/HEAD", ".DS_Store"]));
    expect(truncated).toBe(false);
  });

  it("searches project outputs before dependency files can exhaust the cap", async () => {
    const { paths: all } = await listPaths(root);
    const ordinaryCount = all.filter((entry) => !entry.startsWith("node_modules/") && !entry.startsWith(".git/")).length;
    const { paths, truncated } = await listPaths(root, "", { limit: ordinaryCount });
    expect(paths).toContain("STEP/tom.step");
    expect(paths).toContain("dist/output.unsupported");
    expect(paths.some((entry) => entry.startsWith("node_modules/"))).toBe(false);
    expect(truncated).toBe(true);
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

describe("atomic text saves", () => {
  it("serializes concurrent saves from the same revision and reports the winner's revision", async () => {
    const file = "concurrent.txt";
    await fs.writeFile(path.join(root, file), "base");
    const before = await readTextFile(root, file);
    const results = await Promise.allSettled([writeTextFile(root, file, "first", before.revision), writeTextFile(root, file, "second", before.revision)]);
    const fulfilled = results.filter(result => result.status === "fulfilled");
    const rejected = results.filter(result => result.status === "rejected");
    expect(fulfilled).toHaveLength(1);
    expect(rejected).toHaveLength(1);
    const saved = fulfilled[0]!.value;
    expect(rejected[0]!.reason).toBeInstanceOf(FsConflictError);
    expect(rejected[0]!.reason).toMatchObject({ code: "conflict", actualRevision: saved.revision });
    expect(await fs.readFile(path.join(root, file), "utf8")).toBe(saved.content);
    expect((await fs.readdir(root)).filter(name => name.includes(".hardcore-"))).toEqual([]);
  });

  it("refuses to recreate an externally deleted file from a stale editor", async () => {
    await expect(writeTextFile(root, "already-deleted.txt", "draft", "old-revision")).rejects.toBeInstanceOf(FsConflictError);
    await expect(fs.stat(path.join(root, "already-deleted.txt"))).rejects.toMatchObject({ code: "ENOENT" });
  });

  it("reports committed bytes even if later path metadata becomes unreadable", async () => {
    const target = path.join(root, "receipt.txt");
    await fs.writeFile(target, "before");
    const before = await readTextFile(root, "receipt.txt");
    const stat = fs.stat, realpath = fs.realpath, rename = fs.rename;
    let committed = false;
    const renameSpy = vi.spyOn(fs, "rename").mockImplementation(async (...args) => { await rename(...args); committed = true; });
    const statSpy = vi.spyOn(fs, "stat").mockImplementation((...args: Parameters<typeof fs.stat>) => {
      if (committed) return Promise.reject(Object.assign(new Error("gone after commit"), { code: "ENOENT" }));
      return stat(...args);
    });
    const realpathSpy = vi.spyOn(fs, "realpath").mockImplementation((...args: Parameters<typeof fs.realpath>) => {
      if (committed) return Promise.reject(Object.assign(new Error("root moved after commit"), { code: "ENOENT" }));
      return realpath(...args);
    });
    try {
      expect(await writeTextFile(root, "receipt.txt", "committed", before.revision)).toMatchObject({ content: "committed", path: "receipt.txt" });
      expect(await fs.readFile(target, "utf8")).toBe("committed");
    } finally { renameSpy.mockRestore(); statSpy.mockRestore(); realpathSpy.mockRestore(); }
  });

  it("preserves permissions and writes complete replacement content", async () => {
    await fs.writeFile(path.join(root, "executable.txt"), "old");
    await fs.chmod(path.join(root, "executable.txt"), 0o664);
    const before = await readTextFile(root, "executable.txt");
    const text = "complete replacement\n".repeat(3000);
    const saved = await writeTextFile(root, "executable.txt", text, before.revision);
    expect(await fs.readFile(path.join(root, "executable.txt"), "utf8")).toBe(text);
    expect(saved).toMatchObject({ content: text, size: Buffer.byteLength(text), truncated: false });
    if (process.platform !== "win32") expect((await fs.stat(path.join(root, "executable.txt"))).mode & 0o777).toBe(0o664);
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
