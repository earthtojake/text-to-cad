/**
 * The app's index: projects, the session index, settings and the explorer
 * strip. It lives under `app.getPath("userData")`, which is per-user and
 * survives updates.
 *
 * What this database is NOT is the transcript store. The agent owns
 * transcripts and `session/load` replays them (plan §5); duplicating them here
 * would create a second truth that goes stale the moment someone runs
 * `codex resume` in a terminal.
 */
import path from "node:path";

import Database from "better-sqlite3";
import { app } from "electron";

import { MIGRATIONS, runMigrations } from "./migrations";

export type Db = Database.Database;

let handle: Db | null = null;

/** Absolute path of the sqlite file. */
export function databaseFile() {
  return path.join(app.getPath("userData"), "hardcore.db");
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
  const opened = new Database(databaseFile());
  // WAL keeps a long-lived reader (the sidebar) from blocking a writer (a
  // session updating its status mid-turn).
  opened.pragma("journal_mode = WAL");
  opened.pragma("foreign_keys = ON");
  runMigrations(opened, MIGRATIONS);
  handle = opened;
  return handle;
}

/** Close the connection. Called on quit; safe to call twice. */
export function closeDb() {
  handle?.close();
  handle = null;
}
