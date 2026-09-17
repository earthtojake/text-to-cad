import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type * as NodeFs from "node:fs";
import type { Mock } from "vitest";
import { FileWatchers } from "@main/explorer/fs";
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
  await fs.writeFile(path.join(root, ".gitignore"), "/STEP/**\n*.unsupported\n");
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
  it("does not use Git ignore rules to suppress generated CAD or unknown files", async () => {
    await watchers.watch(root);
    const ignored = driver.recursive.mock.calls[0]![1].ignored as (target: string) => boolean;
    expect(ignored(path.join(root, "STEP", "tom.step"))).toBe(false);
    expect(ignored(path.join(root, "output.unsupported"))).toBe(false);
    expect(ignored(path.join(root, "node_modules", "dependency"))).toBe(true);
    expect(ignored(path.join(root, ".git", "objects"))).toBe(true);
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
