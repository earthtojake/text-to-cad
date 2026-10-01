import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type * as NodeFs from "node:fs";
import type { Mock } from "vitest";
import { FileWatchers, readTextFile, revisionOf, statFile, writeTextFile } from "@main/explorer/fs";
import type { FileChange, Schedule } from "@main/explorer/fs";

const driver = vi.hoisted(() => ({ recursive: vi.fn(), direct: vi.fn() }));
vi.mock("chokidar", () => ({ watch: driver.recursive }));
vi.mock("node:fs", async (importOriginal) => ({
  ...await importOriginal<typeof NodeFs>(), watch: driver.direct,
}));

type ChangeListener = (root: string, changes: FileChange[]) => void;
let root: string;
let watchers: FileWatchers;
let emit: Mock<ChangeListener>;
let recursive: { on: ReturnType<typeof vi.fn>; close: ReturnType<typeof vi.fn> };
let direct: { on: ReturnType<typeof vi.fn>; close: ReturnType<typeof vi.fn> };

beforeEach(async () => {
  root = await fs.mkdtemp(path.join(os.tmpdir(), "text-to-cad-watch-"));
  await fs.mkdir(path.join(root, "STEP"));
  await fs.mkdir(path.join(root, "node_modules", "dependency"), { recursive: true });
  await fs.mkdir(path.join(root, ".git", "info"), { recursive: true });
  await fs.mkdir(path.join(root, "runtime-bundle"));
  await fs.writeFile(path.join(root, ".gitignore"), "/STEP/**\n!/STEP/**/\n*.unsupported\n");
  await fs.writeFile(path.join(root, ".git", "info", "exclude"), "/runtime-bundle/\n");
  emit = vi.fn<ChangeListener>();
  recursive = { on: vi.fn().mockReturnThis(), close: vi.fn(async () => {}) };
  direct = { on: vi.fn().mockReturnThis(), close: vi.fn() };
  driver.recursive.mockReset().mockReturnValue(recursive);
  driver.direct.mockReset().mockReturnValue(direct);
  watchers = new FileWatchers(emit);
});
afterEach(async () => {
  await watchers.closeAll();
  await fs.rm(root, { recursive: true, force: true });
});

