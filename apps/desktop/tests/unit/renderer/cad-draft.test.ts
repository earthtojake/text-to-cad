import { toast } from "sonner";
import { beforeEach, expect, it, vi } from "vitest";
import { addToDraft, cadDraftKey } from "@renderer/state/cad-draft";
import { newSessionKey, useComposer } from "@renderer/state/composer";
import { useProjects } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";
import type { Project, Session } from "@shared/types";

vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));

beforeEach(() => {
  vi.clearAllMocks();
  useProjects.setState({ activeId: "car", projects: [{ id: "car", path: "/car" }, { id: "other", path: "/other" }] as Project[] });
  useSessions.setState({ activeId: null, sessions: [] });
  useComposer.setState({ drafts: {}, pendingFiles: {}, draftRoots: {} });
});

it("keeps a model reference with its project and worktree without replacing prose", () => {
  const key = newSessionKey("car");
  useComposer.getState().setDraft(key, "Round this");
  useComposer.getState().insertReference(cadDraftKey("car", "/car-worktree"), { file: "models/car.step", selector: "o1.1" });
  expect(useComposer.getState().drafts[key]).toBe("Round this models/car.step#o1.1 ");
  expect(useComposer.getState().draftRoots[key]).toBe("/car-worktree");
  useProjects.setState({ activeId: "other" });
  expect(useComposer.getState().drafts[cadDraftKey("other", null)]).toBeUndefined();
  expect(() => cadDraftKey("car", null)).toThrow("project first");
});

it("refuses to send a reference or capture to a chat in another workspace", () => {
  useSessions.setState({ activeId: "s1", sessions: [{ id: "s1", projectId: "car", cwd: "/car" }] as Session[] });
  expect(() => cadDraftKey("car", "/car-worktree")).toThrow("this model's workspace");
  expect(cadDraftKey("car", null)).toBe("s1");
});

it("does not mix worktrees in a draft and releases its root when cleared", () => {
  const key = cadDraftKey("car", "/car-worktree");
  useComposer.getState().insertReference(key, { file: "models/car.step", selector: "o1" });
  expect(() => cadDraftKey("car", null)).toThrow("already references another workspace");
  useComposer.getState().setDraft(key, "");
  expect(cadDraftKey("car", null)).toBe(key);
  expect(useComposer.getState().draftRoots[key]).toBe("/car");
});

it("adds a capture and named reference together without duplicating an existing chip", () => {
  const key = cadDraftKey("car", null);
  useComposer.getState().setDraft(key, "Make models/car.step#o1.1 wider");
  const file = new File(["png"], "view.png", { type: "image/png" });
  addToDraft("car", null, { references: [{ file: "models/car.step", selector: "o1.1", label: "wheel" }], files: [file] });
  const state = useComposer.getState();
  expect(state.drafts[key]).toBe("Make models/car.step#o1.1 wider");
  expect(state.referenceLabels[key]?.["models/car.step#o1.1"]).toBe("wheel");
  expect(state.pendingFiles[key]).toEqual([file]);
  expect(state.focusRequest?.key).toBe(key);
});

it("starts a chat in the context's workspace, preserving the old draft and bundled context", async () => {
  useSessions.setState({ activeId: "old", sessions: [{ id: "old", projectId: "car", cwd: "/car" }] as Session[] });
  useComposer.getState().setDraft("old", "Keep my unfinished request");
  const file = new File(["png"], "view.png", { type: "image/png" });
  const start = vi.spyOn(useSessions.getState(), "start").mockResolvedValue({ id: "new" } as Session);
  try {
    addToDraft("car", "/car-worktree", { references: [{ file: "models/car.step", selector: "o1" }], files: [file] });
    expect(useComposer.getState().pendingFiles.old).toBeUndefined();
    const options = vi.mocked(toast.error).mock.calls[0]?.[1];
    const action = options?.action as { label: string; onClick: () => void };
    expect(action.label).toBe("Start chat here");
    action.onClick();
    action.onClick();
    await vi.waitFor(() => expect(useComposer.getState().pendingFiles.new).toEqual([file]));
    expect(start).toHaveBeenCalledExactlyOnceWith({ projectId: "car", cwd: "/car-worktree" });
    expect(useComposer.getState().drafts.old).toBe("Keep my unfinished request");
    expect(useComposer.getState().drafts.new).toBe("models/car.step#o1 ");
  } finally { start.mockRestore(); }
});

it("retains pending context when creating a chat fails, so the action can be retried", async () => {
  const key = cadDraftKey("car", "/car-worktree");
  useComposer.getState().setDraft(key, "An existing worktree draft");
  const start = vi.spyOn(useSessions.getState(), "start").mockRejectedValueOnce(new Error("Try again")).mockResolvedValueOnce({ id: "retry" } as Session);
  try {
    addToDraft("car", null, { text: "Please revise models/car.py" });
    const clickLatest = () => {
      const options = vi.mocked(toast.error).mock.calls.at(-1)?.[1];
      (options?.action as unknown as { onClick: () => void }).onClick();
    };
    clickLatest();
    await vi.waitFor(() => expect(toast.error).toHaveBeenCalledTimes(3));
    clickLatest();
    await vi.waitFor(() => expect(useComposer.getState().drafts.retry).toBe("Please revise models/car.py"));
    expect(useComposer.getState().drafts[key]).toBe("An existing worktree draft");
  } finally { start.mockRestore(); }
});
