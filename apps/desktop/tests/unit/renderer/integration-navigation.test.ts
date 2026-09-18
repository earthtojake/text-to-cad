import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { performIntegrationCommand } from "@renderer/state/integration-commands";
import { useExplorer } from "@renderer/state/explorer";
import { useProjects } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";
import { useUi } from "@renderer/state/ui";
import type { Project, Session } from "@shared/types";

const bindProject = useExplorer.getState().bindProject;
let sequence = 0, projectA: string, projectB: string;
function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>(done => { resolve = done; });
  return { promise, resolve };
}
beforeEach(() => {
  projectA = `navigation-a-${++sequence}`; projectB = `navigation-b-${sequence}`;
  useProjects.setState({ projects: [projectA, projectB].map(id => ({ id, path: `/projects/${id}`, name: id })) as Project[], activeId: projectA });
  useSessions.setState({ activeId: null, sessions: [] });
  useExplorer.setState({ bindProject, projectId: projectA, root: null, ready: true, tabs: [], activeId: null });
  useUi.setState({ route: "app" });
  vi.mocked(window.hardcore.explorer.loadTabs).mockResolvedValue([]);
});
afterEach(async () => {
  useExplorer.setState({ bindProject });
  await bindProject(null);
  vi.restoreAllMocks();
});
const open = (projectId: string, root: string | null = null, signal?: AbortSignal) => performIntegrationCommand({ requestId: "open", kind: "open-url", projectId, root, url: "https://example.com/" }, signal);

it("preserves the active worktree root when an agent opens another tab in this project", async () => {
  const root = "/worktrees/active";
  useExplorer.setState({ root });
  await open(projectA, root);
  expect(useExplorer.getState().root).toBe(root);
  expect(useExplorer.getState().tabs[0]).toMatchObject({ projectId: projectA, kind: "browser", root });
});
it("derives the selected session root when explicitly opening another project", async () => {
  const root = "/worktrees/project-b";
  useSessions.setState({ activeId: "worktree-session", sessions: [{ id: "worktree-session", projectId: projectB, cwd: root, worktreePath: root }] as Session[] });
  await open(projectB, root);
  expect(useExplorer.getState()).toMatchObject({ projectId: projectB, root, ready: true });
});
it("never opens a stale command in the project selected while restoration was pending", async () => {
  const pending = deferred();
  useExplorer.setState({ ready: false, bindProject: vi.fn(() => pending.promise) });
  const result = open(projectA);
  useProjects.setState({ activeId: projectB });
  useExplorer.setState({ projectId: projectB, ready: true });
  pending.resolve();
  await expect(result).rejects.toThrow("active project changed");
  expect(useExplorer.getState().tabs).toEqual([]);
  expect(useExplorer.getState().projectId).toBe(projectB);
});
it("cancels a queued open before creating a tab or closing settings", async () => {
  const pending = deferred();
  useExplorer.setState({ bindProject: vi.fn(() => pending.promise) });
  useUi.setState({ route: "settings" });
  const controller = new AbortController();
  const result = open(projectA, null, controller.signal);
  controller.abort(new Error("cancelled")); pending.resolve();
  await expect(result).rejects.toThrow("cancelled");
  expect(useExplorer.getState().tabs).toEqual([]);
  expect(useUi.getState().route).toBe("settings");
});
it.each(["show-tab", "close-tab"] as const)("rejects %s when the tab disappeared during project restoration", async kind => {
  const tab = useExplorer.getState().open("browser", { url: "https://example.com/" })!;
  const pending = deferred();
  const restore = vi.fn(() => pending.promise);
  useExplorer.setState({ bindProject: restore });
  const result = performIntegrationCommand({ requestId: "stale", kind, projectId: projectA, root: null, tabId: tab.id });
  await vi.waitFor(() => expect(restore).toHaveBeenCalled());
  useExplorer.getState().close(tab.id);
  pending.resolve();
  await expect(result).rejects.toThrow("closed or changed");
  expect(useExplorer.getState().activeId).toBeNull();
});
it("does not close a file replaced inside the same tab while admission was pending", async () => {
  const tab = useExplorer.getState().open("file", { path: "old.txt" })!;
  const pending = deferred();
  const restore = vi.fn(() => pending.promise);
  useExplorer.setState({ bindProject: restore });
  const result = performIntegrationCommand({ requestId: "replace", kind: "close-tab", projectId: projectA, root: null, tabId: tab.id });
  await vi.waitFor(() => expect(restore).toHaveBeenCalled());
  useExplorer.getState().update(tab.id, { path: "new.txt" });
  pending.resolve();
  await expect(result).rejects.toThrow("closed or changed");
  expect(useExplorer.getState().tabs[0]).toMatchObject({ id: tab.id, path: "new.txt" });
});
