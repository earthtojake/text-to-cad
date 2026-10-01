import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const env = vi.hoisted(() => ({ userData: "", opened: 0, version: 0 }));

vi.mock("electron", () => ({ app: { getPath: () => env.userData } }));
// better-sqlite3 is built for Electron's ABI and will not load here; the
// lifecycle only needs a handle that counts opens and answers `user_version`.
vi.mock("better-sqlite3", () => ({
  default: class {
    constructor() {
      env.opened += 1;
    }
    pragma(source: string) {
      return source === "user_version" ? env.version : undefined;
    }
    prepare() {
      return { run: (file: string) => fs.writeFileSync(file, "") };
    }
    close() {}
  },
}));
vi.mock("@main/db/migrations", () => ({ MIGRATIONS: [{ version: 5 }], runMigrations: () => 5 }));

async function load() {
  vi.resetModules();
  return import("@main/db/index");
}

beforeEach(() => {
  env.userData = fs.mkdtempSync(path.join(os.tmpdir(), "text-to-cad-db-"));
  env.opened = 0;
  env.version = 0;
});

afterEach(() => {
  fs.rmSync(env.userData, { recursive: true, force: true });
});

describe("db lifecycle", () => {
  it("refuses to reopen after closeDb instead of leaking a second connection", async () => {
    const database = await load();
    database.db();
    database.closeDb();
    expect(() => database.db()).toThrow(/after closeDb/);
    expect(env.opened).toBe(1);
  });

  it("keeps only the three newest pre-upgrade backups after an upgrade", async () => {
    vi.spyOn(console, "info").mockImplementation(() => undefined);
    const database = await load();
    const file = database.databaseFile();
    for (const stamp of [100, 200, 300, 400]) {
      fs.writeFileSync(`${file}.before-v4-${stamp}.bak`, "");
    }
    fs.writeFileSync(path.join(env.userData, "unrelated.bak"), "");
    env.version = 4;
    database.db();

    const left = fs.readdirSync(env.userData).filter((name) => name.includes(".before-v"));
    expect(left).toHaveLength(3);
    expect(left).not.toContain("text-to-cad.db.before-v4-100.bak");
    expect(left).not.toContain("text-to-cad.db.before-v4-200.bak");
    expect(left).toContain("text-to-cad.db.before-v4-400.bak");
    expect(fs.existsSync(path.join(env.userData, "unrelated.bak"))).toBe(true);
  });

  it("names the database file in the startup failure message only for a database failure", async () => {
    const database = await load();
    const message = database.startupFailureMessage(new Error("database schema 9 is newer than this app supports (5)"), true);
    expect(message).toContain("newer than this app supports");
    expect(message).toContain(path.join(env.userData, "text-to-cad.db"));
    expect(database.startupFailureMessage(new Error("the MCP bridge could not listen"), false)).toBe(
      "the MCP bridge could not listen",
    );
  });
});
