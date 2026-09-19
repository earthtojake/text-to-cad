import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";

import { projectsFromSessions } from "@renderer/lib/projects";
import { sidebarSections } from "@renderer/lib/sidebar";
import { useActiveProject, useProjects } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";
import { SessionSchema, SidebarSettingsSchema } from "@shared/types";

const session = (id: string, directory: string, extra = {}) => SessionSchema.parse({
  id, projectId: directory, agentId: "fake", cwd: directory, gitMode: "none",
  title: id, createdAt: 1, updatedAt: 2, status: "idle", acpSessionId: `acp-${id}`, ...extra,
});

beforeEach(() => {
  useProjects.setState({ projects: [], ready: false, activeId: null, draft: null });
  useSessions.setState({ sessions: [], ready: false, activeId: null });
});

const sections = () => sidebarSections({
  projects: useProjects.getState().projects,
  sessions: useSessions.getState().sessions,
  filters: SidebarSettingsSchema.parse({}),
});

describe("session-derived directories", () => {
  it("groups worktrees with their original directory and derives labels and creation time", () => {
    const rows = [
      session("one", "/workspace/robot", { createdAt: 30 }),
      session("two", "/workspace/robot", { createdAt: 10, gitMode: "worktree", cwd: "/worktrees/robot-one" }),
      session("three", "/workspace/tool", { createdAt: 20 }),
    ];
    expect(projectsFromSessions(rows)).toEqual([
      { id: "/workspace/robot", path: "/workspace/robot", name: "robot", createdAt: 10 },
      { id: "/workspace/tool", path: "/workspace/tool", name: "tool", createdAt: 20 },
    ]);
    expect(rows[0]!.createdAt).toBe(30);
  });

  it("opens the first folder as a usable draft without creating a phantom group", async () => {
    const directory = { id: "/new/robot", path: "/new/robot", name: "robot", createdAt: 0 };
    vi.mocked(window.hardcore.projects.add).mockResolvedValueOnce(directory);
    await useProjects.getState().add();
    const active = renderHook(useActiveProject);
    expect(active.result.current).toEqual(directory);
    expect(useProjects.getState().projects).toEqual([]);
    expect(sections()).toEqual([]);
    // An unrelated session update cannot discard the folder being drafted in.
    useSessions.getState().receive([session("other", "/other")]);
    expect(useProjects.getState().activeId).toBe(directory.id);
    expect(useProjects.getState().draft).toEqual(directory);
    active.unmount();
  });

  it("retains the first-folder draft if the agent fails while creating its session", () => {
    const directory = { id: "/new/robot", path: "/new/robot", name: "robot", createdAt: 0 };
    useProjects.getState().selectDirectory(directory);
    useSessions.getState().receive([session("connecting", directory.id, { status: "connecting", acpSessionId: null })]);
    useSessions.getState().receive([]);
    expect(useProjects.getState().draft).toEqual(directory);
    expect(useProjects.getState().activeId).toBe(directory.id);
    expect(useProjects.getState().projects).toEqual([]);
  });

  it("materializes a directory only when the first session arrives", () => {
    useProjects.getState().selectDirectory({ id: "/new/robot", path: "/new/robot", name: "robot", createdAt: 0 });
    useSessions.getState().receive([session("first", "/new/robot")]);
    expect(useProjects.getState().draft).toBeNull();
    expect(useProjects.getState().activeId).toBe("/new/robot");
    expect(sections().map(section => section.id)).toEqual(["/new/robot"]);
  });

  it("keeps an explicitly opened archived transcript selected on unrelated updates", () => {
    const row = session("archived", "/workspace/robot", { archived: true });
    useSessions.getState().receive([row]);
    useSessions.getState().select(row.id);
    useSessions.getState().receive([row, session("other", "/other")]);
    expect(useSessions.getState().activeId).toBe(row.id);
    expect(useProjects.getState().activeId).toBe(row.projectId);
  });

  it("hides an archived last session's directory and restores it with the session", () => {
    const row = session("first", "/workspace/robot");
    useSessions.getState().receive([row]);
    useSessions.getState().select(row.id);
    useSessions.getState().receive([{ ...row, archived: true }]);
    expect(sections()).toEqual([]);
    expect(useSessions.getState().sessions).toHaveLength(1);
    expect(useSessions.getState().activeId).toBeNull();
    expect(useProjects.getState().activeId).toBeNull();
    // Archived descriptors remain derivable for Settings; there is no saved group.
    expect(useProjects.getState().projects[0]?.path).toBe(row.projectId);
    useSessions.getState().receive([row]);
    expect(sections().map(section => section.id)).toEqual([row.projectId]);
    useSessions.getState().receive([]);
    expect(useProjects.getState().projects).toEqual([]);
  });
});
