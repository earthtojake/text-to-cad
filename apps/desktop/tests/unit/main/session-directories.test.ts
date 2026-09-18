import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, expect, test, vi } from "vitest";

const stored = vi.hoisted(() => ({ rows: [] as { directory: string; created_at: number }[] }));
vi.mock("@main/db/index", () => ({ db: () => ({ prepare: () => ({ all: () => stored.rows }) }) }));
import { projects } from "@main/db/repositories";

const temporary: string[] = [];
afterEach(() => {
  stored.rows = [];
  for (const dir of temporary.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

test("choosing a directory creates no persistent project", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-directory-")); temporary.push(dir);
  expect(projects.add(dir)).toMatchObject({ id: fs.realpathSync(dir), path: fs.realpathSync(dir) });
  expect(projects.list()).toEqual([]);
});

test("legacy directory spellings remain stable when chosen through an alias", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-directory-")); temporary.push(dir);
  const alias = path.join(dir, "alias");
  const target = path.join(dir, "target"); fs.mkdirSync(target);
  fs.symlinkSync(target, alias, "junction");
  stored.rows = [{ directory: alias, created_at: 123 }];
  expect(projects.get(alias)).toMatchObject({ id: alias, path: alias });
  expect(projects.add(target)).toMatchObject({ id: alias, path: alias, createdAt: 123 });
});

test("a missing checkout does not erase its group or surviving worktree identity", () => {
  const missing = path.join(os.tmpdir(), "hardcore-missing-directory");
  stored.rows = [{ directory: missing, created_at: 1 }];
  expect(projects.list()).toHaveLength(1);
  expect(projects.get(missing)).toMatchObject({ id: missing, path: missing });
});
