import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { PromptContext, PromptPart } from "@hardcore/core/prompt";

import { createDesktopPromptContext } from "@renderer/features/explorer/host/promptContext";
import { useComposer } from "@renderer/state/composer";
import { useProjects } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";
import type { Project, Session } from "@shared/types";

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
  useSessions.setState({ activeId: "first", sessions: [session("first"), session("second")] });
  useComposer.setState({ drafts: {}, pendingFiles: {}, draftRoots: {}, acceptedContexts: {}, focusRequest: null, referenceLabels: {}, queues: {} });
});
afterEach(() => {
  if (originalArrayBuffer) Object.defineProperty(Blob.prototype, "arrayBuffer", originalArrayBuffer); else Reflect.deleteProperty(Blob.prototype, "arrayBuffer");
  vi.restoreAllMocks();
});

it("allows a failed operation to retry with valid attachment bytes", async () => {
  const port = createDesktopPromptContext("car", null, workspaceId, "first");
  expect((await port.deliver(context("retry", [{ id: "image", kind: "attachment", name: "view.png", mimeType: "image/png", content: Promise.reject(new Error("Encoder failed")) }]))).status).toBe("failed");
  expect((await port.deliver(context("retry", [{ id: "image", kind: "attachment", name: "view.png", mimeType: "image/png", content: png() }]))).status).toBe("added");
  expect(useComposer.getState().pendingFiles["first"]).toHaveLength(1);
});

it.each(["constructor", "toString", "__proto__"])("accepts and deduplicates the own receipt for operation %s", async operationId => {
  const bundle = context(operationId, [
    { id: "text", kind: "text", text: "Inspect this view" },
    { id: "image", kind: "attachment", name: "view.png", mimeType: "image/png", content: png() },
  ]);
  const receipt = { status: "added", partIds: ["text", "image"] };
  expect(await createDesktopPromptContext("car", null, workspaceId, "first").deliver(bundle)).toEqual(receipt);
  // A second port must consult the shared receipt without duplicating either part.
  expect(await createDesktopPromptContext("car", null, workspaceId, "first").deliver(bundle)).toEqual(receipt);
  const state = useComposer.getState();
  expect(state.drafts["first"]).toBe("Inspect this view");
  expect(state.pendingFiles["first"]).toHaveLength(1);
  expect(Object.keys(state.acceptedContexts)).toEqual([operationId]);
  expect(Object.getPrototypeOf(state.acceptedContexts)).toBe(Object.prototype);
  expect(JSON.parse(JSON.stringify(state.acceptedContexts))).toEqual(state.acceptedContexts);
});

