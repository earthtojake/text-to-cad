import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { createCadClient } from "@hardcore/core/client";
import type * as CadClientModule from "@hardcore/core/client";
import type { CadClient } from "@hardcore/core/client";
import type { PrepareContext } from "@hardcore/ui/file-viewer";
import { createDesktopCadConnectionRegistry, createDesktopCadConnections } from "@renderer/features/explorer/adapters/cadRuntime";
import { closeSessionTab, useExplorer } from "@renderer/state/explorer";
import { createDesktopRenderers } from "@renderer/features/explorer/renderers";
import type { ViewerOrigin } from "@shared/ipc/cad";

vi.mock("@hardcore/core/client", async (importOriginal) => ({
  ...await importOriginal<typeof CadClientModule>(),
  createCadClient: vi.fn(),
}));

// Exercise the real registration/prepare/dispose path without transforming
// Three.js and the viewport in this connection-ownership unit test. Actual CAD
// rendering and tab reopens are covered by the Electron integration suite.
vi.mock("../../../../../packages/ui/dist/renderers/cad/CadRenderer.js", () => ({ default: () => null }));

function context(path = "part.stl", root = "project", signal = new AbortController().signal): PrepareContext {
  const file = { path, name: path, kind: "file" as const, extension: "stl", mediaType: "cad", size: 12 };
  return { file, source: { id: root, rootName: root, stat: async () => file }, signal };
}

function client() {
  return {
    resolveEntry: vi.fn(async (file: string) => ({ file, kind: "stl", hash: "r1", url: "/mesh.stl" })),
    serverInfo: vi.fn(async () => ({})),
    createRenderSession: vi.fn(() => ({ dispose: vi.fn() })),
    dispose: vi.fn(),
  };
}

beforeEach(() => {
  vi.mocked(createCadClient).mockReset();
  vi.mocked(window.hardcore.cad.viewerOrigin).mockReset().mockResolvedValue({ origin: "http://127.0.0.1:3010" });
});

afterEach(() => {
  for (const id of ["cad-owner-a", "cad-owner-b", "cad-owner-other"]) useExplorer.getState().discardSessionResources(id);
});

it("retains the root client through an empty session, a different project and a collapsed pane", async () => {
  const runtime = client();
  vi.mocked(createCadClient).mockReturnValue(runtime as unknown as CadClient);
  const registry = createDesktopCadConnectionRegistry();
  try {
    await useExplorer.getState().bindSession("cad-owner-a", "project");
    const first = useExplorer.getState().openFile("part.stl")!;
    if (first.kind !== "file") throw new Error("Expected a file tab");
    const borrowed = registry.forTab(first);
    expect(await borrowed.acquire(context())).toBe(runtime);

    await useExplorer.getState().bindSession("cad-owner-b", "project");
    expect(useExplorer.getState().tabs).toHaveLength(0);
    await useExplorer.getState().bindSession("cad-owner-other", "another-project");
    await useExplorer.getState().bindSession(null, null);
    expect(runtime.dispose).not.toHaveBeenCalled();

    await useExplorer.getState().bindSession("cad-owner-a", "project");
    useExplorer.getState().setCollapsed(true);
    expect(registry.forTab(first)).toBe(borrowed);
    expect(await registry.forTab(first).acquire(context())).toBe(runtime);
    expect(createCadClient).toHaveBeenCalledTimes(1);
    expect(runtime.dispose).not.toHaveBeenCalled();

    useExplorer.getState().close(first.id);
    expect(runtime.dispose).toHaveBeenCalledTimes(1);
    expect(() => borrowed.acquire(context())).toThrow(/closed/);
  } finally { registry.dispose(); }
  expect(runtime.dispose).toHaveBeenCalledTimes(1);
});

it("shares a root across sessions and releases it only after the final background owner is discarded", async () => {
  const runtime = client();
  vi.mocked(createCadClient).mockReturnValue(runtime as unknown as CadClient);
  const registry = createDesktopCadConnectionRegistry();
  try {
    await useExplorer.getState().bindSession("cad-owner-a", "project");
    const first = useExplorer.getState().openFile("a.stl")!;
    if (first.kind !== "file") throw new Error("Expected a file tab");
    expect(await registry.forTab(first).acquire(context("a.stl"))).toBe(runtime);
    await useExplorer.getState().bindSession("cad-owner-b", "project");
    const second = useExplorer.getState().openFile("b.stl")!;
    if (second.kind !== "file") throw new Error("Expected a file tab");
    expect(await registry.forTab(second).acquire(context("b.stl"))).toBe(runtime);
    expect(createCadClient).toHaveBeenCalledTimes(1);
    await closeSessionTab("cad-owner-a", first.id);
    expect(runtime.dispose).not.toHaveBeenCalled();

    await useExplorer.getState().bindSession("cad-owner-other", "another-project");
    useExplorer.getState().discardSessionResources("cad-owner-b");
    expect(runtime.dispose).toHaveBeenCalledTimes(1);
  } finally { registry.dispose(); }
  expect(runtime.dispose).toHaveBeenCalledTimes(1);
});

