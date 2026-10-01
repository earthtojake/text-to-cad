import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { performIntegrationCommand } from "@renderer/state/integration-commands";
import { readSessionStrip, useExplorer } from "@renderer/state/explorer";
import { useProjects } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";
import { desktopLiveDocuments } from "@renderer/state/live-documents";
import { useUi } from "@renderer/state/ui";
import type { Project, Session, PersistedExplorerTab } from "@shared/types";

let sequence = 0, sessionA: string, sessionB: string;
const projectId = "/shared/workspace";
beforeEach(async () => {
  sessionA = `navigation-a-${++sequence}`; sessionB = `navigation-b-${sequence}`;
  useProjects.setState({ projects: [{ id: projectId, path: projectId, name: "workspace" }] as Project[], activeId: projectId });
  useSessions.setState({ activeId: sessionA, sessions: [sessionA, sessionB].map(id => ({ id, projectId, cwd: projectId, archived: false })) as Session[] });
  vi.mocked(window.textToCad.explorer.loadTabs).mockResolvedValue([]);
  await useExplorer.getState().bindSession(sessionA, projectId);
  useUi.setState({ route: "app" });
});
afterEach(async () => {
  useExplorer.getState().discardSessionResources(sessionA);
  useExplorer.getState().discardSessionResources(sessionB);
  await useExplorer.getState().bindSession(null, null);
  vi.restoreAllMocks();
});
const open = (sessionId: string, signal?: AbortSignal) => performIntegrationCommand({ sessionId, projectId, requestId: "open", kind: "open-url", root: null, url: "https://example.com/" }, signal);

it("starts a second session in the same directory with no tabs and restores each independent strip", async () => {
  const first = useExplorer.getState().open("file", { path: "same.txt" })!;
  await useExplorer.getState().bindSession(sessionB, projectId);
  expect(useExplorer.getState().tabs).toEqual([]);
  const second = useExplorer.getState().open("file", { path: "same.txt" })!;
  expect(second.id).not.toBe(first.id);
  expect(second.sessionId).toBe(sessionB);
  await useExplorer.getState().bindSession(sessionA, projectId);
  expect(useExplorer.getState().tabs).toEqual([first]);
});
it("background opens and closes address only their owning session without navigating the user", async () => {
  const active = useExplorer.getState().open("drawing")!;
  useUi.getState().openSettings();
  const opened = await open(sessionB) as { tabId: string };
  expect(useExplorer.getState()).toMatchObject({ sessionId: sessionA, activeId: active.id, tabs: [active] });
  expect(useSessions.getState().activeId).toBe(sessionA);
  expect(useUi.getState().route).toBe("settings");
  expect((await readSessionStrip(sessionB)).tabs).toMatchObject([{ id: opened.tabId, sessionId: sessionB }]);
  await performIntegrationCommand({ sessionId: sessionB, projectId, requestId: "close", kind: "close-tab", tabId: opened.tabId });
  expect((await readSessionStrip(sessionB)).tabs).toEqual([]);
  expect(useExplorer.getState().tabs).toEqual([active]);
});
it.each(["tab-resource", "show-tab", "close-tab", "drawing-state"] as const)("refuses %s with another same-directory session's tab ID", async kind => {
  const tab = useExplorer.getState().open("drawing")!;
  await expect(performIntegrationCommand({ sessionId: sessionB, projectId, requestId: "cross-session", kind, tabId: tab.id })).rejects.toThrow(/closed|workspace/);
  expect(useExplorer.getState().tabs).toEqual([tab]);
});
it("cancelled background loading never creates a tab", async () => {
  let resolve!: (tabs: PersistedExplorerTab[]) => void;
  vi.mocked(window.textToCad.explorer.loadTabs).mockImplementationOnce(() => new Promise(done => { resolve = done; }));
  const controller = new AbortController();
  const result = open(sessionB, controller.signal);
  await vi.waitFor(() => expect(resolve).toBeDefined());
  controller.abort(new Error("cancelled")); resolve([]);
  await expect(result).rejects.toThrow("cancelled");
  expect((await readSessionStrip(sessionB)).tabs).toEqual([]);
  expect(useExplorer.getState().sessionId).toBe(sessionA);
});
it("background agent work does not disappear when the user selects another session during loading", async () => {
  const opened = await open(sessionB) as { tabId: string };
  await useExplorer.getState().bindSession(sessionB, projectId);
  expect(useExplorer.getState().tabs).toMatchObject([{ id: opened.tabId }]);
});

