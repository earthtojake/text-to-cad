import { beforeEach, expect, it, vi } from "vitest";

const sqlite = vi.hoisted(() => ({ rows: [] as { payload: string }[], inserted: [] as unknown[][] }));
vi.mock("@main/db/index", () => ({
  db: () => ({
    prepare: (sql: string) => ({
      all: () => sqlite.rows,
      run: (...args: unknown[]) => {
        if (sql.startsWith("INSERT INTO explorer_tabs")) sqlite.inserted.push(args);
      },
    }),
    transaction: (write: () => void) => write,
  }),
}));

import { explorerTabs, sessions } from "@main/db/repositories";
import { SessionSchema } from "@shared/types";
import type { ExplorerTab } from "@shared/types";

const drawing: ExplorerTab = { id: "scratch", sessionId: "s1", projectId: "p1", order: 1, kind: "drawing", title: "Drawing", root: null };
const file: ExplorerTab = { id: "file", sessionId: "s1", projectId: "p1", order: 0, kind: "file", path: "README.md", root: null, panel: null };

beforeEach(() => {
  sqlite.rows = []; sqlite.inserted = [];
  vi.spyOn(sessions, "get").mockReturnValue(SessionSchema.parse({
    id: "s1", projectId: "p1", agentId: "codex", cwd: "/project", gitMode: "none",
    title: "Session", createdAt: 1, updatedAt: 1, status: "idle",
  }));
});

it("filters scratch drawings even when called directly below the IPC guard", () => {
  expect(explorerTabs.replace("s1", [file, drawing])).toEqual([file]);
  expect(sqlite.inserted).toHaveLength(1);
  expect(sqlite.inserted[0]?.[2]).toBe("file");
  expect(JSON.stringify(sqlite.inserted)).not.toContain("scratch");
});

it("refuses to restore scratch drawing rows written by an older build", () => {
  sqlite.rows = [{ payload: JSON.stringify(file) }, { payload: JSON.stringify(drawing) }];
  expect(explorerTabs.list("s1")).toEqual([file]);
});

it("rejects another session's tabs before replacing anything", () => {
  expect(() => explorerTabs.replace("s1", [{ ...file, sessionId: "another" }])).toThrow(/different session/);
  expect(sqlite.inserted).toEqual([]);
});
