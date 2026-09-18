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

import { explorerTabs } from "@main/db/repositories";
import type { ExplorerTab } from "@shared/types";

const drawing: ExplorerTab = { id: "scratch", projectId: "p1", order: 1, kind: "drawing", title: "Drawing", root: null };
const file: ExplorerTab = { id: "file", projectId: "p1", order: 0, kind: "file", path: "README.md", root: null, panel: null };

beforeEach(() => { sqlite.rows = []; sqlite.inserted = []; });

it("filters scratch drawings even when called directly below the IPC guard", () => {
  expect(explorerTabs.replace("p1", [file, drawing])).toEqual([file]);
  expect(sqlite.inserted).toHaveLength(1);
  expect(sqlite.inserted[0]?.[2]).toBe("file");
  expect(JSON.stringify(sqlite.inserted)).not.toContain("scratch");
});

it("refuses to restore scratch drawing rows written by an older build", () => {
  sqlite.rows = [{ payload: JSON.stringify(file) }, { payload: JSON.stringify(drawing) }];
  expect(explorerTabs.list("p1")).toEqual([file]);
});
