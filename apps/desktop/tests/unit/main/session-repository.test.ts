import { DatabaseSync } from "node:sqlite";

import { beforeEach, describe, expect, it, vi } from "vitest";

import { MIGRATIONS, runMigrations } from "@main/db/migrations";
import type { Session } from "@shared/types";

// better-sqlite3 is built for Electron's ABI and will not load under Node, so
// the real SQL runs on node:sqlite behind the three methods the repository
// uses (`prepare().all/get/run`). The schema is the real migrations'.
const env = vi.hoisted(() => ({ handle: null as unknown }));
vi.mock("@main/db/index", () => ({ db: () => env.handle }));

const adapt = (raw: DatabaseSync) => ({
  pragma: (source: string, options?: { simple?: boolean }) => {
    const rows = raw.prepare(`PRAGMA ${source}`).all() as Record<string, unknown>[];
    return options?.simple ? Object.values(rows[0] ?? {})[0] : rows;
  },
  exec: (source: string) => raw.exec(source),
  prepare: (source: string) => {
    const statement = raw.prepare(source);
    return {
      all: (...args: never[]) => statement.all(...args),
      get: (...args: never[]) => statement.get(...args),
      run: (...args: never[]) => statement.run(...args),
    };
  },
});

const base = {
  projectId: "/x", agentId: "claude-code", cwd: "/x", gitMode: "worktree", title: "t", titleSource: "prompt",
  createdAt: 1, updatedAt: 2, status: "closed", acpSessionId: null, changedFiles: 0, insertions: 0, deletions: 0,
  archived: false, pinned: false,
} as const;

describe("sessions repository on a real sqlite", () => {
  let raw: DatabaseSync;
  beforeEach(() => {
    raw = new DatabaseSync(":memory:");
    env.handle = adapt(raw);
  });

  it("round-trips worktree_owned, and a row from before the column reads as not owned", async () => {
    const { sessions } = await import("@main/db/repositories");
    // A v11 database with one row in it, then the newest migration on top.
    runMigrations(adapt(raw), MIGRATIONS.slice(0, 11));
    raw.exec(`INSERT INTO sessions (id, project_id, agent_id, cwd, git_mode, title, created_at, updated_at, status)
              VALUES ('old', '/x', 'claude-code', '/x', 'worktree', 't', 1, 2, 'closed')`);
    runMigrations(adapt(raw), MIGRATIONS);

    expect(sessions.get("old")?.worktreeOwned).toBeUndefined();
    sessions.upsert({ ...base, id: "cut", worktreePath: "/wt/cut", worktreeOwned: true } as Session);
    sessions.upsert({ ...base, id: "given", worktreePath: "/wt/given" } as Session);
    expect(sessions.get("cut")?.worktreeOwned).toBe(true);
    expect(sessions.get("given")?.worktreeOwned).toBeUndefined();
    // The flag is written on update too, not only on insert.
    sessions.upsert({ ...sessions.get("cut")!, worktreeOwned: false });
    expect(sessions.get("cut")?.worktreeOwned).toBeUndefined();
  });
});
