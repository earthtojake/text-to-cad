import { toast } from "sonner";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { PromptContext, PromptPart } from "@hardcore/core/prompt";

import { createDesktopPromptContext } from "@renderer/features/explorer/host/promptContext";
import { newSessionKey, useComposer } from "@renderer/state/composer";
import { useProjects } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";
import type { Project, Session } from "@shared/types";

vi.mock("sonner", () => ({ toast: { error: vi.fn(), dismiss: vi.fn() } }));
const workspaceId = JSON.stringify(["desktop", "car", null]);
const png = () => new Blob([new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10])], { type: "image/png" });
const reference: PromptPart = { id: "part", kind: "reference", reference: { resource: { kind: "workspace-file", workspaceId, path: "models/car.step", revision: "v7" }, target: { kind: "cad-selector", selectors: ["o1.f2"] }, label: "body" } };
const context = (operationId: string, parts: readonly PromptPart[] = [reference]): PromptContext => ({ schemaVersion: 1, operationId, parts });
const session = (id: string, cwd = "/car") => ({ id, projectId: "car", cwd } as Session);
const originalArrayBuffer = Object.getOwnPropertyDescriptor(Blob.prototype, "arrayBuffer");

beforeEach(() => {
  vi.clearAllMocks();
  // jsdom implements FileReader but not Blob.arrayBuffer; keep real browser Blob/File ownership.
  if (!Blob.prototype.arrayBuffer) Object.defineProperty(Blob.prototype, "arrayBuffer", { configurable: true, value: function(this: Blob) {
    return new Promise<ArrayBuffer>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as ArrayBuffer);
      reader.onerror = () => reject(reader.error);
      reader.readAsArrayBuffer(this);
    });
  } });
  useProjects.setState({ activeId: "car", projects: [{ id: "car", path: "/car" }, { id: "other", path: "/other" }] as Project[] });
  useSessions.setState({ activeId: null, sessions: [] });
  useComposer.setState({ drafts: {}, pendingFiles: {}, draftRoots: {}, acceptedContexts: {}, focusRequest: null, referenceLabels: {}, queues: {} });
});
afterEach(() => {
  for (const call of vi.mocked(toast.error).mock.calls) (call[1]?.onDismiss as unknown as (() => void) | undefined)?.();
  if (originalArrayBuffer) Object.defineProperty(Blob.prototype, "arrayBuffer", originalArrayBuffer); else Reflect.deleteProperty(Blob.prototype, "arrayBuffer");
  vi.restoreAllMocks();
});

it("allows a failed operation to retry with valid attachment bytes", async () => {
  const port = createDesktopPromptContext("car", null, workspaceId);
  expect((await port.deliver(context("retry", [{ id: "image", kind: "attachment", name: "view.png", mimeType: "image/png", content: Promise.reject(new Error("Encoder failed")) }]))).status).toBe("failed");
  expect((await port.deliver(context("retry", [{ id: "image", kind: "attachment", name: "view.png", mimeType: "image/png", content: png() }]))).status).toBe("added");
  expect(useComposer.getState().pendingFiles[newSessionKey("car")]).toHaveLength(1);
});

it.each(["constructor", "toString", "__proto__"])("accepts and deduplicates the own receipt for operation %s", async operationId => {
  const bundle = context(operationId, [
    { id: "text", kind: "text", text: "Inspect this view" },
    { id: "image", kind: "attachment", name: "view.png", mimeType: "image/png", content: png() },
  ]);
  const receipt = { status: "added", partIds: ["text", "image"] };
  expect(await createDesktopPromptContext("car", null, workspaceId).deliver(bundle)).toEqual(receipt);
  // A second port must consult the shared receipt without duplicating either part.
  expect(await createDesktopPromptContext("car", null, workspaceId).deliver(bundle)).toEqual(receipt);
  const state = useComposer.getState();
  expect(state.drafts[newSessionKey("car")]).toBe("Inspect this view");
  expect(state.pendingFiles[newSessionKey("car")]).toHaveLength(1);
  expect(Object.keys(state.acceptedContexts)).toEqual([operationId]);
  expect(Object.getPrototypeOf(state.acceptedContexts)).toBe(Object.prototype);
  expect(JSON.parse(JSON.stringify(state.acceptedContexts))).toEqual(state.acceptedContexts);
});