it('deduplicates filesystem receipts for inactive sessions even while a different directory is selected', async () => {
  useExplorer.getState().open('file', { path: 'old/file.txt' });
  await useExplorer.getState().bindSession(sessionB, '/another/directory');
  const mutation = [{ kind: 'moved' as const, previousPath: 'old', path: 'old/new', directory: true, mutationId: `move-${sessionA}` }];
  useExplorer.getState().receiveChanges(projectId, null, mutation);
  useExplorer.getState().receiveChanges(projectId, null, mutation);
  expect((await readSessionStrip(sessionA)).tabs).toMatchObject([{ path: 'old/new/file.txt' }]);
});
it('archive flushes the latest metadata before disposing ephemeral resources', async () => {
  vi.mocked(window.textToCad.explorer.saveTabs).mockClear();
  const file = useExplorer.getState().open('file', { path: 'keep.txt' })!;
  useExplorer.getState().open('drawing');
  useExplorer.getState().discardSessionResources(sessionA, { preserveTabs: true });
  await vi.waitFor(() => expect(window.textToCad.explorer.saveTabs).toHaveBeenCalledWith({ sessionId: sessionA, tabs: [expect.objectContaining({ id: file.id, path: 'keep.txt' })] }));
});
it('a failed restore exposes retry without allowing an empty strip to overwrite saved tabs', async () => {
  vi.mocked(window.textToCad.explorer.loadTabs).mockRejectedValueOnce(new Error('Storage unavailable'));
  await useExplorer.getState().bindSession(sessionB, projectId);
  expect(useExplorer.getState()).toMatchObject({ ready: false, loadError: 'Storage unavailable' });
  expect(useExplorer.getState().open('file')).toBeNull();
  vi.mocked(window.textToCad.explorer.loadTabs).mockResolvedValueOnce([]);
  await useExplorer.getState().bindSession(sessionB, projectId);
  expect(useExplorer.getState()).toMatchObject({ ready: true, loadError: null });
});

it('archiving and restoring preserves an unsaved document while deletion discards it', async () => {
  const tab = useExplorer.getState().open('file', { path: 'draft.txt' })!;
  const host = desktopLiveDocuments(tab.id, { projectId, root: null });
  host.documents!.drafts.put('same-root', 'draft.txt', { base: { content: 'disk' }, value: 'unsaved work', stale: false });
  useExplorer.getState().discardSessionResources(sessionA, { preserveTabs: true });
  expect(host.documents!.drafts.get('same-root', 'draft.txt')?.value).toBe('unsaved work');
  vi.mocked(window.textToCad.explorer.loadTabs).mockResolvedValueOnce([tab as PersistedExplorerTab]);
  await useExplorer.getState().bindSession(sessionA, projectId);
  const restored = desktopLiveDocuments(tab.id, { projectId, root: null });
  expect(restored.documents!.drafts.get('same-root', 'draft.txt')?.value).toBe('unsaved work');
  useExplorer.getState().discardSessionResources(sessionA);
  expect(restored.documents!.drafts.get('same-root', 'draft.txt')).toBeUndefined();
});

it('preserves a background command admitted while watcher startup is still pending', async () => {
  let watched!: () => void;
  vi.mocked(window.textToCad.explorer.watch).mockImplementationOnce(() => new Promise(resolve => { watched = resolve; }));
  const binding = useExplorer.getState().bindSession(sessionB, projectId);
  const opened = await open(sessionB) as { tabId: string };
  watched(); await binding;
  expect(useExplorer.getState().tabs).toMatchObject([{ id: opened.tabId }]);
});

it("lists a terminal the person opened under the recorded spelling when main names the real path", async () => {
  // `/tmp/p` is `/private/tmp/p` on macOS; a tab keeps the first, main resolves the second.
  const terminal = useExplorer.getState().open("terminal")!;
  useExplorer.getState().update(terminal.id, { cwd: `${projectId}/sub` });
  const listed = await performIntegrationCommand({ sessionId: sessionA, projectId, requestId: "list", kind: "list-tabs", root: null,
    rootDirectory: `/private${projectId}`, rootAliases: [projectId] }) as { tabs: Array<{ id: string }> };
  expect(listed.tabs.map(tab => tab.id)).toEqual([terminal.id]);
});

it("marks a terminal tab the agent opens as the agent's, so its respawn keeps the runtime PATH", async () => {
  const opened = await performIntegrationCommand({ sessionId: sessionA, projectId, requestId: "terminal", kind: "terminal-open", root: null,
    rootDirectory: projectId, params: { cwd: projectId, ptyId: "pty-agent" } }) as { tabId: string };
  expect(useExplorer.getState().tabs.find(tab => tab.id === opened.tabId)).toMatchObject({ kind: "terminal", agent: true });
  expect(useExplorer.getState().open("terminal")).toMatchObject({ agent: false });
});