it("binds the destination before PNG resolution, preserves order and never focuses a different chat", async () => {
  useSessions.setState({ activeId: "first", sessions: [session("first"), session("second")] });
  useComposer.getState().setDraft("first", "Keep my draft");
  let resolve!: (blob: globalThis.Blob) => void;
  const image = new Promise<globalThis.Blob>(done => { resolve = done; });
  const port = createDesktopPromptContext("car", null, workspaceId, "first");
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

it("a snapshot's whole-file subject adds no token to a draft that already names that file, and does to one that does not", async () => {
  const port = createDesktopPromptContext("car", null, workspaceId, "first");
  const snapshot = (operationId: string, path = "models/car.step") => context(operationId, [
    { id: "source", kind: "reference", reference: { resource: { kind: "workspace-file", workspaceId, path }, target: { kind: "whole-resource" } } },
    { id: "image", kind: "attachment", name: "car-view.png", mimeType: "image/png", content: png(), about: ["source"] },
  ]);
  // The person added a face of the file; the snapshot's subject is that same file.
  expect((await port.deliver(context("face"))).status).toBe("added");
  expect(await port.deliver(snapshot("shot"))).toEqual({ status: "added", partIds: ["source", "image"] });
  expect(useComposer.getState().drafts.first).toBe("models/car.step#o1.f2 ");
  expect(useComposer.getState().pendingFiles.first?.map(file => file.name)).toEqual(["car-view.png"]);
  // A snapshot of another file still names it, and a whole-file reference chosen on its own
  // (no image about it) is always the person's to add.
  await port.deliver(snapshot("other", "models/wheel.step"));
  expect(useComposer.getState().drafts.first).toBe("models/car.step#o1.f2 models/wheel.step ");
  await port.deliver(context("file", [{ id: "file", kind: "reference", reference: { resource: { kind: "workspace-file", workspaceId, path: "models/car.step" }, target: { kind: "whole-resource" } } }]));
  expect(useComposer.getState().drafts.first).toBe("models/car.step#o1.f2 models/wheel.step models/car.step ");
});

it("rejects an invalid attachment without accepting text or reference parts", async () => {
  const port = createDesktopPromptContext("car", null, workspaceId, "first");
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
  const port = createDesktopPromptContext("car", null, workspaceId, "first");
  const delivered = port.deliver(context("deleted", [{ id: "image", kind: "attachment", name: "view.png", mimeType: "image/png", content: image }]));
  useSessions.setState({ activeId: null, sessions: [] });
  resolve(png() as unknown as globalThis.Blob);
  expect((await delivered).status).toBe("cancelled");
  expect(useComposer.getState().drafts).toEqual({});
});

it("uses the owner session draft and readable URL/text-range references", async () => {
  const port = createDesktopPromptContext("car", null, workspaceId, "first");
  const key = "first";
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
  const port = createDesktopPromptContext("car", null, workspaceId, "first");
  const foreign = structuredClone(reference) as Extract<PromptPart, { kind: "reference" }>;
  foreign.reference.resource = { kind: "workspace-file", workspaceId: "other", path: "car.step" };
  expect((await port.deliver(context("foreign", [foreign]))).status).toBe("failed");
  expect(useComposer.getState().drafts).toEqual({});
});

it("binds the owner before deliver is called, even when a renderer callback outlives a session switch", async () => {
  const port = createDesktopPromptContext("car", null, workspaceId, "first");
  useSessions.setState({ activeId: "second" });
  expect((await port.deliver(context("late-callback"))).status).toBe("added");
  expect(useComposer.getState().drafts.first).toBe("models/car.step#o1.f2 ");
  expect(useComposer.getState().drafts.second).toBeUndefined();
  expect(useComposer.getState().focusRequest).toBeNull();
});

it("cancels capture if the owner is archived without changing another session's draft", async () => {
  let resolve!: (blob: Blob) => void;
  const image = new Promise<Blob>(done => { resolve = done; });
  const port = createDesktopPromptContext("car", null, workspaceId, "first");
  const delivered = port.deliver(context("archived", [{ id: "image", kind: "attachment", name: "view.png", mimeType: "image/png", content: image }]));
  useSessions.setState({ activeId: "second", sessions: [{ ...session("first"), archived: true }, session("second")] });
  resolve(png());
  expect((await delivered).status).toBe("cancelled");
  expect(useComposer.getState().drafts).toEqual({});
  expect(useComposer.getState().pendingFiles).toEqual({});
});

it("rejects a workspace mismatch instead of directing context into another session", async () => {
  const port = createDesktopPromptContext("car", "/car-worktree", workspaceId, "first");
  expect((await port.deliver(context("mismatch"))).status).toBe("failed");
  expect(useComposer.getState().drafts).toEqual({});
});

it("does not reuse another session's delivery receipt", async () => {
  const bundle = context("reused-operation");
  await createDesktopPromptContext("car", null, workspaceId, "first").deliver(bundle);
  expect((await createDesktopPromptContext("car", null, workspaceId, "second").deliver(bundle)).status).toBe("failed");
  expect(useComposer.getState().drafts.second).toBeUndefined();
});

it("does not reuse a receipt produced by another session while encoding was pending", async () => {
  const bundle = context("concurrent-operation", [{ id: "image", kind: "attachment", name: "view.png", mimeType: "image/png", content: png() }]);
  const results = await Promise.all([
    createDesktopPromptContext("car", null, workspaceId, "first").deliver(bundle),
    createDesktopPromptContext("car", null, workspaceId, "second").deliver(bundle),
  ]);
  expect(results.map(result => result.status).sort()).toEqual(["added", "failed"]);
  expect(Object.values(useComposer.getState().pendingFiles).flat()).toHaveLength(1);
});