it("reuses a root client when A, B and A mount in turn, then releases the final root owner", async () => {
  const runtime = client();
  vi.mocked(createCadClient).mockReturnValue(runtime as unknown as CadClient);
  const owner = createDesktopCadConnections("project");
  owner.retainRoots([null]);
  try {
    for (const path of ["a.stl", "b.stl", "a.stl"]) {
      const tab = createDesktopRenderers("project", null, path, owner.forRoot(null));
      const cad = tab.renderers.find((renderer) => renderer.id === "cad")!;
      const document = await cad.prepare(context(path));
      document.dispose?.();
      tab.dispose();
      expect(runtime.dispose).not.toHaveBeenCalled();
    }
    expect(window.hardcore.cad.viewerOrigin).toHaveBeenCalledTimes(3);
    expect(createCadClient).toHaveBeenCalledTimes(1);
    expect(runtime.createRenderSession).toHaveBeenCalledTimes(3);
    owner.retainRoots([]);
    expect(runtime.dispose).toHaveBeenCalledTimes(1);
  } finally {
    owner.dispose();
  }
  expect(runtime.dispose).toHaveBeenCalledTimes(1);
});

it("keeps roots isolated and releases only roots whose last file tab closed", async () => {
  const project = client();
  const worktree = client();
  vi.mocked(createCadClient)
    .mockReturnValueOnce(project as unknown as CadClient)
    .mockReturnValueOnce(worktree as unknown as CadClient);
  const owner = createDesktopCadConnections("project");
  try {
    expect(await owner.forRoot(null).acquire(context())).toBe(project);
    expect(await owner.forRoot("/tmp/worktree").acquire(context("part.stl", "worktree"))).toBe(worktree);
    owner.retainRoots(["/tmp/worktree", "/tmp/worktree"]);
    expect(project.dispose).toHaveBeenCalledTimes(1);
    expect(worktree.dispose).not.toHaveBeenCalled();
    expect(await owner.forRoot("/tmp/worktree").acquire(context("other.stl", "worktree"))).toBe(worktree);
    expect(window.hardcore.cad.viewerOrigin).toHaveBeenLastCalledWith({ projectId: "project", root: "/tmp/worktree" });
  } finally {
    owner.dispose();
  }
  expect(project.dispose).toHaveBeenCalledTimes(1);
  expect(worktree.dispose).toHaveBeenCalledTimes(1);
});

it("fences a pending launch after the root closes and can reacquire after effect remount", async () => {
  const stale = client();
  const current = client();
  vi.mocked(createCadClient)
    .mockReturnValueOnce(stale as unknown as CadClient)
    .mockReturnValueOnce(current as unknown as CadClient);
  const owner = createDesktopCadConnections("project");
  const borrower = owner.forRoot(null);
  expect(await borrower.acquire(context())).toBe(stale);
  let finish!: (answer: ViewerOrigin) => void;
  vi.mocked(window.hardcore.cad.viewerOrigin).mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
  const pending = borrower.acquire(context());
  const rejected = expect(pending).rejects.toMatchObject({ name: "AbortError" });
  owner.dispose();
  finish({ origin: "http://127.0.0.1:3010" });
  await rejected;
  expect(stale.dispose).toHaveBeenCalledTimes(1);
  try {
    expect(await borrower.acquire(context())).toBe(current);
  } finally {
    owner.dispose();
  }
  expect(current.dispose).toHaveBeenCalledTimes(1);
});

it("replaces the root client when main restarts its viewer at a different origin", async () => {
  const first = client();
  const restarted = client();
  vi.mocked(createCadClient)
    .mockReturnValueOnce(first as unknown as CadClient)
    .mockReturnValueOnce(restarted as unknown as CadClient);
  const owner = createDesktopCadConnections("project");
  try {
    const borrower = owner.forRoot(null);
    expect(await borrower.acquire(context())).toBe(first);
    vi.mocked(window.hardcore.cad.viewerOrigin).mockResolvedValue({ origin: "http://127.0.0.1:3011" });
    const [a, b] = await Promise.all([borrower.acquire(context("a.stl")), borrower.acquire(context("b.stl"))]);
    expect(a).toBe(restarted);
    expect(b).toBe(restarted);
    expect(window.hardcore.cad.viewerOrigin).toHaveBeenCalledTimes(2);
    expect(createCadClient).toHaveBeenCalledTimes(2);
    expect(createCadClient).toHaveBeenLastCalledWith({ origin: "http://127.0.0.1:3011", workspaceId: "project" });
    expect(first.dispose).toHaveBeenCalledTimes(1);
    expect(restarted.dispose).not.toHaveBeenCalled();
  } finally {
    owner.dispose();
  }
  expect(restarted.dispose).toHaveBeenCalledTimes(1);
});

it("does not acquire a backend for an already cancelled tab", async () => {
  const owner = createDesktopCadConnections("project");
  const controller = new AbortController();
  controller.abort();
  expect(() => owner.forRoot(null).acquire(context("part.stl", "project", controller.signal))).toThrow();
  owner.dispose();
  expect(window.hardcore.cad.viewerOrigin).not.toHaveBeenCalled();
  expect(createCadClient).not.toHaveBeenCalled();
});
