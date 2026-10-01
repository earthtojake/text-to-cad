/** A deleted session's browser storage and artifacts go with it; archive keeps them; older builds' partitions migrate; orphans are swept. */
import fsSync from "node:fs";
import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
vi.mock("electron", () => ({ app: {}, session: {} }));
import {
  browserArtifactsRoot, browserPartition, browserPartitionName, browserSessionKey, clearBrowserSessionStorage, legacyPartitionName, sweepBrowserStorage,
} from "@main/browser/storage";

let userData: string, workspace: string;
beforeEach(async () => {
  userData = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), "browser-storage-")));
  workspace = path.join(userData, "workspace"); await fs.mkdir(workspace);
});
afterEach(async () => { await fs.rm(userData, { recursive: true, force: true }); });
const exists = (directory: string) => fs.stat(directory).then(() => true, () => false);
const scopeOf = (sessionId: string) => ({ sessionId, projectId: "project", root: workspace });
const live = (...ids: string[]) => () => ids.map(id => ({ id, projectId: "project", cwd: workspace }));
const partitions = () => path.join(userData, "Partitions");
async function onDisk(name: string) {
  await fs.mkdir(path.join(partitions(), name), { recursive: true });
  await fs.writeFile(path.join(partitions(), name, "Cookies"), name);
  return name;
}
const partitionOnDisk = (sessionId: string) => onDisk(browserPartitionName(scopeOf(sessionId)).slice("persist:".length));
async function artifacts(sessionId: string) {
  const directory = path.join(browserArtifactsRoot(userData), browserSessionKey(sessionId));
  await fs.mkdir(directory, { recursive: true }); await fs.writeFile(path.join(directory, "page.png"), "png");
  return directory;
}

it("clears every partition of a deleted session, and its artifacts, and nothing of another session", async () => {
  const doomed = await partitionOnDisk("deleted");
  await partitionOnDisk("kept");
  const doomedArtifacts = await artifacts("deleted");
  const keptArtifacts = await artifacts("kept");
  const clearStorageData = vi.fn().mockResolvedValue(undefined);
  const clearCache = vi.fn().mockResolvedValue(undefined);
  const fromPartition = vi.fn((_partition: string) => ({ clearStorageData, clearCache }));
  await clearBrowserSessionStorage("deleted", { userData, fromPartition });
  expect(fromPartition.mock.calls.map(([partition]) => partition)).toEqual([`persist:${doomed}`]);
  expect(clearStorageData).toHaveBeenCalledTimes(1);
  expect(clearCache).toHaveBeenCalledTimes(1);
  expect(await exists(doomedArtifacts)).toBe(false);
  expect(await exists(keptArtifacts)).toBe(true);
});

it("sweeps partitions and artifacts whose session no longer exists, and nothing else", async () => {
  const kept = await partitionOnDisk("live");
  const orphan = await partitionOnDisk("orphan");
  await onDisk("unrelated");
  const liveArtifacts = await artifacts("live");
  const orphanArtifacts = await artifacts("orphan");
  await sweepBrowserStorage(live("live", "archived-but-kept"), userData);
  expect((await fs.readdir(partitions())).sort()).toEqual([kept, "unrelated"].sort());
  expect(orphan).not.toBe(kept);
  expect(await exists(liveArtifacts)).toBe(true);
  expect(await exists(orphanArtifacts)).toBe(false);
});

it("never sweeps a partition or artifacts this run opened, even for a session the snapshot missed", async () => {
  const name = browserPartition(scopeOf("opened-mid-sweep"), userData).slice("persist:".length);
  await onDisk(name);
  const outputs = await artifacts("opened-mid-sweep");
  await sweepBrowserStorage(live(), userData);
  expect(await exists(path.join(partitions(), name))).toBe(true);
  expect(await exists(outputs)).toBe(true);
});

