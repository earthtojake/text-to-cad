import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import {
  FsError,
  FsConflictError,
  MAX_TEXT_BYTES,
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
  resolveEntryInRoot,
  resolveInRoot,
  statEntry,
  revisionOf,
  sortEntries,
  toRelative,
  uniqueName,
  writeTextFile,
} from "@main/explorer/fs";
import { TextFileSchema } from "@shared/ipc/explorer";

/**
 * A real directory on a real disk. The thing being tested is what the tree
 * does with `.gitignore`, symlinks and file types, and a mocked `fs` would
 * only test the mock.
 */
let root: string;

beforeAll(async () => {
  root = await fs.mkdtemp(path.join(os.tmpdir(), "text-to-cad-fs-"));
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

/**
 * A directory outside the fixture for a test that aims a link out of the root.
 * Never the shared temp directory itself: an assertion about what did not
 * land there must not depend on what an earlier run (or other code) left.
 */
const outsideDirectories: string[] = [];
async function outsideDirectory(): Promise<string> {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "text-to-cad-outside-"));
  outsideDirectories.push(directory);
  return directory;
}
afterEach(async () => {
  await Promise.all(outsideDirectories.splice(0).map((directory) => fs.rm(directory, { recursive: true, force: true })));
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

  it("stats a wide directory's entries concurrently, not one round trip after another", async () => {
    const wide = await fs.mkdtemp(path.join(os.tmpdir(), "text-to-cad-wide-"));
    outsideDirectories.push(wide);
    await Promise.all(Array.from({ length: 200 }, (_, index) => fs.writeFile(path.join(wide, `frame-${index}.png`), "x")));
    const stat = fs.stat.bind(fs);
    let inFlight = 0;
    let widest = 0;
    const spy = vi.spyOn(fs, "stat").mockImplementation(async (...args: Parameters<typeof fs.stat>) => {
      inFlight += 1;
      widest = Math.max(widest, inFlight);
      try { return await stat(...args); } finally { inFlight -= 1; }
    });
    try {
      expect(await listDirectory(wide, "")).toHaveLength(200);
    } finally {
      spy.mockRestore();
    }
    expect(widest).toBeGreaterThan(1);
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
    await fs.symlink(await outsideDirectory(), link);
    try {
      await expect(resolveInRoot(root, "escape")).rejects.toBeInstanceOf(FsError);
    } finally { await fs.unlink(link); }
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

  it("shows a file that is not UTF-8 read-only, so a save cannot write U+FFFD over its bytes", async () => {
    // "café" in Latin-1: 0xE9 is not a UTF-8 sequence, and has no NUL.
    await fs.writeFile(path.join(root, "latin1.txt"), Buffer.from([0x63, 0x61, 0x66, 0xe9, 0x0a]));
    const file = await readTextFile(root, "latin1.txt");
    expect(file.readOnly).toBe(true);
    // Main's answer crosses IPC through the channel's schema.
    expect(TextFileSchema.parse(file).readOnly).toBe(true);
    expect((await readTextFile(root, "README.md")).readOnly).toBeUndefined();
  });

  it("does not take a character split by the text cap for a non-UTF-8 file", async () => {
    const bytes = Buffer.alloc(MAX_TEXT_BYTES + 3, 0x61);
    // "é" (0xC3 0xA9) straddles the cap.
    bytes[MAX_TEXT_BYTES - 1] = 0xc3;
    bytes[MAX_TEXT_BYTES] = 0xa9;
    await fs.writeFile(path.join(root, "long.txt"), bytes);
    const file = await readTextFile(root, "long.txt");
    expect(file.truncated).toBe(true);
    expect(file.readOnly).toBeUndefined();
    await fs.rm(path.join(root, "long.txt"));
  });

  it("reads a file past 2 GiB as its first 4 MB, truncated, without reading the rest", async () => {
    const file = path.join(root, "huge.log");
    const handle = await fs.open(file, "w");
    try {
      await handle.write(Buffer.alloc(MAX_TEXT_BYTES + 16, 0x61), 0, MAX_TEXT_BYTES + 16, 0);
      // Sparse: 3 GiB on paper, a few megabytes on disk.
      await handle.truncate(3 * 1024 ** 3);
    } finally { await handle.close(); }
    try {
      const text = await readTextFile(root, "huge.log");
      expect(text).toMatchObject({ truncated: true, size: 3 * 1024 ** 3 });
      expect(text.content).toHaveLength(MAX_TEXT_BYTES);
    } finally { await fs.rm(file); }
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
    expect((await fs.readdir(root)).filter(name => name.includes(".text-to-cad-"))).toEqual([]);
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
  let elsewhere: string;

  afterAll(async () => {
    await fs.rm(elsewhere, { recursive: true, force: true });
  });

  beforeAll(async () => {
    edits = path.join(root, "edits");
    await fs.mkdir(path.join(edits, "nested"), { recursive: true });
    await fs.writeFile(path.join(edits, "part.step"), "ISO-10303-21;\n");
    await fs.writeFile(path.join(edits, "nested", "note.md"), "# note\n");
    // A door out of the root: a symlink to a directory outside it.
    elsewhere = await fs.mkdtemp(path.join(os.tmpdir(), "text-to-cad-elsewhere-"));
    await fs.symlink(elsewhere, path.join(edits, "escape"));
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
    await expect(createFile(root, elsewhere, "x.txt")).rejects.toBeInstanceOf(FsError);
    await expect(createDirectory(root, "edits/escape", "x")).rejects.toBeInstanceOf(FsError);
    expect(await fs.readdir(elsewhere)).toEqual([]);
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

/**
 * Symlinks inside the root. A path that does not exist yet is checked through
 * its deepest existing ancestor, so a linked directory cannot carry a new file
 * out; and the tree's verbs act on a link row itself, never on what it points
 * at — trashing `current.step -> v3.step` must not trash v3.
 */
describe("symlinks as doors and as rows", () => {
  let links: string;
  let outside: string;

  beforeAll(async () => {
    links = path.join(root, "links");
    outside = await fs.mkdtemp(path.join(os.tmpdir(), "text-to-cad-outside-"));
    await fs.mkdir(path.join(links, "shared"), { recursive: true });
    await fs.writeFile(path.join(links, "v3.step"), "v3\n");
    await fs.writeFile(path.join(links, "shared", "a.txt"), "shared\n");
    await fs.writeFile(path.join(outside, "secret.txt"), "secret\n");
    await fs.symlink("v3.step", path.join(links, "current.step"));
    await fs.symlink("shared", path.join(links, "vendor"));
    await fs.symlink(outside, path.join(links, "out"));
    await fs.symlink(path.join(outside, "secret.txt"), path.join(links, "out.txt"));
  });

  afterAll(async () => {
    await fs.rm(outside, { recursive: true, force: true });
  });

  it("lists a link to a file in the flat index, as the tree shows it, and descends into no link", async () => {
    const { paths } = await listPaths(root, "links");
    expect(paths).toContain("links/current.step");
    expect(paths).not.toContain("links/vendor/a.txt");
  });

  it("refuses to write a new file through a linked directory that leaves the root", async () => {
    const door = await outsideDirectory();
    await fs.symlink(door, path.join(links, "door"));
    try {
      await expect(writeTextFile(root, "links/door/new.txt", "x")).rejects.toBeInstanceOf(FsError);
      expect(await fs.readdir(door)).toEqual([]);
    } finally { await fs.unlink(path.join(links, "door")); }
    await expect(writeTextFile(root, "links/out/authorized_keys", "x")).rejects.toBeInstanceOf(FsError);
    await expect(fs.stat(path.join(outside, "authorized_keys"))).rejects.toMatchObject({ code: "ENOENT" });
    await expect(resolveInRoot(root, "links/out/deeper/still/new.txt")).rejects.toBeInstanceOf(FsError);
    // A new file through a link that stays inside is still fine.
    expect((await writeTextFile(root, "links/vendor/new.txt", "ok")).path).toBe("links/shared/new.txt");
  });

  it("resolves a row to the link itself, not its target", async () => {
    const realRoot = await fs.realpath(root);
    expect(await resolveEntryInRoot(root, "links/current.step")).toBe(path.join(realRoot, "links", "current.step"));
    expect(await resolveEntryInRoot(root, "links/out")).toBe(path.join(realRoot, "links", "out"));
    expect(await resolveEntryInRoot(root, "")).toBe(realRoot);
    await expect(resolveEntryInRoot(root, "links/out/secret.txt")).rejects.toBeInstanceOf(FsError);
    await expect(resolveEntryInRoot(root, "../x")).rejects.toBeInstanceOf(FsError);
    expect(await statEntry(root, "links/vendor")).toMatchObject({ path: "links/vendor", directory: true, symlink: true });
    expect(await statEntry(root, "links/out.txt")).toMatchObject({ path: "links/out.txt", directory: false, symlink: true });
  });

  it("renames a link, leaving its target where it was", async () => {
    expect(await renameEntry(root, "links/current.step", "latest.step")).toEqual({ path: "links/latest.step" });
    expect(await fs.readlink(path.join(links, "latest.step"))).toBe("v3.step");
    expect(await fs.readFile(path.join(links, "v3.step"), "utf8")).toBe("v3\n");
    expect(await renameEntry(root, "links/vendor", "deps")).toEqual({ path: "links/deps" });
    expect((await fs.stat(path.join(links, "shared"))).isDirectory()).toBe(true);
    // A link pointing outside is still a row inside: it can be renamed.
    expect(await renameEntry(root, "links/out.txt", "away.txt")).toEqual({ path: "links/away.txt" });
    expect(await fs.readFile(path.join(outside, "secret.txt"), "utf8")).toBe("secret\n");
  });

  it("duplicates a link as a link", async () => {
    expect(await duplicateEntry(root, "links/latest.step")).toEqual({ path: "links/latest copy.step" });
    expect(await fs.readlink(path.join(links, "latest copy.step"))).toBe("v3.step");
    expect(await duplicateEntry(root, "links/out")).toEqual({ path: "links/out copy" });
    expect(await fs.readlink(path.join(links, "out copy"))).toBe(outside);
  });

  it("refuses a case-only rename onto a different file on a case-sensitive disk", async () => {
    const dir = path.join(links, "case");
    await fs.mkdir(dir, { recursive: true });
    await fs.writeFile(path.join(dir, "a.txt"), "lower\n");
    await fs.writeFile(path.join(dir, "A.txt"), "upper\n");
    const names = await fs.readdir(dir);
    if (names.length === 1) {
      // Case-insensitive: one file, and the case-only rename is legitimate.
      expect(await renameEntry(root, "links/case/a.txt", "A.txt")).toEqual({ path: "links/case/A.txt" });
      expect(await fs.readdir(dir)).toEqual(["A.txt"]);
      return;
    }
    await expect(renameEntry(root, "links/case/a.txt", "A.txt")).rejects.toMatchObject({ code: "already-exists" });
    expect(await fs.readFile(path.join(dir, "A.txt"), "utf8")).toBe("upper\n");
    expect(await fs.readFile(path.join(dir, "a.txt"), "utf8")).toBe("lower\n");
  });
});
