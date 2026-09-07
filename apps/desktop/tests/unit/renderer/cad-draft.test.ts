import { beforeEach, expect, it } from "vitest";
import { cadDraftKey } from "@renderer/state/cad-draft";
import { newSessionKey, useComposer } from "@renderer/state/composer";
import { useProjects } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";
import type { Project, Session } from "@shared/types";

beforeEach(() => {
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
