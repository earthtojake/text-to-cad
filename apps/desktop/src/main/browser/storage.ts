/**
 * What a session's browser leaves on disk: its storage partitions (cookies,
 * logins, cache) and the Playwright MCP artifacts directory. Both are named
 * from a hash of the session ID, so a deleted session's leftovers can be
 * found without the session row.
 */
import { createHash } from "node:crypto";
import { existsSync, realpathSync, renameSync } from "node:fs";
import fs from "node:fs/promises";
import path from "node:path";
import { app, session } from "electron";

export type BrowserScope = { sessionId: string; projectId: string; root: string };
type PartitionSession = { clearStorageData(): Promise<void>; clearCache(): Promise<void> };
export type BrowserStorageHost = { userData: string; fromPartition: (partition: string) => PartitionSession };

const sha256 = (value: string) => createHash("sha256").update(value).digest("hex");
const defaultHost = (): BrowserStorageHost => ({ userData: app.getPath("userData"), fromPartition: partition => session.fromPartition(partition) });
/** Partitions opened this run, per session: a new one may not be on disk yet. */
const opened = new Map<string, Set<string>>();
/** Partitions whose session was deleted this run: loaded, so left for the next launch's sweep. */
const cleared = new Set<string>();

export function browserScopeKey(scope: BrowserScope) { return JSON.stringify([scope.sessionId, scope.projectId, scope.root]); }
export function browserSessionKey(sessionId: string) { return sha256(sessionId); }
export function browserArtifactsRoot(userData: string) { return path.join(userData, "browser-artifacts"); }

/** The name alone, without migrating anything or recording a use. */
export const browserPartitionName = (scope: BrowserScope) => `persist:${partitionName(scope)}`;
const partitionName = (scope: BrowserScope) => `browser-${browserSessionKey(scope.sessionId)}-${sha256(browserScopeKey(scope)).slice(0, 32)}`;
/** The name before the session prefix; still on disk for sessions created by an older build. */
export const legacyPartitionName = (scope: BrowserScope) => `browser-${sha256(browserScopeKey(scope))}`;
const openedNames = () => new Set([...opened.values()].flatMap(names => [...names]).map(name => name.slice("persist:".length)));
function userDataOrNull() { try { return app.getPath("userData"); } catch { return null; } }

/** Move an older build's partition to its current name, so logins and cookies survive the rename. */
function migrateLegacyPartition(partitions: string, scope: BrowserScope) {
  const legacy = path.join(partitions, legacyPartitionName(scope));
  const next = path.join(partitions, partitionName(scope));
  if (!existsSync(legacy)) return false;
  if (existsSync(next)) return false;
  renameSync(legacy, next);
  return true;
}

/**
 * `persist:browser-<sha256(session)>-<sha256(scope)[:32]>`: pages in one
 * session and workspace share storage, separate sessions never do, and the
 * prefix names the owning session. The first use this run moves an older
 * build's `browser-<sha256(scope)>` directory to the new name, before
 * Chromium creates it.
 */
export function browserPartition(scope: BrowserScope, userData = userDataOrNull()) {
  const partition = `persist:${partitionName(scope)}`;
  const names = opened.get(scope.sessionId) ?? new Set<string>();
  if (!names.has(partition) && userData) {
    try { migrateLegacyPartition(path.join(userData, "Partitions"), scope); }
    catch (error) { console.warn(`[browser] could not migrate a browser partition: ${String(error)}`); }
  }
  names.add(partition); opened.set(scope.sessionId, names);
  return partition;
}

async function entries(directory: string) {
  try { return await fs.readdir(directory); } catch { return []; }
}