describe("visible file watching", () => {
  it("prunes Git-ignored outputs and runtime directories only from background recursion", async () => {
    await watchers.watch(root);
    const ignored = driver.recursive.mock.calls[0]![1].ignored as (target: string, stats?: NodeFs.Stats) => boolean;
    const realRoot = await fs.realpath(root);
    const model = path.join(realRoot, "STEP", "tom.step");
    await fs.writeFile(model, "ISO-10303-21;\n");
    // The project re-includes directories; only the typed file probe can
    // distinguish this ignored output from an allowed same-named directory.
    expect(ignored(model)).toBe(false);
    expect(ignored(model, await fs.stat(model))).toBe(true);
    expect(ignored(path.join(realRoot, "output.unsupported"))).toBe(true);
    expect(ignored(path.join(root, "node_modules", "dependency"))).toBe(true);
    expect(ignored(path.join(root, ".git", "objects"))).toBe(true);
    expect(ignored(path.join(realRoot, "source.ts"))).toBe(false);
    const runtime = path.join(realRoot, "runtime-bundle");
    expect(ignored(runtime)).toBe(false);
    expect(ignored(runtime, await fs.stat(runtime))).toBe(true);
    expect(ignored(path.join(realRoot, "STEP"), await fs.stat(path.join(realRoot, "STEP")))).toBe(false);
  });

  it("refreshes new ignored STEP outputs in a listed directory", async () => {
    await watchers.watch(root);
    await watchers.watchListedDirectory(root, "STEP");
    const notify = driver.direct.mock.calls[0]![2] as (event: string, filename: string) => void;
    await fs.writeFile(path.join(root, "STEP", "new.step"), "ISO-10303-21;\n");
    notify("rename", "new.step");
    // No tab has it open, so nothing reads it.
    await vi.waitFor(() => expect(emit).toHaveBeenCalledWith(root, [
      { path: "STEP/new.step", kind: "changed", directory: false },
    ]));
  });

  it("watches an opened ignored file after stat without listing its parent", async () => {
    await watchers.watch(root);
    await fs.writeFile(path.join(root, "runtime-bundle", "settings.txt"), "before\n");
    const entry = await statFile(root, "runtime-bundle/settings.txt");
    await watchers.watchEntry(root, entry);
    expect(driver.direct).toHaveBeenCalledTimes(1);
    expect(driver.direct.mock.calls[0]![0]).toBe(path.join(await fs.realpath(root), "runtime-bundle"));
    const notify = driver.direct.mock.calls[0]![2] as (event: string, filename: string) => void;
    await fs.writeFile(path.join(root, "runtime-bundle", "settings.txt"), "after\n");
    notify("change", "settings.txt");
    await vi.waitFor(() => expect(emit).toHaveBeenCalledWith(root, [
      { path: "runtime-bundle/settings.txt", kind: "changed", directory: false, revision: revisionOf("after\n") },
    ]));
  });

  it("watches a listed cache directory directly, shares the owner and releases every handle", async () => {
    // A listing may finish before the source's watch IPC arrives.
    await watchers.watchListedDirectory(root, "node_modules/dependency");
    expect(driver.direct).not.toHaveBeenCalled();
    await watchers.watch(root);
    await watchers.watch(root);
    await watchers.watchListedDirectory(root, "node_modules/dependency");
    expect(driver.recursive).toHaveBeenCalledTimes(1);
    expect(driver.direct).toHaveBeenCalledTimes(1);
    expect(driver.direct.mock.calls[0]![1]).toEqual({ recursive: false });

    const notify = driver.direct.mock.calls[0]![2] as (event: string, filename: string) => void;
    const file = path.join(root, "node_modules", "dependency", "new.unsupported");
    await fs.writeFile(file, Buffer.from([0, 1, 2]));
    notify("rename", "new.unsupported");
    await vi.waitFor(() => expect(emit).toHaveBeenCalledWith(root, [
      { path: "node_modules/dependency/new.unsupported", kind: "changed", directory: false },
    ]));

    await watchers.unwatch(root);
    expect(direct.close).not.toHaveBeenCalled();
    await watchers.unwatch(root);
    expect(direct.close).toHaveBeenCalledTimes(1);
    expect(recursive.close).toHaveBeenCalledTimes(1);
    emit.mockClear();
    notify("change", "new.unsupported");
    expect(emit).not.toHaveBeenCalled();
  });

  it("stamps a changed file with the revision its own save returned", async () => {
    await fs.writeFile(path.join(root, "notes.txt"), "before\n");
    await watchers.watch(root);
    await watchers.watchEntry(root, await statFile(root, "notes.txt"));
    const notify = driver.direct.mock.calls[0]![2] as (event: string, filename: string) => void;
    const loaded = await readTextFile(root, "notes.txt");
    const saved = await writeTextFile(root, "notes.txt", "after\n", loaded.revision);
    notify("rename", "notes.txt");
    // The editor that saved holds `saved.revision`; the echo carries the same
    // one, so it is not reported to that editor as a change on disk.
    await vi.waitFor(() => expect(emit).toHaveBeenCalledWith(root, [
      { path: "notes.txt", kind: "changed", directory: false, revision: saved.revision },
    ]));
  });

  it("keeps an opened link's own path and reports its target's changes under it", async () => {
    await fs.mkdir(path.join(root, "versions"));
    await fs.writeFile(path.join(root, "versions", "v3.txt"), "v3\n");
    await fs.symlink(path.join("versions", "v3.txt"), path.join(root, "current.txt"));
    const entry = await statFile(root, "current.txt");
    // The tab is the link: its identity is not its target's.
    expect(entry).toMatchObject({ path: "current.txt", name: "current.txt", kind: "file" });
    await watchers.watch(root);
    await watchers.watchEntry(root, entry);
    const realRoot = await fs.realpath(root);
    // The target's directory is watched too; that is where its events come from.
    const targetDirectory = driver.direct.mock.calls.findIndex(([directory]) => directory === path.join(realRoot, "versions"));
    expect(targetDirectory).toBeGreaterThanOrEqual(0);
    const notify = driver.direct.mock.calls[targetDirectory]![2] as (event: string, filename: string) => void;
    await fs.writeFile(path.join(root, "versions", "v3.txt"), "v3, edited\n");
    notify("change", "v3.txt");
    await vi.waitFor(() => expect(emit).toHaveBeenCalledWith(root, [
      { path: "versions/v3.txt", kind: "changed", directory: false, revision: revisionOf("v3, edited\n") },
      { path: "current.txt", kind: "changed", directory: false, revision: revisionOf("v3, edited\n") },
    ]));
  });

  it("arms a listed directory's watch again after it is removed and made again", async () => {
    const handles: Array<{ on: ReturnType<typeof vi.fn>; close: ReturnType<typeof vi.fn> }> = [];
    driver.direct.mockImplementation(() => {
      const handle = { on: vi.fn().mockReturnThis(), close: vi.fn() };
      handles.push(handle);
      return handle;
    });
    await watchers.watch(root);
    await watchers.watchListedDirectory(root, "node_modules");
    await watchers.watchListedDirectory(root, "node_modules/dependency");
    expect(driver.direct).toHaveBeenCalledTimes(2);
    const notifyParent = driver.direct.mock.calls[0]![2] as (event: string, filename: string) => void;
    const notifyDependency = driver.direct.mock.calls[1]![2] as (event: string, filename: string) => void;
    const dependency = path.join(await fs.realpath(root), "node_modules", "dependency");

    await fs.rm(dependency, { recursive: true });
    notifyDependency("rename", "dependency");
    await vi.waitFor(() => expect(handles[1]!.close).toHaveBeenCalled());
    await fs.mkdir(dependency);
    notifyParent("rename", "dependency");
    await vi.waitFor(() => expect(driver.direct).toHaveBeenCalledTimes(3));
    expect(driver.direct.mock.calls[2]![0]).toBe(dependency);
  });

  it("arms a listed directory's watch again when it is removed and made again before its event is read", async () => {
    const handles: Array<{ on: ReturnType<typeof vi.fn>; close: ReturnType<typeof vi.fn> }> = [];
    driver.direct.mockImplementation(() => {
      const handle = { on: vi.fn().mockReturnThis(), close: vi.fn() };
      handles.push(handle);
      return handle;
    });
    await watchers.watch(root);
    await watchers.watchListedDirectory(root, "node_modules");
    await watchers.watchListedDirectory(root, "node_modules/dependency");
    const notifyDependency = driver.direct.mock.calls[1]![2] as (event: string, filename: string) => void;
    const dependency = path.join(await fs.realpath(root), "node_modules", "dependency");

    // `rm -rf dependency && mkdir dependency`: by the time the dead watch's own event is read the
    // name stats again, but it is a new directory the old watch hears nothing from.
    await fs.rm(dependency, { recursive: true });
    await fs.mkdir(dependency);
    notifyDependency("rename", "dependency");
    await vi.waitFor(() => expect(driver.direct).toHaveBeenCalledTimes(3));
    expect(handles[1]!.close).toHaveBeenCalled();
    expect(driver.direct.mock.calls[2]![0]).toBe(dependency);
    await vi.waitFor(() => expect(emit).toHaveBeenCalled());
    expect(emit.mock.calls.flatMap(([, changes]) => changes)).not.toContainEqual(
      expect.objectContaining({ path: "node_modules/dependency/dependency" }),
    );
  });

  it("cancels setup without creating a watcher when the last owner leaves", async () => {
    const pending = watchers.watch(root);
    await watchers.unwatch(root);
    await pending;
    expect(driver.recursive).not.toHaveBeenCalled();
    expect(driver.direct).not.toHaveBeenCalled();
  });

  it("refreshes a root listing when a recursively excluded directory appears", async () => {
    await watchers.watch(root);
    await watchers.watchListedDirectory(root, "");
    const notify = driver.direct.mock.calls[0]![2] as (event: string, filename: string) => void;
    await fs.mkdir(path.join(root, ".venv"));
    notify("rename", ".venv");
    await vi.waitFor(() => expect(emit).toHaveBeenCalledWith(root, [
      { path: ".venv", kind: "changed", directory: true },
    ]));
  });
});

