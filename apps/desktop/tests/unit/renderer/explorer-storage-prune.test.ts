import { beforeEach, expect, it, vi } from "vitest";

/**
 * What a session leaves in localStorage — its file tabs' records and its
 * pane's collapsed/width — goes with the session, even in a later run that
 * never loaded its strip. A module reload is that later run: nothing of the
 * first one is in memory, only what it left in storage.
 */

vi.mock("@renderer/state/drawings", () => ({ deleteDrawingScene: vi.fn() }));

const TABS = "text-to-cad.tabs.v1";
const stored = (key: string) => JSON.parse(localStorage.getItem(key) ?? "{}") as Record<string, unknown>;

async function firstRun(sessionId: string, tabId: string) {
  vi.resetModules();
  const { useExplorer } = await import("@renderer/state/explorer");
  vi.mocked(window.textToCad.explorer.loadTabs).mockResolvedValueOnce([
    { id: tabId, kind: "file", sessionId, projectId: "project", order: 0, path: "a.txt", root: null, panel: null },
  ] as never);
  await useExplorer.getState().bindSession(sessionId, "project");
  // The tab's viewer wrote its record; the person sized the pane.
  localStorage.setItem(TABS, JSON.stringify({ ...stored(TABS), [tabId]: { version: 1 } }));
  useExplorer.getState().setCollapsed(false);
  useExplorer.getState().setWidth(420);
  await useExplorer.getState().bindSession(null, null);
}

beforeEach(() => {
  localStorage.clear();
  vi.mocked(window.textToCad.explorer.saveTabs).mockReset().mockResolvedValue(undefined);
});

it("a session deleted in a run that never loaded it takes its tab records and pane preferences", async () => {
  await firstRun("gone", "tab-gone");
  await firstRun("kept", "tab-kept");
  expect(Object.keys(stored(TABS)).sort()).toEqual(["tab-gone", "tab-kept"]);

  vi.resetModules();
  const { useExplorer } = await import("@renderer/state/explorer");
  useExplorer.getState().discardSessionResources("gone");

  expect(Object.keys(stored(TABS))).toEqual(["tab-kept"]);
  expect(Object.keys(stored("text-to-cad.explorer.session.collapsed"))).toEqual(["kept"]);
  expect(Object.keys(stored("text-to-cad.explorer.session.width"))).toEqual(["kept"]);
});

it("a session list without a session prunes what that session left", async () => {
  await firstRun("gone", "tab-gone");
  await firstRun("archived", "tab-archived");

  vi.resetModules();
  const { useSessions } = await import("@renderer/state/sessions");
  // Deleted while the app was closed: the list simply lacks it. Archived sessions are listed.
  useSessions.getState().receive([{ id: "archived", archived: true, projectId: "/tmp/project", cwd: "/tmp/project", title: "", createdAt: 0, updatedAt: 0 } as never]);

  expect(Object.keys(stored(TABS))).toEqual(["tab-archived"]);
  expect(Object.keys(stored("text-to-cad.explorer.session.width"))).toEqual(["archived"]);
});

it("a session made before the list has loaded prunes nothing: the others are not missing, only not here yet", async () => {
  await firstRun("kept", "tab-kept");

  vi.resetModules();
  const { useSessions } = await import("@renderer/state/sessions");
  const { useAcp } = await import("@renderer/state/acp");
  expect(useSessions.getState().ready).toBe(false);
  Object.assign(window.textToCad.sessions, { create: vi.fn(async () => (
    { id: "fresh", archived: false, projectId: "project", cwd: "/tmp/project", title: "", createdAt: 0, updatedAt: 0 }
  )) });
  await useAcp.getState().create({ projectId: "project", agentId: "claude" } as never);

  expect(Object.keys(stored(TABS))).toEqual(["tab-kept"]);
  expect(Object.keys(stored("text-to-cad.explorer.session.width"))).toEqual(["kept"]);
  expect(useSessions.getState().sessions.map((session) => session.id)).toEqual(["fresh"]);
  // Still not the list: whatever waits for it keeps waiting.
  expect(useSessions.getState().ready).toBe(false);
});
