/**
 * `openCadRoots` is what the viewer manager's bound may never evict: a root
 * with a CAD tab open. "CAD tab" is every file the viewer client renders, not
 * only STEP and GLB — an open STL, DXF or URDF is served by the same viewer.
 */
import { expect, test, vi } from "vitest";

const tabs = vi.hoisted(() => ({ list: vi.fn() }));

vi.mock("electron", () => ({ app: { getPath: () => "/user-data" } }));
vi.mock("@main/app-paths", () => ({ appVersion: () => "0.0.0", appRoot: () => "/app", resourcesDir: () => "/resources" }));
vi.mock("@main/db/repositories", () => ({
  explorerTabs: { list: tabs.list },
  projects: { get: () => ({ path: "/project" }) },
  sessions: { list: () => [{ id: "s1", archived: false }] },
  settings: { get: () => ({ cadPythonOverride: null }) },
}));
vi.mock("@main/projects/git", () => ({ samePath: () => false }));
import { openCadRoots } from "@main/cad";

test.each(["a.stl", "a.dxf", "robot.urdf", "a.3mf"])("an open %s tab keeps its root out of the eviction candidates", (name) => {
  tabs.list.mockReturnValue([{ kind: "file", path: name, root: "/worktree", projectId: "p" }]);
  expect(openCadRoots()).toEqual(["/worktree"]);
});

test("a prose tab does not", () => {
  tabs.list.mockReturnValue([{ kind: "file", path: "notes.md", root: "/worktree", projectId: "p" }]);
  expect(openCadRoots()).toEqual([]);
});
