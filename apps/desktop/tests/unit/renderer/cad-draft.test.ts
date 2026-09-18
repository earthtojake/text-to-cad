import { beforeEach, expect, it } from "vitest";
import { bindDraftDestination, draftDestinationIsCurrent, validateDraftDestination } from "@renderer/state/cad-draft";
import { useComposer } from "@renderer/state/composer";
import { useProjects } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";
import type { Project, Session } from "@shared/types";

beforeEach(() => {
  useProjects.setState({ activeId: "car", projects: [{ id: "car", path: "/car" }, { id: "other", path: "/other" }] as Project[] });
  useSessions.setState({ activeId: "first", sessions: [{ id: "first", projectId: "car", cwd: "/car" }] as Session[] });
  useComposer.setState({ drafts: {}, pendingFiles: {}, draftRoots: {}, acceptedContexts: {}, focusRequest: null, referenceLabels: {} });
});

it("binds a destination without changing a draft and does not follow a later chat switch", () => {
  useSessions.setState({ activeId: "first", sessions: [{ id: "first", projectId: "car", cwd: "/car" }, { id: "second", projectId: "car", cwd: "/car" }] as Session[] });
  const target = bindDraftDestination("car", null, "first");
  useSessions.setState({ activeId: "second" });
  validateDraftDestination(target);
  expect(target.key).toBe("first");
  expect(draftDestinationIsCurrent(target)).toBe(false);
  expect(useComposer.getState().draftRoots).toEqual({});
  useSessions.setState({ sessions: [{ id: "second", projectId: "car", cwd: "/car" }] as Session[] });
  expect(() => validateDraftDestination(target)).toThrow("deleted");
});

it("accepts ordered context atomically, preserves prose and attachments, and retries once", () => {
  const target = bindDraftDestination("car", null, "first");
  const existing = new File(["old"], "old.txt", { type: "text/plain" });
  const capture = new File(["png"], "view.png", { type: "image/png" });
  useComposer.getState().setDraft(target.key, "My draft");
  useComposer.getState().attachFile(target.key, existing);
  const accept = () => useComposer.getState().acceptContext(target.key, "capture-operation", [
    { id: "intro", kind: "text", text: "Inspect this" },
    { id: "ref", kind: "reference", text: "models/car.step#o1", label: "body" },
    { id: "image", kind: "attachment", file: capture },
    { id: "outro", kind: "text", text: "Keep the mounting holes" },
  ], { root: target.workspace, focus: false });
  const updates: string[] = [];
  const unsubscribe = useComposer.subscribe(() => updates.push("accepted"));
  const receipt = accept();
  expect(accept()).toBe(receipt);
  unsubscribe();
  expect(updates).toEqual(["accepted"]);
  expect(receipt.partIds).toEqual(["intro", "ref", "image", "outro"]);
  expect(useComposer.getState().drafts[target.key]).toBe("My draft\n\nInspect this models/car.step#o1 \n\nKeep the mounting holes");
  expect(useComposer.getState().pendingFiles[target.key]).toEqual([existing, capture]);
  expect(useComposer.getState().focusRequest).toBeNull();
  expect(useComposer.getState().queues).toEqual({});
});

it("revalidates an archived owner before acceptance", () => {
  const target = bindDraftDestination("car", null, "first");
  useSessions.setState({ sessions: [{ id: "first", projectId: "car", cwd: "/car", archived: true }] as Session[] });
  expect(() => validateDraftDestination(target)).toThrow("archived");
});