it("caps deferred offers and invalidates an evicted action without starting a chat", async () => {
  useSessions.setState({ activeId: "old", sessions: [session("old")] });
  const start = vi.spyOn(useSessions.getState(), "start");
  vi.mocked(toast.error).mockReturnValue(1);
  const port = createDesktopPromptContext("car", "/car-worktree", workspaceId);
  for (let i = 0; i < 9; i++) await port.deliver(context(`offer-${i}`));
  expect(toast.dismiss).toHaveBeenCalledWith(1);
  const action = vi.mocked(toast.error).mock.calls[0]?.[1]?.action as unknown as { onClick(): void };
  action.onClick();
  expect(start).not.toHaveBeenCalled();
});

it("binds the destination before PNG resolution, preserves order and never focuses a different chat", async () => {
  useSessions.setState({ activeId: "first", sessions: [session("first"), session("second")] });
  useComposer.getState().setDraft("first", "Keep my draft");
  let resolve!: (blob: globalThis.Blob) => void;
  const image = new Promise<globalThis.Blob>(done => { resolve = done; });
  const port = createDesktopPromptContext("car", null, workspaceId);
  const bundle = context("capture", [{ id: "intro", kind: "text", text: "Inspect" }, reference, { id: "image", kind: "attachment", name: "view.png", mimeType: "image/png", content: image, about: ["part"] }, { id: "outro", kind: "text", text: "Keep the holes" }]);
  const delivered = port.deliver(bundle);
  expect(port.deliver(bundle)).toBe(delivered);
  useSessions.setState({ activeId: "second" });
  resolve(png() as unknown as globalThis.Blob);
  expect(await delivered).toEqual({ status: "added", partIds: ["intro", "part", "image", "outro"] });
  expect(useComposer.getState().drafts.first).toBe("Keep my draft\n\nInspect models/car.step#o1.f2 \n\nKeep the holes");
  expect(useComposer.getState().drafts.second).toBeUndefined();
  expect(useComposer.getState().pendingFiles.first?.[0]?.name).toBe("view.png");
  expect(useComposer.getState().acceptedContexts.capture?.parts[1]?.reference?.resource.revision).toBe("v7");
  expect(useComposer.getState().acceptedContexts.capture?.parts[2]?.about).toEqual(["part"]);
  expect(useComposer.getState().focusRequest).toBeNull();
  expect(useComposer.getState().queues).toEqual({});
  await port.deliver(bundle);
  expect(useComposer.getState().pendingFiles.first).toHaveLength(1);
});

it("rejects an invalid attachment without accepting text or reference parts", async () => {
  const port = createDesktopPromptContext("car", null, workspaceId);
  const result = await port.deliver(context("binary", [reference, { id: "binary", kind: "attachment", name: "archive.zip", mimeType: "application/zip", content: new Blob([new Uint8Array([1, 0, 2])], { type: "application/zip" }) as unknown as globalThis.Blob }]));
  expect(result.status).toBe("failed");
  expect(useComposer.getState().drafts).toEqual({});
  expect(useComposer.getState().draftRoots).toEqual({});
  expect(useComposer.getState().pendingFiles).toEqual({});
});

it("cancels when the bound chat disappears during capture", async () => {
  useSessions.setState({ activeId: "first", sessions: [session("first")] });
  let resolve!: (blob: globalThis.Blob) => void;
  const image = new Promise<globalThis.Blob>(done => { resolve = done; });
  const port = createDesktopPromptContext("car", null, workspaceId);
  const delivered = port.deliver(context("deleted", [{ id: "image", kind: "attachment", name: "view.png", mimeType: "image/png", content: image }]));
  useSessions.setState({ activeId: null, sessions: [] });
  resolve(png() as unknown as globalThis.Blob);
  expect((await delivered).status).toBe("cancelled");
  expect(useComposer.getState().drafts).toEqual({});
});

it("uses a project-specific new draft and readable URL/text-range references", async () => {
  const port = createDesktopPromptContext("car", null, workspaceId);
  const key = newSessionKey("car");
  useComposer.getState().setDraft(key, "Existing prose");
  expect((await port.deliver(context("readable", [
    { id: "url", kind: "reference", reference: { resource: { kind: "url", url: "https://example.com/spec" }, target: { kind: "whole-resource" } } },
    { id: "range", kind: "reference", reference: { resource: { kind: "workspace-file", workspaceId, path: "source.py" }, target: { kind: "text-range", start: { line: 1, character: 2 }, end: { line: 3, character: 0 } } } },
  ]))).status).toBe("added");
  expect(useComposer.getState().drafts[key]).toBe("Existing prose https://example.com/spec source.py:2:3-4:1 ");
  expect(useComposer.getState().draftRoots[key]).toBe("/car");
  expect(useComposer.getState().drafts.__new__).toBeUndefined();
});

