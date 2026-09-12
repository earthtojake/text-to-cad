import { describe, expect, it } from "vitest";

import { recentProjects } from "@renderer/lib/projects";
import type { Project, Session } from "@shared/types";

/**
 * The order the project chip's `Recent` list is drawn in. There is no
 * `lastUsedAt` on a project, so the answer comes out of the session index —
 * which is the whole reason this is a function worth testing rather than a
 * `sort` inside the menu.
 */
const project = (id: string, createdAt: number): Project => ({
  id,
  name: id,
  path: `/tmp/${id}`,
  createdAt,
});

const session = (projectId: string, updatedAt: number, overrides: Partial<Session> = {}): Session => ({
  id: `${projectId}-${updatedAt}`,
  projectId,
  agentId: "codex",
  cwd: "/repo",
  gitMode: "none",
  title: "A thread",
  createdAt: 0,
  updatedAt,
  status: "idle",
  acpSessionId: null,
  changedFiles: 0,
  insertions: 0,
  deletions: 0,
  archived: false,
  pinned: false,
  sessionHead: null,
  turnHead: null,
  turnStartedAt: null,
  ...overrides,
});

const names = (projects: Project[]) => projects.map((entry) => entry.id);

describe("recentProjects", () => {
  const projects = [project("first", 1), project("second", 2), project("third", 3)];

  it("puts the project with the newest session first", () => {
    const sessions = [session("first", 10), session("third", 30), session("second", 20)];
    expect(names(recentProjects(projects, sessions))).toEqual(["third", "second", "first"]);
  });

  it("reads a project's activity as its newest session, not its last one", () => {
    const sessions = [session("first", 99), session("first", 1), session("second", 50)];
    expect(names(recentProjects(projects, sessions))).toEqual(["first", "second", "third"]);
  });

  it("counts an archived thread: the folder was still where the work happened", () => {
    const sessions = [session("third", 5), session("first", 40, { archived: true })];
    expect(names(recentProjects(projects, sessions))).toEqual(["first", "third", "second"]);
  });

  it("leaves projects nobody has run a thread in in the list's own order", () => {
    expect(names(recentProjects(projects, []))).toEqual(["first", "second", "third"]);
    expect(names(recentProjects(projects, [session("second", 7)]))).toEqual([
      "second",
      "first",
      "third",
    ]);
  });

  it("breaks a tie by the list's order, so the same index gives the same menu", () => {
    const sessions = [session("third", 12), session("first", 12)];
    expect(names(recentProjects(projects, sessions))).toEqual(["first", "third", "second"]);
  });

  it("ignores a session whose project has gone, and does not mutate its input", () => {
    const sessions = [session("removed", 100), session("second", 4)];
    const order = [...projects];
    expect(names(recentProjects(projects, sessions))).toEqual(["second", "first", "third"]);
    expect(projects).toEqual(order);
  });
});
