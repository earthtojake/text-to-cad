/**
 * The app's index: sessions, settings and each session's explorer
 * strip. It lives under `app.getPath("userData")`, which is per-user and
 * survives updates.
 *
 * What this database is NOT is the transcript store. The agent owns
 * transcripts and `session/load` replays them (plan §5); duplicating them here
 * would create a second truth that goes stale the moment someone runs
 * `codex resume` in a terminal.
 */
import fs from "node:fs";
import path from "node:path";

import Database from "better-sqlite3";
import { app } from "electron";

import { MIGRATIONS, runMigrations } from "./migrations";

export type Db = Database.Database;

let handle: Db | null = null;
/**
 * Set by `closeDb` on quit. Anything that reaches for the database after that
 * gets an error rather than a fresh connection — a second connection opened
 * mid-quit re-runs the migration check and is never closed.
 */
let closed = false;

/** How many pre-upgrade backups (`<db>.before-vN-<ms>.bak`) are kept. */
export const UPGRADE_BACKUPS_KEPT = 3;

/** Absolute path of the sqlite file. */
export function databaseFile() {
  return path.join(app.getPath("userData"), "text-to-cad.db");
}

/**
 * Open (once) and migrate. Every repository goes through here rather than
 * holding its own handle, so there is exactly one connection per process and
 * the migration runs before the first read.
 */
export function db(): Db {
  if (handle) {
    return handle;
  }
  if (closed) {
    throw new Error("[database] used after closeDb(): the app is quitting and the connection is closed");
  }
  const opened = new Database(databaseFile());
  // WAL keeps a long-lived reader (the sidebar) from blocking a writer (a
  // session updating its status mid-turn).
  opened.pragma("journal_mode = WAL");
  opened.pragma("foreign_keys = ON");
  try {
    const version = Number(opened.pragma("user_version", { simple: true }));
    const latest = MIGRATIONS.at(-1)!.version;
    if (version > 0 && version < latest) {
      // VACUUM INTO includes committed WAL contents. A filesystem copy of just
      // text-to-cad.db can silently miss recent sessions while WAL is in use.
      const backup = `${databaseFile()}.before-v${latest}-${Date.now()}.bak`;
      opened.prepare("VACUUM INTO ?").run(backup);
      console.info(`[database] upgrade backup: ${backup}`);
    }
    runMigrations(opened, MIGRATIONS);
    if (version > 0 && version < latest) {
      pruneUpgradeBackups(databaseFile());
    }
  } catch (error) {
    opened.close();
    // Never delete or recreate a database to hide a migration failure.
    throw error;
  }
  handle = opened;
  return handle;
}

/** Close the connection. Called on quit; safe to call twice. */
export function closeDb() {
  closed = true;
  handle?.close();
  handle = null;
}

/**
 * Keep the newest `keep` pre-upgrade backups of `file` and delete the rest.
 * Called after an upgrade has succeeded, so the backup just written is never
 * the one that goes. Newest by the millisecond stamp in the name; a file that
 * cannot be removed is logged and left.
 */
export function pruneUpgradeBackups(file: string, keep = UPGRADE_BACKUPS_KEPT): string[] {
  const directory = path.dirname(file);
  const prefix = `${path.basename(file)}.before-v`;
  const pattern = /^v\d+-(\d+)\.bak$/;
  let entries: string[];
  try {
    entries = fs.readdirSync(directory);
  } catch (error) {
    console.warn("[database] could not list upgrade backups:", error);
    return [];
  }
  const backups = entries
    .filter((name) => name.startsWith(prefix))
    .map((name) => ({ name, stamp: pattern.exec(name.slice(prefix.length - 1))?.[1] }))
    .filter((entry): entry is { name: string; stamp: string } => entry.stamp !== undefined)
    .sort((a, b) => Number(b.stamp) - Number(a.stamp));
  const removed: string[] = [];
  for (const { name } of backups.slice(keep)) {
    const target = path.join(directory, name);
    try {
      fs.rmSync(target);
      removed.push(target);
    } catch (error) {
      console.warn(`[database] could not remove old backup ${target}:`, error);
    }
  }
  return removed;
}

/**
 * What the startup error box says when launch fails before the first window:
 * the reason and, when the failure came from opening the database (a
 * newer-schema refusal, a failed migration, a pre-upgrade backup on a full
 * disk), the database file it is about. A CAD runtime or bridge failure has
 * nothing to do with that file and does not name it.
 */
export function startupFailureMessage(error: unknown, fromDatabase: boolean): string {
  const reason = error instanceof Error ? error.message : String(error);
  if (!fromDatabase) {
    return reason;
  }
  let file: string;
  try {
    file = databaseFile();
  } catch {
    file = "(unknown)";
  }
  return `${reason}\n\nDatabase: ${file}`;
}