it("rejects a foreign workspace reference", async () => {
  const port = createDesktopPromptContext("car", null, workspaceId);
  const foreign = structuredClone(reference) as Extract<PromptPart, { kind: "reference" }>;
  foreign.reference.resource = { kind: "workspace-file", workspaceId: "other", path: "car.step" };
  expect((await port.deliver(context("foreign", [foreign]))).status).toBe("failed");
  expect(useComposer.getState().drafts).toEqual({});
});

it.each(["mismatch", "constructor", "toString", "__proto__"])("defers operation %s to an explicit workspace action and revalidates that action", async operationId => {
  useSessions.setState({ activeId: "old", sessions: [session("old")] });
  useComposer.getState().setDraft("old", "Unfinished");
  const start = vi.spyOn(useSessions.getState(), "start").mockImplementation(async () => {
    const created = session("new", "/car-worktree");
    useSessions.setState({ sessions: [...useSessions.getState().sessions, created] });
    return created;
  });
  const port = createDesktopPromptContext("car", "/car-worktree", workspaceId);
  const bundle = context(operationId);
  expect((await port.deliver(bundle)).status).toBe("deferred");
  expect(start).not.toHaveBeenCalled();
  const action = vi.mocked(toast.error).mock.calls.at(-1)?.[1]?.action as unknown as { onClick(): void };
  action.onClick(); action.onClick();
  await vi.waitFor(() => expect(useComposer.getState().drafts.new).toBe("models/car.step#o1.f2 "));
  expect(start).toHaveBeenCalledExactlyOnceWith({ projectId: "car", cwd: "/car-worktree" }, { select: false });
  expect(useComposer.getState().drafts.old).toBe("Unfinished");
  expect((await port.deliver(bundle)).status).toBe("added");
});

it("keeps an explicitly requested workspace chat bound while PNG capture outlives navigation", async () => {
  useSessions.setState({ activeId: "old", sessions: [session("old")] });
  let resolve!: (blob: Blob) => void;
  const image = new Promise<Blob>(done => { resolve = done; });
  const start = vi.spyOn(useSessions.getState(), "start").mockImplementation(async () => {
    const created = session("new", "/car-worktree");
    useSessions.setState({ sessions: [...useSessions.getState().sessions, created] });
    return created;
  });
  const port = createDesktopPromptContext("car", "/car-worktree", workspaceId);
  expect((await port.deliver(context("navigate", [reference, { id: "image", kind: "attachment", name: "view.png", mimeType: "image/png", content: image }]))).status).toBe("deferred");
  const action = vi.mocked(toast.error).mock.calls.at(-1)?.[1]?.action as unknown as { onClick(): void };
  action.onClick();
  useProjects.setState({ activeId: "other" });
  useSessions.setState({ activeId: null });
  resolve(png());
  await vi.waitFor(() => expect(useComposer.getState().pendingFiles.new).toHaveLength(1));
  expect(start).toHaveBeenCalledExactlyOnceWith({ projectId: "car", cwd: "/car-worktree" }, { select: false });
  expect(useComposer.getState().drafts.new).toBe("models/car.step#o1.f2 ");
  expect(useProjects.getState().activeId).toBe("other");
  expect(useSessions.getState().activeId).toBeNull();
  expect(useComposer.getState().focusRequest).toBeNull();
  expect(useComposer.getState().queues).toEqual({});
});

it("rejects a deferred workspace action after its project disappears", async () => {
  useSessions.setState({ activeId: "old", sessions: [session("old")] });
  const start = vi.spyOn(useSessions.getState(), "start");
  const port = createDesktopPromptContext("car", "/car-worktree", workspaceId);
  expect((await port.deliver(context("removed-project"))).status).toBe("deferred");
  const action = vi.mocked(toast.error).mock.calls.at(-1)?.[1]?.action as unknown as { onClick(): void };
  useProjects.setState({ activeId: "other", projects: useProjects.getState().projects.filter(project => project.id !== "car") });
  action.onClick();
  expect(start).not.toHaveBeenCalled();
  expect(useComposer.getState().acceptedContexts).toEqual({});
  expect(useComposer.getState().drafts).toEqual({});
});