/** A deleted session's logins, cookies, cache and MCP artifacts go with it. Archive keeps them. */
export async function clearBrowserSessionStorage(sessionId: string, host: BrowserStorageHost = defaultHost()) {
  const key = browserSessionKey(sessionId);
  const partitions = new Set(opened.get(sessionId));
  opened.delete(sessionId);
  for (const entry of await entries(path.join(host.userData, "Partitions"))) {
    if (entry.startsWith(`browser-${key}-`)) partitions.add(`persist:${entry}`);
  }
  const results = await Promise.allSettled([
    ...[...partitions].map(async partition => {
      cleared.add(partition.slice("persist:".length));
      const storage = host.fromPartition(partition);
      await storage.clearStorageData();
      await storage.clearCache();
    }),
    fs.rm(path.join(browserArtifactsRoot(host.userData), key), { recursive: true, force: true }),
  ]);
  for (const result of results) if (result.status === "rejected") console.warn(`[browser] could not clear a deleted session's storage: ${String(result.reason)}`);
}

export type LiveBrowserSession = { id: string; projectId: string; cwd: string };

/**
 * Migrate, then remove what no session owns:
 * - an older build's `browser-<sha256(scope)>` partition is renamed to its
 *   current name when a live session's scope (its recorded directory, after
 *   realpath; the recorded spelling when that directory is gone) hashes to
 *   it. When the current name already exists Chromium opens only that one,
 *   so the old one is removed; so is one no live session's scope matches;
 * - a current partition or artifact directory whose session no longer exists
 *   (deleted while the app was not running, or by an older build) is removed.
 * The directories are listed before the sessions are read, so a session
 * created mid-sweep is never mistaken for an orphan; anything opened or
 * cleared this run is skipped as well (an agent's page can open before the
 * first renderer request).
 */
export async function sweepBrowserStorage(liveSessions: () => Iterable<LiveBrowserSession>, userData = app.getPath("userData")) {
  const partitions = path.join(userData, "Partitions");
  const artifacts = browserArtifactsRoot(userData);
  const [partitionEntries, artifactEntries] = await Promise.all([entries(partitions), entries(artifacts)]);
  const sessions = [...liveSessions()];
  const live = new Set(sessions.map(session => browserSessionKey(session.id)));
  const legacy = new Map<string, BrowserScope>();
  // Each session's scope costs a realpath: worked out only when an older build's partition is there to match.
  const anyLegacy = partitionEntries.some(entry => /^browser-[0-9a-f]{64}$/.test(entry));
  for (const session of anyLegacy ? sessions : []) {
    // A removed worktree still owns the partition its recorded path names:
    // the worktree may come back, and one such session must not keep every
    // other ownerless partition alive.
    let root: string;
    try { root = realpathSync(session.cwd); } catch { root = path.resolve(session.cwd); }
    const scope = { sessionId: session.id, projectId: session.projectId, root };
    legacy.set(legacyPartitionName(scope), scope);
  }
  const doomed: string[] = [];
  // Taken once: nothing in the loop below awaits, so nothing opens or clears a partition meanwhile.
  const skipped = new Set([...openedNames(), ...cleared]);
  for (const entry of partitionEntries) {
    const match = /^browser-([0-9a-f]{64})(-[0-9a-f]{32})?$/.exec(entry);
    if (!match || skipped.has(entry)) continue;
    if (match[2]) { if (!live.has(match[1]!)) doomed.push(path.join(partitions, entry)); continue; }
    const scope = legacy.get(entry);
    if (scope) {
      try {
        // Both names on disk: Chromium only ever opens the current one.
        if (!migrateLegacyPartition(partitions, scope) && existsSync(path.join(partitions, partitionName(scope)))) doomed.push(path.join(partitions, entry));
      } catch (error) { console.warn(`[browser] could not migrate ${entry}: ${String(error)}`); }
    } else doomed.push(path.join(partitions, entry));
  }
  const openedSessions = new Set([...opened.keys()].map(browserSessionKey));
  for (const entry of artifactEntries) {
    if (/^[0-9a-f]{64}$/.test(entry) && !live.has(entry) && !openedSessions.has(entry)) doomed.push(path.join(artifacts, entry));
  }
  await Promise.all(doomed.map(directory => fs.rm(directory, { recursive: true, force: true }).catch((error: unknown) => {
    console.warn(`[browser] could not remove orphaned browser storage ${directory}: ${String(error)}`);
  })));
  return doomed;
}