it("reads the sessions after listing the directories, so a session created mid-sweep keeps its storage", async () => {
  const orphan = await partitionOnDisk("orphan");
  // The session index is read (a snapshot without the new session), and
  // right after it the new session's storage lands on disk. Listed after the
  // read, that storage would look ownerless and be swept.
  let partition = "", outputs = "";
  const sessions = vi.fn(() => {
    const snapshot = live("already-live")();
    // Synchronously, as the index read is: create the storage before the sweep continues.
    const name = browserPartitionName(scopeOf("created-mid-sweep")).slice("persist:".length);
    fsSync.mkdirSync(path.join(partitions(), name), { recursive: true });
    fsSync.writeFileSync(path.join(partitions(), name, "Cookies"), name);
    partition = name;
    outputs = path.join(browserArtifactsRoot(userData), browserSessionKey("created-mid-sweep"));
    fsSync.mkdirSync(outputs, { recursive: true });
    return snapshot;
  });
  const swept = await sweepBrowserStorage(sessions, userData);
  expect(sessions).toHaveBeenCalledTimes(1);
  expect(await exists(path.join(partitions(), partition))).toBe(true);
  expect(await exists(outputs)).toBe(true);
  // The sweep itself still ran: the orphan listed before the read went.
  expect(swept).toEqual([path.join(partitions(), orphan)]);
});

it("renames an older build's partition for a live session instead of deleting its logins", async () => {
  // The name an older build gave it, spelled out here rather than taken from
  // the module: `browser-<sha256(JSON [session, project, root])>`.
  const legacy = await onDisk(`browser-${createHash("sha256").update(JSON.stringify(["migrated", "project", workspace])).digest("hex")}`);
  expect(legacy).toBe(legacyPartitionName(scopeOf("migrated")));
  await fs.writeFile(path.join(partitions(), legacy, "Local Storage"), "logged in");
  const orphanLegacy = await onDisk(`browser-${"a".repeat(64)}`);
  await sweepBrowserStorage(live("migrated"), userData);
  const current = browserPartitionName(scopeOf("migrated")).slice("persist:".length);
  expect((await fs.readdir(partitions())).sort()).toEqual([current]);
  expect(await fs.readFile(path.join(partitions(), current, "Cookies"), "utf8")).toBe(legacy);
  expect(await fs.readFile(path.join(partitions(), current, "Local Storage"), "utf8")).toBe("logged in");
  expect(orphanLegacy).not.toBe(legacy);
});

it("judges each older partition on its own: a gone worktree keeps its own, not everyone's", async () => {
  const missing = path.join(userData, "missing");
  const own = await onDisk(legacyPartitionName({ sessionId: "gone-worktree", projectId: "project", root: missing }));
  const ownerless = await onDisk(`browser-${"b".repeat(64)}`);
  await sweepBrowserStorage(() => [{ id: "gone-worktree", projectId: "project", cwd: missing }], userData);
  expect(await exists(path.join(partitions(), ownerless))).toBe(false);
  expect(await exists(path.join(partitions(), own))).toBe(false);
  const current = browserPartitionName({ sessionId: "gone-worktree", projectId: "project", root: missing }).slice("persist:".length);
  expect(await fs.readFile(path.join(partitions(), current, "Cookies"), "utf8")).toBe(own);
});

it("removes an older partition when its current name already exists", async () => {
  const legacy = await onDisk(legacyPartitionName(scopeOf("both-names")));
  const current = await partitionOnDisk("both-names");
  await sweepBrowserStorage(live("both-names"), userData);
  expect(await fs.readdir(partitions())).toEqual([current]);
  expect(await fs.readFile(path.join(partitions(), current, "Cookies"), "utf8")).toBe(current);
  expect(legacy).not.toBe(current);
});

it("migrates an older partition on first use, before Chromium creates the new one", async () => {
  const legacy = await onDisk(legacyPartitionName(scopeOf("first-use")));
  const partition = browserPartition(scopeOf("first-use"), userData);
  const current = path.join(partitions(), partition.slice("persist:".length));
  expect(await fs.readFile(path.join(current, "Cookies"), "utf8")).toBe(legacy);
  expect(await exists(path.join(partitions(), legacy))).toBe(false);
});

it("sweeps nothing when there is no browser storage yet", async () => {
  await expect(sweepBrowserStorage(live(), userData)).resolves.toEqual([]);
});