describe("following an open file", () => {
  // The batch windows run on this clock: a test steps through them, and
  // reads the length each one asked for, instead of sleeping against them.
  type Tick = { run: () => void; ms: number; cancelled: boolean };
  let ticks: Tick[];
  const clock: Schedule = (run, ms) => {
    const tick = { run, ms, cancelled: false };
    ticks.push(tick);
    return () => { tick.cancelled = true; };
  };
  const waiting = () => ticks.filter((tick) => !tick.cancelled);
  const elapse = () => {
    const due = waiting();
    ticks = [];
    for (const tick of due) tick.run();
  };
  let realRoot: string;
  const on = (event: string) => (relative: string) =>
    (recursive.on.mock.calls.find(([name]) => name === event)![1] as (target: string) => void)(path.join(realRoot, relative));

  beforeEach(async () => {
    ticks = [];
    watchers = new FileWatchers(emit, clock);
    realRoot = await fs.realpath(root);
  });

  it("reports an open file's rename as a move, even when its add arrives after the batch window", async () => {
    await fs.writeFile(path.join(root, "notes.txt"), "draft\n");
    await fs.writeFile(path.join(root, "other.txt"), "other\n");
    await watchers.watch(root);
    await watchers.watchEntry(root, await statFile(root, "notes.txt"));
    await fs.rename(path.join(realRoot, "notes.txt"), path.join(realRoot, "renamed.txt"));
    // A file nobody has open is still a plain removal beside it.
    await fs.rm(path.join(realRoot, "other.txt"));
    on("unlink")("notes.txt");
    on("unlink")("other.txt");
    // The removal of an open file waits longer than a batch for its add,
    // which chokidar holds back until the size has settled (awaitWriteFinish).
    expect(waiting().map((tick) => tick.ms)).toEqual([250]);
    on("add")("renamed.txt");
    elapse();
    await vi.waitFor(() => expect(emit).toHaveBeenCalled());
    expect(emit).toHaveBeenCalledTimes(1);
    expect(emit.mock.calls[0]![1]).toEqual(expect.arrayContaining([
      { kind: "moved", previousPath: "notes.txt", path: "renamed.txt", directory: false },
      { kind: "removed", path: "other.txt", directory: false },
    ]));
    expect(emit.mock.calls[0]![1]).toHaveLength(2);
  });

  it("keeps following an open file that was deleted and restored under its name", async () => {
    await fs.writeFile(path.join(root, "notes.txt"), "draft\n");
    await watchers.watch(root);
    await watchers.watchEntry(root, await statFile(root, "notes.txt"));
    // `git checkout other && git checkout -`: gone, then back, with the tab open.
    await fs.rm(path.join(realRoot, "notes.txt"));
    on("unlink")("notes.txt");
    elapse();
    await vi.waitFor(() => expect(emit).toHaveBeenCalledTimes(1));
    await fs.writeFile(path.join(realRoot, "notes.txt"), "draft\n");
    on("add")("notes.txt");
    elapse();
    await vi.waitFor(() => expect(emit).toHaveBeenCalledTimes(2));
    // Then the agent's `mv`.
    await fs.rename(path.join(realRoot, "notes.txt"), path.join(realRoot, "renamed.txt"));
    on("unlink")("notes.txt");
    on("add")("renamed.txt");
    elapse();
    await vi.waitFor(() => expect(emit).toHaveBeenCalledTimes(3));
    expect(emit.mock.calls[2]![1]).toEqual([
      { kind: "moved", previousPath: "notes.txt", path: "renamed.txt", directory: false },
    ]);
  });

  it("follows a file moved after the app saved it", async () => {
    await fs.writeFile(path.join(root, "notes.txt"), "draft\n");
    await watchers.watch(root);
    await watchers.watchEntry(root, await statFile(root, "notes.txt"));
    const before = (await fs.stat(path.join(realRoot, "notes.txt"))).ino;
    // Cmd+S: an atomic rename, so a new inode under the same name.
    await writeTextFile(root, "notes.txt", "saved\n", revisionOf("draft\n"));
    expect((await fs.stat(path.join(realRoot, "notes.txt"))).ino).not.toBe(before);
    on("change")("notes.txt");
    elapse();
    await vi.waitFor(() => expect(emit).toHaveBeenCalledTimes(1));
    // Then the agent's `mv`.
    await fs.rename(path.join(realRoot, "notes.txt"), path.join(realRoot, "renamed.txt"));
    on("unlink")("notes.txt");
    on("add")("renamed.txt");
    elapse();
    await vi.waitFor(() => expect(emit).toHaveBeenCalledTimes(2));
    expect(emit.mock.calls[1]![1]).toEqual([
      { kind: "moved", previousPath: "notes.txt", path: "renamed.txt", directory: false },
    ]);
  });

  it("follows a file moved after the app saved it, before the save's echo arrives", async () => {
    await fs.writeFile(path.join(root, "notes.txt"), "draft\n");
    await watchers.watch(root);
    await watchers.watchEntry(root, await statFile(root, "notes.txt"));
    await writeTextFile(root, "notes.txt", "saved\n", revisionOf("draft\n"));
    // What `explorer.writeText` does after the write lands.
    await watchers.refreshEntry(root, "notes.txt");
    await fs.rename(path.join(realRoot, "notes.txt"), path.join(realRoot, "renamed.txt"));
    on("unlink")("notes.txt");
    on("add")("renamed.txt");
    elapse();
    await vi.waitFor(() => expect(emit).toHaveBeenCalledTimes(1));
    expect(emit.mock.calls[0]![1]).toEqual([
      { kind: "moved", previousPath: "notes.txt", path: "renamed.txt", directory: false },
    ]);
  });

  it("forgets a closed tab's file: its removal is a removal, in one batch window", async () => {
    await fs.writeFile(path.join(root, "a.txt"), "a\n");
    await fs.writeFile(path.join(root, "b.txt"), "b\n");
    // Two tabs on the root; the first one closes.
    await watchers.watch(root);
    await watchers.watch(root);
    await watchers.watchEntry(root, await statFile(root, "a.txt"));
    await watchers.watchEntry(root, await statFile(root, "b.txt"));
    await watchers.unwatch(root, ["a.txt"]);
    await fs.rename(path.join(realRoot, "a.txt"), path.join(realRoot, "c.txt"));
    on("unlink")("a.txt");
    expect(waiting().map((tick) => tick.ms)).toEqual([80]);
    on("add")("c.txt");
    elapse();
    await vi.waitFor(() => expect(emit).toHaveBeenCalledTimes(1));
    expect(emit.mock.calls[0]![1]).toEqual([
      { kind: "removed", path: "a.txt", directory: false },
      { kind: "added", path: "c.txt", directory: false },
    ]);
  });

  it("holds a file again when a tab gives it back and watches again (a remount)", async () => {
    await fs.writeFile(path.join(root, "a.txt"), "a\n");
    await watchers.watch(root);
    await watchers.watch(root);
    await watchers.watchEntry(root, await statFile(root, "a.txt"));
    await watchers.unwatch(root, ["a.txt"]);
    await watchers.watch(root, ["a.txt"]);
    await fs.rename(path.join(realRoot, "a.txt"), path.join(realRoot, "c.txt"));
    on("unlink")("a.txt");
    on("add")("c.txt");
    elapse();
    await vi.waitFor(() => expect(emit).toHaveBeenCalledTimes(1));
    expect(emit.mock.calls[0]![1]).toEqual([{ kind: "moved", previousPath: "a.txt", path: "c.txt", directory: false }]);
  });

  it("gives back a hold whose unwatch overtook the watch that takes it again", async () => {
    await fs.writeFile(path.join(root, "a.txt"), "a\n");
    await watchers.watch(root);
    // A remount: the tab's watch that holds `a.txt` again is still on its way when the tab closes
    // and its unwatch gives `a.txt` back.
    const remount = watchers.watch(root, ["a.txt"]);
    await watchers.unwatch(root, ["a.txt"]);
    await remount;
    await fs.rm(path.join(realRoot, "a.txt"));
    on("unlink")("a.txt");
    // No tab holds it, so its removal waits for no move.
    expect(waiting().map((tick) => tick.ms)).toEqual([80]);
  });

  it("follows an opened link that is renamed, and repeats its target's changes under the new name", async () => {
    await fs.mkdir(path.join(root, "versions"));
    await fs.writeFile(path.join(root, "versions", "v3.txt"), "v3\n");
    await fs.symlink(path.join("versions", "v3.txt"), path.join(root, "current.txt"));
    // The tree's watch and the tab's.
    await watchers.watch(root);
    await watchers.watch(root);
    await watchers.watchEntry(root, await statFile(root, "current.txt"));
    // The link itself is renamed; symlinks are not followed, so the events name the link.
    await fs.rename(path.join(realRoot, "current.txt"), path.join(realRoot, "latest.txt"));
    on("unlink")("current.txt");
    on("add")("latest.txt");
    elapse();
    await vi.waitFor(() => expect(emit).toHaveBeenCalledTimes(1));
    expect(emit.mock.calls[0]![1]).toEqual([
      { kind: "moved", previousPath: "current.txt", path: "latest.txt", directory: false },
    ]);
    await fs.writeFile(path.join(root, "versions", "v3.txt"), "v4\n");
    on("change")("versions/v3.txt");
    elapse();
    await vi.waitFor(() => expect(emit).toHaveBeenCalledTimes(2));
    expect(emit.mock.calls[1]![1].map((change) => change.path)).toEqual(["versions/v3.txt", "latest.txt"]);
    // The tab, now on the new name, closes: nothing is left held for either name.
    await watchers.unwatch(root, ["latest.txt"]);
    on("change")("versions/v3.txt");
    elapse();
    await vi.waitFor(() => expect(emit).toHaveBeenCalledTimes(3));
    expect(emit.mock.calls[2]![1].map((change) => change.path)).toEqual(["versions/v3.txt"]);
  });

  it("follows an opened link re-pointed to a new target and then renamed", async () => {
    await fs.mkdir(path.join(root, "versions"));
    await fs.writeFile(path.join(root, "versions", "v3.txt"), "v3\n");
    await fs.writeFile(path.join(root, "versions", "v4.txt"), "v4\n");
    await fs.symlink(path.join("versions", "v3.txt"), path.join(root, "current.txt"));
    await watchers.watch(root);
    await watchers.watchEntry(root, await statFile(root, "current.txt"));
    // `ln -sfn`: the old link is unlinked and a new one made under the same
    // name — a new inode, which the watcher reports as the name changed.
    const before = (await fs.lstat(path.join(realRoot, "current.txt"))).ino;
    await fs.unlink(path.join(realRoot, "current.txt"));
    await fs.symlink(path.join("versions", "v4.txt"), path.join(realRoot, "current.txt"));
    expect((await fs.lstat(path.join(realRoot, "current.txt"))).ino).not.toBe(before);
    on("change")("current.txt");
    elapse();
    await vi.waitFor(() => expect(emit).toHaveBeenCalledTimes(1));
    expect(emit.mock.calls[0]![1]).toEqual([
      { kind: "changed", path: "current.txt", directory: false, revision: revisionOf("v4\n") },
    ]);
    // Then the new link itself is renamed.
    await fs.rename(path.join(realRoot, "current.txt"), path.join(realRoot, "latest.txt"));
    on("unlink")("current.txt");
    on("add")("latest.txt");
    elapse();
    await vi.waitFor(() => expect(emit).toHaveBeenCalledTimes(2));
    expect(emit.mock.calls[1]![1]).toEqual([
      { kind: "moved", previousPath: "current.txt", path: "latest.txt", directory: false },
    ]);
  });

  it("repeats a re-pointed link's new target under its name, and its old target's no longer", async () => {
    await fs.mkdir(path.join(root, "versions"));
    await fs.mkdir(path.join(root, "releases"));
    await fs.writeFile(path.join(root, "versions", "v3.txt"), "v3\n");
    await fs.writeFile(path.join(root, "releases", "v4.txt"), "v4\n");
    await fs.symlink(path.join("versions", "v3.txt"), path.join(root, "current.txt"));
    await watchers.watch(root);
    await watchers.watchEntry(root, await statFile(root, "current.txt"));
    // `ln -sfn releases/v4.txt current.txt`.
    await fs.unlink(path.join(realRoot, "current.txt"));
    await fs.symlink(path.join("releases", "v4.txt"), path.join(realRoot, "current.txt"));
    on("change")("current.txt");
    elapse();
    await vi.waitFor(() => expect(emit).toHaveBeenCalledTimes(1));
    // The new target's directory is watched now; its writes come from there.
    expect(driver.direct.mock.calls.map(([directory]) => directory)).toContain(path.join(realRoot, "releases"));
    await fs.writeFile(path.join(root, "releases", "v4.txt"), "v4, edited\n");
    on("change")("releases/v4.txt");
    elapse();
    await vi.waitFor(() => expect(emit).toHaveBeenCalledTimes(2));
    expect(emit.mock.calls[1]![1].map((change) => change.path)).toEqual(["releases/v4.txt", "current.txt"]);
    // The old target is no longer the link's file.
    await fs.writeFile(path.join(root, "versions", "v3.txt"), "v3, edited\n");
    on("change")("versions/v3.txt");
    elapse();
    await vi.waitFor(() => expect(emit).toHaveBeenCalledTimes(3));
    expect(emit.mock.calls[2]![1].map((change) => change.path)).toEqual(["versions/v3.txt"]);
  });

  it("reads only the changed files a tab has open", async () => {
    const names = Array.from({ length: 40 }, (_, index) => `file-${index}.txt`);
    for (const name of names) await fs.writeFile(path.join(root, name), `${name}\n`);
    await watchers.watch(root);
    await watchers.watchEntry(root, await statFile(root, "file-7.txt"));
    const readFile = vi.spyOn(fs, "readFile");
    try {
      for (const name of names) on("change")(name);
      elapse();
      await vi.waitFor(() => expect(emit).toHaveBeenCalledTimes(1));
      expect(readFile).toHaveBeenCalledTimes(1);
      expect(readFile.mock.calls[0]![0]).toBe(path.join(realRoot, "file-7.txt"));
      const changes = emit.mock.calls[0]![1];
      expect(changes).toHaveLength(40);
      expect(changes.filter((change) => "revision" in change)).toEqual([
        { path: "file-7.txt", kind: "changed", directory: false, revision: revisionOf("file-7.txt\n") },
      ]);
    } finally {
      readFile.mockRestore();
    }
  });
});
