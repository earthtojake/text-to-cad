import { describe, expect, it } from "vitest";

import { MIGRATIONS, runMigrations, type Migration, type MigrationDb } from "@main/db/migrations";

/**
 * A recording stand-in for a sqlite handle. `runMigrations` was written
 * against this interface precisely so the ordering and the rollback can be
 * tested without a native module built for Electron's ABI.
 */
function fakeDb(startVersion = 0, failOn?: number) {
  let version = startVersion;
  const statements: string[] = [];
  const db: MigrationDb = {
    pragma: (source) => (source === "user_version" ? version : undefined),
    exec: (source) => {
      statements.push(source);
      const setVersion = /^PRAGMA user_version = (\d+)$/.exec(source.trim());
      if (setVersion?.[1]) {
        version = Number(setVersion[1]);
      }
      if (failOn !== undefined && source.includes(`-- migration ${failOn}`)) {
        throw new Error("boom");
      }
      return undefined;
    },
  };
  return { db, statements, version: () => version };
}

const fixture = (count: number): Migration[] =>
  Array.from({ length: count }, (_unused, index) => ({
    version: index + 1,
    name: `m${index + 1}`,
    up: `-- migration ${index + 1}`,
  }));

describe("runMigrations", () => {
  it("applies every migration in order on a fresh database", () => {
    const { db, statements, version } = fakeDb();
    expect(runMigrations(db, fixture(3))).toBe(3);
    expect(version()).toBe(3);
    expect(statements.filter((sql) => sql.startsWith("-- migration"))).toEqual([
      "-- migration 1",
      "-- migration 2",
      "-- migration 3",
    ]);
  });

  it("skips migrations the database has already run", () => {
    const { db, statements } = fakeDb(2);
    runMigrations(db, fixture(3));
    expect(statements.filter((sql) => sql.startsWith("-- migration"))).toEqual(["-- migration 3"]);
  });

  it("does nothing when the database is current", () => {
    const { db, statements } = fakeDb(3);
    runMigrations(db, fixture(3));
    expect(statements).toEqual([]);
  });

  it("rolls the failing migration back and stops", () => {
    const { db, statements, version } = fakeDb(0, 2);
    expect(() => runMigrations(db, fixture(3))).toThrow(/migration 2 \(m2\) failed/);
    // Migration 1 committed; 2 rolled back; 3 never ran.
    expect(version()).toBe(1);
    expect(statements).toContain("ROLLBACK");
    expect(statements).not.toContain("-- migration 3");
  });

  it("refuses migrations that are not numbered 1..n in order", () => {
    const { db } = fakeDb();
    const outOfOrder: Migration[] = [
      { version: 1, name: "a", up: "" },
      { version: 3, name: "c", up: "" },
    ];
    expect(() => runMigrations(db, outOfOrder)).toThrow(/1\.\.n/);
  });

  it("ships migrations that satisfy that rule", () => {
    const { db } = fakeDb();
    expect(() => runMigrations(db, MIGRATIONS)).not.toThrow();
  });

  it("creates the five tables the app indexes", () => {
    const { db, statements } = fakeDb();
    runMigrations(db, MIGRATIONS);
    const sql = statements.join("\n");
    for (const table of ["projects", "sessions", "settings", "explorer_tabs", "agent_options"]) {
      expect(sql).toContain(`CREATE TABLE ${table}`);
    }
  });

  it("gives agent_options a column for each thing the composer's chips need", () => {
    const { db, statements } = fakeDb(5);
    runMigrations(db, MIGRATIONS);
    // The sessions table is never rebuilt from here on: an installed app is
    // already at 5, so only the migrations above it run.
    const sql = statements.join("\n");
    expect(sql).not.toContain("CREATE TABLE sessions");
    for (const column of [
      "agent_id",
      "options",
      "options_at",
      "default_model",
      // The one mode chip is drawn on the new-session screen too, so the
      // modes and the mode picked for the next session are cached with them
      // (migration 8).
      "modes",
      "default_mode",
      // The effort is per model, not per agent (migration 9): the level
      // picked for each model, and the levels each model offers.
      "default_efforts",
      "effort_options",
    ]) {
      expect(sql).toContain(column);
    }
    // And the flat one is gone with nothing left reading it — a level stored
    // against no model is not an answer to "which effort for this model".
    expect(sql).toContain("ALTER TABLE agent_options DROP COLUMN default_effort");
  });

  /**
   * The effort, re-keyed by model on a database that already caches options.
   * Claude reports its `effort` option for whichever model the session is on
   * and its levels change with the model, so one `default_effort` per agent
   * carried the outgoing model's level onto the incoming one — and the model
   * and the mode, which really are per provider, have to survive the change.
   */
  it("re-keys the effort by model without rebuilding the table", () => {
    const { db, statements, version } = fakeDb(8);
    expect(runMigrations(db, MIGRATIONS)).toBe(MIGRATIONS.at(-1)!.version);
    expect(version()).toBe(MIGRATIONS.at(-1)!.version);
    const sql = statements.join("\n");
    expect(sql).not.toContain("CREATE TABLE agent_options");
    expect(sql).not.toContain("DROP TABLE agent_options");
    expect(sql).toContain("ALTER TABLE agent_options ADD COLUMN default_efforts TEXT");
    expect(sql).toContain("ALTER TABLE agent_options ADD COLUMN effort_options TEXT");
    expect(sql).toContain("ALTER TABLE agent_options DROP COLUMN default_effort");
    for (const kept of ["default_model", "default_mode"]) {
      expect(sql).not.toContain(`DROP COLUMN ${kept}`);
    }
  });

  /**
   * The modes, added to a database that already has an `agent_options` row
   * per agent: the mode chip is the app's one permission control and it is
   * drawn before a session exists, so the cache needs the half of the
   * `session/new` reply it was not keeping.
   */
  it("adds the modes columns to a database that already caches options", () => {
    const { db, statements, version } = fakeDb(7);
    expect(runMigrations(db, MIGRATIONS)).toBe(MIGRATIONS.at(-1)!.version);
    expect(version()).toBe(MIGRATIONS.at(-1)!.version);
    const sql = statements.join("\n");
    expect(sql).not.toContain("CREATE TABLE agent_options");
    expect(sql).toContain("ALTER TABLE agent_options ADD COLUMN modes TEXT");
    expect(sql).toContain("ALTER TABLE agent_options ADD COLUMN default_mode TEXT");
  });

  /**
   * The sidebar's `Pinned` section. A pin is a column on the session, added
   * to an installed database rather than shipped in migration 1 — which is
   * the whole point of the runner, and the case a `DEFAULT 0` has to cover:
   * every row that already exists is unpinned.
   */
  it("adds the pinned column to a database that already has sessions", () => {
    const { db, statements, version } = fakeDb(6);
    expect(runMigrations(db, MIGRATIONS)).toBe(MIGRATIONS.at(-1)!.version);
    expect(version()).toBe(MIGRATIONS.at(-1)!.version);
    const sql = statements.join("\n");
    expect(sql).not.toContain("CREATE TABLE sessions");
    expect(sql).toContain("ALTER TABLE sessions ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0");
  });

  /**
   * The snapshot each session's transcript paints from while its agent
   * reconnects (src/main/acp/snapshots.ts). A table of its own, keyed by the
   * session and cascading with it: the sidebar reads the `sessions` row for
   * every title it lists, and a half-megabyte JSON blob does not belong in
   * that read.
   */
  it("adds the session_state table without touching the sessions table", () => {
    const { db, statements, version } = fakeDb(9);
    expect(runMigrations(db, MIGRATIONS)).toBe(MIGRATIONS.at(-1)!.version);
    expect(version()).toBe(MIGRATIONS.at(-1)!.version);
    const sql = statements.join("\n");
    expect(sql).toContain("CREATE TABLE session_state");
    expect(sql).toContain("REFERENCES sessions(id) ON DELETE CASCADE");
    expect(sql).not.toContain("ALTER TABLE sessions");
  });
});
