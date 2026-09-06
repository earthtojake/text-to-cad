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

  it("creates the four tables the app indexes", () => {
    const { db, statements } = fakeDb();
    runMigrations(db, MIGRATIONS);
    const sql = statements.join("\n");
    for (const table of ["projects", "sessions", "settings", "explorer_tabs"]) {
      expect(sql).toContain(`CREATE TABLE ${table}`);
    }
  });
});
