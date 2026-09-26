import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type * as NodeFs from "node:fs";
import type { Mock } from "vitest";
import { FileWatchers, statFile } from "@main/explorer/fs";
import type { FileChange } from "@main/explorer/fs";

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
  root = await fs.mkdtemp(path.join(os.tmpdir(), "hardcore-watch-"));
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
      { path: "runtime-bundle/settings.txt", kind: "changed", directory: false },
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
